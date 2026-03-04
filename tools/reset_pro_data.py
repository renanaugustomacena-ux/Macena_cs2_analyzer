"""
Reset Pro Data — Clean slate for fresh ingestion & training.

Clears all stale data from:
  - database.db (all data tables + CoachState reset)
  - hltv_metadata.db (pro players, teams, stats, matches)
  - knowledge_graph.db (entities, relations)
  - hltv_cache.db (player cache)
  - ingestion/cache/*.mcn (parsed demo cache)
  - models/**/*.pt (all model checkpoints)
  - ingestion/.validated_cache.json (demo registry)
  - data/hltv_sync_state.json (HLTV sync state)
  - match_data/*.db (per-match SQLite files)

Idempotent: safe to run multiple times.
"""

import glob
import json
import os
import sqlite3
import sys
from datetime import datetime

# Resolve project root and add to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

# --- Path Constants ---
BASE_DIR = os.path.join(PROJECT_ROOT, "Programma_CS2_RENAN")
CORE_DB_DIR = os.path.join(BASE_DIR, "backend", "storage")

DATABASE_PATH = os.path.join(CORE_DB_DIR, "database.db")
HLTV_METADATA_PATH = os.path.join(CORE_DB_DIR, "hltv_metadata.db")
KNOWLEDGE_GRAPH_PATH = os.path.join(PROJECT_ROOT, "data", "knowledge_graph.db")
HLTV_CACHE_PATH = os.path.join(BASE_DIR, "data", "hltv_cache.db")

CACHE_DIR = os.path.join(BASE_DIR, "ingestion", "cache")

VALIDATED_CACHE_PATH = os.path.join(BASE_DIR, "ingestion", ".validated_cache.json")
HLTV_SYNC_STATE_PATH = os.path.join(BASE_DIR, "data", "hltv_sync_state.json")
HLTV_PID_FILE = os.path.join(BASE_DIR, "hltv_sync.pid")
HLTV_STOP_FILE = os.path.join(BASE_DIR, "hltv_sync.stop")

# Match data directories (in-project fallback + user-configured)
MATCH_DATA_DIRS = [
    os.path.join(CORE_DB_DIR, "match_data"),
]

MODEL_DIRS = [
    os.path.join(BASE_DIR, "models", "global"),
    os.path.join(BASE_DIR, "models", "user"),
    os.path.join(BASE_DIR, "models", "master_user"),
    os.path.join(BASE_DIR, "backend", "nn", "models", "nn"),
]

# ANSI colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def log(msg: str, color: str = "") -> None:
    print(f"{color}{msg}{RESET}")


def delete_rows(conn: sqlite3.Connection, table: str) -> int:
    """DELETE all rows from a table. Returns count deleted."""
    try:
        cursor = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
        count = cursor.fetchone()[0]
        if count > 0:
            conn.execute(f"DELETE FROM [{table}]")
        return count
    except sqlite3.OperationalError as e:
        log(f"  SKIP {table}: {e}", YELLOW)
        return 0


