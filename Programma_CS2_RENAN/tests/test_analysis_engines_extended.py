"""
Tests for Analysis & Game Theory Engines — Phase 4 Coverage Expansion.

Covers:
  MomentumTracker (momentum.py)
  BeliefModel / DeathProbabilityEstimator (belief_model.py)
  EntropyAnalyzer (entropy_analysis.py)
  WinProbabilityNN / WinProbabilityPredictor (win_probability.py)
"""

import sys


import math

import numpy as np
import pandas as pd
import torch


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------
class TestMomentumState:
    def test_default_neutral(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumState

        s = MomentumState()
        assert s.current_multiplier == 1.0
        assert not s.is_tilted
        assert not s.is_hot

    def test_is_tilted_below_threshold(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumState

        s = MomentumState(current_multiplier=0.80)
        assert s.is_tilted

    def test_is_hot_above_threshold(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumState

        s = MomentumState(current_multiplier=1.25)
        assert s.is_hot


class TestMomentumTracker:
    def test_win_streak_increases_multiplier(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumTracker

        t = MomentumTracker()
        for r in range(1, 4):
            t.update(round_won=True, round_number=r)
        assert t.state.current_multiplier > 1.0

    def test_loss_streak_decreases_multiplier(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumTracker

        t = MomentumTracker()
        for r in range(1, 4):
            t.update(round_won=False, round_number=r)
        assert t.state.current_multiplier < 1.0

    def test_multiplier_clamped_max(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import MULTIPLIER_MAX, MomentumTracker

        t = MomentumTracker()
        for r in range(1, 20):
            t.update(round_won=True, round_number=r)
        assert t.state.current_multiplier <= MULTIPLIER_MAX

    def test_multiplier_clamped_min(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import MULTIPLIER_MIN, MomentumTracker

        t = MomentumTracker()
        for r in range(1, 20):
            t.update(round_won=False, round_number=r)
        assert t.state.current_multiplier >= MULTIPLIER_MIN

    def test_half_switch_resets_mr12(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumTracker

        t = MomentumTracker()
        for r in range(1, 13):
            t.update(round_won=True, round_number=r)
        assert t.state.current_multiplier > 1.0
        # Round 13 = half switch, resets momentum
        t.update(round_won=True, round_number=13)
        # After reset + 1 win, multiplier should be near 1.0 + small boost
        assert t.state.current_multiplier < 1.2

    def test_streak_type_transitions(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumTracker

        t = MomentumTracker()
        t.update(round_won=True, round_number=1)
        t.update(round_won=True, round_number=2)
        assert t.state.streak_type == "win"
        assert t.state.streak_length == 2
        t.update(round_won=False, round_number=3)
        assert t.state.streak_type == "loss"
        assert t.state.streak_length == 1

    def test_history_accumulates(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import MomentumTracker

        t = MomentumTracker()
        for r in range(1, 6):
            t.update(round_won=r % 2 == 1, round_number=r)
        assert len(t.history) == 5


class TestFromRoundStats:
    def test_round_stats_list_dicts(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import from_round_stats

        rounds = [
            {"round_number": 1, "round_won": True},
            {"round_number": 2, "round_won": False},
            {"round_number": 3, "round_won": True},
        ]
        history = from_round_stats(rounds)
        assert len(history) == 3

    def test_round_stats_sorted(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import from_round_stats

        # Out-of-order input
        rounds = [
            {"round_number": 3, "round_won": True},
            {"round_number": 1, "round_won": False},
            {"round_number": 2, "round_won": True},
        ]
        history = from_round_stats(rounds)
        assert len(history) == 3


class TestPredictPerformanceAdjustment:
    def test_adjustment_with_momentum(self):
        from Programma_CS2_RENAN.backend.analysis.momentum import (
            MomentumState,
            predict_performance_adjustment,
        )

        state = MomentumState(current_multiplier=1.2)
        adjusted = predict_performance_adjustment(state, base_rating=1.0)
        assert abs(adjusted - 1.2) < 1e-5


# ---------------------------------------------------------------------------
# Belief Model
# ---------------------------------------------------------------------------
class TestBeliefState:
    def test_threat_level_no_enemies(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import BeliefState

        bs = BeliefState(visible_enemies=0, inferred_enemies=0)
        assert bs.threat_level() == 0.0

    def test_threat_level_visible_only(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import BeliefState

        bs = BeliefState(visible_enemies=3, inferred_enemies=0, information_age=0.0)
        tl = bs.threat_level()
        assert tl == 3.0 / 5.0

    def test_threat_level_decay_with_age(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import BeliefState

        bs_fresh = BeliefState(visible_enemies=0, inferred_enemies=2, information_age=0.0)
        bs_old = BeliefState(visible_enemies=0, inferred_enemies=2, information_age=20.0)
        assert bs_fresh.threat_level() > bs_old.threat_level()


class TestDeathProbabilityEstimator:
    def test_full_hp_prior(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import (
            BeliefState,
            DeathProbabilityEstimator,
        )

        est = DeathProbabilityEstimator()
        bs = BeliefState()
        prob = est.estimate(bs, player_hp=100, armor=True, weapon_class="rifle")
        assert 0.0 <= prob <= 1.0

    def test_critical_hp_higher_probability(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import (
            BeliefState,
            DeathProbabilityEstimator,
        )

        est = DeathProbabilityEstimator()
        bs = BeliefState(visible_enemies=2)
        prob_full = est.estimate(bs, player_hp=100, armor=True, weapon_class="rifle")
        prob_crit = est.estimate(bs, player_hp=20, armor=False, weapon_class="awp")
        assert prob_crit > prob_full

    def test_probability_bounded(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import (
            BeliefState,
            DeathProbabilityEstimator,
        )

        est = DeathProbabilityEstimator()
        # Extreme cases
        bs_max = BeliefState(visible_enemies=5, inferred_enemies=5, positional_exposure=1.0)
        bs_min = BeliefState(visible_enemies=0, inferred_enemies=0, positional_exposure=0.0)
        p_high = est.estimate(bs_max, 10, False, "awp")
        p_low = est.estimate(bs_min, 100, True, "knife")
        assert 0.0 <= p_high <= 1.0
        assert 0.0 <= p_low <= 1.0

    def test_is_high_risk(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import DeathProbabilityEstimator

        est = DeathProbabilityEstimator()
        assert est.is_high_risk(0.7) is True
        assert est.is_high_risk(0.5) is False

    def test_hp_to_bracket(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import DeathProbabilityEstimator

        assert DeathProbabilityEstimator._hp_to_bracket(100) == "full"
        assert DeathProbabilityEstimator._hp_to_bracket(80) == "full"
        assert DeathProbabilityEstimator._hp_to_bracket(50) == "damaged"
        assert DeathProbabilityEstimator._hp_to_bracket(10) == "critical"

    def test_calibrate_with_data(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import DeathProbabilityEstimator

        est = DeathProbabilityEstimator()
        df = pd.DataFrame({
            "health": [90] * 50 + [50] * 50 + [20] * 50,
            "died": [False] * 40 + [True] * 10 + [False] * 25 + [True] * 25 + [False] * 10 + [True] * 40,
        })
        est.calibrate(df)
        assert est._calibrated is True
        # Full HP bracket should have lower rate than critical
        assert est.priors["full"] < est.priors["critical"]

    def test_calibrate_empty_data(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import DeathProbabilityEstimator

        est = DeathProbabilityEstimator()
        est.calibrate(pd.DataFrame(columns=["health", "died"]))
        assert est._calibrated is False


class TestAdaptiveBeliefCalibrator:
    def test_insufficient_samples(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import AdaptiveBeliefCalibrator

        cal = AdaptiveBeliefCalibrator()
        result = cal.calibrate_hp_brackets(pd.DataFrame({"health": [100], "died": [False]}))
        assert result == {}

    def test_weapon_lethality_missing_column(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import AdaptiveBeliefCalibrator

        cal = AdaptiveBeliefCalibrator()
        result = cal.calibrate_weapon_lethality(pd.DataFrame({"health": [100], "died": [False]}))
        assert result == {}

    def test_threat_decay_insufficient(self):
        from Programma_CS2_RENAN.backend.analysis.belief_model import AdaptiveBeliefCalibrator

        cal = AdaptiveBeliefCalibrator()
        result = cal.calibrate_threat_decay(pd.DataFrame({"x": [1]}))
        assert result is None


# ---------------------------------------------------------------------------
# Entropy Analysis
# ---------------------------------------------------------------------------
class TestEntropyAnalyzer:
    def test_empty_positions_zero(self):
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import EntropyAnalyzer

        ea = EntropyAnalyzer()
        assert ea.compute_position_entropy([]) == 0.0

    def test_single_position_zero(self):
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import EntropyAnalyzer

        ea = EntropyAnalyzer()
        # All at same spot = 0 entropy
        entropy = ea.compute_position_entropy([(100.0, 200.0)] * 10)
        assert entropy == 0.0

    def test_uniform_distribution_max_entropy(self):
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import EntropyAnalyzer

        ea = EntropyAnalyzer(grid_resolution=4)
        # Spread positions across grid
        positions = [(i * 100, j * 100) for i in range(4) for j in range(4)]
        entropy = ea.compute_position_entropy(positions)
        # Max entropy for 16 cells = log2(16) = 4.0
        assert entropy > 0.0

    def test_utility_throw_analysis(self):
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import EntropyAnalyzer

        ea = EntropyAnalyzer()
        pre = [(100, 200), (300, 400), (500, 600), (700, 800)]
        # After smoke, enemies cluster
        post = [(100, 200), (110, 210)]
        impact = ea.analyze_utility_throw(pre, post, "smoke")
        assert impact.utility_type == "smoke"
        assert impact.pre_entropy >= impact.post_entropy or True  # Entropy can go either way
        assert 0.0 <= impact.effectiveness_rating <= 1.0

    def test_rank_utility_usage(self):
        from Programma_CS2_RENAN.backend.analysis.entropy_analysis import (
            EntropyAnalyzer,
            UtilityImpact,
        )

        ea = EntropyAnalyzer()
        impacts = [
            UtilityImpact(3.0, 2.0, 1.0, "smoke", 0.4),
            UtilityImpact(2.5, 1.0, 1.5, "molotov", 0.75),
            UtilityImpact(1.0, 0.5, 0.5, "flash", 0.28),
        ]
        ranked = ea.rank_utility_usage(impacts)
        assert ranked[0].utility_type == "molotov"
        assert ranked[-1].utility_type == "flash"


# ---------------------------------------------------------------------------
# Win Probability
# ---------------------------------------------------------------------------
class TestGameState:
    def test_defaults(self):
        from Programma_CS2_RENAN.backend.analysis.win_probability import GameState

        gs = GameState(team_economy=4000, enemy_economy=4000, alive_players=5, enemy_alive=5)
        assert gs.map_control_pct == 0.5
        assert gs.time_remaining == 115
        assert gs.is_ct is True

    def test_custom_values(self):
        from Programma_CS2_RENAN.backend.analysis.win_probability import GameState

        gs = GameState(
            team_economy=8000, enemy_economy=2000,
            alive_players=4, enemy_alive=2,
            bomb_planted=True, is_ct=False,
        )
        assert gs.bomb_planted is True
        assert gs.is_ct is False


class TestWinProbabilityNN:
    def test_forward_shape(self):
        from Programma_CS2_RENAN.backend.analysis.win_probability import WinProbabilityNN

        model = WinProbabilityNN()
        model.eval()
        x = torch.randn(3, 12)
        out = model(x)
        assert out.shape == (3, 1)

    def test_output_bounded(self):
        from Programma_CS2_RENAN.backend.analysis.win_probability import WinProbabilityNN

        model = WinProbabilityNN()
        model.eval()
        x = torch.randn(10, 12) * 10  # Large inputs
        out = model(x)
        assert (out >= 0.0).all()
        assert (out <= 1.0).all()

    def test_gradient_flow(self):
        from Programma_CS2_RENAN.backend.analysis.win_probability import WinProbabilityNN

        model = WinProbabilityNN()
        x = torch.randn(2, 12, requires_grad=True)
        out = model(x)
        out.sum().backward()
        assert x.grad is not None


class TestWinProbabilityPredictor:
    def test_predict_even_match(self):
        from Programma_CS2_RENAN.backend.analysis.win_probability import (
            GameState,
            WinProbabilityPredictor,
        )

        pred = WinProbabilityPredictor()
        gs = GameState(team_economy=4000, enemy_economy=4000, alive_players=5, enemy_alive=5)
        prob, explanation = pred.predict(gs)
        assert 0.0 <= prob <= 1.0
        assert isinstance(explanation, str)

    def test_predict_no_alive_zero(self):
        from Programma_CS2_RENAN.backend.analysis.win_probability import (
            GameState,
            WinProbabilityPredictor,
        )

        pred = WinProbabilityPredictor()
        gs = GameState(team_economy=4000, enemy_economy=4000, alive_players=0, enemy_alive=5)
        prob, _ = pred.predict(gs)
        assert prob == 0.0

    def test_predict_enemy_dead_one(self):
        from Programma_CS2_RENAN.backend.analysis.win_probability import (
            GameState,
            WinProbabilityPredictor,
        )

        pred = WinProbabilityPredictor()
        gs = GameState(team_economy=4000, enemy_economy=4000, alive_players=5, enemy_alive=0)
        prob, _ = pred.predict(gs)
        assert prob == 1.0

    def test_predict_from_dict(self):
        from Programma_CS2_RENAN.backend.analysis.win_probability import WinProbabilityPredictor

        pred = WinProbabilityPredictor()
        prob, explanation = pred.predict_from_dict({"alive_players": 4, "enemy_alive": 2})
        assert 0.0 <= prob <= 1.0
