"""
Round Stats Builder — Constructs per-round, per-player statistics from demo events.

This module bridges raw demo event data (player_death, player_hurt, weapon_fire,
round_end, player_blind) into the RoundStats isolation layer defined in db_models.py.

Fusion Plan Proposal 4: Per-Round Statistical Isolation Layer.
Fusion Plan Phase 1: Wires trade kills, kill enrichment, and utility effectiveness
into the aggregation pipeline (Proposals 1, 2, 3).

Usage:
    from Programma_CS2_RENAN.backend.processing.round_stats_builder import (
        build_round_stats, enrich_from_demo
    )
    round_stats = build_round_stats(parser, demo_name="match.dem")
    enrichment, round_stats = enrich_from_demo("path/to/demo.dem", "demo.dem")
"""

from typing import Dict, List, Optional, Tuple

import pandas as pd

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.round_stats_builder")

# Grenade weapon identifiers in demoparser2
HE_WEAPONS = {"hegrenade"}
FIRE_WEAPONS = {"inferno", "molotov", "incgrenade"}
SMOKE_WEAPONS = {"smokegrenade"}
FLASH_WEAPONS = {"flashbang"}
ALL_GRENADE_WEAPONS = HE_WEAPONS | FIRE_WEAPONS | SMOKE_WEAPONS | FLASH_WEAPONS

# R4-07-01: Flash assist window — 2 seconds at default 64 tick.
# P-RSB-01: This is now a DEFAULT only. build_round_stats() derives a
# per-demo local value instead of mutating this global.
_DEFAULT_FLASH_ASSIST_WINDOW_TICKS = 128


def _parse_events_safe(parser, event_name: str) -> pd.DataFrame:
    """Parse events from demo, returning empty DataFrame on failure."""
    try:
        events = parser.parse_events([event_name])
        if events:
            return events[0][1] if isinstance(events[0], tuple) else pd.DataFrame(events)
    except Exception as e:
        logger.warning("Failed to parse %s: %s", event_name, e)
    return pd.DataFrame()


def _build_round_boundaries(round_end_df: pd.DataFrame) -> List[Dict]:
    """
    Build round metadata from round_end events.

    Returns:
        List of dicts with keys: round_number, start_tick, end_tick, winner
    """
    if round_end_df.empty:
        return []

    boundaries = []
    ticks = sorted(round_end_df["tick"].tolist())

    for i, (_, row) in enumerate(round_end_df.sort_values("tick").iterrows()):
        round_num = int(row.get("round", i + 1))
        end_tick = int(row["tick"])
        # H-18: Use previous end_tick + 1 as start to prevent overlap.
        # Round i's end_tick and round i+1's start_tick no longer share a tick.
        start_tick = ticks[i - 1] + 1 if i > 0 else 0
        winner = str(row.get("winner", "")).strip() if pd.notna(row.get("winner")) else None

        boundaries.append(
            {
                "round_number": round_num,
                "start_tick": start_tick,
                "end_tick": end_tick,
                "winner": winner,
            }
        )

    # H-06: Validate round boundary completeness
    if boundaries:
        expected_rounds = set(range(1, len(boundaries) + 1))
        actual_rounds = {b["round_number"] for b in boundaries}
        missing = expected_rounds - actual_rounds
        if missing:
            logger.warning("Missing round boundaries for rounds: %s", sorted(missing))
        if any(b["start_tick"] > b["end_tick"] for b in boundaries):
            logger.error("Inverted round boundary detected (start > end)")

    return boundaries


def _assign_round(tick: int, boundaries: List[Dict]) -> Optional[int]:
    """Assign a tick to a round number using boundaries.

    P-RSB-04: Returns None for ticks outside all boundaries (warmup/overtime)
    instead of silently attributing them to the last round.
    """
    for b in boundaries:
        if b["start_tick"] <= tick <= b["end_tick"]:
            return b["round_number"]
    return None


def _get_team_roster(parser) -> Dict[str, int]:
    """Get player -> team_num mapping from tick data."""
    try:
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import build_team_roster

        return build_team_roster(parser)
    except Exception:
        logger.warning("Team roster extraction failed — trade kills unavailable", exc_info=True)
        return {}


