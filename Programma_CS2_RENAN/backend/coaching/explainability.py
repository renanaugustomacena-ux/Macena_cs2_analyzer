from typing import Dict, List, Optional

import numpy as np

from Programma_CS2_RENAN.backend.nn.rap_coach.skill_model import SkillAxes

# Coaching thresholds — extracted for visibility and tunability
SILENCE_THRESHOLD = 0.2  # |delta| below this -> no feedback (silence is valid)
SEVERITY_HIGH_BOUNDARY = 1.5  # |delta| above this -> "High" severity
SEVERITY_MEDIUM_BOUNDARY = 0.8  # |delta| above this -> "Medium" severity


class ExplanationGenerator:
    """
    Implementation of Phase 6: Explainability & Feedback.
    Translates latent RL signals into human-readable narratives.
    """

    TEMPLATES = {
        SkillAxes.MECHANICS: {
            "negative": "Your {feature} is currently {delta}% below professional standards. This led to {impact} during meaningful engagements.",
            "positive": "{feature} is at peak professional level. You are maintaining {score}% stability with your {weapon}.",
            "action": "Focus on your crosshair height when clearing corners with your {weapon}.",
        },
        SkillAxes.POSITIONING: {
            "negative": "Positioning at {location} was suboptimal. You were exposed to multiple angles for {time}s.",
            "positive": "Excellent anchoring of {location}. Professional occupancy heatmap aligns with your playstyle here.",
            "action": "Try holding a tighter angle at {location} to reduce exposure.",
        },
        SkillAxes.UTILITY: {
            "negative": "Utility timing with {weapon} was suboptimal. {enemies} enemies were unaffected by the deployment.",
            "positive": "High-impact {weapon} usage! You blinded {enemies} enemies for {time}s.",
            "action": "Wait for a clear sound cue before deploying your {weapon} to maximize effectiveness.",
        },
        SkillAxes.TIMING: {
            "negative": "Engagement timing is lagging behind. You are {delta}% slower than the pro baseline.",
            "positive": "Flawless timing! You are identifying engagement windows with {score}% precision.",
            "action": "Coordinate with teammates to trade-frag more effectively when pushing {location}.",
        },
        SkillAxes.DECISION: {
            "negative": "Decision efficiency is {delta}% lower than optimal. Consider the {recommendation} play next time.",
            "positive": "Elite game sense. Your KAST-driven decisions provide a {score}% win advantage.",
            "action": "In clutch scenarios, prioritize the round objective over the hunt.",
        },
    }

    @staticmethod
    def generate_narrative(
        category: SkillAxes, feature: str, delta: float, context: Dict = None, skill_level: int = 5
    ) -> str:
        """
        Grounded Narrative Generation with Dynamic Context.
        """
        if category not in ExplanationGenerator.TEMPLATES:
            return f"Ongoing analysis of {feature} patterns..."

        templates = ExplanationGenerator.TEMPLATES[category]
        ctx = context or {}

        # Rule: Silence is a Valid Action (Confidence thresholding)
        if abs(delta) < SILENCE_THRESHOLD:
            return ""

        style = "negative" if delta < 0 else "positive"
        base = templates[style].format(
            feature=feature.replace("avg_", "").replace("_", " "),
            delta=abs(int(delta * 100)),
            score=max(0, int(100 - abs(delta * 100))),
            impact="missed opportunities",
            location=ctx.get("location", "your current sector"),
            time=ctx.get("time", "1.2"),
            enemies=ctx.get("enemies", "multiple"),
            weapon=ctx.get("weapon", "equipment"),
            recommendation="conservative" if skill_level < 5 else "aggressive",
        )

        # Skill-level verbosity/complexity filter
        if skill_level < 3 and style == "negative":
            return f"Goal ({category}): {templates['action'].format(location='the objective', weapon='utility')}"

        action = templates["action"].format(
            location=ctx.get("location", "the sector"), weapon=ctx.get("weapon", "utility")
        )

        return f"{base} {action}"

    @staticmethod
    def classify_insight_severity(delta: float) -> str:
        d = abs(delta)
        if d > SEVERITY_HIGH_BOUNDARY:
            return "High"
        if d > SEVERITY_MEDIUM_BOUNDARY:
            return "Medium"
        return "Low"
