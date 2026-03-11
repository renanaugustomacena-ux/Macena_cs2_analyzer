import numpy as np
import torch

try:
    import shap

    _HAS_SHAP = True
except ImportError:
    _HAS_SHAP = False

from Programma_CS2_RENAN.backend.nn.config import WEIGHT_CLAMP
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.nn.evaluate")

# Magnitude below which unused output dimensions are considered inactive.
UNUSED_DIM_SIGNIFICANCE_THRESHOLD = 0.01


def evaluate_adjustments(model, X_sample, role_id=None):
    """
    Evaluates adjustments AND provides SHAP explanations (Item 1).
    """
    model.eval()

    # Prep tensor
    X_tensor = torch.tensor(X_sample, dtype=torch.float32)
    if X_tensor.ndim == 1:
        X_tensor = X_tensor.unsqueeze(0)

    # 1. Prediction with Role Context
    with torch.no_grad():
        adj = model(X_tensor, role_id=role_id).squeeze(0)

    # NN-12: Model outputs METADATA_DIM dimensions but only 4 are used as weights.
    # Remaining dims (indices 4-24) are unused — they could be routed to additional
    # coaching heads (utility, positioning, timing) in a future multi-head architecture.
    if adj.shape[0] > 4:
        unused_dims = adj[4:]
        unused_nonzero = (unused_dims.abs() > UNUSED_DIM_SIGNIFICANCE_THRESHOLD).sum().item()
        if unused_nonzero > 0:
            logger.debug(
                "NN-12: %d/%d unused output dims have non-trivial values (max=%.4f)",
                unused_nonzero, len(unused_dims), unused_dims.abs().max().item(),
            )

    # 2. Explanation (SHAP)
    shap_values = None
    if _HAS_SHAP:
        def model_wrapper(x):
            t = torch.tensor(x, dtype=torch.float32)
            with torch.no_grad():
                return model(t).numpy()

        # NN-EV-01: Use sample mean as SHAP baseline instead of zero-vector.
        # Zero-vector inflates importance of features with non-zero values
        # (e.g., position always > 0). The sample mean centres attributions
        # relative to a realistic reference point.
        baseline = np.mean(X_sample, axis=0, keepdims=True) if len(X_sample) > 1 else np.zeros((1, X_tensor.shape[1]))
        explainer = shap.KernelExplainer(model_wrapper, baseline)
        shap_values = explainer.shap_values(X_tensor.numpy())
    else:
        logger.warning("shap not installed — SHAP explanations unavailable. Install with: pip install shap")

    return {
        "adr_weight": float(adj[0]) * WEIGHT_CLAMP,
        "kast_weight": float(adj[1]) * WEIGHT_CLAMP,
        "hs_weight": float(adj[2]) * WEIGHT_CLAMP,
        "impact_weight": float(adj[3]) * WEIGHT_CLAMP,
        "explanations": shap_values,
    }
