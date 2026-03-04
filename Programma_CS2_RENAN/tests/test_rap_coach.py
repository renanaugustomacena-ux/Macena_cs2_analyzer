"""
Tests for RAP Coach Architecture — Phase 1 Coverage Expansion.

Covers all 7 layers of the RAPCoachModel:
  Perception (ResNetBlock, RAPPerception)
  Memory (RAPMemory — LTC + Hopfield)
  Strategy (ContextualAttention, RAPStrategy — Superposition + MoE)
  Pedagogy (RAPPedagogy, CausalAttributor)
  Model (RAPCoachModel full forward + sparsity)
  Communication (RAPCommunication — skill-tiered advice)
  Trainer (RAPTrainer — train_step + position loss)
"""

import sys


import pytest
import torch

from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM


# ---------------------------------------------------------------------------
# Perception Layer
# ---------------------------------------------------------------------------
class TestResNetBlock:
    """Tests for ResNetBlock (residual building block)."""

    def test_identity_shortcut_same_channels(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.perception import ResNetBlock

        block = ResNetBlock(in_channels=32, out_channels=32, stride=1)
        # Identity shortcut should be nn.Sequential() with 0 children
        assert len(list(block.shortcut.children())) == 0

    def test_projection_shortcut_different_channels(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.perception import ResNetBlock

        block = ResNetBlock(in_channels=16, out_channels=32, stride=2)
        # Projection shortcut should have Conv2d + BN
        children = list(block.shortcut.children())
        assert len(children) == 2

    def test_output_shape_stride1(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.perception import ResNetBlock

        block = ResNetBlock(32, 32, stride=1)
        block.eval()
        x = torch.randn(2, 32, 16, 16)
        out = block(x)
        assert out.shape == (2, 32, 16, 16)

    def test_output_shape_stride2(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.perception import ResNetBlock

        block = ResNetBlock(16, 32, stride=2)
        block.eval()
        x = torch.randn(2, 16, 32, 32)
        out = block(x)
        assert out.shape == (2, 32, 16, 16)

    def test_gradient_flow(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.perception import ResNetBlock

        block = ResNetBlock(16, 32, stride=2)
        x = torch.randn(2, 16, 32, 32, requires_grad=True)
        out = block(x)
        out.sum().backward()
        assert x.grad is not None
        assert x.grad.shape == x.shape


class TestRAPPerception:
    """Tests for the multi-module perception layer."""

    def test_output_dim_is_128(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.perception import RAPPerception

        p = RAPPerception()
        p.eval()
        view = torch.randn(1, 3, 64, 64)
        mp = torch.randn(1, 3, 64, 64)
        motion = torch.randn(1, 3, 64, 64)
        out = p(view, mp, motion)
        assert out.shape == (1, 128)

    def test_forward_batch(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.perception import RAPPerception

        p = RAPPerception()
        p.eval()
        B = 4
        out = p(torch.randn(B, 3, 64, 64), torch.randn(B, 3, 64, 64), torch.randn(B, 3, 64, 64))
        assert out.shape == (B, 128)

    def test_no_nan_output(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.perception import RAPPerception

        torch.manual_seed(99)
        p = RAPPerception()
        p.eval()
        out = p(torch.randn(2, 3, 64, 64), torch.randn(2, 3, 64, 64), torch.randn(2, 3, 64, 64))
        assert not torch.isnan(out).any()

    def test_different_spatial_sizes(self):
        """AdaptiveAvgPool2d should handle non-64x64 inputs."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.perception import RAPPerception

        p = RAPPerception()
        p.eval()
        # 32x32 input
        out = p(torch.randn(1, 3, 32, 32), torch.randn(1, 3, 32, 32), torch.randn(1, 3, 32, 32))
        assert out.shape == (1, 128)


# ---------------------------------------------------------------------------
# Memory Layer
# ---------------------------------------------------------------------------
class TestRAPMemory:
    """Tests for the LTC-Hopfield recurrent belief state."""

    def test_output_shapes(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.memory import RAPMemory

        perception_dim = 128
        hidden_dim = 256
        mem = RAPMemory(perception_dim, METADATA_DIM, hidden_dim)
        mem.eval()
        B, seq = 2, 5
        x = torch.randn(B, seq, perception_dim + METADATA_DIM)
        combined, belief, hidden = mem(x)
        assert combined.shape == (B, seq, hidden_dim)
        assert belief.shape == (B, seq, 64)

    def test_hidden_state_passthrough(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.memory import RAPMemory

        mem = RAPMemory(128, METADATA_DIM, 256)
        mem.eval()
        x = torch.randn(2, 5, 128 + METADATA_DIM)
        _, _, hidden1 = mem(x)
        # Pass hidden from step 1 to step 2
        _, _, hidden2 = mem(x, hidden1)
        assert hidden2 is not None

    def test_no_nan_output(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.memory import RAPMemory

        torch.manual_seed(42)
        mem = RAPMemory(128, METADATA_DIM, 256)
        mem.eval()
        x = torch.randn(2, 5, 128 + METADATA_DIM)
        combined, belief, _ = mem(x)
        assert not torch.isnan(combined).any()
        assert not torch.isnan(belief).any()


# ---------------------------------------------------------------------------
# Strategy Layer
# ---------------------------------------------------------------------------
class TestContextualAttention:
    """Tests for saliency-weighted feature aggregation."""

    def test_attention_shape(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.strategy import ContextualAttention

        attn = ContextualAttention(feature_dim=256, context_dim=METADATA_DIM)
        attn.eval()
        features = torch.randn(2, 5, 256)  # (B, seq, feature_dim)
        context = torch.randn(2, METADATA_DIM)
        probs = attn(features, context)
        assert probs.shape == (2, 1, 5)

    def test_softmax_sums_to_one(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.strategy import ContextualAttention

        attn = ContextualAttention(feature_dim=256, context_dim=METADATA_DIM)
        attn.eval()
        probs = attn(torch.randn(3, 8, 256), torch.randn(3, METADATA_DIM))
        sums = probs.sum(dim=-1)
        assert torch.allclose(sums, torch.ones_like(sums), atol=1e-5)


class TestRAPStrategy:
    """Tests for the MoE strategy layer with Superposition."""

    def test_output_shape(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.strategy import RAPStrategy

        strat = RAPStrategy(hidden_dim=256, output_dim=10, context_dim=METADATA_DIM)
        strat.eval()
        pred, gate = strat(torch.randn(2, 256), torch.randn(2, METADATA_DIM))
        assert pred.shape == (2, 10)
        assert gate.shape == (2, 4)  # 4 experts default

    def test_gate_weights_sum_to_one(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.strategy import RAPStrategy

        strat = RAPStrategy(256, 10)
        strat.eval()
        _, gate = strat(torch.randn(3, 256), torch.randn(3, METADATA_DIM))
        sums = gate.sum(dim=-1)
        assert torch.allclose(sums, torch.ones_like(sums), atol=1e-5)

    def test_custom_num_experts(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.strategy import RAPStrategy

        strat = RAPStrategy(256, 10, num_experts=8)
        strat.eval()
        _, gate = strat(torch.randn(2, 256), torch.randn(2, METADATA_DIM))
        assert gate.shape == (2, 8)
        assert len(strat.experts) == 8


# ---------------------------------------------------------------------------
# Pedagogy Layer
# ---------------------------------------------------------------------------
class TestRAPPedagogy:
    """Tests for the causal feedback / value estimation layer."""

    def test_value_output_shape(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.pedagogy import RAPPedagogy

        ped = RAPPedagogy(hidden_dim=256)
        ped.eval()
        value = ped(torch.randn(2, 256))
        assert value.shape == (2, 1)

    def test_with_skill_vec(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.pedagogy import RAPPedagogy

        torch.manual_seed(42)
        ped = RAPPedagogy(256)
        ped.eval()
        h = torch.randn(2, 256)
        v_no_skill = ped(h, skill_vec=None)
        v_with_skill = ped(h, skill_vec=torch.ones(2, 10))
        # Should produce different values
        assert not torch.allclose(v_no_skill, v_with_skill)

    def test_advantage_gap(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.pedagogy import RAPPedagogy

        ped = RAPPedagogy(256)
        value_pred = torch.tensor([[0.5]])
        actual = torch.tensor([[1.0]])
        gap = ped.calculate_advantage_gap(value_pred, actual)
        assert torch.allclose(gap, torch.tensor([[0.5]]))


class TestCausalAttributor:
    """Tests for the causal attribution head."""

    def test_diagnose_shape(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.pedagogy import CausalAttributor

        attr = CausalAttributor(hidden_dim=256)
        attr.eval()
        scores = attr.diagnose(torch.randn(2, 256), torch.randn(2, 3))
        assert scores.shape == (2, 5)

    def test_concepts_list(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.pedagogy import CausalAttributor

        attr = CausalAttributor(256)
        assert len(attr.concepts) == 5
        assert "Positioning" in attr.concepts
        assert "Utility" in attr.concepts

    def test_with_view_delta(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.pedagogy import CausalAttributor

        attr = CausalAttributor(256)
        attr.eval()
        h = torch.randn(2, 256)
        pos = torch.randn(2, 3)
        view = torch.randn(2, 2)
        scores_no_view = attr.diagnose(h, pos, optimal_view_delta=None)
        scores_with_view = attr.diagnose(h, pos, optimal_view_delta=view)
        # Crosshair Placement (index 1) should differ
        assert not torch.allclose(scores_no_view[:, 1], scores_with_view[:, 1])

    def test_utility_need_bounded(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.pedagogy import CausalAttributor

        attr = CausalAttributor(256)
        attr.eval()
        h = torch.randn(10, 256)
        util = attr._detect_utility_need(h)
        assert (util >= 0.0).all()
        assert (util <= 1.0).all()


# ---------------------------------------------------------------------------
# Full RAPCoachModel
# ---------------------------------------------------------------------------
class TestRAPCoachModel:
    """End-to-end tests for the full 7-layer model."""

    def test_forward_output_keys(self, rap_model, rap_inputs, torch_no_grad):
        out = rap_model(
            rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
            rap_inputs["metadata"], rap_inputs["skill_vec"],
        )
        expected_keys = {"advice_probs", "belief_state", "value_estimate",
                         "gate_weights", "optimal_pos", "attribution"}
        assert set(out.keys()) == expected_keys

    def test_advice_probs_shape(self, rap_model, rap_inputs, torch_no_grad):
        out = rap_model(
            rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
            rap_inputs["metadata"],
        )
        assert out["advice_probs"].shape == (2, 10)

    def test_belief_state_shape(self, rap_model, rap_inputs, torch_no_grad):
        out = rap_model(
            rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
            rap_inputs["metadata"],
        )
        assert out["belief_state"].shape == (2, 5, 64)

    def test_value_estimate_shape(self, rap_model, rap_inputs, torch_no_grad):
        out = rap_model(
            rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
            rap_inputs["metadata"],
        )
        assert out["value_estimate"].shape == (2, 1)

    def test_gate_weights_shape(self, rap_model, rap_inputs, torch_no_grad):
        out = rap_model(
            rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
            rap_inputs["metadata"],
        )
        assert out["gate_weights"].shape == (2, 4)

    def test_optimal_pos_shape(self, rap_model, rap_inputs, torch_no_grad):
        out = rap_model(
            rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
            rap_inputs["metadata"],
        )
        assert out["optimal_pos"].shape == (2, 3)

    def test_attribution_shape(self, rap_model, rap_inputs, torch_no_grad):
        out = rap_model(
            rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
            rap_inputs["metadata"],
        )
        assert out["attribution"].shape == (2, 5)

    def test_sparsity_loss_with_gate(self, rap_model, rap_inputs, torch_no_grad):
        out = rap_model(
            rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
            rap_inputs["metadata"],
        )
        loss = rap_model.compute_sparsity_loss(out["gate_weights"])
        assert loss.ndim == 0  # scalar
        assert loss.item() > 0.0

    def test_sparsity_loss_none(self, rap_model):
        loss = rap_model.compute_sparsity_loss(None)
        assert loss.item() == 0.0

    def test_no_nan_in_outputs(self, rap_model, rap_inputs, torch_no_grad):
        out = rap_model(
            rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
            rap_inputs["metadata"],
        )
        for key, tensor in out.items():
            assert not torch.isnan(tensor).any(), f"NaN detected in {key}"

    def test_deterministic_with_seed(self, rap_inputs):
        from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel

        torch.manual_seed(123)
        m1 = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
        m1.eval()
        with torch.no_grad():
            out1 = m1(rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
                       rap_inputs["metadata"])

        torch.manual_seed(123)
        m2 = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
        m2.eval()
        with torch.no_grad():
            out2 = m2(rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
                       rap_inputs["metadata"])

        assert torch.allclose(out1["advice_probs"], out2["advice_probs"], atol=1e-5)

    def test_without_skill_vec(self, rap_model, rap_inputs, torch_no_grad):
        out = rap_model(
            rap_inputs["view"], rap_inputs["map"], rap_inputs["motion"],
            rap_inputs["metadata"], skill_vec=None,
        )
        assert out["value_estimate"].shape == (2, 1)

    def test_heuristic_config_custom_l1(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel

        class MockConfig:
            context_gate_l1_weight = 0.01

        model = RAPCoachModel(heuristic_config=MockConfig())
        assert model.context_gate_l1_weight == 0.01


# ---------------------------------------------------------------------------
# Communication Layer
# ---------------------------------------------------------------------------
class TestRAPCommunication:
    """Tests for the skill-tiered advice generator."""

    def test_low_confidence_suppresses_advice(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.communication import RAPCommunication

        comm = RAPCommunication()
        result = comm.generate_advice(torch.tensor([0.5, 0.3, 0.2]), confidence=0.5)
        assert result is None

    def test_low_skill_tier(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.communication import RAPCommunication

        comm = RAPCommunication()
        result = comm.generate_advice(torch.tensor([0.9, 0.1, 0.1]), confidence=0.8, skill_level=2)
        assert result is not None
        assert isinstance(result, str)

    def test_mid_skill_tier(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.communication import RAPCommunication

        comm = RAPCommunication()
        result = comm.generate_advice(torch.tensor([0.1, 0.8, 0.1]), confidence=0.85, skill_level=5)
        assert result is not None

    def test_high_skill_tier(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.communication import RAPCommunication

        comm = RAPCommunication()
        result = comm.generate_advice(torch.tensor([0.1, 0.1, 0.9]), confidence=0.9, skill_level=9)
        assert result is not None

    def test_output_is_string(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.communication import RAPCommunication

        comm = RAPCommunication()
        result = comm.generate_advice(torch.tensor([1.0, 0.0, 0.0]), confidence=0.75, skill_level=5)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_default_skill_level(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.communication import RAPCommunication

        comm = RAPCommunication()
        # Default skill_level=5 -> mid tier
        result = comm.generate_advice(torch.tensor([0.5, 0.5, 0.1]), confidence=0.8)
        assert result is not None


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------
class TestRAPTrainer:
    """Tests for the RAP training orchestrator."""

    def test_train_step_returns_metrics(self, rap_inputs):
        from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel
        from Programma_CS2_RENAN.backend.nn.rap_coach.trainer import RAPTrainer

        torch.manual_seed(42)
        model = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
        trainer = RAPTrainer(model, lr=1e-4)
        batch = {
            "view": rap_inputs["view"],
            "map": rap_inputs["map"],
            "motion": rap_inputs["motion"],
            "metadata": rap_inputs["metadata"],
            "target_strat": torch.randn(2, 10),
            "target_val": torch.randn(2, 1),
        }
        metrics = trainer.train_step(batch)
        assert "loss" in metrics
        assert "sparsity_ratio" in metrics
        assert "loss_pos" in metrics
        assert "z_error" in metrics
        assert isinstance(metrics["loss"], float)

    def test_loss_decreases_over_steps(self, rap_inputs):
        from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel
        from Programma_CS2_RENAN.backend.nn.rap_coach.trainer import RAPTrainer

        torch.manual_seed(42)
        model = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
        trainer = RAPTrainer(model, lr=1e-3)
        batch = {
            "view": rap_inputs["view"],
            "map": rap_inputs["map"],
            "motion": rap_inputs["motion"],
            "metadata": rap_inputs["metadata"],
            "target_strat": torch.zeros(2, 10),
            "target_val": torch.zeros(2, 1),
        }
        losses = []
        for _ in range(10):
            m = trainer.train_step(batch)
            losses.append(m["loss"])
        # Loss should generally decrease (last < first)
        assert losses[-1] < losses[0], f"Loss did not decrease: {losses[0]:.4f} -> {losses[-1]:.4f}"

    def test_position_loss_z_penalty(self, rap_inputs):
        from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel
        from Programma_CS2_RENAN.backend.nn.rap_coach.trainer import RAPTrainer

        model = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
        trainer = RAPTrainer(model)
        assert trainer.z_axis_penalty_weight == 2.0

    def test_compute_position_loss_weighted(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel
        from Programma_CS2_RENAN.backend.nn.rap_coach.trainer import RAPTrainer

        model = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
        trainer = RAPTrainer(model)
        pred = torch.tensor([[0.0, 0.0, 1.0]])
        target = torch.tensor([[0.0, 0.0, 0.0]])
        loss, z_err = trainer.compute_position_loss(pred, target)
        # Z error should be 1.0, loss should include 2.0 * 1.0 = 2.0
        assert abs(z_err - 1.0) < 1e-5
        assert loss.item() > 1.5  # At least the Z penalty contribution

    def test_train_step_with_target_pos(self, rap_inputs):
        from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel
        from Programma_CS2_RENAN.backend.nn.rap_coach.trainer import RAPTrainer

        torch.manual_seed(42)
        model = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
        trainer = RAPTrainer(model)
        batch = {
            "view": rap_inputs["view"],
            "map": rap_inputs["map"],
            "motion": rap_inputs["motion"],
            "metadata": rap_inputs["metadata"],
            "target_strat": torch.randn(2, 10),
            "target_val": torch.randn(2, 1),
            "target_pos": torch.randn(2, 3),
        }
        metrics = trainer.train_step(batch)
        assert metrics["loss_pos"] > 0.0

    def test_train_step_without_target_pos(self, rap_inputs):
        from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel
        from Programma_CS2_RENAN.backend.nn.rap_coach.trainer import RAPTrainer

        torch.manual_seed(42)
        model = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
        trainer = RAPTrainer(model)
        batch = {
            "view": rap_inputs["view"],
            "map": rap_inputs["map"],
            "motion": rap_inputs["motion"],
            "metadata": rap_inputs["metadata"],
            "target_strat": torch.randn(2, 10),
            "target_val": torch.randn(2, 1),
        }
        metrics = trainer.train_step(batch)
        assert metrics["loss_pos"] == 0.0
        assert metrics["z_error"] == 0.0
