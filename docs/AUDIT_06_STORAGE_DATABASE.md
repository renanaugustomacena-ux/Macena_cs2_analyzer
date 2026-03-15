# Audit Report 06 — Storage & Database

**Scope:** `backend/storage/`, `schema.py`, Alembic — 30 files, ~4,890 lines | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 2 CRITICAL | 1 HIGH (arch debt) | 15 MEDIUM | 10 LOW

---

## CRITICAL Findings

| ID | File | Finding |
|---|---|---|
| S-48 | schema.py:182-205 | **[FIXED 2026-03-13]** `_transfer_table()` now has INSERT OR IGNORE logic to actually transfer rows. |
| S-49 | schema.py:228-243 | **[FIXED 2026-03-13]** `run_fix("sequences")` now backs up to `_sqlite_sequence_backup` table before DELETE. |

## HIGH — Acknowledged Debt

| ID | File | Finding |
|---|---|---|
| S-28 | backup_manager.py + db_backup.py | Dual backup systems (VACUUM INTO vs Online Backup API). Both serve distinct triggers (startup vs migration). Intentional design — tracked as architectural debt. |

## MEDIUM Findings

| ID | File | Finding |
|---|---|---|
| S-05 | database.py | `_reconcile_stale_schema()` drops/recreates HLTV tables aggressively — data loss risk |
| S-08 | db_models.py | `Ext_PlayerPlaystyle` conflates playstyle stats with user account metadata |
| S-09 | db_models.py | Rating upper bound 5.0 may be too restrictive for outlier matches |
| S-10 | db_models.py | Dangling FK `fk_pro_player_stats` to proplayer (now in separate HLTV DB) |
| S-11 | db_models.py | Field comments use question marks — uncertain semantics (tapd, oap, podt) |
| S-14 | db_models.py | `CoachState.status` stored as plain string — no constraint on valid values |
| S-15 | storage_manager.py | `list_new_demos()` loads ALL paths into Python sets — O(n) memory |
| S-18 | match_data_manager.py | `delete_match()` engine cleanup not under `_engine_lock` |
| S-19 | match_data_manager.py | `get_match_session()` no `expire_all()` after rollback |
| S-29 | backup_manager.py | Label variable shadowing in `create_checkpoint()` |
| S-34 | maintenance.py | `prune_old_metadata()` loads all qualifying demo names without LIMIT |
| S-35 | maintenance.py | Partial pruning: earlier chunks may be flushed, later failure leaves inconsistent state |
| S-50 | remote_file_server.py:120 | Deprecated `@app.on_event("startup")` pattern — FastAPI deprecation since 0.93.0 |
| S-51 | remote_file_server.py:42-63 | `_rate_limiter._hits` dict grows unboundedly — IP strings never evicted. Memory leak over long-running server. |
| S-52 | schema.py:216-224 | **[FIXED 2026-03-13]** Removed `run_fix("knowledge")` block — coachstate migration already handled by `_apply_column_migration()` on database.db. |

## LOW Findings

| ID | File | Finding |
|---|---|---|
| S-02 | database.py | Deprecated `engine_key` parameter still in signature |
| S-04 | database.py | SELECT + INSERT upsert (2 round-trips) instead of ON CONFLICT |
| S-06 | database.py | Unnecessary double-quoting with regex-validated identifiers |
| S-12 | db_models.py | `last_upload_month` monthly quota reset not automated |
| S-16 | storage_manager.py | Path traversal check blocks legitimate subdirectory paths |
| S-21 | match_data_manager.py | GIL-dependent double-checked locking in singleton factory |
| S-23 | match_data_manager.py | Variable `logger` should be `_logger` at line 277 |
| S-40 | db_migrate.py | `ensure_database_current()` creates separate engine vs singleton |
| S-53 | schema.py | Uses `print()` throughout (31+ occurrences) instead of structured logging |
| S-54 | rag_knowledge.py:326-334 | `_update_usage_counts` updates records one-at-a-time instead of bulk `UPDATE ... WHERE id IN (...)` |

## Cross-Cutting

1. **Session Auto-Commit Contract** — `get_session()` auto-commits; contract now well-documented. Some callers may still explicitly commit redundantly.
2. **Migration Chain vs Architecture** — Chain written for monolith-only; HLTV split means some migrations are architecturally incorrect for new installs.
3. **JSON Field Size Governance** — `parameters_json` (CalibrationSnapshot) and `embedding` fields have no size cap.
4. **schema.py Completeness** — `_transfer_table()` is incomplete (no actual data transfer). The CLI tool misleads users about import success.

## Resolved Since 2026-03-10

Removed 6 MEDIUM findings (S-01, 03, 24, 25, 31, 33) and 3 migration findings (S-37, 42, 43, 45, 46, 47 — consolidated into cross-cutting note) — fixed in commits fcf5a99..f1e921f. Key fixes: WAL mode documented, auto-commit contract clarified, read-only get_state(), exceptions logged not swallowed, PRAGMA quick_check instead of full, integrity verified before restore.
