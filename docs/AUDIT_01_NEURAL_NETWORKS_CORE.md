# Audit Report 01 — Neural Networks Core

**Scope:** `backend/nn/` (excl. `rap_coach/`) — 31 files, ~7,420 lines | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 3 HIGH | 21 MEDIUM | 33 LOW

---

## HIGH Findings

| ID | File | Finding |
|---|---|---|
| NN-H-01 | jepa_train.py:334-415 | **[FIXED 2026-03-13]** Added `clip_grad_norm_(model.parameters(), max_norm=1.0)` to finetune loop. |
| NN-H-02 | training_orchestrator.py:316-323 | **[FIXED 2026-03-13]** Validation now uses shared `trainer.encode_raw_negatives()` method — identical 3D encoding path as training. |
| NN-H-03 | training_orchestrator.py:367-399 | **[FIXED 2026-03-13]** Negatives now sampled from cross-match pool (previous batches) instead of same batch. Pool warms up over first ~50 batches. |

## MEDIUM Findings

| ID | File | Finding |
|---|---|---|
| NN-M-02 | jepa_model.py | 1044 lines — exceeds 500-line guideline by 2x |
| NN-M-03 | coach_manager.py:750-756 | **[FIXED 2026-03-13]** Added `is not None` guard matching `_prepare_tensors` pattern. |
| NN-M-04 | coach_manager.py:894-906 | `_apply_dynamic_window_targets` creates strategy target from equipment_value / 10000, not actual tactical role. RAP model learns equipment-tier buckets, not tactics. Legacy path bypasses orchestrator. |
| NN-M-05 | jepa_model.py | `label_tick()` leakage risk — documented with WARNING but function retained |
| NN-M-06 | evaluate.py:56-61 | `evaluate_adjustments` docstring says "25 keys" but only produces OUTPUT_DIM=10 keys. Misleading for downstream consumers. |
| NN-M-07 | hflayers.py:78-121 | `Hopfield` uses fixed learnable memory bank. `stored_patterns` and `pattern_projection_weight` params accepted but never used (dead API). Differs from original hflayers library. |
| NN-M-08 | coach_manager.py | 920 lines — god-class mixing training + presentation |
| NN-M-09 | coach_manager.py | Dual feature lists (TRAINING_FEATURES, MATCH_AGGREGATE_FEATURES) require manual sync |
| NN-M-10 | jepa_trainer.py:43 | **[FIXED 2026-03-13]** `T_max` now parameterized (passed from orchestrator's `max_epochs`). Orchestrator now steps scheduler per epoch. |
| NN-M-11 | training_orchestrator.py | 887 lines — RAP batch prep has nested loops hard to unit test |
| NN-M-12 | training_orchestrator.py | **[FIXED 2026-03-13]** Missing outcomes now use 0.0 placeholder + `val_mask=False`. Loss computation masks out these samples. Genuine 0.5 from `_compute_advantage` is unaffected. |
| NN-M-13 | jepa_model.py:597 | `ConceptLabeler.label_tick()` uses `.item()` inconsistently — `min(labels[5].item() + ..., 1.0)` returns Python float assigned to tensor element. Breaks if tensors on GPU. |
| NN-M-14 | train.py:211-216 | DataLoader yields 2D tensors; `AdvancedCoachNN._validate_input_dim` unsqueezes to (batch,1,features). LSTM always sees seq_len=1 — temporal capabilities wasted (effectively feedforward). |
| NN-M-15 | jepa_train.py | 9 of 25 features always zero-padded — 36% input wasted in pretraining |
| NN-M-17 | maturity_observatory.py | Uncalibrated maturity thresholds and EMA alpha |
| NN-M-18 | win_probability_trainer.py | WIN_PROB_FEATURES maintained separately from schema |
| NN-M-20 | ghost_engine.py | No runtime validation that loaded model matches POV/legacy tensor mode |
| NN-M-22 | superposition.py | `_forward_count += 1` non-atomic increment |
| NN-M-23 | training_orchestrator.py:822-881 | `_classify_tactical_role` T-side has no path to ROLE_ROTATION; CT-side never gets support role. Asymmetric role classification. |
| NN-M-24 | role_head.py:254 | `epoch` variable used in log after loop — fragile scope dependency (correct but misleading). |
| NN-M-25 | train.py:164-165 | `_prepare_splits` return order confusing — works correctly but naming misleads about train vs full X. |

## LOW Findings

| ID | File | Finding |
|---|---|---|
| NN-L-02 | config.py | ML_INTENSITY string comparison without validation |
| NN-L-03 | jepa_model.py | COACHING_CONCEPTS as list — could be Enum |
| NN-L-04 | jepa_trainer.py | Hardcoded drift threshold 0.01 |
| NN-L-05 | train.py | `MIN_TRAINING_SAMPLES = 20` should be in training_config.py |
| NN-L-06 | factory.py | Lazy imports add first-call latency |
| NN-L-07 | role_head.py | ROLE_OUTPUT_ORDER defined in multiple places |
| NN-L-08 | role_head.py | FLEX_CONFIDENCE_THRESHOLD and LABEL_SMOOTHING_EPS undocumented |
| NN-L-09 | coach_manager.py | Maturity tier thresholds (0/50/200) are magic numbers |
| NN-L-10 | training_orchestrator.py | Tactical role thresholds hardcoded inline |
| NN-L-11 | training_controller.py | MIN_DIVERSITY_SCORE = 0.3 undocumented |
| NN-L-12 | training_monitor.py | JSON metrics file write not atomic |
| NN-L-13 | training_callbacks.py | Callback registry has no deduplication |
| NN-L-14 | train_pipeline.py | Legacy 12-feature extraction incompatible with current 25-dim |
| NN-L-15 | jepa_train.py | No LR scheduler in standalone pretrain |
| NN-L-16 | embedding_projector.py | TensorBoard metadata format hardcoded |
| NN-L-17 | tensorboard_callback.py | SummaryWriter resource leak (no close/del) |
| NN-L-18 | ghost_engine.py | Three separate `isinstance(tick_data, dict)` branches |
| NN-L-19 | config.py:27-28 | `_device_logged` and `_cached_device` module-level globals without thread safety. Worst case: redundant logging. |
| NN-L-20 | model.py:36-38 | `AdvancedCoachNN(input_dim=None)` — no validation, fails with unhelpful TypeError from nn.LSTM. |
| NN-L-21 | ema.py:81-86 | `EMA.restore()` is silent no-op if called without preceding `apply_shadow()` — model stays on EMA weights. |
| NN-L-22 | train.py:256-258 | `_log_epoch` function defined but never called (only used in deprecated `train_pipeline.py`). |
| NN-L-23 | dataset.py:50-54 | `SelfSupervisedDataset.__len__` uses `max(0, ...)` but constructor already raises on <=0. |
| NN-L-24 | train.py:261, train_pipeline.py:107 | `_finalize_training` duplicated between files. |
| NN-L-25 | train.py:247-248 | `run_training()` accesses private methods `_fetch_training_data`, `_prepare_tensors` of CoachTrainingManager. |
| NN-L-26 | experimental/rap_coach/communication.py:12-17 | `_compute_relative_direction` — 180 degrees falls through all sectors. `atan2` can return exactly pi/-pi. |
| NN-L-27 | experimental/rap_coach/perception.py:78-84 | `_make_resnet_stack` ignores `num_blocks` list structure — `[1,2,2,1]` and `[6]` produce identical networks. |
| NN-L-28 | experimental/rap_coach/model.py:58-68 | `RAPCoachModel.forward()` uses `assert` for input validation — stripped with `-O` flag. |
| NN-L-29 | maturity_observatory.py:201-212 | `_compute_value_accuracy` denominator can be near-zero if initial val_loss is small. |
| NN-L-30 | jepa_train.py:420 | `save_jepa_model` saves dict with `is_pretrained` boolean. `weights_only=True` handles this in PyTorch 2.x but fragile. |
| NN-L-31 | train.py, train_pipeline.py | Identical `_finalize_training` — will diverge if either is edited. |
| NN-L-32 | experimental/rap_coach/pedagogy.py:87-98 | `_detect_utility_need` uses `sigmoid(hidden.mean())` as utility proxy — arbitrary signal. |
| NN-L-33 | experimental/rap_coach/chronovisor_scanner.py:148-168 | `_load_model` captures maturity gate result but ignores `is_mature` — loads regardless. |

## Cross-Cutting

1. **Feature Dimension Fragmentation** — evaluate.py uses 4/25, jepa_train uses 16/25, RAP output=10, win_prob uses 9. No model uses full 25-dim at both input and output.
2. **Magic Number Proliferation** — 15+ hardcoded thresholds scattered across files.
3. **Code Size Violations** — jepa_model.py (1044), coach_manager.py (920), training_orchestrator.py (887) all exceed 500-line guideline.
4. **Five Training Loops** — `_execute_validated_loop`, `_train_jepa_self_supervised`, `train_jepa_pretrain`, `TrainingOrchestrator._run_epoch`, `JEPATrainer.train_epoch`. Scheduler stepping is inconsistent between them.
5. **11 Deprecated Shims** — `backend/nn/rap_coach/` contains 11 redirect files to `experimental/rap_coach/`. Import overhead and maintenance burden.

## Resolved Since 2026-03-10

Removed 11 MEDIUM findings (NN-M-01, 03, 04, 06, 07, 10, 13, 14, 16, 19, 21) and 1 LOW (NN-L-01) — fixed in commits 6bf7789..45514a2. Key fixes: silent reshape replaced with explicit ValueError, OUTPUT_DIM consistency, timezone-aware datetime, configurable MAX_DEMOS_PER_MONTH, UMAP failure logging, deprecation warnings.
