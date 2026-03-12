# backend/nn/config.py
import random

import numpy as np
import torch

from Programma_CS2_RENAN.core.config import get_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.nn.config")

# --- Reproducibility ---
GLOBAL_SEED = 42


def set_global_seed(seed: int = GLOBAL_SEED):
    """Set all random seeds for reproducible training runs (AR-6, P1-02)."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    logger.info("Global seed set to %d", seed)

# --- Hardware Allocation ---
_device_logged = False
_cached_device = None

# Keywords that identify integrated/low-power GPUs (should be deprioritized)
_INTEGRATED_GPU_KEYWORDS = ("uhd", "iris", "integrated", "intel")


def _select_best_cuda_device() -> torch.device:
    """Enumerate CUDA devices and prefer discrete GPU (most VRAM wins).

    On systems with both an integrated GPU and a discrete GPU (e.g. GTX 1650),
    CUDA typically only sees the NVIDIA device.  However, on multi-GPU setups
    this function picks the device with the most total memory, which reliably
    selects the discrete card.
    """
    device_count = torch.cuda.device_count()
    if device_count == 1:
        return torch.device("cuda:0")

    best_idx = 0
    best_score = -1
    for i in range(device_count):
        props = torch.cuda.get_device_properties(i)
        name_lower = props.name.lower()
        # Penalize integrated GPUs heavily so discrete always wins
        is_integrated = any(kw in name_lower for kw in _INTEGRATED_GPU_KEYWORDS)
        score = 0 if is_integrated else props.total_memory
        if score > best_score:
            best_score = score
            best_idx = i

    return torch.device(f"cuda:{best_idx}")


def get_device() -> torch.device:
    """Detects best available hardware.  Discrete GPU > integrated > CPU.

    Selection priority:
      1. User override via CUDA_DEVICE setting ("auto", "cpu", "cuda:0", etc.)
      2. Discrete NVIDIA GPU (selected by highest VRAM)
      3. CPU fallback
    """
    global _device_logged, _cached_device

    # Return cached result after first call (device doesn't change at runtime)
    if _cached_device is not None:
        return _cached_device

    # Allow user to force a specific device via settings
    user_override = get_setting("CUDA_DEVICE", "auto")
    if user_override != "auto":
        dev = torch.device(user_override)
        if not _device_logged:
            if dev.type == "cuda" and torch.cuda.is_available():
                idx = dev.index if dev.index is not None else 0
                logger.info(
                    "ML Device (user override): %s (CUDA %s)",
                    torch.cuda.get_device_name(idx),
                    torch.version.cuda,
                )
            else:
                logger.info("ML Device (user override): %s", dev)
            _device_logged = True
        _cached_device = dev
        return dev

    # Auto-detect: prefer discrete CUDA GPU
    if torch.cuda.is_available():
        dev = _select_best_cuda_device()
        idx = dev.index if dev.index is not None else 0
        if not _device_logged:
            logger.info(
                "ML Device: %s (CUDA %s, %d device(s) detected)",
                torch.cuda.get_device_name(idx),
                torch.version.cuda,
                torch.cuda.device_count(),
            )
            _device_logged = True
        _cached_device = dev
        return dev

    if not _device_logged:
        logger.info("ML Device: CPU (no CUDA GPU detected)")
        _device_logged = True
    _cached_device = torch.device("cpu")
    return _cached_device


# Data Loader
BATCH_SIZE = 32

# Model Architecture — INPUT_DIM tracks the canonical feature vector
from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

INPUT_DIM = METADATA_DIM  # Canonical 25-dim feature vector (was 19, was legacy 12)
OUTPUT_DIM = 10  # Strategy layer outputs adjustments for the first 10 core features
HIDDEN_DIM = 128  # Hidden layer size for AdvancedCoachNN / TeacherRefinementNN

# Training
LEARNING_RATE = 0.001
EPOCHS = 50

# Evaluation
WEIGHT_CLAMP = 0.5  # Max adjustment factor

# --- ML INTENSITY (Vision Alignment) ---
# High: No sleep, large batch
# Medium: Small sleep, medium batch
# Background: Baseline activity (Always active)


def get_throttling_delay():
    """Returns the sleep delay in seconds between training batches."""
    lvl = get_setting("ML_INTENSITY", "Medium")
    return {"High": 0.0, "Medium": 0.05, "Low": 0.2}.get(lvl, 0.05)


def get_intensity_batch_size():
    """Adjusts batch size to regulate memory/cache usage."""
    lvl = get_setting("ML_INTENSITY", "Medium")
    return {"High": 128, "Medium": 32, "Low": 8}.get(lvl, 32)


# --- RAP Position Scale (P9-01 extraction) ---
# Canonical scale factor for converting normalised position-delta outputs
# (model range [-1, 1]) to CS2 world-unit displacements.
# Must be used consistently in both GhostEngine and overlay code. (F3-05)
RAP_POSITION_SCALE = 500.0
