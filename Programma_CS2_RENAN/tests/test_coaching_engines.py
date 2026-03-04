"""
Tests for Coaching Engines — Phase 11 Coverage Expansion.

Covers:
  ExplanationGenerator (explainability.py)
  PlayerCardAssimilator (pro_bridge.py)
  PlayerTokenResolver._build_token_dict, compare_performance_to_token (token_resolver.py)
  apply_nn_refinement (nn_refinement.py)
  generate_corrections, get_feature_importance (correction_engine.py)
  generate_longitudinal_coaching (longitudinal_engine.py)
"""

import sys


from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# ExplanationGenerator
# ---------------------------------------------------------------------------
class TestExplanationGenerator:
    """Tests for the explainability narrative generator."""

    def _gen(self):
        from Programma_CS2_RENAN.backend.coaching.explainability import ExplanationGenerator
        return ExplanationGenerator

    def _axes(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.skill_model import SkillAxes
        return SkillAxes

    def test_silence_threshold_returns_empty(self):
        Gen = self._gen()
        Axes = self._axes()
        result = Gen.generate_narrative(Axes.MECHANICS, "avg_kills", 0.1)
        assert result == ""

    def test_negative_mechanics(self):
        Gen = self._gen()
        Axes = self._axes()
        result = Gen.generate_narrative(Axes.MECHANICS, "avg_kills", -0.5)
        assert "kills" in result.lower() or "below" in result.lower()
        assert len(result) > 10

    def test_positive_mechanics(self):
        Gen = self._gen()
        Axes = self._axes()
        result = Gen.generate_narrative(Axes.MECHANICS, "avg_hs", 0.5)
        assert "peak" in result.lower() or "stability" in result.lower()

    def test_positioning_negative(self):
        Gen = self._gen()
        Axes = self._axes()
        result = Gen.generate_narrative(Axes.POSITIONING, "position", -0.8, {"location": "B site"})
        assert "B site" in result

    def test_positioning_positive(self):
        Gen = self._gen()
        Axes = self._axes()
        result = Gen.generate_narrative(Axes.POSITIONING, "position", 0.8, {"location": "A ramp"})
        assert "A ramp" in result

    def test_utility_with_context(self):
        Gen = self._gen()
        Axes = self._axes()
        result = Gen.generate_narrative(Axes.UTILITY, "flashbang", -0.6, {"weapon": "flashbang", "enemies": "3"})
        assert "flashbang" in result

    def test_timing_negative(self):
        Gen = self._gen()
        Axes = self._axes()
        result = Gen.generate_narrative(Axes.TIMING, "reaction", -0.5)
        assert len(result) > 10

    def test_decision_positive(self):
        Gen = self._gen()
        Axes = self._axes()
        result = Gen.generate_narrative(Axes.DECISION, "kast", 0.9)
        assert "elite" in result.lower() or "kast" in result.lower()

    def test_unknown_category(self):
        Gen = self._gen()
        result = Gen.generate_narrative("UNKNOWN_CAT", "test_feature", 0.5)
        assert "analysis" in result.lower()

    def test_low_skill_level_negative_simplifies(self):
        Gen = self._gen()
        Axes = self._axes()
        result = Gen.generate_narrative(Axes.MECHANICS, "avg_kills", -0.5, skill_level=2)
        assert "Goal" in result

    def test_classify_severity_high(self):
        from Programma_CS2_RENAN.backend.coaching.explainability import ExplanationGenerator
        assert ExplanationGenerator.classify_insight_severity(2.0) == "High"

    def test_classify_severity_medium(self):
        from Programma_CS2_RENAN.backend.coaching.explainability import ExplanationGenerator
        assert ExplanationGenerator.classify_insight_severity(1.0) == "Medium"

    def test_classify_severity_low(self):
        from Programma_CS2_RENAN.backend.coaching.explainability import ExplanationGenerator
        assert ExplanationGenerator.classify_insight_severity(0.3) == "Low"

    def test_classify_severity_negative(self):
        from Programma_CS2_RENAN.backend.coaching.explainability import ExplanationGenerator
        assert ExplanationGenerator.classify_insight_severity(-2.0) == "High"

    def test_constants(self):
        from Programma_CS2_RENAN.backend.coaching.explainability import (
            SEVERITY_HIGH_BOUNDARY,
            SEVERITY_MEDIUM_BOUNDARY,
            SILENCE_THRESHOLD,
        )
        assert SILENCE_THRESHOLD == 0.2
        assert SEVERITY_HIGH_BOUNDARY == 1.5
        assert SEVERITY_MEDIUM_BOUNDARY == 0.8


# ---------------------------------------------------------------------------
# PlayerCardAssimilator (pro_bridge.py)
# ---------------------------------------------------------------------------
class TestPlayerCardAssimilator:
    """Tests for the Pro Cognitive Bridge."""

    def _make_card(self, **kwargs):
        card = MagicMock()
        card.kpr = kwargs.get("kpr", 0.75)
        card.dpr = kwargs.get("dpr", 0.60)
        card.adr = kwargs.get("adr", 85.0)
        card.kast = kwargs.get("kast", 0.72)
        card.impact = kwargs.get("impact", 1.1)
        card.rating_2_0 = kwargs.get("rating_2_0", 1.15)
        card.detailed_stats_json = kwargs.get("detailed_stats_json", '{}')
        return card

    def test_init_valid_json(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(detailed_stats_json='{"core": {"headshot_pct": 0.55}}')
        assimilator = PlayerCardAssimilator(card)
        assert assimilator.details["core"]["headshot_pct"] == 0.55

    def test_init_invalid_json(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(detailed_stats_json="INVALID JSON")
        assimilator = PlayerCardAssimilator(card)
        assert assimilator.details == {}

    def test_init_none_json(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(detailed_stats_json=None)
        assimilator = PlayerCardAssimilator(card)
        assert assimilator.details == {}

    def test_get_coach_baseline_keys(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card()
        baseline = PlayerCardAssimilator(card).get_coach_baseline()
        assert "avg_kills" in baseline
        assert "avg_deaths" in baseline
        assert "avg_adr" in baseline
        assert "rating" in baseline

    def test_get_coach_baseline_values(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import (
            ESTIMATED_ROUNDS_PER_MATCH,
            PlayerCardAssimilator,
        )
        card = self._make_card(kpr=0.75, dpr=0.60, adr=85.0)
        baseline = PlayerCardAssimilator(card).get_coach_baseline()
        assert baseline["avg_kills"] == pytest.approx(0.75 * ESTIMATED_ROUNDS_PER_MATCH)
        assert baseline["avg_deaths"] == pytest.approx(0.60 * ESTIMATED_ROUNDS_PER_MATCH)
        assert baseline["avg_adr"] == 85.0

    def test_kd_ratio_zero_dpr(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(kpr=0.80, dpr=0.0)
        baseline = PlayerCardAssimilator(card).get_coach_baseline()
        assert baseline["kd_ratio"] == 0.80

    def test_extract_hs_ratio_from_details(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(detailed_stats_json='{"core": {"headshot_pct": 0.58}}')
        assimilator = PlayerCardAssimilator(card)
        assert assimilator._extract_hs_ratio() == 0.58

    def test_extract_hs_ratio_default(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card()
        assimilator = PlayerCardAssimilator(card)
        assert assimilator._extract_hs_ratio() == 0.45

    def test_map_detailed_metrics_with_data(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(
            detailed_stats_json='{"individual": {"total_opening_kills": "150", "utility_damage_per_round": "52.3"}}'
        )
        metrics = PlayerCardAssimilator(card)._map_detailed_metrics()
        assert "entry_rate" in metrics
        assert "utility_damage" in metrics
        assert metrics["utility_damage"] == pytest.approx(52.3)

    def test_map_detailed_metrics_invalid_values(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(
            detailed_stats_json='{"individual": {"total_opening_kills": "INVALID", "utility_damage_per_round": "bad"}}'
        )
        metrics = PlayerCardAssimilator(card)._map_detailed_metrics()
        assert metrics["entry_rate"] == 0.25
        assert metrics["utility_damage"] == 45.0

    def test_archetype_star_fragger(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(impact=1.4)
        assert PlayerCardAssimilator(card).get_player_archetype() == "Star Fragger"

    def test_archetype_support_anchor(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(impact=1.0, kast=0.80)
        assert PlayerCardAssimilator(card).get_player_archetype() == "Support Anchor"

    def test_archetype_awper(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(
            impact=1.0, kast=0.70,
            detailed_stats_json='{"weapons": {"AWP": 500, "AK-47": 200, "M4A4": 100}}'
        )
        assert PlayerCardAssimilator(card).get_player_archetype() == "Sniper Specialist"

    def test_archetype_all_rounder(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card(impact=1.0, kast=0.70)
        assert PlayerCardAssimilator(card).get_player_archetype() == "All-Rounder"

    def test_is_awper_no_weapons(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import PlayerCardAssimilator
        card = self._make_card()
        assert PlayerCardAssimilator(card)._is_awper() is False

    def test_factory_function(self):
        from Programma_CS2_RENAN.backend.coaching.pro_bridge import get_pro_baseline_for_coach
        card = self._make_card()
        baseline = get_pro_baseline_for_coach(card)
        assert isinstance(baseline, dict)
        assert "rating" in baseline


# ---------------------------------------------------------------------------
# PlayerTokenResolver (token_resolver.py) — pure helpers, no DB
# ---------------------------------------------------------------------------
class TestTokenResolverHelpers:
    """Tests for PlayerTokenResolver helpers without DB."""

    def _make_resolver_shell(self):
        from Programma_CS2_RENAN.backend.coaching.token_resolver import PlayerTokenResolver
        resolver = PlayerTokenResolver.__new__(PlayerTokenResolver)
        resolver.db = MagicMock()
        return resolver

    def _make_pro_player(self, nickname="s1mple", real_name="Oleksandr Kostyliev", hltv_id=7998):
        player = MagicMock()
        player.nickname = nickname
        player.real_name = real_name
        player.hltv_id = hltv_id
        return player

    def _make_stat_card(self):
        card = MagicMock()
        card.rating_2_0 = 1.30
        card.adr = 87.5
        card.kast = 0.73
        card.kpr = 0.80
        card.dpr = 0.55
        card.headshot_pct = 0.42
        card.maps_played = 250
        card.opening_duel_win_pct = 0.55
        card.opening_kill_ratio = 1.45
        card.clutch_win_count = 120
        card.multikill_round_pct = 0.18
        card.detailed_stats_json = '{}'
        card.last_updated = MagicMock()
        card.last_updated.isoformat.return_value = "2025-01-15T10:30:00"
        card.time_span = "2024"
        return card

    def test_build_token_dict_structure(self):
        resolver = self._make_resolver_shell()
        player = self._make_pro_player()
        card = self._make_stat_card()
        token = resolver._build_token_dict(player, card)
        assert "identity" in token
        assert "core_metrics" in token
        assert "tactical_baselines" in token
        assert "granular_data" in token
        assert "metadata" in token

    def test_build_token_dict_identity(self):
        resolver = self._make_resolver_shell()
        player = self._make_pro_player(nickname="ZywOo")
        card = self._make_stat_card()
        token = resolver._build_token_dict(player, card)
        assert token["identity"]["name"] == "ZywOo"

    def test_build_token_dict_malformed_json(self):
        resolver = self._make_resolver_shell()
        player = self._make_pro_player()
        card = self._make_stat_card()
        card.detailed_stats_json = "NOT_JSON"
        token = resolver._build_token_dict(player, card)
        assert token["granular_data"] == {}

    def test_compare_performance_to_token(self):
        resolver = self._make_resolver_shell()
        player = self._make_pro_player()
        card = self._make_stat_card()
        token = resolver._build_token_dict(player, card)
        match_stats = {"rating": 1.05, "avg_adr": 75.0, "avg_kast": 0.68, "avg_hs": 0.38}
        comparison = resolver.compare_performance_to_token(match_stats, token)
        assert "player" in comparison
        assert "deltas" in comparison
        assert "is_underperforming" in comparison
        assert comparison["deltas"]["rating"] == pytest.approx(1.05 - 1.30)

    def test_compare_underperforming(self):
        resolver = self._make_resolver_shell()
        player = self._make_pro_player()
        card = self._make_stat_card()
        token = resolver._build_token_dict(player, card)
        match_stats = {"rating": 0.80}
        comparison = resolver.compare_performance_to_token(match_stats, token)
        assert comparison["is_underperforming"] is True

    def test_compare_not_underperforming(self):
        resolver = self._make_resolver_shell()
        player = self._make_pro_player()
        card = self._make_stat_card()
        token = resolver._build_token_dict(player, card)
        match_stats = {"rating": 1.25}
        comparison = resolver.compare_performance_to_token(match_stats, token)
        assert comparison["is_underperforming"] is False


# ---------------------------------------------------------------------------
# apply_nn_refinement (nn_refinement.py)
# ---------------------------------------------------------------------------
class TestNNRefinement:
    """Tests for NN refinement of corrections."""

    def test_basic_refinement(self):
        from Programma_CS2_RENAN.backend.coaching.nn_refinement import apply_nn_refinement
        corrections = [{"feature": "avg_adr", "weighted_z": 1.0}]
        nn_adj = {"avg_adr_weight": 0.5}
        result = apply_nn_refinement(corrections, nn_adj)
        assert len(result) == 1
        assert result[0]["weighted_z"] == pytest.approx(1.5)

    def test_no_matching_adjustment(self):
        from Programma_CS2_RENAN.backend.coaching.nn_refinement import apply_nn_refinement
        corrections = [{"feature": "avg_hs", "weighted_z": 2.0}]
        nn_adj = {"avg_adr_weight": 0.5}
        result = apply_nn_refinement(corrections, nn_adj)
        assert result[0]["weighted_z"] == pytest.approx(2.0)

    def test_multiple_corrections(self):
        from Programma_CS2_RENAN.backend.coaching.nn_refinement import apply_nn_refinement
        corrections = [
            {"feature": "avg_adr", "weighted_z": 1.0},
            {"feature": "avg_hs", "weighted_z": -0.5},
        ]
        nn_adj = {"avg_adr_weight": 0.2, "avg_hs_weight": -0.3}
        result = apply_nn_refinement(corrections, nn_adj)
        assert result[0]["weighted_z"] == pytest.approx(1.2)
        assert result[1]["weighted_z"] == pytest.approx(-0.5 * 0.7)

    def test_preserves_other_fields(self):
        from Programma_CS2_RENAN.backend.coaching.nn_refinement import apply_nn_refinement
        corrections = [{"feature": "avg_adr", "weighted_z": 1.0, "extra": "data"}]
        result = apply_nn_refinement(corrections, {})
        assert result[0]["extra"] == "data"


# ---------------------------------------------------------------------------
# correction_engine.py
# ---------------------------------------------------------------------------
class TestCorrectionEngine:
    """Tests for the correction engine."""

    def test_get_feature_importance_default(self):
        from Programma_CS2_RENAN.backend.coaching.correction_engine import get_feature_importance
        assert get_feature_importance("avg_kast") == 1.5

    def test_get_feature_importance_unknown(self):
        from Programma_CS2_RENAN.backend.coaching.correction_engine import get_feature_importance
        assert get_feature_importance("nonexistent") == 1.0

    def test_generate_corrections_basic(self):
        from Programma_CS2_RENAN.backend.coaching.correction_engine import generate_corrections
        deviations = {"avg_adr": 1.5, "avg_hs": -0.8, "avg_kast": 2.0, "accuracy": 0.3}
        result = generate_corrections(deviations, rounds_played=300)
        assert len(result) <= 3
        assert all("feature" in c for c in result)
        assert all("weighted_z" in c for c in result)

    def test_generate_corrections_sorted_by_importance(self):
        from Programma_CS2_RENAN.backend.coaching.correction_engine import generate_corrections
        deviations = {"avg_adr": 1.0, "avg_kast": 1.0}
        result = generate_corrections(deviations, rounds_played=300)
        # Both have same z but different importance, should be sorted
        assert len(result) == 2

    def test_generate_corrections_confidence_scaling(self):
        from Programma_CS2_RENAN.backend.coaching.correction_engine import generate_corrections
        # 150 rounds / 300 ceiling = 0.5 confidence
        result_low = generate_corrections({"avg_adr": 1.0}, rounds_played=150)
        result_high = generate_corrections({"avg_adr": 1.0}, rounds_played=300)
        assert abs(result_low[0]["weighted_z"]) < abs(result_high[0]["weighted_z"])

    def test_generate_corrections_tuple_input(self):
        from Programma_CS2_RENAN.backend.coaching.correction_engine import generate_corrections
        deviations = {"avg_adr": (1.5, 10.0)}
        result = generate_corrections(deviations, rounds_played=300)
        # Should use the first element of the tuple
        assert result[0]["weighted_z"] == pytest.approx(1.5)

    def test_generate_corrections_with_nn(self):
        from Programma_CS2_RENAN.backend.coaching.correction_engine import generate_corrections
        deviations = {"avg_adr": 1.0}
        nn_adj = {"avg_adr_weight": 0.5}
        result = generate_corrections(deviations, rounds_played=300, nn_adjustments=nn_adj)
        # Should be refined: 1.0 * (1 + 0.5) = 1.5
        assert result[0]["weighted_z"] == pytest.approx(1.5)

    def test_confidence_ceiling(self):
        from Programma_CS2_RENAN.backend.coaching.correction_engine import CONFIDENCE_ROUNDS_CEILING
        assert CONFIDENCE_ROUNDS_CEILING == 300


# ---------------------------------------------------------------------------
# longitudinal_engine.py
# ---------------------------------------------------------------------------
class TestLongitudinalEngine:
    """Tests for the longitudinal coaching engine."""

    def _make_trend(self, feature="avg_adr", slope=-0.5, confidence=0.8):
        t = MagicMock()
        t.feature = feature
        t.slope = slope
        t.confidence = confidence
        return t

    def test_regression_insight(self):
        from Programma_CS2_RENAN.backend.coaching.longitudinal_engine import generate_longitudinal_coaching
        trends = [self._make_trend(slope=-0.5, confidence=0.8)]
        result = generate_longitudinal_coaching(trends, {})
        assert len(result) == 1
        assert "Regression" in result[0]["title"]
        assert result[0]["severity"] == "Medium"

    def test_improvement_insight(self):
        from Programma_CS2_RENAN.backend.coaching.longitudinal_engine import generate_longitudinal_coaching
        trends = [self._make_trend(slope=0.5, confidence=0.8)]
        result = generate_longitudinal_coaching(trends, {})
        assert len(result) == 1
        assert "Improvement" in result[0]["title"]
        assert result[0]["severity"] == "Positive"

    def test_low_confidence_filtered(self):
        from Programma_CS2_RENAN.backend.coaching.longitudinal_engine import generate_longitudinal_coaching
        trends = [self._make_trend(confidence=0.3)]
        result = generate_longitudinal_coaching(trends, {})
        assert len(result) == 0

    def test_stability_warning_upgrades_severity(self):
        from Programma_CS2_RENAN.backend.coaching.longitudinal_engine import generate_longitudinal_coaching
        trends = [self._make_trend(slope=-0.5, confidence=0.8)]
        result = generate_longitudinal_coaching(trends, {"stability_warning": True})
        assert result[0]["severity"] == "High"

    def test_max_three_insights(self):
        from Programma_CS2_RENAN.backend.coaching.longitudinal_engine import generate_longitudinal_coaching
        trends = [self._make_trend(feature=f"stat_{i}", slope=-0.5) for i in range(10)]
        result = generate_longitudinal_coaching(trends, {})
        assert len(result) <= 3

    def test_empty_trends(self):
        from Programma_CS2_RENAN.backend.coaching.longitudinal_engine import generate_longitudinal_coaching
        result = generate_longitudinal_coaching([], {})
        assert result == []

    def test_zero_slope_no_insight(self):
        from Programma_CS2_RENAN.backend.coaching.longitudinal_engine import generate_longitudinal_coaching
        trends = [self._make_trend(slope=0.0, confidence=0.9)]
        result = generate_longitudinal_coaching(trends, {})
        assert len(result) == 0
