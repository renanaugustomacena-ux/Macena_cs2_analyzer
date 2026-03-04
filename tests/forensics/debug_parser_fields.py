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

import pandas as pd
from demoparser2 import DemoParser

# Discover demo files dynamically relative to the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SEARCH_DIRS = [
    _PROJECT_ROOT / "Programma_CS2_RENAN" / "data" / "pro_demos",
    _PROJECT_ROOT / "Programma_CS2_RENAN" / "data" / "demos_to_process" / "ingest",
    _PROJECT_ROOT / "Programma_CS2_RENAN" / "data" / "demos_to_process",
]

demo_path = None
for _d in _SEARCH_DIRS:
    _hits = list(_d.glob("*.dem")) if _d.exists() else []
    if _hits:
        demo_path = str(_hits[0])
        break

if demo_path is not None and os.path.exists(demo_path):
    parser = DemoParser(demo_path)

    print("--- Testing parse_ticks ---")
    try:
        # Try a single known field first
        t = parser.parse_ticks(["player_name"])
        print(f"parse_ticks(['player_name']) success. Type: {type(t)}")
        if isinstance(t, pd.DataFrame):
            print(f"Columns: {t.columns.tolist()}")
    except Exception as e:
        print(f"parse_ticks(['player_name']) FAILED: {e}")

    print("\n--- Testing multiple fields ---")
    fields = ["player_name", "damage_total", "kills_total", "deaths_total"]
    for f in fields:
        try:
            parser.parse_ticks([f])
            print(f"Field '{f}' is valid.")
        except Exception as e:
            print(f"Field '{f}' is INVALID: {e}")

    print("\n--- Testing parse_events structure ---")
    evs = parser.parse_events(["round_end"])
    print(f"Type of parse_events result: {type(evs)}")
    if isinstance(evs, list) and len(evs) > 0:
        print(f"Type of first element: {type(evs[0])}")
        if isinstance(evs[0], tuple):
            print(f"Tuple length: {len(evs[0])}")
            print(f"Tuple[0]: {evs[0][0]}")
            print(f"Tuple[1] Type: {type(evs[0][1])}")

else:
    searched = "\n  ".join(str(d) for d in _SEARCH_DIRS)
    print(f"No .dem files found. Searched:\n  {searched}")
    print("Place a .dem file in data/pro_demos/ to use this script.")
