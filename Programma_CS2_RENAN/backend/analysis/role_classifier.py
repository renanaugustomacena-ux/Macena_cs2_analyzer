"""
Role Classifier

Classifies player roles from match statistics.
Identifies: AWPer, Entry Fragger, Support, IGL, Lurker

Uses statistical analysis and rule-based classification
with optional ML enhancement.

From Phase 1B Roadmap:
Target accuracy: 80%+ agreement with manual labels
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from Programma_CS2_RENAN.core.app_types import PlayerRole  # P3-01: canonical enum
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.role_classifier")


@dataclass
class RoleProfile:
    """
    Profile of typical role characteristics.

    Used for role classification and coaching.
    """

    role: PlayerRole
    description: str
    key_stats: Dict[str, str]  # Stat name → expected range
    coaching_focus: List[str]


# Cold-start fallback tips per role. Used when RAG knowledge base is
# unavailable or returns no results. These are generic CS2 fundamentals
# that are always valid, not map- or meta-specific.
_FALLBACK_TIPS = {
    PlayerRole.AWPER: [
        "Hold angles patiently — avoid aggressive peeks with the AWP",
        "Reposition after each shot to avoid counter-AWP trades",
    ],
    PlayerRole.ENTRY: [
        "Use utility before peeking — flash or smoke your entry point",
        "Communicate contact calls immediately for teammate trades",
    ],
    PlayerRole.SUPPORT: [
        "Prioritize trading your entry fragger over getting your own kills",
        "Save utility for teammate support, not solo plays",
    ],
    PlayerRole.IGL: [
        "Track team economy — avoid force-buying when a full save is better",
        "Call rotations early based on information, not impulse",
    ],
    PlayerRole.LURKER: [
        "Time your flanks with your team's execute — too early wastes the surprise",
        "Gather information silently before committing to engagements",
    ],
    PlayerRole.FLEX: [
        "Adapt your playstyle to what the team needs each round",
        "Fill gaps — if no one is supporting, prioritize utility usage",
    ],
}

# Role profiles for coaching
# Anti-Mock: These profiles contain static metadata but coaching tips must be learned/retrieved
ROLE_PROFILES = {
    PlayerRole.AWPER: RoleProfile(
        role=PlayerRole.AWPER,
        description="Primary sniper, holds angles and gets picks",
        key_stats={"awp_kill_ratio": "High", "first_kill_rate": "High"},
        coaching_focus=[],  # Populated dynamically from Knowledge Base
    ),
    PlayerRole.ENTRY: RoleProfile(
        role=PlayerRole.ENTRY,
        description="First player into sites, creates space",
        key_stats={"entry_rate": "High", "first_death_rate": "High"},
        coaching_focus=[],  # Populated dynamically from Knowledge Base
    ),
    PlayerRole.SUPPORT: RoleProfile(
        role=PlayerRole.SUPPORT,
        description="Trades teammates, provides utility",
        key_stats={"assist_rate": "High", "utility_damage": "High"},
        coaching_focus=[],  # Populated dynamically from Knowledge Base
    ),
    PlayerRole.IGL: RoleProfile(
        role=PlayerRole.IGL,
        description="In-game leader, calls strategies",
        key_stats={"survival_rate": "High", "economy_management": "High"},
        coaching_focus=[],  # Populated dynamically from Knowledge Base
    ),
    PlayerRole.LURKER: RoleProfile(
        role=PlayerRole.LURKER,
        description="Off-angle player, catches rotations",
        key_stats={"solo_kill_rate": "High", "rotation_time": "Late"},
        coaching_focus=[],  # Populated dynamically from Knowledge Base
    ),
    PlayerRole.FLEX: RoleProfile(
        role=PlayerRole.FLEX,
        description="Adaptable player, fills gaps in team needs",
        key_stats={"versatility": "High"},
        coaching_focus=[],  # Populated dynamically from Knowledge Base
    ),
}


class RoleClassifier:
    """
    Classifies player roles from match statistics.

    Uses weighted scoring system:
    1. Calculate role affinity scores
    2. Apply thresholds (LEARNED from real data, never mocked)
    3. Select highest scoring role

    Anti-Mock Philosophy:
        - Thresholds are NEVER hardcoded
        - Uses RoleThresholdStore which learns from HLTV/demo data
        - Cold start detection: returns FLEX with 0% confidence if no learned data
    """

    def __init__(self, threshold_store=None):
        """
        Initialize role classifier with dynamic threshold store.

        Args:
            threshold_store: Optional RoleThresholdStore. If None, uses singleton.
        """
        from Programma_CS2_RENAN.backend.processing.baselines.role_thresholds import (
            get_role_threshold_store,
        )

        self.threshold_store = threshold_store or get_role_threshold_store()

        # Log cold start state
        if self.threshold_store.is_cold_start():
            logger.warning(
                "RoleClassifier initialized in COLD START state. "
                "Role classification will return FLEX with 0% confidence until thresholds are learned."
            )

    def classify(self, player_stats: Dict[str, float]) -> Tuple[PlayerRole, float, RoleProfile]:
        """
        Classify player role from statistics.

        Args:
            player_stats: Dictionary of player statistics

        Returns:
            (role, confidence, role_profile)

        Cold Start Behavior:
            If thresholds haven't been learned yet, returns FLEX with 0% confidence.
            This prevents the coach from making decisions based on non-existent data.
        """
        # COLD START GUARD: Return FLEX with 0% confidence if no learned thresholds
        if self.threshold_store.is_cold_start():
            logger.warning(
                "Cold start: Cannot classify role without learned thresholds. "
                "Returning FLEX with 0% confidence."
            )
            return PlayerRole.FLEX, 0.0, ROLE_PROFILES[PlayerRole.FLEX]

        # Calculate role affinity scores (heuristic)
        scores = self._calculate_role_scores(player_stats)
        heuristic_role = max(scores, key=scores.get)
        heuristic_confidence = scores[heuristic_role]

        # Neural secondary opinion (consensus)
        neural_result = self._neural_classify(player_stats)
        if neural_result is not None:
            neural_role, neural_confidence = neural_result
            best_role, confidence = self._consensus(
                heuristic_role,
                heuristic_confidence,
                neural_role,
                neural_confidence,
            )
        else:
            best_role = heuristic_role
            confidence = heuristic_confidence

        profile = ROLE_PROFILES.get(best_role, ROLE_PROFILES[PlayerRole.FLEX])
        logger.info(
            "Classified role: %s (confidence: %s)", best_role.value, format(confidence, ".2f")
        )
        return best_role, confidence, profile

    def _calculate_role_scores(self, stats: Dict[str, float]) -> Dict[PlayerRole, float]:
        """Calculate affinity score for each role."""
        scores = {}

        # AWPer score
        awp_ratio = stats.get("awp_kills", 0) / max(stats.get("total_kills", 1), 1)
        scores[PlayerRole.AWPER] = self._score_awper(awp_ratio, stats)

        # Entry Fragger score
        entry_rate = stats.get("entry_frags", 0) / max(stats.get("rounds_played", 1), 1)
        scores[PlayerRole.ENTRY] = self._score_entry(entry_rate, stats)

        # Support score
        assist_rate = stats.get("assists", 0) / max(stats.get("rounds_played", 1), 1)
        scores[PlayerRole.SUPPORT] = self._score_support(assist_rate, stats)

        # IGL score
        survival_rate = stats.get("rounds_survived", 0) / max(stats.get("rounds_played", 1), 1)
        scores[PlayerRole.IGL] = self._score_igl(survival_rate, stats)

        # Lurker score
        solo_kills = stats.get("solo_kills", 0) / max(stats.get("total_kills", 1), 1)
        scores[PlayerRole.LURKER] = self._score_lurker(solo_kills, stats)

        # Normalize scores
        total = sum(scores.values())
        if total > 0:
            scores = {role: score / total for role, score in scores.items()}

        return scores

    def _score_awper(self, awp_ratio: float, stats: Dict) -> float:
        """Score AWPer affinity."""
        threshold = self.threshold_store.get_threshold("awp_kill_ratio")
        if threshold is not None and awp_ratio > threshold:
            # 0.8 base = strong AWPer signal; 0.5 scaling = moderate reward for exceeding threshold
            return 0.8 + (awp_ratio - threshold) * 0.5
        # 1.5x linear = AWP ratio is a strong direct indicator of role
        return awp_ratio * 1.5

    def _score_entry(self, entry_rate: float, stats: Dict) -> float:
        """Score Entry Fragger affinity."""
        threshold = self.threshold_store.get_threshold("entry_rate")
        if threshold is not None and entry_rate > threshold:
            # 0.7 base + 0.8 scaling = entry rate above pro threshold is strong signal
            base = 0.7 + (entry_rate - threshold) * 0.8
        else:
            # 2.5x linear = entry rate is the strongest direct indicator for this role
            base = entry_rate * 2.5

        # Bonus for first deaths (entry fraggers die first often)
        first_deaths = stats.get("first_deaths", 0) / max(stats.get("rounds_played", 1), 1)
        # 0.3 weight = secondary signal, not dominant
        return base + first_deaths * 0.3

    def _score_support(self, assist_rate: float, stats: Dict) -> float:
        """Score Support affinity."""
        threshold = self.threshold_store.get_threshold("assist_rate")
        if threshold is not None and assist_rate > threshold:
            # 0.7 base + 0.6 scaling = support signal from assist rate above threshold
            base = 0.7 + (assist_rate - threshold) * 0.6
        else:
            # 2.0x linear = assists are a strong but not sole indicator
            base = assist_rate * 2.0

        # Bonus for utility damage (normalized to ~50 dmg avg)
        utility_damage = stats.get("utility_damage_avg", 0) / 50
        # 0.2 weight, capped at 0.3 = supplementary signal, prevents domination
        return base + min(utility_damage * 0.2, 0.3)

    def _score_igl(self, survival_rate: float, stats: Dict) -> float:
        """Score IGL affinity."""
        threshold = self.threshold_store.get_threshold("survival_rate")
        if threshold is not None and survival_rate > threshold:
            # 0.6 base + 0.5 scaling = IGLs survive more but it's a weaker signal than other roles
            base = 0.6 + (survival_rate - threshold) * 0.5
        else:
            # 0.8x linear = survival alone is a weak IGL indicator
            base = survival_rate * 0.8

        # IGL typically has balanced K/D (0.9-1.2 range = trade-oriented play)
        kd = stats.get("kd_ratio", 1.0)
        balance_bonus = 0.2 if 0.9 < kd < 1.2 else 0

        return base + balance_bonus

    def _score_lurker(self, solo_kills: float, stats: Dict) -> float:
        """Score Lurker affinity."""
        threshold = self.threshold_store.get_threshold("solo_kill_rate")
        if threshold is not None and solo_kills > threshold:
            # 0.7 base + 0.8 scaling = lurkers defined by solo kill rate above threshold
            return 0.7 + (solo_kills - threshold) * 0.8
        # 2.5x linear = solo kills are the strongest direct indicator for lurker role
        return solo_kills * 2.5

    # ------------------------------------------------------------------
    # Neural secondary opinion (Proposal 10)
    # ------------------------------------------------------------------

    def _neural_classify(
        self, player_stats: Dict[str, float]
    ) -> Optional[Tuple[PlayerRole, float]]:
        """Run neural role prediction. Returns (role, confidence) or None."""
        try:
            import torch

            from Programma_CS2_RENAN.backend.nn.role_head import (
                FLEX_CONFIDENCE_THRESHOLD,
                ROLE_OUTPUT_ORDER,
                extract_role_features_from_stats,
                load_role_head,
            )

            result = load_role_head()
            if result is None:
                return None

            model, norm_stats = result
            features = extract_role_features_from_stats(player_stats)
            if features is None:
                return None

            # Normalize using training statistics
            mean_t = torch.tensor(norm_stats["mean"], dtype=torch.float32)
            std_t = torch.tensor(norm_stats["std"], dtype=torch.float32)
            features = (features - mean_t) / (std_t + 1e-8)

            with torch.no_grad():
                probs = model(features.unsqueeze(0)).squeeze(0)  # (5,)

            # R-03: Validate output shape before extracting role
            if probs.dim() != 1 or probs.shape[0] != len(ROLE_OUTPUT_ORDER):
                logger.error(
                    "R-03: Neural classifier output shape mismatch: expected (%d,), got %s",
                    len(ROLE_OUTPUT_ORDER), tuple(probs.shape),
                )
                return None

            max_prob, max_idx = probs.max(dim=0)
            confidence = max_prob.item()

            if confidence < FLEX_CONFIDENCE_THRESHOLD:
                return PlayerRole.FLEX, confidence

            return ROLE_OUTPUT_ORDER[max_idx.item()], confidence

        except Exception as e:
            logger.debug("Neural role classification unavailable: %s", e)
            return None

    # R-01: Named constants for consensus thresholds (previously hardcoded 0.1).
    # CONSENSUS_BOOST: confidence bonus when both classifiers agree.
    # NEURAL_MARGIN: minimum confidence margin for neural to override heuristic.
    _CONSENSUS_BOOST = 0.1
    _NEURAL_MARGIN = 0.1

    @staticmethod
    def _consensus(
        heuristic_role: PlayerRole,
        heuristic_conf: float,
        neural_role: PlayerRole,
        neural_conf: float,
    ) -> Tuple[PlayerRole, float]:
        """Consensus between heuristic and neural classifiers.

        Rules:
            1. Both agree → boosted confidence (avg + _CONSENSUS_BOOST, capped at 1.0)
            2. Disagree, neural has >_NEURAL_MARGIN → neural wins
            3. Otherwise → heuristic wins (established system, breaks ties)
        """
        boost = RoleClassifier._CONSENSUS_BOOST
        margin = RoleClassifier._NEURAL_MARGIN

        if heuristic_role == neural_role:
            combined = min((heuristic_conf + neural_conf) / 2 + boost, 1.0)
            logger.debug("Consensus AGREE: %s (conf=%.2f)", heuristic_role.value, combined)
            return heuristic_role, combined

        if neural_conf > heuristic_conf + margin:
            logger.debug(
                "Consensus NEURAL: %s (%.2f) over heuristic %s (%.2f)",
                neural_role.value,
                neural_conf,
                heuristic_role.value,
                heuristic_conf,
            )
            return neural_role, neural_conf

        logger.debug(
            "Consensus HEURISTIC: %s (%.2f) over neural %s (%.2f)",
            heuristic_role.value,
            heuristic_conf,
            neural_role.value,
            neural_conf,
        )
        return heuristic_role, heuristic_conf

    def get_role_coaching(self, role: PlayerRole, map_name: Optional[str] = None) -> List[str]:
        """
        Get role-specific coaching tips from Knowledge Base (RAG).

        Retrieves contextual advice for the detected role using semantic search.
        Falls back to generic tips from _FALLBACK_TIPS when RAG is unavailable.
        """
        _ROLE_QUERIES = {
            PlayerRole.AWPER: "AWP positioning angles peek timing sniper discipline",
            PlayerRole.ENTRY: "entry fragging site take first contact aggression trade",
            PlayerRole.SUPPORT: "support utility flash smoke trade teammate crossfire",
            PlayerRole.IGL: "round calling economy management strategy rotation leadership",
            PlayerRole.LURKER: "lurking timing rotation catching flanking map control",
            PlayerRole.FLEX: "versatility adaptation role filling team balance",
        }

        try:
            from Programma_CS2_RENAN.backend.knowledge.rag_knowledge import KnowledgeRetriever

            retriever = KnowledgeRetriever()

            query = _ROLE_QUERIES.get(role, "general improvement")
            knowledge = retriever.retrieve(query, top_k=3, map_name=map_name)

            tips = [k.description for k in knowledge if k.description]
            if tips:
                logger.debug("Retrieved %s coaching tips for %s", len(tips), role.value)
                return tips
            return list(_FALLBACK_TIPS.get(role, []))

        except Exception as e:
            logger.warning("RAG coaching retrieval failed for %s: %s", role.value, e)
            return list(_FALLBACK_TIPS.get(role, []))

    def classify_team(
        self, team_stats: List[Dict[str, float]]
    ) -> Dict[str, Tuple[PlayerRole, float]]:
        """
        Classify roles for entire team.

        Ensures balanced team composition (no duplicate AWPers).
        """
        results = {}
        assigned_roles = set()

        # Sort players by total impact (prefer assigning high-impact players first)
        sorted_players = sorted(
            enumerate(team_stats), key=lambda x: x[1].get("impact_rating", 0), reverse=True
        )

        # First pass: Assign preferred roles if available
        for idx, stats in sorted_players:
            player_name = stats.get("name", f"Player {idx+1}")
            role, confidence, _ = self.classify(stats)

            # Constraint: Max 1 AWPer per team
            if role == PlayerRole.AWPER and PlayerRole.AWPER in assigned_roles:
                # Fallback to logical second choice (usually Support or Flex)
                # For now, just assign Flex if AWP is taken
                role = PlayerRole.FLEX
                confidence = 0.5

            assigned_roles.add(role)
            results[player_name] = (role, confidence)

        return results

    # ==========================================================================
    # TASK 2.6.1: Team Balance Audit
    # Detects structural weaknesses in team composition
    # ==========================================================================
    def audit_team_balance(
        self, team_roles: Dict[str, Tuple[PlayerRole, float]]
    ) -> List[Dict[str, str]]:
        """
        Audit team composition for structural weaknesses.

        Args:
            team_roles: Output from classify_team() - player name -> (role, confidence)

        Returns:
            List of structural weakness insights with severity and recommendations
        """
        issues = []

        # Count role occurrences
        role_counts = {}
        for player_name, (role, confidence) in team_roles.items():
            role_counts[role] = role_counts.get(role, 0) + 1

        # Check for multiple AWPers (max 1 recommended)
        awper_count = role_counts.get(PlayerRole.AWPER, 0)
        if awper_count > 1:
            issues.append(
                {
                    "type": "STRUCTURAL_WEAKNESS",
                    "severity": "HIGH",
                    "title": "Multiple AWPers Detected",
                    "message": f"Team has {awper_count} AWPers. Most pro teams run 1 AWPer max. "
                    f"Consider having {awper_count - 1} player(s) switch to rifle roles.",
                    "recommendation": "Designate one primary AWPer. Secondary AWPer should rifle on eco rounds.",
                }
            )

        # Check for missing Entry Fragger (at least 1 needed)
        entry_count = role_counts.get(PlayerRole.ENTRY, 0)
        if entry_count == 0:
            issues.append(
                {
                    "type": "STRUCTURAL_WEAKNESS",
                    "severity": "HIGH",
                    "title": "No Entry Fragger",
                    "message": "Team lacks a dedicated Entry Fragger. Site takes will be chaotic "
                    "without someone creating space.",
                    "recommendation": "Designate an aggressive player to lead site entries with flash support.",
                }
            )

        # Check for missing Support (at least 1 needed)
        support_count = role_counts.get(PlayerRole.SUPPORT, 0)
        if support_count == 0:
            issues.append(
                {
                    "type": "STRUCTURAL_WEAKNESS",
                    "severity": "MEDIUM",
                    "title": "No Support Player",
                    "message": "Team lacks dedicated Support. Entry fraggers won't have flash/smoke backup.",
                    "recommendation": "Assign a player to focus on trading and utility for teammates.",
                }
            )

        # Check for all same role (lack of diversity)
        if len(role_counts) == 1 and len(team_roles) > 1:
            only_role = list(role_counts.keys())[0]
            issues.append(
                {
                    "type": "STRUCTURAL_WEAKNESS",
                    "severity": "CRITICAL",
                    "title": "No Role Diversity",
                    "message": f"All {len(team_roles)} players classified as {only_role.value}. "
                    f"This indicates either data issues or extreme playstyle imbalance.",
                    "recommendation": "Review player statistics for accuracy. Encourage role specialization.",
                }
            )

        # Check for too many Lurkers (max 1 recommended)
        lurker_count = role_counts.get(PlayerRole.LURKER, 0)
        if lurker_count > 1:
            issues.append(
                {
                    "type": "STRUCTURAL_WEAKNESS",
                    "severity": "MEDIUM",
                    "title": "Multiple Lurkers Detected",
                    "message": f"Team has {lurker_count} Lurkers. This weakens site executes "
                    "and leaves the main pack vulnerable.",
                    "recommendation": "Limit to one dedicated lurker. Others should group for site hits.",
                }
            )

        # Check for no IGL (0 needed - wait, 1 needed)
        # Note: IGL is hard to detect from stats alone, but if we have high confidence on someone, good.
        # We won't flag missing IGL as critical because stats don't always show leadership.

        if issues:
            logger.warning("Team Balance Audit: Found %s structural weakness(es)", len(issues))
        else:
            logger.info("Team Balance Audit: Team composition is balanced")

        return issues


def get_role_classifier() -> RoleClassifier:
    """Factory function for role classifier."""
    return RoleClassifier()
