import sys


import pytest

from Programma_CS2_RENAN.backend.analysis.utility_economy import (
    EconomyOptimizer,
    UtilityAnalyzer,
    UtilityType,
)


class TestTacticalFeatures:
    def test_utility_analyzer(self):
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
        assert report.overall_score == pytest.approx(0.63, abs=0.05)
        assert len(report.utility_stats) == 4

        # Per-utility effectiveness — traced from source formulas
        smoke = report.utility_stats[UtilityType.SMOKE]
        assert smoke.effectiveness_score == pytest.approx(0.278, abs=0.01)

        flash = report.utility_stats[UtilityType.FLASH]
        assert flash.effectiveness_score == pytest.approx(0.667, abs=0.01)

        molotov = report.utility_stats[UtilityType.MOLOTOV]
        assert molotov.effectiveness_score == pytest.approx(0.571, abs=0.01)

        he = report.utility_stats[UtilityType.HE]
        assert he.effectiveness_score == pytest.approx(1.0, abs=0.01)

    def test_economy_pistol_round(self):
        optimizer = EconomyOptimizer()
        decision = optimizer.recommend(current_money=800, round_number=1, is_ct=True)
        assert decision.action == "pistol"
        assert len(decision.recommended_weapons) == 3

    def test_economy_full_buy(self):
        optimizer = EconomyOptimizer()
        decision = optimizer.recommend(current_money=5500, round_number=5, is_ct=True)
        assert decision.action == "full-buy"
        assert len(decision.recommended_weapons) == 3

    def test_economy_eco(self):
        optimizer = EconomyOptimizer()
        decision = optimizer.recommend(current_money=1200, round_number=4, is_ct=True)
        assert decision.action == "eco"
        assert "save" in decision.reasoning.lower()
        assert len(decision.recommended_weapons) == 2

    def test_economy_force_buy(self):
        optimizer = EconomyOptimizer()
        decision = optimizer.recommend(current_money=2500, round_number=3, is_ct=False)
        assert decision.action == "force-buy"
        assert len(decision.recommended_weapons) == 3

    def test_economy_half_buy(self):
        optimizer = EconomyOptimizer()
        decision = optimizer.recommend(current_money=3000, round_number=8, is_ct=True)
        assert decision.action == "half-buy"
        assert len(decision.recommended_weapons) == 3

    def test_economy_overtime(self):
        optimizer = EconomyOptimizer()
        decision = optimizer.recommend(current_money=5000, round_number=13, is_ct=True)
        assert decision.action == "full-buy"
        assert len(decision.recommended_weapons) == 2

