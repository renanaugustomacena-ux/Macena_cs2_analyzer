# AUDIT_03: Processing Pipeline
## Date: 2026-03-10
## Scope: 28 files (6,679 lines)

---

### 1. Executive Summary

The Processing Pipeline is the data transformation backbone of the CS2 Coach — responsible for converting raw demo tick data into feature vectors, tensors, baselines, heatmaps, and skill assessments that feed the ML models and coaching engine.

**Total files audited:** 28
**Findings breakdown:** ~~4~~ 0 HIGH (4 FIXED) / 16 MEDIUM / 12 LOW (32 total, 4 resolved)

**Critical cross-references:**
- Report 6 (Storage): ProPlayerStatCard unbounded JSON field affects `stat_aggregator.py` → consumed by `pro_baseline.py`
- Report 8 (Core Engine): Session engine's tri-daemon lifecycle governs when `data_pipeline.py` and `tensor_factory.py` are invoked
- Report 12 (Config): `BASE_DIR` and `get_resource_path()` used by `external_analytics.py` and `pro_baseline.py` for CSV dataset loading

---

### 2. File-by-File Findings

---

#### Programma_CS2_RENAN/backend/processing/data_pipeline.py (336 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-01 | MEDIUM | Security | 98-102 | Scaler persistence via `joblib.dump()`/`joblib.load()` carries deserialization risk. A crafted `.joblib` file can execute arbitrary code on load (same class of vulnerability as pickle RCE). The scaler file is self-generated but lives on disk with no integrity verification. | Add HMAC signature to the persisted scaler file (similar to RASPGuard manifest signing). Verify signature before `joblib.load()`. |
| P3-02 | LOW | Configuration | 31 | `_MAX_PIPELINE_ROWS = 50_000` is a hard cap with no override mechanism. If the dataset legitimately grows beyond 50K rows, data is silently truncated. | Make configurable via `HeuristicConfig` or a pipeline config dataclass. Log a warning when the cap is hit. |

---

#### Programma_CS2_RENAN/backend/processing/feature_engineering/vectorizer.py (461 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-03 | LOW | Correctness | 35-72 | `WEAPON_CLASS_MAP` enumerates all known CS2 weapons. If Valve adds new weapons in an update, they default to `"unknown"` silently with no logging or alerting. | Log at WARNING level when an unknown weapon is encountered, with the weapon name, to aid maintenance. |

---

#### Programma_CS2_RENAN/backend/processing/tensor_factory.py (746 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-04 | MEDIUM | Correctness | 42-58 | `TrainingTensorConfig` uses 64×64 resolution while `InferenceTensorConfig` uses 224×224. Models must use adaptive pooling to handle both sizes. If any downstream model assumes fixed spatial dimensions, shape errors will occur silently (spatial features will be averaged over wrong grid). | Add an assertion in the model forward pass verifying input spatial dimensions match expected config. Document the adaptive pooling requirement in the model interface. |
| P3-05 | LOW | Performance | 14-16 | Lazy `scipy` import (`from scipy.ndimage import gaussian_filter`) on first invocation adds import latency (~200-500ms) to the first heatmap generation. | Pre-import during application startup in a background thread. |

---

#### Programma_CS2_RENAN/backend/processing/tick_enrichment.py (362 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-06 | MEDIUM | Correctness | 89-95 | Field-of-view (FOV) is hardcoded at 90° for enemies_visible computation. CS2 scoped weapons dramatically reduce FOV (AWP scope ≈ 10-40°, AUG/SG scope ≈ 55°). This means scoped players are reported as seeing enemies they cannot actually see, polluting the "NO-WALLHACK" model. | Accept weapon/scope state as input and compute FOV dynamically: 90° default, reduced when scoped. This improves PlayerKnowledge accuracy. |

---

