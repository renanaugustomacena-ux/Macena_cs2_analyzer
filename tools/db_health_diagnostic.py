"""
Comprehensive Database Health Diagnostic Script
Maps to user-provided 13-pillar framework.
"""

import os
import re
import sqlite3
import sys

# --- Venv Guard ---
if sys.prefix == sys.base_prefix and not os.environ.get("CI"):
    print("ERROR: Not in venv. Run: source ~/.venvs/cs2analyzer/bin/activate", file=sys.stderr)
    sys.exit(2)

STORAGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Programma_CS2_RENAN",
    "backend",
    "storage",
)

MAIN_DB = os.path.join(STORAGE_DIR, "database.db")
HLTV_DB = os.path.join(STORAGE_DIR, "hltv_metadata.db")
KNOWLEDGE_DB = os.path.join(STORAGE_DIR, "..", "..", "data", "knowledge_base.db")
try:
    from Programma_CS2_RENAN.core.config import MATCH_DATA_PATH

    MATCH_DATA_DIR = MATCH_DATA_PATH
except ImportError:
    MATCH_DATA_DIR = os.path.join(STORAGE_DIR, "match_data")


_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _safe_table_name(name: str) -> str:
    """Validate and return a safe table name for SQL interpolation.

    SQLite PRAGMAs and some queries require table names inline (cannot use
    parameterized queries for identifiers). This guard prevents injection.
    """
    if not _TABLE_NAME_RE.match(name):
        raise ValueError(f"Unsafe table name rejected: {name!r}")
    return name


def run_query(db_path: str, sql: str, label: str = "") -> list[dict]:
    """Execute a query and return results. Returns empty list on error."""
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"  WARNING: Query failed [{label or sql[:60]}]: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_file_size_mb(path: str) -> float:
    """Return file size in MB, or -1.0 if file cannot be read."""
    try:
        return round(os.path.getsize(path) / 1024 / 1024, 2)
    except OSError as e:
        print(f"  WARNING: Cannot read size of {path}: {e}")
        return -1.0


