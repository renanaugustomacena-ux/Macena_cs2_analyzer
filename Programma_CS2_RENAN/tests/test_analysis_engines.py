"""
Unit tests for Analysis Engines.

Tests Win Probability, Role Classifier, Utility Analyzer, and Economy Optimizer.
"""

import sys


import pytest
import torch

from Programma_CS2_RENAN.backend.analysis.role_classifier import (
    ROLE_PROFILES,
    PlayerRole,
    RoleClassifier,
    get_role_classifier,
)
from Programma_CS2_RENAN.backend.analysis.utility_economy import (
    EconomyOptimizer,
    UtilityAnalyzer,
    UtilityType,
    get_economy_optimizer,
    get_utility_analyzer,
)
from Programma_CS2_RENAN.backend.analysis.win_probability import (
    GameState,
    WinProbabilityNN,
    WinProbabilityPredictor,
    get_win_predictor,
)


class TestWinProbabilityPredictor:
    """Test suite for win probability prediction."""

    def test_predictor_initialization(self):
        """Test predictor can be initialized with a callable model."""
        predictor = WinProbabilityPredictor()
        assert predictor.model is not None
        assert callable(predictor.model)

    def test_even_match_prediction(self):
        """Test prediction for even match."""
        predictor = WinProbabilityPredictor()

        state = GameState(team_economy=4500, enemy_economy=4500, alive_players=5, enemy_alive=5)

        prob, explanation = predictor.predict(state)

        assert 0.3 < prob < 0.7  # Should be near 50%
        assert len(explanation) > 0

    def test_man_advantage_prediction(self):
        """Test prediction with player advantage."""
        predictor = WinProbabilityPredictor()

        state = GameState(team_economy=4000, enemy_economy=4000, alive_players=4, enemy_alive=1)

        prob, _ = predictor.predict(state)

        assert prob > 0.80  # Should heavily favor team

    def test_economy_advantage(self):
        """Test prediction with economy advantage."""
        predictor = WinProbabilityPredictor()

        rich = GameState(team_economy=16000, enemy_economy=2000, alive_players=5, enemy_alive=5)

        poor = GameState(team_economy=2000, enemy_economy=16000, alive_players=5, enemy_alive=5)

        rich_prob, _ = predictor.predict(rich)
        poor_prob, _ = predictor.predict(poor)

        assert rich_prob > poor_prob

    def test_zero_players_lose(self):
        """Test that 0 alive players = 0% win chance."""
        predictor = WinProbabilityPredictor()

        state = GameState(team_economy=4000, enemy_economy=4000, alive_players=0, enemy_alive=3)

        prob, _ = predictor.predict(state)

        assert prob == 0.0

    def test_all_enemies_dead_win(self):
        """Test that all enemies dead = 100% win chance."""
        predictor = WinProbabilityPredictor()

        state = GameState(team_economy=4000, enemy_economy=4000, alive_players=3, enemy_alive=0)

        prob, _ = predictor.predict(state)

        assert prob == 1.0

    def test_predict_from_dict(self):
        """Test dict-based prediction."""
        predictor = WinProbabilityPredictor()

        state_dict = {
            "team_economy": 5000,
            "enemy_economy": 4000,
            "alive_players": 4,
            "enemy_alive": 3,
        }

        prob, explanation = predictor.predict_from_dict(state_dict)

        assert 0 <= prob <= 1
        assert len(explanation) > 0


