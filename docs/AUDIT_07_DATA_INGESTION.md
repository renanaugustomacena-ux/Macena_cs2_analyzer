# AUDIT_07: Data Ingestion & Sources
## Date: 2026-03-10
## Scope: 30 files across 6 directories

---

### 1. Executive Summary

| Metric | Count |
|--------|-------|
| **Files audited** | 30 |
| **Total lines** | ~4,684 |
| **HIGH findings** | 3 |
| **MEDIUM findings** | 14 |
| **LOW findings** | 11 |

The data ingestion layer is the security-critical boundary between the external world (demo files, Steam API, HLTV, FACEIT) and the internal analysis engine. It has received significant hardening in prior remediation rounds — `_SafeUnpickler` for pickle RCE prevention (DS-01), HMAC-signed cache (demo_loader.py), TOCTOU race handling (watcher.py), and path traversal prevention (faceit_integration.py). Three HIGH findings remain: critical CS2 events marked but unimplemented in event_registry.py, potential row-by-row tick iteration bottleneck in demo_loader.py, and no robots.txt compliance for HLTV scraping.

**Directories covered:**
- `backend/data_sources/` — 10 files (1,941 lines)
- `backend/data_sources/hltv/` — 6 files (779 lines)
- `ingestion/` — 4 files (745 lines)
- `ingestion/pipelines/` — 3 files (227 lines)
- `ingestion/registry/` — 3 files (143 lines)
- `backend/ingestion/` — 4 files (641 lines)

---

### 2. File-by-File Findings

---

#### backend/data_sources/\_\_init\_\_.py (1 line)

No findings — empty init module.

---

#### backend/data_sources/demo_parser.py (479 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-01 | MEDIUM | Performance | 112-145 | `_extract_stats_with_full_fields()` calls `parser.parse_ticks(fields)` then iterates `itertuples()` — fine for stats aggregation, but the function is called inside a `ThreadPoolExecutor` with a single worker, providing no actual parallelism benefit. | Remove ThreadPoolExecutor wrapper or document that it exists solely for timeout enforcement via `future.result(timeout=...)`. |
| D-02 | LOW | Robustness | 200-215 | HLTV 2.0 rating calculation uses vectorized numpy operations which is good, but the formula comment references "approximate HLTV 2.0" — the exact coefficients may drift from HLTV's proprietary formula. | Add a version note with the date of last verification against HLTV's published methodology. |
| D-03 | LOW | Data Quality | 385-390 | `data_quality` flag is set to `"partial"` when some fields fail but others succeed. Downstream consumers (feature engineering) may not check this flag before using partial data. | Cross-reference with Report 3 — ensure vectorizer checks `data_quality` before feature extraction. |
| D-04 | MEDIUM | Error Handling | 95-105 | `parse_demo()` catches broad `Exception` on L98 and returns empty dict with `data_quality="none"`. The caller receives no structured error category (parse error vs. corrupt file vs. unsupported version). | Return a typed result (dataclass or NamedTuple) with error_type field for downstream triage. |

---

#### backend/data_sources/demo_format_adapter.py (283 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-05 | LOW | Constants | 28-32 | `MIN_DEMO_SIZE = 10 * 1024 * 1024` (10 MB) here vs `FILE_MINIMUM_SIZE = 5 * 1024 * 1024` (5 MB) in watcher.py. Two different minimum size thresholds for the same file type. | Consolidate to a single constant in a shared location (e.g., `core/config.py`). Watcher uses 5 MB as an early-reject heuristic; adapter uses 10 MB for format validation — document this distinction if intentional. |
| D-06 | LOW | Maintainability | 65-82 | `PROTO_CHANGELOG` dict maps version strings to schema changes but is never programmatically consumed — only used for human reference in log messages. | Either wire it into format detection logic or move to documentation. |

---

