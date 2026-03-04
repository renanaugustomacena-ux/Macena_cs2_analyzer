"""
Test Suite for Temporal Baseline Decay System (Fusion Plan Proposal 11).

Tests cover:
- Weight computation (exponential decay, boundary conditions)
- Weighted baseline computation from synthetic stat cards
- Meta shift detection
- Fallback behavior when data is insufficient
- Determinism (same inputs produce same outputs)
"""

import math
import sys
import types
from datetime import datetime, timedelta, timezone


import pytest

from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
    TemporalBaselineDecay,
    get_pro_baseline,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stat_card(**overrides):
    """Create a ProPlayerStatCard-like object using SimpleNamespace.

    Uses SimpleNamespace instead of MagicMock so that getattr(..., None)
    correctly returns None for missing attributes rather than auto-creating
    new MagicMock objects.
    """
    defaults = {
        "last_updated": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "rating_2_0": 1.15,
        "kpr": 0.78,
        "dpr": 0.62,
        "kast": 0.72,
        "impact": 1.10,
        "adr": 82.0,
        "headshot_pct": 0.52,
        "opening_kill_ratio": 0.0,
        "opening_duel_win_pct": 0.55,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# TestComputeWeight
# ---------------------------------------------------------------------------


class TestComputeWeight:
    """Unit tests for TemporalBaselineDecay.compute_weight()."""

    def setup_method(self):
        self.decay = TemporalBaselineDecay()
        self.reference = datetime(2026, 6, 1, 12, 0, 0)

    def test_weight_for_today(self):
        """Weight for data from today should be 1.0."""
        w = self.decay.compute_weight(self.reference, self.reference)
        assert w == 1.0

    def test_weight_for_future_date(self):
        """Weight for future data should be 1.0 (age <= 0)."""
        future = self.reference + timedelta(days=10)
        w = self.decay.compute_weight(future, self.reference)
        assert w == 1.0

    def test_weight_at_half_life(self):
        """Weight at exactly 90 days should be ~0.5."""
        stat_date = self.reference - timedelta(days=90)
        w = self.decay.compute_weight(stat_date, self.reference)
        assert abs(w - 0.5) < 0.01

    def test_weight_at_45_days(self):
        """Weight at 45 days (half of half-life) should be ~0.707."""
        stat_date = self.reference - timedelta(days=45)
        w = self.decay.compute_weight(stat_date, self.reference)
        expected = math.exp(-math.log(2) * 45 / 90.0)
        assert abs(w - expected) < 0.01

    def test_weight_at_180_days(self):
        """Weight at 180 days (2x half-life) should be ~0.25."""
        stat_date = self.reference - timedelta(days=180)
        w = self.decay.compute_weight(stat_date, self.reference)
        assert abs(w - 0.25) < 0.02

    def test_weight_at_365_days_clamped(self):
        """Weight at 365 days should be clamped to MIN_WEIGHT (0.1)."""
        stat_date = self.reference - timedelta(days=365)
        w = self.decay.compute_weight(stat_date, self.reference)
        assert w == self.decay.MIN_WEIGHT

    def test_weight_always_in_range(self):
        """Weight is always in [MIN_WEIGHT, 1.0] for any age."""
        for days in [0, 1, 10, 30, 60, 90, 180, 365, 730, 1000]:
            stat_date = self.reference - timedelta(days=days)
            w = self.decay.compute_weight(stat_date, self.reference)
            assert self.decay.MIN_WEIGHT <= w <= 1.0, f"Failed at {days} days: w={w}"

    def test_deterministic(self):
        """Same inputs produce same output (determinism requirement)."""
        stat_date = self.reference - timedelta(days=45)
        w1 = self.decay.compute_weight(stat_date, self.reference)
        w2 = self.decay.compute_weight(stat_date, self.reference)
        assert w1 == w2


# ---------------------------------------------------------------------------
# TestComputeWeightedBaseline
# ---------------------------------------------------------------------------


class TestComputeWeightedBaseline:
    """Unit tests for compute_weighted_baseline()."""

    def setup_method(self):
        self.decay = TemporalBaselineDecay()

    def test_empty_list(self):
        """Empty input returns empty baseline."""
        result = self.decay.compute_weighted_baseline([])
        assert result == {}

    def test_single_card(self):
        """Single card produces baseline with correct mean and std >= 0.01."""
        card = _make_stat_card()
        result = self.decay.compute_weighted_baseline([card])
        assert "rating" in result
        assert "avg_kills" in result
        assert result["rating"]["std"] >= 0.01
        assert result["rating"]["mean"] == pytest.approx(1.15, abs=0.01)

    def test_recent_cards_weighted_higher(self):
        """Recent cards should influence mean more than old cards."""
        recent = _make_stat_card(
            last_updated=datetime(2026, 2, 1, tzinfo=timezone.utc),
            rating_2_0=1.30,
        )
        old = _make_stat_card(
            last_updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
            rating_2_0=0.90,
        )
        result = self.decay.compute_weighted_baseline([recent, old])
        # Mean should be closer to 1.30 (recent) than 0.90 (old)
        assert result["rating"]["mean"] > 1.10

    def test_card_without_last_updated(self):
        """Cards with None last_updated get weight 0.5 (middle ground)."""
        card = _make_stat_card(last_updated=None)
        result = self.decay.compute_weighted_baseline([card])
        assert "rating" in result

    def test_deterministic(self):
        """Same inputs, same outputs (within float precision)."""
        cards = [_make_stat_card(last_updated=datetime(2026, 1, 15, tzinfo=timezone.utc))]
        r1 = self.decay.compute_weighted_baseline(cards)
        r2 = self.decay.compute_weighted_baseline(cards)
        # datetime.now(UTC) shifts by microseconds between calls, causing
        # negligible weight differences that surface as float rounding.
        for metric in r1:
            assert r1[metric] == pytest.approx(r2[metric])


# ---------------------------------------------------------------------------
# TestDetectMetaShift
# ---------------------------------------------------------------------------


class TestDetectMetaShift:
    """Unit tests for detect_meta_shift()."""

    def setup_method(self):
        self.decay = TemporalBaselineDecay()

    def test_no_shift(self):
        """Identical baselines produce no shifts."""
        baseline = {"rating": {"mean": 1.15, "std": 0.1}}
        shifts = self.decay.detect_meta_shift(baseline, baseline)
        assert shifts == []

    def test_shift_detected_above_threshold(self):
        """6% change should be flagged (threshold is 5%)."""
        old = {"rating": {"mean": 1.00, "std": 0.1}}
        new = {"rating": {"mean": 1.06, "std": 0.1}}
        shifts = self.decay.detect_meta_shift(old, new)
        assert "rating" in shifts

    def test_no_shift_below_threshold(self):
        """4% change should not be flagged."""
        old = {"rating": {"mean": 1.00, "std": 0.1}}
        new = {"rating": {"mean": 1.04, "std": 0.1}}
        shifts = self.decay.detect_meta_shift(old, new)
        assert "rating" not in shifts

    def test_zero_old_mean_skipped(self):
        """Metrics with old mean of 0 are skipped (avoid division by zero)."""
        old = {"rating": {"mean": 0.0, "std": 0.1}}
        new = {"rating": {"mean": 1.0, "std": 0.1}}
        shifts = self.decay.detect_meta_shift(old, new)
        assert shifts == []


# ---------------------------------------------------------------------------
# TestGetTemporalBaseline
# ---------------------------------------------------------------------------


class TestGetTemporalBaseline:
    """Integration tests for get_temporal_baseline()."""

    def test_fallback_returns_valid_dict(self):
        """Should always return a valid baseline dict, even without DB data."""
        decay = TemporalBaselineDecay()
        baseline = decay.get_temporal_baseline()
        assert isinstance(baseline, dict)
        assert len(baseline) > 0
        assert "rating" in baseline
        assert baseline["rating"]["mean"] > 0
        assert baseline["rating"]["std"] > 0


# ---------------------------------------------------------------------------
# TestMetricToBaselineKey
# ---------------------------------------------------------------------------


class TestMetricToBaselineKey:
    """Unit tests for _metric_to_baseline_key()."""

    def test_known_mappings(self):
        assert TemporalBaselineDecay._metric_to_baseline_key("rating_2_0") == "rating"
        assert TemporalBaselineDecay._metric_to_baseline_key("kpr") == "avg_kills"
        assert TemporalBaselineDecay._metric_to_baseline_key("dpr") == "avg_deaths"
        assert TemporalBaselineDecay._metric_to_baseline_key("kast") == "avg_kast"
        assert TemporalBaselineDecay._metric_to_baseline_key("adr") == "avg_adr"
        assert TemporalBaselineDecay._metric_to_baseline_key("headshot_pct") == "avg_hs"

    def test_unknown_key_passthrough(self):
        assert TemporalBaselineDecay._metric_to_baseline_key("unknown_metric") == "unknown_metric"
