import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from Programma_CS2_RENAN.core.config import BASE_DIR as PROJECT_ROOT
from Programma_CS2_RENAN.core.config import (
    CURRENT_USER_ID,
    DATA_DIR,
    MAX_DEMOS_PER_MONTH,
    MAX_TOTAL_DEMOS_PER_USER,
    get_setting,
)
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.storage_manager")


class StorageManager:
    """
    Manages Local Storage for CS2 Demos:
    1. Ingest folders (Where user places new files).
    2. Archive (Where files go after processing).

    Strictly offline. No automatic downloads.
    """

    def __init__(self):
        # Configuration
        self.local_path = Path(get_setting("DEFAULT_DEMO_PATH", os.path.expanduser("~")))
        self.quota_gb = float(get_setting("LOCAL_QUOTA_GB", 10.0))

        # "The Brain" Storage (Managed Data)
        brain_root = get_setting("BRAIN_DATA_ROOT", None)
        if brain_root:
            self.brain_dir = Path(brain_root)
            self.archive_dir = self.brain_dir / "datasets" / "user_archive"
            self.pro_archive_dir = self.brain_dir / "datasets" / "pro_archive"
        else:
            # Fallback
            self.brain_dir = Path(PROJECT_ROOT) / "data"
            self.archive_dir = self.brain_dir / "archive"
            self.pro_archive_dir = self.brain_dir / "pro_archive"

        # Fallback if settings contain invalid E:/D: paths that don't exist
        if not self.local_path.exists():
            logger.warning("Configured path %s not found. Reverting to default.", self.local_path)
            self.local_path = Path(os.path.expanduser("~"))

        # Legacy/Ingestion paths (User Demos)
        self.ingest_dir = self.local_path

        # Pro Path Logic: Respect independent setting or fallback to subdirectory
        pro_setting = get_setting("PRO_DEMO_PATH", None)
        if pro_setting and os.path.exists(pro_setting):
            # User Selected Path: Use it directly (Assume they selected the folder with demos)
            self.pro_ingest_dir = Path(pro_setting)
        else:
            # Fallback (Default): Use the structured subdirectory in default location
            self.pro_ingest_dir = self.local_path / "pro_ingest"

        self.archive_path = self.archive_dir  # Alias for compatibility

        self._ensure_dirs()

    def _ensure_dirs(self):
        try:
            # NOTE: pro_ingest_dir is excluded — it's a user-managed external path
            # that should already exist. Creating subdirectories inside it causes
            # PermissionError on some configurations.
            for d in [self.local_path, self.ingest_dir, self.archive_path]:
                # If drive doesn't exist (WinError 3), we can't create. Log it.
                try:
                    d.mkdir(parents=True, exist_ok=True)
                    logger.debug("Ensured directory exists: %s", d)
                except OSError as e:
                    # Drive/path unavailable - log but don't crash
                    logger.warning(
                        "Cannot create directory %s: %s (drive may be unavailable)", d, e
                    )
        except Exception as e:
            logger.error("Failed to create storage directories: %s", e)

    def enforce_quota(self):
        """
        Check local usage and move old files to archive if over quota.
        """
        current_usage = self._get_dir_size_gb(self.local_path)
        logger.info(
            "Local storage usage: %s GB / %s GB",
            format(current_usage, ".2f"),
            format(self.quota_gb, ".2f"),
        )

        if current_usage > self.quota_gb:
            logger.info("Quota exceeded. Archiving old demos...")
            self._archive_old_files(target_reduction_gb=current_usage - self.quota_gb + 1.0)

    def get_demo_path(self, filename: str) -> Optional[str]:
        """
        Get absolute path to demo.
        Only checks local search paths.

        P2-03: Validates filename against path traversal attacks.
        """
        # P2-03: Strip directory components to block path traversal (e.g. ../../etc/passwd)
        safe_name = Path(filename).name
        if safe_name != filename:
            logger.warning("Path traversal attempt blocked in get_demo_path: %s", filename)
            return None

        # Check local search paths
        search_paths = [
            self.local_path / safe_name,
            self.ingest_dir / safe_name,
            self.pro_ingest_dir / safe_name,
            self.archive_path / safe_name,
        ]

        for path in search_paths:
            if path.exists():
                return str(path)

        return None

    def _archive_old_files(self, target_reduction_gb: float):
        """Move oldest .dem files to archive."""
        files = []
        # scan all local folders
        # M-27: Exclude pro_ingest_dir from archival — pro demos should not be archived
        for root in [self.local_path, self.ingest_dir]:
            for f in root.glob("*.dem"):
                stat_result = f.stat()
                files.append((f, stat_result.st_mtime, stat_result.st_size))

        # Sort by oldest modified
        files.sort(key=lambda x: x[1])

        freed_bytes = 0
        target_bytes = target_reduction_gb * 1024**3

        for file_path, _, size in files:
            if freed_bytes >= target_bytes:
                break

            try:
                # Move to local archive
                target = self.archive_path / file_path.name
                if str(file_path) != str(target):
                    shutil.move(str(file_path), str(target))
                    logger.info("Archived: %s -> %s", file_path.name, target)

                freed_bytes += size
            except Exception as e:
                logger.error("Failed to archive %s: %s", file_path.name, e)

    def _get_dir_size_gb(self, path: Path) -> float:
        total = 0
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total += os.path.getsize(fp)
                    except (OSError, IOError) as e:
                        # File may have been deleted during walk, or permission denied
                        logger.debug("Cannot get size of %s: %s", fp, e)
        except Exception as e:
            # Path doesn't exist or not accessible
            logger.warning("Cannot calculate storage size for %s: %s", path, e)
        return total / (1024**3)

    # Legacy Compatibility Methods

    def get_ingest_dir(self, is_pro=False):
        return self.pro_ingest_dir if is_pro else self.ingest_dir

    def list_new_demos(self, is_pro=False):
        """
        Scans the ingest folder and filters out demos already recorded in DB.
        Professional Check: uses both filename and path to prevent duplicates if files are moved.
        """
        target = self.get_ingest_dir(is_pro)
        all_dems = list(target.glob("*.dem"))

        from sqlmodel import select

        from .database import get_db_manager
        from .db_models import IngestionTask, PlayerMatchStats

        _QUERY_LIMIT = 10_000
        db = get_db_manager()
        with db.get_session() as s:
            # 1. Check paths in Task table
            known_paths = s.exec(select(IngestionTask.demo_path).limit(_QUERY_LIMIT)).all()
            if len(known_paths) == _QUERY_LIMIT:
                logger.warning(
                    "list_new_demos: IngestionTask query hit %d-row limit; "
                    "some known demos may not be in the dedup set.",
                    _QUERY_LIMIT,
                )

            # 2. Check filenames in MatchStats table (Final verification)
            # This ensures that if the same file is copied back to root, it isn't re-ingested
            known_filenames = s.exec(select(PlayerMatchStats.demo_name).limit(_QUERY_LIMIT)).all()
            if len(known_filenames) == _QUERY_LIMIT:
                logger.warning(
                    "list_new_demos: PlayerMatchStats query hit %d-row limit; "
                    "some known demos may not be in the dedup set.",
                    _QUERY_LIMIT,
                )

            # Use base filename comparison
            # Build dedup set from known filenames. Use stem (no extension) for reliable matching.
            # Previous logic split on '_' which broke filenames containing underscores.
            known_names_set = {os.path.basename(n) for n in known_filenames}
            known_paths_set = set(known_paths)

        # Compare using stem (no extension) since PlayerMatchStats stores stems
        # e.g. "astralis-vs-furia-m1-overpass" not "astralis-vs-furia-m1-overpass.dem"
        return [
            p for p in all_dems if str(p) not in known_paths_set and p.stem not in known_names_set
        ]

    def archive_demo(self, demo_path, is_pro=False):
        """Standard archive: move to ingested folder to prevent re-parsing."""
        target_dir = self.get_ingest_dir(is_pro) / "ingested"
        target_dir.mkdir(exist_ok=True)
        try:
            shutil.move(str(demo_path), str(target_dir / demo_path.name))
        except Exception as e:
            logger.error("Failed to move demo to ingested: %s", e)

    def can_user_upload(self, is_pro=False):
        """Checks if the user can add more demos."""
        if is_pro:
            return True

        from sqlmodel import select

        from .database import get_db_manager
        from .db_models import Ext_PlayerPlaystyle

        db = get_db_manager()
        with db.get_session() as session:
            playstyle = session.exec(select(Ext_PlayerPlaystyle)).first()
            if not playstyle:
                return True
            if playstyle.monthly_upload_count >= MAX_DEMOS_PER_MONTH:
                return False
            if playstyle.total_upload_count >= MAX_TOTAL_DEMOS_PER_USER:
                return False
        return True
