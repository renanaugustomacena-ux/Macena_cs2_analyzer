"""
Tests for CoachingService — end-to-end coaching flows.

Complements test_coaching_service_contracts.py (mode selection, Bug #8 validation).
Covers: generate_new_insights flows, get_latest_insights, _format_coper_message,
traditional correction saving, longitudinal coaching, and fallback chains.

Uses in-memory SQLite with monkeypatched get_db_manager for CI portability.
"""

import sys


from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight, PlayerMatchStats


# ============ Fixtures ============


class _InMemoryDBManager:
    """Lightweight DB manager for tests."""

    def __init__(self, engine):
        self._engine = engine

    @contextmanager
    def get_session(self, engine_key: str = "default"):
        with Session(self._engine, expire_on_commit=False) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise


@pytest.fixture
def db_engine():
    """In-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def mock_db(db_engine):
    """In-memory DB manager."""
    return _InMemoryDBManager(db_engine)


@pytest.fixture
def coaching_service(mock_db):
    """CoachingService with in-memory DB and controlled settings."""
    with patch("Programma_CS2_RENAN.backend.services.coaching_service.get_db_manager", return_value=mock_db), \
         patch("Programma_CS2_RENAN.backend.services.coaching_service.get_setting") as mock_setting:

        def setting_side_effect(key, default=None):
            return {
                "USE_RAG_COACHING": False,
                "USE_HYBRID_COACHING": False,
                "USE_COPER_COACHING": False,
            }.get(key, default)

        mock_setting.side_effect = setting_side_effect
        from Programma_CS2_RENAN.backend.services.coaching_service import CoachingService

        svc = CoachingService()
    return svc


# ============ _format_coper_message ============


class TestFormatCoperMessage:
    """Test COPER message formatting."""

    def test_basic_narrative(self, coaching_service):
        """Simple narrative with no extras."""
        from Programma_CS2_RENAN.backend.knowledge.experience_bank import SynthesizedAdvice

        advice = SynthesizedAdvice(
            narrative="Focus on positioning at A-site.",
            pro_references=[],
            confidence=0.7,
            focus_area="positioning",
            experiences_used=5,
        )
        msg = coaching_service._format_coper_message(advice)
        assert "Focus on positioning at A-site." in msg
        assert "5 similar situations" in msg
        assert "70%" in msg

    def test_with_pro_references(self, coaching_service):
        """Pro references appear in message."""
        from Programma_CS2_RENAN.backend.knowledge.experience_bank import SynthesizedAdvice

        advice = SynthesizedAdvice(
            narrative="Try holding this angle.",
            pro_references=["s1mple (held_angle -> kill)", "NiKo (pushed -> kill)"],
            confidence=0.8,
            focus_area="aim",
            experiences_used=3,
        )
        msg = coaching_service._format_coper_message(advice)
        assert "Pro Examples:" in msg
        assert "s1mple" in msg
        assert "NiKo" in msg

    def test_with_baseline_note(self, coaching_service):
        """Baseline note is appended when provided."""
        from Programma_CS2_RENAN.backend.knowledge.experience_bank import SynthesizedAdvice

        advice = SynthesizedAdvice(
            narrative="Work on aim.",
            pro_references=[],
            confidence=0.6,
            focus_area="aim",
            experiences_used=2,
        )
        msg = coaching_service._format_coper_message(advice, baseline_note="Your HS is 15% below pro.")
        assert "Your HS is 15% below pro." in msg

    def test_zero_confidence_displayed(self, coaching_service):
        """Zero confidence is displayed correctly."""
        from Programma_CS2_RENAN.backend.knowledge.experience_bank import SynthesizedAdvice

        advice = SynthesizedAdvice(
            narrative="No data.",
            pro_references=[],
            confidence=0.0,
            focus_area="general",
            experiences_used=0,
        )
        msg = coaching_service._format_coper_message(advice)
        assert "0 similar situations" in msg
        assert "0%" in msg


# ============ Traditional Coaching Flow ============


class TestTraditionalCoachin:
    """Test traditional (non-COPER, non-Hybrid) coaching pipeline."""

    def test_generate_new_insights_traditional_saves_to_db(self, coaching_service, mock_db):
        """Traditional mode saves correction insights to DB."""
        with patch("Programma_CS2_RENAN.backend.services.coaching_service.generate_corrections") as mock_corr, \
             patch("Programma_CS2_RENAN.backend.services.coaching_service.get_ollama_writer") as mock_writer:

            mock_corr.return_value = [
                {"feature": "avg_adr", "weighted_z": -2.5},
                {"feature": "avg_kills", "weighted_z": -1.8},
            ]
            mock_writer.return_value.polish.side_effect = lambda **kw: kw.get("message", "polished")

            coaching_service.generate_new_insights(
                player_name="TestPlayer",
                demo_name="test.dem",
                deviations={"avg_adr": -15.0},
                rounds_played=20,
            )

            # Verify insights were saved
            with mock_db.get_session() as session:
                insights = session.exec(
                    select(CoachingInsight).where(CoachingInsight.player_name == "TestPlayer")
                ).all()
                assert len(insights) >= 2
                features = [i.focus_area for i in insights]
                assert "avg_adr" in features
                assert "avg_kills" in features

    def test_empty_deviations_empty_corrections(self, coaching_service, mock_db):
        """Empty deviations produce zero corrections."""
        with patch("Programma_CS2_RENAN.backend.services.coaching_service.generate_corrections") as mock_corr, \
             patch("Programma_CS2_RENAN.backend.services.coaching_service.get_ollama_writer") as mock_writer:

            mock_corr.return_value = []
            mock_writer.return_value.polish.return_value = "polished"

            coaching_service.generate_new_insights(
                player_name="TestPlayer",
                demo_name="test.dem",
                deviations={},
                rounds_played=0,
            )

            with mock_db.get_session() as session:
                insights = session.exec(
                    select(CoachingInsight).where(CoachingInsight.player_name == "TestPlayer")
                ).all()
                assert len(insights) == 0


# ============ COPER Fallback Chain ============


class TestCoperFallbackChain:
    """Test COPER → traditional fallback when COPER fails."""

    def test_coper_failure_falls_back_to_traditional(self, mock_db):
        """When COPER throws, fallback to traditional coaching."""
        with patch("Programma_CS2_RENAN.backend.services.coaching_service.get_db_manager", return_value=mock_db), \
             patch("Programma_CS2_RENAN.backend.services.coaching_service.get_setting") as mock_setting, \
             patch("Programma_CS2_RENAN.backend.services.coaching_service.generate_corrections") as mock_corr, \
             patch("Programma_CS2_RENAN.backend.services.coaching_service.get_ollama_writer") as mock_writer:

            def setting_side_effect(key, default=None):
                return {
                    "USE_RAG_COACHING": False,
                    "USE_HYBRID_COACHING": False,
                    "USE_COPER_COACHING": True,
                }.get(key, default)

            mock_setting.side_effect = setting_side_effect
            mock_corr.return_value = [{"feature": "avg_adr", "weighted_z": -2.0}]
            mock_writer.return_value.polish.side_effect = lambda **kw: kw.get("message", "polished")

            from Programma_CS2_RENAN.backend.services.coaching_service import CoachingService

            svc = CoachingService()

            # COPER will fail because get_experience_bank() initializes the real DB
            # But the except block falls back to generate_corrections
            svc.generate_new_insights(
                player_name="FallbackPlayer",
                demo_name="test.dem",
                deviations={"avg_adr": -10.0},
                rounds_played=15,
                map_name="de_mirage",
                tick_data={"team": "CT", "health": 100},
            )

            # Traditional fallback should have saved insights
            with mock_db.get_session() as session:
                insights = session.exec(
                    select(CoachingInsight).where(CoachingInsight.player_name == "FallbackPlayer")
                ).all()
                assert len(insights) >= 1, "Fallback should have produced at least 1 insight"

    def test_coper_with_non_dict_tick_data_does_not_crash(self, mock_db):
        """Non-dict tick_data triggers COPER guard — no crash, no exception.

        The COPER guard returns early without exception, so the COPER block
        completes normally (no fallback to traditional). This is by design:
        invalid tick_data is logged as a warning and silently skipped.
        """
        with patch("Programma_CS2_RENAN.backend.services.coaching_service.get_db_manager", return_value=mock_db), \
             patch("Programma_CS2_RENAN.backend.services.coaching_service.get_setting") as mock_setting, \
             patch("Programma_CS2_RENAN.backend.services.coaching_service.generate_corrections") as mock_corr, \
             patch("Programma_CS2_RENAN.backend.services.coaching_service.get_ollama_writer") as mock_writer:

            def setting_side_effect(key, default=None):
                return {
                    "USE_RAG_COACHING": False,
                    "USE_HYBRID_COACHING": False,
                    "USE_COPER_COACHING": True,
                }.get(key, default)

            mock_setting.side_effect = setting_side_effect
            mock_corr.return_value = [{"feature": "accuracy", "weighted_z": -1.5}]
            mock_writer.return_value.polish.side_effect = lambda **kw: kw.get("message", "polished")

            from Programma_CS2_RENAN.backend.services.coaching_service import CoachingService

            svc = CoachingService()

            # tick_data is a list (not dict) — COPER guard catches it with a warning
            # Should NOT crash or raise any exception
            svc.generate_new_insights(
                player_name="GuardPlayer",
                demo_name="test.dem",
                deviations={"accuracy": -5.0},
                rounds_played=10,
                map_name="de_mirage",
                tick_data=[1, 2, 3],
            )


# ============ get_latest_insights ============


class TestGetLatestInsights:
    """Test insight retrieval."""

    def test_empty_returns_empty(self, coaching_service, mock_db):
        """No insights for player → empty list."""
        results = coaching_service.get_latest_insights("NonexistentPlayer")
        assert results == []

    def test_returns_correct_player(self, coaching_service, mock_db):
        """Only returns insights for the requested player."""
        with mock_db.get_session() as session:
            session.add(CoachingInsight(
                player_name="PlayerA", demo_name="a.dem",
                title="T1", severity="Medium", message="M1", focus_area="aim",
            ))
            session.add(CoachingInsight(
                player_name="PlayerB", demo_name="b.dem",
                title="T2", severity="Medium", message="M2", focus_area="aim",
            ))

        results = coaching_service.get_latest_insights("PlayerA")
        assert len(results) == 1
        assert results[0].player_name == "PlayerA"

    def test_respects_limit(self, coaching_service, mock_db):
        """Limit parameter restricts result count."""
        with mock_db.get_session() as session:
            for i in range(10):
                session.add(CoachingInsight(
                    player_name="TestP", demo_name=f"d{i}.dem",
                    title=f"T{i}", severity="Medium", message=f"M{i}", focus_area="aim",
                ))

        results = coaching_service.get_latest_insights("TestP", limit=3)
        assert len(results) == 3

    def test_ordered_by_created_at_desc(self, coaching_service, mock_db):
        """Results are ordered newest-first."""
        from datetime import timedelta

        with mock_db.get_session() as session:
            older = CoachingInsight(
                player_name="TestP", demo_name="old.dem",
                title="Old", severity="Medium", message="old", focus_area="aim",
                created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            )
            newer = CoachingInsight(
                player_name="TestP", demo_name="new.dem",
                title="New", severity="Medium", message="new", focus_area="aim",
                created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            )
            session.add(older)
            session.add(newer)

        results = coaching_service.get_latest_insights("TestP", limit=2)
        assert results[0].title == "New"
        assert results[1].title == "Old"


# ============ _save_corrections_as_insights ============


class TestSaveCorrections:
    """Test the module-level correction saving function."""

    def test_saves_basic_correction(self, mock_db):
        """Basic correction creates CoachingInsight with correct fields."""
        with patch("Programma_CS2_RENAN.backend.services.coaching_service.get_ollama_writer") as mock_writer:
            mock_writer.return_value.polish.side_effect = lambda **kw: kw.get("message", "polished")

            from Programma_CS2_RENAN.backend.services.coaching_service import _save_corrections_as_insights

            corrections = [{"feature": "avg_adr", "weighted_z": -2.5}]
            _save_corrections_as_insights(mock_db, "Player1", "demo.dem", corrections)

            with mock_db.get_session() as session:
                insights = session.exec(select(CoachingInsight)).all()
                assert len(insights) == 1
                assert insights[0].player_name == "Player1"
                assert insights[0].focus_area == "avg_adr"
                assert insights[0].severity == "High"  # |Z| >= 2

    def test_saves_rag_correction(self, mock_db):
        """RAG-enhanced correction uses rag_title and rag_description."""
        with patch("Programma_CS2_RENAN.backend.services.coaching_service.get_ollama_writer") as mock_writer:
            mock_writer.return_value.polish.side_effect = lambda **kw: kw.get("message", "polished")

            from Programma_CS2_RENAN.backend.services.coaching_service import _save_corrections_as_insights

            corrections = [
                {
                    "feature": "positioning",
                    "weighted_z": 0,
                    "rag_title": "A-site crossfire setup",
                    "rag_description": "Hold A with crossfire from ramp and palace.",
                    "rag_pro_example": "FaZe vs NAVI IEM 2024",
                }
            ]
            _save_corrections_as_insights(mock_db, "Player1", "demo.dem", corrections)

            with mock_db.get_session() as session:
                insights = session.exec(select(CoachingInsight)).all()
                assert len(insights) == 1
                assert insights[0].title == "A-site crossfire setup"
                assert insights[0].severity == "Info"

    def test_severity_medium_for_small_z(self, mock_db):
        """Z-score < 2 → severity Medium."""
        with patch("Programma_CS2_RENAN.backend.services.coaching_service.get_ollama_writer") as mock_writer:
            mock_writer.return_value.polish.side_effect = lambda **kw: kw.get("message", "polished")

            from Programma_CS2_RENAN.backend.services.coaching_service import _save_corrections_as_insights

            corrections = [{"feature": "avg_hs", "weighted_z": -1.5}]
            _save_corrections_as_insights(mock_db, "P", "d.dem", corrections)

            with mock_db.get_session() as session:
                insight = session.exec(select(CoachingInsight)).first()
                assert insight.severity == "Medium"

    def test_severity_high_for_large_z(self, mock_db):
        """Z-score >= 2 → severity High."""
        with patch("Programma_CS2_RENAN.backend.services.coaching_service.get_ollama_writer") as mock_writer:
            mock_writer.return_value.polish.side_effect = lambda **kw: kw.get("message", "polished")

            from Programma_CS2_RENAN.backend.services.coaching_service import _save_corrections_as_insights

            corrections = [{"feature": "avg_adr", "weighted_z": -3.0}]
            _save_corrections_as_insights(mock_db, "P", "d.dem", corrections)

            with mock_db.get_session() as session:
                insight = session.exec(select(CoachingInsight)).first()
                assert insight.severity == "High"


# ============ _run_longitudinal_coaching ============


class TestLongitudinalCoaching:
    """Test trend-aware longitudinal coaching."""

    def test_not_enough_history_no_insights(self, coaching_service, mock_db):
        """< 3 matches → no longitudinal insights generated."""
        with mock_db.get_session() as session:
            session.add(PlayerMatchStats(
                player_name="TestP", demo_name="d1.dem",
                avg_kills=20.0, avg_adr=85.0, avg_kast=0.70, accuracy=0.28,
                match_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
                processed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            ))

        coaching_service._run_longitudinal_coaching("TestP", "d1.dem")

        with mock_db.get_session() as session:
            insights = session.exec(
                select(CoachingInsight).where(CoachingInsight.player_name == "TestP")
            ).all()
            assert len(insights) == 0

    def test_with_enough_history(self, coaching_service, mock_db):
        """>= 3 matches should attempt longitudinal analysis without crash."""
        with mock_db.get_session() as session:
            for i in range(5):
                session.add(PlayerMatchStats(
                    player_name="TestP",
                    demo_name=f"d{i}.dem",
                    avg_kills=18.0 + i,
                    avg_adr=75.0 + i * 2,
                    avg_kast=0.65 + i * 0.02,
                    accuracy=0.24 + i * 0.01,
                    match_date=datetime(2024, 6, i + 1, tzinfo=timezone.utc),
                    processed_at=datetime(2024, 6, i + 1, tzinfo=timezone.utc),
                ))

        # Should not crash; may or may not produce insights depending on trend
        coaching_service._run_longitudinal_coaching("TestP", "d4.dem")
        # If it produced insights, they should be valid
        with mock_db.get_session() as session:
            insights = session.exec(
                select(CoachingInsight).where(CoachingInsight.player_name == "TestP")
            ).all()
            for i in insights:
                assert i.title
                assert i.message
                assert i.focus_area


# ============ _baseline_context_note edge cases ============


class TestBaselineContextNoteEdgeCases:
    """Additional edge cases for baseline comparison."""

    def test_scalar_baseline_value(self, coaching_service):
        """Baseline value as scalar (not dict) is handled."""
        result = coaching_service._baseline_context_note(
            player_stats={"rating": 0.85},
            baseline={"rating": 1.05},  # Scalar, not {"mean": 1.05}
            focus_area="positioning",
        )
        assert "below" in result.lower()

    def test_missing_player_stat_key(self, coaching_service):
        """Missing key in player_stats → no note for that metric."""
        result = coaching_service._baseline_context_note(
            player_stats={"avg_adr": 70.0},  # No "rating" key
            baseline={"rating": {"mean": 1.05}},
            focus_area="positioning",
        )
        assert result == ""

    def test_zero_baseline_mean(self, coaching_service):
        """Zero baseline mean → skip (avoid division by zero)."""
        result = coaching_service._baseline_context_note(
            player_stats={"rating": 1.0},
            baseline={"rating": {"mean": 0}},
            focus_area="positioning",
        )
        assert result == ""

    def test_aim_focus_uses_hs_and_kills(self, coaching_service):
        """'aim' focus area checks avg_hs and avg_kills."""
        result = coaching_service._baseline_context_note(
            player_stats={"avg_hs": 0.35, "avg_kills": 14.0},
            baseline={"avg_hs": {"mean": 0.50}, "avg_kills": {"mean": 18.5}},
            focus_area="aim",
        )
        assert "below" in result.lower()
