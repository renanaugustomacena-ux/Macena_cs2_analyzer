import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional

from Programma_CS2_RENAN.observability.logger_setup import get_logger

app_logger = get_logger("cs2analyzer.db_governor")
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.match_data_manager import get_match_data_manager
from Programma_CS2_RENAN.core.config import CORE_DB_DIR, DB_DIR


class DatabaseGovernor:
    """
    Authoritative controller for Database Tier 1, 2, and 3.
    Enforces architectural boundaries and integrity.
    """

    def __init__(self):
        self.db_manager = get_db_manager()
        self.match_manager = get_match_data_manager()

    def audit_storage(self) -> Dict:
        """
        Calculates storage health and detects anomalies.
        """
        report = {"tier1_2_size": 0, "tier3_count": 0, "tier3_total_size": 0, "anomalies": []}

        # 1. Tier 1 & 2 (Monolith)
        db_path = Path(DB_DIR) / "database.db"
        if db_path.exists():
            # Get size of main DB + WAL + SHM
            total_size = db_path.stat().st_size
            for ext in ["-wal", "-shm"]:
                p = db_path.with_name(db_path.name + ext)
                if p.exists():
                    total_size += p.stat().st_size
            report["tier1_2_size"] = total_size
        else:
            # Fallback check in CORE_DB_DIR just in case
            fallback_path = Path(CORE_DB_DIR) / "database.db"
            if fallback_path.exists():
                report["tier1_2_size"] = fallback_path.stat().st_size
            else:
                report["anomalies"].append("CRITICAL: Monolith database.db not found!")

        # 1b. Check HLTV Metadata DB — auto-restore from backup if missing
        hltv_path = Path(DB_DIR) / "hltv_metadata.db"
        hltv_bak_path = Path(DB_DIR) / "hltv_metadata.db.bak"

        if not hltv_path.exists():
            if hltv_bak_path.exists():
                try:
                    shutil.copy2(str(hltv_bak_path), str(hltv_path))
                    app_logger.info("Auto-restored hltv_metadata.db from backup.")
                except Exception as e:
                    app_logger.error("Failed to auto-restore hltv_metadata.db: %s", e)
                    report["anomalies"].append(
                        f"WARNING: hltv_metadata.db missing, auto-restore failed: {e}"
                    )
            else:
                # Create empty DB with WAL mode so downstream code doesn't crash
                try:
                    conn = sqlite3.connect(str(hltv_path))
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.close()
                    app_logger.info("Created empty hltv_metadata.db (no backup available).")
                except Exception as e:
                    app_logger.error("Failed to create hltv_metadata.db: %s", e)
                    report["anomalies"].append(
                        f"CRITICAL: hltv_metadata.db missing and creation failed: {e}"
                    )

        # 2. Tier 3 (Match Databases)
        available_matches = self.match_manager.list_available_matches()
        report["tier3_count"] = len(available_matches)
        report["tier3_total_size"] = self.match_manager.get_total_storage_bytes()

        # 3. Detect orphaned files (files on disk not in metadata)
        # This is a key governance feature
        return report

    def _run_pragma_quick_check(self) -> bool:
        """DG-02: Execute PRAGMA quick_check synchronously (internal use only).

        This can block for minutes on large DBs — callers must run in a
        background thread with a timeout.
        """
        with self.db_manager.get_session() as session:
            from sqlalchemy import text

            res = session.execute(text("PRAGMA quick_check")).scalar()
            return res == "ok"

    def verify_integrity(self, full: bool = False) -> Dict[str, bool]:
        """Verify database connectivity and optionally run full integrity check.

        By default performs a lightweight connection test (SELECT 1) suitable
        for boot-time checks.  The monolith can be 16+ GB — PRAGMA
        integrity_check / quick_check would block for minutes.

        Args:
            full: If True, run PRAGMA quick_check via the async path with
                  a 120s timeout (DG-02). Never blocks indefinitely.
        """
        if full:
            # DG-02: Always route full check through the async path to prevent
            # indefinite blocking. PRAGMA quick_check has no native timeout.
            app_logger.warning(
                "DG-02: verify_integrity(full=True) — routing through "
                "async path with 120s timeout to prevent indefinite blocking."
            )
            async_results = self.verify_integrity_async(timeout_seconds=120.0)
            return {"monolith": async_results.get("full_check")}

        results = {}
        with self.db_manager.get_session() as session:
            from sqlalchemy import text

            # Lightweight liveness probe — confirms engine can execute queries
            res = session.execute(text("SELECT 1")).scalar()
            results["monolith"] = res == 1

        return results

    def verify_integrity_async(self, timeout_seconds: float = 120.0) -> Dict[str, Optional[bool]]:
        """R3-H07: Run PRAGMA quick_check in a background thread with timeout.

        Returns immediately-available liveness result plus async integrity result.
        If the background check doesn't complete within timeout_seconds, the result
        is None (indeterminate).
        """
        # Run lightweight check synchronously first
        results = self.verify_integrity(full=False)

        # Run full check in background thread with timeout
        full_result: Dict[str, Optional[bool]] = {"full_check": None}

        def _run_full_check():
            try:
                full_result["full_check"] = self._run_pragma_quick_check()
            except Exception as e:
                app_logger.error("Background integrity check failed: %s", e)
                full_result["full_check"] = False

        thread = threading.Thread(target=_run_full_check, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)

        if thread.is_alive():
            app_logger.warning(
                "R3-H07: PRAGMA quick_check did not complete within %.0fs — "
                "result indeterminate. DB may be too large for synchronous check.",
                timeout_seconds,
            )

        results["full_check"] = full_result["full_check"]
        return results

    def prune_match_data(self, match_id: int) -> bool:
        """Privileged deletion of match telemetry."""
        app_logger.warning("Governor: Pruning match %s", match_id)
        return self.match_manager.delete_match(match_id)

    def rebuild_indexes(self):
        """Maintenance: Rebuilds all database indexes via REINDEX using the ORM engine."""
        app_logger.info("Governor: Rebuilding indexes (REINDEX)...")
        from sqlalchemy import text

        with self.db_manager.get_session() as session:
            session.execute(text("REINDEX"))
        app_logger.info("Governor: Index rebuild complete.")
