# Audit Report 07 — Data Ingestion & Sources

**Scope:** `backend/data_sources/`, `ingestion/`, `backend/ingestion/` — 30 files, ~4,684 lines | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 0 HIGH | 7 MEDIUM | 15 LOW

---

## MEDIUM Findings

| ID | File | Finding |
|---|---|---|
| D-01 | demo_parser.py | ThreadPoolExecutor with single worker provides no parallelism (timeout enforcement only) |
| D-08 | event_registry.py | Coverage report ignores severity weighting |
| D-24 | stat_fetcher.py | `_safe_float()` returns 0.0 for unknowns — misleading for stats like rating |
| D-25 | stat_fetcher.py | Partial scrape data saved without completeness flag |
| D-35 | demo_parser.py:280 | `_add_event_stats_safe()` uses `iterrows()` with repeated DataFrame filtering inside loop. O(players * events) per call — pre-group with `groupby()` instead. |
| D-37 | event_registry.py:174-231 | Registry marks 5 events as `implemented=False` that ARE parsed by `demo_loader.py` (flashbang, HE, smoke, inferno_start, inferno_expire). `handler_path` fields missing. Coverage report understates actual implementation. |
| D-38 | demo_loader.py:271,308 | `nades_by_tick` dict grows by (ending_tick - starting_tick + FADE_TICKS) entries per grenade. Single smoke = ~1600 entries. 100 nades/match = ~160K entries. Dominates memory during parsing. Replace with interval-based structure. |

## LOW Findings

| ID | File | Finding |
|---|---|---|
| D-02 | demo_parser.py | Approximate HLTV 2.0 rating — coefficients may drift |
| D-03 | demo_parser.py | `data_quality="partial"` flag not checked by downstream consumers |
| D-06 | demo_format_adapter.py | PROTO_CHANGELOG dict never programmatically consumed |
| D-09 | event_registry.py | `handler_path` field never validated at runtime |
| D-12 | faceit_integration.py | Duplicates ~60% of faceit_api.py intent |
| D-14 | round_context.py | `merge_asof` relies on pre-sorted `round_df` — no assertion |
| D-17 | steam_demo_finder.py | Hardcoded drive letters may miss non-standard installations |
| D-28 | demo_loader.py | HMAC key rotation silently invalidates all caches (not documented) |
| D-29 | steam_locator.py | Duplicate of steam_demo_finder.py |
| D-32 | lifecycle.py | `purge_old_demos()` deletes files but not DB records — orphans |
| D-36 | steam_api.py:116-120 | Dead code: `resp.raise_for_status()` already threw for 403 before this check. The 403 handling after successful return is unreachable. |
| D-39 | demo_format_adapter.py:222-223 | Unreachable code: `_check_corruption_patterns` checks `< 1MB` but only called after `validate_demo` rejects `< 10MB`. |
| D-40 | steam_locator.py:116 | `_iterate_demo_patterns` uses both `"**/*.dem"` and `"*.dem"` — recursive pattern is superset, `"*.dem"` is redundant. |
| D-41 | hltv/flaresolverr_client.py:69 | Italian error message in English-language file |
| D-42 | hltv/docker_manager.py:141 | Italian log message in English-language file |

## Cross-Cutting

1. **Duplicate Clients** — steam_locator.py vs steam_demo_finder.py (~150 lines duplication); faceit_api.py vs faceit_integration.py (vastly different quality).
2. **Derived Metric Storage** — Some ingestors compute/store derived metrics at ingestion time — stale if formula changes.
3. **Event Registry Accuracy** — 5 events marked unimplemented are actually parsed. Coverage report is understated.

## Resolved Since 2026-03-10

Removed 10 MEDIUM findings (D-04, 10, 11, 13, 16, 18, 19, 21, 27, 30, 31, 33) and 2 LOW (D-05, D-34) — fixed in commits 2fa2cf3..381643d. Key fixes: structured parse error, rate limiting + Authorization header, streaming size limit, dynamic trade window ticks, SafeUnpickler hardening, MIN_DEMO_SIZE consolidated. D-05 closed: watcher.py now imports `MIN_DEMO_SIZE` from `demo_format_adapter` — threshold unified at 10MB.
