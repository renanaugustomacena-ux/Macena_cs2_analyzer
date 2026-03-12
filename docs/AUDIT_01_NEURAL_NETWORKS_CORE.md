# Audit Report 01 — Neural Networks Core

**Scope:** `Programma_CS2_RENAN/backend/nn/` (excluding `rap_coach/` — covered in Report 02)
**Files Audited:** 31
**Total Lines:** ~7,420
**Date:** 2026-03-10

---

## Executive Summary

The neural network core comprises the full model zoo (AdvancedCoachNN, JEPA, VL-JEPA, WinProbability, NeuralRoleHead), training infrastructure (orchestrator, controller, monitor, callbacks, pipelines), inference engine (GhostEngine), and supporting layers (SuperpositionLayer, EMA, persistence). The codebase is well-structured with clear separation between model definitions, training workflows, and inference. Three HIGH-severity issues were identified: a position scale factor mismatch between overlay and inference code, unused output dimensions masking wasted model capacity, and a stale log message producing nonsensical arithmetic after a prior fix.

**Severity Distribution:** 3 HIGH | 22 MEDIUM | 18 LOW

---

## File Inventory

| # | File | Lines | Findings |
|---|------|-------|----------|
| 1 | `config.py` | 155 | 1M, 1L |
| 2 | `model.py` | 183 | 1M, 1L |
| 3 | `jepa_model.py` | 1034 | 3M, 2L |
| 4 | `jepa_trainer.py` | 334 | 1M, 1L |
| 5 | `ema.py` | 128 | 0 |
| 6 | `persistence.py` | 100 | 0 |
| 7 | `dataset.py` | 64 | 0 |
| 8 | `train.py` | 274 | 1M, 1L |
| 9 | `evaluate.py` | 69 | 1H, 2M |
| 10 | `factory.py` | 121 | 1M, 1L |
| 11 | `early_stopping.py` | 86 | 0 |
| 12 | `role_head.py` | 327 | 2M, 1L |
| 13 | `coach_manager.py` | 920 | 1H, 3M, 1L |
| 14 | `training_orchestrator.py` | 890 | 2M, 1L |
| 15 | `training_controller.py` | 160 | 1M, 1L |
| 16 | `training_monitor.py` | 123 | 1L |
| 17 | `training_config.py` | 70 | 0 |
| 18 | `training_callbacks.py` | 110 | 1L |
| 19 | `train_pipeline.py` | 115 | 1M, 1L |
| 20 | `jepa_train.py` | 459 | 1H, 1M, 1L |
| 21 | `embedding_projector.py` | 230 | 1M, 1L |
| 22 | `maturity_observatory.py` | 329 | 1M, 1L |
| 23 | `tensorboard_callback.py` | 228 | 2L |
| 24 | `win_probability_trainer.py` | 124 | 1M, 1L |
| 25 | `inference/ghost_engine.py` | 227 | 2M, 1L |
| 26 | `inference/__init__.py` | 1 | 0 |
| 27 | `layers/superposition.py` | 108 | 1M |
| 28 | `layers/__init__.py` | 1 | 0 |
| 29 | `advanced/__init__.py` | 5 | 0 |
| 30 | `experimental/__init__.py` | 10 | 0 |
| 31 | `__init__.py` | 1 | 0 |

---

## HIGH Severity Findings

### NN-H-01: Position Scale Factor Mismatch — Overlay vs Inference (coach_manager.py:851-852)

> **Status: FIXED** — `coach_manager.py` now imports and uses `RAP_POSITION_SCALE` from `config.py`. The hardcoded `1000` no longer exists.

**File:** `coach_manager.py`, lines 851-852
**Category:** Correctness — numerical divergence

The `get_interactive_overlay_data()` method converts RAP model output deltas to world coordinates using a hardcoded scale factor of `1000`:

