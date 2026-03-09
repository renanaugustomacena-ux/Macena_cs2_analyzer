"""
Role-Based Feature Extraction Module.

CS2 roles (Entry, AWPer, Support, Lurker, IGL) have distinct statistical signatures.
This module provides tools to:
1. Classify player roles based on their stats
2. Extract role-specific features for coaching
3. Generate role-appropriate comparisons against pro baselines

NOTE (F2-20): Role signatures (aggression_score, entry_ratio, support_ratio, etc.) are
static heuristics based on fixed thresholds. They do not automatically adapt to
meta-shifts (e.g., if lurkers start using more utility, this module won't capture
the change). Meta-level drift is tracked separately by meta_drift.py.

R4-18-01: `get_adaptive_signatures()` applies meta_drift confidence adjustment
to widen tolerance bands when the meta is shifting significantly.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np

from Programma_CS2_RENAN.core.app_types import PlayerRole  # P3-01: canonical enum


# Role signature centroids (mean stat profiles for each role)
# Based on analysis of top 20 HLTV players in each role category
ROLE_SIGNATURES = {
    PlayerRole.ENTRY: {
        "opening_attempts_per_round": 0.35,  # High opening aggression
        "first_kill_pct": 0.18,
        "first_death_pct": 0.22,  # Dies first often
        "kpr": 0.78,
        "adr": 85.0,
        "flash_assists": 0.8,  # Lower, relies on support
        "utility_damage": 8.0,
    },
    PlayerRole.AWPER: {
        "opening_attempts_per_round": 0.25,
        "first_kill_pct": 0.20,
        "first_death_pct": 0.12,  # Rarely first death
        "kpr": 0.72,
        "adr": 75.0,
        "awp_kills_pct": 0.65,  # Primary weapon signature
        "utility_damage": 5.0,
    },
    PlayerRole.SUPPORT: {
        "opening_attempts_per_round": 0.15,
        "first_kill_pct": 0.08,
        "first_death_pct": 0.14,
        "kpr": 0.65,
        "adr": 72.0,
        "flash_assists": 2.5,  # High flash usage
        "utility_damage": 18.0,  # High utility impact
    },
    PlayerRole.LURKER: {
        "opening_attempts_per_round": 0.18,
        "first_kill_pct": 0.12,
        "first_death_pct": 0.10,
        "kpr": 0.70,
        "adr": 78.0,
        "clutch_success_rate": 0.40,  # Often in clutch situations
        "late_round_kills_pct": 0.35,
    },
    PlayerRole.IGL: {
        "opening_attempts_per_round": 0.12,
        "first_kill_pct": 0.06,
        "first_death_pct": 0.15,
        "kpr": 0.62,  # Typically lower fragging
        "adr": 68.0,
        "flash_assists": 1.8,
        "utility_damage": 12.0,
        "trade_kill_pct": 0.25,  # Often gets traded kills
    },
}


def classify_role(player_stats: Dict[str, float]) -> Tuple[PlayerRole, float]:
    """P3-04: Delegate to the canonical RoleClassifier.

    This function is kept for backward compatibility but now delegates to
    ``role_classifier.RoleClassifier`` which uses learned thresholds + neural
    consensus.  Falls back to centroid-distance heuristic when the classifier
    is in cold-start state (no learned thresholds yet).
    """
    if not player_stats:
        return PlayerRole.UNKNOWN, 0.0

    try:
        from Programma_CS2_RENAN.backend.analysis.role_classifier import RoleClassifier

        clf = RoleClassifier()
        role, confidence, _ = clf.classify(player_stats)
        return role, confidence
    except Exception:
        # Fallback: simple centroid-distance heuristic (original logic)
        return _heuristic_classify_role(player_stats)


def _heuristic_classify_role(player_stats: Dict[str, float]) -> Tuple[PlayerRole, float]:
    """Fallback Euclidean-distance classifier using static ROLE_SIGNATURES centroids."""
    classification_features = [
        "opening_attempts_per_round",
        "first_kill_pct",
        "first_death_pct",
        "kpr",
        "adr",
    ]
    normalization = {
        "opening_attempts_per_round": (0.0, 0.5),
        "first_kill_pct": (0.0, 0.30),
        "first_death_pct": (0.0, 0.30),
        "kpr": (0.5, 1.0),
        "adr": (60.0, 100.0),
    }

    def normalize(value: float, feature: str) -> float:
        min_v, max_v = normalization.get(feature, (0, 1))
        # P3-09: prevent division by near-zero range
        range_v = max_v - min_v
        if range_v < 1e-6:
            return 0.5
        return (value - min_v) / range_v

    player_vec = np.array([normalize(player_stats.get(f, 0), f) for f in classification_features])

    distances = {}
    for role, signature in ROLE_SIGNATURES.items():
        role_vec = np.array([normalize(signature.get(f, 0), f) for f in classification_features])
        distances[role] = np.linalg.norm(player_vec - role_vec)

    closest_role = min(distances, key=distances.get)
    min_distance = distances[closest_role]
    confidence = np.exp(-min_distance * 2)

    return closest_role, float(confidence)


def extract_role_features(
    player_stats: Dict[str, float], role: Optional[PlayerRole] = None
) -> Dict[str, float]:
    """
    Extracts role-specific features for coaching analysis.

    If role is not provided, it will be auto-detected.

    Args:
        player_stats: Raw player statistics
        role: Optional known role, or auto-detect if None

    Returns:
        Dict of role-specific features with deviations from role baseline
    """
    if role is None:
        role, _ = classify_role(player_stats)

    if role == PlayerRole.UNKNOWN:
        return {}

    role_baseline = ROLE_SIGNATURES.get(role, {})
    features = {}

    for stat, baseline_value in role_baseline.items():
        player_value = player_stats.get(stat, 0)

        # Calculate percentage deviation from role baseline
        if baseline_value != 0:
            deviation = (player_value - baseline_value) / baseline_value
        else:
            deviation = player_value

        features[f"{stat}_deviation"] = deviation
        features[f"{stat}_value"] = player_value
        features[f"{stat}_baseline"] = baseline_value

    features["detected_role"] = role.value

    return features


def get_adaptive_signatures(map_name: Optional[str] = None) -> Dict[PlayerRole, Dict[str, float]]:
    """R4-18-01: Return role signatures adjusted by current meta drift.

    When the meta is shifting significantly (drift > 0.3), widen tolerance
    bands proportionally so the heuristic classifier becomes more conservative
    (lower confidence) rather than mis-classifying players into stale archetypes.
    """
    import copy

    sigs = copy.deepcopy(ROLE_SIGNATURES)
    try:
        from Programma_CS2_RENAN.backend.processing.baselines.meta_drift import MetaDriftEngine

        confidence_mult = MetaDriftEngine.get_meta_confidence_adjustment(map_name)
    except Exception:
        return sigs

    # confidence_mult in [0.5, 1.0]; lower = more drift
    # P-RF-01: Scale signature values UP to widen tolerance when meta is chaotic.
    # Higher baselines → player deviations are larger → classification becomes
    # more conservative (lower confidence) rather than mis-classifying.
    if confidence_mult < 0.85:
        scale = 2.0 - confidence_mult  # e.g. 0.7 → 1.3 (widens by 30%)
        for role_sigs in sigs.values():
            for key in role_sigs:
                role_sigs[key] *= scale

    return sigs


def get_role_coaching_focus(role: PlayerRole) -> List[str]:
    """
    Returns the priority coaching areas for a given role.

    Args:
        role: Player's role

    Returns:
        List of stat keys to focus coaching on, in priority order
    """
    focus_areas = {
        PlayerRole.ENTRY: [
            "first_kill_pct",
            "opening_attempts_per_round",
            "kpr",
            "trade_death_pct",  # Getting traded when dying
        ],
        PlayerRole.AWPER: [
            "awp_kills_pct",
            "opening_kill_with_awp",
            "first_death_pct",  # Should be LOW
            "save_success_rate",
        ],
        PlayerRole.SUPPORT: [
            "flash_assists",
            "utility_damage",
            "trade_kill_pct",
            "kast",
        ],
        PlayerRole.LURKER: [
            "clutch_success_rate",
            "late_round_kills_pct",
            "info_kills",  # Kills that reveal enemy positions
            "survival_rate",
        ],
        PlayerRole.IGL: [
            "kast",
            "utility_usage_efficiency",
            "trade_coordination",
            "eco_round_performance",
        ],
    }

    return focus_areas.get(role, ["kpr", "adr", "kast"])
