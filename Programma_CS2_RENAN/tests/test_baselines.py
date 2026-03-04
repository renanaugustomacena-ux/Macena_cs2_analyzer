"""
Tests for Pro Baseline & Role Thresholds — Phase 6 Coverage Expansion.

Covers:
  pro_baseline.py — HARD_DEFAULT_BASELINE, _get_default_pro_baseline,
                     calculate_deviations, TemporalBaselineDecay
  role_thresholds.py — LearnedThreshold, RoleThresholdStore
"""

import sys


import math
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# HARD_DEFAULT_BASELINE
# ---------------------------------------------------------------------------
class TestHardDefaultBaseline:
    """Tests for the hard-coded fallback baseline."""

    def test_baseline_is_dict(self):
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            HARD_DEFAULT_BASELINE,
        )
        assert isinstance(HARD_DEFAULT_BASELINE, dict)

    def test_baseline_has_expected_keys(self):
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            HARD_DEFAULT_BASELINE,
        )
        expected = {
            "rating", "kd_ratio", "avg_kills", "avg_deaths", "avg_adr",
            "avg_hs", "avg_kast", "accuracy",
        }
        assert expected.issubset(set(HARD_DEFAULT_BASELINE.keys()))

    def test_baseline_values_have_mean_std(self):
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            HARD_DEFAULT_BASELINE,
        )
        for key, val in HARD_DEFAULT_BASELINE.items():
            assert "mean" in val, f"Missing 'mean' for {key}"
            assert "std" in val, f"Missing 'std' for {key}"

    def test_baseline_std_positive(self):
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            HARD_DEFAULT_BASELINE,
        )
        for key, val in HARD_DEFAULT_BASELINE.items():
            assert val["std"] > 0, f"std <= 0 for {key}"


class TestGetDefaultProBaseline:
    """Tests for _get_default_pro_baseline()."""

    def test_returns_dict_with_provenance(self):
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            _get_default_pro_baseline,
        )
        result = _get_default_pro_baseline()
        assert isinstance(result, dict)
        assert result.get("_provenance") == "hard_default"

    def test_contains_all_hard_keys(self):
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            HARD_DEFAULT_BASELINE,
            _get_default_pro_baseline,
        )
        result = _get_default_pro_baseline()
        for key in HARD_DEFAULT_BASELINE:
            assert key in result


# ---------------------------------------------------------------------------
# calculate_deviations
# ---------------------------------------------------------------------------
class TestCalculateDeviations:
    """Tests for Z-score calculation."""

    def _calc(self, player, baseline):
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            calculate_deviations,
        )
        return calculate_deviations(player, baseline)

    def test_basic_z_score(self):
        player = {"rating": 1.30}
        baseline = {"rating": {"mean": 1.15, "std": 0.15}}
        devs = self._calc(player, baseline)
        z, raw = devs["rating"]
        assert abs(z - 1.0) < 1e-5  # (1.30-1.15)/0.15 = 1.0
        assert abs(raw - 0.15) < 1e-5

    def test_negative_z_score(self):
        player = {"rating": 0.85}
        baseline = {"rating": {"mean": 1.15, "std": 0.15}}
        devs = self._calc(player, baseline)
        z, _ = devs["rating"]
        assert z < 0

    def test_zero_std_skips(self):
        player = {"rating": 1.30}
        baseline = {"rating": {"mean": 1.15, "std": 0.0}}
        devs = self._calc(player, baseline)
        z, raw = devs["rating"]
        assert z == 0.0  # Skipped
        assert abs(raw - 0.15) < 1e-5

    def test_missing_player_stat(self):
        """Player stats missing a key → no entry in deviations."""
        player = {}
        baseline = {"rating": {"mean": 1.15, "std": 0.15}}
        devs = self._calc(player, baseline)
        assert "rating" not in devs

    def test_multiple_metrics(self):
        player = {"rating": 1.30, "avg_adr": 90.0}
        baseline = {
            "rating": {"mean": 1.15, "std": 0.15},
            "avg_adr": {"mean": 82.0, "std": 12.0},
        }
        devs = self._calc(player, baseline)
        assert "rating" in devs
        assert "avg_adr" in devs

    def test_non_dict_baseline_value(self):
        """Baseline value as scalar (not dict) → treated as mean with std=0."""
        player = {"rating": 1.30}
        baseline = {"rating": 1.15}
        devs = self._calc(player, baseline)
        z, raw = devs["rating"]
        assert z == 0.0  # std=0 → skipped
        assert abs(raw - 0.15) < 1e-5


