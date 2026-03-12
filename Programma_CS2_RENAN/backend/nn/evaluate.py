import numpy as np
import torch

try:
    import shap

    _HAS_SHAP = True
except ImportError:
    _HAS_SHAP = False

from Programma_CS2_RENAN.backend.nn.coach_manager import MATCH_AGGREGATE_FEATURES
from Programma_CS2_RENAN.backend.nn.config import WEIGHT_CLAMP
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.nn.evaluate")


def evaluate_adjustments(model, X_sample, role_id=None):
    """
    Evaluates adjustments AND provides SHAP explanations (Item 1).

    Returns a dict with one ``{feature}_weight`` key per MATCH_AGGREGATE_FEATURES
    entry (25 total) plus an ``explanations`` key for SHAP values.
    """
    model.eval()

    # Prep tensor
    X_tensor = torch.tensor(X_sample, dtype=torch.float32)
    if X_tensor.ndim == 1:
        X_tensor = X_tensor.unsqueeze(0)

    # 1. Prediction with Role Context
    with torch.no_grad():
        adj = model(X_tensor, role_id=role_id).squeeze(0)

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

    # Build adjustment dict for the first OUTPUT_DIM features (10 of 25).
    # Remaining features have no NN adjustment. Keys follow "{feature}_weight".
    adjustments = {}
    for i, feature_name in enumerate(MATCH_AGGREGATE_FEATURES):
        if i < adj.shape[0]:
            adjustments[f"{feature_name}_weight"] = float(adj[i]) * WEIGHT_CLAMP

    adjustments["explanations"] = shap_values
    return adjustments