class TestRoleClassifier:
    """Test suite for role classification."""

    def test_classifier_initialization(self):
        """Test classifier can be initialized in cold start state."""
        classifier = RoleClassifier()
        # Cold start: classifier initializes but may not have thresholds yet
        assert classifier is not None
        assert hasattr(classifier, "classify")

    def test_classify_cold_start_returns_flex(self):
        """Test cold start classification returns FLEX with 0% confidence."""
        classifier = RoleClassifier()

        stats = {
            "awp_kills": 15,
            "total_kills": 25,
            "entry_frags": 2,
            "assists": 3,
            "rounds_played": 24,
            "rounds_survived": 12,
        }

        role, confidence, profile = classifier.classify(stats)

        # Cold start: no learned thresholds, returns FLEX
        assert role == PlayerRole.FLEX
        assert confidence == 0.0

    def test_role_profiles_exist(self):
        """Test all role profiles are defined."""
        for role in [
            PlayerRole.AWPER,
            PlayerRole.ENTRY_FRAGGER,
            PlayerRole.SUPPORT,
            PlayerRole.IGL,
            PlayerRole.LURKER,
        ]:
            assert role in ROLE_PROFILES
            # coaching_focus is populated dynamically from Knowledge Base
            assert ROLE_PROFILES[role].description != ""

    def test_get_role_coaching(self):
        """Test role-specific coaching retrieval (may be empty in cold start)."""
        classifier = RoleClassifier()

        tips = classifier.get_role_coaching(PlayerRole.AWPER)
        # In cold start, coaching tips may be empty until KB is populated
        assert isinstance(tips, list)
        # If tips are populated, verify they contain strings
        for tip in tips:
            assert isinstance(tip, str)


class TestUtilityAnalyzer:
    """Test suite for utility analysis."""

    def test_analyzer_initialization(self):
        """Test analyzer can be initialized with non-empty baselines."""
        analyzer = UtilityAnalyzer()
        assert analyzer.PRO_BASELINES is not None
        assert isinstance(analyzer.PRO_BASELINES, dict)
        assert len(analyzer.PRO_BASELINES) > 0

    def test_analyze_utility(self):
        """Test utility analysis."""
        analyzer = UtilityAnalyzer()

        stats = {
            "molotov_thrown": 10,
            "molotov_damage": 350,
            "he_grenade_thrown": 5,
            "he_grenade_damage": 125,
            "flash_thrown": 15,
            "flash_affected": 18,
            "smoke_thrown": 20,
            "rounds_played": 24,
        }

        report = analyzer.analyze(stats)

        assert 0 <= report.overall_score <= 1
        assert len(report.utility_stats) == 4
        assert report.economy_impact >= 0

    def test_low_utility_recommendations(self):
        """Test recommendations for low utility usage."""
        analyzer = UtilityAnalyzer()

        stats = {
            "molotov_thrown": 2,
            "molotov_damage": 40,
            "he_grenade_thrown": 1,
            "he_grenade_damage": 20,
            "flash_thrown": 5,
            "flash_affected": 2,
            "smoke_thrown": 5,
            "rounds_played": 24,
        }

        report = analyzer.analyze(stats)

        assert len(report.recommendations) > 0


class TestEconomyOptimizer:
    """Test suite for economy optimization."""

    def test_optimizer_initialization(self):
        """Test optimizer can be initialized with non-empty weapon costs."""
        optimizer = EconomyOptimizer()
        assert optimizer.WEAPON_COSTS is not None
        assert isinstance(optimizer.WEAPON_COSTS, dict)
        assert len(optimizer.WEAPON_COSTS) > 0

    def test_pistol_round_decision(self):
        """Test pistol round recommendation."""
        optimizer = EconomyOptimizer()

        decision = optimizer.recommend(current_money=800, round_number=1, is_ct=True)

        assert decision.action == "pistol"
        assert decision.confidence > 0.9

    def test_full_buy_decision(self):
        """Test full buy recommendation."""
        optimizer = EconomyOptimizer()

        decision = optimizer.recommend(current_money=5500, round_number=5, is_ct=True)

        assert decision.action == "full-buy"

    def test_eco_decision(self):
        """Test eco round recommendation."""
        optimizer = EconomyOptimizer()

        decision = optimizer.recommend(
            current_money=1200, round_number=4, is_ct=True, loss_bonus=1900
        )

        assert decision.action == "eco"
        assert "save" in decision.reasoning.lower()

    def test_force_buy_decision(self):
        """Test force buy recommendation."""
        optimizer = EconomyOptimizer()

        decision = optimizer.recommend(
            current_money=2500, round_number=3, is_ct=False, score_diff=-2
        )

        assert decision.action in ["force-buy", "half-buy"]

