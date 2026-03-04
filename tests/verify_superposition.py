import os
import sys

# --- Venv Guard ---
if sys.prefix == sys.base_prefix:
    if "pytest" in sys.modules:
        pass  # Let pytest handle this
    else:
        print("ERROR: Not in venv.", file=sys.stderr)
        sys.exit(2)

import torch
import torch.nn as nn

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from Programma_CS2_RENAN.backend.nn.layers.superposition import SuperpositionLayer
from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel
from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import METADATA_DIM


def verify_superposition_logic():
    print("--- Verifying Superposition Layer ---")
    layer = SuperpositionLayer(in_features=10, out_features=5, context_dim=18)

    x = torch.randn(1, 10)

    # Context A (e.g., Eco Round)
    ctx_a = torch.zeros(1, 18)
    out_a = layer(x, ctx_a)

    # Context B (e.g., Full Buy)
    ctx_b = torch.ones(1, 18)
    out_b = layer(x, ctx_b)

    # Outputs should differ solely due to context
    diff = (out_a - out_b).abs().sum().item()
    print(f"Output Difference between Contexts: {diff:.4f}")

    if diff < 1e-5:
        print("FAILED: Superposition layer did not adapt to context.")
        return False

    print("SUCCESS: Superposition layer verified.")
    return True


def verify_full_model_integration():
    print("\n--- Verifying RAPCoachModel Integration ---")
    # Init model with current METADATA_DIM constant
    model = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
    print("Model instantiated successfully.")

    # Check for core heads (RAPCoachModel has position_head and pedagogy, not stability_head)
    if not hasattr(model, "position_head"):
        print("FAILED: Position Head missing.")
        return False

    if not hasattr(model, "pedagogy"):
        print("FAILED: Pedagogy Head missing.")
        return False

    # Dummy Inputs
    batch_size = 2
    seq_len = 5

    view_frame = torch.randn(batch_size, 3, 224, 224)  # Image
    map_frame = torch.randn(batch_size, 3, 64, 64)  # Map
    motion_diff = torch.randn(batch_size, 3, 64, 64)  # Motion
    metadata = torch.randn(batch_size, seq_len, METADATA_DIM)  # Context

    output = model(view_frame, map_frame, motion_diff, metadata)

    # Check for expected output keys (value_estimate, optimal_pos, attribution)
    value_v = output.get("value_estimate")
    if value_v is None:
        print("FAILED: Output missing 'value_estimate'")
        return False

    print(f"Value Estimate Output Shape: {value_v.shape}")

    optimal_pos = output.get("optimal_pos")
    if optimal_pos is None or optimal_pos.shape != (batch_size, 3):
        print("FAILED: Output missing or incorrect shape for 'optimal_pos'")
        return False

    print(f"Optimal Pos Output Shape: {optimal_pos.shape} (Expected [{batch_size}, 3])")

    print("SUCCESS: Full Model Integration verified.")
    return True


if __name__ == "__main__":
    try:
        res1 = verify_superposition_logic()
        res2 = verify_full_model_integration()

        if res1 and res2:
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
