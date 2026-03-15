# Audit Report 12 — Configuration, CI/CD & Infrastructure

**Scope:** Config files, CI/CD, infrastructure scripts — 62 files | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 2 CRITICAL | 3 HIGH | 18 MEDIUM | 24 LOW

> **Note:** Many findings here are CI/CD and requirements hygiene. The platform is shifting from Windows-primary to Linux — some Windows-only artifacts will naturally phase out.

---

## CRITICAL Findings

| ID | File | Finding |
|---|---|---|
| INF-C1 | scripts/build_production.bat:19,46; tools/build_tools.py:308; console.py:466 | **[FIXED 2026-03-13]** All 5 references (build_production.bat, build_tools.py, console.py, goliath.py) updated to `sync_integrity_manifest.py`. |
| INF-C2 | tools/reset_pro_data.py:41; tools/db_health_diagnostic.py:19; core/config.py:302; backend/knowledge/graph.py:32 | **[FIXED 2026-03-13]** schema.py `KNOWLEDGE_DB_PATH` now points to `knowledge_graph.db` (matching graph.py). Removed wrong-DB `run_fix("knowledge")` block. Remaining `knowledge_base.db` in config.py is unused dead config (tracked separately). |

## HIGH Findings

| ID | File | Finding |
|---|---|---|
| INF-H1 | alembic/env.py vs Programma_CS2_RENAN/migrations/env.py | **[FIXED 2026-03-13]** Orphan env.py replaced with RuntimeError deprecation guard. Canonical chain at `alembic/` now imports all 19 models. |
| INF-H2 | run_full_training_cycle.py:7 | **[FIXED 2026-03-13]** Changed `sys.path.append()` to `sys.path.insert(0, ...)` — project root now has priority. |
| INF-H3 | .github/workflows/build.yml:239-246 | **[FIXED 2026-03-13]** `|| true` narrowed to `|| test $? -eq 1` — only suppresses exit code 1 (findings found), tool errors (2+) now fail the step. |

## MEDIUM Findings

| ID | File | Finding |
|---|---|---|
| 1 | pyproject.toml | `disallow_untyped_defs = false` — mypy won't flag untyped functions |
| 5 | alembic.ini:87 | Hardcoded relative DB path (env.py overrides at runtime) |
| 6 | .pre-commit-config.yaml | No security linter (bandit) at pre-commit stage |
| 7 | .pre-commit-config.yaml | headless-validator only at pre-push — broken code can accumulate |
| 11 | requirements.txt | Wide version ranges (torch <3.0, numpy <3.0) — incompatible major versions possible |
| 13 | requirements-lock.txt | Windows-only lock file with pywin32/kivy-deps — fails on Linux. No platform markers. |
| 14 | requirements-lock.txt | Phantom PDF deps (pdfminer, pdfplumber, PyMuPDF, pypdf) despite documented removal (~50MB unused attack surface) |
| 18 | build.yml | Secret detection is simple grep — misses API keys, tokens |
| 19 | build.yml | `pip install` without hash verification — supply chain risk |
| 24 | console.py | `_cmd_svc_spawn` opens stderr_file, intentionally never closes — FD leak |
| 25 | console.py | `_cmd_maint_clear_cache` walks PROJECT_ROOT with shutil.rmtree — dangerous if misconfigured |
| 26 | console.py | `import threading` at line 1288 instead of top-level |
| INF-M1 | scripts/Setup_Macena_CS2.ps1:37 | **[FIXED 2026-03-13]** Path corrected to `requirements.txt` (project root). |
| INF-M2 | scripts/build_production.bat:26 | Error message references `fix_environment.ps1` which doesn't exist. Only `Setup_Macena_CS2.ps1` exists. |
| INF-M3 | scripts/build_exe.bat:8 | **[FIXED 2026-03-13]** Removed `--add-data database.db` from PyInstaller command. App creates/migrates its own DB on first launch. |
| INF-M4 | docker-compose.yml | No CPU/memory resource limits on FlareSolverr container. |
| INF-M5 | tools/build_pipeline.py:219 | Hardcoded venv path `venv_win/Scripts/pyinstaller.exe` — Windows-only, breaks on Linux. Use `shutil.which()`. |
| INF-M6 | alembic/env.py:26-34 | **[FIXED 2026-03-13]** All 19 model classes now explicitly imported. Was worse than reported — 12 models missing, not 5. |

