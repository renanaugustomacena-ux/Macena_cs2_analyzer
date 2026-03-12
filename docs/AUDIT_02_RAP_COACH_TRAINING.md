# Audit Report 02 — RAP Coach & Training

**Scope:** `Programma_CS2_RENAN/backend/nn/rap_coach/` (shims), `Programma_CS2_RENAN/backend/nn/experimental/rap_coach/` (canonical), plus RAP-specific processing files: `skill_assessment.py`, `state_reconstructor.py`, `tensor_factory.py`, `player_knowledge.py`
**Files Audited:** 25
**Total Lines:** ~3,024
**Date:** 2026-03-10

---

## Executive Summary

The RAP (Reasoning, Action, Prediction) Coach is the high-fidelity experimental neural coaching model combining CNN perception, LTC-Hopfield memory, Superposition-gated MoE strategy, and causal attribution pedagogy. The architecture is clean and well-documented. All original module files have been relocated to `experimental/rap_coach/` with deprecated shims left in `rap_coach/` for backward compatibility. The supporting infrastructure (TensorFactory, PlayerKnowledge, RAPStateReconstructor, SkillAssessment) is production-quality with strong sensorial modeling ("no wallhacks").

No HIGH-severity findings. 12 MEDIUM-severity findings centered on inference/training dimension mismatches, fabricated template values in feedback generation, missing gradient clipping, and channel semantics tracking. The PlayerKnowledge builder is architecturally excellent but has quadratic memory history traversal.

**Severity Distribution:** 0 HIGH | 12 MEDIUM | 11 LOW

---

## File Inventory

| # | File | Lines | Findings |
|---|------|-------|----------|
| 1 | `rap_coach/__init__.py` (shim) | 4 | — |
| 2 | `rap_coach/model.py` (shim) | 7 | — |
| 3 | `rap_coach/memory.py` (shim) | 6 | — |
| 4 | `rap_coach/trainer.py` (shim) | 6 | — |
| 5 | `rap_coach/perception.py` (shim) | 7 | — |
| 6 | `rap_coach/strategy.py` (shim) | 8 | — |
| 7 | `rap_coach/communication.py` (shim) | 7 | — |
| 8 | `rap_coach/pedagogy.py` (shim) | 7 | — |
| 9 | `rap_coach/skill_model.py` (shim) | 9 | — |
| 10 | `rap_coach/chronovisor_scanner.py` (shim) | 16 | — |
| 11 | `rap_coach/test_arch.py` (shim) | 6 | — |
| 12 | `experimental/rap_coach/__init__.py` | 4 | 0 |
| 13 | `experimental/rap_coach/model.py` | 156 | 1M |
| 14 | `experimental/rap_coach/memory.py` | 113 | 1M |
| 15 | `experimental/rap_coach/trainer.py` | 127 | 2M |
| 16 | `experimental/rap_coach/perception.py` | 99 | 1L |
| 17 | `experimental/rap_coach/strategy.py` | 81 | 1L |
| 18 | `experimental/rap_coach/communication.py` | 140 | 2M, 1L |
| 19 | `experimental/rap_coach/pedagogy.py` | 99 | 1M, 1L |
| 20 | `experimental/rap_coach/chronovisor_scanner.py` | 409 | 2L |
| 21 | `experimental/rap_coach/test_arch.py` | 48 | 1M, 1L |
| 22 | `processing/skill_assessment.py` | 155 | 1M |
| 23 | `processing/state_reconstructor.py` | 133 | 0 |
| 24 | `processing/tensor_factory.py` | 746 | 2M |
| 25 | `processing/player_knowledge.py` | 611 | 2M, 1L |

**Note:** Shim files (1-11) are uniform deprecated re-exports. One cross-cutting finding applies to all 11 — see RAP-L-01.

---

## MEDIUM Severity Findings

### RAP-M-01: Position Head Outputs 3D but Inference Uses 2D (model.py:49, ghost_engine.py:172)

**File:** `experimental/rap_coach/model.py`, line 49; cross-ref `inference/ghost_engine.py`, line 172
**Category:** Architecture — wasted capacity + training/inference mismatch

`RAPCoachModel.position_head` outputs 3 dimensions `[dx, dy, dz]`:
```python
self.position_head = nn.Linear(hidden_dim, 3)
```

The trainer applies a Z-axis penalty (`Z_AXIS_PENALTY_WEIGHT=2.0`) to enforce verticality. However, `ghost_engine.py:172` only reads 2 dimensions:
```python
optimal_delta = out["optimal_pos"].cpu().numpy()[0]  # [dx, dy]
ghost_x = current_x + (optimal_delta[0] * RAP_POSITION_SCALE)
ghost_y = current_y + (optimal_delta[1] * RAP_POSITION_SCALE)
```

