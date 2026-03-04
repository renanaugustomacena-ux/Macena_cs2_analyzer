"""
Unit tests for JEPA coaching model.

Tests model architecture, forward passes, and training components.
"""

import sys


import numpy as np
import pytest
import torch

from Programma_CS2_RENAN.backend.nn.jepa_model import (
    COACHING_CONCEPTS,
    CONCEPT_NAMES,
    NUM_COACHING_CONCEPTS,
    ConceptLabeler,
    JEPACoachingModel,
    JEPAEncoder,
    JEPAPredictor,
    VLJEPACoachingModel,
    jepa_contrastive_loss,
    vl_jepa_concept_loss,
)
from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM


class TestJEPAComponents:
    """Test suite for JEPA model components."""

    def test_jepa_encoder(self):
        """Test JEPA encoder forward pass."""
        encoder = JEPAEncoder(input_dim=METADATA_DIM, latent_dim=128)

        x = torch.randn(4, 10, METADATA_DIM)  # [batch, seq, features]
        output = encoder(x)

        assert output.shape == (4, 10, 128)
        assert not torch.isnan(output).any()

    def test_jepa_predictor(self):
        """Test JEPA predictor forward pass."""
        predictor = JEPAPredictor(latent_dim=128)

        x = torch.randn(4, 128)
        output = predictor(x)

        assert output.shape == (4, 128)
        assert not torch.isnan(output).any()

    def test_jepa_model_initialization(self):
        """Test JEPA model can be initialized."""
        model = JEPACoachingModel(
            input_dim=METADATA_DIM, output_dim=METADATA_DIM, latent_dim=128, hidden_dim=64
        )

        assert model.latent_dim == 128
        assert not model.is_pretrained
        assert len(model.experts) == 3  # Default num_experts

    def test_jepa_pretrain_forward(self):
        """Test JEPA pre-training forward pass."""
        model = JEPACoachingModel(input_dim=METADATA_DIM, output_dim=METADATA_DIM, latent_dim=128)

        x_context = torch.randn(4, 10, METADATA_DIM)
        x_target = torch.randn(4, 10, METADATA_DIM)

        pred, target = model.forward_jepa_pretrain(x_context, x_target)

        assert pred.shape == (4, 128)
        assert target.shape == (4, 128)
        assert not torch.isnan(pred).any()
        assert not torch.isnan(target).any()

    def test_jepa_coaching_forward(self):
        """Test coaching inference forward pass."""
        model = JEPACoachingModel(input_dim=METADATA_DIM, output_dim=METADATA_DIM, latent_dim=128)

        x = torch.randn(4, 15, METADATA_DIM)
        output = model.forward_coaching(x)

        assert output.shape == (4, METADATA_DIM)
        assert not torch.isnan(output).any()

    def test_jepa_coaching_with_role(self):
        """Test coaching with role bias."""
        model = JEPACoachingModel(input_dim=METADATA_DIM, output_dim=METADATA_DIM, latent_dim=128)

        x = torch.randn(4, 15, METADATA_DIM)
        output = model.forward_coaching(x, role_id=1)

        assert output.shape == (4, METADATA_DIM)
        assert not torch.isnan(output).any()

    def test_freeze_unfreeze_encoders(self):
        """Test encoder freezing/unfreezing."""
        model = JEPACoachingModel(input_dim=METADATA_DIM, output_dim=METADATA_DIM)

        # Initially unfrozen
        assert all(p.requires_grad for p in model.context_encoder.parameters())

        # Freeze
        model.freeze_encoders()
        assert not any(p.requires_grad for p in model.context_encoder.parameters())
        assert model.is_pretrained

        # Unfreeze
        model.unfreeze_encoders()
        assert all(p.requires_grad for p in model.context_encoder.parameters())
        assert not model.is_pretrained

    def test_contrastive_loss(self):
        """Test JEPA contrastive loss computation."""
        batch_size = 4
        latent_dim = 128
        num_negatives = 8

        pred = torch.randn(batch_size, latent_dim)
        target = torch.randn(batch_size, latent_dim)
        negatives = torch.randn(batch_size, num_negatives, latent_dim)

        loss = jepa_contrastive_loss(pred, target, negatives)

        assert loss.item() >= 0  # Loss should be non-negative
        assert not torch.isnan(loss)

    def test_backward_pass(self):
        """Test that gradients flow correctly."""
        model = JEPACoachingModel(input_dim=METADATA_DIM, output_dim=METADATA_DIM, latent_dim=128)

        x_context = torch.randn(2, 10, METADATA_DIM)
        x_target = torch.randn(2, 10, METADATA_DIM)

        pred, target = model.forward_jepa_pretrain(x_context, x_target)

        # Simple MSE loss for testing
        loss = torch.nn.functional.mse_loss(pred, target)
        loss.backward()

        # Check gradients exist (only for JEPA components)
        jepa_params = ["context_encoder", "target_encoder", "predictor"]
        for name, param in model.named_parameters():
            if param.requires_grad and any(comp in name for comp in jepa_params):
                assert param.grad is not None, f"No gradient for {name}"


