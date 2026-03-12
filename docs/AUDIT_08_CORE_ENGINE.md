# AUDIT_08: Core Engine & App Entry
## Date: 2026-03-10
## Scope: 29 files

---

### 1. Executive Summary

| Metric | Count |
|--------|-------|
| Total files audited | 29 |
| HIGH severity | 5 |
| MEDIUM severity | 22 |
| LOW severity | 16 |
| Clean files (no findings) | 6 |

The Core Engine domain encompasses the application's configuration system, session engine (tri-daemon architecture), the Kivy desktop app entry point (`main.py` — 1945 lines), the ingestion runner pipeline (`run_ingestion.py` — 1211 lines), control layer (console, ML controller, ingestion manager), and supporting modules (lifecycle, localization, spatial data, platform utils, demo frame models, etc.).

**Critical themes:**
1. **`main.py` god-module risk** — 1945 lines combining 6+ UI screens, app lifecycle, file management, settings, training status polling, and ingestion control in a single file.
2. **Platform compatibility gaps** — `ml_controller.py` imports `fcntl` unconditionally (Linux-only), `lifecycle.py` calls `ctypes.windll` without platform guard on shutdown path, priority management only works on Windows.
3. **Module-level globals race** (C-01) — documented but still present; daemon threads reading snapshot-at-import globals while `refresh_settings()` writes under lock.
4. **Mutable class-level defaults** — `_last_completed_tasks = []` and `_nav_stack: list = []` on `CS2AnalyzerApp` are shared across instances (anti-pattern even with single instance).
5. **Private method access** — `match_manager._get_or_create_engine()` called directly from `run_ingestion.py`.

**Cross-references:**
- Report 12: `schema.py` SQL injection (HIGH) — exposed via `console.py` → `db_governor.py` chain
- Report 6 (pending): `database.py`, `db_models.py`, `state_manager.py` — referenced heavily throughout
- Report 7 (pending): `demo_parser.py`, `demo_format_adapter.py` — called by `run_ingestion.py` and `demo_loader.py`

---

### 2. File-by-File Findings

---

#### Programma_CS2_RENAN/core/config.py (393 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 1 | HIGH | Concurrency | 215-238 | **C-01: Module-level globals unsynchronized on read.** `CS2_PLAYER_NAME`, `STEAM_API_KEY`, `FACEIT_API_KEY` etc. are assigned once at import time. `refresh_settings()` (line 318) updates them under `_settings_lock`, but daemon threads reading the bare globals see stale values. The `get_credential()` function (line 306) exists as the safe alternative but adoption is inconsistent across the codebase. | Deprecate module-level globals with `warnings.warn()`. Audit all consumers — replace bare global reads with `get_setting()` or `get_credential()`. |
| 2 | MEDIUM | Design | 277 | **STORAGE_ROOT reassignment.** Module-level `STORAGE_ROOT` is first assigned at line 50 (`get_writeable_dir()`), then reassigned to `USER_DATA_ROOT` at line 277. Import-order dependency: code importing `STORAGE_ROOT` before line 277 executes gets the wrong value. `SETTINGS_PATH` (line 53) deliberately avoids this by using `get_writeable_dir()` directly. | Document the dual-assignment pattern prominently or unify to a single late-binding function. |
| 3 | MEDIUM | Security | 364 | **"PROTECTED_BY_WINDOWS_VAULT" sentinel leaks.** When keyring is available, `save_user_setting()` writes the sentinel string to the JSON file. If the app later runs without keyring (e.g., different environment), `load_user_settings()` returns the literal sentinel as the API key value. Line 200 guards against this, but only for `STEAM_API_KEY` and `FACEIT_API_KEY`. | Extend sentinel guard to any key that might use keyring, or store a distinct JSON-safe marker (e.g., empty string). |
| 4 | LOW | Maintainability | 392 | **Dynamic globals mutation via `globals()[key]`.** Hard to trace statically; IDE navigation and grep miss these assignments. | Consider using a property-based accessor pattern instead. |
| 5 | LOW | Code Quality | 252 | **Russian word in comment** ("которые" = "which"). Minor but indicates copy-paste from non-English source. | Replace with English equivalent. |