def _team_num_to_side(team_num: int, round_number: int) -> str:
    """
    Convert team_num to CT/T side, accounting for half-switch at round 13.

    In CS2: teams switch sides after round 12 (MR12 format).
    team_num 2 and 3 alternate meaning based on half.
    """
    # Before half-switch (rounds 1-12): team 2 = one side, team 3 = other
    # After half-switch (rounds 13+): sides swap
    # We don't know which team_num is CT vs T from the data alone,
    # but we can provide consistent labeling
    if round_number <= 12:
        return "CT" if team_num == 3 else "T"
    else:
        return "T" if team_num == 3 else "CT"


def compute_round_rating(stats: Dict) -> float:
    """
    Compute HLTV 2.0 rating for a single round.

    Per-round values map directly to per-round-rates since n_rounds=1:
      KPR = kills, DPR = deaths, ADR = damage_dealt
      KAST = 1.0 if player got a Kill, Assist, Survived, or was Traded

    Uses the unified rating module to ensure training-inference consistency.

    Args:
        stats: Dict with round stat fields (kills, deaths, assists, etc.)

    Returns:
        HLTV 2.0 rating for this single round.
    """
    from Programma_CS2_RENAN.backend.processing.feature_engineering.rating import (
        compute_hltv2_rating,
    )

    kills = stats.get("kills", 0)
    deaths = stats.get("deaths", 0)
    assists = stats.get("assists", 0)
    damage = stats.get("damage_dealt", 0)
    was_traded = stats.get("was_traded", False)

    kpr = float(kills)
    dpr = float(deaths)
    adr = float(damage)

    # KAST: 1.0 if player contributed (Kill, Assist, Survived, or Traded)
    survived = deaths == 0
    kast = 1.0 if (kills > 0 or assists > 0 or survived or was_traded) else 0.0

    return compute_hltv2_rating(kpr=kpr, dpr=dpr, kast=kast, avg_adr=adr)


