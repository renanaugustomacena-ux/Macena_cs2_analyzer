import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from Programma_CS2_RENAN.backend.ingestion.resource_manager import ResourceManager
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import CoachState, IngestionTask
from Programma_CS2_RENAN.backend.storage.state_manager import state_manager
from Programma_CS2_RENAN.backend.storage.storage_manager import StorageManager
from Programma_CS2_RENAN.core.config import refresh_settings
from Programma_CS2_RENAN.observability.logger_setup import get_logger
from Programma_CS2_RENAN.run_ingestion import _ingest_single_demo, _queue_files

logger = get_logger("cs2analyzer.ingest_manager")


class IngestMode(Enum):
    SINGLE = "single"
    CONTINUOUS = "continuous"
    TIMED = "timed"


class IngestionManager:
    """
    Operator-governed Ingestion Controller.
    Unified queue processor with re-scan loop for TIMED/CONTINUOUS modes.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._stop_requested = False
        self._is_running = False
        self._current_file = None
        self._phase = "idle"  # idle / discovering / processing N/M: file / waiting Xm
        self._total_found = 0
        self._mode = IngestMode.CONTINUOUS
        # F5-32: Default 30-minute re-scan interval. Override via set_mode(interval=N)
        # or expose via get_setting("INGEST_INTERVAL_MINUTES", default=30) if needed.
        self._interval_minutes = 30
        # F5-35: Event-based stop signal — avoids 1-second polling in wait loops.
        self._stop_event = threading.Event()
        self.db_manager = get_db_manager()
        self.storage = StorageManager()

    def set_mode(self, mode: IngestMode, interval: int = 30):
        self._mode = mode
        self._interval_minutes = interval

    def scan_all(self, high_priority: bool = False):
        """Universal entry point: Scans EVERYTHING."""
        with self._lock:
            if self._is_running:
                logger.warning("IngestionManager: Digester already active.")
                return
            self._is_running = True
            self._stop_requested = False

        threading.Thread(target=self._run_unified_cycle, args=(high_priority,), daemon=True).start()

    def stop(self):
        self._stop_requested = True
        self._stop_event.set()  # F5-35: Unblock Event.wait() calls immediately

    def get_status(self) -> Dict:
        from sqlmodel import func, select

        with self.db_manager.get_session() as session:
            queued = session.exec(
                select(func.count(IngestionTask.id)).where(IngestionTask.status == "queued")
            ).one()
            processing = session.exec(
                select(func.count(IngestionTask.id)).where(IngestionTask.status == "processing")
            ).one()
            failed = session.exec(
                select(func.count(IngestionTask.id)).where(IngestionTask.status == "failed")
            ).one()

        # NEW: Get real-time progress from StateManager
        state = state_manager.get_state()
        progress = state.parsing_progress if state else 0.0

        return {
            "is_running": self._is_running,
            "mode": self._mode.value,
            "current_file": self._current_file,
            "phase": self._phase,
            "total_found": self._total_found,
            "queued": queued,
            "processing": processing,
            "failed": failed,
            "interval": self._interval_minutes,
            "progress": progress,  # 0-100
        }

    def _run_unified_cycle(self, high_priority: bool):
        logger.info(
            "IngestionManager: Starting digestion cycle (mode=%s, interval=%sm).",
            self._mode.value,
            self._interval_minutes,
        )
        try:
            refresh_settings()

            while not self._stop_requested:
                # --- DISCOVERY PHASE ---
                self._phase = "discovering"
                all_new_files = []
                for is_pro in [False, True]:
                    demo_files = self.storage.list_new_demos(is_pro)
                    if demo_files:
                        for f in demo_files:
                            all_new_files.append((f, is_pro))

                total_files = len(all_new_files)
                self._total_found = total_files

                if total_files == 0:
                    logger.info("IngestionManager: No new files found.")
                else:
                    logger.info(
                        "IngestionManager: Found %s files to process sequentially.", total_files
                    )

                    # --- PROCESSING PHASE (one-by-one) ---
                    for idx, (demo_path, is_pro) in enumerate(all_new_files, 1):
                        if self._stop_requested:
                            logger.info("IngestionManager: Stop requested during processing.")
                            break

                        self._phase = f"processing {idx}/{total_files}: {demo_path.name}"
                        logger.info(
                            "IngestionManager: file %s/%s: %s", idx, total_files, demo_path.name
                        )

                        with self.db_manager.get_session() as session:
                            _queue_files(session, [demo_path], is_pro)
                            session.commit()

                        self._process_unified_queue(high_priority)

                        if idx < total_files and not self._stop_requested:
                            time.sleep(5)

                # --- MODE-DEPENDENT LOOP CONTROL ---
                if self._mode == IngestMode.SINGLE:
                    break

                if self._mode == IngestMode.TIMED:
                    self._phase = f"waiting {self._interval_minutes}m"
                    logger.info(
                        "IngestionManager: TIMED wait %sm before re-scan...",
                        self._interval_minutes,
                    )
                    # F5-35: Event.wait() blocks until stop or timeout — no 1s polling.
                    self._stop_event.wait(timeout=self._interval_minutes * 60)
                    if self._stop_requested:
                        break
                    self._stop_event.clear()  # Reset for next wait cycle
                    continue

                # CONTINUOUS: re-scan immediately (small pause to avoid busy-loop)
                if total_files == 0:
                    self._phase = "waiting 30s"
                    # F5-35: Event.wait() — wakes immediately on stop signal.
                    self._stop_event.wait(timeout=30)
                    if not self._stop_requested:
                        self._stop_event.clear()  # Reset for next wait cycle

        except Exception as e:
            logger.error("IngestionManager: Cycle Error: %s", e)
        finally:
            with self._lock:
                self._is_running = False
                self._current_file = None
                self._phase = "idle"
                self._total_found = 0
            logger.info("IngestionManager: Digestion stopped.")

    def _process_unified_queue(self, high_priority: bool):
        from sqlmodel import select

        if high_priority:
            ResourceManager.set_high_priority()
        else:
            ResourceManager.set_low_priority()

        while not self._stop_requested:
            # Fetch NEXT task regardless of type (FIFO)
            with self.db_manager.get_session() as session:
                task = session.exec(
                    select(IngestionTask)
                    .where(IngestionTask.status == "queued")
                    .order_by(IngestionTask.id)
                ).first()

                if not task:
                    logger.info("IngestionManager: Queue drained.")
                    break

                task.status = "processing"
                session.add(task)
                session.commit()
                session.refresh(task)

                # Capture task details for processing outside session
                demo_path = Path(task.demo_path)
                is_pro = task.is_pro
                task_id = task.id

            self._current_file = demo_path.name
            logger.info("Ingesting: %s (Pro=%s)", self._current_file, is_pro)
            state_manager.update_status("digester", "Processing", f"Parsing {self._current_file}")

            # Reset Progress
            state_manager.update_parsing_progress(0.0)

            # Execute real ingestion
            success, msg = _ingest_single_demo(self.db_manager, self.storage, demo_path, is_pro)

            with self.db_manager.get_session() as session:
                # Re-fetch task to avoid stale object issues
                t = session.get(IngestionTask, task_id)
                if t:
                    t.status = "completed" if success else "failed"
                    t.error_message = msg
                    session.add(t)
                    session.commit()

            # Mode Logic: SINGLE breaks after first task; others drain the queue
            if self._mode == IngestMode.SINGLE:
                logger.info("IngestionManager: Single mode complete.")
                break
