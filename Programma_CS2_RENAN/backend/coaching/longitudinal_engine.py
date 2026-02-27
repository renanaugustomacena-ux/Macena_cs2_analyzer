"""
Longitudinal Coaching Engine

Generates trend-aware coaching insights by comparing a player's performance
trajectory across multiple sessions against NN stability signals.
"""

from typing import Any, Dict, List

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.coaching.longitudinal")


def generate_longitudinal_coaching(trends: List[Any], nn_signals: Dict[str, Any]) -> List[Dict]:
    insights: List[Dict] = []
    for t in trends:
        if t.confidence >= 0.6:
            _process_trend(t, nn_signals, insights)
    return insights[:3]


def _process_trend(t, nn_signals, insights):
    if t.slope < 0:
        insight = _create_regression_insight(t)
        if nn_signals.get("stability_warning"):
            insight["severity"] = "High"
        insights.append(insight)
    if t.slope > 0:
        insights.append(_create_improvement_insight(t))


def _create_regression_insight(t):
    return {
        "title": f"{t.feature.capitalize()} Regression",
        "severity": "Medium",
        "message": f"Your {t.feature} is declining over time. Refocus on fundamentals.",
        "focus_area": "Consistency",
    }


def _create_improvement_insight(t):
    return {
        "title": f"{t.feature.capitalize()} Improvement",
        "severity": "Positive",
        "message": f"Your {t.feature} is steadily improving. Maintain this approach.",
        "focus_area": "Reinforcement",
    }
