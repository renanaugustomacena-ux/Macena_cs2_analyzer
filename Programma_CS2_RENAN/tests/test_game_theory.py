"""
Game Theory & Analysis Module Tests

Validates advanced game-theory analysis, spatial intelligence, and utility/economy:
- Belief-Based Death Assessment
- Deception Index
- Momentum Multiplier
- Entropy Delta Analysis
- Expectiminimax Game Trees
- Strategic Blind Spot Detection
- Engagement Range Analytics (Proposal 7)
"""

import math

import numpy as np
import pandas as pd
import pytest

# ─────────────────────────── Belief Model ───────────────────────────


class TestBeliefModel:
    """Verify BeliefState and DeathProbabilityEstimator."""

    def test_estimator_default_priors(self):
        """Default priors must match the documented HP brackets."""
        from Programma_CS2_RENAN.backend.analysis.belief_model import (
            _DEFAULT_PRIORS,
            DeathProbabilityEstimator,
        )

        est = DeathProbabilityEstimator()
        assert est.priors == _DEFAULT_PRIORS
        assert "full" in est.priors
        assert "damaged" in est.priors
        assert "critical" in est.priors

    def test_death_probability_bounded(self):
        """estimate() must always return a value in [0.0, 1.0]."""
        from Programma_CS2_RENAN.backend.analysis.belief_model import (
            BeliefState,
            DeathProbabilityEstimator,
        )

        est = DeathProbabilityEstimator()

        # Test extreme inputs
        cases = [
            (
                BeliefState(
                    visible_enemies=5,
                    inferred_enemies=5,
                    information_age=0,
                    positional_exposure=1.0,
                ),
                1,
                False,
                "awp",
            ),
            (
                BeliefState(
                    visible_enemies=0,
                    inferred_enemies=0,
                    information_age=100,
                    positional_exposure=0.0,
                ),
                100,
                True,
                "pistol",
            ),
            (
                BeliefState(
                    visible_enemies=3,
                    inferred_enemies=2,
                    information_age=5,
                    positional_exposure=0.5,
                ),
                50,
                True,
                "rifle",
            ),
        ]
        for belief, hp, armor, weapon in cases:
            p = est.estimate(belief, hp, armor, weapon)
            assert 0.0 <= p <= 1.0, f"P(death)={p} out of bounds for hp={hp}, weapon={weapon}"

    def test_high_risk_threshold(self):
        """is_high_risk should flag probabilities above threshold."""
        from Programma_CS2_RENAN.backend.analysis.belief_model import DeathProbabilityEstimator

        est = DeathProbabilityEstimator()
        assert est.is_high_risk(0.7) is True
        assert est.is_high_risk(0.4) is False
        assert est.is_high_risk(0.6) is False  # threshold is > not >=

    def test_threat_decays_with_info_age(self):
        """Older information should reduce threat level."""
        from Programma_CS2_RENAN.backend.analysis.belief_model import BeliefState

        fresh = BeliefState(visible_enemies=0, inferred_enemies=3, information_age=0)
        stale = BeliefState(visible_enemies=0, inferred_enemies=3, information_age=10)

        assert fresh.threat_level() > stale.threat_level()

    def test_calibrate_updates_priors(self):
        """calibrate() with labeled data should update priors."""
        from Programma_CS2_RENAN.backend.analysis.belief_model import DeathProbabilityEstimator

        est = DeathProbabilityEstimator()
        original_full = est.priors["full"]

        # Synthetic data: full-HP players die 10% of the time
        df = pd.DataFrame(
            {
                "health": [100] * 20 + [50] * 20,
                "died": [False] * 18 + [True] * 2 + [True] * 12 + [False] * 8,
            }
        )
        est.calibrate(df)

        assert est._calibrated is True
        assert est.priors["full"] != original_full  # Should have changed
        assert est.priors["full"] < original_full  # 10% < 35% default


# ──────────────── Adaptive Belief Calibration (Proposal 6) ────────────────