class TestJEPAIntegration:
    """Integration tests for JEPA model."""

    def test_full_training_cycle(self):
        """Test complete pre-train → freeze → fine-tune cycle."""
        model = JEPACoachingModel(input_dim=METADATA_DIM, output_dim=METADATA_DIM, latent_dim=64)

        # Pre-training
        x_context = torch.randn(8, 10, METADATA_DIM)
        x_target = torch.randn(8, 10, METADATA_DIM)

        pred, target = model.forward_jepa_pretrain(x_context, x_target)
        assert pred.shape == (8, 64)

        # Freeze encoders
        model.freeze_encoders()
        assert model.is_pretrained

        # Fine-tuning
        x_finetune = torch.randn(8, 15, METADATA_DIM)
        output = model.forward_coaching(x_finetune)
        assert output.shape == (8, METADATA_DIM)

    def test_model_save_load(self):
        """Test model can be saved and loaded."""
        import tempfile

        model = JEPACoachingModel(input_dim=METADATA_DIM, output_dim=METADATA_DIM)
        model.freeze_encoders()

        # Save
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            torch.save(
                {"model_state_dict": model.state_dict(), "is_pretrained": model.is_pretrained},
                f.name,
            )

            # Load
            checkpoint = torch.load(f.name, weights_only=True)
            model2 = JEPACoachingModel(input_dim=METADATA_DIM, output_dim=METADATA_DIM)
            model2.load_state_dict(checkpoint["model_state_dict"])
            model2.is_pretrained = checkpoint["is_pretrained"]

            assert model2.is_pretrained == True


class TestVLJEPAComponents:
    """Test suite for VL-JEPA coaching concept alignment."""

    def test_vl_jepa_subclass_init(self):
        """VLJEPACoachingModel initializes and is a JEPACoachingModel subclass."""
        model = VLJEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=128,
            hidden_dim=64,
        )
        assert isinstance(model, JEPACoachingModel)
        assert model.num_concepts == NUM_COACHING_CONCEPTS
        assert model.concept_embeddings.weight.shape == (NUM_COACHING_CONCEPTS, 128)

    def test_forward_vl_output_shape(self):
        """forward_vl returns dict with correct tensor shapes."""
        model = VLJEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
        )
        x = torch.randn(4, 10, METADATA_DIM)
        result = model.forward_vl(x)

        assert result["concept_probs"].shape == (4, NUM_COACHING_CONCEPTS)
        assert result["concept_logits"].shape == (4, NUM_COACHING_CONCEPTS)
        assert result["coaching_output"].shape == (4, METADATA_DIM)
        assert result["latent"].shape == (4, 64)
        assert not torch.isnan(result["concept_probs"]).any()

    def test_concept_probs_sum_to_one(self):
        """Softmax concept probabilities sum to ~1 per sample."""
        model = VLJEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
        )
        x = torch.randn(8, 5, METADATA_DIM)
        result = model.forward_vl(x)
        sums = result["concept_probs"].sum(dim=-1)
        assert torch.allclose(sums, torch.ones(8), atol=1e-5)

    def test_top_concepts_decoding(self):
        """top_concepts returns valid (name, probability) tuples."""
        model = VLJEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
        )
        x = torch.randn(2, 5, METADATA_DIM)
        result = model.forward_vl(x)

        top = result["top_concepts"]
        assert len(top) == 3
        for name, prob in top:
            assert name in CONCEPT_NAMES
            assert 0.0 <= prob <= 1.0

    def test_get_concept_activations(self):
        """Lightweight concept-only path returns correct shape."""
        model = VLJEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
        )
        x = torch.randn(4, 10, METADATA_DIM)
        probs = model.get_concept_activations(x)
        assert probs.shape == (4, NUM_COACHING_CONCEPTS)
        assert torch.allclose(probs.sum(dim=-1), torch.ones(4), atol=1e-5)

    def test_parent_forward_paths_preserved(self):
        """All inherited forward paths work unchanged."""
        model = VLJEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
        )
        x = torch.randn(2, 10, METADATA_DIM)

        # forward (delegates to forward_coaching)
        out = model(x)
        assert out.shape == (2, METADATA_DIM)

        # forward_coaching with role
        out_role = model.forward_coaching(x, role_id=1)
        assert out_role.shape == (2, METADATA_DIM)

        # forward_jepa_pretrain
        pred, tgt = model.forward_jepa_pretrain(x, x)
        assert pred.shape == (2, 64)

        # forward_selective
        pred_s, emb, decoded = model.forward_selective(x)
        assert decoded is True
        assert emb.shape == (2, 10, 64)


