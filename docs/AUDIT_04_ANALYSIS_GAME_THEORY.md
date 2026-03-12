# AUDIT_04: Analysis & Game Theory
## Date: 2026-03-10
## Scope: 11 files (3,672 lines)

---

### 1. Executive Summary

This report covers the `Programma_CS2_RENAN/backend/analysis/` package — the game-theoretic analysis layer that drives tactical coaching recommendations. The package implements Bayesian belief models, expectiminimax game trees, win probability prediction, role classification, entropy-based utility evaluation, momentum tracking, deception analysis, blind spot detection, and engagement range profiling.

**Findings breakdown:**
- **HIGH:** 1
- **MEDIUM:** 11
- **LOW:** 9
- **Total:** 21

The single HIGH finding is an architectural mismatch between the `WinProbabilityNN` used in `win_probability.py` (12-dim input) and the trainer in `win_probability_trainer.py` (9-dim input), which means a checkpoint trained by the trainer cannot be loaded by the predictor. The MEDIUM findings cluster around hand-tuned parameters that lack empirical calibration and some data-flow edge cases.

**Cross-references:**
- Report 1 (NN Core): `coach_manager.py` calls analysis engines; position scale mismatch (NN-H-01) may propagate into game state features
- Report 3 (Processing Pipeline): Feature parity (METADATA_DIM=25) does not directly affect this module, but `role_classifier.py` depends on baselines from `processing/baselines/role_thresholds.py`
- Report 12 (Config/Infrastructure): No CI test coverage metrics specific to game theory analysis

---

### 2. File-by-File Findings

---

#### `backend/analysis/__init__.py` (96 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| A-01 | LOW | Performance | 11-57 | Eager imports: importing the package triggers loading all 10 submodules (including PyTorch via `win_probability`). Any module that does `from backend.analysis import X` pays the full import cost even if it only needs one engine. | Consider lazy imports or split the `__all__` re-exports into a lightweight façade that defers heavy imports until first use. |

---

#### `backend/analysis/belief_model.py` (486 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| A-02 | MEDIUM | Correctness | 118-127 | **Hand-tuned log-odds weights (P8-02).** The Bayesian posterior uses hardcoded weights `[2.0, 1.5, -1.0, 1.0]` for threat, weapon lethality, armor, and exposure. These were hand-tuned with no empirical validation — if they are wrong, every death probability estimate is systematically biased. Comment documents validation path (logistic regression) but it has not been executed. | Fit logistic regression on actual death outcomes from parsed demos. Replace hardcoded weights with empirical coefficients. Add a CI check that validates the trained coefficients against the hardcoded defaults. |
| A-03 | MEDIUM | Data Integrity | 100-102 | **HP bracket estimation from equipment_value is a rough proxy.** `_hp_to_bracket()` maps raw HP to `full/damaged/critical` with thresholds at 80 and 40. These are reasonable for HP but the caller may pass equipment_value as a proxy for HP when actual HP is unavailable — the comment at L85 references "HP bracket" but the docstring says `player_hp: Player health (0-100)`, which is correct. If callers pass equipment_value, the brackets are meaningless. | Add an assertion or range check: `assert 0 <= player_hp <= 100`. |
| A-04 | LOW | Code Quality | 186 | Mid-file `import threading` — separated from top-level imports by ~180 lines of class definitions. | Move to top-level imports for readability. Minor — no functional impact. |
| A-05 | LOW | Correctness | 169 | Per-bracket calibration uses `len(group) >= 10` as minimum sample size but the class-level `MIN_CALIBRATION_SAMPLES = 30` applies to the global dataset. A bracket could calibrate with only 10 samples if the other brackets absorb the rest of the 30-sample minimum. | Consider applying `MIN_CALIBRATION_SAMPLES` per bracket or document why 10 is sufficient for per-bracket estimation. |

---