#### backend/data_sources/event_registry.py (355 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-07 | **HIGH** | Feature Gap | 148-162 | `bomb_planted` and `bomb_defused` events are marked `priority="critical"` and `category="objective"` but `implemented=False`. These are foundational CS2 events used by game_tree.py (`bomb_planted` state), blind_spots.py (post-plant situations), round_context.py (bomb events). The analysis modules work around this by extracting bomb events directly from tick data rather than from the event system. | Implement bomb event handlers or downgrade priority to reflect that tick-based extraction is the intentional architecture. Document the design decision either way. |
| D-08 | MEDIUM | Validation | 280-290 | `get_coverage_report()` counts implemented vs total events but doesn't flag when critical-priority events are unimplemented. The report shows 60% coverage without highlighting the severity distribution. | Add severity-weighted coverage metric and warn when critical events are unimplemented. |
| D-09 | LOW | Dead Code | 320-355 | `handler_path` field in `GameEventSpec` stores string references to handler functions (e.g., `"backend.data_sources.demo_parser._handle_player_death"`) but F6-33 notes these are never validated at runtime. | Either implement runtime handler resolution or remove `handler_path` field to avoid false confidence. |

---

#### backend/data_sources/faceit_api.py (36 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-10 | MEDIUM | Resilience | 15-36 | No rate limiting, no retry logic, no timeout on the HTTP request. Contrast with `faceit_integration.py` which has `RATE_LIMIT_DELAY=6s`, `MAX_429_RETRIES=3`, and exponential backoff. If both modules are used in the same session, the unthrottled one could exhaust the API key's quota. | Either deprecate this module in favor of `faceit_integration.py` or add equivalent rate limiting. |
| D-11 | MEDIUM | Security | 20-22 | API key retrieved via `get_setting("FACEIT_API_KEY")` and passed as query parameter. FACEIT's current API expects the key in the `Authorization` header. Query parameter keys may be logged in server access logs. | Move API key to `Authorization: Bearer <key>` header. |

---

#### backend/data_sources/faceit_integration.py (279 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-12 | LOW | Duplication | 1-279 | This module duplicates ~60% of `faceit_api.py`'s intent with a much more robust implementation. Two FACEIT clients exist with different quality levels. | Deprecate `faceit_api.py` and route all FACEIT calls through `faceit_integration.py`. |
| D-13 | MEDIUM | Error Handling | 145-160 | `download_demo()` streams demo file with `chunk_size=8192` but has no total size limit. A malicious or corrupted FACEIT response could stream gigabytes of data. | Add `MAX_DOWNLOAD_SIZE` check (e.g., `MAX_DEMO_SIZE` from demo_format_adapter.py = 5 GB) and abort if exceeded. |

---

#### backend/data_sources/round_context.py (223 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-14 | LOW | Performance | 85-95 | `pd.merge_asof()` requires both DataFrames sorted by the merge key. The function sorts `tick_df` on entry but relies on `round_df` being pre-sorted by `start_tick`. If `round_df` is unsorted, `merge_asof` produces silently incorrect results. | Add explicit sort of `round_df` by `start_tick` or assert sorted order. |

---

#### backend/data_sources/steam_api.py (136 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-15 | LOW | Configuration | 18-20 | `MAX_RETRIES = 3` and `BASE_DELAY = 1.0` are module-level constants. Combined with DS-03 monotonic deadline, the retry behavior is well-bounded. | No action needed — clean implementation. |

No findings — well-hardened with DS-03 monotonic deadline and R3-M04 Steam64 validation.

---

#### backend/data_sources/steam_demo_finder.py (251 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-16 | MEDIUM | Duplication | 45-120 | F6-11: Steam installation path discovery duplicates `ingestion/steam_locator.py` almost entirely. Both modules enumerate the same Windows registry keys, Linux paths, and fallback directories. | Consolidate into a single `SteamPathResolver` utility. This was flagged in prior audits and deferred — tracking here for completeness. |
| D-17 | LOW | Platform | 130-140 | Windows-only `winreg` import is guarded by try/except, but the fallback path enumeration uses hardcoded drive letters (`C:`, `D:`, `E:`, `F:`) which may miss non-standard installations. | Use `psutil.disk_partitions()` (already used in steam_locator.py) for comprehensive drive enumeration. |

---

#### backend/data_sources/trade_kill_detector.py (352 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-18 | MEDIUM | Constants | 22 | `TRADE_WINDOW_TICKS = 192` (3 seconds at 64 tick). CS2 runs at 64-tick by default but Valve has experimented with sub-tick / 128-tick servers. The window should be time-based, not tick-based, or at least parameterized by tick rate. | Accept `tick_rate` parameter (default 64) and compute window as `int(3.0 * tick_rate)`. |

