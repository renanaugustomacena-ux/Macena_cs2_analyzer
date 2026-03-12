import sys


import pytest
import torch

from Programma_CS2_RENAN.backend.nn.win_probability_trainer import WinProbabilityTrainerNN, predict_win_prob
from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import get_pro_baseline
from Programma_CS2_RENAN.backend.processing.external_analytics import EliteAnalytics


class TestIntegration:
    def test_analytics_engine(self):
        analytics = EliteAnalytics()

        # Test player role lookup
        role = analytics.get_player_role("NiKo")
        assert isinstance(role, str)
        assert len(role) > 0, "Role string should not be empty"

        # Test tournament baseline
        baseline = analytics.get_tournament_baseline()
        if not baseline:
            pytest.skip("Tournament baseline CSV data not available")
        assert "accuracy" in baseline, f"Baseline missing 'accuracy', keys: {list(baseline.keys())}"
        assert (
            "econ_rating" in baseline
        ), f"Baseline missing 'econ_rating', keys: {list(baseline.keys())}"

    def test_win_probability_model(self):
        """Pipeline smoke test: model forward pass produces valid sigmoid output."""
        torch.manual_seed(42)
        win_model = WinProbabilityTrainerNN()
        # CT has clear advantage: 5v3, more health, more equipment
        ct_advantage_state = {
            "ct_alive": 5,
            "t_alive": 3,
            "ct_health": 450,
            "t_health": 200,
            "ct_armor": 500,
            "t_armor": 250,
            "ct_eqp": 20000,
            "t_eqp": 12000,
            "bomb_planted": 0,
        }
        prob = predict_win_prob(win_model, ct_advantage_state)
        # Sigmoid always outputs [0,1] — this checks the pipeline doesn't crash
        # and the forward pass produces a valid probability.
        # Note: untrained model can saturate at 0.0 or 1.0 depending on
        # random weight init — that's acceptable for a smoke test.
        assert 0.0 <= prob <= 1.0, f"Model output {prob} outside valid sigmoid range [0,1]"

    def test_pro_baseline(self):
        baseline = get_pro_baseline()
        assert isinstance(baseline, dict)
        assert "rating" in baseline
        assert baseline["rating"]["mean"] > 0

    def test_datasets_availability(self):
        analytics = EliteAnalytics()
        datasets = analytics.get_available_extra_datasets()
        assert isinstance(datasets, list)
        # Validate structure: each entry should be a string (dataset name/path)
        for ds in datasets:
            assert isinstance(ds, str), f"Dataset entry should be str, got {type(ds)}"
            assert len(ds) > 0, "Dataset name should not be empty"