# ---------------------------------------------------------------------------
# TemporalBaselineDecay
# ---------------------------------------------------------------------------
class TestTemporalBaselineDecay:
    """Tests for time-weighted baseline computation."""

    def _make_decay(self):
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            TemporalBaselineDecay,
        )
        return TemporalBaselineDecay()

    def test_compute_weight_today(self):
        decay = self._make_decay()
        now = datetime.now(timezone.utc)
        w = decay.compute_weight(now, reference_date=now)
        assert abs(w - 1.0) < 1e-6

    def test_compute_weight_future(self):
        """Future date → weight = 1.0."""
        decay = self._make_decay()
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=30)
        w = decay.compute_weight(future, reference_date=now)
        assert abs(w - 1.0) < 1e-6

    def test_compute_weight_half_life(self):
        """After exactly HALF_LIFE_DAYS → weight ≈ 0.5."""
        decay = self._make_decay()
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=decay.HALF_LIFE_DAYS)
        w = decay.compute_weight(old, reference_date=now)
        assert abs(w - 0.5) < 0.05

    def test_compute_weight_very_old(self):
        """Very old data → clamped to MIN_WEIGHT."""
        decay = self._make_decay()
        now = datetime.now(timezone.utc)
        ancient = now - timedelta(days=3650)  # 10 years
        w = decay.compute_weight(ancient, reference_date=now)
        assert w == decay.MIN_WEIGHT

    def test_compute_weight_monotone_decreasing(self):
        """Weights decrease with age."""
        decay = self._make_decay()
        now = datetime.now(timezone.utc)
        weights = []
        for days_ago in [0, 30, 90, 180, 365]:
            dt = now - timedelta(days=days_ago)
            weights.append(decay.compute_weight(dt, reference_date=now))
        for i in range(1, len(weights)):
            assert weights[i] <= weights[i - 1]

    def test_compute_weighted_baseline_empty(self):
        decay = self._make_decay()
        result = decay.compute_weighted_baseline([])
        assert result == {}

    def test_compute_weighted_baseline_single_card(self):
        decay = self._make_decay()

        class FakeCard:
            last_updated = datetime.now(timezone.utc)
            rating_2_0 = 1.25
            kpr = 0.80
            dpr = 0.60
            kast = 72.0
            impact = 1.15
            adr = 85.0
            headshot_pct = 0.55
            opening_kill_ratio = 0.58
            opening_duel_win_pct = 0.52

        result = decay.compute_weighted_baseline([FakeCard()])
        assert "rating" in result
        assert abs(result["rating"]["mean"] - 1.25) < 1e-5

    def test_detect_meta_shift_no_shift(self):
        decay = self._make_decay()
        old = {"rating": {"mean": 1.15}, "avg_adr": {"mean": 82.0}}
        new = {"rating": {"mean": 1.16}, "avg_adr": {"mean": 82.5}}
        shifted = decay.detect_meta_shift(old, new)
        assert len(shifted) == 0

    def test_detect_meta_shift_significant(self):
        decay = self._make_decay()
        old = {"rating": {"mean": 1.00}, "avg_adr": {"mean": 82.0}}
        new = {"rating": {"mean": 1.20}, "avg_adr": {"mean": 82.0}}  # 20% jump
        shifted = decay.detect_meta_shift(old, new)
        assert "rating" in shifted

    def test_detect_meta_shift_zero_old_mean(self):
        """Zero old mean → skip (avoid div by zero)."""
        decay = self._make_decay()
        old = {"metric": {"mean": 0}}
        new = {"metric": {"mean": 1.0}}
        shifted = decay.detect_meta_shift(old, new)
        assert len(shifted) == 0

    def test_metric_to_baseline_key_mapping(self):
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            TemporalBaselineDecay,
        )
        assert TemporalBaselineDecay._metric_to_baseline_key("rating_2_0") == "rating"
        assert TemporalBaselineDecay._metric_to_baseline_key("kpr") == "avg_kills"
        assert TemporalBaselineDecay._metric_to_baseline_key("dpr") == "avg_deaths"
        assert TemporalBaselineDecay._metric_to_baseline_key("adr") == "avg_adr"

    def test_metric_to_baseline_key_unknown(self):
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            TemporalBaselineDecay,
        )
        assert TemporalBaselineDecay._metric_to_baseline_key("unknown_metric") == "unknown_metric"

    def test_half_life_constant(self):
        decay = self._make_decay()
        assert decay.HALF_LIFE_DAYS == 90.0

    def test_min_weight_constant(self):
        decay = self._make_decay()
        assert decay.MIN_WEIGHT == 0.1


