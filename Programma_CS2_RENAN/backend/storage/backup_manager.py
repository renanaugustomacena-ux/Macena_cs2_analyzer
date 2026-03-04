import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.core.config import CORE_DB_DIR, USER_DATA_ROOT
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.backup_manager")


class BackupManager:
    """
    Doctorate-Level Backup Solution for Monolithic SQLite.

    Features:
    - Hot Backup: Uses SQLite `VACUUM INTO` for safe, non-blocking backups during WAL mode.
    - Rotation Policy: Maintains 7 daily + 4 weekly backups to balance safety vs storage.
    - Integrity Check: Pre-validates backup integrity before accepting it.
    """

    def __init__(self):
        # Backups live in User Data (preserves data even if app is uninstalled/updated)
        self.backup_dir = os.path.join(USER_DATA_ROOT, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)
        self.db_path = os.path.join(CORE_DB_DIR, "database.db")

    def create_checkpoint(self, label: str = "auto") -> bool:
        """
        Creates a hot backup of the database.

        Args:
            label: Tag for the backup (e.g., 'startup', 'manual', 'pre_migration')

        Returns:
            True if successful, False otherwise.
        """
        if not os.path.exists(self.db_path):
            logger.warning("No database found at %s to backup.", self.db_path)
            return False

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{label}_{timestamp}.db"
        target_path = Path(self.backup_dir) / filename

        logger.info("Starting Backup: %s...", filename)

        try:
            # 1. Hot Backup via SQLite VACUUM INTO
            # This is vastly superior to shutil.copy() as it respects WAL transactions
            db_manager = get_db_manager()
            with db_manager.engine.connect() as conn:
                # VACUUM INTO is available in SQLite 3.27+ (Python 3.8+ includes this)
                # Validate backup path resolves within expected directory
                import re

                label = target_path.stem
                if not re.match(r"^[a-zA-Z0-9_\-]+$", label):
                    raise ValueError(f"Backup label contains invalid characters: {label}")
                resolved = target_path.resolve()
                if not str(resolved).startswith(str(target_path.parent.resolve())):
                    raise ValueError(f"Backup path escapes target directory: {resolved}")
                from sqlalchemy import text

                target_path_safe = str(target_path).replace("'", "''")
                conn.execute(text(f"VACUUM INTO '{target_path_safe}'"))

            # 2. Verify Output
            if not os.path.exists(target_path):
                raise FileNotFoundError("VACUUM INTO completed but file is missing.")

            # 3. Integrity Check on the BACKUP (don't lock the main DB)
            if not self._verify_integrity(target_path):
                logger.error("Backup %s failed integrity check. Deleting.", filename)
                os.remove(target_path)
                return False

            logger.info(
                "Backup Successful: %s (%s MB)",
                target_path,
                os.path.getsize(target_path) / 1024 / 1024,
            )

            # 4. Enforce Retention Policy
            self._prune_backups()
            return True

        except Exception as e:
            logger.error("Backup Failed: %s", e)
            # Cleanup partial file
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except OSError as cleanup_err:
                    logger.warning(
                        "Failed to cleanup partial backup %s: %s", target_path, cleanup_err
                    )
            return False

    def _verify_integrity(self, db_path: str) -> bool:
        """Runs PRAGMA integrity_check on the backup file."""
        import sqlite3

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            conn.close()
            return result == "ok"
        except Exception as e:
            logger.error("Integrity Check Error: %s", e)
            return False

    def _prune_backups(self):
        """
        Enforces Retention Policy:
        - Keep last 7 daily backups
        - Keep last 4 weekly backups (approx 1 per week for last month)
        """
        try:
            # Gather all backups
            files = [
                f
                for f in os.listdir(self.backup_dir)
                if f.startswith("backup_") and f.endswith(".db")
            ]

            # Parse checkpoints
            checkpoints = []
            for f in files:
                path = os.path.join(self.backup_dir, f)
                try:
                    # Format: backup_LABEL_YYYYMMDD_HHMMSS.db
                    # We extract timestamp from end
                    parts = f.replace(".db", "").split("_")
                    if len(parts) >= 3:
                        ts_str = f"{parts[-2]}_{parts[-1]}"
                        dt = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                        checkpoints.append({"path": path, "dt": dt, "file": f})
                except (ValueError, IndexError):
                    continue  # Skip malformed backup filenames

            # Sort by date descending (newest first)
            checkpoints.sort(key=lambda x: x["dt"], reverse=True)

            keep_list = []

            # Strategy:
            # 1. Always keep the absolute latest (Safety)
            if checkpoints:
                keep_list.append(checkpoints[0])

            # 2. Keep last 7 dailies
            # We map date (YYYY-MM-DD) -> latest backup for that date
            seen_dates = set()
            if checkpoints:
                seen_dates.add(checkpoints[0]["dt"].date())

            daily_candidates = checkpoints[1:]
            last_7_days = []
            for cp in daily_candidates:
                d = cp["dt"].date()
                if d not in seen_dates and len(last_7_days) < 6:  # +1 from latest = 7
                    last_7_days.append(cp)
                    seen_dates.add(d)

            keep_list.extend(last_7_days)

            # 3. Keep 4 weeklies (older than 7 days)
            # Simplistic approach: Keep one per week for last 4 weeks
            weekly_candidates = [cp for cp in checkpoints if cp not in keep_list]
            last_4_weeks = []
            if weekly_candidates:
                # Sort by date desc
                current_week_start = weekly_candidates[0]["dt"].isocalendar()[1]
                for cp in weekly_candidates:
                    w = cp["dt"].isocalendar()[1]
                    if w != current_week_start and len(last_4_weeks) < 4:
                        last_4_weeks.append(cp)
                        current_week_start = w

            keep_list.extend(last_4_weeks)

            # Execute Pruning
            keep_paths = {cp["path"] for cp in keep_list}
            for cp in checkpoints:
                if cp["path"] not in keep_paths:
                    logger.info("Pruning old backup: %s", cp["file"])
                    os.remove(cp["path"])

        except Exception as e:
            logger.error("Pruning Failed: %s", e)

    def should_run_auto_backup(self) -> bool:
        """Returns True if no backup exists for today."""
        try:
            today = datetime.now(timezone.utc).date()
            files = [
                f
                for f in os.listdir(self.backup_dir)
                if f.startswith("backup_") and f.endswith(".db")
            ]

            for f in files:
                try:
                    parts = f.replace(".db", "").split("_")
                    ts_str = f"{parts[-2]}_{parts[-1]}"
                    dt = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                    if dt.date() == today:
                        return False  # Backup for today already exists
                except (ValueError, IndexError):
                    continue

            return True
        except Exception as e:
            logger.debug("Auto-backup check failed: %s", e)
            return True  # Fail safe: run it
