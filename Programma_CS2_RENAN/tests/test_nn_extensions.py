"""
Tests for NN Extensions — Phase 12 Coverage Expansion.

Covers:
  NeuralRoleHead (role_head.py) — forward, softmax, constants, extract_features
  nn/config.py — get_device, constants, throttling, batch size
  ProPerformanceDataset, SelfSupervisedDataset (dataset.py)
  AdvancedCoachNN, CoachNNConfig, ModelManager (model.py)
"""

import sys


import numpy as np
import pytest
import torch


# ---------------------------------------------------------------------------
# NeuralRoleHead (role_head.py)
# ---------------------------------------------------------------------------
class TestNeuralRoleHead:
    """Tests for the Neural Role Classification Head."""

    def _make_model(self):
        from Programma_CS2_RENAN.backend.nn.role_head import NeuralRoleHead
        return NeuralRoleHead()

    def test_forward_shape(self):
        model = self._make_model()
        x = torch.randn(4, 5)
        out = model(x)
        assert out.shape == (4, 5)

    def test_forward_softmax_sums_to_one(self):
        model = self._make_model()
        x = torch.randn(8, 5)
        out = model(x)
        sums = out.sum(dim=-1)
        assert torch.allclose(sums, torch.ones(8), atol=1e-5)

    def test_forward_log_softmax_shape(self):
        model = self._make_model()
        x = torch.randn(4, 5)
        out = model.forward_log_softmax(x)
        assert out.shape == (4, 5)
        # Log probabilities should be <= 0
        assert (out <= 0).all()

    def test_single_sample(self):
        model = self._make_model()
        x = torch.randn(1, 5)
        out = model(x)
        assert out.shape == (1, 5)

    def test_constants(self):
        from Programma_CS2_RENAN.backend.nn.role_head import NeuralRoleHead
        assert NeuralRoleHead.ROLE_INPUT_DIM == 5
        assert NeuralRoleHead.ROLE_OUTPUT_DIM == 5

    def test_module_constants(self):
        from Programma_CS2_RENAN.backend.nn.role_head import (
            FLEX_CONFIDENCE_THRESHOLD,
            LABEL_SMOOTHING_EPS,
            MIN_TRAINING_SAMPLES,
            ROLE_OUTPUT_ORDER,
        )
        assert FLEX_CONFIDENCE_THRESHOLD == 0.35
        assert MIN_TRAINING_SAMPLES == 20
        assert LABEL_SMOOTHING_EPS == 0.02
        assert len(ROLE_OUTPUT_ORDER) == 5

    def test_custom_dimensions(self):
        from Programma_CS2_RENAN.backend.nn.role_head import NeuralRoleHead
        model = NeuralRoleHead(input_dim=10, hidden_dim=64, output_dim=3)
        x = torch.randn(2, 10)
        out = model(x)
        assert out.shape == (2, 3)

    def test_gradient_flow(self):
        model = self._make_model()
        x = torch.randn(2, 5, requires_grad=True)
        out = model(x)
        loss = out.sum()
        loss.backward()
        assert x.grad is not None


class TestExtractRoleFeaturesFromStats:
    """Tests for extract_role_features_from_stats."""

    def test_valid_stats(self):
        from Programma_CS2_RENAN.backend.nn.role_head import extract_role_features_from_stats
        stats = {
            "rounds_played": 100,
            "rounds_survived": 45,
            "entry_frags": 12,
            "was_traded_ratio": 0.3,
            "impact_rating": 1.1,
            "positional_aggression_score": 0.6,
        }
        result = extract_role_features_from_stats(stats)
        assert result is not None
        assert result.shape == (5,)

    def test_zero_rounds_returns_none(self):
        from Programma_CS2_RENAN.backend.nn.role_head import extract_role_features_from_stats
        result = extract_role_features_from_stats({"rounds_played": 0})
        assert result is None

    def test_missing_rounds_returns_none(self):
        from Programma_CS2_RENAN.backend.nn.role_head import extract_role_features_from_stats
        result = extract_role_features_from_stats({})
        assert result is None

    def test_missing_optional_stats_use_defaults(self):
        from Programma_CS2_RENAN.backend.nn.role_head import extract_role_features_from_stats
        stats = {"rounds_played": 50}
        result = extract_role_features_from_stats(stats)
        assert result is not None
        assert result.shape == (5,)


