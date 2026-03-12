# AUDIT_11: Tests
## Date: 2026-03-10
## Scope: 96 files (~19,345 lines)

---

### 1. Executive Summary

| Metric | Count |
|--------|-------|
| **Total files audited** | **96** |
| **Total lines of test code** | **~19,345** |
| **HIGH severity findings** | **18** |
| **MEDIUM severity findings** | **86** |
| **LOW severity findings** | **153** |
| **INFO (positive/advisory)** | **37** |
| **Exemplary test files** | 3 (`test_tensor_factory.py`, `test_z_penalty.py`, `test_round_stats_enrichment.py`) |

**File distribution:**
- `Programma_CS2_RENAN/tests/` — 68 main test files (~16,387 lines)
- `Programma_CS2_RENAN/tests/automated_suite/` — 5 test files (236 lines)
- `Programma_CS2_RENAN/backend/nn/*/test_arch.py` — 2 standalone test files (53 lines)
- `tests/` (top-level) — 19 files incl. forensics (2,669 lines)
- `Programma_CS2_RENAN/tests/conftest.py` — shared fixtures (345 lines)

**Critical cross-references:**
- Report 3 (Processing Pipeline): Feature vector index coupling in tests
- Report 6 (Storage/Database): Production DB access in 11+ test files
- Report 8 (Core Engine): Session engine state management tested with manual cleanup

---

### 2. File-by-File Findings

---

#### 2.1 Shared Test Infrastructure

##### `Programma_CS2_RENAN/tests/conftest.py` (345 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Test Isolation | 23-25 | Venv guard calls `pytest.exit()` on CI runners without venv, but the guard allows `CI`/`GITHUB_ACTIONS` env vars as bypass | Correctly implemented — no action needed |
| 2 | LOW | Coverage Gap | 305-344 | `mock_db_manager` fixture provides `InMemoryDBManager` with `get_session`, `get`, `create_db_and_tables`, `upsert` — but missing `close()`, `dispose()`, and `execute_raw()` that the real `DatabaseManager` may provide | Add stub methods for complete interface parity or use `spec=DatabaseManager` |

**Positive notes:** Well-structured fixture hierarchy (in_memory_db, seeded_db_session, real_db_session). The `seeded_db_session` fixture with 6 PlayerMatchStats + 12 RoundStats + 1 PlayerProfile is excellent for CI-portable testing. The `rap_model` and `rap_inputs` fixtures correctly seed with `torch.manual_seed(42)`.

##### `tests/conftest.py` (10 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Coverage Gap | all | Minimal conftest — only adds project root to `sys.path`. No shared fixtures for the `tests/` directory | Consider adding shared fixtures (temp DB, mock configs) for the top-level test files |

---

#### 2.2 Main Test Suite (`Programma_CS2_RENAN/tests/`)

##### `test_analysis_engines.py` (266 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 9 | `import sys` unused | Remove |
| 2 | LOW | Coverage gap | 26-28, 49-52 | Imports inside each test method — unusual but provides isolation against import failures | Acceptable for importability tests |
| 3 | LOW | Coverage gap | 255-266 | `EntropyAnalyzer` lacks test for NaN coordinates or very large position sets | Add boundary tests |

##### `test_analysis_engines_extended.py` (423 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 309 | `assert conf >= 0 or True` — the `or True` makes this assertion a no-op; it always passes | Remove `or True` |
| 2 | LOW | Dead import | 9 | `import sys` unused | Remove |
| 3 | LOW | Assertion quality | 331-338 | `test_entropy_single_point` only checks `isinstance(result, float)` — no value range assertion | Assert `result >= 0.0` |

##### `test_analysis_gaps.py` (500 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 9 | `import sys` unused | Remove |
| 2 | LOW | Mock correctness | 28-29 | `MagicMock()` for `threshold_store` without `spec=` — interface drift undetectable | Use `spec=` on MagicMock |
| 3 | LOW | Coverage gap | 337-436 | `DeceptionAnalyzer` tests lack integration test with all detection types simultaneously | Add combined detection test |

##### `test_analysis_orchestrator.py` (191 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 8 | `import sys` unused | Remove |
| 2 | LOW | Coverage gap | 14-150 | No tests for deception analysis, entropy analysis, or position data paths | Add sub-analyzer path tests |
| 3 | LOW | Assertion quality | 59 | `assert any("Tilt" in i.title ...)` — fragile string matching | Use enum/constant for insight types |

##### `test_auto_enqueue.py` (142 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky pattern | 130 | `time.sleep(0.01)` for timestamp ordering — may fail on fast machines | Use explicit `created_at` values |
| 2 | MEDIUM | Test isolation | 29-39 | Uses `init_database()` touching real `database.db` | Use in-memory DB or `mock_db_manager` fixture |
| 3 | LOW | Dead import | 7 | `import sys` unused | Remove |
| 4 | LOW | Coverage gap | 53-141 | No concurrent enqueueing or duplicate rejection test | Add uniqueness constraint test |

##### `test_baselines.py` (395 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 2 | LOW | Flaky pattern | 152-164 | `datetime.now(timezone.utc)` weight calculations — CI speed variance | Use `freezegun` for deterministic datetime |
| 3 | LOW | Coverage gap | 293-395 | `RoleThresholdStore` thread safety not tested | Add concurrent access test |

##### `test_chronovisor_highlights.py` (380 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 360-369 | Reads raw source code with string matching to verify `scale_marker_sizes` | Import and test the dict values directly |
| 2 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 3 | LOW | Coverage gap | 265-358 | Render tests only check file existence/size, not content | Use snapshot testing |

##### `test_chronovisor_scanner.py` (243 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 231-234 | `test_spike_detected` only asserts `isinstance(moments, list)` — tests nothing useful | Assert specific spike detection behavior |
| 2 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 3 | LOW | Coverage gap | 196-243 | Bypasses `__init__` with `__new__` | Document or test with initialized scanner |

##### `test_coaching_dialogue.py` (143 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Mock correctness | 21-23 | `CoachingService.__new__()` bypasses `__init__` | Test with properly initialized service |
| 2 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 3 | LOW | Coverage gap | 131-143 | `_infer_round_phase` missing "eco" and "force_buy" tests | Add all phase tests |
| 4 | LOW | Redundancy | 107-143 | Duplicates `TestHealthRangeClassification` from `test_coaching_service_contracts.py` | Consolidate |

##### `test_coaching_engines.py` (497 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 45-46 | Disjunctive assertion `"kills" in result or "below" in result` — one path can silently break | Use separate assertions |
| 2 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 3 | LOW | Mock correctness | 128-137 | MagicMock without `spec=` for card parameter | Add `spec=` |
| 4 | LOW | Coverage gap | 443-497 | `TestLongitudinalEngine` uses MagicMock for trends, no real TrendData test | Add real TrendData test |

##### `test_coaching_service_contracts.py` (290 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 129-142 | Catches `AttributeError` but swallows all other exceptions silently | Add `except Exception` with `pytest.fail()` |
| 2 | MEDIUM | Test quality | 167 | `assert not ({})` tests Python semantics, not app code | Remove or relocate |
| 3 | LOW | Coverage gap | 22-65 | Mode selection tests only check boolean flags | Test actual execution paths |
| 4 | LOW | Redundancy | 67-96 | `TestHealthRangeClassification` duplicated in `test_coaching_dialogue.py` | Consolidate |