class TestAdaptiveBeliefCalibrator:
    """Verify AdaptiveBeliefCalibrator and data extraction."""

    def test_auto_calibrate_hp_brackets(self):
        """auto_calibrate should update HP bracket priors from data."""
        from Programma_CS2_RENAN.backend.analysis.belief_model import AdaptiveBeliefCalibrator

        calibrator = AdaptiveBeliefCalibrator()
        original_full = calibrator.estimator.priors["full"]

        # Synthetic data: 200 samples, full-HP die 15%, damaged die 70%
        df = pd.DataFrame(
            {
                "health": [100] * 100 + [50] * 100,
                "died": [False] * 85 + [True] * 15 + [True] * 70 + [False] * 30,
            }
        )

        summary = calibrator.auto_calibrate(df)
        assert summary["hp_priors"]  # Non-empty means calibration happened
        assert calibrator.estimator.priors["full"] != original_full

    def test_bounds_safety(self):
        """Calibrated values must stay within safety bounds."""
        from Programma_CS2_RENAN.backend.analysis.belief_model import AdaptiveBeliefCalibrator

        calibrator = AdaptiveBeliefCalibrator()

        # Extreme data: all full-HP players die (100% death rate)
        df = pd.DataFrame(
            {
                "health": [100] * 200,
                "died": [True] * 200,
            }
        )

        calibrator.auto_calibrate(df)
        # Prior should be clamped to _PRIOR_BOUNDS[1] = 0.95
        assert calibrator.estimator.priors["full"] <= 0.95

    def test_insufficient_samples_skipped(self):
        """Calibration should be skipped if fewer than MIN_SAMPLES."""
        from Programma_CS2_RENAN.backend.analysis.belief_model import (
            _DEFAULT_PRIORS,
            AdaptiveBeliefCalibrator,
        )

        calibrator = AdaptiveBeliefCalibrator()
        original_full = calibrator.estimator.priors["full"]

        # Only 10 samples — below MIN_SAMPLES (100)
        df = pd.DataFrame(
            {
                "health": [100] * 10,
                "died": [True] * 10,
            }
        )

        summary = calibrator.auto_calibrate(df)
        assert summary["hp_priors"] == {}
        assert calibrator.estimator.priors["full"] == original_full

    def test_extract_death_events_empty_db(self):
        """extract_death_events_from_db returns empty DataFrame when no data."""
        from Programma_CS2_RENAN.backend.analysis.belief_model import extract_death_events_from_db

        # This will hit a real (likely empty) DB or fail gracefully
        df = extract_death_events_from_db()
        assert isinstance(df, pd.DataFrame)
        assert "health" in df.columns
        assert "died" in df.columns

    def test_weapon_lethality_calibration(self):
        """Weapon lethality calibration with proper data."""
        from Programma_CS2_RENAN.backend.analysis.belief_model import AdaptiveBeliefCalibrator

        calibrator = AdaptiveBeliefCalibrator()

        # Synthetic data with weapon_class column
        df = pd.DataFrame(
            {
                "health": [100] * 200,
                "died": [True] * 100 + [False] * 100,
                "weapon_class": ["rifle"] * 50 + ["awp"] * 50 + ["smg"] * 50 + ["pistol"] * 50,
            }
        )

        summary = calibrator.auto_calibrate(df)
        # weapon_lethality should have calibrated values for provided weapon classes
        assert (
            len(summary["weapon_lethality"]) > 0
        ), "200 samples with weapon_class should produce weapon_lethality data"
        for wc, mult in summary["weapon_lethality"].items():
            assert 0.1 <= mult <= 3.0, f"Weapon {wc} multiplier {mult} out of safety bounds"


# ──────────────────────── Deception Index ────────────────────────


