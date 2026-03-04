"""
Tests for TrainingController diversity check and monthly limit logic.

Pure math tests for _extract_features() and _cosine_similarity() with all 6
feature fields controlled. Integration tests use real DB with skip gates.

Onboarding flow tests are in test_onboarding.py (no duplication).

F9-09/F9-02: BORDERLINE anti-fabrication review — TestExtractFeatures creates synthetic
PlayerMatchStats objects to test _extract_features() z-centering formula (pure math, not
domain/game behavior). Reviewed and classified as COMPLIANT per CLAUDE.md: these are
formula unit tests analogous to test_unit.py, not ML pipeline assertions against
synthetic data pretending to be real game state.
"""

import sys


import numpy as np
import pytest
from sqlmodel import select

from Programma_CS2_RENAN.backend.nn.training_controller import (
    TrainingController,
    get_training_controller,
)
from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database
from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats


class TestExtractFeatures:
    """Pure math tests for _extract_features() with controlled inputs."""

    def test_baseline_player_yields_zero_vector(self):
        """A player at exact baselines should produce a near-zero vector."""
        controller = TrainingController()
        stats = PlayerMatchStats(
            player_name="test",
            demo_name="test.dem",
            avg_kills=15.0,
            avg_deaths=15.0,
            avg_adr=75.0,
            avg_hs=0.4,
            utility_blind_time=20.0,
            opening_duel_win_pct=0.5,
        )
        vec = controller._extract_features(stats)
        assert vec.shape == (6,)
        np.testing.assert_allclose(vec, np.zeros(6), atol=1e-10)

    def test_above_baseline_positive(self):
        """Stats above baseline should produce positive features (except deaths, inverted)."""
        controller = TrainingController()
        # Good player: high kills, LOW deaths, high ADR/HS/util/opening
        stats = PlayerMatchStats(
            player_name="test",
            demo_name="test.dem",
            avg_kills=25.0,
            avg_deaths=5.0,
            avg_adr=100.0,
            avg_hs=0.6,
            utility_blind_time=40.0,
            opening_duel_win_pct=0.8,
        )
        vec = controller._extract_features(stats)
        # Feature vector is z-centered: (value - baseline) / scale
        # Deaths uses same formula, so fewer deaths = negative feature
        # idx: 0=kills(+), 1=deaths(-), 2=adr(+), 3=hs(+), 4=util(+), 5=opening(+)
        assert vec[0] > 0, f"kills feature should be positive, got {vec[0]}"
        assert vec[1] < 0, f"deaths feature should be negative (good player), got {vec[1]}"
        assert all(v > 0 for v in vec[2:]), f"adr/hs/util/opening should be positive, got {vec[2:]}"

    def test_below_baseline_negative(self):
        """Stats below baseline should produce negative features (except deaths, inverted)."""
        controller = TrainingController()
        # Bad player: low kills, HIGH deaths, low ADR/HS/util/opening
        stats = PlayerMatchStats(
            player_name="test",
            demo_name="test.dem",
            avg_kills=5.0,
            avg_deaths=25.0,
            avg_adr=50.0,
            avg_hs=0.2,
            utility_blind_time=0.0,
            opening_duel_win_pct=0.2,
        )
        vec = controller._extract_features(stats)
        # Deaths uses same formula, so more deaths = positive feature
        assert vec[0] < 0, f"kills feature should be negative, got {vec[0]}"
        assert vec[1] > 0, f"deaths feature should be positive (bad player), got {vec[1]}"
        assert all(v < 0 for v in vec[2:]), f"adr/hs/util/opening should be negative, got {vec[2:]}"


class TestCosineSimilarity:
    """Pure math tests for _cosine_similarity()."""

    def test_identical_vectors_similarity_one(self):
        controller = TrainingController()
        a = np.array([1.0, 2.0, 3.0])
        assert controller._cosine_similarity(a, a) == pytest.approx(1.0)

    def test_orthogonal_vectors_similarity_zero(self):
        controller = TrainingController()
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert controller._cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors_similarity_negative(self):
        controller = TrainingController()
        a = np.array([1.0, 2.0, 3.0])
        b = -a
        assert controller._cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        controller = TrainingController()
        a = np.zeros(3)
        b = np.array([1.0, 2.0, 3.0])
        assert controller._cosine_similarity(a, b) == 0.0


class TestDiversityScore:
    """Integration tests for diversity scoring with real DB."""

    def test_diversity_with_real_db(self):
        """Diversity score from real recent matches, or skip."""
        init_database()
        controller = get_training_controller()
        db = get_db_manager()

        with db.get_session() as session:
            recent = session.exec(select(PlayerMatchStats).limit(2)).all()

        if len(recent) < 2:
            pytest.skip("Need at least 2 PlayerMatchStats for diversity test")

        # Diversity of first match against rest should be in [0, 1]
        score = controller._calculate_diversity_score(recent[0])
        assert 0.0 <= score <= 1.0


class TestMonthlyLimit:
    """Integration tests for monthly training limit with real DB."""

    def test_monthly_count_real_db(self):
        """Monthly count should be a non-negative integer."""
        init_database()
        controller = get_training_controller()
        count = controller._get_monthly_training_count()
        assert isinstance(count, int)
        assert count >= 0

    def test_monthly_limit_threshold(self):
        """MAX_DEMOS_PER_MONTH should be 10."""
        controller = TrainingController()
        assert controller.MAX_DEMOS_PER_MONTH == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