##### `test_coaching_service_fallback.py` (302 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky pattern | 218-235 | Patches `sys.modules` to make imports fail — fragile, affects other tests | Use `patch.object` on COPER method instead |
| 2 | LOW | Coverage gap | 65-196 | Mode selection overlaps with `test_coaching_service_contracts.py` | Consolidate |
| 3 | LOW | Assertion quality | 275-284 | Tests docstring content for keywords — not a stable API contract | Enforce via code, not docstring assertions |

##### `test_coaching_service_flows.py` (518 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 2 | LOW | Typo | 149 | Class name `TestTraditionalCoachin` missing final "g" | Rename to `TestTraditionalCoaching` |
| 3 | LOW | Coverage gap | 428-475 | Longitudinal coaching only checks structure, not trend accuracy | Add slope direction assertions |
| 4 | LOW | Test isolation | 58-75 | Fixture `with patch(...)` scope mismatch | Ensure service doesn't call patched functions post-teardown |

##### `test_coach_manager_flows.py` (803 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Mock correctness | 73-79 | `_make_manager()` uses `__new__` bypass then manual attribute assignment | Mock constructor dependencies instead |
| 2 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 3 | LOW | Assertion quality | 571-591 | Documents known dead-code path (`AttributeError` from `steam_connected`) | Create tracking issue or fix |
| 4 | LOW | Coverage gap | 680-688 | `TestGetInteractiveOverlayData` only tests calibrating case | Add mature state test |

##### `test_coach_manager_tensors.py` (234 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 119-122 | Asserts known bug exists (None values not replaced); blocks the fix | Invert assertion once bug #4 is fixed |
| 2 | MEDIUM | Assertion quality | 130-149 | `try/except (TypeError, ValueError): pass` silently accepts exceptions | Remove silent pass after bug fix |
| 3 | LOW | Coverage gap | 211-234 | Hardcodes expected defaults dict rather than importing from source | Import defaults from source module |

##### `test_config_extended.py` (176 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Test isolation | 126-144 | Mutates global `cfg.SETTINGS_PATH` and `cfg._settings` | Use monkeypatch fixture |
| 2 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 3 | LOW | Flaky pattern | 167-169 | `test_dirs_exist` environment-dependent | Mark as integration or create dirs in fixture |

##### `test_database_layer.py` (406 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 2 | LOW | Test isolation | 148-177 | `__new__` bypass for StateManager | Document or use DI |
| 3 | LOW | Coverage gap | 291-406 | `TestStatCardAggregator` missing edge cases for `detailed_stats_json` | Add Unicode/large JSON tests |
| 4 | LOW | Coverage gap | 24-142 | `TestDatabaseManager` missing WAL mode enforcement test | Add `PRAGMA journal_mode` assertion |

##### `test_data_pipeline_contracts.py` (192 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Coverage gap | 105-144 | Hardcoded vector indices `vec[18]` without named constant | Use feature index lookup |
| 2 | LOW | Coverage gap | 147-192 | Hardcoded index `vec[17]` for map encoding | Use feature index constant |
| 3 | LOW | Assertion quality | 122-124 | `pytest.approx(0.33)` — expected value should be documented as 1/3 | Clarify expected encoding |

##### `test_db_backup.py` (202 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 150-172 | `TestAlembicPreMigrationHook` reads raw source code with string matching | Import and verify callable instead |
| 2 | LOW | Dead import | 12 | `import sys` unused | Remove |
| 3 | LOW | Skip pattern | 19-23 | `TestBackupMonolith` permanently skipped — backup never tested in CI | Track unblocking as work item |
| 4 | LOW | Coverage gap | 56-104 | `TestRestoreBackup` missing overwrite scenario test | Add overwrite test |

##### `test_db_governor_integration.py` (201 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Mock correctness | 23-30 | `__new__()` bypass; MagicMock without `spec=` | Add `spec=DatabaseManager` |
| 2 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 3 | LOW | Test naming | 96-201 | E2E pipeline tests in a file named `test_db_governor_integration` | Move to dedicated file |
| 4 | LOW | Coverage gap | 31-91 | Missing error handling test for `list_available_matches` | Add exception test |

##### `test_debug_ingestion.py` (84 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 8 | `import sys` unused | Remove |
| 2 | LOW | Coverage gap | 15-84 | Missing tests for malformed DataFrame inputs (missing columns, NaN, wrong dtypes) | Add edge cases |
| 3 | LOW | Assertion quality | 43-46 | Test doesn't verify all output keys | Assert all expected keys |

##### `test_demo_format_adapter.py` (255 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Test isolation | 30-36, 60-69 | `tempfile.mkstemp` with manual `os.unlink` — temp files leak on crash | Use `tmp_path` fixture |
| 2 | MEDIUM | Source reading | 209-222 | Tests read source files to verify imports | Test actual behavior instead |
| 3 | LOW | Dead import | 9 | `import sys` unused | Remove |
| 4 | LOW | Coverage gap | 140-167 | `TestFieldMapping` doesn't verify mapped fields match real parser output | Add integration test |

##### `test_demo_parser.py` (187 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 9 | `import sys` unused | Remove |
| 2 | LOW | Coverage gap | 28-57 | Missing tests for corrupted/truncated demo files | Add corruption tests |
| 3 | LOW | Assertion quality | 66-135 | Rating formulas tested inline rather than calling actual functions | Call actual production functions |
| 4 | LOW | Flaky pattern | 154-187 | Integration tests depend on `data/demos/` having `.dem` files | Document how to obtain test files |

##### `test_dem_validator.py` (135 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 8 | `import sys` and `tempfile` unused | Remove |
| 2 | LOW | Assertion quality | 87-88 | Mutates class attribute on instance for size limit test | Use separate instance or monkeypatch |
| 3 | LOW | Coverage gap | 21-131 | Missing boundary test at exact `MIN_FILE_SIZE` | Add boundary test |

##### `test_deployment_readiness.py` (391 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky pattern | 169-202 | Wall-clock latency tests — inherently flaky on shared CI | Increase `CI_LATENCY_MULTIPLIER` or use statistical bounds |
| 2 | LOW | Performance | 144-166 | 500 forward passes in unit tests (100 per model type x 5) | Mark as `@pytest.mark.slow` |
| 3 | LOW | Coverage gap | 260-299 | `TestOODGracefulHandling` missing RAP model | Add RAP to OOD tests |
| 4 | LOW | Assertion quality | 293-299 | `test_nan_input_graceful` doesn't verify exception message is informative | Assert meaningful error message |

##### `test_detonation_overlays.py` (118 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Source reading | 67-118 | Three tests read raw source code to verify string presence | Use `hasattr()` or `inspect` |
| 2 | LOW | Dead import | 10 | `import sys` unused | Remove |
| 3 | LOW | Test isolation | 23-28 | Catches all exceptions for skip — masks non-Kivy failures | Catch only `ImportError`/`RuntimeError` |
| 4 | LOW | Coverage gap | 33-61 | Tests verify constants but not actual overlay rendering | Add visual regression or mock canvas tests |

##### `test_dimension_chain_integration.py` (128 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Redundancy | 93-105 | Duplicates tests from `test_coach_manager_tensors.py` | Keep in one canonical location |
| 2 | LOW | Assertion quality | 62-71 | Catches `TypeError` and falls back to `assert hasattr(model, "forward")` — no-op | Test with correct JEPA signature |
| 3 | LOW | Coverage gap | 15-128 | Missing VL-JEPA and RAP dimension chain tests | Add all model types |