---

#### Programma_CS2_RENAN/core/session_engine.py (503 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 6 | MEDIUM | Technical Debt | 11-14 | **sys.path manipulation at module level.** Commented as "technical debt" in the code itself. | Migrate to proper package installation via `pyproject.toml` entry points. |
| 7 | MEDIUM | Resource Leak | 37-44 | **FileHandler not cleaned up on failure.** If `logging.FileHandler()` succeeds but subsequent code fails, the handler leaks. Also, the handler is created unconditionally on every import — if session_engine is imported but not run, the log file is created unnecessarily. | Wrap in try/finally; move handler setup inside `run_session_loop()`. |
| 8 | MEDIUM | Correctness | 473-476 | **`PlayerMatchStats.is_pro == True`** — SQLAlchemy boolean comparison should use `.is_(True)` for correctness with NULL values and to satisfy linters. | Replace with `PlayerMatchStats.is_pro.is_(True)`. |
| 9 | LOW | Concurrency | 397-400 | **Teacher daemon 5-minute sleep as 300×1s loop.** Functional but could use `_shutdown_event.wait(300)` directly (already used elsewhere in the file). The 1s loop was intentional for responsiveness, but `Event.wait(timeout=300)` wakes immediately on shutdown signal. | Use `_shutdown_event.wait(300)` for cleaner implementation. |
| 10 | LOW | Error Handling | 107-108 | **`pass` in nested except block.** Notification failure during backup error is silently swallowed. | Log at DEBUG level at minimum. |

---

#### Programma_CS2_RENAN/main.py (1945 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 11 | HIGH | Architecture | 1-1945 | **God module.** 1945 lines containing 6 screen classes (`HomeScreen`, `CoachScreen`, `UserProfileScreen`, `SettingsScreen`, `ProfileScreen`, `SteamConfigScreen`, `FaceitConfigScreen`), the full `CS2AnalyzerApp` class (1500+ lines), and the `__main__` block. Violates single-responsibility principle; makes testing, navigation, and code review extremely difficult. | Extract screen classes to individual files under `apps/desktop_app/screens/`. Keep `CS2AnalyzerApp` in `main.py` but move helper methods to mixins or delegates. |
| 12 | MEDIUM | Correctness | 467 | **Mutable class-level default `_last_completed_tasks = []`.** This is a class variable, not an instance variable. If multiple `CS2AnalyzerApp` instances were created, they'd share the same list. While only one instance exists in practice, this is a latent bug. | Move to `__init__` as `self._last_completed_tasks = []`. |
| 13 | MEDIUM | Correctness | 1838 | **Mutable class-level default `_nav_stack: list = []`.** Same issue as finding #12 — shared across instances. | Move to `__init__`. |
| 14 | MEDIUM | Correctness | 1689 | **Broken atexit cleanup.** `atexit.register(lambda: os.path.exists(out_path) and os.unlink(out_path))` — Python's `and` short-circuits: if `os.path.exists()` returns `True`, `os.unlink()` is called and its return value (`None`) becomes the expression result. This works correctly by accident — `os.unlink()` is indeed called. However, the intent is clearer and safer with an `if` statement inside the lambda. Also, `atexit.register` is called on every `show_skill_radar()` invocation, accumulating handlers. | Use `atexit.register(lambda: os.unlink(out_path) if os.path.exists(out_path) else None)` and guard against duplicate registration. |
| 15 | MEDIUM | Performance | 1059 | **`queue.pop(0)` in BFS widget refresh.** `list.pop(0)` is O(n). For deep widget trees this could be slow. | Use `collections.deque` with `popleft()`. |
| 16 | MEDIUM | Concurrency | 305-306, 387, 620-639, 780, 971, 1208, 1443, 1728, 1894 | **Daemon threads performing DB writes.** At least 9 places spawn `daemon=True` threads that perform database operations. Daemon threads are killed when the main thread exits — if killed mid-transaction, SQLite WAL state could be corrupted. | Use non-daemon threads with join timeout in `on_stop()`, or use a task queue pattern. |
| 17 | MEDIUM | UI Safety | 326 | **`self.ids.name_label.text = p["player_name"] or "Player"`.** If `ids.name_label` doesn't exist (KV layout missing), this raises `AttributeError`. | Guard with `hasattr` or `.get()` pattern like other methods do (e.g., line 270). |
| 18 | MEDIUM | Error Handling | 68 | **Bare `except Exception: pass`** for Sentry initialization. Silently swallows all errors including `ImportError` for the module and configuration errors. | Log at DEBUG level. |
| 19 | LOW | Code Quality | 128-134 | **Tuple unpacking for class properties.** `title, severity, message, focus_area = (StringProperty(), ...)` — unusual pattern, harder to read than individual assignments. | Use standard individual property declarations. |
| 20 | LOW | Maintainability | 601 | **Duplicate import `from kivy.core.window import Window`** — already imported at line 86. | Remove duplicate import. |
| 21 | LOW | Maintainability | 1029 | **`import copy` inside method.** Imported on every `apply_font_settings()` call. | Move to module level. |