def build_round_stats(
    parser,
    demo_name: str,
    team_roster: Optional[Dict[str, int]] = None,
) -> List[Dict]:
    """
    Build per-round, per-player statistics from a parsed demo.

    Args:
        parser: demoparser2.DemoParser instance.
        demo_name: Name of the demo file for DB linking.
        team_roster: Optional pre-built team roster. If None, built from parser.

    Returns:
        List of dicts, each representing one RoundStats row.
    """
    # P-RSB-01: Derive flash assist window locally (no global mutation).
    try:
        header = parser.parse_header()
        tick_rate = int(float(header.get("tick_rate", 64) or 64))
        # P-RSB-05: Validate tick_rate range (32–256) to prevent absurd windows.
        if not (32 <= tick_rate <= 256):
            logger.warning(
                "P-RSB-05: tick_rate %d outside valid range [32, 256], using default",
                tick_rate,
            )
            flash_assist_window = _DEFAULT_FLASH_ASSIST_WINDOW_TICKS
        else:
            flash_assist_window = tick_rate * 2  # 2-second window
    except Exception:
        flash_assist_window = _DEFAULT_FLASH_ASSIST_WINDOW_TICKS

    # Parse all needed events
    round_end_df = _parse_events_safe(parser, "round_end")
    deaths_df = _parse_events_safe(parser, "player_death")
    hurt_df = _parse_events_safe(parser, "player_hurt")

    if round_end_df.empty:
        logger.warning("No round_end events — cannot build round stats")
        return []

    # Build round boundaries
    boundaries = _build_round_boundaries(round_end_df)
    if not boundaries:
        return []

    # Get team roster
    if team_roster is None:
        team_roster = _get_team_roster(parser)

    # R4-07-02: Validate team mapping — all team_num values should be 0, 2, or 3
    invalid_teams = {v for v in team_roster.values() if v not in (0, 2, 3)}
    if invalid_teams:
        logger.warning("R4-07-02: Unexpected team_num values in roster: %s", invalid_teams)

    # Collect all unique player names from deaths (both attacker and victim)
    all_players = set()
    if not deaths_df.empty:
        if "attacker_name" in deaths_df.columns:
            all_players.update(
                deaths_df["attacker_name"].dropna().astype(str).str.strip().str.lower().unique()
            )
        if "user_name" in deaths_df.columns:
            all_players.update(
                deaths_df["user_name"].dropna().astype(str).str.strip().str.lower().unique()
            )
    # Also from roster — P-RSB-02: only include players with valid team_num (2 or 3).
    # team_num 0 means unassigned/spectator, which produces unreliable stats.
    for name, tnum in team_roster.items():
        if tnum in (2, 3):
            all_players.add(name)
    all_players.discard("")

    # Initialize per-round, per-player accumulators
    round_player_stats: Dict[Tuple[int, str], Dict] = {}

    for b in boundaries:
        rn = b["round_number"]
        for player in all_players:
            team_num = team_roster.get(player, 0)
            # P-RSB-02: Skip players without a valid team assignment.
            if team_num not in (2, 3):
                continue
            side = _team_num_to_side(team_num, rn)

            # Determine if player's side won this round
            round_won = False
            if b["winner"] and side != "unknown":
                round_won = b["winner"].upper() == side

            round_player_stats[(rn, player)] = {
                "demo_name": demo_name,
                "round_number": rn,
                "player_name": player,
                "side": side,
                "kills": 0,
                "deaths": 0,
                "assists": 0,
                "damage_dealt": 0,
                "headshot_kills": 0,
                "trade_kills": 0,
                "was_traded": False,
                "thrusmoke_kills": 0,
                "wallbang_kills": 0,
                "noscope_kills": 0,
                "blind_kills": 0,
                "opening_kill": False,
                "opening_death": False,
                "he_damage": 0.0,
                "molotov_damage": 0.0,
                "flashes_thrown": 0,
                "smokes_thrown": 0,
                "flash_assists": 0,
                "equipment_value": 0,
                "round_won": round_won,
                "mvp": False,
                "round_rating": None,
            }

    # Process deaths
    if not deaths_df.empty:
        deaths_df = deaths_df.sort_values("tick").reset_index(drop=True)

        # Diagnostic: check if demoparser2 resolved assister (int) → assister_name (str)
        if "assister_name" not in deaths_df.columns:
            logger.info(
                "player_death events lack 'assister_name' — assists counted from other sources only"
            )

        # Track first death per round for opening duel detection
        first_death_per_round: Dict[int, bool] = {}

        for _, death in deaths_df.iterrows():
            tick = int(death["tick"])
            rn = _assign_round(tick, boundaries)
            if rn is None:
                continue  # P-RSB-04: skip warmup/overtime deaths

            attacker = str(death.get("attacker_name", "")).strip().lower()
            victim = str(death.get("user_name", "")).strip().lower()

            # Kills for attacker
            key_a = (rn, attacker)
            if key_a in round_player_stats:
                round_player_stats[key_a]["kills"] += 1
                if death.get("headshot", False):
                    round_player_stats[key_a]["headshot_kills"] += 1
                if death.get("thrusmoke", False):
                    round_player_stats[key_a]["thrusmoke_kills"] += 1
                if int(death.get("penetrated", 0)) > 0:
                    round_player_stats[key_a]["wallbang_kills"] += 1
                if death.get("noscope", False):
                    round_player_stats[key_a]["noscope_kills"] += 1
                if death.get("attackerblind", False):
                    round_player_stats[key_a]["blind_kills"] += 1

            # Death for victim
            key_v = (rn, victim)
            if key_v in round_player_stats:
                round_player_stats[key_v]["deaths"] += 1

            # Assists
            assister = str(death.get("assister_name", "")).strip().lower()
            key_assist = (rn, assister)
            if assister and key_assist in round_player_stats:
                round_player_stats[key_assist]["assists"] += 1

            # Opening duel (first death in each round)
            if rn not in first_death_per_round:
                first_death_per_round[rn] = True
                if key_a in round_player_stats:
                    round_player_stats[key_a]["opening_kill"] = True
                if key_v in round_player_stats:
                    round_player_stats[key_v]["opening_death"] = True

    # Process damage (hurt events)
    if not hurt_df.empty and "dmg_health" in hurt_df.columns:
        for _, hurt in hurt_df.iterrows():
            tick = int(hurt["tick"])
            rn = _assign_round(tick, boundaries)
            if rn is None:
                continue
            attacker = str(hurt.get("attacker_name", "")).strip().lower()
            weapon = str(hurt.get("weapon", "")).strip().lower()
            dmg = int(hurt.get("dmg_health", 0))

            key = (rn, attacker)
            if key not in round_player_stats:
                continue

            round_player_stats[key]["damage_dealt"] += dmg

            # Utility damage breakdown
            if weapon in HE_WEAPONS:
                round_player_stats[key]["he_damage"] += dmg
            elif weapon in FIRE_WEAPONS:
                round_player_stats[key]["molotov_damage"] += dmg

    # Process weapon_fire events for flash/smoke throw counting
    fire_df = _parse_events_safe(parser, "weapon_fire")
    if not fire_df.empty and "weapon" in fire_df.columns:
        for _, fire in fire_df.iterrows():
            tick = int(fire["tick"])
            rn = _assign_round(tick, boundaries)
            if rn is None:
                continue
            player = str(fire.get("player_name", "")).strip().lower()
            weapon = str(fire.get("weapon", "")).strip().lower()

            key = (rn, player)
            if key not in round_player_stats:
                continue

            if weapon in FLASH_WEAPONS:
                round_player_stats[key]["flashes_thrown"] += 1
            elif weapon in SMOKE_WEAPONS:
                round_player_stats[key]["smokes_thrown"] += 1

    # Flash assist detection: player_blind + kill within flash_assist_window
    blind_df = _parse_events_safe(parser, "player_blind")
    if not blind_df.empty and not deaths_df.empty and "blind_duration" in blind_df.columns:
        blind_df = blind_df.sort_values("tick").reset_index(drop=True)
        deaths_sorted = deaths_df.sort_values("tick").reset_index(drop=True)

        for _, blind_event in blind_df.iterrows():
            blind_tick = int(blind_event["tick"])
            blinder = str(blind_event.get("attacker_name", "")).strip().lower()
            blinded_player = str(blind_event.get("user_name", "")).strip().lower()
            rn = _assign_round(blind_tick, boundaries)
            if rn is None:
                continue

            if not blinder or not blinded_player:
                continue

            blinder_team = team_roster.get(blinder, 0)

            # Look for kills of the blinded player within the assist window
            for _, kill in deaths_sorted.iterrows():
                kill_tick = int(kill["tick"])
                if kill_tick < blind_tick:
                    continue
                if kill_tick > blind_tick + flash_assist_window:
                    break

                victim = str(kill.get("user_name", "")).strip().lower()
                killer = str(kill.get("attacker_name", "")).strip().lower()

                if victim != blinded_player:
                    continue

                # Killer must be a teammate of the blinder (same team, not the blinder)
                killer_team = team_roster.get(killer, 0)
                if killer_team == blinder_team and killer != blinder and killer_team in (2, 3):
                    key = (rn, blinder)
                    if key in round_player_stats:
                        round_player_stats[key]["flash_assists"] += 1
                    break  # Only count one assist per blind event

    # Integrate trade kill data
    try:
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import analyze_demo_trades

        trade_result, _ = analyze_demo_trades(parser)
        for detail in trade_result.trade_details:
            rn = detail["round"]
            trader = detail["trade_killer"]
            traded_victim = detail["original_victim"]

            key_trader = (rn, trader)
            if key_trader in round_player_stats:
                round_player_stats[key_trader]["trade_kills"] += 1

            key_traded = (rn, traded_victim)
            if key_traded in round_player_stats:
                round_player_stats[key_traded]["was_traded"] = True
    except Exception as e:
        logger.warning("Trade kill integration into round stats skipped: %s", e)

    # Compute per-round HLTV 2.0 rating for each entry
    for key, stats in round_player_stats.items():
        stats["round_rating"] = compute_round_rating(stats)

    result = list(round_player_stats.values())
    logger.info(
        "Built %d round stats entries (%d rounds x %d players) for %s",
        len(result), len(boundaries), len(all_players), demo_name,
    )
    return result