#### `backend/analysis/game_tree.py` (516 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| A-06 | MEDIUM | Correctness | 39-52 | **`_state_hash` uses Python `hash()`.** Python's `hash()` is randomized across processes (PYTHONHASHSEED). The transposition table is process-local so this is safe for single-process usage, but if TT entries are ever serialized/shared (e.g., for distributed analysis), hashes won't match. | Document the single-process assumption explicitly. If cross-process persistence is needed, switch to a deterministic hash (e.g., `hashlib.md5`). |
| A-07 | MEDIUM | Performance | 400-401 | **Transposition table eviction uses `next(iter(dict))` — FIFO, not LRU.** When `_tt` reaches `_TT_MAX_SIZE` (10,000), the oldest entry is evicted regardless of access recency. Frequently accessed states may be evicted while rarely used states linger. | Switch to `collections.OrderedDict` with move-to-end on access (LRU semantics), or accept FIFO as "good enough" for the bounded computation and document the trade-off. |
| A-08 | LOW | Correctness | 308-310 | **Chance node child.value temporarily holds opponent probability.** The comment at L309 says this is overwritten by minimax evaluation, but if `_expand` returns early due to budget exhaustion, the child may retain the probability as its value — which is not a win probability. The `evaluate()` method handles this by evaluating leaves via `_evaluate_leaf()`, so the stale value is only visible if someone inspects `child.value` directly before calling `evaluate()`. | Add a sentinel (`value = None`) and handle it in `evaluate()` with an explicit leaf evaluation, or remove the temporary assignment. |
| A-09 | LOW | Correctness | 327-340 | **Push action is symmetric — both sides lose 1 player.** This is a documented simplification ("DESIGN" comment at L323-326) and is acceptable given that `WinProbabilityPredictor` provides asymmetric correction at leaf nodes. | No action needed — design decision is well-documented. |

---

#### `backend/analysis/momentum.py` (218 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| A-10 | LOW | Correctness | 33-34 | **Momentum multipliers (P8-03) are hand-tuned.** `MOMENTUM_WIN_PER_STREAK = 0.05` and `MOMENTUM_LOSS_PER_STREAK = 0.04`. Comment documents validation path (analyze 500+ matches) but it has not been executed. | Run the proposed validation. Until then, the values are reasonable approximations. |
| A-11 | LOW | Code Quality | 60 | `is_hot` threshold 1.2 is hardcoded inline instead of using a named constant like `TILT_THRESHOLD`. | Extract to `HOT_THRESHOLD = 1.2` for consistency with `TILT_THRESHOLD`. |

---

#### `backend/analysis/win_probability.py` (299 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| A-12 | HIGH | Correctness | 72 | **MITIGATED** — `win_probability.py` (12-dim predictor) and `win_probability_trainer.py` (9-dim trainer) are intentionally separate architectures. A validation gate at `win_probability.py:131-142` explicitly rejects mismatched checkpoints with a `ValueError`. Cross-loading is impossible at runtime. ~~WinProbabilityNN input_dim=12 vs trainer's 9-dim architecture.~~ | ~~Align input dimensions.~~ No action needed — architectures are separate by design, guarded by checkpoint dimension validation. |
| A-13 | MEDIUM | Correctness | 192-223 | **Heuristic adjustments dominate predictions.** Without a trained checkpoint, `WinProbabilityNN` uses random weights, and the heuristic adjustments at L192-223 (player advantage floors/ceilings, bomb planted offsets, economy thresholds) override the NN output. This means the predictor is effectively a hand-crafted heuristic, not an ML model. The architecture exists but is non-functional until trained. | This is acceptable as a cold-start fallback, but document it clearly: "Without a checkpoint, this predictor is a heuristic engine with a dormant NN." |
| A-14 | LOW | Code Quality | 257-298 | `if __name__ == "__main__"` self-test block uses synthetic scenarios. Not reachable via test framework. | Move scenarios to a proper unit test or remove the self-test block. |

---