The Z-axis is trained but never used in inference — gradient capacity is spent learning a dimension that is discarded. On multi-level maps (Nuke, Vertigo), the Z recommendation could be valuable but is inaccessible.

**Remediation:** Either expose `optimal_delta[2]` as a floor recommendation in GhostEngine, or reduce position_head to 2D and remove Z_AXIS_PENALTY_WEIGHT.

---

### RAP-M-02: Feedback Templates Use Fabricated Values (communication.py:118-123)

**File:** `experimental/rap_coach/communication.py`, lines 118-123

Template placeholders are populated from the `confidence` scalar, not from actual game measurements:
```python
return template.format(
    score=int(confidence * 100),
    time=round(float(confidence * 2), 1),     # FAKE: not real exposure time
    error=int((1 - confidence) * 300),         # FAKE: not real timing error in ms
    angle=angle,
    recommendation="conservative" if confidence > 0.8 else "aggressive",
)
```

The template "You were exposed to {angle} for {time}s" populates `{time}` with `confidence * 2`, which is a number between 0.0 and 2.0 — it has no relation to actual exposure time. Similarly, "counter-strafing was off by {error}ms" uses `(1-confidence)*300` — not an actual measured timing error.

**Remediation:** Accept a `game_metrics` dict parameter with actual measurements, or change templates to use language that doesn't claim specific measurements.

---

### RAP-M-03: Utility Need Heuristic Arbitrary (pedagogy.py:97)

**File:** `experimental/rap_coach/pedagogy.py`, line 97

`CausalAttributor._detect_utility_need()` computes:
```python
util_signal = torch.sigmoid(hidden.mean(dim=-1))
```

This maps the average hidden activation to a `[0, 1]` "utility need" score via sigmoid. The hidden representation encodes the full game state — there is no guarantee that `mean(hidden)` correlates with utility need. This proxy was explicitly upgraded from a static zero (per the comment), but the current heuristic may produce misleading attribution scores for the "Utility" concept.

---

### RAP-M-04: Hopfield Activation Semantics (memory.py:101-103)

**File:** `experimental/rap_coach/memory.py`, lines 101-103

`_hopfield_trained` is set to `True` on the first training forward pass:
```python
if self.training and not self._hopfield_trained:
    self._hopfield_trained = True
```

This activates Hopfield associative recall immediately after the first forward pass, before any backward pass or gradient update has occurred. The Hopfield stored patterns are still random at this point. More accurate semantics would require checking that at least one optimizer step has been completed, or using a forward-count threshold.

The `load_state_dict` override (line 107-112) correctly sets the flag for checkpoint-loaded models.

---

### RAP-M-05: No Gradient Clipping in RAPTrainer (trainer.py)

**File:** `experimental/rap_coach/trainer.py`

`RAPTrainer.train_step()` calls `total_loss.backward()` and `self.optimizer.step()` without gradient clipping. The LTC (Liquid Time-Constant) layer processes sequential data with continuous-time dynamics, which can produce gradient spikes during early training or on unusual sequences. The main NN training loops in `train.py` use `clip_grad_norm_(max_norm=1.0)` — this discipline is absent from the RAP trainer.

**Remediation:** Add `torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)` before `self.optimizer.step()`.

---

### RAP-M-06: Silent Position Training Skip (trainer.py:71)

**File:** `experimental/rap_coach/trainer.py`, line 71

When `target_pos` is absent from the batch, position loss defaults to `torch.tensor(0.0)` with no logging:
```python
loss_pos = torch.tensor(0.0, device=loss_strat.device)
```

This means the position head receives no gradient signal for that batch. If batch preparation consistently omits `target_pos` (e.g., when pro baseline deltas don't include position targets), the position head never trains — but the trainer reports success. No log message distinguishes "position training active" from "position training skipped."

---

### RAP-M-07: test_arch.py Uses Assert Instead of Test Framework (test_arch.py)

**File:** `experimental/rap_coach/test_arch.py`

`test_rap_forward_pass()` uses Python `assert` statements for verification. When run with `-O` (optimize) flag, assertions are stripped, turning the test into a no-op. This is in `experimental/` not `tests/`, but it's invoked via `if __name__ == "__main__"` as a standalone verification tool. Using a proper test framework (`pytest.raises`, `assert` inside pytest which doesn't strip) would be safer.

---

### RAP-M-08: Channel Semantics Reversal Not Tracked (tensor_factory.py)

**File:** `processing/tensor_factory.py`, class docstring (lines 107-123)

Legacy mode uses `Ch0=enemies, Ch1=teammates` while POV mode uses `Ch0=teammates, Ch1=enemies` (reversed). This is documented in comments (R4-04-01) and in the ghost_engine, but there is no programmatic indicator on the generated tensor. A model trained in legacy mode that receives POV tensors (or vice versa) will silently process reversed channels. The `USE_POV_TENSORS` setting gates inference, but training mode is controlled separately by whether `knowledge` is passed.

