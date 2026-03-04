"""
Tests for NN Infrastructure — Phase 2 Coverage Expansion.

Covers:
  EMA (Exponential Moving Average)
  ModelFactory (model instantiation dispatcher)
  Persistence (checkpoint save/load, StaleCheckpointError)
  SuperpositionLayer (context-gated MLP)
"""

import sys


import pytest
import torch
import torch.nn as nn

from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM


# ---------------------------------------------------------------------------
# EMA (Exponential Moving Average)
# ---------------------------------------------------------------------------
class TestEMA:
    """Tests for EMA shadow weight management."""

    def test_shadow_initialized_from_model(self):
        from Programma_CS2_RENAN.backend.nn.ema import EMA

        model = nn.Linear(10, 5)
        ema = EMA(model, decay=0.999)
        for name, param in model.named_parameters():
            if param.requires_grad:
                assert name in ema.shadow
                assert torch.allclose(ema.shadow[name], param.data)

    def test_update_moves_shadow(self):
        from Programma_CS2_RENAN.backend.nn.ema import EMA

        torch.manual_seed(42)
        model = nn.Linear(10, 5)
        ema = EMA(model, decay=0.9)  # Lower decay so update is visible
        original_shadow_w = ema.shadow["weight"].clone()
        # Simulate a training step with large delta
        model.weight.data += torch.ones_like(model.weight) * 2.0
        ema.update()
        # Weight shadow (large tensor) should have moved
        assert not torch.allclose(ema.shadow["weight"], original_shadow_w)

    def test_apply_shadow_replaces_weights(self):
        from Programma_CS2_RENAN.backend.nn.ema import EMA

        torch.manual_seed(42)
        model = nn.Linear(10, 5)
        ema = EMA(model, decay=0.9)
        # Train several steps to diverge shadow from params
        for _ in range(20):
            model.weight.data += torch.randn_like(model.weight) * 0.1
            ema.update()
        weight_before_apply = model.weight.data.clone()
        ema.apply_shadow()
        # Weights should now be the shadow (different from training weights)
        assert not torch.allclose(model.weight.data, weight_before_apply)

    def test_restore_recovers_original(self):
        from Programma_CS2_RENAN.backend.nn.ema import EMA

        torch.manual_seed(42)
        model = nn.Linear(10, 5)
        ema = EMA(model, decay=0.9)
        for _ in range(10):
            model.weight.data += torch.randn_like(model.weight) * 0.1
            ema.update()
        weight_before = model.weight.data.clone()
        ema.apply_shadow()
        ema.restore()
        assert torch.allclose(model.weight.data, weight_before)

    def test_state_dict_returns_clones(self):
        from Programma_CS2_RENAN.backend.nn.ema import EMA

        model = nn.Linear(10, 5)
        ema = EMA(model, decay=0.999)
        sd = ema.state_dict()
        # Modify returned dict — should NOT affect internal shadow
        for k in sd:
            sd[k].zero_()
        for name in ema.shadow:
            assert not torch.allclose(ema.shadow[name], torch.zeros_like(ema.shadow[name]))

    def test_load_state_dict(self):
        from Programma_CS2_RENAN.backend.nn.ema import EMA

        model = nn.Linear(10, 5)
        ema1 = EMA(model, decay=0.999)
        for _ in range(10):
            model.weight.data += torch.randn_like(model.weight) * 0.1
            ema1.update()
        sd = ema1.state_dict()
        # Create new EMA and load
        model2 = nn.Linear(10, 5)
        ema2 = EMA(model2, decay=0.999)
        ema2.load_state_dict(sd)
        for name in sd:
            assert torch.allclose(ema2.shadow[name], ema1.shadow[name])

    def test_decay_parameter_effect(self):
        from Programma_CS2_RENAN.backend.nn.ema import EMA

        torch.manual_seed(42)
        model1 = nn.Linear(10, 5)
        model2 = nn.Linear(10, 5)
        model2.load_state_dict(model1.state_dict())
        ema_slow = EMA(model1, decay=0.999)
        ema_fast = EMA(model2, decay=0.9)
        delta = torch.randn_like(model1.weight) * 0.5
        model1.weight.data += delta
        model2.weight.data += delta
        ema_slow.update()
        ema_fast.update()
        # Fast EMA (lower decay) should move more toward the new weight
        slow_dist = torch.norm(ema_slow.shadow["weight"] - model1.weight.data)
        fast_dist = torch.norm(ema_fast.shadow["weight"] - model2.weight.data)
        assert fast_dist < slow_dist

    def test_multiple_updates_converge(self):
        from Programma_CS2_RENAN.backend.nn.ema import EMA

        torch.manual_seed(42)
        model = nn.Linear(10, 5)
        ema = EMA(model, decay=0.99)
        target_weight = model.weight.data.clone() + 1.0
        # Push model weights to a fixed target
        for _ in range(500):
            model.weight.data = target_weight.clone()
            ema.update()
        # Shadow should be very close to the fixed target
        assert torch.allclose(ema.shadow["weight"], target_weight, atol=0.15)