#### Programma_CS2_RENAN/backend/processing/player_knowledge.py (611 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-07 | MEDIUM | Correctness | 180-195 | Utility zone tracking (smoke/molotov) uses time-based expiry but doesn't account for early dissipation (e.g., smoke dispersed by HE grenade, molotov extinguished by smoke). Players may "know" about utility that no longer exists. | Track utility destruction events from the demo parser and remove zones on destruction, not just timeout. |
| P3-08 | LOW | Correctness | 142, 155 | Memory decay tau values (`sound_decay_tau=3.0`, `visual_decay_tau=5.0` seconds) are plausible but not empirically validated against pro player reaction patterns. | Document as heuristic (G-05 deferred). Flag for calibration when pro-annotated dataset becomes available. |

---

#### Programma_CS2_RENAN/backend/processing/state_reconstructor.py (133 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Clean, focused module with proper feature parity validation and `require_pov` enforcement. | — |

---

#### Programma_CS2_RENAN/backend/processing/feature_engineering/base_features.py (189 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-09 | MEDIUM | Data Integrity | 165-175 | `load_learned_heuristics()` reads JSON from disk without schema validation. A malformed or tampered JSON file could cause silent `KeyError` failures when downstream code accesses expected keys. | Validate loaded JSON against `HeuristicConfig` fields. Reject and log (not crash) if schema doesn't match, falling back to defaults. |

---

#### Programma_CS2_RENAN/backend/processing/feature_engineering/kast.py (162 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-10 | MEDIUM | Correctness | 122-162 | `estimate_kast_from_stats()` uses a linear heuristic approximation: `kast ≈ 1 - (deaths_per_round × penalty)`. This diverges significantly from actual KAST for edge cases (very high K/D or very low round counts), producing values that may exceed the [0, 1] bounds before clamping. | Document the expected error margin. Consider using a logistic function instead of linear approximation for better boundary behavior. |

---

#### Programma_CS2_RENAN/backend/processing/feature_engineering/rating.py (182 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-11 | MEDIUM | Code Quality | 130-182 | `compute_hltv2_rating_regression()` is marked as dead code (F2-39) but remains importable and is listed in the module namespace. Could be accidentally used instead of the canonical component-based `compute_hltv2_rating()`. | Either remove entirely or prefix with `_` to mark private. Add a deprecation warning if it must remain for reference. |
| P3-12 | LOW | API Contract | 45-50 | KAST ratio vs percentage contract (0.0-1.0 vs 0-100) is documented in comments but not enforced at the function boundary — relies entirely on upstream `sanity.py` enforcement. | Add an assertion `0 <= kast <= 1.0` at the entry of `compute_hltv2_rating()` to catch contract violations early. |

---

#### Programma_CS2_RENAN/backend/processing/feature_engineering/role_features.py (263 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-13 | MEDIUM | Correctness | 22-55 | `ROLE_SIGNATURES` centroids are static constants. `get_adaptive_signatures()` adjusts confidence via `meta_drift` but never updates the centroids themselves. As the CS2 meta evolves, the centroids become stale while only the confidence multiplier changes. | Allow `meta_drift` to shift centroids proportionally to drift magnitude, or periodically recompute centroids from recent pro data. |

---

#### Programma_CS2_RENAN/backend/processing/heatmap_engine.py (295 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-14 | MEDIUM | Performance | 78-95 | `generate_heatmap_data()` creates dense numpy arrays sized `(resolution, resolution)`. At 224×224 inference resolution, this is ~50KB per heatmap (manageable). But if resolution is ever increased (e.g., 512×512 for export), memory scales quadratically with no cap. | Add a max resolution constant and validate input resolution against it. |

---

#### Programma_CS2_RENAN/backend/processing/cv_framebuffer.py (193 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-15 | MEDIUM | Correctness | 120-145 | HUD region extraction coordinates (kill feed position, health bar, ammo counter) are hardcoded for a specific CS2 UI layout. Valve periodically updates the CS2 HUD, and any coordinate shift will cause the frame buffer to extract wrong regions, corrupting CV analysis. | Externalize HUD coordinates to a versioned config file. Add a CS2 version check or visual landmark detection for auto-calibration. |