```python
ghost_x = tick.pos_x + (optimal_pos[0] * 1000)  # Scale factor
ghost_y = tick.pos_y + (optimal_pos[1] * 1000)
```

Meanwhile, `inference/ghost_engine.py:184-185` correctly uses the canonical constant:

```python
ghost_x = current_x + (optimal_delta[0] * RAP_POSITION_SCALE)  # 500.0
ghost_y = current_y + (optimal_delta[1] * RAP_POSITION_SCALE)
```

The overlay ghost positions are displayed at **2x** the distance from the player compared to what the inference engine produces. This means:
- The overlay visualization shows the ghost in the wrong position
- Any user-facing coaching derived from overlay data is spatially incorrect
- Training targets and inference outputs use 500.0, but the interactive visualization uses 1000

**Remediation:** Replace `1000` with `RAP_POSITION_SCALE` (imported from `config.py`).

---

### NN-H-02: 84% of Model Output Dimensions Unused (evaluate.py:63-66)

> **Status: FIXED** — `OUTPUT_DIM` in `config.py` now correctly set to `10` (matching the actual model architecture). `evaluate.py` iterates all 25 `MATCH_AGGREGATE_FEATURES` but populates only the first `OUTPUT_DIM` (10) with NN adjustments. The original code extracting only 4 hardcoded indices has been replaced with a loop over all model outputs.

**File:** `evaluate.py`, lines 32-66
**Category:** Architecture — wasted capacity

`evaluate_adjustments()` runs the model (which outputs `METADATA_DIM=25` dimensions) but only extracts 4 values:

```python
"adr_weight": float(adj[0]) * WEIGHT_CLAMP,
"kast_weight": float(adj[1]) * WEIGHT_CLAMP,
"hs_weight": float(adj[2]) * WEIGHT_CLAMP,
"impact_weight": float(adj[3]) * WEIGHT_CLAMP,
```

Dimensions 4-24 (21 values) are computed but discarded. The model trains on all 25 output dimensions but only 4 influence coaching. This causes:
- **Wasted gradient capacity** — the model allocates parameters to outputs that are never used downstream
- **Silent drift** — if unused dimensions diverge, no alarm fires because they're never read
- **Misleading architecture** — OUTPUT_DIM=25 suggests 25 coaching signals, but only 4 exist

The NN-12 comment documents awareness but no resolution path. The debug logging (lines 35-42) monitors unused dims but takes no corrective action.

**Remediation:** Either (a) expand consumers to use all 25 dims via multi-head coaching, or (b) reduce OUTPUT_DIM to 4 and save parameters.

---

### NN-H-03: Stale Log Arithmetic Produces Nonsensical Values (jepa_train.py:~155-163)

**File:** `jepa_train.py`, `load_pro_demo_sequences()` log message
**Category:** Correctness — misleading diagnostics

After NN-32 was fixed, matches without RoundStats are now **skipped** (via `continue`), not tiled. But `fallback_count` still increments, and the log message still references tiling:

```python
logger.info("Loaded %d pro demo sequences (%d from RoundStats, %d fallback-tiled)",
            len(sequences), len(sequences) - fallback_count, fallback_count)
```

If 30 matches have RoundStats (→ `len(sequences)=30`) and 70 are skipped (`fallback_count=70`), the log reads:
`"Loaded 30 pro demo sequences (-40 from RoundStats, 70 fallback-tiled)"`

This is arithmetically wrong: `-40` is nonsensical, and "fallback-tiled" is factually incorrect since no tiling occurs. The subsequent warning (lines ~159-163) compounds this by saying sequences "used np.tile fallback" when they were actually skipped.

**Remediation:** Fix the log message:
```python
logger.info("Loaded %d pro demo sequences from RoundStats (%d matches skipped — no RoundStats)",
            len(sequences), fallback_count)
```

---

## MEDIUM Severity Findings

### NN-M-01: Auto-unsqueeze Masks Batch Dimension Errors (model.py:~78)