def phase_main_database() -> dict:
    """Phase 1: Clear database.db tables and reset CoachState."""
    log("\n=== Phase 1: Main Database (database.db) ===", BOLD + CYAN)
    results = {}

    if not os.path.exists(DATABASE_PATH):
        log(f"  NOT FOUND: {DATABASE_PATH}", YELLOW)
        return results

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
    except Exception:
        conn.close()
        raise

    # Order matters: delete child tables before parent tables (FK constraints)
    tables_to_clear = [
        "playertickstate",
        "roundstats",
        "coachingexperience",
        "coachinginsight",
        "calibrationsnapshot",
        "rolethresholdrecord",
        "servicenotification",
        "tacticalknowledge",
        "mapveto",
        "proplayerstatcard",
        "playermatchstats",
        "hltvdownload",
        "matchresult",
        "ingestiontask",
        "ext_teamroundstats",
        "ext_playerplaystyle",
        "proplayer",
        "proteam",
    ]

    for table in tables_to_clear:
        count = delete_rows(conn, table)
        results[table] = count
        status = f"{count} rows" if count > 0 else "already empty"
        log(f"  {table}: {status}", GREEN if count == 0 else YELLOW)

    # Reset CoachState counters (don't delete — keep the singleton row)
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM coachstate")
        coach_count = cursor.fetchone()[0]
        if coach_count > 0:
            conn.execute(
                """
                UPDATE coachstate SET
                    last_trained_sample_count = 0,
                    total_matches_processed = 0,
                    last_pro_ingest_sync = NULL,
                    last_ingest_sync = NULL,
                    current_epoch = 0,
                    total_epochs = 0,
                    train_loss = 0.0,
                    val_loss = 0.0,
                    eta_seconds = 0.0,
                    parsing_progress = 0.0,
                    belief_confidence = 0.0,
                    detail = 'System ready — fresh start',
                    status = 'Paused',
                    hltv_status = 'Idle',
                    ingest_status = 'Idle',
                    ml_status = 'Idle',
                    service_pid = NULL,
                    last_heartbeat = NULL
                WHERE 1=1
            """
            )
            log("  coachstate: reset to defaults", GREEN)
        else:
            log("  coachstate: no rows (will be created on first run)", YELLOW)
        results["coachstate"] = "reset"
    except sqlite3.OperationalError as e:
        log(f"  coachstate: {e}", RED)
        results["coachstate"] = f"error: {e}"

    # NOTE: PlayerProfile is NOT cleared — it belongs to the user, not pro data
    try:
        conn.commit()
    finally:
        conn.close()
    return results


