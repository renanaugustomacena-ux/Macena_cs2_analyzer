"""
KAST (Kill, Assist, Survive, Trade) Calculation Module.

KAST is a key CS2 performance metric representing the percentage of rounds
where a player had a positive impact through one of:
- K: Getting a kill
- A: Getting an assist
- S: Surviving the round
- T: Being traded (dying but a teammate kills the enemy who killed you within 5 seconds)

HLTV 2.0 considers KAST one of the core components of player ratings.
"""

from typing import Any, Dict, List


def calculate_kast_for_round(
    player_name: str,
    round_events: List[Dict[str, Any]],
    trade_window_seconds: float = 5.0,
    ticks_per_second: int = 64,
) -> bool:
    """
    Determines if a player achieved KAST in a single round.

    Args:
        player_name:          The player to evaluate.
        round_events:         List of events with 'type', 'attacker', 'victim', 'assister', 'tick'.
        trade_window_seconds: Time window for trade consideration (default 5 s).
        ticks_per_second:     Tick rate of the demo (64 for matchmaking, 128 for FACEIT/ESEA).
                              Callers SHOULD read this from the demo header and pass it here.
                              Default 64 produces a 320-tick window. At 128 ticks/s, omitting
                              this parameter halves the trade window to ~2.5 s.

    Returns:
        bool: True if player achieved K, A, S, or T this round.
    """
    trade_window_ticks = int(trade_window_seconds * ticks_per_second)

    player_kills = []
    player_deaths = []
    player_assists = []
    all_deaths = []

    for event in round_events:
        if event.get("type") != "player_death":
            continue

        attacker = event.get("attacker", "")
        victim = event.get("victim", "")
        assister = event.get("assister", "")
        tick = event.get("tick", 0)

        # Track all deaths for trade calculation
        all_deaths.append({"victim": victim, "attacker": attacker, "tick": tick})

        # K: Player got a kill
        if attacker == player_name and victim != player_name:
            player_kills.append(tick)

        # A: Player got an assist
        if assister == player_name:
            player_assists.append(tick)

        # Track player deaths
        if victim == player_name:
            player_deaths.append({"attacker": attacker, "tick": tick})

    # K or A achieved
    if player_kills or player_assists:
        return True

    # S: Survived (no deaths recorded for this player)
    if not player_deaths:
        return True

    # T: Was traded
    # For each death, check if the attacker was killed within trade_window
    for death in player_deaths:
        attacker = death["attacker"]
        death_tick = death["tick"]

        for other_death in all_deaths:
            if (
                other_death["victim"] == attacker
                and other_death["tick"] > death_tick
                and other_death["tick"] <= death_tick + trade_window_ticks
            ):
                return True  # Player was traded

    return False


def calculate_kast_percentage(
    player_name: str,
    rounds_events: List[List[Dict[str, Any]]],
    ticks_per_second: int = 64,
) -> float:
    """
    Calculates KAST percentage across multiple rounds.

    Args:
        player_name:      The player to evaluate.
        rounds_events:    List of rounds, each containing list of events.
        ticks_per_second: Tick rate of the demo (64 for matchmaking, 128 for FACEIT/ESEA).

    Returns:
        float: KAST ratio (0.0 to 1.0)
    """
    if not rounds_events:
        return 0.0

    kast_rounds = sum(
        1
        for round_events in rounds_events
        if calculate_kast_for_round(player_name, round_events, ticks_per_second=ticks_per_second)
    )

    return kast_rounds / len(rounds_events)


def estimate_kast_from_stats(kills: int, assists: int, deaths: int, rounds_played: int) -> float:
    """
    Estimates KAST from aggregate stats when round-level data is unavailable.

    This is an approximation based on the observation that:
    - Kill/Assist rounds are bounded by kills + assists
    - Survival rounds are bounded by rounds_played - deaths
    - Trade probability is estimated at ~30% of deaths at high level

    Args:
        kills: Total kills
        assists: Total assists
        deaths: Total deaths
        rounds_played: Total rounds played

    Returns:
        float: Estimated KAST ratio (0.0 to 1.0)
    """
    if rounds_played == 0:
        return 0.0

    # Estimate unique rounds with kills/assists.
    # The 0.8 weight on assists assumes ~80% of assists occur in rounds that
    # already have a kill, reducing double-counting. This heuristic is based on
    # empirical observation at pro level; no formal statistical source exists. (F2-35)
    ka_rounds = min(kills + assists * 0.8, rounds_played)

    # Survival rounds (not killed)
    survival_rounds = rounds_played - deaths

    # Trade probability estimate (30% of deaths are traded at pro level)
    estimated_trades = deaths * 0.30

    # Union of all positive impact rounds (with overlap reduction)
    # Using inclusion-exclusion approximation
    unique_positive_rounds = min(
        ka_rounds + survival_rounds * 0.5 + estimated_trades * 0.3, rounds_played
    )

    return min(unique_positive_rounds / rounds_played, 1.0)