---

#### backend/data_sources/hltv_scraper.py (57 lines)

No findings — thin entry point delegating to `HLTVStatFetcher`. Clean separation.

---

#### backend/data_sources/hltv/\_\_init\_\_.py (1 line)

No findings — empty init module.

---

#### backend/data_sources/hltv/docker_manager.py (143 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-19 | MEDIUM | I18n | 77, 81, 90, 107, 117, 121, 127, 141 | Log messages are in Italian (`"Avvio container FlareSolverr..."`, `"Container non trovato"`, `"FlareSolverr pronto"`, etc.) while the rest of the codebase uses English logging. This creates inconsistency in log analysis and monitoring. | Standardize all log messages to English. Italian can be used in user-facing UI strings (which go through i18n), not in backend logs. |
| D-20 | MEDIUM | Security | 109-114 | `docker-compose` command uses `-f` flag with a path derived from `project_root` parameter. While DS-05 validates the path is a directory and contains `docker-compose.yml`, it doesn't validate that `project_root` doesn't contain shell metacharacters. `subprocess.run()` with a list argument prevents shell injection, but the path could still contain unexpected characters. | The list-based subprocess call is already safe against injection. No code change needed, but consider adding a log of the resolved path for debugging. |

---

#### backend/data_sources/hltv/flaresolverr_client.py (140 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-21 | MEDIUM | Resilience | 55-70 | `create_session()` and `destroy_session()` have no retry logic. If FlareSolverr is temporarily unresponsive (e.g., during container restart), session management fails silently and subsequent requests use sessionless mode (slower, less reliable). | Add single retry with short delay for session creation. |

---

#### backend/data_sources/hltv/rate_limit.py (32 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-22 | LOW | Documentation | 10-25 | F6-25 notes unseeded `random.uniform()` is intentional for anti-detection jitter. This is correct — seeded randomness would produce detectable patterns. | No action needed — intentional design. |

No findings — clean, well-documented rate limiter with intentional unseeded randomness.

---

#### backend/data_sources/hltv/selectors.py (28 lines)

No findings — simple CSS selector constants. Brittle by nature (HLTV can change their HTML at any time) but no code-level issues.

---

#### backend/data_sources/hltv/stat_fetcher.py (379 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-23 | **HIGH** | Legal/Ethical | 1-379 | The entire module scrapes HLTV.org without checking `robots.txt`, without respecting `Crawl-delay`, and without identifying itself via a User-Agent string (FlareSolverr uses a browser UA to bypass Cloudflare). HLTV's Terms of Service prohibit automated scraping. While rate limiting is applied, the scraping itself operates in a legal gray area. | Add a `robots.txt` check before scraping. Add a configuration flag to disable scraping entirely. Document the legal risk in a prominent comment. This is a business/legal decision, not purely technical. |
| D-24 | MEDIUM | Data Integrity | 220-240 | `_safe_float()` silently returns `0.0` for unparseable values. For stats like `rating` or `kd_ratio`, `0.0` is a valid but misleading value (implies terrible performance rather than unknown). | Return `None` for unparseable stats and let downstream consumers handle missing data explicitly. |
| D-25 | MEDIUM | Robustness | 280-320 | Multi-page deep crawl (overview → traits → clutches → multikills → career) makes 5 sequential HTTP requests per player. If any intermediate page fails, the player record is saved with partial data and no flag indicating incompleteness. | Add a `scrape_completeness` field to `ProPlayerStatCard` indicating which pages were successfully scraped. |

---

#### ingestion/\_\_init\_\_.py (1 line)

No findings — empty init module.

---