#### `backend/analysis/role_classifier.py` (562 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| A-15 | MEDIUM | Correctness | 444-448 | **AWPer dedup assigns FLEX without second-best role consideration.** When a duplicate AWPer is detected in `classify_team()`, the player is demoted to FLEX with confidence 0.5 instead of re-running classification with AWPer excluded. The player's actual second-best role (e.g., Lurker at 0.7 confidence) is discarded. | Re-run `_calculate_role_scores()` with AWPer excluded, or pick the second-highest scoring role from the existing scores dict. |
| A-16 | MEDIUM | Correctness | 333 | **FLEX_CONFIDENCE_THRESHOLD usage in neural classifier.** If neural confidence < `FLEX_CONFIDENCE_THRESHOLD`, the neural classifier returns `(FLEX, confidence)` — but this FLEX result can override a high-confidence heuristic AWPer classification via the consensus mechanism if the margin condition at L369 is met. This seems unlikely in practice (FLEX confidence would be low) but the logic path exists. | Add a guard: neural FLEX results should not override non-FLEX heuristic results. |
| A-17 | LOW | Code Quality | 405-410 | `KnowledgeRetriever()` is instantiated fresh on every call to `get_role_coaching()`. If the retriever has initialization cost (embedding model loading), this is wasteful. | Cache the retriever instance or use the singleton pattern. |

---

#### `backend/analysis/entropy_analysis.py` (183 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| A-18 | MEDIUM | Correctness | 32-36 | **_MAX_DELTA values are hand-estimated (P8-07).** Used to normalize utility effectiveness. If the estimates are too high, all utilities appear ineffective; if too low, they appear overpowered. Comment documents validation path (95th percentile from 100+ parsed demos) but it has not been executed. | Run the proposed empirical validation. Until then, note that coaching recommendations based on these scores may be miscalibrated. |
| A-19 | LOW | Concurrency | 91-132 | Thread safety via `_buffer_lock` is correctly implemented with try/finally. The lock is only acquired when using the shared grid buffer (default resolution); non-default resolutions allocate a fresh array and skip locking. Clean implementation. | No action needed. |

---

#### `backend/analysis/utility_economy.py` (405 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| A-20 | MEDIUM | Correctness | 162-167 | **Flash cost hardcoded as $200.** CS2 updated flash grenade cost from $200 to $250 in some patches (patch-dependent). If the game is running on a post-update version, the economy impact calculation understates flash cost by 25%. | Verify current CS2 flash cost and update. Consider making utility costs configurable or loading from a game-data JSON. |
| A-21 | MEDIUM | Correctness | 65-78 | **PRO_BASELINES are hand-estimated (P8-06).** Damage-per-throw, enemies-per-flash, and usage-rate baselines are manually estimated from VOD analysis, not computed from actual parsed demo data. Coaching recommendations ("Practice damage lineups") are calibrated against potentially inaccurate benchmarks. | Compute baselines from parsed pro demo files. Update the values and add a script to regenerate them periodically. |
| A-22 | MEDIUM | Performance | 106 | **np.mean on dict.values()** — creates intermediate list. Minor, but `statistics.mean()` or manual sum would avoid numpy overhead for typically 4 values. | Use `sum(scores) / len(scores)` for 4-element collections. Negligible impact. |

---

#### `backend/analysis/blind_spots.py` (220 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Clean implementation with proper error handling (B-01 try-except at L77), clear situation classification, and well-structured coaching output. | — |

---