## LOW Findings

| ID | File | Finding |
|---|---|---|
| 2 | pyproject.toml | Coverage fail_under = 30 — very low threshold |
| 3 | pyproject.toml | Uses legacy/private setuptools build backend |
| 4 | pytest.ini | `--disable-warnings` suppresses all warnings including deprecation |
| 8 | .pre-commit-config.yaml | Hook versions may not be latest |
| 9 | docker-compose.yml | FlareSolverr v3.4.6 — check for CVEs |
| 12 | requirements.txt | Comment says PDF deps removed but lock file still has them |
| 15 | requirements-lock.txt | torch locked to CUDA 12.1 |
| 16 | bindep.txt | Only Windows entries — no Linux binary deps listed |
| 20 | build.yml | All jobs on windows-latest — may not match production Linux |
| 21 | gemini-dispatch.yml | Edge case: empty body falls through (mitigated by auth check) |
| 22 | gemini-invoke.yml | Gemini CLI action not pinned to SHA |
| 27 | console.py | Logger named "MacenaConsole" not "cs2analyzer.console" |
| 28 | console.py | `dispatch_interactive` splits on spaces — can't handle paths with spaces |
| 29 | console.py | `_throttle_factor` private attribute access for display |
| 30 | console.py | `renderer._dirty` accessed from outside class |
| 31 | goliath.py | Logger named "Goliath" not "cs2analyzer.goliath" |
| 32 | goliath.py | `_cleanup_children` silently swallows all exceptions |
| INF-L1 | Programma_CS2_RENAN/migrations/env.py:22 | `sys.path.insert(0, os.getcwd())` — fragile, breaks if invoked from different directory. |
| INF-L2 | tools/build_pipeline.py:73 | Logger named `"MacenaBuild"` not `"cs2analyzer.build_pipeline"` |
| INF-L3 | tools/Feature_Audit.py:64 | Logger named `"FeatureAuditor"` not `"cs2analyzer.feature_audit"` |
| INF-L4 | seed_hltv_top20.py:16-20 | Own path stabilization instead of `_infra.py`; missing venv guard |
| INF-L5 | scripts/build_production.bat:24 | Checks `import keyring` — not in requirements.txt, appears unused |
| INF-L6 | backend/server.py:27 | `sys.path.append()` instead of `sys.path.insert(0, ...)` |
| INF-L7 | observability/__init__.py | Empty — no convenience re-exports |

## Cross-Cutting

1. **Logger Naming** — console.py, goliath.py, build_pipeline.py, Feature_Audit.py, logger_setup.py all use custom names instead of `cs2analyzer.<module>`.
2. **Requirements Drift** — Lock file has phantom PDF deps, is Windows-only, and contains CUDA-specific torch pin.
3. **Security Scanning Gaps** — No pre-commit security linter; CI Bandit error masking via `|| true`.
4. **Knowledge DB Split** — Two different filenames (`knowledge_graph.db` vs `knowledge_base.db`) point to different files. Tools operate on wrong databases.
5. **Missing File References** — `generate_manifest.py` referenced in 3+ locations, does not exist. Build pipeline partially broken.

## Resolved Since 2026-03-10

Removed 4 MEDIUM findings (36: fetchall() bounded, 39: private method access fixed, 41: portable paths, 44/45: training_progress.json stale data) and 6 LOW findings (37: schema.py logging added, 38: typo fixed, 40: f-strings in logging, 42: zh PDF lang fixed, 43: manifest refreshed, 46/47: stale JSON/settings cleaned). Addressed in commits f1e921f..45514a2.
