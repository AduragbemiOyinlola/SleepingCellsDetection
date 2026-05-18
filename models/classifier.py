"""
models/classifier.py — ResNet-18 / ResNet-50 sleeping cell classifier
=======================================================================
This module provides:
  • SleepingCellClassifier  — the model wrapper
  • classify_plots()        — batch classification for all cells

Transfer-learning setup
-----------------------
The model is a pretrained ResNet with its final FC layer replaced by a
single-output binary head + sigmoid.  Fine-tune it on your labelled
plot dataset using train.py (included separately as a training script).

Inference without weights file
-------------------------------
If MODEL_MOCK=1 (default) or no weights file is found, the classifier
runs in probabilistic mock mode — returning random but reproducible
logits so the UI pipeline can be demonstrated end-to-end without GPU.
"""

import io
import os
import random
from typing import Dict, Tuple

import numpy as np
from PIL import Image

from utils.config import (
    MODEL_ARCH,
    MODEL_WEIGHTS_PATH,
    MODEL_MOCK,
    DECISION_THRESHOLD,
)


# ─── Optional PyTorch import ──────────────────────────────────────────────────

try:
    import torch
    import torch.nn as nn
    from torchvision import models, transforms
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


# ─── Image pre-processing ─────────────────────────────────────────────────────

_IMG_SIZE = 224

_preprocess = None   # lazy init

def _get_transform():
    global _preprocess
    if _preprocess is None:
        if _TORCH_AVAILABLE:
            _preprocess = transforms.Compose([
                transforms.Resize((_IMG_SIZE, _IMG_SIZE)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std =[0.229, 0.224, 0.225],
                ),
            ])
        else:
            _preprocess = lambda img: img   # no-op placeholder
    return _preprocess


# ─── Model ───────────────────────────────────────────────────────────────────

class SleepingCellClassifier:
    """
    Wraps a fine-tuned ResNet for binary sleeping-cell classification.

    Parameters
    ----------
    arch    : "resnet18" | "resnet50"
    weights : path to a saved .pt state-dict (optional)
    mock    : if True, skip PyTorch entirely and return simulated predictions
    """

    def __init__(
        self,
        arch: str = MODEL_ARCH,
        weights: str = MODEL_WEIGHTS_PATH,
        mock: bool = MODEL_MOCK,
    ):
        self.arch  = arch
        self.mock  = mock or (not _TORCH_AVAILABLE)
        self.model = None
        self.device = None

        if not self.mock:
            self._load_model(weights)

    # ── loading ──────────────────────────────────────────────────────────────

    def _load_model(self, weights_path: str):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        if self.arch == "resnet50":
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
        self.model = base.to(self.device)
        self.model.eval()

        if os.path.exists(weights_path):
            state = torch.load(weights_path, map_location=self.device)
            self.model.load_state_dict(state)
            print(f"[Classifier] Loaded weights from {weights_path}")
        else:
            print(f"[Classifier] Weights not found at {weights_path} — using ImageNet init.")

    # ── inference ────────────────────────────────────────────────────────────

    def predict(self, png_bytes: bytes, cell_id: str = "") -> Tuple[float, int]:
        """
        Predict whether a diagnostic plot shows a sleeping cell.

        Parameters
        ----------
        png_bytes : raw PNG image bytes
        cell_id   : used for deterministic mock seeding

        Returns
        -------
        prob  : float in [0, 1]  — probability of sleeping cell
        label : int  0 or 1
        """
        if self.mock:
            return self._mock_predict(cell_id, png_bytes)

        transform = _get_transform()
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        tensor = transform(img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            prob = self.model(tensor).item()

        label = 1 if prob >= DECISION_THRESHOLD else 0
        return prob, label

    @staticmethod
    def _mock_predict(cell_id: str, png_bytes: bytes) -> Tuple[float, int]:
        """
        Deterministic fake prediction based on cell_id hash.
        Simulates model output so the UI can be demonstrated without PyTorch.
        """
        seed = int(abs(hash(cell_id + str(len(png_bytes)))) % (2**32))
        rng  = random.Random(seed)

        # Bias toward "healthy" at 65 % to feel realistic
        is_sleep = rng.random() < 0.35
        if is_sleep:
            prob = rng.uniform(0.62, 0.98)
        else:
            prob = rng.uniform(0.04, 0.44)

        label = 1 if prob >= DECISION_THRESHOLD else 0
        return round(prob, 4), label


# ─── Batch classification ─────────────────────────────────────────────────────

_classifier_singleton: SleepingCellClassifier | None = None


def _get_classifier() -> SleepingCellClassifier:
    global _classifier_singleton
    if _classifier_singleton is None:
        _classifier_singleton = SleepingCellClassifier()
    return _classifier_singleton


def classify_plots(
    plots: Dict[str, Dict[str, bytes]],
    progress_callback=None,
) -> Tuple[Dict[str, Dict], list]:
    """
    Classify CS and PS plots for every cell.

    Decision logic (logical OR):
        A cell is confirmed sleeping if EITHER the CS plot OR the PS plot
        is classified positive.  This matches Section 3.10 of the project.

    Returns
    -------
    classifications : {
        cell_id: {
            "cs_prob":  float,
            "cs_label": int,
            "ps_prob":  float,
            "ps_label": int,
            "final":    int,   # 1 = sleeping, 0 = healthy
        }
    }
    log_lines : list of status strings
    """
    clf       = _get_classifier()
    results   = {}
    log_lines = []
    total     = len(plots)

    for i, (cid, plot_pair) in enumerate(plots.items()):
        if progress_callback:
            progress_callback((i + 1) / total, f"Classifying {cid}…")

        cs_prob, cs_label = clf.predict(plot_pair["cs"], cell_id=cid + "_cs")
        ps_prob, ps_label = clf.predict(plot_pair["ps"], cell_id=cid + "_ps")

        # OR decision rule
        final = 1 if (cs_label == 1 or ps_label == 1) else 0

        results[cid] = {
            "cs_prob":  cs_prob,
            "cs_label": cs_label,
            "ps_prob":  ps_prob,
            "ps_label": ps_label,
            "final":    final,
        }

        verdict = "SLEEPING ⚠" if final == 1 else "healthy ✓"
        log_lines.append(
            f"{cid}: CS={cs_prob:.3f} PS={ps_prob:.3f} → {verdict}"
        )

    return results, log_lines