**File:** `model.py`, `_validate_input_dim()`
`AdvancedCoachNN._validate_input_dim()` auto-unsqueezes 1D input to `[1, 1, features]`. While convenient, this silently promotes a shape `[features]` (missing batch AND sequence dims) to a valid 3D tensor, masking bugs where the caller forgot to batch the input. A `[batch_size]` tensor with the wrong semantics would also be unsqueezed into `[1, 1, batch_size]`.

**Remediation:** Raise `ValueError` for 1D inputs instead of silently reshaping. Callers should be explicit about batch and sequence dimensions.

---

### NN-M-02: jepa_model.py Exceeds Size Guideline (jepa_model.py — 1034 lines)

**File:** `jepa_model.py`
At 1034 lines, this file contains 6 classes (`JEPAEncoder`, `JEPAPredictor`, `JEPACoachingModel`, `ConceptLabeler`, `VLJEPACoachingModel`) plus standalone loss functions. This exceeds the 500-line guideline by 2x. The `ConceptLabeler` alone (lines ~500-785) is a domain-specific labeling utility that could live in its own module.

---

### NN-M-03: Mid-File Imports in jepa_model.py (jepa_model.py:379)

**File:** `jepa_model.py`, line 379
`from Programma_CS2_RENAN.backend.nn.config import METADATA_DIM` appears mid-file inside the `JEPACoachingModel` class definition instead of at the top. This breaks import convention and makes dependency tracing harder.

---

### NN-M-04: Hardcoded Cosine Distance Threshold (jepa_model.py, forward_selective)

**File:** `jepa_model.py`, `forward_selective()`
The cosine distance threshold for selective decoding is hardcoded to `0.3`. This magic number determines which concept dimensions are "close enough" to trigger selective attention. The optimal threshold depends on the trained embedding space and should be configurable or learned.

---

### NN-M-05: Concept Label Leakage in label_tick() (jepa_model.py:535-567)

**File:** `jepa_model.py`, `ConceptLabeler.label_tick()`
`label_tick()` derives concept labels from the same tick-level features that the model receives as input (hp, crouching, scoped, enemies_visible, etc.). This creates a label leakage risk: the model can learn to reconstruct input features rather than learn meaningful predictive patterns.

The `label_from_round_stats()` method (line 635) exists as the leakage-free alternative (G-01 fix), deriving labels from round outcomes instead. However, `label_batch()` (line 762) still calls `label_tick()` as its primary path, meaning VL-JEPA training still uses the leaky labeler when RoundStats are unavailable.

**Remediation:** Add a warning when `label_batch()` falls through to `label_tick()`, and track the proportion of training data using the leaky path.

---

### NN-M-06: JEPA Negative Sampling Duplicated (train.py vs jepa_train.py)

**File:** `train.py`, `_train_jepa_self_supervised()`
The in-batch negative sampling logic (using `torch.randperm` to shuffle the batch as negatives) is independently implemented in both `train.py` and `jepa_train.py`. DRY violation. Any fix to one negative sampling strategy may not propagate to the other.

**Remediation:** Extract a shared `sample_in_batch_negatives()` utility.

---

### NN-M-07: RAP Output Dimension Differs from Other Models (factory.py:~60)

**File:** `factory.py`, `get_model()` for `TYPE_RAP`
RAP model defaults to `output_dim=10` while all other model types use `METADATA_DIM=25`. This inconsistency means:
- RAP and JEPA models cannot share evaluation code that assumes 25-dim output
- If RAP is ever evaluated through `evaluate_adjustments()` (which reads indices 0-3 of a 25-dim output), the indices may have different semantic meaning

---

### NN-M-08: coach_manager.py God-Class Risk (coach_manager.py — 920 lines)

**File:** `coach_manager.py`
At 920 lines, `CoachTrainingManager` handles: training orchestration, dataset splitting, feature extraction, maturity gating, overlay data generation, delta calculation, and interactive data formatting. This exceeds the 500-line threshold by 84% and mixes training lifecycle with presentation logic (overlay).