---

#### Programma_CS2_RENAN/run_ingestion.py (1211 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 22 | HIGH | Encapsulation | 1160 | **Private method access `match_manager._get_or_create_engine(match_id)`.** Directly accesses internal API of `MatchDataManager`, bypassing any public interface. If `_get_or_create_engine` is renamed or refactored, this breaks silently. | Expose a public `get_engine(match_id)` method on `MatchDataManager`. |
| 23 | MEDIUM | Architecture | 924-1204 | **`_save_sequential_data()` is ~280 lines.** Single function handling parsing, interpolation, enrichment, DataFrame construction, chunked DB writes, metadata storage, and event extraction. Extremely difficult to unit test. | Break into sub-functions: `_build_match_dataframe()`, `_build_legacy_dataframe()`, `_write_chunks()`, etc. |
| 24 | MEDIUM | Data Integrity | 593-602 | **state_lookup eviction strategy.** When `_STATE_LOOKUP_CAP` (50K) is hit, the first half of keys are deleted. This evicts the oldest ticks — but if a later event references those ticks via `_lookup_state()` fallback, the lookup fails silently and returns defaults `{health: 100, armor: 0}`. | Use an LRU cache (e.g., `collections.OrderedDict` or `functools.lru_cache`) or increase the cap. |
| 25 | MEDIUM | Performance | 594 | **`for _, row in df_ticks.iterrows()` for building state_lookup.** `iterrows()` is extremely slow on large DataFrames (2.4M+ rows). The comment acknowledges this was an optimization target for the main loop but the state_lookup builder still uses it. | Use vectorized operations or `itertuples()`. |
| 26 | MEDIUM | Correctness | 125-126 | **`PlayerMatchStats.is_pro == False`** — same SQLAlchemy boolean comparison issue as finding #8. | Use `.is_(False)`. |
| 27 | LOW | Code Quality | 451 | **`import math` inside function.** Imported on every `_save_player_stats()` call. | Move to module level. |
| 28 | LOW | Naming | 44 | **Logger name mismatch.** Logger is `cs2analyzer.ingestion_runner` but the module path is `Programma_CS2_RENAN.run_ingestion`. Not wrong, but inconsistent with the convention of matching logger name to module path. | Align logger name with module hierarchy. |

---

