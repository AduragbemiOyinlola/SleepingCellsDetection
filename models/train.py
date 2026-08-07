"""
models/train.py — 5-fold grouped cross-validation for the sleeping-cell classifier
====================================================================================
Usage
-----
    python models/train.py \
        --data_dir   Dataset_clean \
        --arch       resnet18 \
        --n_splits   5 \
        --epochs     30 \
        --batch      16 \
        --lr         1e-4 \
        --output_dir models/weights

Dataset structure expected
--------------------------
    Dataset_clean/
        train/  val/  test/
            healthy/     *.png
            sleeping/    *.png

Mirrors SleepingCell_CrossValidation.ipynb exactly: every image across
train/val/test is pooled together, grouped by underlying cell ID *and*
by post-crop pixel content (some different cell IDs render identical
charts once the title is stripped), then split with StratifiedGroupKFold
so no group's images can ever cross a fold's train/test boundary. This
is what prevents the leakage found in earlier, per-image random splits.

Each fold trains a fresh model and is evaluated once on its held-out
fold; results are reported per-fold, as mean +/- std across folds, and
as a single pooled out-of-fold report (every image evaluated exactly
once, by a model that never saw it during training). Each fold's best
weights are also saved, matching how sleeping_cell_model_fold{N}.pt
files are produced.
"""

import argparse
import os
import re
import copy
import random
import hashlib
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.optim import Adam
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torchvision import models, transforms
from torch.utils.data import DataLoader, Dataset
from sklearn.model_selection import StratifiedGroupKFold, GroupShuffleSplit
from sklearn.metrics import classification_report, confusion_matrix


# ─── Reproducibility ──────────────────────────────────────────────────────────

def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def worker_init_fn(worker_id):
    seed = torch.initial_seed() % (2**32)
    np.random.seed(seed)
    random.seed(seed)


# ─── Argument parsing ─────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Grouped cross-validation for sleeping cell detection")
    p.add_argument("--data_dir",    default="Dataset_clean", help="Root containing train/val/test dirs")
    p.add_argument("--arch",        default="resnet18",      choices=["resnet18", "resnet50"])
    p.add_argument("--n_splits",    default=5,   type=int, help="Number of grouped CV folds")
    p.add_argument("--epochs",      default=30,  type=int)
    p.add_argument("--batch",       default=16,  type=int)
    p.add_argument("--lr",          default=1e-4, type=float)
    p.add_argument("--workers",     default=4,   type=int)
    p.add_argument("--output_dir",  default="models/weights")
    p.add_argument("--threshold",   default=0.5, type=float, help="Decision threshold")
    p.add_argument("--seed",        default=42,  type=int, help="Random seed for reproducibility")
    p.add_argument("--inner_val_fraction", default=0.12, type=float,
                   help="Fraction of each fold's training pool carved off for early stopping")
    return p.parse_args()


# ─── Pooling + leak-safe grouping ─────────────────────────────────────────────

FILENAME_PATTERN = re.compile(r"^(?:(\d[A-Z])_)?([A-Z]+)_(.+)\.png$", re.IGNORECASE)


def pool_dataset(data_dir):
    """Pool every image across train/val/test, hashing content and parsing the
    underlying cell ID out of the filename (handles both '3G_PS_<id>.png' and
    the tech-prefix-less 2G '<plot>_<id>.png' naming)."""
    records = []
    for split in ["train", "val", "test"]:
        for cls in ["healthy", "sleeping"]:
            d = os.path.join(data_dir, split, cls)
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                p = os.path.join(d, fn)
                m = FILENAME_PATTERN.match(fn)
                _, _, base_id = m.groups()
                with open(p, "rb") as f:
                    content_hash = hashlib.md5(f.read()).hexdigest()
                records.append({"path": p, "cls": cls, "base_id": base_id, "content_hash": content_hash})
    return records


def build_groups(records):
    """Union-find: merge records sharing (class, base_id) OR (class, content_hash),
    so images of the same cell and images with identical rendered content both end
    up in the same group and can never be split across a fold's train/test."""
    parent = list(range(len(records)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_base, by_hash = defaultdict(list), defaultdict(list)
    for i, r in enumerate(records):
        by_base[(r["cls"], r["base_id"])].append(i)
        by_hash[(r["cls"], r["content_hash"])].append(i)
    for idxs in by_base.values():
        for i in idxs[1:]:
            union(idxs[0], i)
    for idxs in by_hash.values():
        for i in idxs[1:]:
            union(idxs[0], i)

    return np.array([find(i) for i in range(len(records))])


class ListDataset(Dataset):
    """Dataset over an explicit list of file paths + labels, since pooling
    across train/val/test rules out torchvision.datasets.ImageFolder."""

    def __init__(self, paths, labels, transform):
        self.paths, self.labels, self.transform = paths, labels, transform

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, idx):
        img = Image.open(self.paths[idx]).convert("RGB")
        return self.transform(img), self.labels[idx]


# ─── Data transforms ──────────────────────────────────────────────────────────

def get_transforms():
    train_tf = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(8),
        transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.1),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225]),
    ])
    val_tf = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225]),
    ])
    return train_tf, val_tf


