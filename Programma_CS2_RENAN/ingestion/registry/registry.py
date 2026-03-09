import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Set

from filelock import FileLock

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.demo_registry")


class DemoRegistry:
    def __init__(self, registry_path: Path):
        self.registry_path = registry_path
        self._lock = threading.Lock()  # R3-08: thread-safe read/write
        self._file_lock = FileLock(str(registry_path) + ".lock")  # R3-08: cross-process safety
        self._load()

    def _load(self):
        # DS-08: Acquire both locks in consistent order (thread lock → file lock)
        # to prevent races where _save() writes the file while _load() reads it.
        with self._lock:
            with self._file_lock:
                data = _execute_registry_load(self.registry_path)
            # F6-20: Convert list → set for O(1) membership checks.
            # JSON serializes as list; we deserialize as set internally.
            self._processed: Set[str] = set(data.get("processed_demos", []))

    def _save(self):
        # R3-08: caller must hold self._lock; file lock for cross-process safety
        with self._file_lock:
            self._save_inner()

    def _save_inner(self):
        # Create backup before overwriting
        if self.registry_path.exists():
            backup_path = self.registry_path.with_suffix(".json.backup")
            try:
                shutil.copy2(self.registry_path, backup_path)
                logger.debug("Registry backup created: %s", backup_path)
            except Exception as e:
                logger.warning("Failed to create registry backup: %s", e)

        # R3-H04: Write-ahead pattern — write to temp file, then atomic rename.
        # Prevents corruption if process crashes mid-write.
        parent = self.registry_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"processed_demos": list(self._processed)}, f, indent=4)
            os.replace(tmp_path, str(self.registry_path))
        except BaseException:
            # Clean up temp file on any failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def is_processed(self, demo_name: str) -> bool:
        with self._lock:
            return demo_name in self._processed  # F6-20: O(1) set lookup

    def mark_processed(self, demo_name: str):
        with self._lock:
            if demo_name not in self._processed:  # F6-20: O(1) set lookup
                self._processed.add(demo_name)
                self._save()


def _execute_registry_load(path):
    """
    Load demo registry with backup recovery.

    If registry is corrupted, attempts to restore from .backup file.
    Only resets to empty if both primary and backup are unavailable.
    """
    if not path.exists():
        logger.info("Registry does not exist, creating new: %s", path)
        return {"processed_demos": []}

    # Try loading primary registry
    try:
        with open(path, "r") as f:
            data = json.load(f)
            logger.debug(
                "Registry loaded: %s demos processed", len(data.get("processed_demos", []))
            )
            return data
    except json.JSONDecodeError as e:
        logger.error("Registry file corrupted (JSON decode error): %s", e)
    except Exception as e:
        logger.error("Failed to load registry: %s", e)

    # Primary corrupted - attempt backup recovery
    backup_path = path.with_suffix(".json.backup")
    if backup_path.exists():
        try:
            with open(backup_path, "r") as f:
                data = json.load(f)
                logger.warning(
                    "Registry recovered from backup: %s demos", len(data.get("processed_demos", []))
                )
                # Restore backup to primary
                shutil.copy2(backup_path, path)
                return data
        except Exception as e:
            logger.error("Backup recovery also failed: %s", e)

    # Both primary and backup failed - reset to empty
    logger.critical("Registry reset to empty - all demo history lost!")
    return {"processed_demos": []}