#### Programma_CS2_RENAN/core/localization.py (438 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 29 | MEDIUM | Correctness | 82, 200, 318 | **Import-time path evaluation in translation strings.** `wizard_step1_desc` uses f-string with `os.path.expanduser('~')` evaluated at module import time, not at display time. If `HOME` changes (rare but possible in containers), the displayed path is stale. The `_get_home_dir()` function exists (line 17-19) but isn't used in the hardcoded dict. | Use `{home_dir}` placeholder in hardcoded strings and resolve via `_get_home_dir()` at display time. |
| 30 | LOW | Completeness | 377 | **Only 3 languages supported (en, pt, it).** JSON files checked for same 3 codes. No mechanism for user-contributed translations. | Consider a plugin mechanism or at least document how to add languages. |
| 31 | LOW | Code Quality | 14 | **`_HOME_DIR` assigned but only used as documentation.** The module-level `_HOME_DIR = os.path.expanduser("~")` is never referenced anywhere. | Remove dead variable. |

---

#### Programma_CS2_RENAN/core/registry.py (50 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Clean, well-structured module with proper thread safety via `_registry_lock`. | — |

---

#### Programma_CS2_RENAN/core/spatial_data.py (419 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 32 | LOW | Design | 224-228 | **`reload()` is not thread-safe.** Sets `_loaded = False`, calls `_load_config()`, then sets `_loaded = True`. A concurrent `__init__()` could see `_loaded = False` and trigger a second `_load_config()` that races with the first. | Wrap reload in `_loader_lock`. |
| 33 | LOW | Correctness | 289-291 | **Ambiguous partial match returns first candidate.** When multiple maps match (e.g., "de_nuke" and "de_nuke_lower" both match "nuke"), the code returns `candidates[0]` after logging a warning. The ordering depends on dict iteration order. | Sort candidates by key length (shortest = most specific) before returning. |

---

#### Programma_CS2_RENAN/core/lifecycle.py (146 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 34 | HIGH | Platform | 138-141 | **`ctypes.windll.kernel32.CloseHandle` called unconditionally in `shutdown()`.** On Linux/macOS, `ctypes.windll` doesn't exist. If `_instance_mutex` is somehow set on a non-Windows platform, this crashes. Currently mitigated because `ensure_single_instance()` returns early on non-Windows, so `_instance_mutex` stays `None`. But if the code is modified in the future, this becomes a crash. | Add `if sys.platform == "win32":` guard around the CloseHandle block. |
| 35 | MEDIUM | Resource Leak | 79-80 | **Log file handles stored on `self`.** `self._out_log` and `self._err_log` are opened before `Popen`. If `Popen` succeeds but `shutdown()` is never called (process crash), handles leak. The `atexit.register(self.shutdown)` at line 102 mitigates this but `atexit` handlers are not guaranteed to run on all termination signals. | Use a context manager pattern or ensure handles are tracked more robustly. |
| 36 | LOW | Naming | 23 | **Mutex name includes `Global\\` prefix.** This is a Windows kernel namespace prefix — meaningless on Linux. Not a bug (Linux skips mutex entirely), but the naming could confuse maintainers. | Add comment explaining this is Windows-only. |

---

#### Programma_CS2_RENAN/core/platform_utils.py (72 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Well-structured with explicit platform handling and validated fallbacks. | — |

---

#### Programma_CS2_RENAN/core/__init__.py (empty)

No findings.

---

#### Programma_CS2_RENAN/core/constants.py (35 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Clean constants module with clear documentation and derivation formulas. | — |

---

#### Programma_CS2_RENAN/core/demo_frame.py (166 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 37 | LOW | Design | 56-62 | **`__post_init__` uses `object.__setattr__`** to mutate coordinates on a non-frozen dataclass. `PlayerState` is not frozen, so regular `self.x = 0.0` would work. | Use standard attribute assignment. |
| 38 | LOW | Completeness | 101 | **`NadeState.trajectory` uses mutable default `field(default_factory=list)`** on a frozen dataclass. This is correct (frozen prevents reassignment, not mutation of contents), but the trajectory list can still be modified after creation, which violates the spirit of immutability. | Use `tuple` instead of `list` for trajectory. |

---

#### Programma_CS2_RENAN/backend/control/__init__.py (empty)

No findings.

---