# ---------------------------------------------------------------------------
# LearnedThreshold
# ---------------------------------------------------------------------------
class TestLearnedThreshold:
    """Tests for the LearnedThreshold dataclass."""

    def test_defaults(self):
        from Programma_CS2_RENAN.backend.processing.baselines.role_thresholds import (
            LearnedThreshold,
        )
        lt = LearnedThreshold()
        assert lt.value is None
        assert lt.sample_count == 0
        assert lt.last_updated is None
        assert lt.source == "unknown"

    def test_custom_values(self):
        from Programma_CS2_RENAN.backend.processing.baselines.role_thresholds import (
            LearnedThreshold,
        )
        now = datetime.now()
        lt = LearnedThreshold(value=0.42, sample_count=100, last_updated=now, source="hltv")
        assert lt.value == 0.42
        assert lt.sample_count == 100
        assert lt.source == "hltv"


# ---------------------------------------------------------------------------
# RoleThresholdStore
# ---------------------------------------------------------------------------
class TestRoleThresholdStore:
    """Tests for the dynamic threshold store."""

    def _make_store(self):
        from Programma_CS2_RENAN.backend.processing.baselines.role_thresholds import (
            RoleThresholdStore,
        )
        return RoleThresholdStore()

    def test_cold_start_initial(self):
        store = self._make_store()
        assert store.is_cold_start() is True

    def test_get_threshold_none_unlearned(self):
        store = self._make_store()
        assert store.get_threshold("awp_kill_ratio") is None

    def test_get_threshold_unknown_stat(self):
        store = self._make_store()
        assert store.get_threshold("nonexistent_stat") is None

    def test_get_threshold_insufficient_samples(self):
        """Even with a value, insufficient samples → None."""
        store = self._make_store()
        store._thresholds["awp_kill_ratio"].value = 0.3
        store._thresholds["awp_kill_ratio"].sample_count = 5  # < 10
        assert store.get_threshold("awp_kill_ratio") is None

    def test_get_threshold_sufficient_samples(self):
        store = self._make_store()
        store._thresholds["awp_kill_ratio"].value = 0.3
        store._thresholds["awp_kill_ratio"].sample_count = 15
        assert store.get_threshold("awp_kill_ratio") == 0.3

    def test_validate_consistency_placeholder(self):
        store = self._make_store()
        assert store.validate_consistency() is True

    def test_readiness_report_structure(self):
        store = self._make_store()
        report = store.get_readiness_report()
        assert "is_cold_start" in report
        assert "thresholds" in report
        assert report["is_cold_start"] is True
        # Each threshold entry
        for name, info in report["thresholds"].items():
            assert "value" in info
            assert "samples" in info
            assert "valid" in info
            assert "source" in info

    def test_expected_threshold_keys(self):
        store = self._make_store()
        expected = {
            "awp_kill_ratio", "entry_rate", "assist_rate", "survival_rate",
            "solo_kill_rate", "first_death_rate", "utility_damage_rate",
            "clutch_rate", "trade_rate",
        }
        assert set(store._thresholds.keys()) == expected

    def test_learn_from_pro_data_empty(self):
        """Empty data → no crash, still cold start."""
        store = self._make_store()
        store.learn_from_pro_data([])
        assert store.is_cold_start() is True

    def test_learn_from_pro_data_real(self):
        """Realistic pro stats → thresholds learned, exits cold start."""
        store = self._make_store()
        pro_stats = []
        for i in range(20):
            pro_stats.append({
                "awp_kills": 5 + i,
                "total_kills": 50 + i,
                "entry_frags": 3 + i % 5,
                "rounds_played": 30,
                "assists": 4 + i % 3,
                "rounds_survived": 15 + i % 10,
                "solo_kills": 2 + i % 4,
            })
        store.learn_from_pro_data(pro_stats)
        # At least 3 valid thresholds → no longer cold start
        assert store.is_cold_start() is False
        assert store._is_initialized is True

    def test_learn_from_pro_data_updates_values(self):
        store = self._make_store()
        pro_stats = [
            {"awp_kills": 10, "total_kills": 50, "entry_frags": 5,
             "rounds_played": 30, "assists": 4, "rounds_survived": 20,
             "solo_kills": 3}
        ] * 15  # 15 identical records
        store.learn_from_pro_data(pro_stats)
        # awp_kill_ratio = 10/50 = 0.2 for all → 75th percentile = 0.2
        t = store._thresholds["awp_kill_ratio"]
        assert t.value is not None
        assert t.sample_count == 15
        assert t.source == "hltv"

    def test_min_samples_constant(self):
        store = self._make_store()
        assert store.MIN_SAMPLES_FOR_VALIDITY == 10
