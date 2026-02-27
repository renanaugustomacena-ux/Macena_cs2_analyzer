"""
Momentum Multiplier (Phase 6: Game Theory)

Models psychological momentum as a time-decaying multiplier that influences
expected performance based on recent round outcomes.

Governance: Rule 1 §7.3 (Behavioral modeling), Rule 2 §6.1 (Temporal decay functions)
"""

import math
from dataclasses import dataclass
from typing import List, Optional

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.analysis.momentum")

# Half-switch round boundaries (CS2 default is MR12 = 24 rounds total)
HALF_SWITCH_MR12 = 13
# MR13 (legacy 30-round format) — kept for backward compat with older demos
HALF_SWITCH_MR13 = 16

# Multiplier bounds
MULTIPLIER_MIN = 0.7
MULTIPLIER_MAX = 1.4

# Tilt detection threshold
TILT_THRESHOLD = 0.85


@dataclass
class MomentumState:
    """Current momentum state for a player/team."""

    current_multiplier: float = 1.0
    streak_length: int = 0
    streak_type: str = "neutral"  # "win", "loss", "neutral"
    decay_rate: float = 0.15

    @property
    def is_tilted(self) -> bool:
        """True when multiplier indicates potential tilt."""
        return self.current_multiplier < TILT_THRESHOLD

    @property
    def is_hot(self) -> bool:
        """True when multiplier indicates peak performance."""
        return self.current_multiplier > 1.2


class MomentumTracker:
    """
    Tracks psychological momentum across rounds within a match.

    Win streaks increase the multiplier; loss streaks decrease it.
    Momentum decays exponentially between rounds and resets on half-switch.
    """

    def __init__(self, decay_rate: float = 0.15):
        self._state = MomentumState(decay_rate=decay_rate)
        self._last_round: int = 0
        self._history: List[MomentumState] = []

    @property
    def state(self) -> MomentumState:
        return self._state

    @property
    def history(self) -> List[MomentumState]:
        return list(self._history)

    def update(self, round_won: bool, round_number: int) -> MomentumState:
        """
        Update momentum based on round outcome.

        Args:
            round_won: Whether the round was won.
            round_number: Current round number (1-indexed).

        Returns:
            Updated MomentumState.
        """
        # Check for half-switch reset
        if self._is_half_switch(round_number):
            logger.info("Half-switch at round %s, resetting momentum", round_number)
            self._reset()

        # Compute gap from last update (for decay)
        gap = max(0, round_number - self._last_round) if self._last_round > 0 else 0
        self._last_round = round_number

        # Update streak
        if round_won:
            if self._state.streak_type == "win":
                self._state.streak_length += 1
            else:
                self._state.streak_length = 1
                self._state.streak_type = "win"
        else:
            if self._state.streak_type == "loss":
                self._state.streak_length += 1
            else:
                self._state.streak_length = 1
                self._state.streak_type = "loss"

        # DESIGN: gap=0 for consecutive rounds → decay=1.0 (no dampening within a half).
        # Momentum persists fully round-to-round; decay only applies to skipped rounds.
        # This is intentional: half-switch resets (L116) handle cross-half dampening.
        decay = math.exp(-self._state.decay_rate * gap)
        streak = self._state.streak_length

        if self._state.streak_type == "win":
            raw = 1.0 + 0.05 * streak * decay
        elif self._state.streak_type == "loss":
            raw = 1.0 - 0.04 * streak * decay
        else:
            raw = 1.0

        # Clamp to bounds
        self._state.current_multiplier = max(MULTIPLIER_MIN, min(MULTIPLIER_MAX, raw))

        # Archive snapshot
        self._history.append(
            MomentumState(
                current_multiplier=self._state.current_multiplier,
                streak_length=self._state.streak_length,
                streak_type=self._state.streak_type,
                decay_rate=self._state.decay_rate,
            )
        )

        if self._state.is_tilted:
            logger.info(
                "Tilt risk detected: multiplier=%s", format(self._state.current_multiplier, ".2f")
            )

        return self._state

    def _is_half_switch(self, round_number: int) -> bool:
        """Check if this round marks a half-switch."""
        return round_number in (HALF_SWITCH_MR12, HALF_SWITCH_MR13)

    def _reset(self) -> None:
        """Reset momentum state for half-switch."""
        self._state.current_multiplier = 1.0
        self._state.streak_length = 0
        self._state.streak_type = "neutral"


def predict_performance_adjustment(
    momentum: MomentumState,
    base_rating: float,
) -> float:
    """
    Adjust expected performance rating by momentum multiplier.

    Args:
        momentum: Current MomentumState.
        base_rating: Player's base rating (e.g. HLTV 2.0).

    Returns:
        Adjusted rating.
    """
    return base_rating * momentum.current_multiplier


def from_round_stats(round_stats_list: List[dict]) -> List[MomentumState]:
    """
    Build momentum timeline from RoundStats records for a single player.

    This provides a clean round-outcome based momentum computation,
    replacing the need to reconstruct outcomes from raw tick data.

    Args:
        round_stats_list: List of RoundStats dicts (or model instances)
                          for ONE player, sorted by round_number.
                          Each must have 'round_number' and 'round_won' fields.

    Returns:
        List of MomentumState snapshots, one per round (chronological).
    """
    tracker = MomentumTracker()

    # Sort by round_number to ensure chronological order
    sorted_rounds = sorted(
        round_stats_list,
        key=lambda rs: rs["round_number"] if isinstance(rs, dict) else rs.round_number,
    )

    for rs in sorted_rounds:
        if isinstance(rs, dict):
            round_num = rs["round_number"]
            round_won = rs["round_won"]
        else:
            round_num = rs.round_number
            round_won = rs.round_won

        tracker.update(round_won=bool(round_won), round_number=int(round_num))

    return tracker.history


def get_momentum_tracker() -> MomentumTracker:
    """Factory function for singleton access."""
    return MomentumTracker()