def aggregate_round_stats_to_match(
    round_stats: List[Dict],
    player_name: str,
) -> Dict:
    """
    Aggregate per-round stats for a single player into match-level enrichment fields.

    These fields are designed to merge directly into PlayerMatchStats via dict.update().

    Args:
        round_stats: Full list of round stat dicts (all players, all rounds).
        player_name: Lowercase player name to filter for.

    Returns:
        Dict with enrichment keys matching PlayerMatchStats field names.
    """
    player_rounds = [rs for rs in round_stats if rs["player_name"] == player_name]

    if not player_rounds:
        return {}

    num_rounds = len(player_rounds)
    total_kills = sum(rs["kills"] for rs in player_rounds)
    total_deaths = sum(rs["deaths"] for rs in player_rounds)

    enrichment = {
        # Trade kill metrics (Proposal 1)
        "trade_kill_ratio": sum(rs["trade_kills"] for rs in player_rounds) / max(1, total_kills),
        "was_traded_ratio": sum(1 for rs in player_rounds if rs["was_traded"])
        / max(1, total_deaths),
        # Kill enrichment (Proposal 1)
        "thrusmoke_kill_pct": sum(rs["thrusmoke_kills"] for rs in player_rounds)
        / max(1, total_kills),
        "wallbang_kill_pct": sum(rs["wallbang_kills"] for rs in player_rounds)
        / max(1, total_kills),
        "noscope_kill_pct": sum(rs["noscope_kills"] for rs in player_rounds) / max(1, total_kills),
        "blind_kill_pct": sum(rs["blind_kills"] for rs in player_rounds) / max(1, total_kills),
        # Utility breakdown (Proposal 2)
        "he_damage_per_round": sum(rs["he_damage"] for rs in player_rounds) / max(1, num_rounds),
        "molotov_damage_per_round": sum(rs["molotov_damage"] for rs in player_rounds)
        / max(1, num_rounds),
        "smokes_per_round": sum(rs["smokes_thrown"] for rs in player_rounds) / max(1, num_rounds),
        "flash_assists": float(sum(rs["flash_assists"] for rs in player_rounds)),
    }

    # Opening duel win % (only count rounds where player was in an opening duel)
    opening_kills = sum(1 for rs in player_rounds if rs["opening_kill"])
    opening_deaths = sum(1 for rs in player_rounds if rs["opening_death"])
    total_opening_duels = opening_kills + opening_deaths
    if total_opening_duels > 0:
        enrichment["opening_duel_win_pct"] = opening_kills / total_opening_duels

    return enrichment