##### `test_drift_and_heuristics.py` (255 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 12 | `import sys` unused | Remove |
| 2 | LOW | Flaky pattern | 64-80 | n=20 samples may exceed z-threshold by chance despite seed | Increase sample size |
| 3 | LOW | Coverage gap | 239-255 | `TestDifferentialHeatmap` only tests importability | Add actual heatmap generation test |
| 4 | LOW | Coverage gap | 187-238 | Missing `save_learned_heuristics` roundtrip test | Add save/load test |

##### `test_experience_bank_db.py` (695 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Test isolation | 60-64 | `ExperienceBank.__new__()` bypasses `__init__` | Use proper constructor with DI |
| 2 | LOW | Coverage gap | 593-695 | `extract_experiences_from_demo` only checks `count`, not record content | Assert on CoachingExperience fields |
| 3 | LOW | Coverage gap | N/A | No concurrent access test despite tri-daemon architecture | Add threading test |
| 4 | LOW | Dead import | 7-8 | `import sys` unused | Remove |

##### `test_experience_bank_logic.py` (137 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Coverage gap | 107-137 | `TestSynthesizedAdvice` missing boundary tests (confidence=0.0, 1.0, empty narrative) | Add boundary tests |
| 2 | LOW | Assertion quality | 125-136 | Tautological test — asserts the value it just set | Test enforcement by the dataclass |

##### `test_feature_extractor_contracts.py` (263 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Coverage gap | 176-207 | Hard-coded index positions 20-24 for context features | Use `get_feature_names()` for indices |
| 2 | LOW | Coverage gap | N/A | No `extract_batch` test with context parameter | Add batch+context test |
| 3 | LOW | Assertion quality | 91-94 | Hard-coded indices `[2, 3, 5, 6, 7]` for binary features | Derive from `get_feature_names()` |

##### `test_feature_kast_roles.py` (481 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Mock correctness | 306-314 | `__new__()` bypass for `CoachingDialogueEngine` — 5 manually set attributes | Use factory pattern |
| 2 | LOW | Flaky patterns | 316-334 | Intent classification depends on keyword heuristics | Test keyword lists themselves |
| 3 | LOW | Coverage gap | N/A | No ambiguous-intent test (keywords from multiple categories) | Add ambiguity test |
| 4 | LOW | Coverage gap | N/A | `chat()` method never tested | Add smoke test with mocked LLM |
| 5 | LOW | Dead import | 10 | `import sys` unused | Remove |

##### `test_features.py` (80 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Coverage gap | 21-79 | Only 3 tests for `extract_match_stats`. Missing: single-row, NaN, negative values | Add edge cases |
| 2 | LOW | Assertion quality | 47 | `approx(0.66, abs=0.01)` when actual value is 2/3 ≈ 0.6667 | Use `approx(2/3)` |
| 3 | LOW | Coverage gap | N/A | Rating formula `assert rating > 0 and rating < 5.0` is extremely weak | Verify against known formula inputs |
| 4 | LOW | Dead import | 9 | `import sys` unused | Remove |

##### `test_game_theory.py` (986 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky patterns | 194-202 | `test_extract_death_events_empty_db` hits real database | Mock DB or use in-memory fixture |
| 2 | LOW | Coverage gap | 228-298 | `TestDeceptionAnalyzer` lacks mixed flash+blind event test | Add mixed event test |
| 3 | LOW | Coverage gap | 576-688 | `TestBlindSpotDetector` allows empty `spots` — assertion may never execute | Assert `len(spots) > 0` |
| 4 | LOW | Assertion quality | 621-627 | Loop assertion guard missing | Add guard before loop |

##### `test_game_tree.py` (552 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Coverage gap | 157-209 | No persistence verification across multiple `get_opponent_probs` calls | Add stability test |
| 2 | LOW | Assertion quality | 456-457 | Fragile string assertions on strategy output format | Use regex or structured output |
| 3 | LOW | Dead import | 11-12 | `import sys` unused | Remove |

##### `test_hybrid_engine.py` (239 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Test isolation | 163-200 | `test_save_insights_to_db` writes to **production database** via `get_db_manager()`. Cleanup in `finally` can fail, leaving test data in prod | Use in-memory SQLite fixture |
| 2 | MEDIUM | Test isolation | 27-33 | `test_engine_initialization` may connect to production DB internally | Mock database dependencies |
| 3 | LOW | Coverage gap | N/A | No test for `generate_insights` with empty input | Add empty stats test |
| 4 | LOW | Dead import | 7 | `import sys` unused | Remove |

##### `test_integration.py` (68 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky patterns | 13-28 | `test_analytics_engine` no skip guard for missing player data | Add skip guard |
| 2 | MEDIUM | Flaky patterns | 59-66 | `test_datasets_availability` passes with empty list — no `len > 0` assertion | Assert minimum count or mark conditional |
| 3 | LOW | Coverage gap | 30-51 | Win probability smoke test only checks `0.0 <= prob <= 1.0` on untrained model | Acceptable as smoke test; document |
| 4 | LOW | Dead import | 1 | `import sys` unused | Remove |

##### `test_jepa_model.py` (539 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Test isolation | 171-191 | `NamedTemporaryFile(delete=False)` never cleaned up | Use `tmp_path` fixture |
| 2 | LOW | Coverage gap | N/A | No base model `forward_selective` test (only VL-JEPA) | Add base model test |
| 3 | LOW | Assertion quality | 191 | `== True` instead of `is True` for boolean | Use `is True` |
| 4 | LOW | Dead import | 7 | `import sys` unused | Remove |

##### `test_knowledge_graph.py` (248 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Mock correctness | 26-30 | `__new__()` bypass for `KnowledgeGraph`, manually sets `DB_PATH` | Use real constructor with `tmp_path` |
| 2 | LOW | Coverage gap | N/A | No delete/remove tests (only C and R of CRUD) | Add delete tests |
| 3 | LOW | Coverage gap | N/A | No Unicode entity name test | Add Unicode test |
| 4 | LOW | Test isolation | 36-62 | Opens `sqlite3.connect` directly to verify schema | Use public inspection methods |
| 5 | LOW | Dead import | 14 | `import sys` unused | Remove |

##### `test_lifecycle.py` (81 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky patterns | 42-44 | `test_ensure_single_instance_returns_bool` acquires real OS mutex | Mock mutex acquisition |
| 2 | LOW | Coverage gap | N/A | No `launch_daemon` test with valid script | Add mock daemon test |
| 3 | LOW | Coverage gap | N/A | No `shutdown` test with running process | Add running process test |

##### `test_map_manager.py` (104 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky patterns | 18-24 | `test_map_path_resolution` depends on asset files on disk | Add `skipif` for missing assets |
| 2 | LOW | Coverage gap | N/A | No test for unknown map metadata | Add unknown map test |
| 3 | LOW | Assertion quality | 43-47 | `asset.exists == False` instead of `is False` | Use `is False` or `not` |

##### `test_model_factory_contracts.py` (238 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Coverage gap | 93-146 | "CURRENTLY FAILS" comments may be stale (bugs may be fixed) | Remove stale comments or add `xfail` |
| 2 | LOW | Coverage gap | 148-177 | Dimension propagation only for `default` and `jepa` | Add all model types |
| 3 | LOW | Assertion quality | 176 | Only asserts `isinstance(model, nn.Module)` without verifying dimensions | Verify internal dimensions |

