import os
import sys
from pathlib import Path

# --- Venv Guard ---
if sys.prefix == sys.base_prefix:
    if "pytest" in sys.modules:
        pass  # Let pytest handle this
    else:
        print("ERROR: Not in venv.", file=sys.stderr)
        sys.exit(2)

from PIL import Image

# --- Path Stabilization ---
script_dir = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(script_dir))
if root not in sys.path:
    sys.path.insert(0, root)

from Programma_CS2_RENAN.core.spatial_data import SPATIAL_REGISTRY


def verify_dimensions():
    # Use stabilized project root to find assets
    maps_dir = Path(root) / "Programma_CS2_RENAN" / "PHOTO_GUI" / "maps"
    print(f"{'Map Name':<15} | {'Width':<6} | {'Height':<6} | {'Status'}")
    print("-" * 45)

    for map_name in SPATIAL_REGISTRY.keys():
        path = maps_dir / f"{map_name}.png"
        if path.exists():
            with Image.open(path) as img:
                w, h = img.size
                status = "OK" if (w == 1024 and h == 1024) else f"Mismatch ({w}x{h})"
                print(f"{map_name:<15} | {w:<6} | {h:<6} | {status}")
        else:
            print(f"{map_name:<15} | {'N/A':<6} | {'N/A':<6} | Missing File")


if __name__ == "__main__":
    verify_dimensions()
