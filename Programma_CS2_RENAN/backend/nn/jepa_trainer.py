from typing import List, Optional

import torch
import torch.optim as optim

from Programma_CS2_RENAN.backend.nn.jepa_model import (
    ConceptLabeler,
    JEPACoachingModel,
    VLJEPACoachingModel,
    jepa_contrastive_loss,
    vl_jepa_concept_loss,
)
from Programma_CS2_RENAN.backend.processing.validation.drift import (
    DriftMonitor,
    DriftReport,
    should_retrain,
)
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.jepa_trainer")


class JEPATrainer:
    """
    Trainer for JEPA (Joint-Embedding Predictive Architecture).
    Handles self-supervised pre-training with drift-triggered retraining (Task 2.19.3).
    """

    def __init__(
        self,
        model: JEPACoachingModel,
        lr: float = 1e-4,
        weight_decay: float = 1e-4,
        drift_threshold: float = 2.5,
    ):
        self.model = model
        # NN-36: Exclude target encoder (EMA-only, never receives gradients)
        trainable = [p for n, p in model.named_parameters() if "target_encoder" not in n]
        self.optimizer = optim.AdamW(trainable, lr=lr, weight_decay=weight_decay)
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(self.optimizer, T_max=100)

        # Task 2.19.3: Drift monitoring for automatic retraining
        self.drift_monitor = DriftMonitor(z_threshold=drift_threshold)
        self.drift_history: List[DriftReport] = []
        self._needs_full_retrain = False
        self._reference_stats: Optional[dict] = None

    def train_step(
        self, x_context: torch.Tensor, x_target: torch.Tensor, negatives: torch.Tensor
    ) -> dict:
        """
        Single self-supervised training step.

        Returns dict with "loss" key for consistency with RAPTrainer and VL-JEPA interfaces.

        Handles two negative-sample paths:
        1. Pre-encoded negatives (from train_epoch dataloader) — shape (B, N, latent_dim)
        2. Raw feature negatives (from TrainingOrchestrator._prepare_batch) — shape (B, N, METADATA_DIM)
           These are auto-detected by dimension mismatch and encoded via target_encoder.
        """
        # NN-TR-03: Validate input tensor shapes before forward pass
        if x_context.ndim != 3:
            raise ValueError(
                f"NN-TR-03: x_context must be 3D (B, seq_len, input_dim), got {x_context.ndim}D"
            )
        if x_target.ndim != 3:
            raise ValueError(
                f"NN-TR-03: x_target must be 3D (B, seq_len, input_dim), got {x_target.ndim}D"
            )
        if x_context.shape[0] != x_target.shape[0]:
            raise ValueError(
                f"NN-TR-03: batch size mismatch: context={x_context.shape[0]}, target={x_target.shape[0]}"
            )

        # NN-JT-03: Ensure input tensors are on the model's device
        device = next(self.model.parameters()).device
        x_context = x_context.to(device)
        x_target = x_target.to(device)
        if negatives is not None:
            negatives = negatives.to(device)

        self.model.train()
        self.optimizer.zero_grad()

        # 1. Forward Pass
        pred_embedding, target_embedding = self.model.forward_jepa_pretrain(x_context, x_target)

        # 2. Encode raw negatives if from orchestrator batch (dimension mismatch = raw features)
        if negatives is not None and negatives.shape[-1] != pred_embedding.shape[-1]:
            with torch.no_grad():
                b, n, d = negatives.shape
                # Treat each negative as a length-1 sequence, expand to match context seq_len
                neg_seqs = negatives.reshape(b * n, 1, d)
                neg_seqs = neg_seqs.expand(-1, x_context.shape[1], -1)
                neg_encoded = self.model.target_encoder(neg_seqs).mean(dim=1)
                negatives = neg_encoded.reshape(b, n, -1)

        # 3. Compute Loss
        loss = jepa_contrastive_loss(pred_embedding, target_embedding, negatives)

        # 4. Optimization
        loss.backward()
        self.optimizer.step()

        # 5. Update Target Encoder (EMA)
        self.model.update_target_encoder()

        # 6. Embedding diversity monitoring (P9-02 acceptance criterion)
        embedding_variance = self._log_embedding_diversity(pred_embedding)

        return {"loss": loss.item(), "embedding_variance": embedding_variance}

    def _log_embedding_diversity(self, embeddings: torch.Tensor) -> float:
        """Monitor embedding collapse risk (P9-02 acceptance criterion).

        Returns the mean variance across latent dimensions. A healthy value
        should be > 0.01; below that indicates potential representation collapse.
        """
        with torch.no_grad():
            variance = embeddings.var(dim=0).mean().item()
            if variance < 0.01:
                logger.warning(
                    "JEPA embedding variance=%.6f — potential collapse detected", variance
                )
            else:
                logger.debug("JEPA embedding variance=%.6f (healthy)", variance)
            return variance

    def train_epoch(self, dataloader, device):
        """
        Train for one epoch.
        """
        total_loss = 0
        count = 0

        for batch in dataloader:
            x_context = batch["context"].to(device)
            x_target = batch["target"].to(device)

            # In-batch negatives: encode all targets once, then exclude self (NN-35 fix)
            batch_size = x_target.size(0)

            # NN-JT-01: In-batch negatives require batch_size > 1 (can't exclude self
            # from a single-element batch). Skip training on degenerate batches.
            if batch_size < 2:
                logger.debug("NN-JT-01: Skipping batch with size %d (need >= 2 for negatives)", batch_size)
                continue

            with torch.no_grad():
                all_encoded = self.model.target_encoder(x_target).mean(dim=1)  # [B, latent]

            # NN-TR-01: O(B²) negative construction — each sample excludes itself.
            # For typical batch sizes (32–128) this is fast. For B > 256 consider
            # vectorised masking: mask = ~torch.eye(B, dtype=bool, device=device)
            indices = torch.arange(batch_size, device=device)
            negatives_tensor = torch.stack(
                [all_encoded[indices != i] for i in range(batch_size)]
            )  # [B, B-1, latent]

            result = self.train_step(x_context, x_target, negatives_tensor)
            total_loss += result["loss"]
            count += 1

        # Step scheduler once per epoch (not per batch)
        self.scheduler.step()

        # NN-TR-02: Warn if dataloader was empty (no batches processed)
        if count == 0:
            logger.warning("NN-TR-02: train_epoch completed with 0 batches — dataloader may be empty")

        return total_loss / max(1, count)

    def check_val_drift(self, val_df, reference_stats: Optional[dict] = None):
        """
        Check validation set for feature drift and update retraining flag.

        Args:
            val_df: Validation DataFrame with feature columns.
            reference_stats: Optional reference statistics. If None, uses stored reference.
        """
        if reference_stats is None:
            if self._reference_stats is None:
                logger.warning("No reference stats available for drift check — skipping")
                return
            reference_stats = self._reference_stats
        else:
            self._reference_stats = reference_stats

        report = self.drift_monitor.check_drift(val_df, reference_stats)
        self.drift_history.append(report)

        logger.info(
            "Drift check: is_drifted=%s, max_z=%.2f, drifted_features=%s",
            report.is_drifted,
            report.max_z_score,
            report.drifted_features,
        )

        # Check if retraining should be triggered
        if should_retrain(self.drift_history, window=5):
            self._needs_full_retrain = True
            logger.warning("Drift threshold exceeded — flagging for full retraining")

    def retrain_if_needed(self, full_dataloader, device, epochs: int = 10):
        """
        Conditionally retrain model if drift flag is set.

        Args:
            full_dataloader: Full dataset loader for retraining.
            device: Training device.
            epochs: Number of epochs for full retraining.

        Returns:
            True if retraining occurred, False otherwise.
        """
        if not self._needs_full_retrain:
            return False

        logger.warning("Starting full model retraining due to detected drift")

        # Reset learning rate scheduler for fresh training
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(self.optimizer, T_max=epochs)

        for epoch in range(epochs):
            avg_loss = self.train_epoch(full_dataloader, device)
            logger.info("Retrain epoch %d/%d: loss=%.4f", epoch + 1, epochs, avg_loss)

        # Clear drift flag and history after successful retraining
        self._needs_full_retrain = False
        self.drift_history.clear()
        logger.info("Retraining complete — drift flag cleared")

        return True

    def train_step_vl(
        self,
        x_context: torch.Tensor,
        x_target: torch.Tensor,
        negatives: torch.Tensor,
        concept_alpha: float = 0.5,
        concept_beta: float = 0.1,
        round_stats=None,
    ) -> dict:
        """
        VL-JEPA training step: InfoNCE + concept alignment + diversity.

        Requires self.model to be a VLJEPACoachingModel instance.

        Args:
            x_context: Context window [batch, context_len, input_dim]
            x_target: Target window [batch, target_len, input_dim]
            negatives: Negative samples [batch, num_negatives, latent_dim]
            concept_alpha: Weight for concept alignment loss
            concept_beta: Weight for diversity regularization
            round_stats: Optional list of RoundStats objects for outcome-based labeling (G-01)

        Returns:
            Dict with infonce_loss, concept_loss, diversity_loss, total_loss
        """
        if not isinstance(self.model, VLJEPACoachingModel):
            raise TypeError("train_step_vl requires a VLJEPACoachingModel")

        self.model.train()
        self.optimizer.zero_grad()

        # 1. Standard JEPA pre-training forward
        pred_embedding, target_embedding = self.model.forward_jepa_pretrain(
            x_context,
            x_target,
        )

        # 2. InfoNCE contrastive loss
        infonce_loss = jepa_contrastive_loss(
            pred_embedding,
            target_embedding,
            negatives,
        )

        # 3. Concept alignment: encode context and get concept logits
        vl_output = self.model.forward_vl(x_context)
        concept_logits = vl_output["concept_logits"]

        # 4. Generate concept labels — prefer outcome-based (G-01 fix) over heuristic
        labeler = ConceptLabeler()
        if round_stats is not None and any(rs is not None for rs in round_stats):
            # G-01: Use RoundStats outcome data (no label leakage)
            batch_labels = []
            for rs in round_stats:
                if rs is not None:
                    batch_labels.append(labeler.label_from_round_stats(rs))
                else:
                    # Fallback: neutral labels for missing RoundStats
                    batch_labels.append(torch.full((16,), 0.5))
            concept_labels = torch.stack(batch_labels).to(x_context.device)
        else:
            # NN-JT-02: Legacy heuristic fallback — label leakage risk.
            # Escalated from warning to error-level because heuristic labels derive
            # directly from input features, allowing the model to shortcut learning.
            if not getattr(self, "_concept_label_warning_logged", False):
                logger.error(
                    "NN-JT-02: VL-JEPA concept alignment using heuristic labels (label leakage). "
                    "Model may learn input reconstruction rather than coaching concepts. "
                    "Provide RoundStats data for outcome-based labeling."
                )
                self._concept_label_warning_logged = True
            concept_labels = labeler.label_batch(x_context).to(x_context.device)

        # 5. Concept loss + diversity
        concept_total, concept_loss, diversity_loss = vl_jepa_concept_loss(
            concept_logits,
            concept_labels,
            self.model.concept_embeddings.weight,
            alpha=concept_alpha,
            beta=concept_beta,
        )

        # 6. Combined loss
        total_loss = infonce_loss + concept_total

        # 7. Backward + optimize
        total_loss.backward()
        self.optimizer.step()
        # Note: scheduler.step() is called once per epoch in train_epoch(), not per batch

        # 8. EMA update for target encoder
        self.model.update_target_encoder()

        return {
            "total_loss": total_loss.item(),
            "infonce_loss": infonce_loss.item(),
            "concept_loss": concept_loss.item(),
            "diversity_loss": diversity_loss.item(),
        }
