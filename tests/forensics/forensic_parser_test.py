import os
import sys

# --- Venv Guard ---
if sys.prefix == sys.base_prefix:
    if "pytest" in sys.modules:
        pass  # Let pytest handle this
    else:
        print("ERROR: Not in venv.", file=sys.stderr)
        sys.exit(2)

import pandas as pd
import pytest
from demoparser2 import DemoParser


def test_extraction_pro_sample():
    """Verify that we can extract data from a real pro demo in the data folder."""
    # Resolve relative to project root
    demo_p = os.path.join(
        "Programma_CS2_RENAN", "data", "pro_demos", "furia-vs-natus-vincere-m1-mirage.dem"
    )

    if not os.path.exists(demo_p):
        pytest.skip("Pro sample demo not found for forensic test.")

    parser = DemoParser(demo_p)
    fields = ["player_name", "name", "damage_total", "kills_total", "deaths_total"]

    # 1. Parse Ticks
    raw = parser.parse_ticks(fields)
    final = pd.DataFrame(raw)
    assert not final.empty, "DataFrame should not be empty"

    # 2. Identify Column
    p_col = next((c for c in ["player_name", "name"] if c in final.columns), None)
    assert p_col is not None, "Identity column must exist"

    # 3. Grouping Logic Verification
    final = final.rename(columns={p_col: "std_player_name"}).fillna(0)
    totals = (
        final.groupby("std_player_name")
        .agg({"kills_total": "max", "deaths_total": "max", "damage_total": "max"})
        .reset_index()
    )

    assert len(totals) > 0, "Should find players in the demo"
    # FURIA/Navi should have at least 10 players
    assert len(totals) >= 10, f"Expected 10+ players, got {len(totals)}"