class TestConceptLabeler:
    """Test suite for heuristic concept label generation."""

    def test_label_tick_output_shape(self):
        """label_tick returns [16] tensor."""
        labeler = ConceptLabeler()
        features = torch.zeros(METADATA_DIM)
        labels = labeler.label_tick(features)
        assert labels.shape == (NUM_COACHING_CONCEPTS,)

    def test_label_tick_range(self):
        """All labels are in [0, 1]."""
        labeler = ConceptLabeler()
        # Random features in normalized range
        features = torch.rand(METADATA_DIM)
        labels = labeler.label_tick(features)
        assert (labels >= 0.0).all()
        assert (labels <= 1.0).all()

    def test_positioning_exposed(self):
        """Low HP + enemies visible → positioning_exposed activates."""
        labeler = ConceptLabeler()
        features = torch.zeros(METADATA_DIM)
        features[0] = 0.2  # low HP
        features[8] = 0.5  # enemies visible
        labels = labeler.label_tick(features)
        assert labels[2] > 0.5  # positioning_exposed

    def test_economy_wasteful_pistol_round(self):
        """High equip in pistol round → economy_wasteful activates."""
        labeler = ConceptLabeler()
        features = torch.zeros(METADATA_DIM)
        features[4] = 0.5  # high equipment
        features[18] = 0.1  # pistol round
        labels = labeler.label_tick(features)
        assert labels[6] > 0.5  # economy_wasteful

    def test_trade_isolated_low_kast(self):
        """Low KAST → trade_isolated activates."""
        labeler = ConceptLabeler()
        features = torch.zeros(METADATA_DIM)
        features[16] = 0.1  # very low KAST
        labels = labeler.label_tick(features)
        assert labels[10] > 0.5  # trade_isolated

    def test_label_batch_2d(self):
        """label_batch works with [batch, METADATA_DIM] input."""
        labeler = ConceptLabeler()
        batch = torch.rand(8, METADATA_DIM)
        labels = labeler.label_batch(batch)
        assert labels.shape == (8, NUM_COACHING_CONCEPTS)

    def test_label_batch_3d(self):
        """label_batch works with [batch, seq_len, METADATA_DIM] input."""
        labeler = ConceptLabeler()
        batch = torch.rand(4, 10, METADATA_DIM)
        labels = labeler.label_batch(batch)
        assert labels.shape == (4, NUM_COACHING_CONCEPTS)


class TestVLJEPATraining:
    """Test suite for VL-JEPA training loss and gradients."""

    def test_concept_loss_computation(self):
        """vl_jepa_concept_loss returns valid loss components."""
        concept_logits = torch.randn(4, NUM_COACHING_CONCEPTS)
        concept_labels = torch.rand(4, NUM_COACHING_CONCEPTS)
        concept_embs = torch.randn(NUM_COACHING_CONCEPTS, 64)

        total, concept, diversity = vl_jepa_concept_loss(
            concept_logits,
            concept_labels,
            concept_embs,
        )
        assert not torch.isnan(total)
        assert not torch.isnan(concept)
        assert not torch.isnan(diversity)
        assert concept.item() >= 0  # BCE is non-negative

    def test_diversity_loss_prevents_collapse(self):
        """Identical concept embeddings produce higher diversity loss."""
        concept_logits = torch.randn(4, NUM_COACHING_CONCEPTS)
        concept_labels = torch.rand(4, NUM_COACHING_CONCEPTS)

        # Collapsed: all embeddings identical
        collapsed = torch.ones(NUM_COACHING_CONCEPTS, 64)
        _, _, div_collapsed = vl_jepa_concept_loss(
            concept_logits,
            concept_labels,
            collapsed,
        )

        # Diverse: random embeddings
        diverse = torch.randn(NUM_COACHING_CONCEPTS, 64)
        _, _, div_diverse = vl_jepa_concept_loss(
            concept_logits,
            concept_labels,
            diverse,
        )

        # Collapsed should have worse (higher / less negative) diversity loss
        # Since diversity_loss = -std.mean(), collapsed → std≈0 → loss≈0
        # Diverse → std>0 → loss<0 (better)
        assert div_diverse < div_collapsed

    def test_backward_pass(self):
        """Gradients flow through concept alignment head."""
        model = VLJEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
        )
        x = torch.randn(2, 5, METADATA_DIM)
        result = model.forward_vl(x)

        labeler = ConceptLabeler()
        concept_labels = labeler.label_batch(x)

        total, _, _ = vl_jepa_concept_loss(
            result["concept_logits"],
            concept_labels,
            model.concept_embeddings.weight,
        )
        total.backward()

        assert model.concept_embeddings.weight.grad is not None
        assert model.concept_projector[0].weight.grad is not None
        # concept_temperature is used in softmax (inference path), not in
        # BCE loss (training path on raw logits), so no gradient expected here