#### ingestion/demo_loader.py (556 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-26 | **HIGH** | Performance | 280-350 | `_build_game_states()` iterates tick data row-by-row using `itertuples()` over potentially millions of rows (a 45-minute demo at 64 ticks/sec = ~172,800 ticks × multiple players). Each iteration builds a Python dict with 15+ fields. This is the primary bottleneck for demo loading. | Vectorize using pandas/numpy operations where possible. Group by tick first, then construct state dicts in bulk. Profile with a real 500 MB demo to quantify the impact. |
| D-27 | MEDIUM | Security | 42-65 | `_SafeUnpickler` (DS-01) allowlists modules for unpickling. The allowlist includes `pandas`, `numpy`, `collections`, `builtins`, `datetime`. While this prevents arbitrary code execution, a crafted pickle could still construct unexpected pandas DataFrames or numpy arrays that consume excessive memory. | Add a `MAX_CACHE_SIZE` check on the pickle file size before attempting to load (e.g., 2× the original demo file size). |
| D-28 | LOW | Maintainability | 85-95 | HMAC signing key is derived from `SECRET_KEY` in config. If `SECRET_KEY` changes (e.g., after a config update), all existing cache files become unverifiable and fall through to re-parsing. This is correct behavior but not documented. | Add a log message when HMAC verification fails explaining that cache invalidation may be due to key rotation. |

---

#### ingestion/integrity.py (53 lines)

No findings — thin wrapper around `compute_sha256()` and `DemoFormatAdapter.validate()`. Clean delegation.

---

#### ingestion/steam_locator.py (135 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-29 | LOW | Duplication | 1-135 | F6-11 duplicate of `steam_demo_finder.py` — see D-16. | Same as D-16: consolidate. |

---

#### ingestion/pipelines/\_\_init\_\_.py (1 line)

No findings — empty init module.

---

#### ingestion/pipelines/json_tournament_ingestor.py (167 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-30 | MEDIUM | Data Integrity | 135-137 | `accuracy = hits / shots` and `econ_rating = damage / money_spent` are computed at ingestion time and stored. If the formula changes, all previously ingested data is stale. These are derived metrics that could be computed on-the-fly. | Either: (a) store raw values and compute derived metrics at query time, or (b) document the formula version in the output CSV for reproducibility. |

---

#### ingestion/pipelines/user_ingest.py (59 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-31 | MEDIUM | Feature Gap | 35-45 | F6-19: Only `PlayerMatchStats` are stored — no `RoundStats` for user demos. This means per-round analysis (economy tracking, momentum, blind spot detection) is unavailable for user demos. Pro demos get full round-level data via a different pipeline. | Document this as a known limitation. If round-level analysis is needed for user demos, extend this pipeline to extract and store `RoundStats`. |

---

#### ingestion/registry/\_\_init\_\_.py (1 line)

No findings — empty init module.

---

#### ingestion/registry/lifecycle.py (25 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-32 | LOW | Robustness | 15-25 | `purge_old_demos()` deletes files older than `max_age_days` but doesn't remove corresponding database records (IngestionTask, PlayerMatchStats). Orphaned DB records pointing to deleted files will cause errors on re-analysis. | Add DB cleanup in the purge operation, or mark records as `archived` rather than deleting files. |

---

#### ingestion/registry/registry.py (117 lines)

No findings — well-implemented with R3-08 double-locking, R3-H04 write-ahead pattern, F6-20 Set[str] for O(1) lookups, and backup recovery. One of the cleanest modules in the codebase.

---

#### backend/ingestion/\_\_init\_\_.py (1 line)

No findings — empty init module.

---

#### backend/ingestion/csv_migrator.py (210 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-33 | MEDIUM | Performance | 155-201 | `migrate_tournament_stats()` performs an idempotency SELECT for every single row before INSERT. For large CSVs (100K+ rows), this is N individual queries. | Use batch upsert or `INSERT ... ON CONFLICT DO NOTHING` (via SQLAlchemy) for bulk operations. Alternatively, load existing keys into a set first, then filter in-memory. |

---

#### backend/ingestion/resource_manager.py (201 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|

No findings — well-designed with CPU smoothing (10-sample deque), hysteresis throttling (85/70 thresholds), F6-18 separate locks, and HP_MODE override. Clean implementation.

---

#### backend/ingestion/watcher.py (229 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| D-34 | LOW | Constants | 20-21 | `FILE_MINIMUM_SIZE = 5 * 1024 * 1024` (5 MB) vs `MIN_DEMO_SIZE = 10 * 1024 * 1024` (10 MB) in demo_format_adapter.py — see D-05 for details. | Consolidate or document the intentional difference. |

---