# ─── Model builder ────────────────────────────────────────────────────────────

def build_model(arch: str, device):
    if arch == "resnet50":
        base = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
    else:
        base = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)

    in_features = base.fc.in_features
    base.fc = nn.Sequential(
        nn.Linear(in_features, 256),
        nn.ReLU(),
        nn.Dropout(0.4),
        nn.Linear(256, 1),
        nn.Sigmoid(),
    )
    return base.to(device)


# ─── Per-fold training ────────────────────────────────────────────────────────

def train_fold(fold_idx, train_pool_idx, test_idx, paths, labels, group_ids,
               train_tf, val_tf, device, args):
    set_seed(args.seed + fold_idx)

    # inner grouped split: carve a val set out of this fold's training pool for early stopping
    gss = GroupShuffleSplit(n_splits=1, test_size=args.inner_val_fraction, random_state=args.seed + fold_idx)
    inner_train_rel, inner_val_rel = next(gss.split(
        train_pool_idx, labels[train_pool_idx], group_ids[train_pool_idx]))
    train_idx = train_pool_idx[inner_train_rel]
    val_idx = train_pool_idx[inner_val_rel]

    train_ds = ListDataset(paths[train_idx].tolist(), labels[train_idx], train_tf)
    val_ds = ListDataset(paths[val_idx].tolist(), labels[val_idx], val_tf)
    test_ds = ListDataset(paths[test_idx].tolist(), labels[test_idx], val_tf)

    gen = torch.Generator()
    gen.manual_seed(args.seed + fold_idx)
    train_dl = DataLoader(train_ds, batch_size=args.batch, shuffle=True,
                          num_workers=args.workers, pin_memory=True,
                          generator=gen, worker_init_fn=worker_init_fn)
    val_dl = DataLoader(val_ds, batch_size=args.batch, shuffle=False,
                        num_workers=args.workers, pin_memory=True,
                        worker_init_fn=worker_init_fn)
    test_dl = DataLoader(test_ds, batch_size=args.batch, num_workers=args.workers)

    class_counts = torch.tensor([
        (labels[train_idx] == 0).sum(), (labels[train_idx] == 1).sum()], dtype=torch.float)
    w0, w1 = class_counts[1] / class_counts.sum(), class_counts[0] / class_counts.sum()

    model = build_model(args.arch, device)
    criterion = nn.BCELoss()
    optimiser = Adam(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = ReduceLROnPlateau(optimiser, mode="min", patience=5, factor=0.5)

    best_val_loss, best_weights, patience_count = float("inf"), None, 0
    EARLY_STOP = 10

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        for imgs, lbls in train_dl:
            imgs = imgs.to(device)
            lbls = lbls.float().unsqueeze(1).to(device)
            sample_w = torch.where(lbls == 1,
                                   torch.tensor(w1, device=device),
                                   torch.tensor(w0, device=device))
            preds = model(imgs)
            loss = (criterion(preds, lbls) * sample_w).mean()
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            train_loss += loss.item()

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for imgs, lbls in val_dl:
                imgs = imgs.to(device)
                lbls = lbls.float().unsqueeze(1).to(device)
                preds = model(imgs)
                val_loss += criterion(preds, lbls).item()
        train_loss /= len(train_dl)
        val_loss /= max(1, len(val_dl))
        scheduler.step(val_loss)

        print(f"  Fold {fold_idx}  Epoch {epoch:3d}/{args.epochs}  "
              f"train_loss={train_loss:.4f}  val_loss={val_loss:.4f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_weights = copy.deepcopy(model.state_dict())
            patience_count = 0
        else:
            patience_count += 1
            if patience_count >= EARLY_STOP:
                print(f"  Fold {fold_idx}  early stopping at epoch {epoch}.")
                break

    model.load_state_dict(best_weights)
    model.eval()
    fold_preds = []
    with torch.no_grad():
        for imgs, lbls in test_dl:
            preds = model(imgs.to(device))
            fold_preds.extend((preds.cpu() >= args.threshold).int().flatten().tolist())

    return best_weights, np.array(fold_preds)


# ─── Cross-validation driver ──────────────────────────────────────────────────

def cross_validate(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    print(f"Seed: {args.seed}")

    records = pool_dataset(args.data_dir)
    print(f"Pooled images: {len(records)}")

    group_ids = build_groups(records)
    paths = np.array([r["path"] for r in records])
    labels = np.array([0 if r["cls"] == "healthy" else 1 for r in records])
    print(f"Distinct groups: {len(set(group_ids))}")
    print(f"healthy images: {(labels == 0).sum()}  sleeping images: {(labels == 1).sum()}")

    train_tf, val_tf = get_transforms()

    skf = StratifiedGroupKFold(n_splits=args.n_splits, shuffle=True, random_state=args.seed)
    outer_folds = list(skf.split(paths, labels, group_ids))
    for i, (tr, te) in enumerate(outer_folds):
        print(f"Fold {i}: train_pool={len(tr)}  test={len(te)}  "
              f"test_healthy={(labels[te]==0).sum()}  test_sleeping={(labels[te]==1).sum()}")

    os.makedirs(args.output_dir, exist_ok=True)

    oof_preds = np.full(len(paths), -1, dtype=int)
    fold_reports = []

    for fold_idx, (train_pool_idx, test_idx) in enumerate(outer_folds):
        print(f"\n{'='*60}\nFOLD {fold_idx}\n{'='*60}")
        best_weights, fold_preds = train_fold(
            fold_idx, train_pool_idx, test_idx, paths, labels, group_ids,
            train_tf, val_tf, device, args)

        oof_preds[test_idx] = fold_preds
        fold_true = labels[test_idx]

        report_dict = classification_report(fold_true, fold_preds, target_names=["healthy", "sleeping"],
                                             zero_division=0, output_dict=True)
        print(classification_report(fold_true, fold_preds, target_names=["healthy", "sleeping"], zero_division=0))
        print("Confusion matrix:")
        print(confusion_matrix(fold_true, fold_preds))
        fold_reports.append(report_dict)

        fold_output = os.path.join(args.output_dir, f"sleeping_cell_model_fold{fold_idx}.pt")
        torch.save(best_weights, fold_output)
        print(f"Fold {fold_idx} weights saved -> {fold_output}")

    assert (oof_preds >= 0).all(), "Every sample should have exactly one out-of-fold prediction"

    print("\nPer-fold summary (sleeping class):")
    accs, sl_prec, sl_rec, sl_f1 = [], [], [], []
    for i, rep in enumerate(fold_reports):
        accs.append(rep["accuracy"])
        sl_prec.append(rep["sleeping"]["precision"])
        sl_rec.append(rep["sleeping"]["recall"])
        sl_f1.append(rep["sleeping"]["f1-score"])
        print(f"  fold {i}: acc={rep['accuracy']:.3f}  sleeping_precision={rep['sleeping']['precision']:.3f}  "
              f"sleeping_recall={rep['sleeping']['recall']:.3f}  sleeping_f1={rep['sleeping']['f1-score']:.3f}")

    summary = (
        f"\nMean +/- std across {args.n_splits} folds:\n"
        f"  accuracy:            {np.mean(accs):.3f} +/- {np.std(accs):.3f}\n"
        f"  sleeping precision:  {np.mean(sl_prec):.3f} +/- {np.std(sl_prec):.3f}\n"
        f"  sleeping recall:     {np.mean(sl_rec):.3f} +/- {np.std(sl_rec):.3f}\n"
        f"  sleeping f1:         {np.mean(sl_f1):.3f} +/- {np.std(sl_f1):.3f}\n"
    )
    print(summary)

    print("\n── Pooled out-of-fold report (every sample evaluated exactly once, never during its own training) ──")
    pooled_report = classification_report(labels, oof_preds, target_names=["healthy", "sleeping"], zero_division=0)
    print(pooled_report)
    pooled_cm = confusion_matrix(labels, oof_preds)
    print("Pooled confusion matrix:")
    print(pooled_cm)

    report_path = os.path.join(args.output_dir, "cv_report.txt")
    with open(report_path, "w") as f:
        f.write(f"{args.n_splits}-fold grouped stratified cross-validation, seed={args.seed}\n\n")
        f.write(summary)
        f.write("\nPooled out-of-fold report:\n")
        f.write(pooled_report)
        f.write("\nPooled confusion matrix (rows=true, cols=pred, order=[healthy, sleeping]):\n")
        f.write(str(pooled_cm))
    print(f"\nSaved -> {report_path}")


if __name__ == "__main__":
    cross_validate(parse_args())