**Remediation:** Attach a metadata flag to generated tensors (e.g., via a wrapper NamedTuple or a `mode` attribute on TensorFactory) so consumers can verify mode compatibility.

---

### RAP-M-09: int() Truncation in World-to-Grid Conversion (tensor_factory.py:625-626)

**File:** `processing/tensor_factory.py`, lines 625-626

```python
gx = int(nx * resolution)
gy = int(ny * resolution)
```

Python `int()` truncates toward zero. For negative normalized coordinates (`nx = -0.1`), `int(-0.1 * 128) = int(-12.8) = -12`. But `math.floor(-12.8) = -13`. The bounds check `0 <= gx < resolution` filters these out, so the functional impact is limited to dropping edge-case positions that should map to grid cell -13 (which is also out of bounds). However, for coordinates near zero, this truncation vs floor difference could matter.

---

### RAP-M-10: Enemy Memory Traversal is O(N*E) (player_knowledge.py:373-460)

**File:** `processing/player_knowledge.py`, `_build_enemy_memory()`

Walks the entire `recent_all_players_history` dict (potentially hundreds of ticks) and for each tick, iterates all non-teammate players. For matches with 200K ticks and 10 players per tick, this is substantial. The method is called per knowledge build, which happens per inference tick.

In practice, `recent_all_players_history` is likely windowed to a small subset of ticks, but there's no hard cap on the dict size — it's controlled by the caller. Adding a `MAX_HISTORY_TICKS` cap within this method would provide defense-in-depth.

---

### RAP-M-11: Flash Radius Uses Smoke Approximation (player_knowledge.py:606)

**File:** `processing/player_knowledge.py`, line 606

```python
radius=SMOKE_RADIUS,  # 200.0
```

Flash effective blind radius in CS2 is approximately 400 units. Using `SMOKE_RADIUS = 200.0` underestimates by 2x. The F2-08 comment acknowledges this. The TensorFactory renders utility zones on view tensors using this radius, meaning the neural network sees a flash zone that is half the actual effective area.

---

### RAP-M-12: Skill Vector Attribute Access Without Guards (skill_assessment.py:70-113)

**File:** `processing/skill_assessment.py`, lines 70-113

`SkillLatentModel.calculate_skill_vector()` accesses stats attributes directly:
```python
m_vals = [get_z("accuracy", stats.accuracy), get_z("avg_hs", stats.avg_hs)]
```

If a `PlayerMatchStats` instance is missing an attribute (possible for partially-populated records from older schema versions), this raises `AttributeError`. The `get_z()` helper checks `not val` but doesn't catch the attribute access exception.

**Remediation:** Use `getattr(stats, "accuracy", None)` for defensive access.

---

## LOW Severity Findings

### RAP-L-01: 11 Deprecated Shims Not Cleaned Up (rap_coach/)
All files in `rap_coach/` are deprecated re-export shims from the P9-01 consolidation. They function correctly but add import indirection and maintenance burden. Once all callers are migrated to `experimental.rap_coach.*`, these shims can be removed.

### RAP-L-02: No Perception Output Dimension Assertion (perception.py)
`RAPPerception.forward()` returns a 128-dim vector (64+32+32) but has no runtime assertion. The F2-02 comment in `TensorConfig` recommends `assert output.shape[-1] == 128` to catch regressions if ResNet stack is modified.

### RAP-L-03: Strategy Forward Returns Bare Tuple (strategy.py:80)
`RAPStrategy.forward()` returns `(final_output, gate_weights)` as a tuple. Callers must know the positional convention. A NamedTuple would be more self-documenting.

### RAP-L-04: Confidence Threshold Hardcoded (communication.py:84)
`confidence < 0.7` check is hardcoded. The threshold for suppressing advice should be configurable per skill tier.

### RAP-L-05: Coaching Concepts Hardcoded as List (pedagogy.py:48)
`CausalAttributor.concepts = ["Positioning", "Crosshair Placement", "Aggression", "Utility", "Rotation"]` — same pattern as NN-L-03 in Report 1. Could be an Enum or shared constant.

### RAP-L-06: Maturity Gate Not Enforced (chronovisor_scanner.py:150-154)
`ChronovisorScanner._load_model()` calls `check_maturity_gate()` but doesn't enforce the result. Comment says "The UI gates access" — backend should be independently robust.

### RAP-L-07: Meaningless Truthiness Check (chronovisor_scanner.py:159)
`if model:` after `model = RAPCoachModel()` — `nn.Module` instances are always truthy. This check can never fail.