# ---------------------------------------------------------------------------
# ModelFactory
# ---------------------------------------------------------------------------
class TestModelFactory:
    """Tests for centralized model instantiation."""

    def test_get_model_default(self):
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        model = ModelFactory.get_model("default")
        assert model is not None
        assert isinstance(model, nn.Module)

    def test_get_model_jepa(self):
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        model = ModelFactory.get_model("jepa")
        assert model is not None

    def test_get_model_vl_jepa(self):
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        model = ModelFactory.get_model("vl-jepa")
        assert model is not None

    def test_get_model_rap(self):
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        model = ModelFactory.get_model("rap")
        assert model is not None

    def test_get_model_role_head(self):
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        model = ModelFactory.get_model("role_head")
        assert model is not None

    def test_get_model_invalid_type(self):
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        with pytest.raises(ValueError, match="Unknown model type"):
            ModelFactory.get_model("nonexistent")

    def test_get_checkpoint_name_all_types(self):
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        expected = {
            "default": "latest",
            "jepa": "jepa_brain",
            "vl-jepa": "vl_jepa_brain",
            "rap": "rap_coach",
            "role_head": "role_head",
        }
        for mtype, name in expected.items():
            assert ModelFactory.get_checkpoint_name(mtype) == name

    def test_get_checkpoint_name_invalid(self):
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        with pytest.raises(ValueError, match="Unknown model type for checkpoint"):
            ModelFactory.get_checkpoint_name("nonexistent")

    def test_kwargs_passthrough(self):
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        model = ModelFactory.get_model("default", input_dim=10, output_dim=5, hidden_dim=32)
        assert model is not None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
class TestPersistence:
    """Tests for model checkpoint save/load."""

    def test_get_model_path_global(self, tmp_path, monkeypatch):
        import Programma_CS2_RENAN.backend.nn.persistence as pers

        monkeypatch.setattr(pers, "BASE_NN_DIR", tmp_path)
        path = pers.get_model_path("v1")
        assert "global" in str(path)
        assert path.name == "v1.pt"

    def test_get_model_path_user(self, tmp_path, monkeypatch):
        import Programma_CS2_RENAN.backend.nn.persistence as pers

        monkeypatch.setattr(pers, "BASE_NN_DIR", tmp_path)
        path = pers.get_model_path("v1", user_id="player123")
        assert "player123" in str(path)

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        import Programma_CS2_RENAN.backend.nn.persistence as pers

        monkeypatch.setattr(pers, "BASE_NN_DIR", tmp_path)
        torch.manual_seed(42)
        model = nn.Linear(10, 5)
        original_weight = model.weight.data.clone()
        pers.save_nn(model, "test_v1")
        # Create fresh model with different weights
        model2 = nn.Linear(10, 5)
        assert not torch.allclose(model2.weight.data, original_weight)
        loaded = pers.load_nn("test_v1", model2)
        assert torch.allclose(loaded.weight.data, original_weight)

    def test_stale_checkpoint_error(self, tmp_path, monkeypatch):
        import Programma_CS2_RENAN.backend.nn.persistence as pers

        monkeypatch.setattr(pers, "BASE_NN_DIR", tmp_path)
        # Save a model with dim=10
        model_old = nn.Linear(10, 5)
        pers.save_nn(model_old, "stale_v1")
        # Try to load into a model with dim=20 (architecture upgrade)
        model_new = nn.Linear(20, 5)
        with pytest.raises(pers.StaleCheckpointError):
            pers.load_nn("stale_v1", model_new)

    def test_load_missing_model(self, tmp_path, monkeypatch):
        import Programma_CS2_RENAN.backend.nn.persistence as pers

        monkeypatch.setattr(pers, "BASE_NN_DIR", tmp_path)
        # Monkeypatch get_resource_path to return a non-existent path too
        monkeypatch.setattr(
            pers, "get_factory_model_path",
            lambda version, user_id=None: tmp_path / "no_exist" / f"{version}.pt",
        )
        model = nn.Linear(10, 5)
        original_weight = model.weight.data.clone()
        loaded = pers.load_nn("nonexistent_v99", model)
        # Model should be returned with its original (random) weights
        assert torch.allclose(loaded.weight.data, original_weight)