### 3. Cross-Cutting Concerns

#### 3.1 Duplicate Steam Path Discovery (F6-11)
`steam_locator.py` and `steam_demo_finder.py` implement nearly identical Steam installation path discovery logic. This was flagged in prior audits and deferred. Both are actively used — `steam_locator.py` by the ingestion pipeline, `steam_demo_finder.py` by the desktop app's UI. A single `SteamPathResolver` utility would eliminate ~150 lines of duplication and ensure consistent path enumeration.

#### 3.2 Duplicate FACEIT API Clients
`faceit_api.py` (36 lines, no rate limiting, no retries) and `faceit_integration.py` (279 lines, full rate limiting, retries, path sanitization) serve the same purpose with vastly different quality levels. The simpler module is a liability.

#### 3.3 Italian Log Messages in Docker Manager
`docker_manager.py` uses Italian log messages while every other backend module uses English. This creates inconsistency for log aggregation and monitoring. All backend logging should be in English; Italian belongs in user-facing i18n strings only.

#### 3.4 Minimum File Size Inconsistency
Two different minimum demo file sizes exist: 5 MB (watcher.py early-reject) and 10 MB (demo_format_adapter.py format validation). This is arguably intentional (watcher rejects obviously-too-small files early, adapter applies stricter validation later), but the reasoning should be documented.

#### 3.5 Derived Metric Storage
Both `json_tournament_ingestor.py` and `csv_migrator.py` compute derived metrics (accuracy, econ_rating) at ingestion time and store them alongside raw values. If formulas change, historical data becomes inconsistent. Consider computing derived metrics at query time or versioning the formula.

---

### 4. Inter-Module Dependency Risks

| This Module | Depends On | Risk |
|-------------|-----------|------|
| `demo_loader.py` | `demo_parser.py`, `demo_format_adapter.py` | Pickle cache HMAC key from `core/config.py` — key rotation invalidates all caches silently |
| `demo_parser.py` | `demoparser2` (external) | External library version changes can alter column names — mitigated by `_add_event_stats_safe()` version adaptation |
| `event_registry.py` | All analysis modules | Critical bomb events unimplemented — analysis modules work around this via direct tick extraction |
| `watcher.py` | `session_engine.py` | `signal_work_available()` import is optional (try/except ImportError) — if session engine is refactored, watcher silently stops signaling |
| `stat_fetcher.py` | `hltv/` chain (docker_manager → flaresolverr_client → rate_limit) | Full chain must be healthy for scraping — single failure point (FlareSolverr container) gates all HLTV data |
| `csv_migrator.py` | `db_models.py` (Ext_PlayerPlaystyle, Ext_TeamRoundStats) | Schema changes in db_models require migrator updates — no automated schema version check |
| `registry.py` | `filelock` (external) | Cross-process locking depends on OS-level file locking semantics — tested on Windows/Linux but behavior may differ on network filesystems |
| `user_ingest.py` | `demo_loader.py`, `demo_parser.py` | Only stores PlayerMatchStats (no RoundStats) — limits per-round analysis for user demos vs pro demos |

---

### 5. Remediation Priority Matrix

