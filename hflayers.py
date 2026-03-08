import math

import torch
import torch.nn as nn
import torch.nn.functional as F

# R1-06: Extracted from inline magic number. Controls associative memory capacity.
HOPFIELD_MEMORY_SLOTS = 512


class Hopfield(nn.Module):
    """
    Continuous Hopfield Network / Dense Associative Memory (Ramsauer et al., 2020).

    Implements a modern Hopfield layer that stores patterns and retrieves them
    via dot-product attention (softmax pooling).

    This replaces the missing 'hflayers' library with a first-principles implementation
    of the required neural architecture.
    """

    def __init__(
        self,
        input_size,
        output_size=None,
        num_heads=1,
        stored_pattern_size=None,
        hidden_dim=None,
        update_steps_max=0,
        scaling=None,
        dropout=0.0,
    ):
        super().__init__()
        self.input_size = input_size
        self.output_size = output_size or input_size
        self.num_heads = num_heads
        self.stored_pattern_size = stored_pattern_size or input_size

        # R4-25-01 verified: stored_pattern_size == per-head dimension (d_k).
        # Scaling = 1/sqrt(d_k) matches standard Transformer/Hopfield attention.
        self.scaling = scaling or (1.0 / math.sqrt(self.stored_pattern_size))

        # Internal Memory (Learnable Prototypes)
        # We assume the layer learns "prototype" patterns to associate with inputs.
        # If stored_pattern_size is not provided, we default to input_size.
        # We create a bank of patterns (keys) and values.
        # For simplicity and robustness, we use a projecting attention mechanism.

        # Query projection
        self.query_proj = nn.Linear(input_size, self.stored_pattern_size * num_heads)

        # Key/Value projections (or learnable memory)
        # Since this is a "Memory" layer, we likely want to store patterns.
        # Here we implement it as a self-attention mechanism augmented with learned prototypes if needed.
        # Given the usage in RAPMemory (LTC -> Hopfield), it's likely processing the sequence.
        # But if it claims to "Store Prototype Rounds", it might need a fixed memory bank.
        # Let's implement a learnable memory bank of size 'stored_pattern_size'.

        # We'll use a widely generic implementation:
        # Attention(Q, K, V) where Q = Input, K=V = Learned Memory

        # R1-06: Hopfield associative memory capacity. 512 slots provides sufficient
        # capacity for CS2 tactical pattern storage without excessive memory overhead.
        memory_slots = HOPFIELD_MEMORY_SLOTS

        self.memory_keys = nn.Parameter(
            torch.randn(memory_slots, self.stored_pattern_size * num_heads) * 0.02
        )
        self.memory_values = nn.Parameter(
            torch.randn(memory_slots, self.stored_pattern_size * num_heads) * 0.02
        )

        # Output projection
        self.out_proj = nn.Linear(self.stored_pattern_size * num_heads, self.output_size)

        self.dropout = nn.Dropout(dropout)

    def forward(self, x, stored_patterns=None, pattern_projection_weight=None):
        """
        Args:
            x: Input tensor (batch, seq_len, input_size) or (batch, input_size)
        """
        is_sequence = x.dim() == 3
        if not is_sequence:
            x = x.unsqueeze(1)  # (batch, 1, input_size)

        b, s, _ = x.shape
        head_dim = self.stored_pattern_size

        # 1. Project Input to Queries
        q = self.query_proj(x).view(b, s, self.num_heads, head_dim)  # (B, S, H, D)

        # 2. Retrieve Memory (Keys/Values)
        # Expand memory for batch
        k = self.memory_keys.view(1, -1, self.num_heads, head_dim).expand(
            b, -1, -1, -1
        )  # (B, Mem, H, D)
        v = self.memory_values.view(1, -1, self.num_heads, head_dim).expand(
            b, -1, -1, -1
        )  # (B, Mem, H, D)

        # 3. Scaled Dot-Product Attention (Hopfield Update Rule)
        # Score = Q @ K.T
        scores = torch.einsum("bshd,bmhd->bshm", q, k)  # (B, S, H, Mem)
        scores = scores * self.scaling

        attn = F.softmax(scores, dim=-1)  # (B, S, H, Mem)
        attn = self.dropout(attn)

        # 4. Aggregate Values
        # Out = Attn @ V
        out = torch.einsum("bshm,bmhd->bshd", attn, v)  # (B, S, H, D)

        # 5. Concatenate Heads and Project
        out = out.reshape(b, s, -1)  # (B, S, H*D)
        out = self.out_proj(out)  # (B, S, Output_Size)

        if not is_sequence:
            out = out.squeeze(1)

        return out