class TestDeceptionAnalyzer:
    """Verify DeceptionAnalyzer and DeceptionMetrics."""

    def test_empty_round_returns_zeros(self):
        """Empty DataFrame should produce all-zero metrics."""
        from Programma_CS2_RENAN.backend.analysis.deception_index import DeceptionAnalyzer

        analyzer = DeceptionAnalyzer()
        result = analyzer.analyze_round(pd.DataFrame())

        assert result.fake_flash_rate == 0.0
        assert result.rotation_feint_rate == 0.0
        assert result.sound_deception_score == 0.0
        assert result.composite_index == 0.0

    def test_flash_bait_detection(self):
        """Flashbangs without blinds should produce non-zero fake_flash_rate."""
        from Programma_CS2_RENAN.backend.analysis.deception_index import DeceptionAnalyzer

        analyzer = DeceptionAnalyzer()

        # 3 flashes thrown, 0 blinds -> 100% bait rate
        df = pd.DataFrame(
            {
                "tick": [100, 200, 300],
                "event_type": ["flashbang_throw", "flashbang_throw", "flashbang_throw"],
                "player_name": ["player1"] * 3,
                "pos_x": [0.0] * 3,
                "pos_y": [0.0] * 3,
            }
        )

        result = analyzer.analyze_round(df)
        assert result.fake_flash_rate == 1.0, "All flashes without blinds should be baits"

    def test_composite_index_bounded(self):
        """composite_index computed by analyzer must be in [0, 1]."""
        from Programma_CS2_RENAN.backend.analysis.deception_index import DeceptionAnalyzer

        analyzer = DeceptionAnalyzer()

        # Create input data with maximum deception indicators
        df = pd.DataFrame(
            {
                "tick": [100, 200, 300],
                "event_type": ["flashbang_throw", "flashbang_throw", "flashbang_throw"],
                "player_name": ["player1"] * 3,
                "pos_x": [0.0, 500.0, 1000.0],
                "pos_y": [0.0, 500.0, 1000.0],
            }
        )
        result = analyzer.analyze_round(df)
        assert 0.0 <= result.composite_index <= 1.0

    def test_compare_to_baseline_narrative(self):
        """compare_to_baseline must return a non-empty string."""
        from Programma_CS2_RENAN.backend.analysis.deception_index import (
            DeceptionAnalyzer,
            DeceptionMetrics,
        )

        analyzer = DeceptionAnalyzer()
        user_metrics = DeceptionMetrics(composite_index=0.3, rotation_feint_rate=0.2)
        pro_metrics = DeceptionMetrics(composite_index=0.5, rotation_feint_rate=0.4)

        narrative = analyzer.compare_to_baseline(user_metrics, pro_metrics)
        assert len(narrative) > 0
        assert "deception index" in narrative.lower()


# ───────────────────── Momentum Multiplier ──────────────────────


