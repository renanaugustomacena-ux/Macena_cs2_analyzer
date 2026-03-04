import os
import shutil
import sys
from pathlib import Path

# --- Venv Guard ---
if sys.prefix == sys.base_prefix:
    if "pytest" in sys.modules:
        pass  # Let pytest handle this
    else:
        print("ERROR: Not in venv.", file=sys.stderr)
        sys.exit(2)

# Path setup — anchored to this file's location, not CWD
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
_TEST_REPORTS_DIR = str(Path(__file__).resolve().parent / "test_reports")

from Programma_CS2_RENAN.reporting.report_generator import MatchReportGenerator
from Programma_CS2_RENAN.reporting.visualizer import MatchVisualizer


def verify_visualizer():
    print("--- Verifying Visualizer (REAL DATA) ---")

    # 1. Fetch Real Data
    from Programma_CS2_RENAN.backend.storage.match_data_manager import get_match_data_manager

    mgr = get_match_data_manager()
    matches = mgr.list_available_matches()

    if not matches:
        print("FAILED: No matches in DB to generate report from.")
        return False

    match_id = matches[0]
    ticks = mgr.get_ticks_for_round(match_id, 1) or mgr.get_ticks_for_round(match_id, 2)

    if not ticks:
        print("FAILED: No ticks found in match.")
        return False

    # Extract positions (X, Y) from real ticks
    real_positions = [(t.pos_x, t.pos_y) for t in ticks]
    print(f"    Fetched {len(real_positions)} real coordinates.")

    viz = MatchVisualizer(output_dir=_TEST_REPORTS_DIR)

    # Use real map name and real positions
    meta = mgr.get_metadata(match_id)
    map_name = meta.map_name if meta else "de_mirage"

    path = viz.generate_heatmap(real_positions, map_name, f"Real_Heatmap_{match_id}")

    if os.path.exists(path):
        print(f"SUCCESS: Heatmap generated at {path}")
        return True
    else:
        print("FAILED: Heatmap file not created.")
        return False


def verify_generator_stub():
    print("\n--- Verifying Generator Class ---")
    # We can't easily test full generation without a real .dem file and DB connection
    # So we just verify instantiation

    try:
        gen = MatchReportGenerator(db_manager=None)
        print("SUCCESS: MatchReportGenerator instantiated.")
        return True
    except Exception as e:
        print(f"FAILED: Instantiation error: {e}")
        return False


if __name__ == "__main__":
    if os.path.exists(_TEST_REPORTS_DIR):
        shutil.rmtree(_TEST_REPORTS_DIR)

    v_res = verify_visualizer()
    g_res = verify_generator_stub()

    if v_res and g_res:
        print("\nReporting System Verified.")
    else:
        print("\nReporting System Verification FAILED.")
        sys.exit(1)