---

### NN-M-09: Dual Feature Lists Require Manual Sync (coach_manager.py)

**File:** `coach_manager.py`, `TRAINING_FEATURES` and `MATCH_AGGREGATE_FEATURES`
Two separate 25-element lists must be kept in sync with `METADATA_DIM`. While both have `assert len(...) == METADATA_DIM` guards, the semantic mapping between tick-level features and match-aggregate features is implicit. A rename or reorder in one list could pass the length check but break feature alignment.

---

### NN-M-10: Timezone-Naive datetime in Dataset Splitting (coach_manager.py)

**File:** `coach_manager.py`, `_assign_dataset_splits()`
Uses `datetime.now()` without timezone, producing timezone-naive timestamps. If the system timezone changes between runs, temporal split boundaries shift, potentially leaking future data into the training set.

---

### NN-M-11: training_orchestrator.py Size and Complexity (training_orchestrator.py — 890 lines)

**File:** `training_orchestrator.py`
At 890 lines, `TrainingOrchestrator` handles JEPA batch preparation, RAP Player-POV tensor construction, advantage computation, tactical role classification, and round stats fetching. The RAP batch preparation path (`_prepare_rap_batch()`) involves nested loops with PlayerKnowledge construction and complex fallback logic that is difficult to unit test.

---

### NN-M-12: Continuous vs Binary Advantage Mismatch (training_orchestrator.py)

**File:** `training_orchestrator.py`, `_compute_advantage()`
Returns a continuous `[0, 1]` advantage value from game state, but some downstream consumers may interpret it as binary (won/lost). The advantage computation uses alive-count ratios and bomb state, producing values like 0.65 or 0.35 — the semantic boundary between "advantage" and "disadvantage" at 0.5 is not documented.

---

### NN-M-13: Monthly Demo Limit Not Configurable (training_controller.py)

**File:** `training_controller.py`
`MAX_DEMOS_PER_MONTH = 10` is hardcoded. Power users who play frequently may hit this limit and be blocked from training on their most recent demos. This should be configurable via settings.

---

### NN-M-14: Deprecated Pipeline Still Importable (train_pipeline.py)

**File:** `train_pipeline.py`
Marked as deprecated with `DeprecationWarning` at function call time, but the module is still importable without any warning. Legacy 12-feature extraction (zero-padded to `INPUT_DIM`) is inconsistent with the current 25-feature standard. Any code that accidentally imports from this module gets silently wrong feature vectors.

**Remediation:** Add a module-level deprecation warning or remove entirely if no callers remain.

---

### NN-M-15: RoundStats Feature Dimension Gap (jepa_train.py)

**File:** `jepa_train.py`, `_roundstats_to_features()`
Produces a 16-dimensional feature vector from RoundStats fields, then zero-pads to `METADATA_DIM=25`. This means 9 out of 25 features are always zero during JEPA pre-training, wasting 36% of the input capacity. The JEPA encoder learns to ignore these dimensions during pre-training, but they become active during fine-tuning — creating a distribution shift.

---

### NN-M-16: UMAP Failure Silent (embedding_projector.py)

**File:** `embedding_projector.py`
UMAP is an optional dependency. If import fails, the projector silently degrades to TensorBoard-only mode with no user feedback. Since UMAP projections are the primary visualization (TensorBoard projector has been removed from TF 2.x), the silent failure effectively disables the feature.

---

### NN-M-17: Uncalibrated Maturity Thresholds (maturity_observatory.py)

**File:** `maturity_observatory.py`
The 5-signal maturity scoring system uses hardcoded thresholds for each state transition (e.g., belief_entropy > 0.8 → CRISIS, gate_specialization > 0.6 → CONVICTION). These thresholds are not empirically calibrated. The EMA smoothing factor `alpha=0.3` is similarly uncalibrated. Incorrect maturity classification could cause premature or delayed activation of coaching features.