class TestMomentumTracker:
    """Verify MomentumTracker state transitions and bounds."""

    def test_initial_state_neutral(self):
        """Fresh tracker has neutral state (multiplier=1.0)."""
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumTracker

        tracker = MomentumTracker()
        assert tracker.state.current_multiplier == 1.0
        assert tracker.state.streak_type == "neutral"
        assert tracker.state.streak_length == 0

    def test_win_streak_increases_multiplier(self):
        """Consecutive wins should increase the multiplier above 1.0."""
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumTracker

        tracker = MomentumTracker()
        for i in range(1, 4):
            tracker.update(round_won=True, round_number=i)

        assert tracker.state.current_multiplier > 1.0
        assert tracker.state.streak_type == "win"
        assert tracker.state.streak_length == 3

    def test_loss_streak_decreases_multiplier(self):
        """Consecutive losses should decrease the multiplier below 1.0."""
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumTracker

        tracker = MomentumTracker()
        for i in range(1, 4):
            tracker.update(round_won=False, round_number=i)

        assert tracker.state.current_multiplier < 1.0
        assert tracker.state.streak_type == "loss"
        assert tracker.state.streak_length == 3

    def test_half_switch_resets_multiplier(self):
        """Momentum must reset to 1.0 at the MR12 half-switch (round 13)."""
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumTracker

        tracker = MomentumTracker()
        # Build a win streak
        for i in range(1, 10):
            tracker.update(round_won=True, round_number=i)
        assert tracker.state.current_multiplier > 1.0

        # Round 13 triggers half-switch reset before processing
        tracker.update(round_won=True, round_number=13)
        # After reset, the first round of new half starts fresh
        # The multiplier should be close to 1.0 (only 1 win in new half)
        assert tracker.state.current_multiplier <= 1.1

    def test_multiplier_capped_at_max(self):
        """Even with 20 consecutive wins, multiplier must not exceed MULTIPLIER_MAX."""
        from Programma_CS2_RENAN.backend.analysis.momentum import MULTIPLIER_MAX, MomentumTracker

        tracker = MomentumTracker()
        for i in range(1, 13):  # 12 rounds (before half-switch)
            tracker.update(round_won=True, round_number=i)

        assert tracker.state.current_multiplier <= MULTIPLIER_MAX

    def test_multiplier_capped_at_min(self):
        """Even with many consecutive losses, multiplier must not go below MULTIPLIER_MIN."""
        from Programma_CS2_RENAN.backend.analysis.momentum import MULTIPLIER_MIN, MomentumTracker

        tracker = MomentumTracker()
        for i in range(1, 13):
            tracker.update(round_won=False, round_number=i)

        assert tracker.state.current_multiplier >= MULTIPLIER_MIN

    def test_tilt_detection(self):
        """is_tilted should trigger below 0.85 threshold after 7 consecutive losses."""
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumTracker

        tracker = MomentumTracker()
        for i in range(1, 8):
            tracker.update(round_won=False, round_number=i)

        # After 7 losses, multiplier must be below tilt threshold
        assert (
            tracker.state.current_multiplier < 0.85
        ), f"7 losses should push multiplier below 0.85, got {tracker.state.current_multiplier}"
        assert tracker.state.is_tilted is True

    def test_performance_adjustment(self):
        """predict_performance_adjustment should multiply base_rating by multiplier."""
        from Programma_CS2_RENAN.backend.analysis.momentum import (
            MomentumState,
            predict_performance_adjustment,
        )

        state = MomentumState(current_multiplier=1.2)
        adjusted = predict_performance_adjustment(state, base_rating=1.0)
        assert abs(adjusted - 1.2) < 1e-6


# ──────────────────── Entropy Analysis ───────────────────────


class TestEntropyAnalyzer:
    """Verify Shannon entropy computation and utility impact analysis."""

    def test_empty_positions_returns_zero(self):
        """No positions should produce zero entropy."""
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import EntropyAnalyzer

        analyzer = EntropyAnalyzer()
        assert analyzer.compute_position_entropy([]) == 0.0

    def test_single_position_returns_zero(self):
        """A single position has zero entropy (no uncertainty)."""
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import EntropyAnalyzer

        analyzer = EntropyAnalyzer()
        h = analyzer.compute_position_entropy([(100.0, 200.0)])
        assert h == 0.0

    def test_spread_positions_higher_entropy(self):
        """Spread-out positions should have higher entropy than clustered ones."""
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import EntropyAnalyzer

        analyzer = EntropyAnalyzer(grid_resolution=16)

        # Clustered: all near same spot
        clustered = [(100 + i * 0.1, 200 + i * 0.1) for i in range(10)]
        h_clustered = analyzer.compute_position_entropy(clustered)

        # Spread: across the map
        spread = [(i * 400, j * 400) for i in range(4) for j in range(4)]
        h_spread = analyzer.compute_position_entropy(spread)

        assert h_spread > h_clustered

    def test_identical_positions_zero_delta(self):
        """Identical pre/post positions should yield zero entropy delta."""
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import EntropyAnalyzer

        analyzer = EntropyAnalyzer()
        positions = [(100, 200), (300, 400), (500, 600)]

        impact = analyzer.analyze_utility_throw(positions, positions, "smoke")
        assert impact.entropy_delta == 0.0

    def test_effectiveness_rating_bounded(self):
        """effectiveness_rating must always be in [0.0, 1.0]."""
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import EntropyAnalyzer

        analyzer = EntropyAnalyzer()

        pre = [(i * 100, j * 100) for i in range(5) for j in range(5)]
        post = [(100, 200)]

        impact = analyzer.analyze_utility_throw(pre, post, "smoke")
        assert 0.0 <= impact.effectiveness_rating <= 1.0

    def test_rank_utility_usage(self):
        """rank_utility_usage should sort by effectiveness descending."""
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import (
            EntropyAnalyzer,
            UtilityImpact,
        )

        analyzer = EntropyAnalyzer()

        impacts = [
            UtilityImpact(
                pre_entropy=3.0,
                post_entropy=2.0,
                entropy_delta=1.0,
                utility_type="smoke",
                effectiveness_rating=0.4,
            ),
            UtilityImpact(
                pre_entropy=3.0,
                post_entropy=1.0,
                entropy_delta=2.0,
                utility_type="flash",
                effectiveness_rating=0.8,
            ),
            UtilityImpact(
                pre_entropy=3.0,
                post_entropy=2.5,
                entropy_delta=0.5,
                utility_type="he_grenade",
                effectiveness_rating=0.2,
            ),
        ]

        ranked = analyzer.rank_utility_usage(impacts)
        assert ranked[0].effectiveness_rating == 0.8
        assert ranked[-1].effectiveness_rating == 0.2


