"""
Hybrid Coaching Engine

Synthesizes ML model predictions with RAG knowledge retrieval
for unified, contextual coaching insights.

Architecture:
    1. ML Model → Deviation predictions (Z-scores)
    2. RAG Retriever → Relevant tactical knowledge
    3. Synthesizer → Unified insights with confidence scoring

From Phase 1B Roadmap:
    - Eliminates duplicate/conflicting advice
    - Adds confidence scoring (ML + knowledge effectiveness)
    - Context-aware retrieval (map, side, round type)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

from Programma_CS2_RENAN.backend.knowledge.rag_knowledge import KnowledgeRetriever
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight, TacticalKnowledge
from Programma_CS2_RENAN.core.config import get_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.hybrid_coaching")


class InsightPriority(Enum):
    """Priority levels for coaching insights."""

    CRITICAL = "critical"  # |Z| > 2.5, confidence > 0.8
    HIGH = "high"  # |Z| > 2.0, confidence > 0.6
    MEDIUM = "medium"  # |Z| > 1.0, confidence > 0.4
    LOW = "low"  # |Z| < 1.0 or low confidence


@dataclass
class HybridInsight:
    """
    Unified insight combining ML and RAG.

    Attributes:
        title: Insight title
        message: Detailed coaching message
        priority: Priority level (CRITICAL/HIGH/MEDIUM/LOW)
        confidence: Combined confidence score (0-1)
        feature: Feature being addressed
        ml_z_score: ML-derived Z-score
        knowledge_refs: Referenced knowledge entries
        pro_examples: Pro match examples
        tick_range: TASK 2.7.1 - Tuple of (start_tick, end_tick) for Reference Clip
        demo_name: TASK 2.7.1 - Demo file name for clip reference
    """

    title: str
    message: str
    priority: InsightPriority
    confidence: float
    feature: str
    ml_z_score: float
    knowledge_refs: List[str]
    pro_examples: List[str]
    # TASK 2.7.1: Reference Clip Index - allows UI to jump directly to evidence
    tick_range: Optional[Tuple[int, int]] = None  # (start_tick, end_tick)
    demo_name: Optional[str] = None  # Demo file for reference


class HybridCoachingEngine:
    """
    Combines ML predictions with RAG knowledge for unified coaching.

    Pipeline:
        1. ML model predicts deviations from pro baseline
        2. RAG retrieves relevant tactical knowledge
        3. Synthesize into unified insights
        4. Score confidence and prioritize

    Eliminates:
        - Duplicate insights
        - Conflicting advice
        - Generic recommendations
    """

    def __init__(self, use_jepa: bool = None):
        """
        Initialize hybrid engine.

        Args:
            use_jepa: Use JEPA model (True) or AdvancedCoachNN (False).
                     If None, uses config setting.
        """
        # DB must be initialized at app startup before instantiating this class (F4-04).
        # Calling init_database() here was a constructor side-effect that violated
        # single-responsibility and made unit testing require live DB infrastructure.
        self.db = get_db_manager()
        self.retriever = KnowledgeRetriever()

        # Model selection
        if use_jepa is None:
            use_jepa = get_setting("USE_JEPA_MODEL", default=False)

        self.use_jepa = use_jepa
        self.model = self._load_model()

        # Pro baseline for deviation calculation.
        # _using_fallback_baseline is set True when get_pro_baseline() fails (F4-02).
        self._using_fallback_baseline: bool = False
        self.pro_baseline = self._load_pro_baseline()

    def _load_model(self):
        """Load ML model (JEPA or AdvancedCoachNN).

        Uses METADATA_DIM from vectorizer.py to ensure dimension consistency.
        """
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

        try:
            if self.use_jepa:
                from Programma_CS2_RENAN.backend.nn.jepa_model import JEPACoachingModel

                model = JEPACoachingModel(input_dim=METADATA_DIM, output_dim=METADATA_DIM)
                logger.info("Loaded JEPA model for hybrid coaching (dim=%s)", METADATA_DIM)
            else:
                from Programma_CS2_RENAN.backend.nn.model import AdvancedCoachNN

                model = AdvancedCoachNN(input_dim=METADATA_DIM, output_dim=METADATA_DIM)
                logger.info("Loaded AdvancedCoachNN for hybrid coaching (dim=%s)", METADATA_DIM)
            return model
        except Exception as e:
            logger.error("Failed to load ML model: %s", e)
            return None

    def _load_pro_baseline(self) -> Dict[str, float]:
        """Load pro baseline statistics from centralized source.

        Uses the unified pro_baseline module to ensure consistency between
        training (coach_manager) and inference (hybrid_engine).
        """
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import get_pro_baseline

        try:
            baseline_data = get_pro_baseline()
            # Return full nested structure {feature: {"mean": x, "std": y}}
            # so that calculate_deviations() can compute proper Z-scores
            return baseline_data
        except Exception as e:
            logger.error(
                "Failed to load dynamic baseline: %s. "
                "Using HARDCODED fallback — coaching quality is DEGRADED.",
                e,
            )
            # Fallback only if module fails completely.
            # WARNING: These values are stale approximations, not from real data.
            # _using_fallback_baseline=True causes insights to be tagged with
            # baseline_quality="degraded" so callers can display a warning (F4-02).
            self._using_fallback_baseline = True
            return {
                "avg_kills": 0.78,
                "avg_deaths": 0.62,
                "avg_adr": 82.0,
                "avg_hs": 0.52,
                "avg_kast": 0.74,
                "kd_ratio": 1.20,
                "impact_rounds": 0.35,
                "accuracy": 0.22,
                "econ_rating": 1.05,
                "rating": 1.15,
                "utility_damage": 45.0,
                "entry_rate": 0.25,
            }

    def generate_insights(
        self,
        player_stats: Dict[str, float],
        map_name: Optional[str] = None,
        side: Optional[str] = None,  # "T" or "CT"
        round_type: Optional[str] = None,  # "pistol", "eco", "full-buy"
        pro_reference_id: Optional[int] = None,  # Reference a specific Pro Player HLTV ID
        demo_name: Optional[str] = None,  # TASK 2.7.1: Demo file for Reference Clip
        tick_data: Optional[
            Dict[str, Tuple[int, int]]
        ] = None,  # TASK 2.7.1: feature -> (start, end) tick
    ) -> List[HybridInsight]:
        """
        Generate hybrid coaching insights.

        Args:
            player_stats: Player statistics dictionary
            map_name: Optional map context (e.g., "de_mirage")
            side: Optional side context ("T" or "CT")
            round_type: Optional round type context
            pro_reference_id: Optional Pro HLTV ID to use as baseline
            demo_name: TASK 2.7.1 - Demo file name for Reference Clip feature
            tick_data: TASK 2.7.1 - Dict mapping feature names to (start_tick, end_tick) tuples

        Returns:
            List of HybridInsight objects, sorted by priority
        """
        logger.info(
            "Generating hybrid insights (map=%s, side=%s, pro_id=%s)",
            map_name,
            side,
            pro_reference_id,
        )

        # Step 0: Resolve Contextual Pro Baseline
        active_baseline = self.pro_baseline
        if pro_reference_id:
            active_baseline = self._get_contextual_pro_baseline(pro_reference_id)

        # Step 1: Calculate deviations from the active baseline
        deviations = self._calculate_deviations(player_stats, active_baseline)

        # Step 2: Get ML predictions (if model available)
        ml_predictions = self._get_ml_predictions(player_stats)

        # Step 3: Retrieve relevant knowledge
        knowledge = self._retrieve_contextual_knowledge(deviations, map_name, side, round_type)

        # Step 4: Synthesize insights (TASK 2.7.1: pass demo_name and tick_data for Reference Clip)
        insights = self._synthesize_insights(
            deviations,
            ml_predictions,
            knowledge,
            map_name,
            active_baseline,
            demo_name=demo_name,
            tick_data=tick_data or {},
        )

        # Step 4b: Tag insights when the baseline is a stale hardcoded fallback (F4-02).
        # Downstream callers (UI, CoachingService) can surface a "degraded baseline"
        # warning instead of silently serving lower-quality advice.
        if self._using_fallback_baseline:
            for ins in insights:
                ins.message = (
                    ins.message
                    + " [AVISO: baseline_quality=degraded — usando valores estáticos; "
                    "precisão do coaching reduzida.]"
                )

        # Step 5: Sort by priority and confidence
        insights.sort(key=lambda x: (-self._priority_value(x.priority), -x.confidence))

        logger.info("Generated %s hybrid insights", len(insights))
        return insights

    def _get_contextual_pro_baseline(self, pro_id: int) -> Dict[str, float]:
        """Fetches and assimilates a specific Pro Player Card as a baseline."""
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.coaching.pro_bridge import get_pro_baseline_for_coach
        from Programma_CS2_RENAN.backend.storage.db_models import ProPlayerStatCard

        try:
            with self.db.get_session() as session:
                card = session.exec(
                    select(ProPlayerStatCard).where(ProPlayerStatCard.player_id == pro_id)
                ).first()

                if card:
                    logger.info("Using contextual baseline from Pro Card (ID: %s)", pro_id)
                    return get_pro_baseline_for_coach(card)
        except Exception as e:
            logger.error("Failed to fetch pro card %s: %s", pro_id, e)

        return self.pro_baseline  # Fallback

    def _calculate_deviations(
        self, player_stats: Dict[str, float], baseline_override: Optional[Dict[str, float]] = None
    ) -> Dict[str, Tuple[float, float]]:
        """
        Calculate Z-score deviations from pro baseline.

        Uses dynamic standard deviations from the centralized pro_baseline module
        instead of hardcoded estimates, ensuring scientific validity.

        Returns:
            Dict mapping feature to (z_score, raw_deviation)
        """
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            calculate_deviations,
        )

        target_baseline = baseline_override or self.pro_baseline
        # Delegate to centralized math logic
        return calculate_deviations(player_stats, target_baseline)

    def _get_ml_predictions(self, player_stats: Dict[str, float]) -> Optional[Dict[str, float]]:
        """Get ML model predictions."""
        if self.model is None:
            return None

        try:
            from Programma_CS2_RENAN.backend.nn.coach_manager import MATCH_AGGREGATE_FEATURES

            # All 25 match-aggregate features — no zero-padding needed
            features = [player_stats.get(f, 0.0) for f in MATCH_AGGREGATE_FEATURES]

            x = torch.FloatTensor(features).unsqueeze(0).unsqueeze(0)

            with torch.no_grad():
                if self.use_jepa:
                    output = self.model.forward_coaching(x)
                else:
                    output = self.model(x)

            # Map output to predictions
            predictions = {
                "recommended_kills": output[0, 0].item(),
                "recommended_adr": output[0, 2].item() if output.shape[1] > 2 else 0,
                "recommended_hs": output[0, 3].item() if output.shape[1] > 3 else 0,
            }

            return predictions

        except Exception as e:
            logger.error("ML prediction failed: %s", e)
            return None

    def _retrieve_contextual_knowledge(
        self,
        deviations: Dict[str, Tuple[float, float]],
        map_name: Optional[str],
        side: Optional[str],
        round_type: Optional[str],
    ) -> List[TacticalKnowledge]:
        """
        Retrieve knowledge with full context.

        Uses deviation features to build semantic query.
        """
        # Build query from significant deviations
        query_parts = []

        significant_features = [
            (feature, z, raw) for feature, (z, raw) in deviations.items() if abs(z) > 1.0
        ]

        for feature, z_score, _ in sorted(significant_features, key=lambda x: -abs(x[1])):
            if z_score < 0:
                query_parts.append(f"low {feature.replace('avg_', '')}")
            else:
                query_parts.append(f"high {feature.replace('avg_', '')}")

        # Add context
        if side:
            query_parts.append(f"{side}-side")
        if round_type:
            query_parts.append(round_type)

        query = " ".join(query_parts) if query_parts else "general improvement"

        # Retrieve knowledge
        knowledge = self.retriever.retrieve(query, top_k=5, map_name=map_name)

        # Filter by side if specified
        if side:
            knowledge = [k for k in knowledge if not k.situation or side in k.situation]

        return knowledge

    def _synthesize_insights(
        self,
        deviations: Dict[str, Tuple[float, float]],
        ml_predictions: Optional[Dict[str, float]],
        knowledge: List[TacticalKnowledge],
        map_name: Optional[str],
        active_baseline: Dict[str, float],
        demo_name: Optional[str] = None,  # TASK 2.7.1: Demo name for Reference Clip
        tick_data: Optional[Dict[str, Tuple[int, int]]] = None,  # TASK 2.7.1: feature -> tick range
    ) -> List[HybridInsight]:
        """
        Synthesize ML and RAG into unified insights.

        Strategy:
        - High-confidence ML (|Z| > 2): Lead with ML, support with RAG
        - Low-confidence ML (|Z| < 1): Lead with RAG
        - Medium: Balanced approach

        TASK 2.7.1: Now includes Reference Clip information via demo_name and tick_data.
        """
        insights = []
        used_features = set()
        tick_data = tick_data or {}

        # Process significant deviations
        for feature, (z_score, raw_dev) in sorted(deviations.items(), key=lambda x: -abs(x[1][0])):
            if abs(z_score) < 0.5:
                continue  # Skip insignificant deviations

            # Find matching knowledge
            matching_knowledge = [
                k for k in knowledge if self._feature_matches_category(feature, k.category)
            ]

            # Calculate confidence
            USAGE_COUNT_NORMALIZER = 100
            knowledge_effectiveness = min(
                1.0,
                np.mean([k.usage_count for k in matching_knowledge]) / USAGE_COUNT_NORMALIZER
                if matching_knowledge
                else 0,
            )
            confidence = self._calculate_confidence(z_score, knowledge_effectiveness)

            # Determine priority
            priority = self._determine_priority(z_score, confidence)

            # TASK 2.7.1: Get tick range for this feature if available
            feature_tick_range = tick_data.get(feature)

            # Generate insight (TASK 2.7.1: pass tick_range and demo_name)
            insight = self._generate_insight(
                feature,
                z_score,
                raw_dev,
                matching_knowledge,
                ml_predictions,
                priority,
                confidence,
                map_name,
                active_baseline,
                tick_range=feature_tick_range,
                demo_name=demo_name,
            )

            insights.append(insight)
            used_features.add(feature)

        # Add knowledge-only insights for unused knowledge
        for k in knowledge[:3]:
            if not any(self._feature_matches_category(f, k.category) for f in used_features):
                insight = HybridInsight(
                    title=k.title,
                    message=k.description,  # Emoji stripped — presentation is UI concern
                    priority=InsightPriority.LOW,
                    confidence=0.4,
                    feature=k.category,
                    ml_z_score=0,
                    knowledge_refs=[k.title],
                    pro_examples=[k.pro_example] if k.pro_example else [],
                )
                insights.append(insight)

        return insights

    def _feature_matches_category(self, feature: str, category: str) -> bool:
        """Check if feature matches knowledge category."""
        mappings = {
            "avg_adr": ["positioning", "aim"],
            "avg_kills": ["positioning", "aim"],
            "avg_deaths": ["positioning"],
            "avg_hs": ["aim"],
            "utility_damage": ["utility"],
            "econ_rating": ["economy"],
            "impact_rounds": ["positioning"],
            "entry_rate": ["positioning"],
        }
        return category in mappings.get(feature, [])

    def _calculate_confidence(self, z_score: float, knowledge_effectiveness: float) -> float:
        """
        Calculate combined confidence score.

        Factors:
        - ML confidence: |Z-score| (higher = more confident)
        - Knowledge effectiveness: Usage count
        - NEW: Meta-Drift adjustment (Stability of pro baseline)
        """
        from Programma_CS2_RENAN.backend.processing.baselines.meta_drift import MetaDriftEngine

        Z_SCORE_CONFIDENCE_CAP = 3.0
        ml_confidence = min(abs(z_score) / Z_SCORE_CONFIDENCE_CAP, 1.0)

        # Weighted average (ML signal 60%, knowledge signal 40%)
        ML_WEIGHT = 0.6
        KNOWLEDGE_WEIGHT = 0.4
        base_confidence = ml_confidence * ML_WEIGHT + knowledge_effectiveness * KNOWLEDGE_WEIGHT

        # Apply Meta-Drift penalty
        meta_adj = MetaDriftEngine.get_meta_confidence_adjustment()

        return min(base_confidence * meta_adj, 1.0)

    def _determine_priority(self, z_score: float, confidence: float) -> InsightPriority:
        """Determine insight priority."""
        abs_z = abs(z_score)

        if abs_z > 2.5 and confidence > 0.8:
            return InsightPriority.CRITICAL
        elif abs_z > 2.0 and confidence > 0.6:
            return InsightPriority.HIGH
        elif abs_z > 1.0 and confidence > 0.4:
            return InsightPriority.MEDIUM
        else:
            return InsightPriority.LOW

    def _generate_insight(
        self,
        feature: str,
        z_score: float,
        raw_dev: float,
        knowledge: List[TacticalKnowledge],
        ml_predictions: Optional[Dict[str, float]],
        priority: InsightPriority,
        confidence: float,
        map_name: Optional[str],
        active_baseline: Dict[str, float],
        tick_range: Optional[Tuple[int, int]] = None,  # TASK 2.7.1: Reference Clip tick range
        demo_name: Optional[str] = None,  # TASK 2.7.1: Demo file name
    ) -> HybridInsight:
        """
        Generate a single hybrid insight.

        TASK 2.7.1: Now includes tick_range and demo_name for Reference Clip feature,
        allowing UI to jump directly to the evidence in the demo file.
        """
        feature_name = feature.replace("avg_", "").replace("_", " ").title()

        # Build title
        # Emoji stripped — presentation is UI concern
        if z_score < -1.5:
            title = f"Improve Your {feature_name}"
        elif z_score < 0:
            title = f"{feature_name} Below Average"
        else:
            title = f"Strong {feature_name}"

        # Build message
        message_parts = []

        # ML-derived insight
        baseline_entry = active_baseline.get(feature, 0)
        baseline = (
            baseline_entry["mean"] if isinstance(baseline_entry, dict) else float(baseline_entry)
        )
        if z_score < 0:
            message_parts.append(
                f"Your {feature_name.lower()} is below pro level "
                f"(Z-score: {z_score:.1f}). Target: {baseline:.1f}"
            )
        else:
            message_parts.append(
                f"Your {feature_name.lower()} exceeds pro average "
                f"(Z-score: +{z_score:.1f}). Keep it up!"
            )

        # Knowledge-derived insight
        if knowledge:
            best_knowledge = knowledge[0]
            message_parts.append(f"\nPro tip: {best_knowledge.description}")  # Emoji stripped — presentation is UI concern

        # Pro examples
        pro_examples = [k.pro_example for k in knowledge if k.pro_example]
        if pro_examples:
            message_parts.append(f"\nReference: {pro_examples[0]}")  # Emoji stripped — presentation is UI concern

        # TASK 2.7.1: Add Reference Clip info to message if available
        if tick_range and demo_name:
            message_parts.append(
                f"\nReference Clip: {demo_name} (ticks {tick_range[0]}-{tick_range[1]})"  # Emoji stripped — presentation is UI concern
            )

        return HybridInsight(
            title=title,
            message="\n".join(message_parts),
            priority=priority,
            confidence=confidence,
            feature=feature,
            ml_z_score=z_score,
            knowledge_refs=[k.title for k in knowledge],
            pro_examples=pro_examples,
            tick_range=tick_range,  # TASK 2.7.1
            demo_name=demo_name,  # TASK 2.7.1
        )

    def _priority_value(self, priority: InsightPriority) -> int:
        """Convert priority to numeric value for sorting."""
        return {
            InsightPriority.CRITICAL: 4,
            InsightPriority.HIGH: 3,
            InsightPriority.MEDIUM: 2,
            InsightPriority.LOW: 1,
        }.get(priority, 0)

    def save_insights_to_db(self, insights: List[HybridInsight], player_name: str, demo_name: str):
        """Save hybrid insights to database."""
        with self.db.get_session() as session:
            for insight in insights:
                db_insight = CoachingInsight(
                    player_name=player_name,
                    demo_name=demo_name,
                    title=insight.title,
                    severity=insight.priority.value.capitalize(),
                    message=insight.message,
                    focus_area=insight.feature,
                )
                session.add(db_insight)
            session.commit()

        logger.info("Saved %s insights for %s", len(insights), player_name)


def get_hybrid_engine() -> HybridCoachingEngine:
    """Factory function for hybrid engine."""
    return HybridCoachingEngine()


if __name__ == "__main__":
    # Self-test
    logger.info("=== Hybrid Coaching Engine Test ===")

    engine = HybridCoachingEngine()

    # NOTE: Synthetic values for self-test only — not representative of real match data.
    player_stats = {
        "avg_kills": 14.0,  # Below 18.5 baseline
        "avg_deaths": 17.0,  # Above 15.2 baseline
        "avg_adr": 68.0,  # Below 85 baseline
        "avg_hs": 0.35,  # Below 0.45 baseline
        "avg_kast": 0.65,
        "kd_ratio": 0.82,
        "impact_rounds": 0.22,
        "accuracy": 0.24,
        "econ_rating": 0.95,
        "rating": 0.98,
    }

    insights = engine.generate_insights(player_stats, map_name="de_mirage", side="T")

    logger.info("Generated %s insights:", len(insights))
    for i, insight in enumerate(insights, 1):
        logger.info("%s. [%s] %s", i, insight.priority.value.upper(), insight.title)
        logger.info("   Confidence: %.2f", insight.confidence)
        logger.info("   %s", insight.message[:100])