# ---------------------------------------------------------------------------
# nn/config.py
# ---------------------------------------------------------------------------
class TestNNConfig:
    """Tests for the NN configuration module."""

    def test_get_device_returns_torch_device(self):
        from Programma_CS2_RENAN.backend.nn.config import get_device
        dev = get_device()
        assert isinstance(dev, torch.device)

    def test_constants(self):
        from Programma_CS2_RENAN.backend.nn.config import (
            BATCH_SIZE,
            EPOCHS,
            HIDDEN_DIM,
            INPUT_DIM,
            LEARNING_RATE,
            OUTPUT_DIM,
            WEIGHT_CLAMP,
        )
        assert BATCH_SIZE == 32
        assert INPUT_DIM > 0
        assert OUTPUT_DIM == 10
        assert HIDDEN_DIM == 128
        assert LEARNING_RATE == 0.001
        assert EPOCHS == 50
        assert WEIGHT_CLAMP == 0.5

    def test_get_throttling_delay(self):
        from Programma_CS2_RENAN.backend.nn.config import get_throttling_delay
        delay = get_throttling_delay()
        assert isinstance(delay, float)
        assert delay >= 0.0

    def test_get_intensity_batch_size(self):
        from Programma_CS2_RENAN.backend.nn.config import get_intensity_batch_size
        bs = get_intensity_batch_size()
        assert isinstance(bs, int)
        assert bs > 0

    def test_integrated_gpu_keywords(self):
        from Programma_CS2_RENAN.backend.nn.config import _INTEGRATED_GPU_KEYWORDS
        assert "uhd" in _INTEGRATED_GPU_KEYWORDS
        assert "iris" in _INTEGRATED_GPU_KEYWORDS


# ---------------------------------------------------------------------------
# dataset.py
# ---------------------------------------------------------------------------
class TestProPerformanceDataset:
    """Tests for ProPerformanceDataset."""

    def test_from_tensors(self):
        from Programma_CS2_RENAN.backend.nn.dataset import ProPerformanceDataset
        X = torch.randn(10, 25)
        y = torch.randn(10, 4)
        ds = ProPerformanceDataset(X, y)
        assert len(ds) == 10
        x_i, y_i = ds[0]
        assert x_i.shape == (25,)
        assert y_i.shape == (4,)

    def test_from_numpy(self):
        from Programma_CS2_RENAN.backend.nn.dataset import ProPerformanceDataset
        X = np.random.randn(5, 10).astype(np.float32)
        y = np.random.randn(5, 3).astype(np.float32)
        ds = ProPerformanceDataset(X, y)
        assert len(ds) == 5

    def test_dtype_is_float32(self):
        from Programma_CS2_RENAN.backend.nn.dataset import ProPerformanceDataset
        X = torch.randn(3, 5)
        y = torch.randn(3, 2)
        ds = ProPerformanceDataset(X, y)
        assert ds.X.dtype == torch.float32
        assert ds.y.dtype == torch.float32


class TestSelfSupervisedDataset:
    """Tests for SelfSupervisedDataset (JEPA)."""

    def test_basic_creation(self):
        from Programma_CS2_RENAN.backend.nn.dataset import SelfSupervisedDataset
        X = torch.randn(50, 25)
        ds = SelfSupervisedDataset(X, context_len=10, prediction_len=5)
        assert len(ds) == 35  # 50 - 10 - 5

    def test_getitem_shapes(self):
        from Programma_CS2_RENAN.backend.nn.dataset import SelfSupervisedDataset
        X = torch.randn(30, 10)
        ds = SelfSupervisedDataset(X, context_len=8, prediction_len=4)
        context, target = ds[0]
        assert context.shape == (8, 10)
        assert target.shape == (4, 10)

    def test_too_short_raises_error(self):
        from Programma_CS2_RENAN.backend.nn.dataset import SelfSupervisedDataset
        X = torch.randn(10, 5)
        with pytest.raises(ValueError, match="too short"):
            SelfSupervisedDataset(X, context_len=10, prediction_len=5)

    def test_from_numpy(self):
        from Programma_CS2_RENAN.backend.nn.dataset import SelfSupervisedDataset
        X = np.random.randn(40, 15).astype(np.float32)
        ds = SelfSupervisedDataset(X, context_len=10, prediction_len=5)
        assert len(ds) == 25