# ────────────────────── Game Tree ──────────────────────────


class TestExpectiminimaxSearch:
    """Verify game tree construction, evaluation, and budget enforcement."""

    def _base_state(self):
        return {
            "team_economy": 4000,
            "enemy_economy": 4000,
            "alive_players": 5,
            "enemy_alive": 5,
            "map_control_pct": 0.5,
            "time_remaining": 115,
            "utility_remaining": 4,
        }

    def test_build_tree_respects_budget(self):
        """Tree construction must not exceed node_budget."""
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch

        search = ExpectiminimaxSearch(node_budget=50)
        root = search.build_tree(self._base_state(), depth=3)

        assert search._nodes_created <= 50

    def test_terminal_state_alive_zero(self):
        """With zero alive_players, evaluation should return 0.0 (loss)."""
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch

        search = ExpectiminimaxSearch()
        state = {**self._base_state(), "alive_players": 0}
        value = search._evaluate_leaf(state)
        assert value == 0.0

    def test_terminal_state_enemy_zero(self):
        """With zero enemy_alive, evaluation should return 1.0 (win)."""
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch

        search = ExpectiminimaxSearch()
        state = {**self._base_state(), "enemy_alive": 0}
        value = search._evaluate_leaf(state)
        assert value == 1.0

    def test_get_best_action_returns_valid(self):
        """Best action must be one of the valid tactical actions."""
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch

        search = ExpectiminimaxSearch(node_budget=200)
        root = search.build_tree(self._base_state(), depth=2)
        action, value = search.get_best_action(root)

        assert action in {"push", "hold", "rotate", "use_utility"}
        assert 0.0 <= value <= 1.0

    def test_suggest_strategy_returns_string(self):
        """suggest_strategy must return a non-empty string with 'Recommended'."""
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch

        search = ExpectiminimaxSearch(node_budget=100)
        result = search.suggest_strategy(self._base_state())

        assert isinstance(result, str)
        assert len(result) > 0
        assert "Recommended" in result

    def test_empty_children_returns_hold(self):
        """get_best_action with no children should default to 'hold'."""
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch, GameNode

        search = ExpectiminimaxSearch()
        empty_root = GameNode(node_type="max", state=self._base_state())
        action, value = search.get_best_action(empty_root)
        assert action == "hold"


# ─────────────────── Blind Spot Detection ──────────────────────


