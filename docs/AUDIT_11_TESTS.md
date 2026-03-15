# Audit Report 11 — Tests

**Scope:** 96 test files, ~19,345 lines | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 4 HIGH | 80 MEDIUM | 150 LOW

> **Note:** Test hygiene is important but secondary to getting the pipeline trained. These findings represent technical debt that should be addressed incrementally. The systemic patterns (unused imports, `__new__()` bypass, prod DB access) are batch-fixable.

---

## HIGH Findings

| ID | File | Finding |
|---|---|---|
| — | test_services.py | Almost entirely smoke tests — no functional logic exercised |
| — | test_training_orchestrator_logic.py:76 | Tautological: manually implements early stopping logic instead of testing production code |
| — | test_e2e.py + test_functional.py | Operate on production DB/config (mitigated via `isolated_settings` but risky) |
| — | backend/nn/experimental/rap_coach/test_arch.py | Test file inside production source tree — packaged with prod code |
| — | tests/forensics/check_db_status.py | Not a test — queries prod DB at module-load time |
| — | tests/verify_chronovisor_real.py | Depends on real matches in production DB — always skips in CI |
| — | tests/verify_reporting.py | Connects to prod DB, writes files on disk, `shutil.rmtree` risk |
| T11-H1 | test_system_regression.py:10-11,41-44 | `test_database_schema_regression()` and `test_full_system_ingestion_query()` call `get_db_manager()` directly, connecting to production database. Should use `mock_db_manager` or `in_memory_db` fixtures. |

## Systemic MEDIUM Patterns (80 total)

### `__new__()` Constructor Bypass (12 files)
ExperienceBank, CoachingDialogueEngine, KnowledgeGraph, CoachingService, ChronovisorScanner, CoachTrainingManager, StateManager, DatabaseGovernor, TrainingController, ProfileService, ExperienceBank (round_utils), RAPStateReconstructor — all use `ClassName.__new__()` bypassing `__init__`, creating partially initialized objects that mask initialization bugs.

### Source Code Reading Anti-Pattern (6 files)
test_chronovisor_highlights.py, test_db_backup.py, test_demo_format_adapter.py, test_detonation_overlays.py — read raw .py source and do string matching instead of testing behavior.

### Production DB Access (5 remaining files)
test_system_regression.py (module-level), test_onboarding.py, test_rag_knowledge.py, test_auto_enqueue.py, test_onboarding_training.py — use `init_database()` or `get_db_manager()` touching production DB.

### Weak/Tautological Assertions
- `assert conf >= 0 or True` (always passes) — test_analysis_engines_extended.py
- `assert not ({})` tests Python semantics, not app code — test_coaching_service_contracts.py
- Conditional assertions `if SkillAxes.X in vec` — test_skill_model.py
- `isinstance(moments, list)` only — test_chronovisor_scanner.py
- `status != "INVALID"` weak negative — test_phase0_3_regressions.py

### Flaky Patterns
- `time.sleep(0.01)` for ordering — test_auto_enqueue.py
- Wall-clock latency tests — test_deployment_readiness.py
- 100 threads via ThreadPoolExecutor — test_phase0_3_regressions.py
- `datetime.now(UTC)` float rounding — test_temporal_baseline.py
- Non-deterministic embeddings — test_rag_knowledge.py
- `torch.randn()` without seed — test_arch.py

### Other MEDIUM
- Disjunctive assertion — test_coaching_engines.py
- Catches AttributeError but swallows all other exceptions — test_coaching_service_contracts.py
- `sys.modules` patching to make imports fail — test_coaching_service_fallback.py
- MagicMock without `spec=` (multiple files)
- `tempfile.mkstemp` with manual cleanup instead of `tmp_path` — test_demo_format_adapter.py
- Loss decrease fragility — test_rap_coach.py
- Only 5 tests for PlaybackEngine — test_playback_engine.py
- `mine_all_pro_stats` processes ALL pro players — test_pro_demo_miner.py
- Mixed unittest.TestCase + pytest — verify_chronovisor_logic.py, verify_chronovisor_real.py
- Diagnostic scripts masquerading as tests (9 files in tests/forensics/)

## Systemic LOW Patterns (150 total)

### Unused `import sys` (68 files)
Remnant of per-file sys.path manipulation centralized to conftest.py. Trivial batch cleanup.

### Coverage Gaps (~30 files)
Missing edge cases, boundary tests, NaN/negative inputs, concurrent access tests, multi-model tests across many files.

### Other LOW
- Duplicate test implementations (health range classification, mode selection, factory tests, dimension chain)
- Hardcoded feature indices instead of named constants
- Weak tolerance values in approx assertions
- Always-skipped CI tests (7 files depend on real data)
- Dead code in test files
- `conftest.py` sets `KIVY_NO_ARGS` but not `KIVY_NO_WINDOW` — tests may attempt window creation in headless CI
- `test_smoke.py` manually constructs `PROJECT_ROOT` and inserts `sys.path`, duplicating conftest.py logic

## Cross-Cutting

1. **Production DB in Tests** — 5+ files still touch production database. Standardize on `mock_db_manager` or `seeded_db_session` fixtures.
2. **`__new__()` Bypass** — 12 files bypass constructors, masking `__init__` bugs. Replace with DI or `patch.__init__`.
3. **68 Unused `import sys`** — Trivial batch cleanup with high hygiene value.
4. **Scripts in Test Tree** — 9 diagnostic scripts in tests/forensics/ are not pytest-compatible. Move to tools/ or add ImportError guards.

## Resolved Since 2026-03-10

Removed 1 HIGH finding (test_hybrid_engine.py:163 — now uses mock_db_manager via patch, no prod DB access). Minor improvements to test_rap_coach.py conftest in commit f1e921f.