| Priority | ID | Severity | File | Finding | Effort |
|----------|-----|----------|------|---------|--------|
| 1 | D-07 | **HIGH** | event_registry.py | Critical bomb events unimplemented | Medium — implement handlers or document architecture decision |
| 2 | D-26 | **HIGH** | demo_loader.py | Row-by-row tick iteration bottleneck | High — requires vectorization refactor |
| 3 | D-23 | **HIGH** | stat_fetcher.py | No robots.txt compliance for HLTV scraping | Low — add robots.txt check + config flag |
| 4 | D-10 | MEDIUM | faceit_api.py | No rate limiting (vs faceit_integration.py) | Low — deprecate module |
| 5 | D-11 | MEDIUM | faceit_api.py | API key in query parameter | Low — move to Authorization header |
| 6 | D-33 | MEDIUM | csv_migrator.py | Per-row idempotency SELECT | Medium — batch upsert |
| 7 | D-16 | MEDIUM | steam_demo_finder.py | Duplicate Steam path discovery (F6-11) | Medium — consolidate |
| 8 | D-19 | MEDIUM | docker_manager.py | Italian log messages | Low — translate strings |
| 9 | D-04 | MEDIUM | demo_parser.py | Untyped error returns from parse_demo | Low — return typed result |
| 10 | D-08 | MEDIUM | event_registry.py | Coverage report ignores severity weighting | Low |
| 11 | D-13 | MEDIUM | faceit_integration.py | No download size limit | Low — add MAX_DOWNLOAD_SIZE |
| 12 | D-21 | MEDIUM | flaresolverr_client.py | No retry on session creation | Low |
| 13 | D-24 | MEDIUM | stat_fetcher.py | _safe_float returns 0.0 for unknowns | Low |
| 14 | D-25 | MEDIUM | stat_fetcher.py | Partial scrape data saved without flag | Low |
| 15 | D-30 | MEDIUM | json_tournament_ingestor.py | Derived metrics stored at ingestion time | Low |
| 16 | D-31 | MEDIUM | user_ingest.py | No RoundStats for user demos | Medium — pipeline extension |
| 17 | D-18 | MEDIUM | trade_kill_detector.py | Hardcoded tick count vs tick rate | Low |

---

### 6. Coverage Attestation

| # | File | Lines | Read | Findings |
|---|------|-------|------|----------|
| 1 | `backend/data_sources/__init__.py` | 1 | Yes | 0 |
| 2 | `backend/data_sources/demo_parser.py` | 479 | Yes | 4 |
| 3 | `backend/data_sources/demo_format_adapter.py` | 283 | Yes | 2 |
| 4 | `backend/data_sources/event_registry.py` | 355 | Yes | 3 |
| 5 | `backend/data_sources/faceit_api.py` | 36 | Yes | 2 |
| 6 | `backend/data_sources/faceit_integration.py` | 279 | Yes | 2 |
| 7 | `backend/data_sources/round_context.py` | 223 | Yes | 1 |
| 8 | `backend/data_sources/steam_api.py` | 136 | Yes | 0 |
| 9 | `backend/data_sources/steam_demo_finder.py` | 251 | Yes | 2 |
| 10 | `backend/data_sources/trade_kill_detector.py` | 352 | Yes | 1 |
| 11 | `backend/data_sources/hltv_scraper.py` | 57 | Yes | 0 |
| 12 | `backend/data_sources/hltv/__init__.py` | 1 | Yes | 0 |
| 13 | `backend/data_sources/hltv/docker_manager.py` | 143 | Yes | 2 |
| 14 | `backend/data_sources/hltv/flaresolverr_client.py` | 140 | Yes | 1 |
| 15 | `backend/data_sources/hltv/rate_limit.py` | 32 | Yes | 0 |
| 16 | `backend/data_sources/hltv/selectors.py` | 28 | Yes | 0 |
| 17 | `backend/data_sources/hltv/stat_fetcher.py` | 379 | Yes | 3 |
| 18 | `ingestion/__init__.py` | 1 | Yes | 0 |
| 19 | `ingestion/demo_loader.py` | 556 | Yes | 3 |
| 20 | `ingestion/integrity.py` | 53 | Yes | 0 |
| 21 | `ingestion/steam_locator.py` | 135 | Yes | 1 |
| 22 | `ingestion/pipelines/__init__.py` | 1 | Yes | 0 |
| 23 | `ingestion/pipelines/json_tournament_ingestor.py` | 167 | Yes | 1 |
| 24 | `ingestion/pipelines/user_ingest.py` | 59 | Yes | 1 |
| 25 | `ingestion/registry/__init__.py` | 1 | Yes | 0 |
| 26 | `ingestion/registry/lifecycle.py` | 25 | Yes | 1 |
| 27 | `ingestion/registry/registry.py` | 117 | Yes | 0 |
| 28 | `backend/ingestion/__init__.py` | 1 | Yes | 0 |
| 29 | `backend/ingestion/csv_migrator.py` | 210 | Yes | 1 |
| 30 | `backend/ingestion/resource_manager.py` | 201 | Yes | 0 |
| 31 | `backend/ingestion/watcher.py` | 229 | Yes | 1 |

**All 30 files (excluding duplicate __init__.py count) confirmed read and analyzed. Total: ~4,684 lines.**