#### Programma_CS2_RENAN/backend/control/console.py (507 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 39 | MEDIUM | Localization | 265 | **Hardcoded Italian log message.** `"Console: FlareSolverr non disponibile. Hunter non avviato. Avvia Docker Desktop e riprova."` — this message appears in application logs, not UI, but non-Italian-speaking maintainers cannot read it. | Use English for all log messages; reserve Italian for user-facing UI strings via localization system. |
| 40 | MEDIUM | Design | 225-228 | **Console singleton reset on init failure.** When subsystem creation fails, `Console._instance = None` is set, allowing retry. However, the `delattr` loop at lines 223-225 can raise `AttributeError` if the attribute was never set (e.g., `ml_controller` fails before `db_governor` is created). The `hasattr` guard handles this correctly, but if `supervisor` init fails, the other attributes were never set. | The `hasattr` guard is sufficient. Consider logging which subsystems failed. |
| 41 | LOW | Performance | 291-298 | **Shutdown wait loop uses `time.sleep(0.5)` polling.** 10 iterations × 0.5s = 5s max wait. Could use `threading.Event` for cleaner implementation. | Use event-based wait. |

---

#### Programma_CS2_RENAN/backend/control/ingest_manager.py (278 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 42 | LOW | Correctness | 136 | **`_queue_files` import without explicit commit.** `session.commit()` is missing after `_queue_files(session, [demo_path], is_pro)`, but `_queue_files` itself doesn't commit. The context manager `get_session()` may auto-commit on exit (depends on database.py implementation). | Add explicit `session.commit()` after `_queue_files()` call for clarity. |
| 43 | LOW | Design | 193-194 | **Hardcoded `_MAX_RETRIES = 3` and `_STALE_THRESHOLD = timedelta(minutes=5)`.** These should be configurable via `get_setting()` or constants, similar to `ZOMBIE_TASK_THRESHOLD_SECONDS` in session_engine.py. | Extract to config constants. |

---

#### Programma_CS2_RENAN/backend/control/ml_controller.py (173 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 44 | HIGH | Platform | 1 | **`import fcntl` — Linux-only module.** This will raise `ImportError` on Windows, making the entire `ml_controller` module unimportable on Windows. The project targets Windows as primary platform (frozen builds, Windows mutex, etc.). | Guard with `try: import fcntl except ImportError: fcntl = None` and use `msvcrt` on Windows, or make file locking conditional. |
| 45 | MEDIUM | Correctness | 21 | **`from Programma_CS2_RENAN.core.constants import DATA_DIR`** — `constants.py` does NOT export `DATA_DIR`. `DATA_DIR` is defined in `config.py`. This import will raise `ImportError` at runtime when `training_file_lock()` is called. | Change to `from Programma_CS2_RENAN.core.config import DATA_DIR`. |

---

#### Programma_CS2_RENAN/backend/progress/__init__.py (empty)

No findings.

---

#### Programma_CS2_RENAN/backend/progress/longitudinal.py (10 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Simple, clean dataclass. | — |

---

#### Programma_CS2_RENAN/backend/progress/trend_analysis.py (17 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 46 | LOW | Correctness | 14 | **Confidence formula `min(1.0, len(values) / 30)`** — confidence reaches 1.0 at 30 data points, but the function is called with `limit(10)` in `_get_feature_trends()` (run_ingestion.py:139). Confidence can never exceed 0.33 in practice. | Either increase the history limit or adjust the confidence denominator. |

---

#### Programma_CS2_RENAN/backend/control/db_governor.py (175 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Well-structured with proper async integrity checking, timeout guards, and tiered storage audit. | — |

---

#### Programma_CS2_RENAN/backend/ingestion/__init__.py (empty)

No findings.

---

