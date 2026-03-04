import sys
from pathlib import Path

# --- Venv Guard ---
if sys.prefix == sys.base_prefix:
    if "pytest" in sys.modules:
        pass  # Let pytest handle this
    else:
        print("ERROR: Not in venv.", file=sys.stderr)
        sys.exit(2)

from demoparser2 import DemoParser

# Discover first available .dem file from the pro_demos directory
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PRO_DEMOS_DIR = _PROJECT_ROOT / "Programma_CS2_RENAN" / "data" / "pro_demos"
_demo_files = sorted(_PRO_DEMOS_DIR.glob("*.dem")) if _PRO_DEMOS_DIR.exists() else []
if not _demo_files:
    print(f"No .dem files in {_PRO_DEMOS_DIR} — place a demo there to use this script.")
    raise SystemExit(0)

path = str(_demo_files[0])
print(f"Using demo: {path}")
parser = DemoParser(path)

print("--- smokegrenade_detonate ---")
res = parser.parse_events(["smokegrenade_detonate"])
if res:
    df = res[0][1]
    print(df.columns.tolist())
    if not df.empty:
        print(df.iloc[0].to_dict())

print("\n--- grenade_thrown ---")
res = parser.parse_events(["grenade_thrown"])
if res:
    df = res[0][1]
    print(df.columns.tolist())
    if not df.empty:
        print(df.iloc[0].to_dict())