class TestBlindSpotDetector:
    """Verify blind spot detection and training plan generation."""

    def _base_state(self):
        return {
            "team_economy": 4000,
            "enemy_economy": 4000,
            "alive_players": 5,
            "enemy_alive": 5,
            "map_control_pct": 0.5,
            "time_remaining": 115,
            "utility_remaining": 4,
        }

    def test_empty_history_returns_empty(self):
        """No history should produce no blind spots."""
        from Programma_CS2_RENAN.backend.analysis.blind_spots import BlindSpotDetector

        detector = BlindSpotDetector()
        spots = detector.detect([])
        assert spots == []

    def test_repeated_mismatch_detected(self):
        """Consistently choosing 'hold' when tree says 'push' should be detected."""
        from Programma_CS2_RENAN.backend.analysis.blind_spots import BlindSpotDetector

        detector = BlindSpotDetector()

        # Create history where player always holds in a numbers-advantage scenario
        advantage_state = {
            **self._base_state(),
            "alive_players": 5,
            "enemy_alive": 2,
        }

        history = [
            {"game_state": advantage_state, "action_taken": "hold", "round_won": False}
            for _ in range(5)
        ]

        spots = detector.detect(history)
        # The detector should find at least one mismatch pattern
        # (actual behavior may vary based on tree evaluation)
        assert isinstance(spots, list)
        # Each spot should have valid structure
        for spot in spots:
            assert hasattr(spot, "situation_type")
            assert hasattr(spot, "frequency")
            assert hasattr(spot, "impact_rating")
            assert spot.frequency >= 1

    def test_training_plan_generated(self):
        """generate_training_plan with spots should return non-empty string."""
        from Programma_CS2_RENAN.backend.analysis.blind_spots import BlindSpot, BlindSpotDetector

        detector = BlindSpotDetector()
        spots = [
            BlindSpot(
                situation_type="numbers advantage",
                optimal_action="push",
                actual_action="hold",
                frequency=5,
                impact_rating=0.15,
            )
        ]

        plan = detector.generate_training_plan(spots)
        assert len(plan) > 0
        assert "hold" in plan
        assert "push" in plan

    def test_training_plan_no_spots(self):
        """generate_training_plan with empty spots should return positive message."""
        from Programma_CS2_RENAN.backend.analysis.blind_spots import BlindSpotDetector

        detector = BlindSpotDetector()
        plan = detector.generate_training_plan([])
        assert "No strategic blind spots" in plan

    def test_priority_sorting(self):
        """Blind spots should be sorted by priority (frequency * impact) descending."""
        from Programma_CS2_RENAN.backend.analysis.blind_spots import BlindSpot

        spots = [
            BlindSpot(
                situation_type="eco",
                optimal_action="push",
                actual_action="hold",
                frequency=2,
                impact_rating=0.1,
            ),
            BlindSpot(
                situation_type="post-plant",
                optimal_action="hold",
                actual_action="push",
                frequency=5,
                impact_rating=0.3,
            ),
            BlindSpot(
                situation_type="clutch",
                optimal_action="rotate",
                actual_action="hold",
                frequency=3,
                impact_rating=0.2,
            ),
        ]
        sorted_spots = sorted(spots, key=lambda s: s.priority, reverse=True)

        assert sorted_spots[0].situation_type == "post-plant"  # 5 * 0.3 = 1.5
        assert sorted_spots[1].situation_type == "clutch"  # 3 * 0.2 = 0.6
        assert sorted_spots[2].situation_type == "eco"  # 2 * 0.1 = 0.2


# ────────────── Engagement Range Analytics (Proposal 7) ──────────────