---

#### Programma_CS2_RENAN/backend/processing/round_stats_builder.py (568 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-16 | MEDIUM | Correctness | 185-195 | Flash assist detection uses a fixed 2-second window after flashbang detonation. CS2's actual flash duration varies by distance, grenade type, and whether the player was facing the flash (0.1s to 5.2s). A fixed window over-counts distant flashes and under-counts close ones. | Use the actual flash duration from demo events (`player_blind` event includes duration). Fall back to 2s only if event data is missing. |

---

#### Programma_CS2_RENAN/backend/processing/skill_assessment.py (155 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-17 | MEDIUM | Correctness | 98-110 | Gaussian CDF approximation via sigmoid (`1 / (1 + exp(-1.7 * z))`) deviates from the true normal CDF by up to ~2% at the tails (|z| > 2). For coaching purposes this is acceptable, but percentile labels ("top 5%") may be inaccurate by 1-2 percentile points. | Document the approximation error. For display, consider using `math.erfc()` which is exact and available in the standard library. |

---

#### Programma_CS2_RENAN/backend/processing/external_analytics.py (192 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-18 | ~~HIGH~~ **FIXED** | Correctness | 79-82 | `_prepare_tournament()` accesses `self.tournament_df[["accuracy", "econ_rating", "utility_value"]]` without checking that these columns exist. If the `tournament_advanced_stats.csv` file has different column names (or a subset), this raises `KeyError` and crashes `EliteAnalytics.__init__()`, making the entire analytics subsystem unavailable. | **FIXED (2fa2cf3):** Column existence is now guarded via `[c for c in adv if c in self.tournament_df.columns]` before accessing. |
| P3-19 | LOW | Observability | 173-178 | Z-score calculations skip NaN/Inf values (via `np.isfinite()` guard) but don't report how many values were skipped. A dataset with mostly NaN values would produce valid-looking but statistically meaningless Z-scores. | Log the skip count when > 0. If > 50% of values are skipped, return empty dict with a warning. |

---

#### Programma_CS2_RENAN/backend/processing/connect_map_context.py (113 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-20 | LOW | Configuration | 28-32 | Z-penalty factor for multi-level distance calculation is hardcoded at a single value for all maps. Maps like Nuke and Vertigo have very different vertical scales than Mirage or Dust2. | Make Z-penalty configurable per map, sourced from `spatial_data.py` metadata. |

---

#### Programma_CS2_RENAN/backend/processing/validation/dem_validator.py (201 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-21 | LOW | Configuration | 45 | Maximum file size constraint (2GB) may be tight for exceptionally long pro matches with extensive overtime (40+ rounds). While rare, such matches produce demo files approaching 1.8-2.0 GB. | Increase to 3GB or make configurable. |

---

#### Programma_CS2_RENAN/backend/processing/validation/drift.py (176 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-22 | MEDIUM | Correctness | 142-155 | `should_retrain()` uses a threshold of 3/5 drifted features with no hysteresis. If drift oscillates around the boundary (2-3 features alternating), the system flip-flops between "retrain needed" and "stable", causing unnecessary retraining or missed drift. | Add hysteresis: require 3/5 to trigger retrain, but require drop to 1/5 before declaring stable again. |
| P3-23 | LOW | Configuration | 85 | Z-score drift threshold is hardcoded at 2.0 for all features. Features with naturally higher variance (e.g., `adr`) may trigger false positives while low-variance features (e.g., `kast`) may miss real drift. | Allow per-feature drift thresholds, defaulting to 2.0 if not specified. |

---