##### `test_models.py` (76 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Coverage gap | 21-75 | Only tests default values. No validation, constraints, or relationship tests | Add field validation and FK tests |
| 2 | LOW | Coverage gap | N/A | `CoachingExperience` and `TacticalKnowledge` models not tested | Add creation tests |
| 3 | LOW | Assertion quality | 26 | `isinstance(stats.processed_at, datetime)` — no recency check | Assert within reasonable time window |

##### `test_nn_extensions.py` (373 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Coverage gap | 255-309 | MoE gating mechanism not tested for expert diversity | Add input-dependent expert selection test |
| 2 | LOW | Coverage gap | 322-343 | `TestModelManager` only tests `save_version`, not `load` or `list` | Add load/list tests |
| 3 | LOW | Dead import | 11 | `import sys` unused | Remove |

##### `test_nn_infrastructure.py` (373 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Redundancy | 143-208 | `TestModelFactory` overlaps with `test_model_factory_contracts.py` | Consolidate factory tests |
| 2 | LOW | Flaky patterns | 165-168 | `test_get_model_rap` missing `pytest.importorskip("ncps")` | Add importorskip guard |
| 3 | LOW | Dead import | 11 | `import sys` unused | Remove |
| 4 | LOW | Assertion quality | 138 | `atol=0.15` generous for 500 EMA updates at decay=0.99 | Tighten to `atol=0.05` |

##### `test_nn_training.py` (186 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Mock correctness | 119-122 | `_make_controller_shell` uses `__new__` bypass for `TrainingController` | Verify tested methods don't depend on `__init__` state |
| 2 | LOW | Coverage gap | N/A | No `should_train()` test (main decision method) | Add with mocked DB state |
| 3 | LOW | Coverage gap | N/A | No NaN loss test for `EarlyStopping` | Add NaN handling test |
| 4 | LOW | Dead import | 11 | `import sys` unused | Remove |

##### `test_onboarding.py` (91 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Test isolation | 47-66 | Queries real DB with hard-coded `"test_user"` | Use isolated in-memory DB |
| 2 | MEDIUM | Test isolation | 69-86 | No cleanup of cached state after test | Add teardown |
| 3 | LOW | Coverage gap | 20-41 | Missing negative demo count test (-1) | Add negative input test |
| 4 | LOW | Dead import | 8 | `import sys` unused | Remove |

##### `test_onboarding_training.py` (160 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Test isolation | 124-138 | Queries real DB; always skipped in CI | Seed test data fixture |
| 2 | MEDIUM | Test isolation | 141-155 | `init_database()` touches production DB | Use in-memory DB |
| 3 | LOW | Dead import | 7 | `import sys` unused | Remove |
| 4 | LOW | Coverage gap | 94-118 | Missing NaN/inf input test for cosine similarity | Add edge case |

##### `test_persistence_stale_checkpoint.py` (235 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Assertion quality | 200-217 | `test_corrupted_file` only checks `result is not None` | Verify weights match random init |
| 2 | LOW | Assertion quality | 219-234 | `test_empty_file` same issue | Verify weights unchanged |

##### `test_phase0_3_regressions.py` (576 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky pattern | 70-105 | 100 threads via ThreadPoolExecutor — timing-dependent on CI | Reduce to 20 threads |
| 2 | MEDIUM | Test isolation | 107-121 | Modifies module-level `_state_manager` singleton | Use monkeypatch |
| 3 | MEDIUM | Assertion quality | 550-576 | Weak negative assertion (`status != "INVALID"`) | Assert expected valid status |
| 4 | LOW | Tautological | 359-387 | Tests re-implement negative sampling logic inline instead of calling production code | Test actual production function |
| 5 | LOW | Mock correctness | 446-468 | MagicMock without `spec=` for card | Add `spec=ProPlayerStatCard` |

##### `test_playback_engine.py` (168 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Coverage gap | 80-168 | Only 5 tests. Missing: pause, resume, boundary seeking, interpolation | Add state transition and boundary tests |
| 2 | LOW | Assertion quality | 116-121 | `get_total_ticks() == 49` unexplained | Document the off-by-one |
| 3 | LOW | Dead import | 6 | `import sys` unused | Remove |

##### `test_pro_demo_miner.py` (194 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Test isolation | 172-189 | `mine_all_pro_stats` processes ALL pro players, not just test player | Scope miner to test player only |
| 2 | LOW | Coverage gap | 112-142 | Only 2 archetypes tested | Add parametrized tests for all archetypes |

##### `test_profile_service.py` (140 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Mock correctness | 24-29 | `__new__()` bypass for `ProfileService` | Use proper constructor |
| 2 | LOW | Coverage gap | 21-43 | Only guard conditions tested, no happy path | Add successful fetch tests |
| 3 | LOW | Dead import | 7 | `import sys` unused | Remove |

##### `test_rag_knowledge.py` (293 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Test isolation | 63-89, 127-170 | Uses `init_database()` touching production DB | Use dedicated test DB |
| 2 | MEDIUM | Flaky pattern | 172-178 | `test_retrieve_knowledge` expects results from non-deterministic embeddings | Assert specific expected results |
| 3 | LOW | Coverage gap | 199-214 | Usage count increment not verified as exactly +1 | Assert `== initial + 1` |

##### `test_rap_coach.py` (568 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky pattern | 488-508 | `test_loss_decreases_over_steps` fragile if architecture changes | Assert minimum percentage decrease |
| 2 | LOW | Coverage gap | 411-458 | `generate_advice` tests only check `is not None` and `isinstance(str)` | Assert expected keywords |
| 3 | LOW | Assertion quality | 300-349 | 7 tests each call `rap_model(...)` redundantly | Combine or cache output |

##### `test_round_stats_enrichment.py` (238 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Coverage gap | 212-238 | `TestEnrichFromDemoImport` only tests importability | Add functional tests |
| 2 | LOW | Dead import | 7 | `import sys` unused | Remove |

**Positive:** Excellent test coverage with `pytest.approx`. Edge cases well covered. Exemplary test file.

##### `test_round_utils.py` (308 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Assertion quality | 220-225 | `__new__()` bypass for ExperienceBank | Document assumption |
| 2 | LOW | Dead import | 7 | `import sys` unused | Remove |

**Positive:** Thorough boundary testing of `infer_round_phase` with exact threshold values.

##### `test_security.py` (158 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 96-113 | `test_no_eval_in_production` regex may produce false positives for `model.eval()` | Use AST parsing for accuracy |
| 2 | LOW | Coverage gap | 35-46 | API key regex misses `token`, `secret`, `credential` | Expand regex patterns |

##### `test_services.py` (104 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Coverage gap | 14-104 | Almost entirely smoke tests — no functional logic exercised | Add functional tests with controlled inputs |
| 2 | MEDIUM | Test isolation | 62-92 | `test_plot_with_real_data` depends on `seeded_db_session` | Add skip guard |
| 3 | LOW | Dead import | 8 | `import sys` unused | Remove |

##### `test_session_engine.py` (472 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Test isolation | 386-402 | Modifies module-level `_work_available_event` | Use monkeypatch |
| 2 | MEDIUM | Test isolation | 410-448 | Modifies `sys.stdin` and `_shutdown_event` | Wrap cleanup in fixture with yield |
| 3 | LOW | Coverage gap | 182-257 | Patch path may not match actual import path | Verify patch path |
| 4 | LOW | Dead import | 8 | `import sys` unused | Remove |

##### `test_skill_model.py` (192 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 29-107 | Conditional assertions (`if SkillAxes.X in vec`) — test trivially passes when axis absent | Make assertions unconditional |
| 2 | LOW | Dead import | 7 | `import sys` unused | Remove |

