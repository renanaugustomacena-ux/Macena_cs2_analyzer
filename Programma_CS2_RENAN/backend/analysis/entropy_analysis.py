"""
Entropy Delta for Utility Evaluation (Phase 6: Game Theory)

Measures the information-theoretic impact of utility usage (smokes, flashes,
molotovs) by computing the entropy reduction in enemy position distribution
after each utility throw.

Governance: Rule 1 §7.4 (Information-theoretic metrics), Rule 2 §8.2 (Quantitative utility evaluation)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.analysis.entropy")

# Theoretical max entropy reduction per utility type (in bits)
_MAX_DELTA: Dict[str, float] = {
    "smoke": 2.5,
    "flash": 1.8,
    "molotov": 2.0,
    "he_grenade": 1.5,
}


@dataclass
class UtilityImpact:
    """Information-theoretic impact of a single utility throw."""

    pre_entropy: float
    post_entropy: float
    entropy_delta: float
    utility_type: str
    effectiveness_rating: float


class EntropyAnalyzer:
    """
    Computes Shannon entropy of enemy position distributions before and after
    utility usage to quantify each throw's information-theoretic impact.
    """

    def __init__(self, grid_resolution: int = 32):
        # Default 32x32 grid. Sufficient for macro-positioning analysis.
        # For fine-grained clustering, KDE would provide smoother estimates.
        self.grid_resolution = grid_resolution

    def compute_position_entropy(
        self,
        player_positions: List[Tuple[float, float]],
        grid_resolution: Optional[int] = None,
    ) -> float:
        """
        Compute Shannon entropy H of a set of player positions.

        Discretizes the map into a grid, computes the probability distribution
        across occupied cells, and returns ``H = -sum(p * log2(p))``.

        Args:
            player_positions: List of (x, y) world-coordinate tuples.
            grid_resolution: Override for grid size (default: self.grid_resolution).

        Returns:
            Shannon entropy in bits. 0.0 if no positions.
        """
        res = grid_resolution or self.grid_resolution
        if not player_positions:
            return 0.0

        grid = np.zeros((res, res), dtype=np.float32)

        xs = [p[0] for p in player_positions]
        ys = [p[1] for p in player_positions]

        x_min, x_max = min(xs) - 1, max(xs) + 1
        y_min, y_max = min(ys) - 1, max(ys) + 1

        x_range = x_max - x_min if x_max != x_min else 1.0
        y_range = y_max - y_min if y_max != y_min else 1.0

        for x, y in player_positions:
            gx = int((x - x_min) / x_range * (res - 1))
            gy = int((y - y_min) / y_range * (res - 1))
            gx = max(0, min(res - 1, gx))
            gy = max(0, min(res - 1, gy))
            grid[gy, gx] += 1.0

        total = grid.sum()
        if total == 0:
            return 0.0

        probs = grid.ravel() / total
        probs = probs[probs > 0]

        entropy = -np.sum(probs * np.log2(probs))
        return float(entropy)

    def analyze_utility_throw(
        self,
        pre_positions: List[Tuple[float, float]],
        post_positions: List[Tuple[float, float]],
        utility_type: str,
    ) -> UtilityImpact:
        """
        Analyze the information impact of a single utility throw.

        Args:
            pre_positions: Enemy positions before utility effect.
            post_positions: Enemy positions after utility resolves.
            utility_type: "smoke", "flash", "molotov", or "he_grenade".

        Returns:
            UtilityImpact with pre/post entropy, delta, and effectiveness rating.
        """
        pre_h = self.compute_position_entropy(pre_positions)
        post_h = self.compute_position_entropy(post_positions)

        delta = pre_h - post_h  # Positive = information gained

        # Effectiveness relative to theoretical max for this utility type
        max_delta = _MAX_DELTA.get(utility_type, 2.0)
        effectiveness = max(0.0, min(1.0, delta / max_delta)) if max_delta > 0 else 0.0

        return UtilityImpact(
            pre_entropy=pre_h,
            post_entropy=post_h,
            entropy_delta=delta,
            utility_type=utility_type,
            effectiveness_rating=effectiveness,
        )

    def rank_utility_usage(
        self,
        round_utilities: List[UtilityImpact],
    ) -> List[UtilityImpact]:
        """
        Sort utility throws by effectiveness rating (descending).

        Useful for coaching: "Your best smoke reduced uncertainty by X bits."
        """
        return sorted(round_utilities, key=lambda u: u.effectiveness_rating, reverse=True)


def get_entropy_analyzer() -> EntropyAnalyzer:
    """Factory function for singleton access."""
    return EntropyAnalyzer()