#### Programma_CS2_RENAN/backend/processing/validation/schema.py (95 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-24 | LOW | Completeness | 13-27 | Schema validates only 8 columns (`round`, `kills`, `deaths`, `assists`, `adr`, `headshot_pct`, `kast`, `accuracy`) while the `FeatureExtractor` in `vectorizer.py` produces 25 features. The remaining 17 features are computed downstream and never schema-validated. | Consider a separate schema validation step for the 25-dim feature vector after extraction, not just the raw demo output. |
| P3-25 | LOW | Error Handling | 42-44 | Unknown schema version silently falls back to latest (`SCHEMA_VERSION`) without error. This could mask version incompatibilities between the demo parser and validator. | Log at WARNING level (currently does), but also include the calling context to aid debugging. |

---

#### Programma_CS2_RENAN/backend/processing/validation/sanity.py (128 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Well-designed with strict/trim modes, KAST auto-conversion (P-SAN-01), and proper copy semantics in trim mode. | — |

---

#### Programma_CS2_RENAN/backend/processing/baselines/pro_baseline.py (516 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-26 | ~~HIGH~~ **FIXED** | Performance | 434 | `get_temporal_baseline()` calls `session.exec(query).all()` on ProPlayerStatCard with no `.limit()`. Unlike `_load_pro_from_db()` which caps at 5,000 rows, the temporal path loads the entire table into memory. With a growing HLTV scraper, this could be tens of thousands of ORM objects. | **FIXED (2fa2cf3):** Query now uses `.limit(5000)` to bound result set. |
| P3-27 | ~~HIGH~~ **FIXED** | Correctness | 504-514 | `_metric_to_baseline_key()` maps both `"opening_kill_ratio"` and `"opening_duel_win_pct"` to the same output key `"opening_duel_win_pct"`. Since `BASELINE_METRICS` contains both, `compute_weighted_baseline()` processes both — the second silently overwrites the first in the baseline dict, producing incorrect weighted statistics. | **FIXED (2fa2cf3):** Each metric now maps to its own distinct key (`opening_kill_ratio` → `opening_kill_ratio`, `opening_duel_win_pct` → `opening_duel_win_pct`). |
| P3-28 | MEDIUM | Correctness | 122 | Survival rate approximation `max(0.0, min(1.0, 1.0 - c.dpr))` is a crude linear proxy. HLTV doesn't expose a dedicated survival metric, and `dpr` (deaths per round) doesn't capture survival nuance (clutch ability, trade positioning). Values near 0.38 (documented mean) are plausible but the approximation breaks down at extremes. | Document as a known approximation limitation. Consider using `rounds_survived / rounds_played` if available from stat cards. |
| P3-29 | LOW | Code Quality | 301-305 | `import math`, `from datetime import ...`, and `from typing import List` appear mid-file (line 301-305) instead of at the top. While not harmful, this violates PEP 8 import ordering and makes the file harder to scan. | Move imports to the top of the file. |

---

#### Programma_CS2_RENAN/backend/processing/baselines/meta_drift.py (141 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-30 | ~~HIGH~~ **FIXED** | Performance | 55-60 | `calculate_spatial_drift()` historical tick query (`hist_stmt`) has NO `.limit()` clause. For maps with extensive pro match history, this could load millions of PlayerTickState rows into memory, causing OOM. The recent query is similarly unbounded. | **FIXED (2fa2cf3):** Both recent and historical queries now have `.limit(50_000)`. |
| P3-31 | MEDIUM | Architecture | 32-60 | `calculate_spatial_drift()` queries `PlayerTickState` from the monolith DB, but detailed tick data lives in per-match SQLite databases (via `MatchDataManager`). The monolith's tick data may be sparse or incomplete, reducing spatial drift accuracy. | Consider querying per-match databases (like `get_pro_positions()` in `pro_baseline.py` does) for more complete spatial data. |

---