#### Programma_CS2_RENAN/backend/ingestion/resource_manager.py (202 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 47 | MEDIUM | Platform | 150-153, 156-171 | **Priority management only works on Windows.** `set_low_priority()` and `set_high_priority()` are guarded by `if os.name == "nt":` — on Linux, background ingestion runs at normal priority, defeating the purpose of resource management. | Add Linux support via `os.nice()` or `psutil.Process().nice()` with Unix nice values. |
| 48 | MEDIUM | Correctness | 139 | **Unused loop variable.** `for f, arg in enumerate(cmd)` — `f` is never used. | Change to `for arg in cmd` or `for _, arg in ...`. |
| 49 | LOW | Performance | 130 | **`psutil.process_iter()` in `is_gui_active()`.** Iterates ALL system processes to find the GUI. Called periodically, this is expensive. | Cache result with TTL, or use a PID file / shared memory flag. |

---

#### Programma_CS2_RENAN/backend/ingestion/watcher.py (230 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 50 | MEDIUM | Correctness | 212-217 | **Watcher uses import-time path values.** `DEFAULT_DEMO_PATH` and `PRO_DEMO_PATH` are imported at module level (line 13). If the user changes these paths via the Settings UI, the watcher continues monitoring the old directories. `os.makedirs()` also creates directories at the old paths. | Re-read paths from `get_setting()` on each `start()` call; support `restart()` method. |
| 51 | LOW | Design | 212-213 | **`os.makedirs(DEFAULT_DEMO_PATH, exist_ok=True)` creates user home directory structure.** If `DEFAULT_DEMO_PATH` is `~`, this is a no-op. But if it's a custom path that doesn't exist yet, the watcher silently creates it. This is arguably correct behavior but should be logged. | Add info-level log when directories are created. |

---

#### Programma_CS2_RENAN/ingestion/__init__.py (empty)

No findings.

---

#### Programma_CS2_RENAN/ingestion/steam_locator.py (136 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 52 | LOW | Duplication | 16 | **Duplicate Steam path discovery.** Comment at line 13-15 documents that `backend/data_sources/steam_demo_finder.py` performs similar logic. Consolidation is deferred. | Track as technical debt; consolidate when feasible. |
| 53 | LOW | Security | 122 | **`Path(target_dir).glob("**/*.dem")` — recursive glob.** On large drives with deep directory structures, this can be very slow and could follow symlinks into unexpected locations. | Add depth limit or symlink guard. |

---

#### Programma_CS2_RENAN/ingestion/demo_loader.py (557 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 54 | MEDIUM | Performance | 266 | **`for t in range(t_tick or st, et + FADE_TICKS + 1)` — potentially massive range.** If `MAX_NADE_DURATION` is 20s × 64 ticks = 1280 ticks, plus `FADE_TICKS` = 5s × 64 = 320 ticks, each grenade creates up to 1600 entries. With 100+ grenades per match, `nades_by_tick` can contain 100K+ entries, each a list of `NadeState` objects. | Use interval-based lookup (binary search on sorted intervals) instead of populating every tick. |
| 55 | MEDIUM | Memory | 142-158, 366-465 | **Two full-match DataFrame passes held in memory simultaneously.** Pass 1 builds `pos_by_tick` (dict of dicts for every tick × every player), Pass 3 builds `rows_df` (full DataFrame). For a long match, both structures can consume several GB. `del rows_df` at line 158 helps but `pos_by_tick` persists for the entire function. | Stream Pass 1 data to disk-backed storage or merge passes. |
| 56 | LOW | Code Quality | 90-91 | **`CACHE_DIR` computed relative to `__file__`.** If the module is installed as a package, `__file__` may point to a read-only location. | Use `config.DATA_DIR` for cache storage. |

---

#### Programma_CS2_RENAN/ingestion/integrity.py (54 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings. Clean wrapper around `demo_format_adapter.validate_demo_file()` with proper error classification. | — |

---

