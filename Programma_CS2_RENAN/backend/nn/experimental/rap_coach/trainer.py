import torch
import torch.nn as nn
import torch.optim as optim

from Programma_CS2_RENAN.backend.nn.experimental.rap_coach.model import RAPCoachModel
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.nn.experimental.rap_coach.trainer")


class RAPTrainer:
    """
    Orchestrates training for the multi-layered RAP-Coach.
    Handles temporal gradients across Perception and Memory layers.
    """

    # NN-58: Loss weights extracted to class-level constants for tuning
    LOSS_WEIGHT_STRATEGY = 1.0
    LOSS_WEIGHT_VALUE = 0.5
    LOSS_WEIGHT_SPARSITY = 1.0
    LOSS_WEIGHT_POSITION = 1.0

    # NN-TR-02b: Z-axis penalty weight for position loss. Verticality errors in CS2
    # are disproportionately impactful (wrong floor = instant death), so Z-axis MSE
    # is penalised 2× relative to X/Y. (Task 2.17.1: Strict verticality enforcement)
    Z_AXIS_PENALTY_WEIGHT = 2.0

    def __init__(self, model: RAPCoachModel, lr=1e-4):
        self.model = model
        self.optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
        self.criterion_strat = nn.MSELoss()  # For strategy optimization
        self.criterion_val = nn.MSELoss()  # For pedagogical evaluation
        self.criterion_pos = nn.MSELoss()  # For positioning (Optimal Shadow)
        self.z_axis_penalty_weight = self.Z_AXIS_PENALTY_WEIGHT

    def train_step(self, batch):
        """
        Single optimization step over a temporal window.
        """
        self.optimizer.zero_grad()

        # Forward Pass
        try:
            outputs = self.model(batch["view"], batch["map"], batch["motion"], batch["metadata"])
        except Exception:
            logger.exception("Forward pass failed during train_step")
            raise

        # 1. Strategy Loss (Decision optimality)
        # In actual training, 'targets' come from pro-baseline deltas
        loss_strat = self.criterion_strat(outputs["advice_probs"], batch["target_strat"])

        # 2. Pedagogy Loss (Value estimation)
        # V(s) should approximate the eventual round outcome
        loss_val = self.criterion_val(outputs["value_estimate"], batch["target_val"])

        # 3. Sparsity Loss (Interpretation) — pass gate_weights explicitly for thread-safety (F3-07)
        gate_weights = outputs.get("gate_weights")
        loss_sparsity = self.model.compute_sparsity_loss(gate_weights)

        # LOGGING: Sparsity Ratio (How many gate weights are effectively zero?)
        sparsity_ratio = 0.0
        if gate_weights is not None:
            with torch.no_grad():
                sparse_mask = gate_weights.abs() < 0.01
                sparsity_ratio = sparse_mask.float().mean().item()

        # 4. Position Loss (Verticality Awareness - Task 2.17.1)
        # We compare predicted position delta (optimal_pos) against target delta
        # If target_pos_delta is not in batch, we default to 0 (unsupervised) or skip
        loss_pos = torch.tensor(0.0, device=loss_strat.device)
        z_error = 0.0

        if "target_pos" in batch:
            # Calculate predicted absolute position or work with deltas?
            # Model predicts optimal_pos (delta from current).
            # Let's assume batch['target_pos'] is the TARGET DELTA (future - current).
            loss_pos, z_error = self.compute_position_loss(
                outputs["optimal_pos"], batch["target_pos"]
            )

        # NN-58: Use class-level loss weights for tunable multi-task balance
        total_loss = (
            self.LOSS_WEIGHT_STRATEGY * loss_strat
            + self.LOSS_WEIGHT_VALUE * loss_val
            + self.LOSS_WEIGHT_SPARSITY * loss_sparsity
            + self.LOSS_WEIGHT_POSITION * loss_pos
        )

        total_loss.backward()
        self.optimizer.step()

        logger.debug(
            "train_step: loss=%.4f sparsity=%.3f pos_loss=%.4f z_err=%.4f",
            total_loss.item(), sparsity_ratio, loss_pos.item(), z_error,
        )

        # Return dict with metrics for the Orchestrator to log
        return {
            "loss": total_loss.item(),
            "sparsity_ratio": sparsity_ratio,
            "loss_pos": loss_pos.item(),
            "z_error": z_error,
        }

    def compute_position_loss(self, pred_delta, target_delta):
        """
        Computes weighted MSE for position, penalizing Z-axis errors.
        Args:
            pred_delta: (Batch, 3) [dx, dy, dz]
            target_delta: (Batch, 3) [dx, dy, dz]
        Returns:
            weighted_loss, z_error (for logging)
        """
        # Separate components
        diff = pred_delta - target_delta
        squared_diff = diff**2  # (Batch, 3)

        mse_x = squared_diff[:, 0].mean()
        mse_y = squared_diff[:, 1].mean()
        mse_z = squared_diff[:, 2].mean()

        # Apply strict Z-penalty
        weighted_loss = mse_x + mse_y + (self.z_axis_penalty_weight * mse_z)

        return weighted_loss, mse_z.item()