#### Programma_CS2_RENAN/backend/processing/baselines/role_thresholds.py (320 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-32 | MEDIUM | Completeness | 157-236 | `learn_from_pro_data()` computes thresholds for only 5 of 9 defined types (`awp_kill_ratio`, `entry_rate`, `assist_rate`, `survival_rate`, `solo_kill_rate`). The remaining 4 (`first_death_rate`, `utility_damage_rate`, `clutch_rate`, `trade_rate`) are never populated and permanently return `None`. | Either add computation logic for the remaining 4 thresholds, or remove them from `_thresholds` to avoid false expectations. |
| P3-33 | MEDIUM | Data Integrity | 239-273 | `persist_to_db()` iterates over all thresholds and adds them to the session, but doesn't wrap in an explicit transaction boundary. If the session fails mid-persist (e.g., DB lock timeout), some thresholds may be saved while others are not, creating an inconsistent persisted state. | Wrap the entire persist loop in an explicit `session.begin()` / `session.commit()` block. |
| P3-34 | LOW | Correctness | 176 | `datetime.now()` used without `timezone.utc` parameter. The rest of the codebase (meta_drift.py, pro_baseline.py) consistently uses `datetime.now(timezone.utc)`. This creates timezone inconsistency in `last_updated` timestamps. | Change to `datetime.now(timezone.utc)`. |

---

#### Programma_CS2_RENAN/backend/processing/baselines/nickname_resolver.py (129 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| P3-35 | MEDIUM | Correctness | 55, 128 | Exact match path compares `ProPlayer.nickname == clean_name` where `clean_name` is always lowercased (via `_clean()`). SQLite's `==` operator is case-sensitive by default for text columns. If the DB stores `"s1mple"` but `_clean()` produces `"s1mple"`, it matches. But if DB stores `"S1mple"`, the exact match fails, forcing fallback to O(n) substring/fuzzy matching for every query. | Use `func.lower(ProPlayer.nickname) == clean_name` in the SQL query, or apply `COLLATE NOCASE` to the nickname column in the schema. |

---

#### Programma_CS2_RENAN/backend/processing/baselines/__init__.py (1 line — empty)

No findings.

---

#### Programma_CS2_RENAN/backend/processing/__init__.py (1 line — empty)

No findings.

---

#### Programma_CS2_RENAN/backend/processing/validation/__init__.py (3 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Clean re-export of `detect_feature_drift`, `validate_demo_sanity`, `validate_demo_schema`. | — |

---

#### Programma_CS2_RENAN/backend/processing/feature_engineering/__init__.py (60 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Well-designed lazy import mechanism via `__getattr__` to prevent `_modulelock` deadlocks in multi-threaded Kivy app. All exported names verified to exist in their respective modules. | — |

---

### 3. Cross-Cutting Concerns

#### 3.1 Unbounded Query Pattern (HIGH)
Three separate files perform database queries without row limits on potentially large tables:
- `meta_drift.py:55-60` — PlayerTickState historical query
- `meta_drift.py:44-51` — PlayerTickState recent query
- `pro_baseline.py:434` — ProPlayerStatCard full table load

This pattern can cause OOM crashes as the database grows with more scraped pro data. The bounded pattern exists in the codebase (`_load_pro_from_db()` uses `.limit(5000)` and `.yield_per(500)`) but wasn't applied consistently.

#### 3.2 Hardcoded CS2 Game Constants
Multiple files hardcode CS2-specific values that Valve can change in patches:
- FOV = 90° (tick_enrichment.py)
- Flash duration = 2s (round_stats_builder.py)
- HUD coordinates (cv_framebuffer.py)
- Trade kill window = 5s (kast.py)
- Kills per round max = 10 (sanity.py)

These should ideally be centralized in a `cs2_constants.py` module that can be updated in one place when patches change game mechanics.

#### 3.3 Baseline Provenance Gap
The baseline system has three tiers (DB → CSV → hard-coded defaults) but consumers of baselines don't know which tier produced the data. Only `HARD_DEFAULT_BASELINE` adds a `_provenance` key. Z-scores computed from hard-coded defaults vs real pro data have vastly different reliability, but this isn't surfaced to the coaching engine.