### RAP-L-08: Architecture Test Covers Shapes Only (test_arch.py)
`test_rap_forward_pass()` verifies output shapes but not gradient flow, backward pass, or loss computation. A shape-only test cannot detect NaN propagation or gradient explosion.

### RAP-L-09: Skill Fallback 0.5 Undocumented (skill_assessment.py:119)
When all skill axes are unavailable, all are set to 0.5 (curriculum level 5). This represents "average" but is not documented as such.

### RAP-L-10: Unused Constant (player_knowledge.py:41)
`HEARING_RANGE_FOOTSTEP = 1000.0` is defined but never referenced anywhere in the codebase.

### RAP-L-11: _make_resnet_stack Ignores Group Structure (perception.py:78-84)
`num_blocks=[1,2,2,1]` is treated as `sum()=6` total blocks, with only the first using stride=2. The list structure (implying 4 groups) is misleading — all blocks after the first are identical stride-1 blocks.

---

## Cross-Cutting Concerns

### 1. Training/Inference Skew Vectors

Multiple skew vectors exist between training and inference:

| Aspect | Training | Inference | Risk |
|--------|----------|-----------|------|
| Position dims | 3D (dx, dy, dz) with Z penalty | 2D (dx, dy) only | Z axis trained but unused |
| Channel order | Legacy (Ch0=enemies) or POV (Ch0=teammates) | Controlled by USE_POV_TENSORS | No runtime validation |
| Tensor resolution | 64x64 (TrainingTensorConfig) | 128x128 or 224x224 (TensorConfig) | AdaptiveAvgPool handles it |
| Feature parity | Validated (P-SR-01) | Validated (P-SR-01) | Covered |

### 2. Deprecated Shim Layer

The P9-01 migration created a clean two-tier structure: `rap_coach/` (shims) → `experimental/rap_coach/` (canonical). However, 11 shim files remain indefinitely. No migration tracker or deprecation timeline exists.

### 3. Heuristic Attribution Quality

The CausalAttributor uses three proxy signals (pos_delta for Positioning/Aggression/Rotation, aim_delta for Crosshair, hidden.mean() for Utility). Two of five concepts (Aggression = 0.5 * pos_delta, Rotation = 0.8 * pos_delta) are directly derived from position delta with different scaling — they are not independent signals. The "why" explanations may not reflect actual causal factors.

### 4. Fabricated Feedback Values

RAPCommunication generates player-facing advice using confidence-derived fake measurements ("exposed for {time}s", "off by {error}ms"). While the language is coaching-appropriate, the specificity of these numbers creates false precision that could mislead players who try to act on the exact values.

---

## Positive Observations

1. **NO-WALLHACK sensorial model:** PlayerKnowledge correctly implements fair perception — the coach sees only what the player legitimately knows. FOV cone, exponential memory decay, Z-level guards, and hearing range are all implemented.
2. **LTC + Hopfield architecture:** Clean continuous-time dynamics (LTC) with associative memory (Hopfield). Deterministic NCP wiring via seeded RNG (NN-45, NN-MEM-02).
3. **Thread-safe sparsity loss:** `compute_sparsity_loss()` takes `gate_weights` as explicit parameter (F3-07), avoiding cached state across threads.
4. **Feature parity validation:** Both training (state_reconstructor.py:100) and inference (ghost_engine.py:156) validate feature vectors via `FeatureExtractor.validate_feature_parity()`.
5. **Multi-scale Chronovisor:** Three temporal scales (micro/standard/macro) with cross-scale deduplication — principled signal processing for critical moment detection.
6. **Tick truncation safety:** `_MAX_TICKS_PER_SCAN = 50,000` with truncation detection and warning (F3-21, NN-CV-02).
7. **TensorFactory quality:** Named constants for all intensity/radius/speed values, shape assertions on all outputs, lazy scipy import, thread-safe singleton.
8. **ScanResult structured errors:** Chronovisor returns typed result objects with success/failure status instead of bare lists.

---

## Remediation Priority

| Priority | ID | Fix |
|----------|----|-----|
| 1 | RAP-M-05 | Add gradient clipping to RAPTrainer |
| 2 | RAP-M-01 | Expose Z-axis in GhostEngine or reduce to 2D |
| 3 | RAP-M-02 | Replace fabricated template values with real metrics or neutral language |
| 4 | RAP-M-08 | Add tensor mode tracking to TensorFactory |
| 5 | RAP-M-11 | Use actual flash radius (~400 units) instead of SMOKE_RADIUS |
| 6 | RAP-M-06 | Log when position training is skipped |
| 7 | RAP-M-12 | Use getattr() for defensive attribute access |
| 8 | RAP-M-10 | Cap _build_enemy_memory history traversal |

---

*Report generated by exhaustive line-by-line audit of 25 files (3,024 lines) across `rap_coach/`, `experimental/rap_coach/`, and RAP-specific processing modules.*
