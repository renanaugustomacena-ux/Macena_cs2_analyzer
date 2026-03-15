"""
Tick Enrichment Engine for Demo Parsing Pipeline.

Computes cross-player and contextual features that are not directly available
from demoparser2's per-player tick data. These features close the
training/inference skew for METADATA_DIM features 20-24.

Features computed:
- round_number (from round_context.py)
- time_in_round (seconds since round action started)
- bomb_planted (boolean state per tick)
- teammates_alive (count, excluding self)
- enemies_alive (count)
- team_economy (sum of team balance)
- enemies_visible (FOV-based geometric approximation)
- map_name (propagated to every row)
"""

import math
from typing import Optional

import numpy as np
import pandas as pd

from Programma_CS2_RENAN.backend.data_sources.round_context import (
    assign_round_to_ticks,
    extract_bomb_events,
    extract_round_context,
)
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.tick_enrichment")


def enrich_tick_data(
    df_all_players: pd.DataFrame,
    demo_path: str,
    tick_rate: float = 64.0,
    map_name: str = "de_unknown",
) -> pd.DataFrame:
    """Enrich tick DataFrame with cross-player and contextual features.

    This function takes raw tick data for ALL players (not just target)
    and computes the features that require knowledge of the full game state.

    Args:
        df_all_players: DataFrame from parse_sequential_ticks(target="ALL").
            Must contain: tick, player_name, team_name, is_alive, balance,
            X, Y, Z, yaw, health, armor, equipment_value.
        demo_path: Path to the .dem file for event extraction.
        tick_rate: Demo tick rate (default 64.0 for CS2).
        map_name: Map name to propagate to every row.

    Returns:
        The input DataFrame with added columns:
        round_number, time_in_round, bomb_planted, teammates_alive,
        enemies_alive, team_economy, enemies_visible, map_name
    """
    if df_all_players.empty:
        return df_all_players

    df = df_all_players.copy()
    total_rows = len(df)
    logger.info(
        "Starting tick enrichment: %s rows, %d players",
        f"{total_rows:,}",
        df["player_name"].nunique() if "player_name" in df.columns else 0,
    )

    # --- Step 1: Round context (round_number + time_in_round) ---
    round_ctx = extract_round_context(demo_path)
    df = assign_round_to_ticks(df, round_ctx, tick_rate=tick_rate)
    logger.info("Round context assigned: %d rounds detected", len(round_ctx))

    # --- Step 2: Bomb state ---
    bomb_events = extract_bomb_events(demo_path)
    df = _compute_bomb_state(df, bomb_events, round_ctx)

    # --- Step 3: Alive counts (teammates + enemies) ---
    df = _compute_alive_counts(df)

    # --- Step 4: Team economy ---
    df = _compute_team_economy(df)

    # --- Step 5: Enemies visible (FOV geometric) ---
    df = _compute_enemies_visible(df)

    # --- Step 6: Map name ---
    df["map_name"] = map_name

    logger.info("Tick enrichment complete: %s rows enriched", f"{total_rows:,}")
    return df


def _compute_bomb_state(
    df: pd.DataFrame,
    bomb_events: pd.DataFrame,
    round_ctx: pd.DataFrame,
) -> pd.DataFrame:
    """Compute per-tick bomb_planted boolean state.

    Logic:
    - bomb_planted becomes True at the tick of a bomb_planted event
    - Stays True until bomb_defused event or new round starts
    - Resets to False at each round start
    """
    df["bomb_planted"] = False

    if bomb_events.empty:
        return df

    # Get all unique ticks and sort
    all_ticks = df["tick"].unique()
    all_ticks.sort()

    # Build round boundaries for reset detection
    round_starts = set()
    if not round_ctx.empty:
        round_starts = set(round_ctx["round_start_tick"].tolist())

    # Build bomb state array: iterate through events in tick order
    planted_events = bomb_events[bomb_events["event_type"] == "planted"]["tick"].tolist()
    defused_events = bomb_events[bomb_events["event_type"] == "defused"]["tick"].tolist()

    # Create tick -> bomb_planted mapping using vectorized approach
    bomb_state = np.zeros(len(all_ticks), dtype=bool)
    is_planted = False
    planted_idx = 0
    defused_idx = 0

    for i, tick in enumerate(all_ticks):
        # Check for round reset
        if tick in round_starts:
            is_planted = False

        # Check for bomb_planted event at this tick
        while planted_idx < len(planted_events) and planted_events[planted_idx] <= tick:
            if planted_events[planted_idx] == tick:
                is_planted = True
            planted_idx += 1

        # Check for bomb_defused event at this tick
        while defused_idx < len(defused_events) and defused_events[defused_idx] <= tick:
            if defused_events[defused_idx] == tick:
                is_planted = False
            defused_idx += 1

        bomb_state[i] = is_planted

    # Map back to DataFrame via tick lookup
    tick_to_bomb = dict(zip(all_ticks, bomb_state))
    df["bomb_planted"] = df["tick"].map(tick_to_bomb).fillna(False).astype(bool)

    planted_count = df["bomb_planted"].sum()
    if planted_count > 0:
        logger.info("Bomb state computed: %s ticks with bomb planted", f"{planted_count:,}")

    return df


