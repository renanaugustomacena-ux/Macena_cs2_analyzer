"""
Tests for the Analysis Orchestrator — Phase 6 Integration Layer.

Validates that the orchestrator correctly coordinates all Phase 6
analysis modules and produces structured CoachingInsight objects.
"""

import sys


import pytest


class TestAnalysisOrchestrator:
    """Verify AnalysisOrchestrator end-to-end behavior."""

    def test_instantiation(self):
        """Orchestrator should instantiate all sub-analyzers."""
        from Programma_CS2_RENAN.backend.services.analysis_orchestrator import AnalysisOrchestrator

        orch = AnalysisOrchestrator()
        assert orch.belief_estimator is not None
        assert orch.deception_analyzer is not None
        assert orch.momentum_tracker is not None
        assert orch.entropy_analyzer is not None
        assert orch.game_tree is not None
        assert orch.blind_spot_detector is not None

    def test_factory_function(self):
        """get_analysis_orchestrator should return an AnalysisOrchestrator."""
        from Programma_CS2_RENAN.backend.services.analysis_orchestrator import (
            AnalysisOrchestrator,
            get_analysis_orchestrator,
        )

        orch = get_analysis_orchestrator()
        assert isinstance(orch, AnalysisOrchestrator)

    def test_analyze_match_with_momentum(self):
        """Momentum analysis should produce insights from round outcomes."""
        from Programma_CS2_RENAN.backend.services.analysis_orchestrator import AnalysisOrchestrator

        orch = AnalysisOrchestrator()

        # Simulate a match with a long loss streak (should trigger tilt detection)
        round_outcomes = [{"round_number": i, "round_won": False} for i in range(1, 8)]

        analysis = orch.analyze_match(
            player_name="test_player",
            demo_name="test_demo",
            round_outcomes=round_outcomes,
        )

        assert analysis.player_name == "test_player"
        assert analysis.demo_name == "test_demo"
        # With 7 consecutive losses, tilt should be detected
        tilt_insights = [i for i in analysis.all_insights if i.focus_area == "momentum"]
        assert len(tilt_insights) > 0
        assert any("Tilt" in i.title for i in tilt_insights)

    def test_analyze_match_with_hot_streak(self):
        """Hot streak should produce momentum insights."""
        from Programma_CS2_RENAN.backend.services.analysis_orchestrator import AnalysisOrchestrator

        orch = AnalysisOrchestrator()

        round_outcomes = [{"round_number": i, "round_won": True} for i in range(1, 8)]

        analysis = orch.analyze_match(
            player_name="test_player",
            demo_name="test_demo",
            round_outcomes=round_outcomes,
        )

        hot_insights = [i for i in analysis.all_insights if "Hot" in i.title]
        assert len(hot_insights) > 0

    def test_analyze_match_empty_data(self):
        """Empty round outcomes should produce no insights without error."""
        from Programma_CS2_RENAN.backend.services.analysis_orchestrator import AnalysisOrchestrator

        orch = AnalysisOrchestrator()

        analysis = orch.analyze_match(
            player_name="test_player",
            demo_name="test_demo",
            round_outcomes=[],
        )

        assert analysis.all_insights == []

    def test_analyze_match_with_game_states(self):
        """Game states should produce strategy and/or blind spot insights."""
        from Programma_CS2_RENAN.backend.services.analysis_orchestrator import AnalysisOrchestrator

        orch = AnalysisOrchestrator()

        # Simulate states where player always holds in an advantage scenario
        game_states = [
            {
                "game_state": {
                    "team_economy": 5000,
                    "enemy_economy": 2000,
                    "alive_players": 5,
                    "enemy_alive": 2,
                    "map_control_pct": 0.6,
                    "time_remaining": 90,
                    "utility_remaining": 3,
                },
                "action_taken": "hold",
                "round_won": False,
            }
            for _ in range(5)
        ]

        analysis = orch.analyze_match(
            player_name="test_player",
            demo_name="test_demo",
            round_outcomes=[],
            game_states=game_states,
        )

        # Should have at least the strategy recommendation
        strategy_insights = [i for i in analysis.all_insights if i.focus_area == "game_theory"]
        assert len(strategy_insights) > 0

    def test_insight_structure(self):
        """All generated insights should have valid CoachingInsight fields."""
        from Programma_CS2_RENAN.backend.services.analysis_orchestrator import AnalysisOrchestrator
        from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight

        orch = AnalysisOrchestrator()

        round_outcomes = [{"round_number": i, "round_won": i % 3 == 0} for i in range(1, 13)]

        analysis = orch.analyze_match(
            player_name="test_player",
            demo_name="test_demo",
            round_outcomes=round_outcomes,
        )

        for insight in analysis.all_insights:
            assert isinstance(insight, CoachingInsight)
            assert insight.player_name == "test_player"
            assert insight.demo_name == "test_demo"
            assert insight.title
            assert insight.message
            assert insight.focus_area
            assert insight.severity in ("Info", "Medium", "High")


class TestMatchAnalysis:
    """Verify MatchAnalysis dataclass."""

    def test_all_insights_aggregation(self):
        """all_insights should combine match_insights and round analysis insights."""
        from Programma_CS2_RENAN.backend.services.analysis_orchestrator import (
            MatchAnalysis,
            RoundAnalysis,
        )
        from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight

        ma = MatchAnalysis(player_name="p", demo_name="d")
        ma.match_insights.append(
            CoachingInsight(
                player_name="p",
                demo_name="d",
                title="T1",
                severity="Info",
                message="M1",
                focus_area="f1",
            )
        )
        ma.round_analyses.append(
            RoundAnalysis(
                round_number=1,
                insights=[
                    CoachingInsight(
                        player_name="p",
                        demo_name="d",
                        title="T2",
                        severity="Info",
                        message="M2",
                        focus_area="f2",
                    )
                ],
            )
        )

        assert len(ma.all_insights) == 2