#### `backend/analysis/deception_index.py` (245 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| A-23 | MEDIUM | Correctness | 184-203 | **`_detect_sound_deception` uses crouch ratio as sole proxy for sound deception.** Crouch ratio measures stealth tendency, not deliberate sound generation for misdirection. A player who never crouches (low crouch ratio → high deception score) might simply be unaware of sound, not deliberately deceptive. The metric conflates lack of stealth with active deception. | If demo data includes `is_walking` or velocity, use a multi-signal approach: combine crouch ratio with walking vs. sprinting transitions, weapon-switch sounds, and jump events. Alternatively, rename the metric to `noise_exposure_score` to reflect what it actually measures. |
| A-24 | MEDIUM | Correctness | 26-34 | **Composite deception weights (P8-04) are hand-tuned.** Sum is correctly 1.0 (`0.25 + 0.40 + 0.35`), but the relative weighting (rotation feints > sound > fake flash) is based on subjective assessment. Comment documents validation path (pro vs. amateur discriminative analysis) but it has not been executed. | Run the proposed discriminative validation. |

---

#### `backend/analysis/engagement_range.py` (442 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| A-25 | MEDIUM | Data Integrity | 49-118 | **Named positions are hardcoded.** 50+ callout positions for 8 maps are defined as Python literals. While `load_from_json()` exists (L184), the default positions cannot be updated without a code change. Position coordinates have not been verified against actual CS2 map data — they may be from CS:GO or approximate. | Extract default positions to a JSON file loaded at initialization. Verify coordinates against CS2 Source 2 map data. Add a coordinate validation test that checks positions are within map bounds. |
| A-26 | LOW | Correctness | 238-247 | **_ROLE_RANGE_BASELINES are hand-estimated.** Expected engagement profiles per role are defined without empirical data. The values are plausible but unvalidated. | Compute from parsed pro demo files. |

---

### 3. Cross-Cutting Concerns

#### 3.1 Pervasive Hand-Tuned Parameters

Eight of the eleven files contain hand-tuned constants with documented-but-unexecuted validation paths: belief_model (P8-02), momentum (P8-03), deception_index (P8-04), utility_economy (P8-06), entropy_analysis (P8-07), engagement_range (baselines), role_classifier (scoring weights), and game_tree (opponent priors). While each constant is individually reasonable and bounded, the **aggregate calibration debt** means the entire analysis layer operates on unvalidated assumptions. A single empirical calibration pass across all modules using parsed pro demo data would significantly improve coaching accuracy.

#### 3.2 Factory Function Inconsistency

Most modules provide factory functions (`get_X()`) that create **new instances** each call (not singletons), except `belief_model.py` which implements a true thread-safe singleton with double-checked locking. Callers may assume singleton behavior from the naming pattern. This is not a bug (stateless analyzers are fine to re-create) but the inconsistency could mislead developers.

#### 3.3 WinProbabilityPredictor as Shared Dependency

The game tree search (`game_tree.py`), blind spot detector (`blind_spots.py`), and coaching service all depend on `WinProbabilityPredictor` for leaf evaluation. The predictor's heuristic-only mode (no trained checkpoint) means all downstream analysis inherits the same hand-crafted approximations. Training the win probability model would cascade improvements through the entire analysis stack.

---

### 4. Inter-Module Dependency Risks

| Source Module | Depends On | Risk |
|---|---|---|
| `game_tree.py` | `win_probability.py` (leaf eval) | Circular import avoided via lazy import. If WinProbabilityNN architecture changes, game tree evaluation silently degrades to fallback heuristic (L412-421). |
| `blind_spots.py` | `game_tree.py` (optimal action) | Transitive dependency on win probability. Blind spot detection quality bounded by game tree depth (2) and heuristic leaf eval. |
| `role_classifier.py` | `processing/baselines/role_thresholds.py` | Cold-start guard works correctly. If threshold store fails to initialize, all classifications return FLEX/0%. |
| `role_classifier.py` | `nn/role_head.py` | Neural role head failure is gracefully handled (returns None → heuristic-only). |
| `__init__.py` | All 10 submodules | Eager import chain. Failure in any submodule import breaks the entire `analysis` package. |
| `engagement_range.py` | None (self-contained) | Clean — no external dependencies beyond logging. |
| `deception_index.py` | None (self-contained) | Clean — no external dependencies beyond logging and numpy. |

---