---

### NN-M-18: WIN_PROB_FEATURES Maintained Separately (win_probability_trainer.py)

**File:** `win_probability_trainer.py`
`WIN_PROB_FEATURES` is a 9-element list of column names maintained separately from any schema definition. If the underlying data source renames a column, this list breaks silently at query time. `WIN_PROB_MIN_SAMPLES=20` duplicates the same threshold from `train.py` but is defined independently.

---

### NN-M-19: Indistinguishable Error Returns (inference/ghost_engine.py)

**File:** `ghost_engine.py`, `predict_tick()`
Returns `(0.0, 0.0)` for all failure modes: model disabled, model not loaded, missing map_name, CUDA error, and generic exception. The caller cannot distinguish between:
- "No RAP model available" (expected, non-actionable)
- "Map name missing from tick data" (bug, actionable)
- "CUDA out of memory" (resource issue, actionable)

**Remediation:** Return a result object with status field, or raise typed exceptions.

---

### NN-M-20: POV/Legacy Channel Semantics Not Validated at Runtime (ghost_engine.py:103-107)

**File:** `ghost_engine.py`, lines 103-107
The R4-04-01 comment documents that POV tensors use `Ch0=teammates, Ch1=last-known enemies` while legacy training uses `Ch0=enemies, Ch1=teammates` (reversed). This channel swap is gated by `USE_POV_TENSORS` setting, but there is no runtime validation that the loaded model was actually trained with the matching tensor mode. Loading a legacy-trained model with POV tensors enabled (or vice versa) silently produces wrong predictions.

---

### NN-M-21: SHAP KernelExplainer Recreated Per Call (evaluate.py:57)

**File:** `evaluate.py`, line 57
`shap.KernelExplainer` is instantiated on every call to `evaluate_adjustments()`. KernelExplainer initialization involves background dataset processing. For repeated calls (e.g., batch evaluation), this creates significant overhead.

---

### NN-M-22: SuperpositionLayer Forward Counter Not Atomic (layers/superposition.py:50)

**File:** `layers/superposition.py`, line 50
`self._forward_count += 1` is a non-atomic Python integer increment. While PyTorch training is typically single-threaded, if the model is used in a DataParallel or multi-threaded inference context, concurrent increments could lose counts. The counter drives the log interval check (line 53), so lost counts produce irregular logging.

---

## LOW Severity Findings

### NN-L-01: TeacherRefinementNN Alias (model.py:~140)
`TeacherRefinementNN = AdvancedCoachNN` is a pure alias with no behavioral difference. May confuse maintainers who expect a distinct model variant.

### NN-L-02: ML_INTENSITY Enum String Comparison (config.py)
`ML_INTENSITY` levels are compared as strings without validation. An unrecognized intensity string silently falls through to default behavior.

### NN-L-03: 16 Coaching Concepts as Module-Level List (jepa_model.py:~490)
`COACHING_CONCEPTS` is a module-level list of 16 string names. Could be a frozen dataclass or Enum for type safety and IDE completion.

### NN-L-04: Hardcoded JEPA Drift Threshold (jepa_trainer.py)
Embedding diversity collapse threshold (`variance < 0.01`) is hardcoded. Should be configurable for different model scales.

### NN-L-05: MIN_TRAINING_SAMPLES Hardcoded (train.py)
`MIN_TRAINING_SAMPLES = 20` should be in `training_config.py` alongside other training parameters.

### NN-L-06: Lazy Imports Add First-Call Latency (factory.py)
Each `get_model()` type branch uses a lazy import. While preventing circular imports, the first model creation call incurs import overhead that may surprise latency-sensitive callers.