##### `test_spatial_and_baseline.py` (128 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Coverage gap | 19-37 | Only 2 verticality cases. Missing exact boundary (Z diff == 200) | Add boundary test |
| 2 | LOW | Dead import | 7 | `import sys` unused | Remove |

**Positive:** Good coverage of fuzzy matching, outlier trimming, tier classification.

##### `test_spatial_engine.py` (67 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Coverage gap | 1-67 | Only 5 tests for SpatialEngine. Missing Inferno, Nuke, Vertigo, clamping | Add all supported maps and boundary tests |
| 2 | LOW | Dead import | 6 | `MAP_DATA` imported but unused | Remove |
| 3 | LOW | Assertion quality | 54-56 | Fallback `(0.5, 0.5)` unexplained | Add comment explaining fallback |

##### `test_state_reconstructor.py` (109 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Tautological | 92-109 | `__new__()` bypass then asserts manually-set attributes — tests own setup, not production code | Test actual constructor or computed defaults |
| 2 | LOW | Coverage gap | 16-90 | Missing core reconstruction pipeline tests | Add `reconstruct_state` tests |
| 3 | LOW | Dead import | 7 | `import sys` unused | Remove |

##### `test_tactical_features.py` (80 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Coverage gap | 13-78 | Missing zero/negative edge cases | Add edge case tests |
| 2 | LOW | Assertion quality | 27 | Tolerance 0.05 wide for deterministic inputs | Tighten or document |
| 3 | LOW | Dead import | 1 | `import sys` unused | Remove |

##### `test_temporal_baseline.py` (248 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky pattern | 161-169 | `datetime.now(UTC)` causes float rounding differences | Use fixed `reference_date` or `freezegun` |
| 2 | LOW | Coverage gap | 216-227 | Only tests fallback path, not primary path with real data | Add seeded data test |

**Positive:** Excellent boundary testing with mathematical verification (half-life, clamping, monotonicity).

##### `test_tensor_factory.py` (861 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Test isolation | 726-742 | Singleton reset without restore | Save/restore original in teardown |
| 2 | LOW | Flaky pattern | 744-766 | Thread test with timeout — threads could hang | Check `thread.is_alive()` post-join |

**Positive:** One of the best test files — 56 tests with comprehensive coverage of legacy mode, POV mode, motion tensors, edge cases, resolution independence. Exemplary.

##### `test_trade_kill_detector.py` (333 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Assertion quality | 180-191 | `result.trade_kills >= 1` — weak when exact count is known | Assert `== 1` |
| 2 | LOW | Dead import | 7 | `import sys` unused | Remove |

**Positive:** Excellent trade detection tests — empty input, missing columns, window boundaries, cross-round isolation, team kills.

##### `test_training_orchestrator_flows.py` (579 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Mock correctness | 21-33 | MagicMock manager without `spec=` | Add `spec=CoachTrainingManager` |
| 2 | MEDIUM | Coverage gap | 500-535 | `test_aborts_when_no_training_data` only checks "no crash" | Assert return value or log warning |
| 3 | LOW | Dead import | 7 | `import sys` unused | Remove |

##### `test_training_orchestrator_logic.py` (177 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Tautological | 76-123 | `TestEarlyStopping` manually implements early stopping logic (if/else) in the test itself instead of calling a method on the orchestrator — tests the test, not production code | Extract early stopping into testable method; test that method |
| 2 | LOW | Coverage gap | 152-175 | Missing seed divergence test | Add different-seed test |

##### `test_z_penalty.py` (156 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Dead import | 12 | `import sys` unused | Remove |

**Positive:** Excellent boundary testing — exact boundary, saturation, monotonicity, custom transition bands. Exemplary test file.

---

#### 2.3 Automated Suite (`Programma_CS2_RENAN/tests/automated_suite/`)

##### `test_e2e.py` (62 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Test isolation | 31, 41 | `init_database()` and `get_db_manager()` operate on production DB; modifies `CS2_PLAYER_NAME` in production config | Use temp DB and temp config via fixtures |
| 2 | **HIGH** | Flaky pattern | 43-48 | Always skips in CI (requires real data) | Seed test data fixture |
| 3 | MEDIUM | Test isolation | 60-61 | Restore logic doesn't handle `original_name is None` — test value persists | Delete key when original was None |
| 4 | MEDIUM | Assertion quality | 52-53 | Only `pytest.fail()` if `run_training_cycle()` raises — no output validation | Assert on model checkpoint/metrics |

##### `test_functional.py` (32 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Test isolation | 24-31 | Reads/writes production config file; `None` original value leaves test data permanently | Use temp config or mock config module |
| 2 | MEDIUM | Coverage gap | all | Only one functional test (`test_config_persistence`) | Add core workflow tests |
| 3 | LOW | Assertion quality | 27 | Only tests one key, no side-effect check | Assert other keys unchanged |

##### `test_smoke.py` (42 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Flaky pattern | 23-24 | `import kivy` may trigger OpenGL context in headless CI | Mock Kivy or set `KIVY_NO_WINDOW` |
| 2 | MEDIUM | Assertion quality | 20-31 | Error message says "core module" even when failure is in `kivy`/`pandas`/`torch` | Provide per-import error messages |
| 3 | LOW | Test isolation | 36-41 | `init_database()` in smoke test has side effects on production DB | Mock or use in-memory |
| 4 | LOW | Coverage gap | all | Only 2 smoke tests — missing CLI, config, logger | Add more entry point smoke tests |

##### `test_system_regression.py` (56 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Test isolation | 4, 10-11 | `get_db_manager()` at module-level connects to production DB on import | Move to test function or fixture |
| 2 | MEDIUM | Mock correctness | 12-30 | `test_database_schema_regression` never persists to DB — only tests Python model constructor | Persist and roundtrip through temp DB |
| 3 | MEDIUM | Flaky pattern | 44-47 | Always skips in CI (no real data) | Seed temp DB |
| 4 | LOW | Dead import | 2 | `Session` and `create_engine` imported but unused | Remove |
| 5 | LOW | Assertion quality | 53-55 | No value range assertions (e.g., `avg_adr >= 0`) | Add range checks |

##### `test_unit.py` (49 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 30-33 | Exact floating-point equality (`stats["accuracy"] == 30 / 90`) | Use `pytest.approx()` |
| 2 | MEDIUM | Coverage gap | 10-28 | 13 input columns but only 4 output fields asserted | Assert all output fields |
| 3 | LOW | Mock correctness | 10-27 | If `extract_match_stats()` adds required columns, test breaks silently | Use schema validation |
| 4 | LOW | Assertion quality | 40-48 | Hardcoded expected translations — fragile but correct for regression | Document as intentional regression test |

---

#### 2.4 Standalone Test Files in Production Source Tree

##### `backend/nn/experimental/rap_coach/test_arch.py` (48 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Test location | all | Test file inside production source tree — gets packaged with production code | Move to `tests/nn/test_experimental_rap_arch.py` |
| 2 | MEDIUM | Assertion quality | 33-39 | `belief_state` shape hardcodes hidden dim 64, but HIDDEN_DIM=128 in config | Use `HIDDEN_DIM` constant from `nn/config.py` |
| 3 | MEDIUM | Flaky pattern | 20-25 | `torch.randn()` without seed — non-deterministic | Add `torch.manual_seed(42)` |
| 4 | LOW | Coverage gap | all | Only one forward pass config. Missing: batch_size=1, seq_len=1 | Add edge cases |
| 5 | LOW | Dead code | 46-47 | `__main__` block bypasses pytest infrastructure | Remove or add CLI handling |

