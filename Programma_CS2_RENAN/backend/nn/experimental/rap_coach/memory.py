import torch
import torch.nn as nn
from ncps.torch import LTC
from ncps.wirings import AutoNCP

from hflayers import Hopfield

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.nn.experimental.rap_coach.memory")


class RAPMemory(nn.Module):
    """
    Recurrent Belief State Module (Generation 2: Liquid Mind).
    Upgraded from LSTM to Liquid Time-Constant (LTC) + Hopfield Associative Memory.

    Resolves POMDP partial observability via Bayesian filtering in latent space,
    with continuous-time handling (LTC) and long-term pattern recall (Hopfield).
    """

    def __init__(self, perception_dim, metadata_dim, hidden_dim=256):
        super().__init__()

        input_dim = perception_dim + metadata_dim

        # 1. Liquid Time-Constant (LTC) Layer
        # Models continuous-time dynamics (variable frame rates, "pace" of the game)
        # We use AutoNCP wiring to create a sparse, brain-like connectivity.
        # NCP Constraint: units must be significantly larger than output_size (inter-neurons).
        # Ratio 2:1 ensures enough inter-neurons for expressive wiring.
        # NOTE: changing this invalidates existing checkpoints — version-gated loading required.
        ncp_units = hidden_dim * 2
        # NN-45 + NN-MEM-02: Seed both numpy and torch RNGs for deterministic,
        # checkpoint-portable NCP wiring. AutoNCP uses numpy internally, but
        # downstream LTC init may use torch — save/restore both to isolate side effects.
        import numpy as np
        np_rng_state = np.random.get_state()
        torch_rng_state = torch.random.get_rng_state()
        np.random.seed(42)
        torch.manual_seed(42)
        try:
            self.wiring = AutoNCP(units=ncp_units, output_size=hidden_dim)
        finally:
            np.random.set_state(np_rng_state)
            torch.random.set_rng_state(torch_rng_state)
        self.ltc = LTC(input_dim, self.wiring, batch_first=True)

        # 2. Hopfield Layer (Associative Memory)
        # Stores and retrieves "Prototype Rounds" (perfect plays) to guide the ghost.
        # Acts as a Dense Associative Memory.
        # NOTE: Stored patterns start as random (torch.randn * 0.02) and are only
        # shaped via gradient descent during training. Until sufficient training
        # on real CS2 data occurs, attention will be near-uniform across all slots.
        # Monitor attention entropy in TensorBoard to verify pattern formation.
        # NN-MEM-01: Track whether Hopfield has been trained (via checkpoint load or
        # gradient updates). Until trained, forward() bypasses associative recall.
        self._hopfield_trained = False
        self.hopfield = Hopfield(
            input_size=hidden_dim,
            output_size=hidden_dim,
            num_heads=4,  # Multiple association heads
            stored_pattern_size=hidden_dim,
        )

        # 3. State Reconstruction Head (The Belief State)
        # Predicts latent properties like "Enemy Strategy" or "Rotation Phase"
        self.belief_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),  # Better gradient flow than ReLU
            nn.Linear(hidden_dim, 64),  # Belief vector size
        )
        logger.debug(
            "RAPMemory initialized: input=%d, hidden=%d, ncp_units=%d, hopfield_heads=4",
            input_dim, hidden_dim, ncp_units,
        )

    def forward(self, x, hidden=None):
        """
        Processes sequential observation features.
        x shape: (batch, seq_len, input_dim)
        """
        # Liquid Flow: Handle temporal dynamics
        ltc_out, hidden = self.ltc(x, hidden)

        # Associative Recall: Retrieve tactical prototypes
        # NN-MEM-01: Skip Hopfield if not yet trained — random prototypes produce
        # near-uniform attention that adds noise rather than signal.
        if self._hopfield_trained:
            mem_out = self.hopfield(ltc_out)
        else:
            mem_out = torch.zeros_like(ltc_out)

        # Residual Combination: Dynamics + Memory
        combined_state = ltc_out + mem_out

        # We use the full sequence for training, but the last tick for decision
        belief = self.belief_head(combined_state)

        # NN-MEM-01: After first training forward pass, mark Hopfield as active
        if self.training and not self._hopfield_trained:
            self._hopfield_trained = True
            logger.debug("NN-MEM-01: Hopfield marked as trained after first training forward")

        return combined_state, belief, hidden

    def load_state_dict(self, state_dict, strict=True, assign=False):
        """Override to mark Hopfield as trained when loading a checkpoint."""
        result = super().load_state_dict(state_dict, strict=strict, assign=assign)
        self._hopfield_trained = True
        logger.debug("NN-MEM-01: Hopfield marked as trained via checkpoint load")
        return result
