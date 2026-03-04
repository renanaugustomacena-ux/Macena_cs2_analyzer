import os
import sqlite3
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

# Ensure project root is in path regardless of CWD
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

GOLDEN_DIR = Path(__file__).resolve().parent / "golden_data"
DEMO_PATH = str(GOLDEN_DIR / "golden.dem")
DB_PATH = str(GOLDEN_DIR / "golden.db")

# Comprehensive list of fields to extract
# Based on common CS2 demo analysis needs
TICK_FIELDS = [
    "tick",
    "game_time",
    "player_name",
    "steamid",
    "team_name",
    "X",
    "Y",
    "Z",
    "pitch",
    "yaw",
    "velocity_X",
    "velocity_Y",
    "velocity_Z",
    "health",
    "armor",
    "has_helmet",
    "has_defuser",
    "active_weapon",
    "total_ammo_left",
    "flash_duration",
    "is_scoped",
    "is_defusing",
    "is_walking",
    "is_strafing",
    "in_bomb_zone",
    "in_buy_zone",
    "money",
    "equipment_value",
    "ping",
]

COMMON_EVENTS = [
    "player_death",
    "player_hurt",
    "weapon_fire",
    "round_start",
    "round_end",
    "bomb_planted",
    "bomb_defused",
    "bomb_exploded",
    "flashbang_detonate",
    "smokegrenade_detonate",
    "hegrenade_detonate",
    "molotov_detonate",
]


def setup_golden_data():
    print(f"--- Setting up Golden Dataset: {DB_PATH} ---")

    if not os.path.exists(DEMO_PATH):
        print(f"ERROR: Golden demo not found at {DEMO_PATH}")
        return

    parser = DemoParser(DEMO_PATH)

    # 1. Parse Ticks (Comprehensive)
    print("Parsing ticks (this may take a moment)...")
    try:
        # Note: Some fields might not exist depending on parser version/demo,
        # so we might need to be safer, but let's try the full list.
        # If specific fields fail, demoparser2 usually ignores them or errors out.
        tick_df = parser.parse_ticks(TICK_FIELDS)
        print(f"Ticks parsed: {len(tick_df)} rows")
    except Exception as e:
        print(f"Error parsing ticks: {e}")
        # Fallback to a smaller safe list if full list fails
        print("Retrying with core fields...")
        CORE_FIELDS = [
            "tick",
            "player_name",
            "steamid",
            "team_name",
            "X",
            "Y",
            "Z",
            "pitch",
            "yaw",
            "health",
        ]
        tick_df = parser.parse_ticks(CORE_FIELDS)
        print(f"Ticks parsed (Core): {len(tick_df)} rows")

    # 2. Parse Events
    print("Parsing events...")
    events_data = {}
    for evt_name in COMMON_EVENTS:
        try:
            events = parser.parse_events([evt_name])
            if events:
                # events is a list of tuples like [(name, df), ...]
                for name, df in events:
                    events_data[name] = df
                    print(f"  - {name}: {len(df)} rows")
        except Exception as e:
            print(f"  - {evt_name}: Failed ({e})")

    # 3. Store in SQLite
    print("Saving to SQLite...")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)

    # Store Ticks
    # Rename columns to match our internal conventions if needed,
    # but for Golden Data, keeping raw names is fine as long as we map them later.
    # However, to facilitate drop-in replacement for existing tests, let's map some.
    tick_df.rename(
        columns={
            "X": "pos_x",
            "Y": "pos_y",
            "Z": "pos_z",
            "velocity_X": "vel_x",
            "velocity_Y": "vel_y",
            "velocity_Z": "vel_z",
        },
        inplace=True,
        errors="ignore",
    )

    tick_df.to_sql("ticks", conn, index=False, if_exists="replace")

    # Store Events
    for name, df in events_data.items():
        df.to_sql(f"evt_{name}", conn, index=False, if_exists="replace")

    # Store Metadata (Map Name, Header)
    try:
        header = parser.parse_header()
        # Header is usually a dict
        meta_df = pd.DataFrame([header])
        meta_df.to_sql("metadata", conn, index=False, if_exists="replace")
        print("Metadata saved.")
    except Exception as e:
        print(f"Metadata error: {e}")

    conn.close()
    print("Golden Dataset Setup Complete.")


if __name__ == "__main__":
    setup_golden_data()