def phase_hltv_metadata() -> dict:
    """Phase 2: Clear hltv_metadata.db."""
    log("\n=== Phase 2: HLTV Metadata (hltv_metadata.db) ===", BOLD + CYAN)
    results = {}

    if not os.path.exists(HLTV_METADATA_PATH):
        log(f"  NOT FOUND: {HLTV_METADATA_PATH}", YELLOW)
        return results

    conn = sqlite3.connect(HLTV_METADATA_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")

        # Child tables first
        tables = [
            "proplayerstatcard",
            "mapveto",
            "hltvdownload",
            "matchresult",
            "proplayer",
            "proteam",
        ]

        for table in tables:
            count = delete_rows(conn, table)
            results[table] = count
            status = f"{count} rows" if count > 0 else "already empty"
            log(f"  {table}: {status}", GREEN if count == 0 else YELLOW)

        conn.commit()
    finally:
        conn.close()
    return results


def phase_knowledge_graph() -> dict:
    """Phase 3: Clear knowledge_graph.db."""
    log("\n=== Phase 3: Knowledge Graph (knowledge_graph.db) ===", BOLD + CYAN)
    results = {}

    if not os.path.exists(KNOWLEDGE_GRAPH_PATH):
        log(f"  NOT FOUND: {KNOWLEDGE_GRAPH_PATH}", YELLOW)
        return results

    conn = sqlite3.connect(KNOWLEDGE_GRAPH_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")

        for table in ["relations", "entities"]:
            count = delete_rows(conn, table)
            results[table] = count
            status = f"{count} rows" if count > 0 else "already empty"
            log(f"  {table}: {status}", GREEN if count == 0 else YELLOW)

        # Reset autoincrement sequence
        try:
            conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('relations', 'entities')")
            log("  sqlite_sequence: reset", GREEN)
        except sqlite3.OperationalError:
            pass  # Table may not exist if autoincrement was never used

        conn.commit()
    finally:
        conn.close()
    return results


def phase_hltv_cache() -> dict:
    """Phase 4: Clear hltv_cache.db."""
    log("\n=== Phase 4: HLTV Cache (hltv_cache.db) ===", BOLD + CYAN)
    results = {}

    if not os.path.exists(HLTV_CACHE_PATH):
        log(f"  NOT FOUND: {HLTV_CACHE_PATH}", YELLOW)
        return results

    conn = sqlite3.connect(HLTV_CACHE_PATH)
    try:
        count = delete_rows(conn, "hltv_player_cache")
        results["hltv_player_cache"] = count
        status = f"{count} rows" if count > 0 else "already empty"
        log(f"  hltv_player_cache: {status}", GREEN if count == 0 else YELLOW)

        conn.commit()
    finally:
        conn.close()
    return results


def phase_demo_cache() -> list:
    """Phase 5: Delete cached .mcn files."""
    log("\n=== Phase 5: Demo Cache (ingestion/cache/*.mcn) ===", BOLD + CYAN)
    deleted = []

    if not os.path.isdir(CACHE_DIR):
        log(f"  Cache directory not found: {CACHE_DIR}", YELLOW)
        return deleted

    mcn_files = glob.glob(os.path.join(CACHE_DIR, "*.mcn"))
    if not mcn_files:
        log("  No .mcn files found", GREEN)
        return deleted

    total_bytes = 0
    for f in mcn_files:
        size = os.path.getsize(f)
        total_bytes += size
        os.remove(f)
        deleted.append(os.path.basename(f))
        log(f"  DELETED: {os.path.basename(f)} ({size / 1024 / 1024:.1f} MB)", YELLOW)

    log(f"  Total freed: {total_bytes / 1024 / 1024:.1f} MB", GREEN)
    return deleted


def phase_state_files() -> dict:
    """Phase 5.5: Reset cache and state files."""
    log("\n=== Phase 5.5: State Files & Demo Registry ===", BOLD + CYAN)
    results = {}

    # Reset .validated_cache.json (demo registry)
    if os.path.exists(VALIDATED_CACHE_PATH):
        with open(VALIDATED_CACHE_PATH, "w") as f:
            json.dump({}, f)
        log("  .validated_cache.json: reset to {}", GREEN)
        results["validated_cache"] = "reset"
    else:
        log("  .validated_cache.json: not found (OK)", YELLOW)
        results["validated_cache"] = "not_found"

    # Reset hltv_sync_state.json
    if os.path.exists(HLTV_SYNC_STATE_PATH):
        with open(HLTV_SYNC_STATE_PATH, "w") as f:
            json.dump({}, f)
        log("  hltv_sync_state.json: reset to {}", GREEN)
        results["hltv_sync_state"] = "reset"
    else:
        log("  hltv_sync_state.json: not found (OK)", YELLOW)
        results["hltv_sync_state"] = "not_found"

    # Delete stale PID and stop signal files
    for label, path in [("hltv_sync.pid", HLTV_PID_FILE), ("hltv_sync.stop", HLTV_STOP_FILE)]:
        if os.path.exists(path):
            os.remove(path)
            log(f"  {label}: DELETED", YELLOW)
            results[label] = "deleted"

    return results


def phase_match_data() -> list:
    """Phase 5.7: Delete per-match SQLite files."""
    log("\n=== Phase 5.7: Per-Match SQLite Files ===", BOLD + CYAN)
    deleted = []

    # Also check user-configured match_data path
    try:
        from Programma_CS2_RENAN.core.config import MATCH_DATA_PATH
        extra_dirs = [MATCH_DATA_PATH] if MATCH_DATA_PATH else []
    except Exception:
        extra_dirs = []

    all_dirs = list(set(MATCH_DATA_DIRS + extra_dirs))

    for match_dir in all_dirs:
        if not os.path.isdir(match_dir):
            log(f"  Directory not found: {match_dir}", YELLOW)
            continue

        # Find all match_*.db files and their WAL/SHM companions
        db_files = glob.glob(os.path.join(match_dir, "match_*.db*"))
        if not db_files:
            log(f"  No match files in {match_dir}", GREEN)
            continue

        total_bytes = 0
        for f in db_files:
            size = os.path.getsize(f)
            total_bytes += size
            os.remove(f)
            deleted.append(os.path.basename(f))

        log(f"  DELETED {len(db_files)} files from {match_dir} ({total_bytes / 1024 / 1024:.1f} MB)", YELLOW)

    if not deleted:
        log("  No per-match files found", GREEN)

    return deleted


def phase_model_checkpoints() -> list:
    """Phase 6: Delete all .pt model checkpoints."""
    log("\n=== Phase 6: Model Checkpoints (models/**/*.pt) ===", BOLD + CYAN)
    deleted = []

    for model_dir in MODEL_DIRS:
        if not os.path.isdir(model_dir):
            continue
        pt_files = glob.glob(os.path.join(model_dir, "*.pt"))
        for f in pt_files:
            size = os.path.getsize(f)
            os.remove(f)
            rel_path = os.path.relpath(f, BASE_DIR)
            deleted.append(rel_path)
            log(f"  DELETED: {rel_path} ({size / 1024:.1f} KB)", YELLOW)

    if not deleted:
        log("  No .pt files found", GREEN)

    return deleted


def phase_vacuum() -> None:
    """Phase 7: VACUUM all databases to reclaim disk space."""
    log("\n=== Phase 7: VACUUM (reclaim disk space) ===", BOLD + CYAN)

    db_paths = {
        "database.db": DATABASE_PATH,
        "hltv_metadata.db": HLTV_METADATA_PATH,
        "knowledge_graph.db": KNOWLEDGE_GRAPH_PATH,
        "hltv_cache.db": HLTV_CACHE_PATH,
    }

    for name, path in db_paths.items():
        if not os.path.exists(path):
            continue
        size_before = os.path.getsize(path)
        conn = sqlite3.connect(path)
        conn.execute("VACUUM")
        conn.close()
        size_after = os.path.getsize(path)
        saved = size_before - size_after
        log(
            f"  {name}: {size_before / 1024:.1f} KB -> {size_after / 1024:.1f} KB (saved {saved / 1024:.1f} KB)",
            GREEN,
        )


def phase_verify() -> bool:
    """Phase 8: Verify all data is cleared."""
    log("\n=== Phase 8: Verification ===", BOLD + CYAN)
    all_ok = True

    # Verify database.db
    if os.path.exists(DATABASE_PATH):
        conn = sqlite3.connect(DATABASE_PATH)
        tables = [
            "playertickstate",
            "roundstats",
            "playermatchstats",
            "coachinginsight",
            "coachingexperience",
            "ingestiontask",
            "matchresult",
            "servicenotification",
            "calibrationsnapshot",
            "rolethresholdrecord",
            "tacticalknowledge",
        ]
        for table in tables:
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
                count = cursor.fetchone()[0]
                if count > 0:
                    log(f"  FAIL: {table} still has {count} rows", RED)
                    all_ok = False
            except sqlite3.OperationalError:
                pass  # Table doesn't exist — OK
        conn.close()

    # Verify hltv_metadata.db
    if os.path.exists(HLTV_METADATA_PATH):
        conn = sqlite3.connect(HLTV_METADATA_PATH)
        for table in ["proplayer", "proteam", "proplayerstatcard", "matchresult"]:
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
                count = cursor.fetchone()[0]
                if count > 0:
                    log(f"  FAIL: hltv.{table} still has {count} rows", RED)
                    all_ok = False
            except sqlite3.OperationalError:
                pass
        conn.close()

    # Verify knowledge_graph.db
    if os.path.exists(KNOWLEDGE_GRAPH_PATH):
        conn = sqlite3.connect(KNOWLEDGE_GRAPH_PATH)
        for table in ["entities", "relations"]:
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
                count = cursor.fetchone()[0]
                if count > 0:
                    log(f"  FAIL: graph.{table} still has {count} rows", RED)
                    all_ok = False
            except sqlite3.OperationalError:
                pass
        conn.close()

    # Verify cache dir
    mcn_files = glob.glob(os.path.join(CACHE_DIR, "*.mcn")) if os.path.isdir(CACHE_DIR) else []
    if mcn_files:
        log(f"  FAIL: {len(mcn_files)} .mcn files remain in cache", RED)
        all_ok = False

    # Verify model checkpoints
    remaining_pt = []
    for model_dir in MODEL_DIRS:
        if os.path.isdir(model_dir):
            remaining_pt.extend(glob.glob(os.path.join(model_dir, "*.pt")))
    if remaining_pt:
        log(f"  FAIL: {len(remaining_pt)} .pt files remain", RED)
        all_ok = False

    # Verify demo registry is empty
    if os.path.exists(VALIDATED_CACHE_PATH):
        try:
            with open(VALIDATED_CACHE_PATH, "r") as f:
                cache_data = json.load(f)
            if cache_data:
                log(f"  FAIL: .validated_cache.json not empty ({len(cache_data)} keys)", RED)
                all_ok = False
            else:
                log("  .validated_cache.json: empty (OK)", GREEN)
        except Exception as e:
            log(f"  WARN: .validated_cache.json unreadable: {e}", YELLOW)

    # Verify hltv_sync_state is empty
    if os.path.exists(HLTV_SYNC_STATE_PATH):
        try:
            with open(HLTV_SYNC_STATE_PATH, "r") as f:
                sync_data = json.load(f)
            if sync_data:
                log(f"  FAIL: hltv_sync_state.json not empty ({len(sync_data)} keys)", RED)
                all_ok = False
            else:
                log("  hltv_sync_state.json: empty (OK)", GREEN)
        except Exception as e:
            log(f"  WARN: hltv_sync_state.json unreadable: {e}", YELLOW)

    # Verify no per-match SQLite files remain
    for match_dir in MATCH_DATA_DIRS:
        if os.path.isdir(match_dir):
            remaining_match = glob.glob(os.path.join(match_dir, "match_*.db"))
            if remaining_match:
                log(f"  FAIL: {len(remaining_match)} match files remain in {match_dir}", RED)
                all_ok = False

    if all_ok:
        log("  ALL CLEAR — system is ready for fresh ingestion", GREEN + BOLD)
    else:
        log("  SOME CHECKS FAILED — review above", RED + BOLD)

    return all_ok


def main() -> int:
    log(f"\n{'=' * 60}", BOLD)
    log("  Macena CS2 Analyzer — Pro Data Reset", BOLD + CYAN)
    log(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", CYAN)
    log(f"{'=' * 60}", BOLD)

    log("\nThis will DELETE:", YELLOW + BOLD)
    log("  - All data rows in database.db (stats, ticks, insights, tasks, pro tables)")
    log("  - All rows in hltv_metadata.db (pro players, teams)")
    log("  - All rows in knowledge_graph.db (entities, relations)")
    log("  - All rows in hltv_cache.db")
    log("  - All .mcn files in ingestion/cache/")
    log("  - All .pt model checkpoints")
    log("  - Demo registry (.validated_cache.json)")
    log("  - HLTV sync state (hltv_sync_state.json)")
    log("  - All per-match SQLite files (match_data/*.db)")
    log("\nPreserved: schema, user profile, settings, CSVs, knowledge base, migrations")

    confirm = input(f"\n{BOLD}Proceed? [y/N]: {RESET}").strip().lower()
    if confirm != "y":
        log("\nAborted.", YELLOW)
        return 1

    phase_main_database()
    phase_hltv_metadata()
    phase_knowledge_graph()
    phase_hltv_cache()
    phase_demo_cache()
    phase_state_files()
    phase_match_data()
    phase_model_checkpoints()
    phase_vacuum()
    ok = phase_verify()

    log(f"\n{'=' * 60}", BOLD)
    if ok:
        log("  RESET COMPLETE — Ready for fresh ingestion & training", GREEN + BOLD)
    else:
        log("  RESET COMPLETED WITH WARNINGS — Review output above", YELLOW + BOLD)
    log(f"{'=' * 60}\n", BOLD)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
