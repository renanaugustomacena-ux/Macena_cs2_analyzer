# Audit Report 10 — Observability, Reporting & Tools

**Scope:** Observability, reporting, inner tools, root tools — 41 files, ~14,501 lines | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 1 CRITICAL | 1 HIGH (arch debt) | 21 MEDIUM | 10 LOW

---

## CRITICAL Finding

| ID | File | Finding |
|---|---|---|
| T10-C1 | tools/reset_pro_data.py:76-83,268 | **[FIXED 2026-03-13]** Added `"hltv_player_cache"` to `_ALLOWED_TABLES` frozenset. |

## HIGH — Acknowledged Debt

| ID | File | Finding |
|---|---|---|
| T10-H5 | Goliath_Hospital.py | 2894 lines, single class, 11 departments. Works correctly; size is maintainability concern. Tracked as architecture debt. |

## MEDIUM Findings

| ID | File | Finding |
|---|---|---|
| — | sentry_setup.py | Sentry DSN empty-string vs None — init may be called with invalid DSN |
| — | visualizer.py | matplotlib.use("Agg") may conflict with other backends |
| — | visualizer.py | Plotting methods catch broad Exception without re-raise |
| — | analytics.py | AnalyticsEngine singleton not explicitly thread-safe |
| — | analytics.py | HLTV 2.0 rating weights may not match current formula |
| — | _infra.py | Severity enum duplicated in 3 places (Goliath, portability_test) |
| — | backend_validator.py | Import smoke tests overlap with headless_validator — cached imports mask failures |
| — | db_inspector.py | f-string SQL for table names (from introspection, not user input) |
| — | demo_inspector.py | Auto-discovers .dem files — symlink/network path resolution may fail |
| — | Goliath_Hospital.py | Timeout exception swallowed into generic "Timed out" message |
| — | Goliath_Hospital.py | _ONCOLOGY_LENGTH_EXCLUSIONS whitelist manually maintained |
| — | Goliath_Hospital.py | JSON report write not atomic (no temp+rename) |
| — | headless_validator.py (root) | CRITICAL_DIRS list (27) manually maintained |
| — | headless_validator.py (root) | Import lists (~130 modules) manually maintained |
| — | headless_validator.py (root) | Oversized function check capped at 3 violations — rest silently pass |
| — | seed_hltv_top20.py | Own path stabilization instead of _infra.py; hardcoded player stats will go stale |
| — | user_tools.py | Heartbeat PID check via `os.kill(pid, 0)` fails on Windows |
| — | portability_test.py | Triple-quote counting heuristic produces false positives/negatives |
| — | Sanitize_Project.py | Deletes database.db without backup |
| — | rasp.py:22 | Static fallback HMAC key `"macena-cs2-integrity-v1"` — attacker who knows key can forge manifests. Consider per-installation key. |
| — | logger_setup.py:94 | `app_logger = get_logger("CS2_Coach_App")` — non-standard name. Should be `cs2analyzer.app`. |

## LOW Findings

| ID | File | Finding |
|---|---|---|
| — | project_snapshot.py | f-string SQL with KEY_TABLES constant |
| — | portability_test.py | 70+ SAFE_IMPORT_PATTERNS manually maintained |
| — | portability_test.py | Regex pattern recompilation per line per file |
| — | reset_pro_data.py | No venv guard |
| — | context_gatherer.py | O(n*m) AST walking — acceptable for current scale |
| — | audit_binaries.py + build_pipeline.py | Rich dependency not shared |
| — | verify_main_boot.py | No explicit venv guard |
| — | console.py + goliath.py | Logger names don't follow cs2analyzer.<module> convention |
| — | db_health_diagnostic.py | No venv guard |
| — | _infra.py:249 | `_detect_color()` returns `True` unconditionally on Windows — trailing `or True` defeats color detection. |

## Cross-Cutting

1. **Duplicated Severity Enum** — 3 copies with different semantics (HIGH/MEDIUM/LOW vs CRITICAL/WARNING/INFO).
2. **Root Tools Lack Shared Framework** — 15 root tools each implement own venv guard, path stabilization, Rich imports (~800 lines duplication).
3. **Oversized Files** — Goliath_Hospital.py (2894 lines) and headless_validator.py (2733 lines) would benefit from decomposition.

## Resolved Since 2026-03-10

Removed 4 MEDIUM findings (run_console_boot.py hardcoded sleep, verify_all_safe.py timeout, missing venv guards in 3 tools, duplicated Rich boilerplate) and related entries consolidated — addressed in commits f1e921f..2fa2cf3.
