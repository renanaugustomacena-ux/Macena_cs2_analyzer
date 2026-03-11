import os
import threading
import time
from typing import Dict

from sqlalchemy import select
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import CoachState, IngestionTask
from Programma_CS2_RENAN.core.config import DEFAULT_DEMO_PATH, PRO_DEMO_PATH
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.watcher")

# File stability constants
FILE_STABILITY_CHECK_INTERVAL = 1.0  # seconds between size checks
FILE_STABILITY_REQUIRED_CHECKS = 2  # file must be stable for this many checks
# R3-M20: Use the canonical MIN_DEMO_SIZE from demo_format_adapter to prevent
# accepting files that the adapter will reject downstream.
from Programma_CS2_RENAN.backend.data_sources.demo_format_adapter import MIN_DEMO_SIZE as FILE_MINIMUM_SIZE
# F6-16: Maximum total stability attempts before giving up (~30 seconds at 1s interval)
_MAX_STABILITY_ATTEMPTS = 30


class DemoFileHandler(FileSystemEventHandler):
    """Handles file system events for .dem files with file stability debouncing."""

    def __init__(self, is_pro_folder=False):
        self.is_pro_folder = is_pro_folder
        self.db_manager = get_db_manager()
        self._pending_files: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".dem"):
            return

        logger.info("New demo detected: %s (waiting for file stability...)", event.src_path)
        self._schedule_stability_check(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        if not event.dest_path.endswith(".dem"):
            return

        logger.info("Demo moved/renamed: %s (waiting for file stability...)", event.dest_path)
        self._schedule_stability_check(event.dest_path)

    def _schedule_stability_check(self, file_path: str):
        """Schedule a delayed stability check for the file."""
        with self._lock:
            # Cancel any existing timer for this file
            if file_path in self._pending_files:
                self._pending_files[file_path].cancel()

            # Schedule new stability check; attempt_count=0 on first schedule
            timer = threading.Timer(
                FILE_STABILITY_CHECK_INTERVAL,
                self._check_file_stability,
                args=[file_path, 0, 0, 0],  # (file_path, last_size, stable_count, attempt_count)
            )
            timer.daemon = True
            self._pending_files[file_path] = timer
            timer.start()

    def _check_file_stability(
        self, file_path: str, last_size: int, stable_count: int, attempt_count: int
    ):
        """Check if file size has stabilized (not being written to)."""
        try:
            # F6-16: Guard against infinite timer accumulation when file stays locked.
            attempt_count += 1
            if attempt_count > _MAX_STABILITY_ATTEMPTS:
                logger.warning(
                    "File stability check exceeded max attempts (%s), giving up: %s",
                    _MAX_STABILITY_ATTEMPTS,
                    file_path,
                )
                with self._lock:
                    self._pending_files.pop(file_path, None)
                return

            if not os.path.exists(file_path):
                logger.warning("File no longer exists: %s", file_path)
                with self._lock:
                    self._pending_files.pop(file_path, None)
                return

            # DS-02: wrap in try-except to handle file disappearing between
            # the existence check above and the size read (TOCTOU race).
            try:
                current_size = os.path.getsize(file_path)
            except OSError:
                logger.warning("DS-02: File disappeared during stability check: %s", file_path)
                with self._lock:
                    self._pending_files.pop(file_path, None)
                return

            # Check if size is stable
            if current_size == last_size and current_size > 0:
                stable_count += 1
            else:
                stable_count = 0

            if stable_count >= FILE_STABILITY_REQUIRED_CHECKS:
                # File is stable - verify minimum size and try exclusive lock
                if current_size < FILE_MINIMUM_SIZE:
                    logger.warning(
                        "File too small (%s bytes), skipping: %s", current_size, file_path
                    )
                    with self._lock:
                        self._pending_files.pop(file_path, None)
                    return

                # Try to open file to verify it's not locked
                if self._is_file_accessible(file_path):
                    logger.info("File stable and accessible, queueing: %s", file_path)
                    self._queue_file(file_path)
                    with self._lock:
                        self._pending_files.pop(file_path, None)
                else:
                    # File still locked, continue waiting
                    logger.debug("File still locked, will retry: %s", file_path)
                    self._reschedule_check(file_path, current_size, 0, attempt_count)
            else:
                # Not stable yet, schedule another check
                self._reschedule_check(file_path, current_size, stable_count, attempt_count)

        except Exception as e:
            logger.error("Error checking file stability for %s: %s", file_path, e)
            with self._lock:
                self._pending_files.pop(file_path, None)

    def _reschedule_check(
        self, file_path: str, current_size: int, stable_count: int, attempt_count: int
    ):
        """Reschedule stability check with updated state."""
        with self._lock:
            timer = threading.Timer(
                FILE_STABILITY_CHECK_INTERVAL,
                self._check_file_stability,
                args=[file_path, current_size, stable_count, attempt_count],
            )
            timer.daemon = True
            self._pending_files[file_path] = timer
            timer.start()

    def _is_file_accessible(self, file_path: str) -> bool:
        """Check if file can be opened (not locked by writer)."""
        try:
            with open(file_path, "rb") as _:  # F6-24: read-only check; avoids timestamp mutation
                pass
            return True
        except (PermissionError, OSError):
            return False

    def _queue_file(self, file_path):
        """Thread-safe queue injection."""
        try:
            # IM-01: Final existence check right before DB insertion to close TOCTOU gap
            if not os.path.exists(file_path):
                logger.warning("IM-01: File disappeared before enqueue: %s", file_path)
                return

            # Check for duplicate
            with self.db_manager.get_session() as session:
                existing = session.exec(
                    select(IngestionTask).where(IngestionTask.demo_path == file_path)
                ).first()

                if existing:
                    logger.debug("Task already exists for: %s", file_path)
                    return

                new_task = IngestionTask(
                    demo_path=file_path, is_pro=self.is_pro_folder, status="queued"
                )
                session.add(new_task)
                session.commit()

                logger.info("Queued ingestion task: %s", os.path.basename(file_path))

                # Signal session_engine that work is available (event-driven wake-up)
                try:
                    from Programma_CS2_RENAN.core.session_engine import signal_work_available

                    signal_work_available()
                except ImportError:
                    pass  # Session engine not running in this context

        except Exception as e:
            logger.error("Failed to queue file %s: %s", file_path, e)


class IngestionWatcher:
    """Manages the Watchdog functionality."""

    def __init__(self):
        self.observer = Observer()
        self.user_handler = DemoFileHandler(is_pro_folder=False)
        self.pro_handler = DemoFileHandler(is_pro_folder=True)
        self.running = False

    def start(self):
        if self.running:
            return

        # Ensure directories exist
        os.makedirs(DEFAULT_DEMO_PATH, exist_ok=True)
        os.makedirs(PRO_DEMO_PATH, exist_ok=True)

        # Schedule watchers
        self.observer.schedule(self.user_handler, DEFAULT_DEMO_PATH, recursive=False)
        self.observer.schedule(self.pro_handler, PRO_DEMO_PATH, recursive=False)

        self.observer.start()
        self.running = True
        logger.info("Ingestion Watchdog Started (Event-Driven Mode)")

    def stop(self):
        if not self.running:
            return
        self.observer.stop()
        self.observer.join()
        self.running = False
        logger.info("Ingestion Watchdog Stopped")
