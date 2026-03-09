"""
Strategic Blind Spot Detection (Phase 6: Game Theory)

Identifies recurring situations where a player consistently makes suboptimal
decisions by comparing their actual actions against game tree optimal actions.

Governance: Rule 1 §8.2 (Pattern-based weakness identification), Rule 3 §3.1 (Actionable coaching output)
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.analysis.blind_spots")


@dataclass
class BlindSpot:
    """A recurring strategic weakness."""

    situation_type: str  # e.g. "2v1 retake", "eco rush", "post-plant"
    optimal_action: str  # Action recommended by game tree
    actual_action: str  # Action the player actually took
    frequency: int = 0  # Number of occurrences
    impact_rating: float = 0.0  # Average win-prob delta (optimal - actual)

    @property
    def priority(self) -> float:
        """Combined priority score for coaching ranking."""
        return self.frequency * self.impact_rating


class BlindSpotDetector:
    """
    Detects strategic blind spots by comparing player actions to game tree
    optimal recommendations across historical rounds.
    """

    def __init__(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch

        self._search = ExpectiminimaxSearch()

    def detect(
        self,
        player_history: List[Dict],
        game_tree: Optional[object] = None,
    ) -> List[BlindSpot]:
        """
        Detect blind spots from historical round data.

        Args:
            player_history: List of round dicts, each containing:
                - 'game_state': Dict matching GameState fields
                - 'action_taken': str (what the player did)
                - 'round_won': bool
                - Optional context fields (alive_players, enemy_alive, etc.)
            game_tree: Optional pre-built ExpectiminimaxSearch (uses internal default if None).

        Returns:
            List of BlindSpot instances sorted by priority (highest first).
        """
        search = game_tree if game_tree is not None else self._search
        mismatches: Dict[str, List[Dict]] = defaultdict(list)

        for round_data in player_history:
            state = round_data.get("game_state", {})
            actual = round_data.get("action_taken", "hold")

            if not state:
                continue

            # B-01: Wrap game tree analysis in try-except — malformed states
            # (missing keys, invalid types) should skip the round, not crash.
            try:
                # Get optimal action from game tree
                root = search.build_tree(state, depth=2)
                optimal, optimal_value = search.get_best_action(root)

                if optimal == actual:
                    continue  # Player chose optimally

                # Classify situation
                situation = self._classify_situation(state)

                # Compute impact: how much worse was the actual choice
                actual_value = self._evaluate_action(search, state, actual)
                impact = max(0.0, optimal_value - actual_value)
            except Exception as e:
                logger.debug("B-01: Blind spot analysis skipped for round: %s", e)
                continue

            mismatches[situation].append(
                {
                    "optimal": optimal,
                    "actual": actual,
                    "impact": impact,
                }
            )

        # Aggregate into BlindSpot instances
        spots: List[BlindSpot] = []
        for situation, cases in mismatches.items():
            if not cases:
                continue

            # Find the most common mismatch pattern
            pattern_counts: Dict[str, int] = defaultdict(int)
            pattern_impacts: Dict[str, List[float]] = defaultdict(list)

            for case in cases:
                key = f"{case['optimal']}|{case['actual']}"
                pattern_counts[key] += 1
                pattern_impacts[key].append(case["impact"])

            for key, count in pattern_counts.items():
                optimal_act, actual_act = key.split("|")
                avg_impact = sum(pattern_impacts[key]) / len(pattern_impacts[key])

                spots.append(
                    BlindSpot(
                        situation_type=situation,
                        optimal_action=optimal_act,
                        actual_action=actual_act,
                        frequency=count,
                        impact_rating=avg_impact,
                    )
                )

        spots.sort(key=lambda s: s.priority, reverse=True)
        return spots

    def _classify_situation(self, state: Dict) -> str:
        """Classify a game state into a human-readable situation type."""
        alive = state.get("alive_players", 5)
        enemy = state.get("enemy_alive", 5)
        bomb = state.get("bomb_planted", False)
        time_left = state.get("time_remaining", 115)

        if bomb:
            if alive > enemy:
                return "post-plant advantage"
            elif alive < enemy:
                return "post-plant disadvantage"
            return "post-plant even"

        if alive == 1 and enemy >= 2:
            return f"1v{enemy} clutch"
        if alive >= 2 and enemy == 1:
            return f"{alive}v1 retake"
        if alive < enemy:
            return "numbers disadvantage"
        if alive > enemy:
            return "numbers advantage"

        econ_diff = state.get("team_economy", 4000) - state.get("enemy_economy", 4000)
        if econ_diff < -3000:
            return "eco round"
        if econ_diff > 3000:
            return "economic advantage"

        if time_left < 30:
            return "late round"

        return "standard"

    def _evaluate_action(self, search, state: Dict, action: str) -> float:
        """Evaluate a specific action via the game tree public API (F4-03)."""
        return search.evaluate_single_action(state, action)

    def generate_training_plan(
        self,
        blind_spots: List[BlindSpot],
        top_n: int = 3,
    ) -> str:
        """
        Generate a natural-language coaching plan targeting the most impactful blind spots.

        Args:
            blind_spots: Detected blind spots (should be pre-sorted by priority).
            top_n: Number of top blind spots to include.

        Returns:
            Multi-line coaching plan string.
        """
        if not blind_spots:
            return (
                "No strategic blind spots detected. Your decision-making aligns with optimal play."
            )

        top = blind_spots[:top_n]
        lines = ["## Strategic Training Plan\n"]

        for i, spot in enumerate(top, 1):
            action_advice = {
                "push": "practice aggressive timing and trade-fragging",
                "hold": "practice passive positioning and crosshair placement",
                "rotate": "practice map awareness and rotation timing",
                "use_utility": "practice utility lineups and timing",
            }

            advice = action_advice.get(spot.optimal_action, f"practice {spot.optimal_action}")

            lines.append(
                f"**{i}. {spot.situation_type.title()}** "
                f"(seen {spot.frequency}x, impact: {spot.impact_rating:.0%})\n"
                f"   You tend to **{spot.actual_action}** when the optimal play is to "
                f"**{spot.optimal_action}**.\n"
                f"   Training: {advice} in {spot.situation_type} scenarios.\n"
            )

        return "\n".join(lines)


def get_blind_spot_detector() -> BlindSpotDetector:
    """Factory function for singleton access."""
    return BlindSpotDetector()
