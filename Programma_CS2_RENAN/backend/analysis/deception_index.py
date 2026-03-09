"""
Deception Index (Phase 6: Game Theory)

Quantifies the degree of tactical deception in a player's behavior by measuring
the divergence between observable actions and true intent.

Governance: Rule 1 §7.2 (Game-theoretic analysis), Rule 2 §8.1 (Novel metrics require validation)
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.analysis.deception")

# Configurable detection windows (in seconds)
FAKE_EXECUTE_WINDOW = 5.0  # Time window to detect site-take fakes
UTILITY_FOLLOWUP_WINDOW = 3.0  # Time after utility for expected engagement
FLASH_BLIND_WINDOW_TICKS: int = 128  # ~2 s at 64 tick

# P8-04: Composite deception index weights. Sum = 1.0.
# Hand-tuned based on subjective impact assessment:
#   - Rotation feints (0.40): highest weight because position > utility in CS2 info-war
#   - Sound deception (0.35): fake-step / gun-switch noise exploits directional audio
#   - Fake flash (0.25): lowest weight because flash baits are common at all skill levels
# Validation: compute distribution of deception indices for pro vs amateur matches.
# Discriminative weights should produce significantly higher indices for pro players.
W_FAKE_FLASH = 0.25
W_ROTATION_FEINT = 0.40
W_SOUND_DECEPTION = 0.35


@dataclass
class DeceptionMetrics:
    """Quantified deception metrics for a round or match."""

    fake_flash_rate: float = 0.0
    rotation_feint_rate: float = 0.0
    sound_deception_score: float = 0.0
    composite_index: float = 0.0


class DeceptionAnalyzer:
    """
    Analyzes tactical deception patterns in round data.

    Detects fake executes, flash/smoke baits, and deliberate
    noise generation to quantify a player's deception sophistication.
    """

    def __init__(
        self,
        fake_execute_window: float = FAKE_EXECUTE_WINDOW,
        utility_followup_window: float = UTILITY_FOLLOWUP_WINDOW,
    ):
        self.fake_execute_window = fake_execute_window
        self.utility_followup_window = utility_followup_window

    def analyze_round(self, round_data: pd.DataFrame) -> DeceptionMetrics:
        """
        Analyze a single round for deception patterns.

        Expected columns: tick, player_name, pos_x, pos_y, event_type,
        event_detail, team, round_number.

        Returns:
            DeceptionMetrics with individual rates and composite index.
        """
        if round_data.empty:
            return DeceptionMetrics()

        fake_flash = self._detect_flash_baits(round_data)
        rotation_feint = self._detect_rotation_feints(round_data)
        sound_deception = self._detect_sound_deception(round_data)

        composite = (
            W_FAKE_FLASH * fake_flash
            + W_ROTATION_FEINT * rotation_feint
            + W_SOUND_DECEPTION * sound_deception
        )

        return DeceptionMetrics(
            fake_flash_rate=fake_flash,
            rotation_feint_rate=rotation_feint,
            sound_deception_score=sound_deception,
            composite_index=min(1.0, composite),
        )

    def _detect_flash_baits(self, df: pd.DataFrame) -> float:
        """Detect flash throws that don't blind enemies (bait fakes)."""
        if "event_type" not in df.columns:
            return 0.0

        flashes = df[df["event_type"] == "flashbang_throw"]
        if flashes.empty:
            return 0.0

        blinds = df[df["event_type"] == "player_blind"]
        total_flashes = len(flashes)

        if blinds.empty:
            # No blinds at all — every flash is a bait
            return 1.0

        # Vectorized: use sorted blind ticks + searchsorted for O(F·log B)
        flash_ticks = flashes["tick"].values
        blind_ticks = np.sort(blinds["tick"].values)

        # For each flash, find the first blind tick >= flash_tick
        idx = np.searchsorted(blind_ticks, flash_ticks, side="left")
        # A flash is "effective" if the nearest blind tick is within the window
        effective_mask = (idx < len(blind_ticks)) & (
            blind_ticks[np.minimum(idx, len(blind_ticks) - 1)] <= flash_ticks + FLASH_BLIND_WINDOW_TICKS
        )
        effective_flashes = int(np.sum(effective_mask))

        bait_rate = 1.0 - (effective_flashes / max(1, total_flashes))
        return min(1.0, bait_rate)

    def _detect_rotation_feints(self, df: pd.DataFrame) -> float:
        """
        Detect fake executes: movement toward site A followed by rapid rotation to B.

        Measures direction changes that indicate strategic misdirection.
        """
        if "pos_x" not in df.columns or "pos_y" not in df.columns:
            return 0.0

        if len(df) < 20:
            return 0.0

        # Sample positions at intervals to detect movement direction changes
        positions = df[["pos_x", "pos_y"]].values
        n = len(positions)
        step = max(1, n // 20)
        sampled = positions[::step]

        if len(sampled) < 3:
            return 0.0

        # AC-04-01: Normalize minimum displacement by map scale (ptp = point-to-point extent)
        # so the threshold adapts to different coordinate systems across maps.
        map_extent = max(float(np.ptp(positions[:, 0])), float(np.ptp(positions[:, 1])), 1.0)
        min_displacement = map_extent * 0.001  # 0.1% of map extent

        # Compute direction changes (angular velocity)
        direction_changes = 0
        significant_changes = 0

        for i in range(1, len(sampled) - 1):
            dx1 = sampled[i][0] - sampled[i - 1][0]
            dy1 = sampled[i][1] - sampled[i - 1][1]
            dx2 = sampled[i + 1][0] - sampled[i][0]
            dy2 = sampled[i + 1][1] - sampled[i][1]

            mag1 = np.sqrt(dx1**2 + dy1**2)
            mag2 = np.sqrt(dx2**2 + dy2**2)

            if mag1 < min_displacement or mag2 < min_displacement:
                continue

            cos_angle = (dx1 * dx2 + dy1 * dy2) / (mag1 * mag2)
            cos_angle = np.clip(cos_angle, -1.0, 1.0)
            angle = np.arccos(cos_angle)

            direction_changes += 1
            if angle > np.pi * 0.6:  # > 108° turn = significant reversal
                significant_changes += 1

        if direction_changes == 0:
            return 0.0

        return min(1.0, significant_changes / max(1, direction_changes))

    def _detect_sound_deception(self, df: pd.DataFrame) -> float:
        """
        Detect deliberate noise generation vs. silent movement.

        High ratio of sprinting (noisy) in non-combat situations suggests
        intentional sound cues for misdirection.
        """
        if "is_crouching" not in df.columns:
            return 0.0

        total_ticks = len(df)
        if total_ticks == 0:
            return 0.0

        crouching_ticks = df["is_crouching"].sum()
        crouch_ratio = crouching_ticks / total_ticks

        # High crouch ratio = stealthy; low = noisy (potential deception)
        # Score inverts: more noise in "safe" zones = more deceptive
        return min(1.0, max(0.0, 1.0 - crouch_ratio * 2.0))

    def compare_to_baseline(
        self,
        metrics: DeceptionMetrics,
        pro_baseline: DeceptionMetrics,
    ) -> str:
        """Generate natural-language comparison for coaching output."""
        parts: List[str] = []

        delta_composite = metrics.composite_index - pro_baseline.composite_index

        if delta_composite > 0.15:
            parts.append(
                f"Your deception index ({metrics.composite_index:.2f}) is above "
                f"the pro baseline ({pro_baseline.composite_index:.2f}). "
                "Your fakes and rotations are well-developed."
            )
        elif delta_composite < -0.15:
            parts.append(
                f"Your deception index ({metrics.composite_index:.2f}) is below "
                f"the pro baseline ({pro_baseline.composite_index:.2f}). "
                "Consider incorporating more fake executes and utility baits."
            )
        else:
            parts.append(
                f"Your deception index ({metrics.composite_index:.2f}) aligns "
                f"with pro standards ({pro_baseline.composite_index:.2f})."
            )

        if metrics.rotation_feint_rate < pro_baseline.rotation_feint_rate - 0.1:
            parts.append(
                "Pro players use rotation feints more frequently. "
                "Practice fake site-takes to create map control."
            )

        return " ".join(parts)


def get_deception_analyzer() -> DeceptionAnalyzer:
    """Factory function for singleton access."""
    return DeceptionAnalyzer()
