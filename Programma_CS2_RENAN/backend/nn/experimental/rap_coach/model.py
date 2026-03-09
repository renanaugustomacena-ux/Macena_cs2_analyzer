import torch
import torch.nn as nn

from Programma_CS2_RENAN.backend.nn.config import RAP_POSITION_SCALE  # noqa: F401
from Programma_CS2_RENAN.backend.nn.experimental.rap_coach.memory import RAPMemory
from Programma_CS2_RENAN.backend.nn.experimental.rap_coach.pedagogy import CausalAttributor, RAPPedagogy
from Programma_CS2_RENAN.backend.nn.experimental.rap_coach.perception import RAPPerception
from Programma_CS2_RENAN.backend.nn.experimental.rap_coach.strategy import RAPStrategy
from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.nn.experimental.rap_coach.model")


class RAPCoachModel(nn.Module):
    """
    Near-Perfect CS2 Machine Learning Coach (Full Integration).
    Layers: Perception, Prediction, Evaluation, Strategy, Memory, Pedagogy.
    """

    def __init__(self, metadata_dim=METADATA_DIM, output_dim=10, heuristic_config=None):
        super().__init__()
        self.metadata_dim = metadata_dim

        # Resolve L1 sparsity weight from HeuristicConfig or default
        if heuristic_config is not None:
            self.context_gate_l1_weight = heuristic_config.context_gate_l1_weight
        else:
            self.context_gate_l1_weight = 1e-4

        # 1. Perception Layer (70 Conv Layer Budget)
        self.perception = RAPPerception()
        # Perception output dim = 64 (view) + 32 (map) + 32 (motion) = 128
        perception_dim = 128

        # 2. Memory Layer (Recurrent Belief State)
        hidden_dim = 256
        self.memory = RAPMemory(perception_dim, metadata_dim, hidden_dim)

        # 3. Strategy Layer (Decision Optimization)
        self.strategy = RAPStrategy(hidden_dim, output_dim, context_dim=metadata_dim)

        # 4. Pedagogy Layer (Causal Attribution)
        self.pedagogy = RAPPedagogy(hidden_dim)
        self.attributor = CausalAttributor(hidden_dim)

        # 5. Position Head (Optimal Shadow)
        # Predicts delta (dx, dy, dz) from current pos to optimal pos
        self.position_head = nn.Linear(hidden_dim, 3)

        logger.info(
            "RAPCoachModel initialized: metadata_dim=%d, output_dim=%d, hidden=%d, perception=%d",
            metadata_dim, output_dim, hidden_dim, perception_dim,
        )

    def forward(self, view_frame, map_frame, motion_diff, metadata, skill_vec=None, hidden_state=None):
        # P-X-02: Input shape assertions — catch misaligned tensors before they
        # propagate into cryptic LSTM/CNN errors.
        assert metadata.ndim == 3 and metadata.shape[-1] == self.metadata_dim, (
            f"P-X-02: metadata shape {metadata.shape}, "
            f"expected (B, seq_len, {self.metadata_dim})"
        )
        assert view_frame.ndim in (4, 5), (
            f"P-X-02: view_frame must be 4D (B,C,H,W) or 5D (B,T,C,H,W), got {view_frame.ndim}D"
        )
        assert metadata.shape[1] >= 1, (
            f"NN-RM-02: metadata seq_len must be >= 1, got {metadata.shape[1]}"
        )
        # NN-40: hidden_state allows persisting recurrent state across forward calls
        batch_size, seq_len, _ = metadata.shape

        # NN-39 fix: support both per-timestep [B,T,C,H,W] and static [B,C,H,W] visual input
        if view_frame.dim() == 5:
            # Per-timestep visual input — process each timestep through CNN
            z_frames = []
            for t in range(view_frame.shape[1]):
                z_t = self.perception(
                    view_frame[:, t], map_frame[:, t], motion_diff[:, t]
                )
                z_frames.append(z_t)
            z_spatial_seq = torch.stack(z_frames, dim=1)  # [B, T, 128]
        else:
            # Static spatial context — single frame expanded across timesteps
            z_spatial = self.perception(view_frame, map_frame, motion_diff)  # [B, 128]
            z_spatial_seq = z_spatial.unsqueeze(1).expand(-1, seq_len, -1)

        lstm_in = torch.cat([z_spatial_seq, metadata], dim=2)

        # NN-40: Forward through Recurrent Belief State with optional initial hidden state
        hidden_seq, belief, new_hidden = self.memory(lstm_in, hidden=hidden_state)

        # Last hidden state for decision
        last_hidden = hidden_seq[:, -1, :]

        # Strategy Execution
        # We pass the last metadata frame as context for Superposition
        context = metadata[:, -1, :]
        prediction, gate_weights = self.strategy(last_hidden, context)

        # NN-RM-01: Validate skill_vec shape before passing to pedagogy adapter.
        # skill_adapter expects (B, 10) — mismatched shapes produce silent garbage.
        if skill_vec is not None:
            if skill_vec.ndim != 2 or skill_vec.shape[1] != 10:
                logger.warning(
                    "NN-RM-01: skill_vec shape %s invalid (expected [B, 10]), ignoring",
                    tuple(skill_vec.shape),
                )
                skill_vec = None
            elif skill_vec.shape[0] != batch_size:
                logger.warning(
                    "NN-RM-01: skill_vec batch=%d != metadata batch=%d, ignoring",
                    skill_vec.shape[0], batch_size,
                )
                skill_vec = None

        # Evaluation (Value function)
        value_v = self.pedagogy(last_hidden, skill_vec)

        # Positioning (Optimal Shadow)
        optimal_pos = self.position_head(last_hidden)  # [Batch, 3]

        # Causal Attribution (Why?)
        attribution = self.attributor.diagnose(last_hidden, optimal_pos)  # [Batch, 5]

        return {
            "advice_probs": prediction,
            "belief_state": belief,
            "value_estimate": value_v,
            "gate_weights": gate_weights,
            "optimal_pos": optimal_pos,
            "attribution": attribution,
            "hidden_state": new_hidden,  # NN-40: expose for stateful inference
        }

    def compute_sparsity_loss(self, gate_weights: torch.Tensor = None) -> torch.Tensor:
        """
        Computes L1 Regularization loss on the Context Gate activations.
        Enforces sparsity (interpretability) in decision making.

        Args:
            gate_weights: Gate weight tensor from the last forward() call.
                Callers should pass out["gate_weights"] explicitly to avoid
                thread-safety issues that arise from caching on self. (F3-07)
        """
        if gate_weights is None:
            # NN-RM-03: Warn rather than silently returning 0 — callers should
            # pass out["gate_weights"] from forward(). None means either forward()
            # wasn't called or strategy layer produced no gates.
            logger.debug("NN-RM-03: gate_weights is None, returning 0.0 sparsity loss")
            return torch.tensor(0.0)

        # L1 Norm: Mean of absolute values
        # We want gate values to be mostly near 0, with few strong activations
        l1_loss = torch.mean(torch.abs(gate_weights))
        return self.context_gate_l1_weight * l1_loss
