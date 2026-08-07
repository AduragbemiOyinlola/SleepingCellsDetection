"""
models/train.py — Fine-tune ResNet-18/50 on labelled sleeping-cell plots
=========================================================================
Usage
-----
    python models/train.py \
        --data_dir  data/plots \
        --arch      resnet18 \
        --epochs    30 \
        --batch     16 \
        --lr        1e-4 \
        --output    models/weights/sleeping_cell_model.pt

Dataset structure expected
--------------------------
    data/plots/
        train/
            sleeping/    *.png
            healthy/     *.png
        val/
            sleeping/    *.png
            healthy/     *.png
        test/           (optional — evaluated at end)
            sleeping/    *.png
            healthy/     *.png

This matches the torchvision.datasets.ImageFolder convention.

Class weights
-------------
Computed automatically from class frequencies in the training set
to handle the sleeping-cell class imbalance described in Chapter 3.
"""

import argparse
import os
import copy
import random

import numpy as np
import torch
import torch.nn as nn
from torch.optim import Adam
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torchvision import datasets, models, transforms
from torch.utils.data import DataLoader
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
    p = argparse.ArgumentParser(description="Fine-tune ResNet for sleeping cell detection")
    p.add_argument("--data_dir", default="data/plots",    help="Root of train/val/test dirs")
    p.add_argument("--arch",     default="resnet18",       choices=["resnet18","resnet50"])
    p.add_argument("--epochs",   default=30,  type=int)
    p.add_argument("--batch",    default=16,  type=int)
    p.add_argument("--lr",       default=1e-4, type=float)
    p.add_argument("--workers",  default=4,   type=int)
    p.add_argument("--output",   default="models/weights/sleeping_cell_model.pt")
    p.add_argument("--threshold",default=0.5, type=float, help="Decision threshold")
    p.add_argument("--seed",     default=42,  type=int, help="Random seed for reproducibility")
    return p.parse_args()


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


# ─── Training loop ────────────────────────────────────────────────────────────

def train(args):
    set_seed(args.seed)
    print(f"Seed: {args.seed}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    train_tf, val_tf = get_transforms()

    train_ds = datasets.ImageFolder(os.path.join(args.data_dir, "train"), train_tf)
    val_ds   = datasets.ImageFolder(os.path.join(args.data_dir, "val"),   val_tf)

    gen = torch.Generator()
    gen.manual_seed(args.seed)

    train_dl = DataLoader(train_ds, batch_size=args.batch, shuffle=True,
                          num_workers=args.workers, pin_memory=True,
                          generator=gen, worker_init_fn=worker_init_fn)
    val_dl   = DataLoader(val_ds,   batch_size=args.batch, shuffle=False,
                          num_workers=args.workers, pin_memory=True,
                          worker_init_fn=worker_init_fn)

    # Class weights (inverse frequency)
    class_counts = torch.tensor(
        [train_ds.targets.count(i) for i in range(len(train_ds.classes))],
        dtype=torch.float,
    )
    w0, w1 = class_counts[1] / class_counts.sum(), class_counts[0] / class_counts.sum()
    print(f"Class weights — healthy: {w0:.3f}  sleeping: {w1:.3f}")

    # sleeping class index  (ImageFolder sorts alphabetically: healthy=0, sleeping=1)
    sleeping_idx = train_ds.class_to_idx.get("sleeping", 1)
    w_pos = class_counts[1 - sleeping_idx] / class_counts.sum()

    model     = build_model(args.arch, device)
    criterion = nn.BCELoss()
    optimiser = Adam(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = ReduceLROnPlateau(optimiser, mode="min", patience=5, factor=0.5)

    best_val_loss  = float("inf")
    best_weights   = None
    patience_count = 0
    EARLY_STOP     = 10

    for epoch in range(1, args.epochs + 1):
        # ── Train ──────────────────────────────────────────────
        model.train()
        train_loss = 0.0
        for imgs, labels in train_dl:
            imgs   = imgs.to(device)
            labels = labels.float().unsqueeze(1).to(device)

            # Per-sample weight
            sample_w = torch.where(labels == sleeping_idx,
                                   torch.tensor(w1, device=device),
                                   torch.tensor(w0, device=device))
            preds  = model(imgs)
            loss   = (criterion(preds, labels) * sample_w).mean()

            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            train_loss += loss.item()

        # ── Validate ───────────────────────────────────────────
        model.eval()
        val_loss = 0.0
        all_preds, all_labels = [], []
        with torch.no_grad():
            for imgs, labels in val_dl:
                imgs   = imgs.to(device)
                labels = labels.float().unsqueeze(1).to(device)
                preds  = model(imgs)
                val_loss += criterion(preds, labels).item()
                all_preds.extend((preds.cpu() >= args.threshold).int().tolist())
                all_labels.extend(labels.int().cpu().tolist())

        train_loss /= len(train_dl)
        val_loss   /= len(val_dl)
        scheduler.step(val_loss)

        # Flatten nested lists
        all_preds  = [p[0] if isinstance(p, list) else p for p in all_preds]
        all_labels = [l[0] if isinstance(l, list) else l for l in all_labels]

        correct = sum(p == l for p, l in zip(all_preds, all_labels))
        acc     = correct / len(all_labels) * 100

        print(f"Epoch {epoch:3d}/{args.epochs}  "
              f"train_loss={train_loss:.4f}  val_loss={val_loss:.4f}  "
              f"val_acc={acc:.1f}%")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_weights  = copy.deepcopy(model.state_dict())
            patience_count = 0
        else:
            patience_count += 1
            if patience_count >= EARLY_STOP:
                print(f"Early stopping at epoch {epoch}.")
                break

    # ── Save ───────────────────────────────────────────────────
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    torch.save(best_weights, args.output)
    print(f"\nBest model saved → {args.output}")

    # ── Test evaluation (optional) ─────────────────────────────
    test_dir = os.path.join(args.data_dir, "test")
    if os.path.isdir(test_dir):
        test_ds = datasets.ImageFolder(test_dir, val_tf)
        test_dl = DataLoader(test_ds, batch_size=args.batch, num_workers=args.workers)

        model.load_state_dict(best_weights)
        model.eval()
        all_preds, all_labels = [], []
        with torch.no_grad():
            for imgs, labels in test_dl:
                preds = model(imgs.to(device))
                all_preds.extend((preds.cpu() >= args.threshold).int().tolist())
                all_labels.extend(labels.tolist())

        all_preds  = [p[0] if isinstance(p, list) else p for p in all_preds]
        print("\n── Test Set Report ──────────────────────────────────────")
        print(classification_report(
            all_labels, all_preds,
            target_names=test_ds.classes,
            zero_division=0,
        ))
        print("Confusion matrix:")
        print(confusion_matrix(all_labels, all_preds))


if __name__ == "__main__":
    train(parse_args())