##### `backend/nn/rap_coach/test_arch.py` (7 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Dead/Redundant | all | Deprecated shim re-exporting from experimental module. Adds indirection, pollutes production tree | Delete this file; update references to canonical location |
| 2 | LOW | Test location | all | In production source tree | Move to `tests/` or delete |

---

#### 2.5 Top-Level Test & Verification Scripts (`tests/`)

##### `tests/forensics/forensic_parser_test.py` (49 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Not a test | all | Diagnostic script for demo parser forensics. No pytest test functions | Move to `tools/diagnostics/` |
| 2 | MEDIUM | Flaky pattern | 16-22 | Depends on `.dem` files in `data/pro_demos/` | Use `pytest.skip` or move out of test tree |

##### `tests/forensics/test_skill_logic.py` (75 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | LOW | Coverage gap | 15-75 | Only basic happy path for skill axes computation | Add boundary tests |

##### `tests/forensics/check_db_status.py` (55 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Test isolation | 26-55 | **Not a test.** Queries production DB at module-load time. If pytest collects, side effects occur | Wrap in `if __name__ == "__main__":` or move to `tools/` |
| 2 | **HIGH** | Flaky pattern | 26-27 | `get_db_manager()` at module level — no isolation | Exclude from pytest collection or rename |
| 3 | MEDIUM | Assertion quality | all | No assertions — only prints counts | Add assertions or move to tools |
| 4 | LOW | Coverage gap | 29 | `is_pro == False` should use `is_(False)` for SQLAlchemy | Use `.is_(False)` |

##### `tests/forensics/check_failed_tasks.py` (39 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Not a test | all | Diagnostic script, no assertions, no test functions | Move to `tools/` |
| 2 | MEDIUM | Test isolation | 26-27 | Queries production database | Use test fixture |

##### `tests/forensics/debug_env.py` (31 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Dead/Redundant | all | Developer debug script — no assertions, no test functions | Move to `tools/debug_env.py` or delete |
| 2 | LOW | Test isolation | 14-28 | Kivy import may trigger event loop side effects | Exclude from pytest collection |

##### `tests/forensics/debug_nade_cols.py` (41 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Dead/Redundant | all | Debug script for grenade columns — no assertions | Move to `tools/` or delete |
| 2 | MEDIUM | Flaky pattern | 17-23 | Depends on `.dem` files; uses `SystemExit(0)` which crashes pytest | Use `pytest.skip` or exclude |

##### `tests/forensics/debug_parser_fields.py` (67 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Dead/Redundant | all | Debug script for `demoparser2` fields — no assertions | Move to `tools/` or delete |
| 2 | MEDIUM | Flaky pattern | 24-29 | Depends on real `.dem` files on disk | Use `pytest.skip` or exclude |

##### `tests/forensics/probe_missing_tables.py` (35 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Not a test | all | Diagnostic script — introspects production DB schema | Move to `tools/` or convert to proper test |
| 2 | MEDIUM | Test isolation | 24 | `inspect(get_db_manager().engine)` hits production DB | Use test DB |

##### `tests/forensics/verify_map_dimensions.py` (43 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Not a test | all | Diagnostic script — no test functions, no assertions | Convert to test or move to `tools/` |
| 2 | MEDIUM | Flaky pattern | 30-38 | Depends on image files at `PHOTO_GUI/maps/` | Add skip guard |
| 3 | LOW | Assertion quality | 35 | Hardcoded 1024x1024 magic number | Extract to named constant |

##### `tests/forensics/verify_spatial_integrity.py` (49 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 37-38 | Extremely tight tolerances (0.88-0.89, 0.40-0.41) | Use `pytest.approx` with documented tolerance |
| 2 | MEDIUM | Test isolation | 44-48 | Catches all exceptions and prints "FAILURE" — hides traceback | Let exceptions propagate |
| 3 | LOW | Coverage gap | 20 | Only tests `de_mirage` | Add parametrized tests for all maps |
| 4 | LOW | Not a test | all | Script with `__main__` guard, not pytest | Convert to proper pytest test |

##### `tests/setup_golden_data.py` (172 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Not a test | all | Data setup utility — creates golden SQLite DB from demo file. Constants/imports execute at module level on pytest collection | Move to `tools/setup_golden_data.py` |
| 2 | MEDIUM | Test isolation | 128-129 | Unconditionally deletes `DB_PATH` without backup | Add `--force` flag or backup |
| 3 | MEDIUM | Flaky pattern | 79-80 | Depends on `golden.dem` at fixed path | Add `FileNotFoundError` with instructions |
| 4 | LOW | Assertion quality | all | No assertions — no verification of created DB | Add post-setup verification |

##### `tests/verify_chronovisor_logic.py` (130 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Test framework | 40-129 | Uses `unittest.TestCase` instead of pytest — mixed framework | Migrate to pytest |
| 2 | MEDIUM | Assertion quality | 72 | `delta=0.01` tight tolerance — fragile | Document as exact-algorithm test or widen |
| 3 | LOW | Test isolation | 46-47 | Reaches into private `self.scanner.model = None` | Create test mode or constructor parameter |
| 4 | LOW | Coverage gap | all | Only 3 test cases. Missing: boundary spikes, empty timeline | Add edge cases |

##### `tests/verify_chronovisor_real.py` (116 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Flaky pattern | 40-46 | Depends on real matches in production DB — always skips in CI | Create fixture with seeded temp DB |
| 2 | **HIGH** | Test isolation | 35-36 | `get_match_data_manager()` connects to production DB | Use isolated test DB |
| 3 | MEDIUM | Assertion quality | 107-108 | `assertIsInstance(crit_moments, list)` — extremely weak | Assert on content properties |
| 4 | MEDIUM | Flaky pattern | 96 | `10000.0` magic number for equipment normalization | Extract to named constant |
| 5 | LOW | Test framework | 32-115 | Uses `unittest.TestCase` | Migrate to pytest |

##### `tests/verify_csv_ingestion.py` (63 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Test isolation | 23 | `DatabaseManager()` directly — connects to production DB | Use fixture with isolated DB |
| 2 | MEDIUM | Not a test | all | Verification script with `verify_ingestion()` returning boolean — no `test_` functions | Rename or move to `tools/` |
| 3 | MEDIUM | Assertion quality | 52-56 | `sys.exit(1)` for missing prerequisites instead of `pytest.skip` | Use `pytest.skip` |

##### `tests/verify_map_integration.py` (118 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Mock correctness | 23-38 | `MockTick` missing fields that `PlayerTickState` may have | Keep in sync or use schema introspection |
| 2 | MEDIUM | Assertion quality | 82-97 | Hardcoded feature index assertions | Use named constants from vectorizer |
| 3 | LOW | Not a test | all | Script returning boolean, not pytest | Convert to pytest |
| 4 | LOW | Coverage gap | 52 | Only tests single tick | Add multi-tick and edge cases |

##### `tests/verify_reporting.py` (89 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | **HIGH** | Test isolation | 29-37 | Connects to production DB and generates actual files on disk | Use temp DB fixture |
| 2 | **HIGH** | Test isolation | 78-79 | `shutil.rmtree(_TEST_REPORTS_DIR)` could delete unexpected directory | Use `tempfile.mkdtemp()` |
| 3 | MEDIUM | Flaky pattern | 30-31 | Returns `False` without `pytest.skip` if no matches | Use `pytest.skip` |
| 4 | MEDIUM | Assertion quality | 69 | `MatchReportGenerator(db_manager=None)` — only tests constructor doesn't crash | Test actual generation |
| 5 | LOW | Not a test | all | Script structure | Convert to pytest |