def main():
    """Run all 10 diagnostic sections."""
    # ===========================================================================
    # SECTION 1: STRUCTURAL HEALTH (Schema & Constraints)
    # ===========================================================================
    print("=" * 70)
    print("SECTION 1: STRUCTURAL HEALTH — Schema & Constraints")
    print("=" * 70)

    # List all tables
    tables = run_query(MAIN_DB, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = [t["name"] for t in tables if isinstance(t, dict)]
    print(f"\n[1.1] Tables in main DB: {len(table_names)}")
    for t in table_names:
        print(f"   • {t}")

    # Get table info for each table
    schema_info = {}
    for tname in table_names:
        if tname.startswith("alembic") or tname.startswith("sqlite"):
            continue
        safe = _safe_table_name(tname)
        cols = run_query(MAIN_DB, f"PRAGMA table_info('{safe}')")
        fks = run_query(MAIN_DB, f"PRAGMA foreign_key_list('{safe}')")
        indexes = run_query(MAIN_DB, f"PRAGMA index_list('{safe}')")
        row_count = run_query(MAIN_DB, f"SELECT COUNT(*) as cnt FROM '{safe}'")

        count = row_count[0]["cnt"] if row_count else "error"

        schema_info[tname] = {
            "columns": len(cols),
            "foreign_keys": len(fks),
            "indexes": len(indexes),
            "row_count": count,
            "fk_details": fks,
            "col_details": cols,
        }

        # Check for PRIMARY KEY presence
        has_pk = any(c.get("pk", 0) > 0 for c in cols)

        print(f"\n   [{tname}]")
        print(
            f"      Columns: {schema_info[tname]['columns']}  |  Rows: {count}  |  Indexes: {schema_info[tname]['indexes']}  |  FKs: {schema_info[tname]['foreign_keys']}  |  Has PK: {has_pk}"
        )

    # ===========================================================================
    # SECTION 2: INTEGRITY CHECK (Corruption Detection)
    # ===========================================================================
    print("\n" + "=" * 70)
    print("SECTION 2: INTEGRITY CHECK — Corruption Detection")
    print("=" * 70)

    for db_label, db_path in [("MAIN", MAIN_DB), ("HLTV", HLTV_DB)]:
        if not os.path.exists(db_path):
            print(f"\n   [{db_label}] FILE NOT FOUND: {db_path}")
            continue
        result = run_query(db_path, "PRAGMA integrity_check")
        status = result[0].get("integrity_check", "UNKNOWN") if result else "ERROR"
        size = get_file_size_mb(db_path)
        print(f"\n   [{db_label}] Integrity: {status}  |  Size: {size} MB")

    # Check WAL file sizes
    for db_label, db_path in [("MAIN", MAIN_DB), ("HLTV", HLTV_DB)]:
        wal_path = db_path + "-wal"
        shm_path = db_path + "-shm"
        wal_size = get_file_size_mb(wal_path) if os.path.exists(wal_path) else 0
        shm_size = get_file_size_mb(shm_path) if os.path.exists(shm_path) else 0
        print(f"   [{db_label}] WAL: {wal_size} MB  |  SHM: {shm_size} MB")

    # Per-match DB integrity spot check (first 3)
    if os.path.exists(MATCH_DATA_DIR):
        match_files = [f for f in os.listdir(MATCH_DATA_DIR) if f.endswith(".db")]
        print(f"\n   [MATCH DBs] Total files: {len(match_files)}")

        total_match_storage = 0
        for mf in match_files:
            total_match_storage += get_file_size_mb(os.path.join(MATCH_DATA_DIR, mf))
        print(f"   [MATCH DBs] Total storage: {total_match_storage:.2f} MB")

        # TQ-RT03-01: Check all match DBs, not just first 3
        for mf in match_files:
            mpath = os.path.join(MATCH_DATA_DIR, mf)
            result = run_query(mpath, "PRAGMA integrity_check")
            status = result[0].get("integrity_check", "UNKNOWN") if result else "ERROR"
            size = get_file_size_mb(mpath)
            tick_count = run_query(mpath, "SELECT COUNT(*) as cnt FROM match_tick_state")
            ticks = tick_count[0]["cnt"] if tick_count else "N/A"
            print(f"   [{mf}] Integrity: {status}  |  Size: {size} MB  |  Ticks: {ticks}")

    # ===========================================================================
    # SECTION 3: WAL & JOURNAL MODE VERIFICATION
    # ===========================================================================
    print("\n" + "=" * 70)
    print("SECTION 3: WAL & JOURNAL MODE VERIFICATION")
    print("=" * 70)

    for db_label, db_path in [("MAIN", MAIN_DB), ("HLTV", HLTV_DB)]:
        if not os.path.exists(db_path):
            continue
        journal = run_query(db_path, "PRAGMA journal_mode")
        sync = run_query(db_path, "PRAGMA synchronous")
        busy = run_query(db_path, "PRAGMA busy_timeout")
        j_mode = journal[0].get("journal_mode", "?") if journal else "?"
        s_mode = sync[0].get("synchronous", "?") if sync else "?"
        b_val = busy[0].get("busy_timeout", "?") if busy else "?"
        print(
            f"\n   [{db_label}] journal_mode: {j_mode}  |  synchronous: {s_mode}  |  busy_timeout: {b_val}"
        )

    # ===========================================================================
    # SECTION 4: DATA CONSISTENCY & LOGICAL STABILITY
    # ===========================================================================
    print("\n" + "=" * 70)
    print("SECTION 4: DATA CONSISTENCY & LOGICAL STABILITY")
    print("=" * 70)

    # 4.1 Check for duplicate (demo_name, player_name) in PlayerMatchStats
    # Multiple rows per demo_name is expected (one per player), so GROUP BY
    # both columns to detect actual duplicates.
    dupes = run_query(
        MAIN_DB,
        """
        SELECT demo_name, player_name, COUNT(*) as cnt
        FROM playermatchstats
        GROUP BY demo_name, player_name
        HAVING COUNT(*) > 1
        LIMIT 10
    """,
    )
    print(f"\n   [4.1] Duplicate (demo, player) in PlayerMatchStats: {len(dupes)} found")
    for d in dupes[:5]:
        print(
            f"      demo: {d.get('demo_name','?')} player: {d.get('player_name','?')} -> {d.get('cnt','?')} rows"
        )

    # 4.2 Check for orphan PlayerTickState (match_id not in MatchResult)
    orphan_check = run_query(
        MAIN_DB,
        """
        SELECT COUNT(*) as cnt FROM playertickstate
        WHERE match_id NOT IN (SELECT match_id FROM matchresult)
        AND match_id != 0
    """,
    )
    if orphan_check:
        print(
            f"   [4.2] Orphan PlayerTickState rows (FK violation): {orphan_check[0].get('cnt', '?')}"
        )

    # 4.3 Check for NULL or negative values where they shouldn't be
    neg_checks = [
        (
            "PlayerMatchStats — negative avg_kills",
            "SELECT COUNT(*) as cnt FROM playermatchstats WHERE avg_kills < 0",
        ),
        (
            "PlayerMatchStats — negative avg_adr",
            "SELECT COUNT(*) as cnt FROM playermatchstats WHERE avg_adr < 0",
        ),
        (
            "PlayerMatchStats — kd_ratio < 0",
            "SELECT COUNT(*) as cnt FROM playermatchstats WHERE kd_ratio < 0",
        ),
        (
            "PlayerMatchStats — rating out of range",
            "SELECT COUNT(*) as cnt FROM playermatchstats WHERE rating < 0 OR rating > 5",
        ),
        (
            "IngestionTask — invalid status",
            "SELECT COUNT(*) as cnt FROM ingestiontask WHERE status NOT IN ('queued','processing','complete','failed','cancelled')",
        ),
    ]

    print(f"\n   [4.3] Impossible value checks:")
    for label, sql in neg_checks:
        result = run_query(MAIN_DB, sql)
        val = result[0]["cnt"] if result else "error"
        flag = "[WARN]" if (isinstance(val, int) and val > 0) else "[OK]"
        print(f"      {flag} {label}: {val}")

    # 4.4 Check dataset_split distribution
    split_dist = run_query(
        MAIN_DB,
        """
        SELECT dataset_split, COUNT(*) as cnt
        FROM playermatchstats
        GROUP BY dataset_split
    """,
    )
    if split_dist:
        print(f"\n   [4.4] Dataset split distribution:")
        for s in split_dist:
            print(f"      {s.get('dataset_split', '?')}: {s.get('cnt', 0)} rows")

    # 4.5 Pro vs non-pro distribution
    pro_dist = run_query(
        MAIN_DB,
        """
        SELECT is_pro, COUNT(*) as cnt
        FROM playermatchstats
        GROUP BY is_pro
    """,
    )
    if pro_dist:
        print(f"\n   [4.5] Pro vs Non-Pro distribution:")
        for s in pro_dist:
            print(f"      is_pro={s.get('is_pro', '?')}: {s.get('cnt', 0)} rows")

    # ===========================================================================
    # SECTION 5: INGESTION PIPELINE HEALTH
    # ===========================================================================
    print("\n" + "=" * 70)
    print("SECTION 5: INGESTION PIPELINE HEALTH")
    print("=" * 70)

    task_stats = run_query(
        MAIN_DB,
        """
        SELECT status, COUNT(*) as cnt, AVG(retry_count) as avg_retries
        FROM ingestiontask
        GROUP BY status
    """,
    )
    if task_stats:
        print(f"\n   [5.1] Ingestion task status distribution:")
        for t in task_stats:
            print(
                f"      {t.get('status','?')}: {t.get('cnt',0)} tasks  (avg retries: {t.get('avg_retries',0):.1f})"
            )

    # Check for stuck tasks (processing for too long)
    stuck = run_query(
        MAIN_DB,
        """
        SELECT id, demo_path, status, updated_at, retry_count
        FROM ingestiontask
        WHERE status = 'processing'
        LIMIT 10
    """,
    )
    if stuck:
        print(f"\n   [5.2] [WARN] Stuck tasks (status='processing'): {len(stuck)}")
        for s in stuck:
            print(
                f"      Task {s.get('id','?')}: {s.get('demo_path','?')} (retries: {s.get('retry_count',0)})"
            )
    else:
        print(f"\n   [5.2] [OK] No stuck ingestion tasks")

    # 5.3: Cross-DB consistency — match files vs main DB records
    if os.path.exists(MATCH_DATA_DIR):
        match_file_ids = set()
        for f in os.listdir(MATCH_DATA_DIR):
            if f.startswith("match_") and f.endswith(".db"):
                try:
                    match_file_ids.add(int(f[6:-3]))
                except ValueError:
                    pass

        main_match_ids = run_query(MAIN_DB, "SELECT match_id FROM matchresult")
        main_ids = set(r["match_id"] for r in main_match_ids)

        orphan_files = match_file_ids - main_ids
        missing_files = main_ids - match_file_ids

        print(f"\n   [5.3] Cross-DB consistency:")
        print(f"      Match files on disk:        {len(match_file_ids)}")
        print(f"      MatchResult rows in main:   {len(main_ids)}")
        print(
            f"      Orphan files (no main rec): {len(orphan_files)} {'[WARN]' if orphan_files else '[OK]'}"
        )
        print(
            f"      Missing files (main rec, no file): {len(missing_files)} {'[WARN]' if missing_files else '[OK]'}"
        )
        if orphan_files:
            print(f"      Orphan match IDs: {sorted(orphan_files)[:10]}")
        if missing_files:
            print(f"      Missing file match IDs: {sorted(missing_files)[:10]}")

    # ===========================================================================
    # SECTION 6: PERFORMANCE HEALTH — Query Plan Analysis
    # ===========================================================================
    print("\n" + "=" * 70)
    print("SECTION 6: PERFORMANCE HEALTH — Index Coverage")
    print("=" * 70)

    # List all indexes
    indexes = run_query(
        MAIN_DB, "SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY tbl_name"
    )
    if indexes:
        print(f"\n   [6.1] Total indexes in main DB: {len(indexes)}")
        # Group by table
        idx_by_table = {}
        for idx in indexes:
            tbl = idx.get("tbl_name", "?")
            idx_by_table.setdefault(tbl, []).append(idx.get("name", "?"))
        for tbl, idxs in sorted(idx_by_table.items()):
            print(f"      {tbl}: {len(idxs)} indexes")

    # Check EXPLAIN QUERY PLAN for critical queries
    print(f"\n   [6.2] Query plan analysis (critical queries):")
    critical_queries = [
        (
            "Player stats lookup by name",
            "SELECT * FROM playermatchstats WHERE player_name = 'test' LIMIT 1",
        ),
        ("IngestionTask by status", "SELECT * FROM ingestiontask WHERE status = 'queued' LIMIT 1"),
        ("CoachState latest", "SELECT * FROM coachstate ORDER BY last_updated DESC LIMIT 1"),
        ("ProPlayer by HLTV ID", "SELECT * FROM proplayer WHERE hltv_id = 12345"),
    ]
    for label, sql in critical_queries:
        plan = run_query(MAIN_DB, f"EXPLAIN QUERY PLAN {sql}")
        if plan:
            detail = plan[0].get("detail", "?")
            # Full table scan: "SCAN TABLE x" without "USING" (index-assisted scans include "USING INDEX")
            is_full_scan = bool(re.search(r"SCAN TABLE \w+(?! USING)", str(detail)))
            scan_warning = "[WARN] FULL SCAN" if is_full_scan else "[OK]"
            print(f"      {scan_warning} {label}: {detail}")

    # ===========================================================================
    # SECTION 7: OBSERVABILITY — Diagnostic Metadata Coverage
    # ===========================================================================
    print("\n" + "=" * 70)
    print("SECTION 7: OBSERVABILITY — Diagnostic Metadata Coverage")
    print("=" * 70)

    # Check which tables have timestamps
    metadata_tables = {}
    for tname, info in schema_info.items():
        timestamp_cols = [
            c["name"]
            for c in info["col_details"]
            if any(
                ts in c["name"].lower()
                for ts in [
                    "created_at",
                    "updated_at",
                    "last_updated",
                    "processed_at",
                    "ingested_at",
                ]
            )
        ]
        source_cols = [
            c["name"]
            for c in info["col_details"]
            if any(s in c["name"].lower() for s in ["source", "version", "parser_version"])
        ]
        metadata_tables[tname] = {
            "timestamp_cols": timestamp_cols,
            "source_cols": source_cols,
            "has_timestamps": len(timestamp_cols) > 0,
            "has_source_tracking": len(source_cols) > 0,
        }

    tables_missing_ts = [t for t, m in metadata_tables.items() if not m["has_timestamps"]]
    tables_missing_src = [t for t, m in metadata_tables.items() if not m["has_source_tracking"]]

    print(
        f"\n   [7.1] Tables WITH timestamp columns: {len(metadata_tables) - len(tables_missing_ts)}/{len(metadata_tables)}"
    )
    print(
        f"   [7.2] Tables WITHOUT timestamps: {tables_missing_ts if tables_missing_ts else 'None [OK]'}"
    )
    print(
        f"   [7.3] Tables WITH source tracking: {len(metadata_tables) - len(tables_missing_src)}/{len(metadata_tables)}"
    )

    # ===========================================================================
    # SECTION 8: HLTV DATABASE CHECK
    # ===========================================================================
    print("\n" + "=" * 70)
    print("SECTION 8: HLTV PRO STATISTICS DATABASE")
    print("=" * 70)

    if os.path.exists(HLTV_DB):
        hltv_tables = run_query(HLTV_DB, "SELECT name FROM sqlite_master WHERE type='table'")
        if hltv_tables:
            print(f"\n   Tables: {[t['name'] for t in hltv_tables]}")
            for ht in hltv_tables:
                tn = _safe_table_name(ht["name"])
                count = run_query(HLTV_DB, f"SELECT COUNT(*) as cnt FROM '{tn}'")
                c = count[0]["cnt"] if count else "?"
                print(f"      {tn}: {c} rows")

    # ===========================================================================
    # SECTION 9: COACH STATE (ML PIPELINE READINESS)
    # ===========================================================================
    print("\n" + "=" * 70)
    print("SECTION 9: ML PIPELINE READINESS — CoachState")
    print("=" * 70)

    coach = run_query(MAIN_DB, "SELECT * FROM coachstate LIMIT 1")
    if coach:
        c = coach[0]
        print(f"\n   Status: {c.get('status','?')}")
        print(f"   ML Status: {c.get('ml_status','?')}")
        print(f"   Ingest Status: {c.get('ingest_status','?')}")
        print(f"   HLTV Status: {c.get('hltv_status','?')}")
        print(f"   Current Epoch: {c.get('current_epoch',0)}/{c.get('total_epochs',0)}")
        print(f"   Train Loss: {c.get('train_loss',0)}  |  Val Loss: {c.get('val_loss',0)}")
        print(f"   Total Matches Processed: {c.get('total_matches_processed',0)}")
        print(f"   Last Trained Sample Count: {c.get('last_trained_sample_count',0)}")
        print(f"   Last Heartbeat: {c.get('last_heartbeat','Never')}")

    # ===========================================================================
    # SECTION 10: STORAGE SUMMARY
    # ===========================================================================
    print("\n" + "=" * 70)
    print("SECTION 10: STORAGE SUMMARY")
    print("=" * 70)

    print(f"\n   Main DB: {get_file_size_mb(MAIN_DB)} MB")
    print(f"   HLTV DB: {get_file_size_mb(HLTV_DB)} MB")
    print(f"   Main WAL: {get_file_size_mb(MAIN_DB + '-wal')} MB")

    if os.path.exists(MATCH_DATA_DIR):
        match_files = [f for f in os.listdir(MATCH_DATA_DIR) if f.endswith(".db")]
        total = sum(get_file_size_mb(os.path.join(MATCH_DATA_DIR, f)) for f in match_files)
        print(f"   Match DBs: {len(match_files)} files = {total:.2f} MB total")

        for mf in sorted(match_files):
            mpath = os.path.join(MATCH_DATA_DIR, mf)
            size = get_file_size_mb(mpath)
            ticks = run_query(mpath, "SELECT COUNT(*) as cnt FROM match_tick_state")
            t = ticks[0]["cnt"] if ticks else "?"
            print(f"      {mf}: {size} MB  ({t} ticks)")

    print("\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