# ---------------------------------------------------------------------------
# SuperpositionLayer
# ---------------------------------------------------------------------------
class TestSuperpositionLayer:
    """Tests for context-gated superposition MLP."""

    def test_forward_shape(self):
        from Programma_CS2_RENAN.backend.nn.layers.superposition import SuperpositionLayer

        layer = SuperpositionLayer(in_features=256, out_features=128, context_dim=METADATA_DIM)
        layer.eval()
        x = torch.randn(3, 256)
        ctx = torch.randn(3, METADATA_DIM)
        out = layer(x, ctx)
        assert out.shape == (3, 128)

    def test_gate_activations_stored(self):
        from Programma_CS2_RENAN.backend.nn.layers.superposition import SuperpositionLayer

        layer = SuperpositionLayer(256, 128, METADATA_DIM)
        layer.eval()
        assert layer.get_gate_activations() is None
        layer(torch.randn(2, 256), torch.randn(2, METADATA_DIM))
        assert layer.get_gate_activations() is not None
        assert layer.get_gate_activations().shape == (2, 128)

    def test_gate_statistics(self):
        from Programma_CS2_RENAN.backend.nn.layers.superposition import SuperpositionLayer

        layer = SuperpositionLayer(256, 128, METADATA_DIM)
        layer.eval()
        layer(torch.randn(4, 256), torch.randn(4, METADATA_DIM))
        stats = layer.get_gate_statistics()
        assert "mean_activation" in stats
        assert "std_activation" in stats
        assert "sparsity" in stats
        assert "active_ratio" in stats
        assert "top_3_dims" in stats
        assert "bottom_3_dims" in stats

    def test_gate_statistics_no_forward(self):
        from Programma_CS2_RENAN.backend.nn.layers.superposition import SuperpositionLayer

        layer = SuperpositionLayer(256, 128, METADATA_DIM)
        stats = layer.get_gate_statistics()
        assert stats == {"error": "no_activations_recorded"}

    def test_gate_sparsity_loss(self):
        from Programma_CS2_RENAN.backend.nn.layers.superposition import SuperpositionLayer

        layer = SuperpositionLayer(256, 128, METADATA_DIM)
        layer.eval()
        layer(torch.randn(2, 256), torch.randn(2, METADATA_DIM))
        loss = layer.gate_sparsity_loss()
        assert loss.ndim == 0  # scalar
        assert loss.item() >= 0.0

    def test_gate_sparsity_loss_no_forward(self):
        from Programma_CS2_RENAN.backend.nn.layers.superposition import SuperpositionLayer

        layer = SuperpositionLayer(256, 128, METADATA_DIM)
        loss = layer.gate_sparsity_loss()
        assert loss.item() == 0.0

    def test_context_gate_modulation(self):
        from Programma_CS2_RENAN.backend.nn.layers.superposition import SuperpositionLayer

        torch.manual_seed(42)
        layer = SuperpositionLayer(256, 128, METADATA_DIM)
        layer.eval()
        x = torch.randn(2, 256)
        ctx1 = torch.randn(2, METADATA_DIM)
        ctx2 = torch.randn(2, METADATA_DIM) * 5.0  # Very different context
        out1 = layer(x, ctx1)
        out2 = layer(x, ctx2)
        # Different contexts should produce different outputs
        assert not torch.allclose(out1, out2)

    def test_enable_disable_tracing(self):
        from Programma_CS2_RENAN.backend.nn.layers.superposition import SuperpositionLayer

        layer = SuperpositionLayer(256, 128, METADATA_DIM)
        assert layer._gate_stats_log_interval == 100
        layer.enable_tracing(interval=1)
        assert layer._gate_stats_log_interval == 1
        layer.disable_tracing()
        assert layer._gate_stats_log_interval == 100
