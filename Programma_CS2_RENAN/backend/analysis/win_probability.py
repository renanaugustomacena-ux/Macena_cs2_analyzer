"""
Win Probability Predictor

Predicts round win probability from current game state.
Uses neural network trained on pro demo data.

Features:
- Real-time probability updates
- Economy-aware predictions
- Player advantage modeling
- Time remaining factor

Adheres to GEMINI.md principles:
- Clean architecture
- Explicit state management
- GPU-friendly operations
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.win_probability")


@dataclass
class GameState:
    """
    Current game state for win probability prediction.

    Attributes:
        team_economy: Team's total economy ($)
        enemy_economy: Enemy team's economy ($)
        alive_players: Number of alive teammates (0-5)
        enemy_alive: Number of alive enemies (0-5)
        utility_remaining: Number of utility items remaining
        map_control_pct: Percentage of map controlled (0-1)
        time_remaining: Seconds remaining in round
        bomb_planted: Whether bomb is planted
        is_ct: Whether team is CT side
    """

    team_economy: int
    enemy_economy: int
    alive_players: int
    enemy_alive: int
    utility_remaining: int = 0
    map_control_pct: float = 0.5
    time_remaining: int = 115
    bomb_planted: bool = False
    is_ct: bool = True


class WinProbabilityNN(nn.Module):
    """
    Neural network for round win probability prediction.

    Architecture:
    - Input: 12 game state features
    - Hidden: 64 → 32 neurons with ReLU + Dropout
    - Output: Sigmoid (probability 0-1)

    From Phase 1B Roadmap:
    Target accuracy: 72%+ on test set
    """

    def __init__(self, input_dim: int = 12, hidden_dim: int = 64):
        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid(),
        )

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Xavier initialization for stable training."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Args:
            x: Game state features [batch, 12]

        Returns:
            Win probability [batch, 1]
        """
        return self.network(x)


class WinProbabilityPredictor:
    """
    Win probability prediction engine.

    Uses neural network for prediction with rule-based fallbacks.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model = WinProbabilityNN()
        self._checkpoint_loaded = False

        if model_path:
            try:
                self.model.load_state_dict(torch.load(model_path, weights_only=True))
                self._checkpoint_loaded = True
                logger.info("Loaded win probability model from %s", model_path)
            except Exception as e:
                logger.warning("Could not load model: %s. Using heuristic.", e)

        if not self._checkpoint_loaded:
            logger.warning(
                "AC-11-01: No checkpoint loaded — predictions use random weights. "
                "Heuristic adjustments will dominate. Train or provide a model_path."
            )

        self.model.eval()

    def predict(self, game_state: GameState) -> Tuple[float, str]:
        """
        Predict win probability from game state.

        Args:
            game_state: Current game state

        Returns:
            (probability, explanation)
        """
        # Extract features
        features = self._extract_features(game_state)

        # Predict with neural network
        with torch.no_grad():
            x = torch.FloatTensor(features).unsqueeze(0)
            prob = self.model(x).item()

        # Apply heuristic adjustments
        prob = self._apply_heuristics(prob, game_state)

        # Generate explanation
        explanation = self._generate_explanation(prob, game_state)

        return prob, explanation

    def _extract_features(self, state: GameState) -> np.ndarray:
        """Extract normalized features from game state."""
        return np.array(
            [
                # Economy (normalized to 16000 max)
                state.team_economy / 16000,
                state.enemy_economy / 16000,
                (state.team_economy - state.enemy_economy) / 16000,
                # Player counts (normalized to 5)
                state.alive_players / 5,
                state.enemy_alive / 5,
                (state.alive_players - state.enemy_alive) / 5,
                # Utility (normalized to 10)
                state.utility_remaining / 10,
                # Map control
                state.map_control_pct,
                # Time (normalized to 115s)
                state.time_remaining / 115,
                # Binary features
                1.0 if state.bomb_planted else 0.0,
                1.0 if state.is_ct else 0.0,
                # Derived: Expected equipment value ratio
                min(state.team_economy / max(state.enemy_economy, 1), 2) / 2,
            ],
            dtype=np.float32,
        )

    def _apply_heuristics(self, prob: float, state: GameState) -> float:
        """Apply rule-based adjustments to probability."""
        # Deterministic boundary checks FIRST — before any probabilistic adjustments
        if state.alive_players == 0:
            return 0.0
        if state.enemy_alive == 0:
            return 1.0

        # Player advantage is highly predictive
        player_diff = state.alive_players - state.enemy_alive

        if player_diff >= 3:
            prob = max(prob, 0.85)
        elif player_diff <= -3:
            prob = min(prob, 0.15)

        # W-01: Bomb planted adjustments — additive to stay within [0, 1]
        # at every intermediate step (no transient overflow).
        if state.bomb_planted:
            if not state.is_ct:
                prob = min(prob + 0.10, 1.0)  # T advantage
            else:
                prob = max(prob - 0.10, 0.0)  # CT disadvantage

        # Economy heuristics (Fallback for untrained models)
        econ_diff = state.team_economy - state.enemy_economy
        if econ_diff > 8000:
            prob = max(prob, 0.65)
        elif econ_diff < -8000:
            prob = min(prob, 0.35)

        return max(0, min(1, prob))

    def _generate_explanation(self, prob: float, state: GameState) -> str:
        """Generate human-readable explanation."""
        if prob > 0.70:
            return f"Favorable position ({prob:.0%})"
        elif prob > 0.50:
            return f"Slight advantage ({prob:.0%})"
        elif prob > 0.30:
            return f"Slight disadvantage ({prob:.0%})"
        else:
            return f"Unfavorable position ({prob:.0%})"

    def predict_from_dict(self, state_dict: Dict) -> Tuple[float, str]:
        """Predict from dictionary (convenience method)."""
        game_state = GameState(
            team_economy=state_dict.get("team_economy", 4000),
            enemy_economy=state_dict.get("enemy_economy", 4000),
            alive_players=state_dict.get("alive_players", 5),
            enemy_alive=state_dict.get("enemy_alive", 5),
            utility_remaining=state_dict.get("utility_remaining", 0),
            map_control_pct=state_dict.get("map_control_pct", 0.5),
            time_remaining=state_dict.get("time_remaining", 115),
            bomb_planted=state_dict.get("bomb_planted", False),
            is_ct=state_dict.get("is_ct", True),
        )
        return self.predict(game_state)


def get_win_predictor() -> WinProbabilityPredictor:
    """Factory function for win predictor."""
    return WinProbabilityPredictor()


if __name__ == "__main__":
    # Self-test
    logger.info("=== Win Probability Predictor Test ===\n")

    predictor = WinProbabilityPredictor()

    # Test scenarios
    scenarios = [
        {
            "name": "Even match",
            "state": GameState(
                team_economy=4500, enemy_economy=4500, alive_players=5, enemy_alive=5
            ),
        },
        {
            "name": "Man advantage (4v2)",
            "state": GameState(
                team_economy=4000, enemy_economy=3000, alive_players=4, enemy_alive=2
            ),
        },
        {
            "name": "Economy disadvantage",
            "state": GameState(
                team_economy=2000, enemy_economy=8000, alive_players=5, enemy_alive=5
            ),
        },
        {
            "name": "Bomb planted (T side)",
            "state": GameState(
                team_economy=4000,
                enemy_economy=4000,
                alive_players=3,
                enemy_alive=3,
                bomb_planted=True,
                is_ct=False,
            ),
        },
    ]

    for scenario in scenarios:
        prob, explanation = predictor.predict(scenario["state"])
        logger.info("%s: %.1f%% - %s", scenario["name"], prob * 100, explanation)