#### Programma_CS2_RENAN/hltv_sync_service.py (202 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 57 | MEDIUM | Localization | 56, 62, 72, 77, 88-90 | **Hardcoded Italian strings in log messages and notifications.** `"FlareSolverr non avviabile automaticamente"`, `"HLTV sync bloccato"`, `"non raggiungibile"`, etc. These appear in user-visible notifications (via `add_notification`). | Route through `i18n.get_text()` or at minimum use English for log messages. |
| 58 | LOW | Design | 25-26 | **PID and stop signal files stored in source directory.** `PID_FILE` and `STOP_SIGNAL` are in `SCRIPT_DIR` (the package directory). In installed/frozen mode, this directory may be read-only. | Use `config.DATA_DIR` or a platform-appropriate temp directory. |
| 59 | LOW | Resilience | 129-131 | **`time.sleep(60)` on sync error.** Fixed 60s backoff with no exponential increase. Repeated failures flood logs at 1/min. | Implement exponential backoff (e.g., 60, 120, 240, ..., max 3600). |

---

#### Programma_CS2_RENAN/backend/storage/db_migrate.py (113 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| 60 | LOW | Correctness | 36-38 | **`alembic.ini` searched relative to `BASE_DIR`.** `BASE_DIR` is `Programma_CS2_RENAN/` but `alembic.ini` is in the project root (one level up). The path `os.path.join(BASE_DIR, "alembic.ini")` won't find it. Line 44 also sets `script_location` relative to `BASE_DIR`. | Verify path resolution works correctly in both development and frozen modes; consider using project root instead. |

---

### 3. Cross-Cutting Concerns

#### 3.1 Platform Compatibility Gap
The project targets Windows as primary platform (frozen builds, Windows mutex, Windows priority classes) but several modules assume Linux:
- `ml_controller.py` imports `fcntl` unconditionally (HIGH — breaks Windows import)
- `resource_manager.py` process priority management is Windows-only
- `lifecycle.py` CloseHandle call lacks platform guard

#### 3.2 Module-Level Globals (C-01)
The `config.py` unsynchronized globals pattern is the most significant concurrency risk. Seven module-level variables (`CS2_PLAYER_NAME`, `STEAM_ID`, `STEAM_API_KEY`, `FACEIT_API_KEY`, `DEFAULT_DEMO_PATH`, `PRO_DEMO_PATH`, `LANGUAGE`) are read without locks by daemon threads. `get_setting()` and `get_credential()` exist as safe alternatives but are not consistently used.

#### 3.3 Daemon Thread Safety
At least 12 daemon threads are spawned across `main.py`, `session_engine.py`, and `hltv_sync_service.py`. Daemon threads are killed on main thread exit without cleanup. Any in-progress SQLite transaction will be rolled back (WAL mode handles this gracefully), but file operations (cache writes, log flushes) may produce corrupt artifacts.

#### 3.4 Italian Log Messages
Both `console.py` (line 265) and `hltv_sync_service.py` (lines 56, 62, 72, 77, 88-90) contain hardcoded Italian strings in log messages and user-visible notifications. This breaks the localization architecture.

---

### 4. Inter-Module Dependency Risks

| This Domain | Depends On | Risk |
|-------------|-----------|------|
| `run_ingestion.py` | `match_data_manager._get_or_create_engine()` | Private API access — breaks on refactor |
| `ml_controller.py` | `core.constants.DATA_DIR` | Import error — `DATA_DIR` is in `config.py`, not `constants.py` |
| `watcher.py` | `config.DEFAULT_DEMO_PATH` (import-time) | Stale path after user changes settings |
| `session_engine.py` | `ml_controller._TRAINING_LOCK` | Direct access to module-level lock — tight coupling |
| `main.py` | 20+ modules from every subsystem | God module creates import web; any change risks cascading failures |
| `lifecycle.py` | `ctypes.windll` | Platform crash risk if mutex state leaks |

---

### 5. Remediation Priority Matrix