# ---------------------------------------------------------------------------
# AdvancedCoachNN / CoachNNConfig / ModelManager (model.py)
# ---------------------------------------------------------------------------
class TestCoachNNConfig:
    """Tests for the CoachNNConfig dataclass."""

    def test_defaults(self):
        from Programma_CS2_RENAN.backend.nn.model import CoachNNConfig
        cfg = CoachNNConfig()
        assert cfg.hidden_dim == 128
        assert cfg.num_experts == 3
        assert cfg.num_lstm_layers == 2
        assert cfg.dropout == 0.2
        assert cfg.use_layer_norm is True

    def test_custom(self):
        from Programma_CS2_RENAN.backend.nn.model import CoachNNConfig
        cfg = CoachNNConfig(hidden_dim=64, num_experts=5, dropout=0.3)
        assert cfg.hidden_dim == 64
        assert cfg.num_experts == 5


class TestAdvancedCoachNN:
    """Tests for the AdvancedCoachNN model."""

    def _make_model(self, **kwargs):
        from Programma_CS2_RENAN.backend.nn.model import AdvancedCoachNN
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM
        return AdvancedCoachNN(input_dim=METADATA_DIM, output_dim=METADATA_DIM, **kwargs)

    def test_forward_3d_input(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM
        model = self._make_model()
        x = torch.randn(2, 5, METADATA_DIM)
        out = model(x)
        assert out.shape == (2, METADATA_DIM)

    def test_forward_2d_input(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM
        model = self._make_model()
        x = torch.randn(2, METADATA_DIM)
        out = model(x)
        assert out.shape == (2, METADATA_DIM)

    def test_forward_with_role_id(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM
        model = self._make_model()
        x = torch.randn(2, 5, METADATA_DIM)
        out = model(x, role_id=1)
        assert out.shape == (2, METADATA_DIM)

    def test_forward_output_bounded(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM
        model = self._make_model()
        x = torch.randn(4, 5, METADATA_DIM)
        out = model(x)
        # tanh output should be in [-1, 1]
        assert (out >= -1.0).all()
        assert (out <= 1.0).all()

    def test_from_config(self):
        from Programma_CS2_RENAN.backend.nn.model import AdvancedCoachNN, CoachNNConfig
        cfg = CoachNNConfig(hidden_dim=64, num_experts=2)
        model = AdvancedCoachNN(config=cfg)
        x = torch.randn(2, 5, cfg.input_dim)
        out = model(x)
        assert out.shape == (2, cfg.output_dim)

    def test_role_id_out_of_bounds_clamps(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM
        model = self._make_model()
        x = torch.randn(2, 5, METADATA_DIM)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            out = model(x, role_id=99)
        assert out.shape == (2, METADATA_DIM)

    def test_validate_input_dim_1d_raises(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM
        model = self._make_model()
        x = torch.randn(METADATA_DIM)
        import pytest
        with pytest.raises(ValueError, match="at least 2 dims"):
            model(x)


class TestModelManager:
    """Tests for the ModelManager save/load."""

    def test_save_version(self, tmp_path):
        from Programma_CS2_RENAN.backend.nn.model import AdvancedCoachNN, ModelManager
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM
        mgr = ModelManager(model_dir=str(tmp_path))
        model = AdvancedCoachNN(input_dim=METADATA_DIM, output_dim=METADATA_DIM)
        path = mgr.save_version(model, {"loss": 0.05})
        assert path.endswith(".pt")
        import os
        assert os.path.exists(path)
        # Metadata JSON should also exist
        meta_path = path.replace(".pt", ".json")
        assert os.path.exists(meta_path)

    def test_model_dir_created(self, tmp_path):
        from Programma_CS2_RENAN.backend.nn.model import ModelManager
        model_dir = str(tmp_path / "new_models")
        mgr = ModelManager(model_dir=model_dir)
        import os
        assert os.path.isdir(model_dir)


class TestTeacherRefinementNNAlias:
    """Test backward compatibility alias."""

    def test_alias_exists(self):
        from Programma_CS2_RENAN.backend.nn.model import AdvancedCoachNN, TeacherRefinementNN
        assert TeacherRefinementNN is AdvancedCoachNN