class TestVLJEPACheckpointMigration:
    """Test loading a JEPA checkpoint into a VL-JEPA model."""

    def test_jepa_checkpoint_loads_into_vl_jepa(self):
        """JEPA state_dict loads into VLJEPACoachingModel with strict=False."""
        jepa = JEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
        )
        state = jepa.state_dict()

        vl = VLJEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
        )
        missing, unexpected = vl.load_state_dict(state, strict=False)

        # Missing keys should be exactly the concept-alignment layers
        missing_prefixes = {k.split(".")[0] for k in missing}
        assert "concept_embeddings" in missing_prefixes
        assert "concept_projector" in missing_prefixes
        assert "concept_temperature" in [k for k in missing]
        assert len(unexpected) == 0

    def test_vl_jepa_works_after_migration(self):
        """VL-JEPA produces valid output after loading JEPA checkpoint."""
        jepa = JEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
        )
        state = jepa.state_dict()

        vl = VLJEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
        )
        vl.load_state_dict(state, strict=False)

        x = torch.randn(2, 5, METADATA_DIM)
        result = vl.forward_vl(x)
        assert result["concept_probs"].shape == (2, NUM_COACHING_CONCEPTS)
        assert not torch.isnan(result["concept_probs"]).any()


class TestVLJEPAIntegration:
    """End-to-end integration: pre-train → concept-align → fine-tune."""

    def test_full_vl_jepa_cycle(self):
        """Complete VL-JEPA lifecycle preserves correctness."""
        model = VLJEPACoachingModel(
            input_dim=METADATA_DIM,
            output_dim=METADATA_DIM,
            latent_dim=64,
            hidden_dim=32,
        )
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

        # Phase 1: JEPA pre-training
        x_ctx = torch.randn(4, 10, METADATA_DIM)
        x_tgt = torch.randn(4, 10, METADATA_DIM)
        pred, tgt = model.forward_jepa_pretrain(x_ctx, x_tgt)
        negs = torch.randn(4, 3, 64)
        loss_pretrain = jepa_contrastive_loss(pred, tgt, negs)
        loss_pretrain.backward()
        optimizer.step()
        optimizer.zero_grad()

        # Phase 2: Concept alignment
        result = model.forward_vl(x_ctx)
        labeler = ConceptLabeler()
        labels = labeler.label_batch(x_ctx)
        total, _, _ = vl_jepa_concept_loss(
            result["concept_logits"],
            labels,
            model.concept_embeddings.weight,
        )
        total.backward()
        optimizer.step()
        optimizer.zero_grad()

        # Phase 3: Freeze encoders, fine-tune coaching head
        model.freeze_encoders()
        assert model.is_pretrained

        x_ft = torch.randn(4, 15, METADATA_DIM)
        coaching_out = model.forward_coaching(x_ft)
        assert coaching_out.shape == (4, METADATA_DIM)

        # Concepts still work after freeze
        result2 = model.forward_vl(x_ft)
        assert result2["concept_probs"].shape == (4, NUM_COACHING_CONCEPTS)

    def test_factory_produces_correct_type(self):
        """ModelFactory.get_model('vl-jepa') returns VLJEPACoachingModel."""
        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

        model = ModelFactory.get_model("vl-jepa")
        assert isinstance(model, VLJEPACoachingModel)
        assert isinstance(model, JEPACoachingModel)

    def test_coaching_concepts_metadata(self):
        """COACHING_CONCEPTS list has correct structure."""
        assert len(COACHING_CONCEPTS) == NUM_COACHING_CONCEPTS
        assert len(CONCEPT_NAMES) == NUM_COACHING_CONCEPTS
        # All IDs are sequential 0..15
        for i, c in enumerate(COACHING_CONCEPTS):
            assert c.id == i
            assert len(c.name) > 0
            assert c.dimension in ("positioning", "utility", "decision", "engagement", "psychology")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