| Priority | Finding # | File | Issue | Effort |
|----------|-----------|------|-------|--------|
| P0 | 44 | ml_controller.py | `import fcntl` crashes on Windows | Low (add try/except) |
| P0 | 45 | ml_controller.py | Wrong import path for `DATA_DIR` | Low (fix import) |
| P1 | 34 | lifecycle.py | CloseHandle without platform guard | Low (add if-guard) |
| P1 | 1 | config.py | C-01 unsynchronized globals | Medium (deprecation + consumer audit) |
| P1 | 22 | run_ingestion.py | Private method `_get_or_create_engine` | Low (add public method) |
| P2 | 11 | main.py | God module — 1945 lines | High (major refactor) |
| P2 | 16 | main.py | Daemon threads with DB writes | Medium (thread pool pattern) |
| P2 | 50 | watcher.py | Stale import-time paths | Medium (dynamic path resolution) |
| P2 | 47 | resource_manager.py | Priority management Windows-only | Medium (add Linux support) |
| P2 | 57 | hltv_sync_service.py | Hardcoded Italian strings | Low (route through i18n) |
| P3 | 23 | run_ingestion.py | 280-line function | Medium (decompose) |
| P3 | 54 | demo_loader.py | O(ticks) nade lookup | Medium (interval-based) |
| P3 | 12,13 | main.py | Mutable class-level defaults | Low |
| P3 | 8,26 | session_engine/run_ingestion | SQLAlchemy `== True/False` | Low |

---

### 6. Coverage Attestation

All 29 files in this domain were read in full and analyzed:

- [x] `Programma_CS2_RENAN/core/config.py` (393 lines)
- [x] `Programma_CS2_RENAN/core/session_engine.py` (503 lines)
- [x] `Programma_CS2_RENAN/main.py` (1945 lines)
- [x] `Programma_CS2_RENAN/run_ingestion.py` (1211 lines)
- [x] `Programma_CS2_RENAN/core/localization.py` (438 lines)
- [x] `Programma_CS2_RENAN/core/registry.py` (50 lines)
- [x] `Programma_CS2_RENAN/core/spatial_data.py` (419 lines)
- [x] `Programma_CS2_RENAN/core/lifecycle.py` (146 lines)
- [x] `Programma_CS2_RENAN/core/platform_utils.py` (72 lines)
- [x] `Programma_CS2_RENAN/core/__init__.py` (empty)
- [x] `Programma_CS2_RENAN/core/constants.py` (35 lines)
- [x] `Programma_CS2_RENAN/core/demo_frame.py` (166 lines)
- [x] `Programma_CS2_RENAN/backend/control/__init__.py` (empty)
- [x] `Programma_CS2_RENAN/backend/control/console.py` (507 lines)
- [x] `Programma_CS2_RENAN/backend/control/ingest_manager.py` (278 lines)
- [x] `Programma_CS2_RENAN/backend/control/ml_controller.py` (173 lines)
- [x] `Programma_CS2_RENAN/backend/control/db_governor.py` (175 lines)
- [x] `Programma_CS2_RENAN/backend/progress/__init__.py` (empty)
- [x] `Programma_CS2_RENAN/backend/progress/longitudinal.py` (10 lines)
- [x] `Programma_CS2_RENAN/backend/progress/trend_analysis.py` (17 lines)
- [x] `Programma_CS2_RENAN/backend/ingestion/__init__.py` (empty)
- [x] `Programma_CS2_RENAN/backend/ingestion/resource_manager.py` (202 lines)
- [x] `Programma_CS2_RENAN/backend/ingestion/watcher.py` (230 lines)
- [x] `Programma_CS2_RENAN/ingestion/__init__.py` (empty)
- [x] `Programma_CS2_RENAN/ingestion/steam_locator.py` (136 lines)
- [x] `Programma_CS2_RENAN/ingestion/demo_loader.py` (557 lines)
- [x] `Programma_CS2_RENAN/ingestion/integrity.py` (54 lines)
- [x] `Programma_CS2_RENAN/hltv_sync_service.py` (202 lines)
- [x] `Programma_CS2_RENAN/backend/storage/db_migrate.py` (113 lines)

**Total lines audited: ~7,484**