def enrich_from_demo(
    demo_path: str,
    demo_name: str,
    target_player: Optional[str] = None,
) -> Tuple[Dict[str, Dict], List[Dict]]:
    """
    Build round stats from a demo and aggregate to match-level enrichment.

    This is the bridge function that connects the round_stats_builder to the
    ingestion pipeline, closing the gap where enrichment fields were never populated.

    Args:
        demo_path: Path to the .dem file.
        demo_name: Name of the demo file for DB linking.
        target_player: If set, return enrichment only for this player (lowercase).
                       If None, return enrichment for all players.

    Returns:
        Tuple of:
        - enrichment_by_player: Dict[player_name, enrichment_dict] for PlayerMatchStats
        - round_stats: List[Dict] raw round stats for RoundStats DB persistence
    """
    from demoparser2 import DemoParser

    try:
        parser = DemoParser(demo_path)
        round_stats = build_round_stats(parser, demo_name)
    except Exception as e:
        logger.exception("Failed to build round stats for %s", demo_name)
        return {}, []

    if not round_stats:
        return {}, []

    # Get unique player names
    all_players = {rs["player_name"] for rs in round_stats}
    if target_player:
        all_players = {p for p in all_players if p == target_player.strip().lower()}

    # Aggregate per player
    enrichment_by_player = {}
    for player in all_players:
        enrichment = aggregate_round_stats_to_match(round_stats, player)
        if enrichment:
            enrichment_by_player[player] = enrichment

    logger.info(
        "Enrichment complete for %s: %d players, %d round entries",
        demo_name, len(enrichment_by_player), len(round_stats),
    )
    return enrichment_by_player, round_stats