##### `tests/verify_superposition.py` (111 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | MEDIUM | Assertion quality | 43-44 | Hardcoded epsilon `1e-5` for random-init comparison | Set `torch.manual_seed()` |
| 2 | MEDIUM | Assertion quality | 70 | Uses 224x224 view frames but project standard is 64x64 | Use `TrainingTensorConfig` resolution |
| 3 | MEDIUM | Coverage gap | 86-89 | No value range check for `optimal_pos` | Add position range assertions |
| 4 | LOW | Not a test | all | Script returning booleans | Convert to pytest |
| 5 | LOW | Flaky pattern | 29 | `torch.randn` without seed | Add `torch.manual_seed(42)` |

---

### 3. Cross-Cutting Concerns

#### 3.1 Production Database Access in Tests (CRITICAL)

**11+ test files** access the production `database.db` instead of using isolated in-memory databases:

| File | Access Pattern | Risk |
|------|----------------|------|
| `test_hybrid_engine.py:163` | **Writes** to prod DB (INSERT + DELETE in finally) | **Data corruption** |
| `test_e2e.py:31,41` | `init_database()` + `get_db_manager()` + writes config | Config corruption |
| `test_functional.py:24-31` | Writes production config | Config corruption |
| `test_system_regression.py:10` | Module-level DB connection | Import side effects |
| `check_db_status.py:26` | Module-level DB queries | Import side effects |
| `verify_chronovisor_real.py:35` | Reads match data from prod | Environment-dependent |
| `verify_reporting.py:29` | Reads match data + writes files | Environment-dependent |
| `verify_csv_ingestion.py:23` | Direct `DatabaseManager()` | Environment-dependent |
| `test_onboarding.py:47` | Queries real DB | Environment-dependent |
| `test_rag_knowledge.py:63` | `init_database()` | Schema side effects |
| `test_auto_enqueue.py:29` | `init_database()` | Schema side effects |

**Recommendation:** Standardize on the `mock_db_manager` fixture from `conftest.py` or `seeded_db_session` for all unit tests. Reserve real DB access exclusively for tests marked `@pytest.mark.integration`.

#### 3.2 Unused `import sys` (68 files)

At least 68 of 96 test files contain `import sys` that is never used. This was a remnant of per-file `sys.path` manipulation that was centralized to `conftest.py`. Trivial cleanup with high hygiene value.

#### 3.3 `__new__()` Constructor Bypass Pattern (12 files)

Files using `ClassName.__new__(ClassName)` to bypass `__init__`, creating partially initialized objects:

| File | Class Bypassed |
|------|----------------|
| `test_experience_bank_db.py` | `ExperienceBank` |
| `test_feature_kast_roles.py` | `CoachingDialogueEngine` |
| `test_knowledge_graph.py` | `KnowledgeGraph` |
| `test_coaching_dialogue.py` | `CoachingService` |
| `test_chronovisor_scanner.py` | `ChronovisorScanner` |
| `test_coach_manager_flows.py` | `CoachTrainingManager` |
| `test_database_layer.py` | `StateManager` |
| `test_db_governor_integration.py` | `DatabaseGovernor` |
| `test_nn_training.py` | `TrainingController` |
| `test_profile_service.py` | `ProfileService` |
| `test_round_utils.py` | `ExperienceBank` |
| `test_state_reconstructor.py` | `RAPStateReconstructor` |

**Risk:** When production `__init__` methods add new required attributes, these tests silently pass with incomplete objects. The `__new__` pattern masks initialization bugs.

**Recommendation:** Use proper dependency injection or `unittest.mock.patch` on specific dependencies within `__init__`.

#### 3.4 Source Code Reading Anti-Pattern (6 files)

Tests that read raw `.py` source files and do string matching:

| File | What It Reads |
|------|---------------|
| `test_chronovisor_highlights.py` | scale_marker_sizes source |
| `test_db_backup.py` | Alembic hook source |
| `test_demo_format_adapter.py` | KAST estimator import, adapter delegation |
| `test_detonation_overlays.py` | property/method/overlay definitions |

**Risk:** Fragile — breaks on formatting changes, doesn't work with compiled distributions.

**Recommendation:** Use `hasattr()`, `inspect.getsource()`, or test actual behavior.

#### 3.5 Tautological Tests (3 files)

Tests that verify their own inline implementation, not production code:

| File | What It Tests |
|------|---------------|
| `test_training_orchestrator_logic.py:76-123` | Manually implements early stopping logic inline |
| `test_phase0_3_regressions.py:359-387` | Re-implements negative sampling inline |
| `test_state_reconstructor.py:92-109` | Sets attributes then asserts them |

#### 3.6 Scripts Masquerading as Tests (9 files)

Files in `tests/` that are diagnostic scripts, not pytest-compatible tests:

| File | Type |
|------|------|
| `forensics/check_db_status.py` | DB status printer |
| `forensics/check_failed_tasks.py` | Failed task query |
| `forensics/debug_env.py` | Environment debugger |
| `forensics/debug_nade_cols.py` | Grenade column inspector |
| `forensics/debug_parser_fields.py` | Parser field prober |
| `forensics/probe_missing_tables.py` | Schema inspector |
| `forensics/verify_map_dimensions.py` | Map asset checker |
| `setup_golden_data.py` | Golden DB creator |
| `verify_csv_ingestion.py` | CSV ingestion verifier |

**Recommendation:** Move to `tools/diagnostics/` or convert to proper pytest tests.

#### 3.7 Mixed Test Frameworks

2 files use `unittest.TestCase` while the rest of the project uses pytest:
- `tests/verify_chronovisor_logic.py`
- `tests/verify_chronovisor_real.py`

**Recommendation:** Migrate to pytest for consistency.

#### 3.8 Redundant/Duplicate Tests (~15 test methods)

| Test | Duplicated In |
|------|---------------|
| Health range classification | `test_coaching_dialogue.py`, `test_coaching_service_contracts.py` |
| Mode selection logic | `test_coaching_service_contracts.py`, `test_coaching_service_fallback.py`, `test_coaching_service_flows.py` |
| ModelFactory tests | `test_nn_infrastructure.py`, `test_model_factory_contracts.py` |
| Dimension chain tests | `test_dimension_chain_integration.py`, `test_coach_manager_tensors.py` |

#### 3.9 Always-Skipped Tests in CI (7 files)

Tests that depend on real data/files and are always skipped in CI environments:

| File | Dependency |
|------|-----------|
| `verify_chronovisor_real.py` | Real match data in production DB |
| `verify_reporting.py` | Real match data |
| `test_e2e.py` | >=5 PlayerMatchStats in prod DB |
| `test_system_regression.py` | Real data in prod DB |
| `verify_csv_ingestion.py` | CSV ingestion data |
| `forensics/debug_nade_cols.py` | `.dem` files on disk |
| `forensics/forensic_parser_test.py` | `.dem` files on disk |

**Impact:** ~7% of test files provide zero coverage in CI.

---

### 4. Inter-Module Dependency Risks