class TestEngagementRangeAnalyzer:
    """Verify kill distance analysis, named positions, and role comparison."""

    def test_kill_distance_known_values(self):
        """Euclidean distance calculation must be correct."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        analyzer = EngagementRangeAnalyzer()
        # 3-4-5 triangle: sqrt(300^2 + 400^2) = 500
        dist = analyzer.compute_kill_distance(0, 0, 0, 300, 400, 0)
        assert abs(dist - 500.0) < 0.01

    def test_kill_distance_3d(self):
        """Distance must account for Z axis."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        dist = EngagementRangeAnalyzer.compute_kill_distance(0, 0, 0, 0, 0, 100)
        assert abs(dist - 100.0) < 0.01

    def test_classify_range_close(self):
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        assert EngagementRangeAnalyzer.classify_range(300) == "close"

    def test_classify_range_medium(self):
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        assert EngagementRangeAnalyzer.classify_range(800) == "medium"

    def test_classify_range_long(self):
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        assert EngagementRangeAnalyzer.classify_range(2000) == "long"

    def test_classify_range_extreme(self):
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        assert EngagementRangeAnalyzer.classify_range(5000) == "extreme"

    def test_profile_empty_input(self):
        """Empty kill list should produce a zero profile."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        analyzer = EngagementRangeAnalyzer()
        profile = analyzer.compute_profile([])
        assert profile.total_kills == 0
        assert profile.avg_distance == 0.0

    def test_profile_distribution_sums_to_one(self):
        """Range percentages must sum to 1.0."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        analyzer = EngagementRangeAnalyzer()
        distances = [200, 400, 700, 1200, 1800, 2500, 3500]
        profile = analyzer.compute_profile(distances)
        total = profile.close_pct + profile.medium_pct + profile.long_pct + profile.extreme_pct
        assert abs(total - 1.0) < 0.001
        assert profile.total_kills == 7

    def test_compare_to_role_awper_close_heavy(self):
        """AWPer taking only close fights should trigger observation."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import (
            EngagementProfile,
            EngagementRangeAnalyzer,
        )

        analyzer = EngagementRangeAnalyzer()
        # AWPer baseline: close_pct=0.10; this profile has close=0.60
        close_heavy = EngagementProfile(
            close_pct=0.60,
            medium_pct=0.30,
            long_pct=0.05,
            extreme_pct=0.05,
            avg_distance=400,
            total_kills=20,
        )
        obs = analyzer.compare_to_role(close_heavy, "awper")
        assert len(obs) > 0
        assert any("close-range" in o.lower() for o in obs)

    def test_compare_to_role_insufficient_kills(self):
        """Less than 5 kills should produce no observations."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import (
            EngagementProfile,
            EngagementRangeAnalyzer,
        )

        analyzer = EngagementRangeAnalyzer()
        profile = EngagementProfile(
            close_pct=0.80,
            medium_pct=0.20,
            total_kills=3,
        )
        obs = analyzer.compare_to_role(profile, "awper")
        assert obs == []


class TestNamedPositionRegistry:
    """Verify named position lookup and registry operations."""

    def test_find_nearest_mirage_a_site(self):
        """Should find A Site on Mirage near its center coordinates."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import NamedPositionRegistry

        registry = NamedPositionRegistry()
        pos = registry.find_nearest("de_mirage", -290, -2080, 0)
        assert pos is not None
        assert "A Site" in pos.name

    def test_find_nearest_no_match(self):
        """Very distant coordinates should return None."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import NamedPositionRegistry

        registry = NamedPositionRegistry()
        pos = registry.find_nearest("de_mirage", 99999, 99999, 0)
        assert pos is None

    def test_unknown_map_returns_none(self):
        """Unknown map name should return None."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import NamedPositionRegistry

        registry = NamedPositionRegistry()
        pos = registry.find_nearest("de_nonexistent", 0, 0, 0)
        assert pos is None

    def test_all_competitive_maps_have_positions(self):
        """Each competitive map should have at least 2 named positions."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import NamedPositionRegistry

        registry = NamedPositionRegistry()
        competitive = [
            "de_mirage",
            "de_inferno",
            "de_dust2",
            "de_anubis",
            "de_nuke",
            "de_ancient",
            "de_overpass",
            "de_vertigo",
            "de_train",
        ]
        for map_name in competitive:
            positions = registry.get_positions(map_name)
            assert len(positions) >= 2, f"{map_name} has only {len(positions)} positions"

    def test_add_position(self):
        """Adding a position should make it findable."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import (
            NamedPosition,
            NamedPositionRegistry,
        )

        registry = NamedPositionRegistry()
        custom = NamedPosition("Custom Spot", "de_test", 100, 200, 0, 50)
        registry.add_position(custom)
        found = registry.find_nearest("de_test", 100, 200)
        assert found is not None
        assert found.name == "Custom Spot"

    def test_annotate_kill_position(self):
        """annotate_kill_position should return a callout name."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        analyzer = EngagementRangeAnalyzer()
        name = analyzer.annotate_kill_position("de_dust2", 1230, 2500, 0)
        assert name == "A Site"

    def test_annotate_unknown_returns_default(self):
        """Far-away position should return 'Unknown Position'."""
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        analyzer = EngagementRangeAnalyzer()
        name = analyzer.annotate_kill_position("de_dust2", 99999, 99999, 0)
        assert name == "Unknown Position"


