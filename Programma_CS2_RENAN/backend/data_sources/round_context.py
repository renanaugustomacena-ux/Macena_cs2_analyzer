"""
Round Context Extraction for Demo Parsing Enrichment.

Extracts round boundaries (freeze_end and round_end ticks) from CS2 demo files
to enable computation of round_number and time_in_round for each tick.

Uses the same demoparser2 event parsing patterns proven in:
- demo_loader.py (round_freeze_end for round starts)
- round_stats_builder.py (_build_round_boundaries for round ends)
"""

from typing import List, Tuple

import pandas as pd
from demoparser2 import DemoParser

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.round_context")


def extract_round_context(demo_path: str) -> pd.DataFrame:
    """Extract round boundaries from a demo file.

    Parses round_freeze_end and round_end events to build a mapping of
    round numbers to their tick boundaries.

    Args:
        demo_path: Path to the .dem file.

    Returns:
        DataFrame with columns:
        - round_number: int (1-based)
        - round_start_tick: int (tick when freeze time ends, action begins)
        - round_end_tick: int (tick when round ends)

        Empty DataFrame if parsing fails or no round events found.
    """
    try:
        parser = DemoParser(demo_path)
    except Exception as e:
        logger.error("Failed to create DemoParser for round context: %s", e)
        return pd.DataFrame()

    # Extract round_freeze_end ticks (marks when action begins)
    freeze_end_ticks: List[int] = []
    try:
        res = parser.parse_events(["round_freeze_end"])
        if res:
            df = res[0][1] if isinstance(res[0], tuple) else pd.DataFrame(res)
            if not df.empty and "tick" in df.columns:
                freeze_end_ticks = sorted(df["tick"].astype(int).tolist())
    except Exception as e:
        logger.warning("Failed to parse round_freeze_end events: %s", e)

    # Extract round_end ticks (marks when round ends)
    round_end_ticks: List[int] = []
    try:
        res = parser.parse_events(["round_end"])
        if res:
            df = res[0][1] if isinstance(res[0], tuple) else pd.DataFrame(res)
            if not df.empty and "tick" in df.columns:
                round_end_ticks = sorted(df["tick"].astype(int).tolist())
    except Exception as e:
        logger.warning("Failed to parse round_end events: %s", e)

    if not round_end_ticks:
        logger.warning("No round_end events found — cannot build round context")
        return pd.DataFrame()

    # Build round boundaries by pairing freeze_end with round_end
    total_rounds = len(round_end_ticks)
    rows: List[dict] = []

    for i in range(total_rounds):
        round_number = i + 1
        round_end = round_end_ticks[i]

        # Match freeze_end to this round: use the last freeze_end tick before round_end
        # that is also after the previous round_end (or 0 for round 1)
        prev_round_end = round_end_ticks[i - 1] if i > 0 else 0

        matching_freeze = [
            t for t in freeze_end_ticks
            if prev_round_end <= t < round_end
        ]

        if matching_freeze:
            round_start = matching_freeze[-1]
        else:
            # Fallback: use previous round_end as start
            round_start = prev_round_end
            if i > 0:
                logger.debug(
                    "No freeze_end found for round %d, using prev round_end=%d as start",
                    round_number, round_start,
                )

        rows.append({
            "round_number": round_number,
            "round_start_tick": round_start,
            "round_end_tick": round_end,
        })

    result = pd.DataFrame(rows)
    logger.info(
        "Round context extracted: %d rounds, tick range %d-%d",
        len(result),
        result["round_start_tick"].min() if not result.empty else 0,
        result["round_end_tick"].max() if not result.empty else 0,
    )
    return result


def extract_bomb_events(demo_path: str) -> pd.DataFrame:
    """Extract bomb_planted and bomb_defused events from a demo file.

    Args:
        demo_path: Path to the .dem file.

    Returns:
        DataFrame with columns:
        - tick: int
        - event_type: str ("planted" or "defused")

        Empty DataFrame if no bomb events found.
    """
    try:
        parser = DemoParser(demo_path)
    except Exception as e:
        logger.error("Failed to create DemoParser for bomb events: %s", e)
        return pd.DataFrame()

    rows: List[dict] = []

    for event_name, event_label in [
        ("bomb_planted", "planted"),
        ("bomb_defused", "defused"),
        ("bomb_exploded", "exploded"),  # H-07: Track bomb explosions
    ]:
        try:
            res = parser.parse_events([event_name])
            if res:
                df = res[0][1] if isinstance(res[0], tuple) else pd.DataFrame(res)
                if not df.empty and "tick" in df.columns:
                    for tick in df["tick"].astype(int).tolist():
                        rows.append({"tick": tick, "event_type": event_label})
        except Exception as e:
            logger.debug("No %s events found: %s", event_name, e)

    if not rows:
        return pd.DataFrame(columns=["tick", "event_type"])

    result = pd.DataFrame(rows).sort_values("tick").reset_index(drop=True)
    logger.info("Bomb events extracted: %d events", len(result))
    return result


def assign_round_to_ticks(
    df_ticks: pd.DataFrame,
    round_context: pd.DataFrame,
    tick_rate: float = 64.0,
) -> pd.DataFrame:
    """Assign round_number and time_in_round to each tick row.

    Uses pd.merge_asof for efficient O(n log m) assignment:
    each tick is matched to the round whose round_start_tick is
    the largest value <= tick.

    Args:
        df_ticks: DataFrame with a 'tick' column (must be sorted).
        round_context: DataFrame from extract_round_context().
        tick_rate: Demo tick rate (default 64.0 for CS2).

    Returns:
        df_ticks with added columns: round_number, time_in_round
    """
    if round_context.empty:
        df_ticks["round_number"] = 1
        df_ticks["time_in_round"] = 0.0
        return df_ticks

    # Ensure sorted for merge_asof
    was_sorted = df_ticks["tick"].is_monotonic_increasing
    if not was_sorted:
        df_ticks = df_ticks.sort_values("tick")

    # merge_asof: for each tick, find the last round_start_tick <= tick
    rc = round_context[["round_number", "round_start_tick"]].copy()
    rc = rc.sort_values("round_start_tick")

    # Ensure matching dtypes for merge_asof (demoparser2 may return int32)
    df_ticks["tick"] = df_ticks["tick"].astype("int64")
    rc["round_start_tick"] = rc["round_start_tick"].astype("int64")

    merged = pd.merge_asof(
        df_ticks,
        rc,
        left_on="tick",
        right_on="round_start_tick",
        direction="backward",
        suffixes=("_orig", ""),
    )

    # Handle ticks before the first round (warmup): assign to round 1
    if "round_number" in merged.columns:
        merged["round_number"] = merged["round_number"].fillna(1).astype(int)
    else:
        merged["round_number"] = 1

    # Compute time_in_round in seconds
    if "round_start_tick" in merged.columns:
        merged["time_in_round"] = (
            (merged["tick"] - merged["round_start_tick"].fillna(0)) / tick_rate
        ).clip(lower=0.0, upper=175.0)
    else:
        merged["time_in_round"] = 0.0

    # Clean up merge artifact column
    if "round_start_tick" in merged.columns:
        merged.drop(columns=["round_start_tick"], inplace=True)

    # Handle potential duplicate column from merge
    if "round_number_orig" in merged.columns:
        merged.drop(columns=["round_number_orig"], inplace=True)

    return merged
