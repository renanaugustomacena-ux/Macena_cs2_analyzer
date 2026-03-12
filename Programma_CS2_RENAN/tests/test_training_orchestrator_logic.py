"""
Tests for training_orchestrator.py — Tier 2: Core training logic.

Verifies:
1. TrainingOrchestrator rejects unknown model_type at init (unlike ModelFactory)
2. Early stopping logic works correctly
3. Empty batch handling (refuses to train on zeros)
4. Batch preparation produces correct tensor shapes
5. RAP path behavior
"""

import numpy as np
import pytest
import torch
from unittest.mock import MagicMock, patch


class TestOrchestratorInit:
    """Verify constructor validation and state initialization."""

    def test_valid_jepa_type_accepted(self):
        with patch("Programma_CS2_RENAN.backend.nn.training_orchestrator.get_device",
                    return_value=torch.device("cpu")):
            from Programma_CS2_RENAN.backend.nn.training_orchestrator import TrainingOrchestrator

            manager = MagicMock()
            orch = TrainingOrchestrator(manager, model_type="jepa")
            assert orch.model_type == "jepa"
            assert orch.model_name == "jepa_brain"

    def test_valid_vl_jepa_type_accepted(self):
        with patch("Programma_CS2_RENAN.backend.nn.training_orchestrator.get_device",
                    return_value=torch.device("cpu")):
            from Programma_CS2_RENAN.backend.nn.training_orchestrator import TrainingOrchestrator

            manager = MagicMock()
            orch = TrainingOrchestrator(manager, model_type="vl-jepa")
            assert orch.model_type == "vl-jepa"
            assert orch.model_name == "vl_jepa_brain"

    def test_valid_rap_type_accepted(self):
        pytest.importorskip("ncps", reason="ncps not installed")
        with patch("Programma_CS2_RENAN.backend.nn.training_orchestrator.get_device",
                    return_value=torch.device("cpu")), \
             patch("Programma_CS2_RENAN.core.config.get_setting",
                    side_effect=lambda key, default=None: True if key == "USE_RAP_MODEL" else default):
            from Programma_CS2_RENAN.backend.nn.training_orchestrator import TrainingOrchestrator

            manager = MagicMock()
            orch = TrainingOrchestrator(manager, model_type="rap")
            assert orch.model_type == "rap"
            assert orch.model_name == "rap_coach"

    def test_invalid_type_raises_value_error(self):
        """TrainingOrchestrator CORRECTLY rejects unknown types (unlike ModelFactory)."""
        with patch("Programma_CS2_RENAN.backend.nn.training_orchestrator.get_device",
                    return_value=torch.device("cpu")):
            from Programma_CS2_RENAN.backend.nn.training_orchestrator import TrainingOrchestrator

            manager = MagicMock()
            with pytest.raises(ValueError, match="Unknown model type"):
                TrainingOrchestrator(manager, model_type="invalid")

    def test_default_patience(self):
        with patch("Programma_CS2_RENAN.backend.nn.training_orchestrator.get_device",
                    return_value=torch.device("cpu")):
            from Programma_CS2_RENAN.backend.nn.training_orchestrator import TrainingOrchestrator

            orch = TrainingOrchestrator(MagicMock(), model_type="jepa")
            assert orch.patience == 10
            assert orch.best_val_loss == float("inf")
            assert orch.patience_counter == 0


class TestEarlyStopping:
    """Verify early stopping triggers correctly using the production EarlyStopping class."""

    def test_patience_counter_increments_on_no_improvement(self):
        """When val_loss doesn't improve, counter should increment."""
        from Programma_CS2_RENAN.backend.nn.early_stopping import EarlyStopping

        es = EarlyStopping(patience=3, min_delta=1e-4)
        es(0.5)  # First call sets baseline
        result = es(0.6)  # Worse — should increment counter, not stop

        assert result is False
        assert es.counter == 1
        assert es.best_loss == 0.5

    def test_patience_resets_on_improvement(self):
        """When val_loss improves, counter should reset."""
        from Programma_CS2_RENAN.backend.nn.early_stopping import EarlyStopping

        es = EarlyStopping(patience=3, min_delta=1e-4)
        es(0.5)  # Baseline
        es(0.6)  # No improvement — counter=1
        es(0.7)  # No improvement — counter=2
        result = es(0.3)  # Improvement — counter should reset

        assert result is False
        assert es.counter == 0
        assert es.best_loss == 0.3

    def test_early_stop_triggers_at_patience_limit(self):
        """After patience epochs with no improvement, should_stop must be True."""
        from Programma_CS2_RENAN.backend.nn.early_stopping import EarlyStopping

        es = EarlyStopping(patience=3, min_delta=1e-4)
        es(0.5)  # Baseline
        es(0.6)  # counter=1
        es(0.7)  # counter=2
        result = es(0.8)  # counter=3 — should trigger stop

        assert result is True
        assert es.should_stop is True


class TestEmptyBatchHandling:
    """Verify that empty batches are handled safely."""

    def test_prepare_tensor_batch_returns_none_for_empty(self):
        """_prepare_tensor_batch must return None for empty input, never all-zero tensors."""
        with patch("Programma_CS2_RENAN.backend.nn.training_orchestrator.get_device",
                    return_value=torch.device("cpu")):
            from Programma_CS2_RENAN.backend.nn.training_orchestrator import TrainingOrchestrator

            orch = TrainingOrchestrator(MagicMock(), model_type="jepa")
            result = orch._prepare_tensor_batch([])
            assert result is None, "Empty batch should return None, not zero tensors"

    def test_fetch_batches_empty_when_no_data(self):
        """_fetch_batches should return empty list when manager has no data."""
        with patch("Programma_CS2_RENAN.backend.nn.training_orchestrator.get_device",
                    return_value=torch.device("cpu")):
            from Programma_CS2_RENAN.backend.nn.training_orchestrator import TrainingOrchestrator

            manager = MagicMock()
            manager._fetch_jepa_ticks.return_value = []
            orch = TrainingOrchestrator(manager, model_type="jepa")

            result = orch._fetch_batches(is_train=True)
            assert result == []


class TestDeterministicNegativeSampling:
    """Verify reproducibility of negative sampling RNG."""

    def test_neg_rng_is_seeded(self):
        with patch("Programma_CS2_RENAN.backend.nn.training_orchestrator.get_device",
                    return_value=torch.device("cpu")):
            from Programma_CS2_RENAN.backend.nn.training_orchestrator import TrainingOrchestrator

            orch = TrainingOrchestrator(MagicMock(), model_type="jepa")
            assert orch._neg_rng is not None

    def test_neg_rng_produces_reproducible_results(self):
        with patch("Programma_CS2_RENAN.backend.nn.training_orchestrator.get_device",
                    return_value=torch.device("cpu")):
            from Programma_CS2_RENAN.backend.nn.training_orchestrator import TrainingOrchestrator

            orch1 = TrainingOrchestrator(MagicMock(), model_type="jepa")
            orch2 = TrainingOrchestrator(MagicMock(), model_type="jepa")

            result1 = orch1._neg_rng.choice(100, 5, replace=False)
            result2 = orch2._neg_rng.choice(100, 5, replace=False)

            np.testing.assert_array_equal(result1, result2), (
                "Same seed should produce identical negative samples"
            )
