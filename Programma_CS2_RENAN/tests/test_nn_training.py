"""
Tests for NN Training Components — Phase 7 Coverage Expansion.

Covers:
  EarlyStopping (early_stopping.py) — patience, min_delta, reset
  TrainingDecision (training_controller.py) — dataclass
  TrainingController (training_controller.py) — diversity, monthly limit, features
"""

import sys


import numpy as np
import pytest


# ---------------------------------------------------------------------------
# EarlyStopping
# ---------------------------------------------------------------------------
class TestEarlyStopping:
    """Tests for the early stopping mechanism."""

    def _make(self, patience=3, min_delta=0.01):
        from Programma_CS2_RENAN.backend.nn.early_stopping import EarlyStopping
        return EarlyStopping(patience=patience, min_delta=min_delta)

    def test_first_call_never_stops(self):
        es = self._make()
        assert es(1.0) is False

    def test_improvement_resets_counter(self):
        es = self._make(patience=3, min_delta=0.01)
        es(1.0)
        es(0.95)  # Improvement
        es(0.94)  # No improvement (delta < 0.01)
        assert es.counter == 1  # Only 1 no-improvement

    def test_stops_after_patience(self):
        es = self._make(patience=3, min_delta=0.01)
        es(1.0)  # Initial
        es(1.0)  # No improvement → counter=1
        es(1.0)  # counter=2
        result = es(1.0)  # counter=3 → stop
        assert result is True
        assert es.should_stop is True

    def test_no_stop_with_improvements(self):
        es = self._make(patience=3, min_delta=0.01)
        losses = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5]
        for loss in losses:
            assert es(loss) is False

    def test_reset(self):
        es = self._make(patience=2, min_delta=0.01)
        es(1.0)
        es(1.0)  # counter=1
        es.reset()
        assert es.counter == 0
        assert es.best_loss is None
        assert es.should_stop is False

    def test_reset_then_reuse(self):
        es = self._make(patience=2, min_delta=0.01)
        es(1.0)
        es(1.0)  # counter=1
        es(1.0)  # counter=2 → stop
        assert es.should_stop is True
        es.reset()
        assert es(0.5) is False  # Fresh start

    def test_min_delta_boundary(self):
        """Improvement exactly at min_delta should NOT count."""
        es = self._make(patience=3, min_delta=0.10)
        es(1.0)
        es(0.90)  # Exactly min_delta: 1.0 - 0.90 = 0.10, NOT < best - delta
        # 0.90 < 1.0 - 0.10 → 0.90 < 0.90 → False → no improvement
        assert es.counter == 1

    def test_significant_improvement(self):
        es = self._make(patience=3, min_delta=0.10)
        es(1.0)
        result = es(0.85)  # 0.85 < 1.0 - 0.10 = 0.90 → improvement
        assert result is False
        assert es.counter == 0
        assert es.best_loss == 0.85

    def test_default_params(self):
        from Programma_CS2_RENAN.backend.nn.early_stopping import EarlyStopping
        es = EarlyStopping()
        assert es.patience == 10
        assert es.min_delta == 1e-4


# ---------------------------------------------------------------------------
# TrainingDecision
# ---------------------------------------------------------------------------
class TestTrainingDecision:
    """Tests for the TrainingDecision dataclass."""

    def test_creation(self):
        from Programma_CS2_RENAN.backend.nn.training_controller import TrainingDecision
        td = TrainingDecision(should_train=True, reason="Good diversity", diversity_score=0.75)
        assert td.should_train is True
        assert td.reason == "Good diversity"
        assert td.diversity_score == 0.75

    def test_default_diversity(self):
        from Programma_CS2_RENAN.backend.nn.training_controller import TrainingDecision
        td = TrainingDecision(should_train=False, reason="Monthly limit")
        assert td.diversity_score == 0.0


# ---------------------------------------------------------------------------
# TrainingController (isolated methods)
# ---------------------------------------------------------------------------
class TestTrainingControllerHelpers:
    """Tests for TrainingController helper methods without DB deps."""

    def _make_controller_shell(self):
        from Programma_CS2_RENAN.backend.nn.training_controller import TrainingController
        ctrl = TrainingController.__new__(TrainingController)
        return ctrl

    def test_cosine_similarity_identical(self):
        ctrl = self._make_controller_shell()
        v = np.array([1.0, 2.0, 3.0])
        assert abs(ctrl._cosine_similarity(v, v) - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        ctrl = self._make_controller_shell()
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert abs(ctrl._cosine_similarity(a, b)) < 1e-6

    def test_cosine_similarity_zero_vector(self):
        ctrl = self._make_controller_shell()
        a = np.array([1.0, 2.0])
        b = np.array([0.0, 0.0])
        assert ctrl._cosine_similarity(a, b) == 0.0

    def test_extract_features_shape(self):
        ctrl = self._make_controller_shell()

        class FakeStats:
            avg_kills = 20.0
            avg_deaths = 15.0
            avg_adr = 80.0
            avg_hs = 0.50
            utility_blind_time = 15.0
            opening_duel_win_pct = 0.55

        features = ctrl._extract_features(FakeStats())
        assert isinstance(features, np.ndarray)
        assert features.shape == (6,)

    def test_extract_features_normalization(self):
        """Features are normalized: (val - baseline) / scale."""
        ctrl = self._make_controller_shell()

        class FakeStats:
            avg_kills = 15.0  # baseline=15, scale=10 → (15-15)/10 = 0.0
            avg_deaths = 15.0
            avg_adr = 75.0  # baseline=75, scale=25 → 0.0
            avg_hs = 0.4
            utility_blind_time = 20.0
            opening_duel_win_pct = 0.5

        features = ctrl._extract_features(FakeStats())
        # All at baseline → all zeros
        assert np.allclose(features, np.zeros(6), atol=1e-6)

    def test_extract_features_missing_attr_raises(self):
        """Missing attributes raise AttributeError (stats contract enforced)."""
        ctrl = self._make_controller_shell()

        class EmptyStats:
            pass

        with pytest.raises(AttributeError):
            ctrl._extract_features(EmptyStats())

    def test_constants(self):
        from Programma_CS2_RENAN.backend.nn.training_controller import TrainingController
        assert TrainingController.MAX_DEMOS_PER_MONTH == 10
        assert TrainingController.MIN_DIVERSITY_SCORE == 0.3