### NN-L-07: Role Order Defined in Multiple Places (role_head.py)
`ROLE_OUTPUT_ORDER = ["LURKER", "ENTRY", "SUPPORT", "AWPER", "IGL"]` is defined in `role_head.py` but also implicitly assumed in `training_orchestrator.py`'s `_classify_tactical_role()`. A reorder in one place silently breaks the other.

### NN-L-08: FLEX_CONFIDENCE_THRESHOLD Magic Number (role_head.py)
`FLEX_CONFIDENCE_THRESHOLD = 0.35` and `LABEL_SMOOTHING_EPS = 0.02` are undocumented thresholds with no calibration rationale.

### NN-L-09: Maturity Tier Thresholds Hardcoded (coach_manager.py)
`CALIBRATING(0-49)`, `LEARNING(50-199)`, `MATURE(200+)` demo-count thresholds are magic numbers. Should be in config or documented with rationale.

### NN-L-10: Tactical Role Thresholds Hardcoded (training_orchestrator.py)
`_classify_tactical_role()` uses 10 tactical roles with inline numeric thresholds (e.g., `equipment_value < 2000` for eco). These CS2-specific constants should be named.

### NN-L-11: MIN_DIVERSITY_SCORE Magic Number (training_controller.py)
`MIN_DIVERSITY_SCORE = 0.3` has no documented calibration basis.

### NN-L-12: Training Monitor JSON Not Atomic (training_monitor.py)
JSON metrics file is read and written without atomic rename. A crash mid-write could corrupt the progress file.

### NN-L-13: Callback Registry No Deduplication (training_callbacks.py)
`CallbackRegistry` stores callbacks in a list. Registering the same callback instance twice causes double-dispatch with no warning.

### NN-L-14: Legacy 12-Feature Extraction (train_pipeline.py)
Deprecated pipeline extracts 12 features and zero-pads to `INPUT_DIM=25`. This zero-padding pattern is incompatible with the current `FeatureExtractor` which produces semantically meaningful 25-dim vectors.

### NN-L-15: No Learning Rate Scheduler in Standalone Pretrain (jepa_train.py)
`train_jepa_pretrain()` uses a fixed learning rate. `JEPATrainer` (in `jepa_trainer.py`) uses `CosineAnnealingLR`. The standalone pipeline misses this optimization.

### NN-L-16: TensorBoard Metadata Format Hardcoded (embedding_projector.py)
TSV metadata format for TensorBoard projector is hardcoded. No configurability for custom metadata columns.

### NN-L-17: SummaryWriter Resource Leak (tensorboard_callback.py)
`SummaryWriter` is created in `__init__` but no `close()` or `__del__` method exists. If the callback is instantiated but never used (or used and abandoned), the writer holds file handles open.

### NN-L-18: Duplicate isinstance Branches (inference/ghost_engine.py)
`predict_tick()` has three separate `isinstance(tick_data, dict)` checks (lines 93, 142, 177), each with dict/attribute access branches. A unified accessor wrapper would reduce duplication.

---

## Cross-Cutting Concerns

### 1. Feature Dimension Fragmentation

`METADATA_DIM=25` is the canonical dimension, but multiple subsystems operate on subsets:

| Component | Dimensions Used | Gap |
|-----------|----------------|-----|
| `evaluate.py` | 4 of 25 (indices 0-3) | 21 dims ignored |
| `jepa_train.py` (`_roundstats_to_features`) | 16 of 25 (9 zero-padded) | 9 dims wasted in pretraining |
| `factory.py` (RAP) | output_dim=10 | Different from METADATA_DIM |
| `win_probability_trainer.py` | 9 input features | Separate schema |
| `train_pipeline.py` (deprecated) | 12 features, zero-padded to 25 | Legacy incompatible |

This fragmentation means no single model type uses the full 25-dim capacity at both input and output, and transfer between model types requires dimension awareness.

### 2. Magic Number Proliferation

At least 15 hardcoded thresholds, scale factors, and limits are scattered across files instead of being centralized in `config.py` or `training_config.py`:

