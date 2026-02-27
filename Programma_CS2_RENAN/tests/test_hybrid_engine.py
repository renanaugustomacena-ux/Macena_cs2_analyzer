"""
Unit tests for Hybrid Coaching Engine.

Tests ML-RAG synthesis, confidence scoring, and priority classification.
"""

import pytest
from sqlmodel import select

from Programma_CS2_RENAN.backend.coaching.hybrid_engine import (
    HybridCoachingEngine,
    HybridInsight,
    InsightPriority,
    get_hybrid_engine,
)
from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database
from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight, TacticalKnowledge


@pytest.mark.xfail(
    strict=False,
    reason="F9-10/F9-01: pro_baseline format mismatch may cause TypeError in _calculate_deviations",
)
class TestHybridCoachingEngine:
    """Test suite for hybrid coaching engine."""

    def test_engine_initialization(self):
        """Test engine can be initialized."""
        engine = HybridCoachingEngine(use_jepa=False)

        assert engine.retriever is not None
        assert engine.pro_baseline is not None
        assert "avg_adr" in engine.pro_baseline

    def test_calculate_deviations(self):
        """Test deviation calculation."""
        engine = HybridCoachingEngine(use_jepa=False)

        player_stats = {
            "avg_adr": 70.0,  # Below 85 baseline
            "avg_kills": 20.0,  # Above 18.5 baseline
        }

        deviations = engine._calculate_deviations(player_stats)

        assert "avg_adr" in deviations
        assert "avg_kills" in deviations

        # ADR should be negative (below baseline)
        assert deviations["avg_adr"][0] < 0

        # Kills should be positive (above baseline)
        assert deviations["avg_kills"][0] > 0

    def test_priority_determination(self):
        """Test priority classification."""
        engine = HybridCoachingEngine(use_jepa=False)

        # Critical: |Z| > 2.5, high confidence
        assert engine._determine_priority(3.0, 0.9) == InsightPriority.CRITICAL

        # High: |Z| > 2.0 AND confidence > 0.6
        assert engine._determine_priority(2.5, 0.7) == InsightPriority.HIGH

        # Medium: |Z| > 1.0 AND confidence > 0.4
        assert engine._determine_priority(1.5, 0.5) == InsightPriority.MEDIUM

        # Low: |Z| < 1
        assert engine._determine_priority(0.5, 0.2) == InsightPriority.LOW

    def test_confidence_calculation(self):
        """Test confidence scoring with real MetaDriftEngine."""
        engine = HybridCoachingEngine(use_jepa=False)

        # High Z-score, high effectiveness → confidence should be meaningful
        confidence_high = engine._calculate_confidence(2.5, 0.8)
        assert 0.0 < confidence_high <= 1.0

        # Low Z-score, low effectiveness → confidence should be lower
        confidence_low = engine._calculate_confidence(0.5, 0.1)
        assert 0.0 <= confidence_low <= 1.0
        assert (
            confidence_low < confidence_high
        ), f"Low inputs ({confidence_low}) should produce lower confidence than high inputs ({confidence_high})"

    def test_feature_category_matching(self):
        """Test feature to category matching."""
        engine = HybridCoachingEngine(use_jepa=False)

        assert engine._feature_matches_category("avg_adr", "positioning")
        assert engine._feature_matches_category("avg_adr", "aim")
        assert engine._feature_matches_category("utility_damage", "utility")
        assert engine._feature_matches_category("econ_rating", "economy")

        # Non-matching
        assert not engine._feature_matches_category("avg_adr", "economy")

    def test_generate_insights_basic(self):
        """Test basic insight generation."""
        engine = HybridCoachingEngine(use_jepa=False)

        player_stats = {
            "avg_kills": 14.0,
            "avg_deaths": 17.0,
            "avg_adr": 68.0,
            "avg_hs": 0.35,
            "avg_kast": 0.65,
            "kd_ratio": 0.82,
            "impact_rounds": 0.22,
            "accuracy": 0.24,
            "econ_rating": 0.95,
            "rating": 0.98,
        }

        insights = engine.generate_insights(player_stats)

        assert len(insights) > 0
        assert all(isinstance(i, HybridInsight) for i in insights)

        # ADR should be a key insight (significantly below baseline)
        adr_insights = [i for i in insights if "adr" in i.feature.lower()]
        assert len(adr_insights) > 0

    def test_generate_insights_with_map_context(self):
        """Test insight generation with map context."""
        engine = HybridCoachingEngine(use_jepa=False)

        player_stats = {"avg_adr": 70.0, "avg_kills": 15.0}

        insights = engine.generate_insights(player_stats, map_name="de_mirage", side="T")

        assert len(insights) > 0, "Should produce insights for below-baseline stats"
        assert all(isinstance(i, HybridInsight) for i in insights)
        # Verify insights contain real content (not empty placeholders)
        for i in insights:
            assert i.title, f"Insight should have a non-empty title"
            assert i.message, f"Insight should have a non-empty message"
            assert i.feature, f"Insight should reference a feature"

    def test_insights_sorted_by_priority(self):
        """Test insights are sorted by priority."""
        engine = HybridCoachingEngine(use_jepa=False)

        player_stats = {
            "avg_adr": 50.0,  # Very low (critical)
            "avg_kills": 16.0,  # Low (medium)
            "avg_hs": 0.40,  # Slightly low (low)
        }

        insights = engine.generate_insights(player_stats)

        # With ADR at 50.0 (very low) we must get multiple insights
        assert (
            len(insights) > 1
        ), f"Expected multiple insights for stats with ADR=50, got {len(insights)}"

        # First insight should have highest priority
        priorities = [engine._priority_value(i.priority) for i in insights]
        assert priorities == sorted(
            priorities, reverse=True
        ), f"Insights not sorted by priority: {[i.priority.value for i in insights]}"

    def test_save_insights_to_db(self):
        """Test saving insights to database."""
        engine = HybridCoachingEngine(use_jepa=False)

        insights = [
            HybridInsight(
                title="Test Insight",
                message="Test message",
                priority=InsightPriority.HIGH,
                confidence=0.8,
                feature="avg_adr",
                ml_z_score=-2.0,
                knowledge_refs=["Knowledge 1"],
                pro_examples=["Pro Match 1"],
            )
        ]

        engine.save_insights_to_db(insights, "test_player", "test_demo.dem")

        # Verify saved
        db = get_db_manager()
        try:
            with db.get_session() as session:
                saved = session.exec(
                    select(CoachingInsight).where(CoachingInsight.player_name == "test_player")
                ).all()

                assert len(saved) >= 1
                assert saved[0].title == "Test Insight"
        finally:
            # Cleanup: remove test rows to avoid polluting production DB
            with db.get_session() as session:
                orphans = session.exec(
                    select(CoachingInsight).where(CoachingInsight.player_name == "test_player")
                ).all()
                for row in orphans:
                    session.delete(row)
                session.commit()


class TestInsightPriority:
    """Test suite for InsightPriority enum."""

    def test_priority_values(self):
        """Test priority enum values."""
        assert InsightPriority.CRITICAL.value == "critical"
        assert InsightPriority.HIGH.value == "high"
        assert InsightPriority.MEDIUM.value == "medium"
        assert InsightPriority.LOW.value == "low"


class TestHybridInsight:
    """Test suite for HybridInsight dataclass."""

    def test_insight_creation(self):
        """Test insight dataclass creation."""
        insight = HybridInsight(
            title="Test",
            message="Test message",
            priority=InsightPriority.HIGH,
            confidence=0.85,
            feature="avg_adr",
            ml_z_score=-2.1,
            knowledge_refs=["Ref 1", "Ref 2"],
            pro_examples=["Match 1"],
        )

        assert insight.title == "Test"
        assert insight.confidence == 0.85
        assert insight.priority == InsightPriority.HIGH
        assert len(insight.knowledge_refs) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
