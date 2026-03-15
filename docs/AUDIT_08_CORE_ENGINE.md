# Audit Report 08 — Core Engine & App Entry

**Scope:** `core/`, `backend/control/`, `main.py`, `run_ingestion.py` — 29 files, ~7,484 lines | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 1 HIGH (arch debt) | 12 MEDIUM | 15 LOW

---

## HIGH — Acknowledged Debt

| ID | File | Finding |
|---|---|---|
| Core-11 | main.py | 2062 lines, 6 screen classes + full CS2AnalyzerApp. High-effort refactor deferred. |

## MEDIUM Findings

| ID | File | Finding |
|---|---|---|
| Core-12 | main.py | Mutable class-level `_last_completed_tasks = []` shared across instances |
| Core-13 | main.py | Mutable class-level `_nav_stack: list = []` shared across instances |
| Core-14 | main.py | Broken atexit cleanup — accumulates handlers on each `show_skill_radar()` |
| Core-16 | main.py | 9+ daemon threads perform DB writes — killed mid-transaction on exit |
| Core-17 | main.py | `self.ids.name_label.text` — no guard for missing KV widget |
| Core-25 | run_ingestion.py | `iterrows()` for state_lookup on 2.4M+ rows — extremely slow |
| Core-29 | localization.py | Import-time f-string path evaluation in translation strings |
| Core-35 | lifecycle.py | Log file handles stored on `self` — leak if `shutdown()` never called |
| Core-47 | resource_manager.py | Priority management Windows-only — Linux runs at normal priority |
| Core-50 | watcher.py | Import-time path values — stale after user changes settings |
| Core-54 | demo_loader.py | O(ticks) per-grenade nade lookup — could use interval-based |
| Core-57 | console.py:424 | `PlayerMatchStats.is_pro == True` without `.is_(True)` — SQLAlchemy boolean comparison inconsistency. session_engine.py already uses correct `.is_(True)` pattern. |

## LOW Findings

| ID | File | Finding |
|---|---|---|
| Core-04 | config.py | `globals()[key]` dynamic mutation — hard to trace |
| Core-05 | config.py | Russian word in comment ("которые") |
| Core-09 | session_engine.py | Teacher daemon 5-min sleep as 300x1s loop |
| Core-10 | session_engine.py | `pass` in nested except — notification failure silently swallowed |
| Core-19 | main.py | Unusual tuple unpacking for Kivy StringProperty declarations |
| Core-20 | main.py | Duplicate `from kivy.core.window import Window` import |
| Core-21 | main.py | `import copy` inside method |
| Core-27 | run_ingestion.py | `import math` inside function |
| Core-28 | run_ingestion.py | Logger name mismatch vs module path |
| Core-30 | localization.py | Only 3 languages supported |
| Core-36 | lifecycle.py | `Global\\` mutex prefix meaningless on Linux |
| Core-40 | console.py:220-228 | Console singleton reset on init failure — actually correct recovery behavior (cleans up partial state with delattr). **Reclassified from MEDIUM.** |
| Core-42 | ingest_manager.py | Missing explicit commit after `_queue_files()` |
| Core-43 | ingest_manager.py | Hardcoded `_MAX_RETRIES` and `_STALE_THRESHOLD` |
| Core-56 | localization.py:79,199,319 | Import-time f-string embeds `os.path.expanduser('~')` directly in TRANSLATIONS dict. `_get_home_dir()` helper exists but is not used for these f-strings. Path frozen at import time. |
| Core-58 | session_engine.py:33-48 | Module-level `_session_fh` FileHandler added to logger at import time, never removed. Leaks if module imported but `run_session_loop()` never called. |

## Cross-Cutting

1. **Daemon Thread Safety** — 12+ daemon threads killed on exit without cleanup; in-progress SQLite transactions rolled back by WAL.
2. **Platform Gaps** — resource_manager.py priority is Windows-only; Linux runs unrestricted.
3. **Import-Time Side Effects** — config.py creates directories, session_engine.py opens FileHandler, localization.py evaluates f-strings with filesystem paths.

## Resolved Since 2026-03-10

Removed 2 HIGH findings (Core-22 obsolete — code refactored, Core-45 fixed — correct import), 10 MEDIUM findings (Core-02, 03, 06, 07, 08, 18, 26, 39, 48, 57), and 5 LOW findings (Core-31, 32, 37, 38, 46) — fixed in commits 17d3a30..45514a2. Key fixes: STORAGE_ROOT single assignment, sentinel handled, sys.path guarded, FileHandler cleanup, is_pro .is_(True), Sentry logging, Italian strings translated, spatial_data thread-safe reload, resource_manager loop variable, demo_frame dataclass.

Obsolete findings removed: Core-15 (queue.pop refactored), Core-23 (_save_sequential_data refactored), Core-24 (state_lookup refactored), Core-55 (DataFrame passes refactored).