- Position scale: `1000` (coach_manager), `500.0` (config/ghost_engine)
- Maturity tiers: `0/50/200` (coach_manager)
- Diversity: `0.3` (training_controller), `0.01` (jepa_trainer)
- Monthly limit: `10` (training_controller)
- Min samples: `20` (train.py, win_probability_trainer)
- SHAP weight clamp: `0.5` (config → evaluate)
- Cosine threshold: `0.3` (jepa_model forward_selective)
- Role confidence: `0.35` (role_head)
- Label smoothing: `0.02` (role_head)

### 3. Code Size Violations

Three files exceed the 500-line guideline:

| File | Lines | Over |
|------|-------|------|
| `jepa_model.py` | 1034 | +107% |
| `coach_manager.py` | 920 | +84% |
| `training_orchestrator.py` | 890 | +78% |

Each could be decomposed without losing cohesion: `jepa_model.py` → models + labeler, `coach_manager.py` → training lifecycle + overlay, `training_orchestrator.py` → batch preparation + advantage computation.

### 4. Scale Factor Governance

`RAP_POSITION_SCALE = 500.0` is defined in `config.py` and correctly used in `ghost_engine.py`, but `coach_manager.py:851` uses `1000`. This indicates a governance gap: there is no enforcement that position scaling goes through the canonical constant. Any new code that handles ghost positions could introduce a third scale factor.

---

## Positive Observations

1. **Security:** `persistence.py` uses `weights_only=True` in `torch.load()` — prevents pickle-based RCE (P1-12 addressed).
2. **EMA correctness:** `ema.py` returns cloned tensors in `state_dict()` — prevents in-place mutation of shadow parameters.
3. **Feature parity validation:** `ghost_engine.py:156` calls `FeatureExtractor.validate_feature_parity()` at the inference boundary — catches training/inference feature drift.
4. **Gradient safety:** Training loops use `torch.nn.utils.clip_grad_norm_(max_norm=1.0)` — prevents gradient explosion.
5. **Architecture versioning:** `StaleCheckpointError` in `persistence.py` prevents loading checkpoints from incompatible model architectures.
6. **Embedding collapse detection:** `jepa_trainer.py` monitors embedding variance and warns at `< 0.01` — proactive diversity guard.
7. **Clean callback pattern:** `training_callbacks.py` uses opt-in ABC pattern with `CallbackRegistry` error isolation — a failing callback doesn't crash training.
8. **Lazy imports:** `factory.py` and `feature_engineering/__init__.py` use lazy imports to prevent circular dependencies and `_modulelock` deadlocks in multi-threaded Kivy.
9. **Fallback chain:** `persistence.py` implements a 4-tier checkpoint fallback (local user → local global → factory user → factory global) — never returns random weights.
10. **Zero-tensor tracking:** `training_orchestrator.py` tracks and filters zero-tensor fallbacks — prevents training on degenerate data.

---

## Remediation Priority

| Priority | ID | Fix |
|----------|----|-----|
| 1 | NN-H-01 | Replace `1000` with `RAP_POSITION_SCALE` in coach_manager.py:851-852 |
| 2 | NN-H-03 | Fix stale log message in jepa_train.py |
| 3 | NN-H-02 | Design decision: expand consumers to 25-dim or reduce OUTPUT_DIM to 4 |
| 4 | NN-M-01 | Raise ValueError for 1D inputs in _validate_input_dim |
| 5 | NN-M-19 | Return typed result from predict_tick() instead of bare tuple |
| 6 | NN-M-20 | Validate model training mode matches tensor mode at load time |
| 7 | NN-M-05 | Add leakage tracking when label_batch falls through to label_tick |
| 8 | NN-M-14 | Add module-level deprecation warning to train_pipeline.py |

---

*Report generated by exhaustive line-by-line audit of 31 files (7,420 lines) in `backend/nn/`.*
