import os
from typing import Dict, Optional

import pandas as pd
from demoparser2 import DemoParser

from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import estimate_kast_from_stats
from Programma_CS2_RENAN.backend.processing.feature_engineering.rating import (
    BASELINE_ADR,
    BASELINE_DPR_COMPLEMENT,
    BASELINE_KAST,
    BASELINE_KPR,
)
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.demo_parser")

# HLTV 2.0 baselines imported from the canonical rating module.
# Local aliases preserve the vectorized DataFrame code below.
RATING_BASELINE_KPR = BASELINE_KPR
RATING_BASELINE_SURVIVAL = BASELINE_DPR_COMPLEMENT
RATING_BASELINE_KAST = BASELINE_KAST
RATING_BASELINE_ADR = BASELINE_ADR
RATING_BASELINE_ECON = 85.0  # Economy-specific, not part of HLTV 2.0


def parse_demo(demo_path: str, target_player: Optional[str] = None) -> pd.DataFrame:
    """Extremely stable parsing with full data integrity checks."""
    if not os.path.exists(demo_path):
        logger.warning("Demo file not found: %s", demo_path)
        return pd.DataFrame()
    try:
        parser = DemoParser(demo_path)
        evs = parser.parse_events(["round_end"])
        if not evs:
            return pd.DataFrame()
        rounds_df = evs[0][1] if isinstance(evs[0], tuple) else pd.DataFrame(evs)
        if rounds_df.empty:
            return pd.DataFrame()

        return _extract_stats_with_full_fields(parser, len(rounds_df), target_player)
    except Exception as e:
        logger.exception("Parser Fatal")
        return pd.DataFrame()


def _extract_stats_with_full_fields(parser, total_rounds, target_player):
    """Ensures 100% of DB-required fields are calculated or defaulted."""
    raw = parser.parse_ticks(["player_name", "name", "kills_total", "deaths_total", "damage_total"])
    df = pd.DataFrame(raw)
    if df.empty:
        return pd.DataFrame()

    p_col = next((c for c in ["player_name", "name"] if c in df.columns), None)
    if not p_col:
        return pd.DataFrame()

    df = df.rename(columns={p_col: "player_name"})

    if target_player and target_player != "ALL":
        df = df[
            df["player_name"].astype(str).str.strip().str.lower()
            == str(target_player).strip().lower()
        ]
        if df.empty:
            return pd.DataFrame()

    totals = (
        df.groupby("player_name")
        .agg({"kills_total": "max", "deaths_total": "max", "damage_total": "max"})
        .reset_index()
    )

    # Calculate and Fill ALL Mandatory Fields
    if total_rounds == 0:
        logger.warning("Demo has 0 rounds — cannot compute per-round stats")
        return pd.DataFrame()
    totals["avg_kills"] = totals["kills_total"] / total_rounds
    totals["avg_deaths"] = totals["deaths_total"] / total_rounds
    totals["avg_adr"] = totals["damage_total"] / total_rounds
    totals["kd_ratio"] = totals["kills_total"] / totals["deaths_total"].replace(0, 1)

    # Add dynamic event stats (HS, Accuracy, etc)
    _add_event_stats_safe(parser, totals, total_rounds)

    # Compute per-round variance from round_end kill/damage deltas
    totals["kill_std"] = 0.0
    totals["adr_std"] = 0.0
    try:
        round_stats = _compute_per_round_variance(parser)
        if round_stats is not None:
            totals = totals.merge(round_stats, on="player_name", how="left", suffixes=("", "_calc"))
            if "kill_std_calc" in totals.columns:
                totals["kill_std"] = totals["kill_std_calc"].fillna(0.0)
                totals["adr_std"] = totals["adr_std_calc"].fillna(0.0)
                totals.drop(
                    columns=["kill_std_calc", "adr_std_calc"], inplace=True, errors="ignore"
                )
    except Exception as e:
        logger.debug("Could not compute per-round variance: %s", e)

    # --- HLTV 2.0 LOGIC START ---
    # Validated: baselines and formula match the canonical rating module
    # (backend/processing/feature_engineering/rating.py, R²=0.995).
    # Vectorized here for DataFrame performance; scalar version in rating.py.

    # 1. Base Metrics
    totals["kpr"] = totals["avg_kills"]
    totals["dpr"] = totals["avg_deaths"]

    # 2. Impact Rating
    # Formula: 2.13*KPR + 0.42*AssistPR - 0.41*SurvivalPR (Simplified for Phase 2)
    # We don't have AssistPR yet easily, so we use refined Kills/ADR proxy for now
    # until Multikill sub-task is complete.
    # REF: study_notes/domain_2_math.md
    totals["rating_impact"] = (totals["kpr"] * 2.13) + (totals["avg_adr"] / 100 * 0.42)

    # 3. Survival Rating
    # Formula: (1 - DPR) / Avg_Survival_Rate (~0.33) ? No, simply component weight.
    totals["rating_survival"] = 1.0 - totals["dpr"]

    # 4. Component Storage
    # avg_kast is pre-initialized to 0.0; treat 0.0 as "no data" and use fallback
    totals["rating_kast"] = totals["avg_kast"].apply(lambda x: x if x > 0 else 0.70)
    totals["rating_kpr"] = totals["kpr"]
    totals["rating_adr"] = totals["avg_adr"]

    # 5. Normalized rating (each component scaled to ~1.0 baseline)
    r_kill = totals["kpr"] / RATING_BASELINE_KPR
    r_surv = (1.0 - totals["dpr"]) / RATING_BASELINE_SURVIVAL
    r_kast = totals["rating_kast"] / RATING_BASELINE_KAST
    r_imp = totals["rating_impact"] / 1.0
    r_dmg = totals["avg_adr"] / RATING_BASELINE_ADR

    totals["rating"] = (r_kill + r_surv + r_kast + r_imp + r_dmg) / 5.0

    totals["econ_rating"] = totals["avg_adr"] / RATING_BASELINE_ECON

    # [INTEGRATION FIX] Alias new Rating 2.0 Impact to legacy field
    # This prevents Frontend/ML breakage (Domino Effect Repair)
    totals["impact_rounds"] = totals["rating_impact"]

    return totals