def _compute_alive_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Compute teammates_alive and enemies_alive for each player at each tick.

    For each (tick, player):
    - teammates_alive = count of alive players on same team, excluding self
    - enemies_alive = count of alive players on opposing team
    """
    # Ensure is_alive is boolean
    if "is_alive" in df.columns:
        df["is_alive"] = df["is_alive"].fillna(True).astype(bool)
    else:
        df["is_alive"] = True

    if "team_name" not in df.columns:
        df["teammates_alive"] = 4
        df["enemies_alive"] = 5
        return df

    # Count alive players per (tick, team)
    alive_mask = df["is_alive"] == True
    alive_per_tick_team = (
        df[alive_mask]
        .groupby(["tick", "team_name"])
        .size()
        .reset_index(name="alive_count")
    )

    # Merge alive counts for own team
    df = df.merge(
        alive_per_tick_team,
        on=["tick", "team_name"],
        how="left",
        suffixes=("", "_own"),
    )
    # teammates_alive = own team alive count - 1 (exclude self if alive)
    own_alive = df["alive_count"].fillna(0).astype(int)
    self_alive = df["is_alive"].astype(int)
    df["teammates_alive"] = (own_alive - self_alive).clip(lower=0)
    df.drop(columns=["alive_count"], inplace=True)

    # For enemies: we need the opposing team's alive count
    # Get unique teams per tick — CS2 has exactly 2 teams (CT, T + possibly spectators)
    # Approach: total alive per tick minus own team alive = enemy alive
    total_alive_per_tick = (
        df[alive_mask]
        .groupby("tick")
        .size()
        .reset_index(name="total_alive")
    )
    df = df.merge(total_alive_per_tick, on="tick", how="left")

    # Re-merge own team alive count for enemy calculation
    df = df.merge(
        alive_per_tick_team.rename(columns={"alive_count": "own_team_alive"}),
        on=["tick", "team_name"],
        how="left",
    )
    own_team = df["own_team_alive"].fillna(0).astype(int)
    total = df["total_alive"].fillna(0).astype(int)
    df["enemies_alive"] = (total - own_team).clip(lower=0)

    df.drop(columns=["total_alive", "own_team_alive"], inplace=True)

    return df


def _compute_team_economy(df: pd.DataFrame) -> pd.DataFrame:
    """Compute team_economy (sum of team balance) for each tick.

    team_economy = sum of 'balance' for all players on the same team at this tick.
    """
    if "balance" not in df.columns:
        df["team_economy"] = 0
        return df

    if "team_name" not in df.columns:
        df["team_economy"] = 0
        return df

    team_econ = (
        df.groupby(["tick", "team_name"])["balance"]
        .sum()
        .reset_index(name="team_economy")
    )

    df = df.merge(team_econ, on=["tick", "team_name"], how="left")
    df["team_economy"] = df["team_economy"].fillna(0).astype(int)

    return df


def _compute_enemies_visible(
    df: pd.DataFrame,
    fov_degrees: float = 90.0,
    max_distance: float = 4000.0,
) -> pd.DataFrame:
    """Compute enemies_visible using geometric FOV cone approximation.

    For each player at each tick:
    1. Get player position (X, Y) and yaw angle
    2. For each alive enemy at the same tick:
       a. Compute direction vector from player to enemy
       b. Compute angle between player's yaw and direction to enemy
       c. If angle < fov_degrees/2 AND distance < max_distance: visible
    3. Count visible enemies

    This is a simplified check (no wall/raycast occlusion). The PlayerKnowledge
    system handles full occlusion at inference time.

    Performance: Processes per-tick batches (~10 players per tick).
    Uses numpy vectorization for trigonometric calculations.

    Args:
        df: DataFrame with X, Y, yaw, team_name, is_alive columns.
        fov_degrees: Field of view in degrees (CS2 default ~90).
        max_distance: Maximum visibility distance in world units.

    Returns:
        DataFrame with enemies_visible column added/updated.
    """
    required_cols = {"X", "Y", "yaw", "team_name", "is_alive"}
    if not required_cols.issubset(df.columns):
        missing = required_cols - set(df.columns)
        logger.warning("Cannot compute enemies_visible — missing columns: %s", missing)
        df["enemies_visible"] = 0
        return df

    half_fov_rad = math.radians(fov_degrees / 2.0)

    # Pre-allocate result array
    enemies_visible = np.zeros(len(df), dtype=np.int32)

    # Process per-tick batches for efficiency
    # Group by tick — each group has ~10 rows (one per player)
    tick_groups = df.groupby("tick")
    total_ticks = len(tick_groups)

    processed = 0
    for tick, group in tick_groups:
        if len(group) < 2:
            processed += 1
            continue

        indices = group.index.values
        positions_x = group["X"].values.astype(np.float64)
        positions_y = group["Y"].values.astype(np.float64)
        yaws = group["yaw"].values.astype(np.float64)
        teams = np.asarray(group["team_name"].values)
        alive = group["is_alive"].values.astype(bool)

        n_players = len(group)

        # C-02: Numpy-vectorized FOV computation (replaces O(P²) Python loops)
        # Pairwise direction vectors: dx[i,j] = pos_x[j] - pos_x[i]
        dx = positions_x[np.newaxis, :] - positions_x[:, np.newaxis]
        dy = positions_y[np.newaxis, :] - positions_y[:, np.newaxis]
        dist = np.sqrt(dx ** 2 + dy ** 2)

        # Player look direction vectors
        yaw_rad = np.radians(yaws)
        look_dx = np.cos(yaw_rad)
        look_dy = np.sin(yaw_rad)

        # Normalized direction from i to j (avoid division by zero)
        with np.errstate(divide="ignore", invalid="ignore"):
            dx_n = np.where(dist > 1e-6, dx / dist, 0.0)
            dy_n = np.where(dist > 1e-6, dy / dist, 0.0)

        # Dot product: look[i] · direction[i→j]
        dot = look_dx[:, np.newaxis] * dx_n + look_dy[:, np.newaxis] * dy_n
        dot = np.clip(dot, -1.0, 1.0)
        angle = np.arccos(dot)

        # Boolean masks
        not_self = ~np.eye(n_players, dtype=bool)
        enemy_mask = teams[:, np.newaxis] != teams[np.newaxis, :]
        alive_observer = alive[:, np.newaxis]
        alive_target = alive[np.newaxis, :]
        dist_ok = (dist <= max_distance) & (dist > 1e-6)
        fov_ok = angle <= half_fov_rad

        visible = not_self & enemy_mask & alive_observer & alive_target & dist_ok & fov_ok
        counts = visible.sum(axis=1)
        enemies_visible[indices] = counts

        processed += 1
        if processed % 50000 == 0:
            logger.info(
                "enemies_visible progress: %d/%d ticks (%.1f%%)",
                processed, total_ticks, processed / total_ticks * 100,
            )

    df["enemies_visible"] = enemies_visible
    total_visible = (enemies_visible > 0).sum()
    logger.info(
        "enemies_visible computed: %s ticks with at least 1 visible enemy (%.1f%%)",
        f"{total_visible:,}",
        total_visible / max(len(df), 1) * 100,
    )

    return df