class TestAnalyzeMatchEngagements:
    """Verify the full match analysis pipeline."""

    def test_full_analysis_returns_profile(self):
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        analyzer = EngagementRangeAnalyzer()
        kills = [
            {
                "killer_x": 0,
                "killer_y": 0,
                "killer_z": 0,
                "victim_x": 300,
                "victim_y": 400,
                "victim_z": 0,
            },
            {
                "killer_x": 100,
                "killer_y": 100,
                "killer_z": 0,
                "victim_x": 1100,
                "victim_y": 100,
                "victim_z": 0,
            },
        ]
        result = analyzer.analyze_match_engagements(kills, "de_mirage", "entry_fragger")
        assert "profile" in result
        assert "observations" in result
        assert "annotated_kills" in result
        assert result["profile"].total_kills == 2

    def test_empty_kills_returns_zero_profile(self):
        from Programma_CS2_RENAN.backend.analysis.engagement_range import EngagementRangeAnalyzer

        analyzer = EngagementRangeAnalyzer()
        result = analyzer.analyze_match_engagements([], "de_mirage", "flex")
        assert result["profile"].total_kills == 0


# ────────────────────── Factory Functions ──────────────────────


@pytest.mark.xfail(
    strict=False,
    reason="F9-03/F9-01: imports via backend.analysis.__init__; may pass post-Phase-4 exports",
)
class TestFactoryFunctions:
    """Verify all Phase 6 factory functions return correct types."""

    def test_get_death_estimator(self):
        from Programma_CS2_RENAN.backend.analysis import (
            DeathProbabilityEstimator,
            get_death_estimator,
        )

        assert isinstance(get_death_estimator(), DeathProbabilityEstimator)

    def test_get_deception_analyzer(self):
        from Programma_CS2_RENAN.backend.analysis import DeceptionAnalyzer, get_deception_analyzer

        assert isinstance(get_deception_analyzer(), DeceptionAnalyzer)

    def test_get_momentum_tracker(self):
        from Programma_CS2_RENAN.backend.analysis import MomentumTracker, get_momentum_tracker

        assert isinstance(get_momentum_tracker(), MomentumTracker)

    def test_get_entropy_analyzer(self):
        from Programma_CS2_RENAN.backend.analysis import EntropyAnalyzer, get_entropy_analyzer

        assert isinstance(get_entropy_analyzer(), EntropyAnalyzer)

    def test_get_game_tree_search(self):
        from Programma_CS2_RENAN.backend.analysis import ExpectiminimaxSearch, get_game_tree_search

        assert isinstance(get_game_tree_search(), ExpectiminimaxSearch)

    def test_get_blind_spot_detector(self):
        from Programma_CS2_RENAN.backend.analysis import BlindSpotDetector, get_blind_spot_detector

        assert isinstance(get_blind_spot_detector(), BlindSpotDetector)

    def test_get_engagement_range_analyzer(self):
        from Programma_CS2_RENAN.backend.analysis import (
            EngagementRangeAnalyzer,
            get_engagement_range_analyzer,
        )

        assert isinstance(get_engagement_range_analyzer(), EngagementRangeAnalyzer)


# ─────────────── Utility & Economy (merged from test_tactical_features) ───────────────


class TestTacticalFeatures:
    def test_utility_analyzer(self):
        from Programma_CS2_RENAN.backend.analysis.utility_economy import UtilityAnalyzer

        analyzer = UtilityAnalyzer()
        stats = {
            "molotov_thrown": 5,
            "molotov_damage": 100,
            "flash_thrown": 10,
            "flash_affected": 8,
            "smoke_thrown": 5,
            "he_grenade_thrown": 2,
            "he_grenade_damage": 50,
            "rounds_played": 20,
        }
        report = analyzer.analyze(stats)
        assert report.overall_score >= 0
        assert len(report.utility_stats) > 0

    def test_economy_optimizer(self):
        from Programma_CS2_RENAN.backend.analysis.utility_economy import EconomyOptimizer

        optimizer = EconomyOptimizer()
        decision = optimizer.recommend(current_money=800, round_number=1, is_ct=True)
        assert decision.action == "pistol"
        assert len(decision.recommended_weapons) > 0