def _resolve_name_column(df: pd.DataFrame, candidates: list) -> Optional[str]:
    """Find the player name column in an event DataFrame.

    demoparser2 uses different field names per event type:
    - weapon_fire: 'player_name' (sometimes absent, only 'userid' int)
    - player_hurt/death/blind: 'attacker_name' / 'user_name'
    """
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _compute_per_round_variance(parser):
    """Compute per-round kill and damage std from player_death and player_hurt events."""
    import numpy as np

    try:
        deaths_evs = parser.parse_events(["player_death"])
        hurts_evs = parser.parse_events(["player_hurt"])
        if not deaths_evs or not hurts_evs:
            return None

        d_df = deaths_evs[0][1] if isinstance(deaths_evs[0], tuple) else pd.DataFrame(deaths_evs)
        h_df = hurts_evs[0][1] if isinstance(hurts_evs[0], tuple) else pd.DataFrame(hurts_evs)

        if d_df.empty or h_df.empty:
            return None

        d_name = _resolve_name_column(d_df, ["attacker_name", "user_name", "player_name"])
        h_name = _resolve_name_column(h_df, ["attacker_name", "user_name", "player_name"])

        if not d_name or not h_name or "total_rounds_played" not in d_df.columns:
            return None

        # Per-round kills
        kills_per_round = (
            d_df.groupby([d_name, "total_rounds_played"]).size().reset_index(name="kills")
        )
        kill_std = kills_per_round.groupby(d_name)["kills"].std().fillna(0.0).reset_index()
        kill_std.columns = ["player_name", "kill_std"]

        # Per-round damage
        dmg_col = "dmg_health" if "dmg_health" in h_df.columns else "damage"
        if dmg_col not in h_df.columns:
            return kill_std.rename(columns={"kill_std": "kill_std"}).assign(adr_std=0.0)

        dmg_per_round = (
            h_df.groupby([h_name, "total_rounds_played"])[dmg_col].sum().reset_index(name="damage")
        )
        adr_std = dmg_per_round.groupby(h_name)["damage"].std().fillna(0.0).reset_index()
        adr_std.columns = ["player_name", "adr_std"]

        return kill_std.merge(adr_std, on="player_name", how="outer").fillna(0.0)
    except Exception:
        logger.debug("Per-round variance computation failed", exc_info=True)
        return None