#### 3.4 Timezone Inconsistency
Most of the pipeline uses `datetime.now(timezone.utc)` (meta_drift.py, pro_baseline.py TemporalBaselineDecay), but `role_thresholds.py` uses `datetime.now()` (naive, local timezone). This creates inconsistent `last_updated` timestamps across the baseline subsystem.

---

### 4. Inter-Module Dependency Risks

| This Module | Depends On | Risk |
|-------------|-----------|------|
| `pro_baseline.py` | `storage/database.py`, `db_models.ProPlayerStatCard` | If HLTV scraper floods ProPlayerStatCard with unbounded data, `get_temporal_baseline()` OOMs (P3-26). |
| `meta_drift.py` | `storage/db_models.PlayerMatchStats`, `PlayerTickState` | Queries monolith tick data but detailed ticks live in per-match DBs — spatial drift accuracy is limited (P3-31). |
| `external_analytics.py` | CSV files in `data/external/` | Missing or renamed CSV columns crash init (P3-18). No graceful degradation for tournament data. |
| `tensor_factory.py` | `player_knowledge.py` | PlayerKnowledge's utility zone inaccuracy (P3-07) propagates into tensor spatial channels. |
| `data_pipeline.py` | `joblib` (scaler persistence) | Deserialization risk (P3-01) — a compromised scaler file is a code execution vector. |
| `role_thresholds.py` | `db_models.RoleThresholdRecord` | Partial persist (P3-33) could leave DB in inconsistent state, affecting role classification across restarts. |
| `nickname_resolver.py` | `db_models.ProPlayer` | Case-sensitive exact match (P3-35) forces O(n) fallback, impacting resolution latency with large pro rosters. |
| `vectorizer.py` (METADATA_DIM=25) | All downstream consumers | Any change to METADATA_DIM requires synchronized updates in `state_reconstructor.py`, `tensor_factory.py`, RAP Coach model input layer, and JEPA encoder. |

---

### 5. Remediation Priority Matrix

| Priority | ID | Severity | Effort | Description |
|----------|-----|----------|--------|-------------|
| ~~1~~ | P3-30 | ~~HIGH~~ **FIXED** | Low | ~~Add `.limit()` to meta_drift spatial queries~~ — Fixed in 2fa2cf3 |
| ~~2~~ | P3-26 | ~~HIGH~~ **FIXED** | Low | ~~Add `.limit()` to temporal baseline query~~ — Fixed in 2fa2cf3 |
| ~~3~~ | P3-27 | ~~HIGH~~ **FIXED** | Low | ~~Fix duplicate metric mapping in `_metric_to_baseline_key()`~~ — Fixed in 2fa2cf3 |
| ~~4~~ | P3-18 | ~~HIGH~~ **FIXED** | Low | ~~Guard tournament column access in external_analytics~~ — Fixed in 2fa2cf3 |
| 5 | P3-01 | MEDIUM | Medium | Add HMAC integrity check to joblib scaler files |
| 6 | P3-06 | MEDIUM | Medium | Dynamic FOV based on weapon/scope state |
| 7 | P3-35 | MEDIUM | Low | Case-insensitive SQL query for nickname exact match |
| 8 | P3-33 | MEDIUM | Low | Explicit transaction in `persist_to_db()` |
| 9 | P3-22 | MEDIUM | Low | Hysteresis for drift retrain threshold |
| 10 | P3-09 | MEDIUM | Low | Schema validation for loaded heuristic JSON |
| 11 | P3-15 | MEDIUM | Medium | Externalize HUD coordinates to versioned config |
| 12 | P3-16 | MEDIUM | Medium | Use actual flash duration from demo events |
| 13 | P3-32 | MEDIUM | Medium | Compute remaining 4 role thresholds or remove stubs |
| 14 | P3-13 | MEDIUM | Medium | Allow meta_drift to shift role centroids |
| 15 | P3-04 | MEDIUM | Low | Add spatial dimension assertion in model forward pass |
| 16 | P3-07 | MEDIUM | Medium | Track utility destruction events |
| 17 | P3-10 | MEDIUM | Low | Replace linear KAST approximation with logistic |
| 18 | P3-11 | MEDIUM | Low | Remove or privatize dead `compute_hltv2_rating_regression()` |
| 19 | P3-14 | MEDIUM | Low | Add max resolution cap for heatmaps |
| 20 | P3-17 | MEDIUM | Low | Document sigmoid CDF approximation error |
| 21 | P3-28 | MEDIUM | Low | Document survival rate approximation limitation |
| 22 | P3-31 | MEDIUM | High | Consider per-match DB queries for spatial drift |
| 23 | P3-34 | LOW | Low | Fix `datetime.now()` → `datetime.now(timezone.utc)` |
| 24 | P3-29 | LOW | Low | Move mid-file imports to top |
| 25-32 | LOW | — | Low | Remaining LOW findings (config hardcoding, documentation) |

