import math
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

# Path setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import METADATA_DIM
from Programma_CS2_RENAN.backend.processing.state_reconstructor import RAPStateReconstructor


# Mock PlayerTickState — duck-typed to satisfy FeatureExtractor and TensorFactory
class MockTick:
    def __init__(self, pos_x=0.0, pos_y=0.0, view_x=0.0):
        self.health = 100
        self.armor = 100
        self.is_crouching = False
        self.is_scoped = False
        self.equipment_value = 5000
        self.enemies_visible = 0
        self.is_blinded = False
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.pos_z = 0.0
        self.view_x = view_x
        self.view_y = 0.0
        self.map_name = "de_mirage"


def verify_map_integration():
    print("Verifying Map Integration (RAPStateReconstructor + FeatureExtractor)...")

    # 1. Verify metadata_dim matches unified constant
    recon = RAPStateReconstructor(map_name="de_mirage")
    print(f"Reconstructor metadata_dim: {recon.metadata_dim}")
    if recon.metadata_dim != METADATA_DIM:
        print(f"FAILED: metadata_dim should be {METADATA_DIM}")
        return False

    # 2. Call reconstruct_belief_tensors with a single mock tick
    # TensorFactory uses duck typing — MockTick provides all required fields
    tick = MockTick(pos_x=0.0, pos_y=0.0, view_x=0.0)
    result = recon.reconstruct_belief_tensors([tick])

    # 3. Verify output keys
    expected_keys = {"view", "map", "motion", "metadata"}
    missing = expected_keys - set(result.keys())
    if missing:
        print(f"FAILED: Missing output keys: {missing}")
        return False
    print(f"Output keys: {list(result.keys())}")

    # 4. Verify metadata tensor shape: (batch=1, seq_len=1, METADATA_DIM)
    metadata = result["metadata"]
    print(f"Metadata tensor shape: {metadata.shape}")
    if metadata.shape[2] != METADATA_DIM:
        print(f"FAILED: Tensor 3rd dim is {metadata.shape[2]}, expected {METADATA_DIM}")
        return False

    # 5. Spot-check feature values for known inputs
    # Current 25-dim layout (vectorizer.py):
    #   0: health/max        1: armor/max         2: has_helmet
    #   3: has_defuser       4: equipment_value   5: is_crouching
    #   6: is_scoped         7: is_blinded        8: enemies_visible
    #   9: pos_x/extent     10: pos_y/extent     11: pos_z/extent
    #  12: view_x_sin (sin of yaw for cyclic continuity)
    #  13: view_x_cos (cos of yaw for cyclic continuity)
    #  14: view_y/pitch_max 15: z_penalty        16: kast_estimate
    #  17: map_id           18: round_phase      19: weapon_class
    #  20: time_in_round    21: bomb_planted     22: teammates_alive
    #  23: enemies_alive    24: team_economy
    features = metadata[0, 0]

    health_feat = features[0].item()
    if abs(health_feat - 1.0) > 0.01:
        print(f"FAILED: health feature should be ~1.0 (100/100), got {health_feat}")
        return False

    # view_x=0 → sin(0)=0, cos(0)=1
    view_sin = features[12].item()
    view_cos = features[13].item()
    if abs(view_sin - math.sin(0.0)) > 0.01:
        print(f"FAILED: view_x_sin at idx 12 should be ~0.0, got {view_sin}")
        return False
    if abs(view_cos - math.cos(0.0)) > 0.01:
        print(f"FAILED: view_x_cos at idx 13 should be ~1.0, got {view_cos}")
        return False

    print(f"health feature: {health_feat:.3f} (expected ~1.0)")
    print(f"view_x_sin: {view_sin:.3f} (expected 0.0), view_x_cos: {view_cos:.3f} (expected 1.0)")

    print("SUCCESS: Map integration verified.")
    return True


if __name__ == "__main__":
    try:
        if verify_map_integration():
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"CRITICAL FAILURE: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
