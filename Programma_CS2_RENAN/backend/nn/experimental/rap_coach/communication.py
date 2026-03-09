import math
from typing import Optional

import numpy as np
import torch

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.nn.experimental.rap_coach.communication")

# Relative angle sectors (degrees from facing direction)
_ANGLE_SECTORS = [
    ((-45, 45), "ahead"),
    ((45, 135), "your left flank"),
    ((-135, -45), "your right flank"),
    ((135, 180), "behind you"),
    ((-180, -135), "behind you"),
]


def _compute_relative_direction(
    player_view_angle: float,
    player_pos: tuple,
    threat_pos: tuple,
) -> str:
    """Map a threat position to a human-readable direction relative to the player."""
    dx = threat_pos[0] - player_pos[0]
    dy = threat_pos[1] - player_pos[1]
    threat_angle = math.degrees(math.atan2(dy, dx))
    relative = (threat_angle - player_view_angle + 180) % 360 - 180

    for (lo, hi), label in _ANGLE_SECTORS:
        if lo <= relative < hi:
            return label
    return "the flank"


class RAPCommunication:
    """
    Pedagogical Feedback Generator.
    Translates causal attribution into templated advice.

    Adheres to Layer 5: Multi-Timescale & Skill Modeling.
    """

    def __init__(self):
        # Level-stratified templates
        self.templates = {
            "low": {  # Level 1-3: Direct, Concrete
                "positioning": "Watch your back. You were exposed to {angle} for {time}s without checking.",
                "mechanics": "Stop moving before you shoot. Your counter-strafing was off by {error}ms.",
                "strategy": "Stick with the team. You are entering sites alone too often.",
            },
            "mid": {  # Level 4-7: Pattern-based
                "positioning": "Your site anchoring is {score}% optimal, but you over-rotate when utility lands.",
                "mechanics": "Burst control is solid, but your crosshair height dropped during the {time}s spray.",
                "strategy": "Team economy suggests a {recommendation} play. Consider saving utility for the retake.",
            },
            "high": {  # Level 8-10: Strategic / Abstract
                "positioning": "Professional positioning suggests a {angle} lurk here would have 2x advantage.",
                "mechanics": "Flick stability is high, but you are favoring left-side peeks by {error}%.",
                "strategy": "Conditioning successful. They expect an A push; a {recommendation} pivot now is optimal.",
            },
        }

    def generate_advice(
        self,
        layer_outputs,
        confidence,
        skill_level: int = 5,
        game_context: Optional[dict] = None,
    ):
        """
        Applies the 'Skill-Conditioned Explanation' rule.

        Args:
            layer_outputs: Neural network layer activations.
            confidence: Model confidence [0, 1].
            skill_level: Player skill level 1-10.
            game_context: Optional dict with keys 'player_view_angle',
                          'player_pos' (x,y), 'threat_pos' (x,y) for
                          spatial angle computation.
        """
        if confidence < 0.7:
            logger.debug("Advice suppressed: confidence %.2f below threshold 0.7", confidence)
            return None

        # 1. Determine Tier
        if skill_level <= 3:
            tier = "low"
        elif skill_level <= 7:
            tier = "mid"
        else:
            tier = "high"

        # 2. Extract Top Signal
        with torch.no_grad():
            # NN-52: Handle both tensor and list fallback paths safely
            if hasattr(layer_outputs, "squeeze"):
                scores = layer_outputs.squeeze().cpu().numpy()
            else:
                scores = np.array([0.1])
            # NN-COM-01: Ensure scores is at least 1D before argmax.
            # squeeze() can reduce to 0D scalar when output has shape (1,).
            if scores.ndim == 0:
                scores = np.array([scores.item()])
            top_idx = int(np.argmax(scores))

            topics = ["positioning", "mechanics", "strategy"]
            topic = topics[top_idx % len(topics)]

            # 3. Compute spatial angle from game context when available
            angle = self._resolve_angle(game_context)

            # 4. Format based on tier templates
            template = self.templates[tier][topic]

            return template.format(
                score=int(confidence * 100),
                time=round(float(confidence * 2), 1),
                error=int((1 - confidence) * 300),
                angle=angle,
                recommendation="conservative" if confidence > 0.8 else "aggressive",
            )

    @staticmethod
    def _resolve_angle(game_context: Optional[dict]) -> str:
        """Resolve threat angle from spatial context, falling back to generic."""
        if not game_context:
            return "the flank"
        view_angle = game_context.get("player_view_angle")
        player_pos = game_context.get("player_pos")
        threat_pos = game_context.get("threat_pos")
        if view_angle is None or player_pos is None or threat_pos is None:
            return "the flank"
        try:
            return _compute_relative_direction(float(view_angle), player_pos, threat_pos)
        except (TypeError, ValueError):
            return "the flank"