---

### 6. Coverage Attestation

| # | File | Lines | Read | Findings |
|---|------|-------|------|----------|
| 1 | `backend/processing/data_pipeline.py` | 336 | YES | P3-01, P3-02 |
| 2 | `backend/processing/feature_engineering/vectorizer.py` | 461 | YES | P3-03 |
| 3 | `backend/processing/tensor_factory.py` | 746 | YES | P3-04, P3-05 |
| 4 | `backend/processing/tick_enrichment.py` | 362 | YES | P3-06 |
| 5 | `backend/processing/player_knowledge.py` | 611 | YES | P3-07, P3-08 |
| 6 | `backend/processing/state_reconstructor.py` | 133 | YES | None |
| 7 | `backend/processing/feature_engineering/base_features.py` | 189 | YES | P3-09 |
| 8 | `backend/processing/feature_engineering/kast.py` | 162 | YES | P3-10 |
| 9 | `backend/processing/feature_engineering/rating.py` | 182 | YES | P3-11, P3-12 |
| 10 | `backend/processing/feature_engineering/role_features.py` | 263 | YES | P3-13 |
| 11 | `backend/processing/heatmap_engine.py` | 295 | YES | P3-14 |
| 12 | `backend/processing/cv_framebuffer.py` | 193 | YES | P3-15 |
| 13 | `backend/processing/round_stats_builder.py` | 568 | YES | P3-16 |
| 14 | `backend/processing/skill_assessment.py` | 155 | YES | P3-17 |
| 15 | `backend/processing/external_analytics.py` | 192 | YES | P3-18, P3-19 |
| 16 | `backend/processing/connect_map_context.py` | 113 | YES | P3-20 |
| 17 | `backend/processing/validation/dem_validator.py` | 201 | YES | P3-21 |
| 18 | `backend/processing/validation/drift.py` | 176 | YES | P3-22, P3-23 |
| 19 | `backend/processing/validation/schema.py` | 95 | YES | P3-24, P3-25 |
| 20 | `backend/processing/validation/sanity.py` | 128 | YES | None |
| 21 | `backend/processing/validation/__init__.py` | 3 | YES | None |
| 22 | `backend/processing/baselines/pro_baseline.py` | 516 | YES | P3-26, P3-27, P3-28, P3-29 |
| 23 | `backend/processing/baselines/meta_drift.py` | 141 | YES | P3-30, P3-31 |
| 24 | `backend/processing/baselines/role_thresholds.py` | 320 | YES | P3-32, P3-33, P3-34 |
| 25 | `backend/processing/baselines/nickname_resolver.py` | 129 | YES | P3-35 |
| 26 | `backend/processing/baselines/__init__.py` | 1 | YES | None |
| 27 | `backend/processing/__init__.py` | 1 | YES | None |
| 28 | `backend/processing/feature_engineering/__init__.py` | 60 | YES | None |

**All 28 files read and analyzed. No files skipped.**