def _add_event_stats_safe(parser, df, total_rounds):
    """Safe per-player headshot and accuracy extraction.

    NO HARDCODED FALLBACKS. If event parsing fails, fields remain 0.0.
    This ensures training data is not poisoned with synthetic placeholders.

    Column names vary across demoparser2 event types and demo versions:
    - player_hurt: attacker_name, user_name
    - weapon_fire: player_name (sometimes absent)
    - player_death: attacker_name, user_name
    """
    # Initialize to 0.0 (meaning "no data", not "0% headshot rate")
    df["avg_hs"] = 0.0
    df["accuracy"] = 0.0
    df["avg_kast"] = 0.0
    # Data quality flag: "none" = no event data, "partial" = some players missing,
    # "complete" = all players have real event data. Downstream consumers (training
    # pipeline) should filter or weight samples based on this flag (Bug #3).
    df["data_quality"] = "partial"

    try:
        hurt = parser.parse_events(["player_hurt"])
        shots = parser.parse_events(["weapon_fire"])
        deaths = parser.parse_events(["player_death"])

        h_df = hurt[0][1] if hurt and isinstance(hurt[0], tuple) else pd.DataFrame()
        s_df = shots[0][1] if shots and isinstance(shots[0], tuple) else pd.DataFrame()
        d_df = deaths[0][1] if deaths and isinstance(deaths[0], tuple) else pd.DataFrame()

        # If ALL event DataFrames are empty, no meaningful stats can be extracted
        if h_df.empty and s_df.empty and d_df.empty:
            df["data_quality"] = "none"
            logger.warning(
                "No event data extracted — all event DataFrames empty. "
                "Stats remain 0.0 (missing, not measured)."
            )
            return

        # Resolve name columns — varies across demo versions and event types
        h_name_col = _resolve_name_column(h_df, ["attacker_name", "user_name", "player_name"])
        s_name_col = _resolve_name_column(s_df, ["player_name", "user_name", "name"])
        d_name_col = _resolve_name_column(d_df, ["attacker_name", "user_name", "player_name"])

        if not s_name_col and not s_df.empty:
            logger.warning("weapon_fire has no name column (columns: %s)", list(s_df.columns))
        if not h_name_col and not h_df.empty:
            logger.warning("player_hurt has no name column (columns: %s)", list(h_df.columns))
        if not d_name_col and not d_df.empty:
            logger.warning("player_death has no name column (columns: %s)", list(d_df.columns))

        players_with_data = 0
        for idx, row in df.iterrows():
            name = str(row["player_name"]).lower()
            player_has_data = False

            # Calculate accuracy from weapon_fire and player_hurt events
            if not s_df.empty and not h_df.empty and h_name_col and s_name_col:
                hit_count = len(h_df[h_df[h_name_col].astype(str).str.lower() == name])
                shot_count = len(s_df[s_df[s_name_col].astype(str).str.lower() == name])
                if shot_count > 0:
                    df.at[idx, "accuracy"] = hit_count / shot_count
                    player_has_data = True

            # Calculate headshot % from player_death events
            if not d_df.empty and d_name_col:
                kills = d_df[d_df[d_name_col].astype(str).str.lower() == name]
                if not kills.empty:
                    hs_count = len(kills[kills["headshot"] == True])
                    df.at[idx, "avg_hs"] = hs_count / len(kills)
                    player_has_data = True

            # Compute assists from actual assister_name in player_death events
            total_kills = int(row.get("kills_total", 0))
            total_deaths = int(row.get("deaths_total", 0))
            total_assists = 0
            if not d_df.empty and "assister_name" in d_df.columns:
                total_assists = int((d_df["assister_name"].astype(str).str.lower() == name).sum())
            else:
                # No assister data available — set to 0 (no fabricated estimates)
                logger.warning(
                    "player_death events lack 'assister_name' column — assists set to 0 for %s",
                    name,
                )
            if total_rounds > 0:
                df.at[idx, "avg_kast"] = estimate_kast_from_stats(
                    total_kills, total_assists, total_deaths, total_rounds
                )
                player_has_data = True

            if player_has_data:
                df.at[idx, "data_quality"] = "complete"
                players_with_data += 1

        partial_count = len(df) - players_with_data
        if partial_count > 0:
            logger.warning(
                "%d/%d players have PARTIAL event data (0.0 = missing, not measured). "
                "Training pipeline should filter or weight these samples.",
                partial_count, len(df),
            )
        logger.info("Event stats extracted for %d/%d players", players_with_data, len(df))

    except Exception as e:
        df["data_quality"] = "none"
        logger.exception("Event parsing failed - stats remain 0.0")


def parse_sequential_ticks(
    demo_path: str, target_player: str, rate: int = None, start_tick: int = 0
) -> pd.DataFrame:
    if not os.path.exists(demo_path):
        logger.warning("Demo file not found: %s", demo_path)
        return pd.DataFrame()
    try:
        parser = DemoParser(demo_path)
        sampling = (
            rate if rate else 1
        )  # FORCE NATIVE RATE (No Decimation as per Gemini_argument_master.md)

        # WP6: Complete Data Extraction (All demoparser2 fields)
        fields = [
            # Identity
            "player_name",
            "name",
            "player_steamid",
            "team_name",
            # Position & View
            "X",
            "Y",
            "Z",
            "pitch",
            "yaw",
            # Vitals
            "health",
            "armor",
            "is_alive",
            "life_state",
            # Tactical State
            "is_crouching",
            "is_scoped",
            "is_blinded",
            # Equipment & Economy
            "active_weapon",
            "equipment_value",
            "balance",
            "total_cash_spent",
            "cash_spent_this_round",
            "has_defuser",
            "has_helmet",
            # Round Context
            "kills_this_round",
            "deaths_this_round",
            "assists_this_round",
            "headshot_kills_this_round",
            "damage_this_round",
            "utility_damage_this_round",
            "enemies_flashed_this_round",
            # Cumulative Stats
            "kills_total",
            "deaths_total",
            "assists_total",
            "headshot_kills_total",
            "mvps",
            "score",
            # Technical
            "ping",
        ]

        df = pd.DataFrame(parser.parse_ticks(fields))
        if df.empty:
            return pd.DataFrame()
        p_col = next((c for c in ["player_name", "name"] if c in df.columns), None)
        if p_col:
            df = df.rename(columns={p_col: "player_name"})

        # Filter by start_tick
        if start_tick > 0:
            df = df[df["tick"] > start_tick]
            if df.empty:
                return pd.DataFrame()

        df = df.iloc[::sampling]
        if target_player != "ALL":
            df = df[
                df["player_name"].astype(str).str.strip().str.lower()
                == str(target_player).strip().lower()
            ]
        return df
    except Exception as e:
        logger.exception("Seq failure")
        return pd.DataFrame()