| Risk | Source (Tests) | Affected Domain |
|------|----------------|-----------------|
| Production DB corruption | `test_hybrid_engine.py` writes+deletes from prod DB | Report 6 (Storage) |
| Config file corruption | `test_e2e.py`, `test_functional.py` modify production config | Report 8 (Core Engine) |
| Feature index coupling | `test_feature_extractor_contracts.py`, `test_data_pipeline_contracts.py` hardcode vector indices | Report 3 (Processing Pipeline) |
| Stale `__new__` bypasses | 12 files bypass constructors — won't detect `__init__` changes | All production modules |
| Module-level DB connections | `test_system_regression.py`, `check_db_status.py` connect on import | Report 12 (CI/CD) — pytest collection may fail |

---

### 5. Remediation Priority Matrix

| Priority | Severity | Category | Effort | Scope | Recommendation |
|----------|----------|----------|--------|-------|----------------|
| P0 | HIGH | Test Isolation — prod DB writes | Low | 11 files | Replace `get_db_manager()` with `mock_db_manager` fixture |
| P1 | HIGH | Scripts in test tree | Low | 9 files | Move to `tools/diagnostics/` |
| P2 | HIGH | Test files in prod tree | Low | 2 files | Move `test_arch.py` files to `tests/` |
| P3 | HIGH | Tautological tests | Medium | 3 files | Refactor to test actual production methods |
| P4 | MEDIUM | `__new__` bypass pattern | Medium | 12 files | Replace with DI or `patch.__init__` |
| P5 | MEDIUM | Source code reading | Low | 6 files | Use `hasattr()` or behavioral tests |
| P6 | MEDIUM | Unused `import sys` | Trivial | 68 files | Batch removal |
| P7 | MEDIUM | Duplicate tests | Low | 4 test pairs | Consolidate to canonical locations |
| P8 | LOW | Always-skipped CI tests | High | 7 files | Create seeded test data fixtures |
| P9 | LOW | Coverage gaps | High | ~30 files | Incremental: add edge cases |
| P10 | LOW | Mixed test frameworks | Low | 2 files | Migrate to pytest |

---

### 6. Coverage Attestation

**All 96 test files were read in their entirety and individually analyzed:**

#### `Programma_CS2_RENAN/tests/` (68 files)
- [x] test_analysis_engines.py (266 lines)
- [x] test_analysis_engines_extended.py (423 lines)
- [x] test_analysis_gaps.py (500 lines)
- [x] test_analysis_orchestrator.py (191 lines)
- [x] test_auto_enqueue.py (142 lines)
- [x] test_baselines.py (395 lines)
- [x] test_chronovisor_highlights.py (380 lines)
- [x] test_chronovisor_scanner.py (243 lines)
- [x] test_coaching_dialogue.py (143 lines)
- [x] test_coaching_engines.py (497 lines)
- [x] test_coaching_service_contracts.py (290 lines)
- [x] test_coaching_service_fallback.py (302 lines)
- [x] test_coaching_service_flows.py (518 lines)
- [x] test_coach_manager_flows.py (803 lines)
- [x] test_coach_manager_tensors.py (234 lines)
- [x] test_config_extended.py (176 lines)
- [x] test_database_layer.py (406 lines)
- [x] test_data_pipeline_contracts.py (192 lines)
- [x] test_db_backup.py (202 lines)
- [x] test_db_governor_integration.py (201 lines)
- [x] test_debug_ingestion.py (84 lines)
- [x] test_demo_format_adapter.py (255 lines)
- [x] test_demo_parser.py (187 lines)
- [x] test_dem_validator.py (135 lines)
- [x] test_deployment_readiness.py (391 lines)
- [x] test_detonation_overlays.py (118 lines)
- [x] test_dimension_chain_integration.py (128 lines)
- [x] test_drift_and_heuristics.py (255 lines)
- [x] test_experience_bank_db.py (695 lines)
- [x] test_experience_bank_logic.py (137 lines)
- [x] test_feature_extractor_contracts.py (263 lines)
- [x] test_feature_kast_roles.py (481 lines)
- [x] test_features.py (80 lines)
- [x] test_game_theory.py (986 lines)
- [x] test_game_tree.py (552 lines)
- [x] test_hybrid_engine.py (239 lines)
- [x] test_integration.py (68 lines)
- [x] test_jepa_model.py (539 lines)
- [x] test_knowledge_graph.py (248 lines)
- [x] test_lifecycle.py (81 lines)
- [x] test_map_manager.py (104 lines)
- [x] test_model_factory_contracts.py (238 lines)
- [x] test_models.py (76 lines)
- [x] test_nn_extensions.py (373 lines)
- [x] test_nn_infrastructure.py (373 lines)
- [x] test_nn_training.py (186 lines)
- [x] test_onboarding.py (91 lines)
- [x] test_onboarding_training.py (160 lines)
- [x] test_persistence_stale_checkpoint.py (235 lines)
- [x] test_phase0_3_regressions.py (576 lines)
- [x] test_playback_engine.py (168 lines)
- [x] test_pro_demo_miner.py (194 lines)
- [x] test_profile_service.py (140 lines)
- [x] test_rag_knowledge.py (293 lines)
- [x] test_rap_coach.py (568 lines)
- [x] test_round_stats_enrichment.py (238 lines)
- [x] test_round_utils.py (308 lines)
- [x] test_security.py (158 lines)
- [x] test_services.py (104 lines)
- [x] test_session_engine.py (472 lines)
- [x] test_skill_model.py (192 lines)
- [x] test_spatial_and_baseline.py (128 lines)
- [x] test_spatial_engine.py (67 lines)
- [x] test_state_reconstructor.py (109 lines)
- [x] test_tactical_features.py (80 lines)
- [x] test_temporal_baseline.py (248 lines)
- [x] test_tensor_factory.py (861 lines)
- [x] test_trade_kill_detector.py (333 lines)
- [x] test_training_orchestrator_flows.py (579 lines)
- [x] test_training_orchestrator_logic.py (177 lines)
- [x] test_z_penalty.py (156 lines)

#### `Programma_CS2_RENAN/tests/automated_suite/` (5 files)
- [x] test_e2e.py (62 lines)
- [x] test_functional.py (32 lines)
- [x] test_smoke.py (42 lines)
- [x] test_system_regression.py (56 lines)
- [x] test_unit.py (49 lines)

#### `Programma_CS2_RENAN/tests/conftest.py` (1 file)
- [x] conftest.py (345 lines)

#### Standalone Test Files in Production Tree (2 files)
- [x] backend/nn/experimental/rap_coach/test_arch.py (48 lines)
- [x] backend/nn/rap_coach/test_arch.py (7 lines)

#### `tests/` Top-Level (19 files)
- [x] conftest.py (10 lines)
- [x] setup_golden_data.py (172 lines)
- [x] verify_chronovisor_logic.py (130 lines)
- [x] verify_chronovisor_real.py (116 lines)
- [x] verify_csv_ingestion.py (63 lines)
- [x] verify_map_integration.py (118 lines)
- [x] verify_reporting.py (89 lines)
- [x] verify_superposition.py (111 lines)
- [x] forensics/forensic_parser_test.py (49 lines)
- [x] forensics/test_skill_logic.py (75 lines)
- [x] forensics/check_db_status.py (55 lines)
- [x] forensics/check_failed_tasks.py (39 lines)
- [x] forensics/debug_env.py (31 lines)
- [x] forensics/debug_nade_cols.py (41 lines)
- [x] forensics/debug_parser_fields.py (67 lines)
- [x] forensics/probe_missing_tables.py (35 lines)
- [x] forensics/verify_map_dimensions.py (43 lines)
- [x] forensics/verify_spatial_integrity.py (49 lines)

**Total: 96 files audited. All files read completely, line-by-line.**