### 5. Remediation Priority Matrix

| Priority | ID | Severity | Finding | Effort |
|---|---|----------|---------|--------|
| 1 | A-12 | HIGH | WinProbabilityNN 12-dim vs trainer 9-dim mismatch | Medium — align feature extraction in both modules |
| 2 | A-02 | MEDIUM | Belief model log-odds weights unvalidated | High — requires logistic regression on demo data |
| 3 | A-15 | MEDIUM | AWPer dedup assigns FLEX without considering second-best role | Low — use existing scores dict |
| 4 | A-23 | MEDIUM | Sound deception uses crouch ratio as sole proxy | Medium — requires additional demo data fields |
| 5 | A-20 | MEDIUM | Flash cost hardcoded at $200 (may be $250 in current CS2) | Low — verify and update constant |
| 6 | A-25 | MEDIUM | Named positions hardcoded as Python literals | Medium — extract to JSON, verify coordinates |
| 7 | A-06 | MEDIUM | _state_hash uses non-deterministic Python hash() | Low — document assumption or switch to hashlib |
| 8 | A-07 | MEDIUM | Transposition table uses FIFO eviction (not LRU) | Low — switch to OrderedDict if perf matters |
| 9 | A-21 | MEDIUM | PRO_BASELINES hand-estimated | High — requires pro demo data analysis |
| 10 | A-18 | MEDIUM | _MAX_DELTA entropy normalization hand-estimated | High — requires empirical validation |
| 11 | A-24 | MEDIUM | Deception index composite weights unvalidated | Medium — requires pro vs amateur dataset |
| 12 | A-13 | MEDIUM | Heuristic adjustments dominate untrained NN | Low — documentation improvement |
| 13 | A-16 | MEDIUM | Neural FLEX can override heuristic non-FLEX | Low — add guard clause |
| 14 | A-22 | MEDIUM | np.mean on 4-element dict values | Negligible |
| 15 | A-01 | LOW | Eager package imports trigger full module loading | Medium — lazy import refactor |
| 16 | A-03 | LOW | HP range assertion missing in estimate() | Low |
| 17 | A-04 | LOW | Mid-file threading import | Trivial |
| 18 | A-05 | LOW | Per-bracket calibration minimum (10) vs global (30) | Low |
| 19 | A-08 | LOW | Chance node value temporarily holds probability | Low |
| 20 | A-10 | LOW | Momentum multipliers hand-tuned | Part of calibration pass |
| 21 | A-11 | LOW | is_hot threshold not a named constant | Trivial |
| 22 | A-14 | LOW | Self-test block in win_probability.py | Low |
| 23 | A-17 | LOW | KnowledgeRetriever re-instantiated per call | Low |
| 24 | A-26 | LOW | Role range baselines hand-estimated | Part of calibration pass |

---

### 6. Coverage Attestation

All 11 files in `Programma_CS2_RENAN/backend/analysis/` were read in their entirety:

- [x] `__init__.py` (96 lines) — read in full
- [x] `belief_model.py` (486 lines) — read in full (L1-250 verified, L250-486 verified)
- [x] `game_tree.py` (516 lines) — read in full (L1-250 verified, L250-516 verified)
- [x] `momentum.py` (218 lines) — read in full
- [x] `win_probability.py` (299 lines) — read in full (L1-190 verified, L190-299 verified)
- [x] `role_classifier.py` (562 lines) — read in full (L1-300 verified, L300-562 verified)
- [x] `entropy_analysis.py` (183 lines) — read in full
- [x] `utility_economy.py` (405 lines) — read in full (L1-100 verified, L100-405 verified)
- [x] `blind_spots.py` (220 lines) — read in full
- [x] `deception_index.py` (245 lines) — read in full
- [x] `engagement_range.py` (442 lines) — read in full (L1-100 verified, L100-442 verified)

**Total lines audited: 3,672**
**Files audited: 11/11 (100%)**
