import logging
import os
import sys
import threading
import time

# F6-06: sys.path bootstrap — required only when this daemon is executed directly as a script
# (e.g. `python session_engine.py`). With proper package installation (pip install -e .)
# and `python -m` invocation this block is a no-op. Technical debt: remove when entrypoints
# are configured in pyproject.toml/setup.py.
current = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(os.path.dirname(current)))
if root not in sys.path:
    sys.path.insert(0, root)

from pathlib import Path

from sqlmodel import select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database
from Programma_CS2_RENAN.backend.storage.db_models import (
    CoachState,
    IngestionTask,
    PlayerMatchStats,
    PlayerProfile,
    PlayerTickState,
)
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.session_engine")

# File logging for session engine subprocess
try:
    from Programma_CS2_RENAN.core.config import LOG_DIR

    log_file = os.path.join(LOG_DIR, "session_engine.log")
    fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.info("Session Engine File Logging Initialized")
except Exception as e:
    logger.warning("Failed to setup file logging: %s", e)


# if project_root not in sys.path:
#     sys.path.insert(0, project_root)
# from Programma_CS2_RENAN.core.config import stabilize_paths
# project_root = stabilize_paths()

# ResourceManager is used in _digester_daemon_loop
from Programma_CS2_RENAN.backend.ingestion.resource_manager import ResourceManager

# STOP_SIGNAL = SCRIPT_DIR / "session_engine.stop" # Removed

# Event-driven signaling for daemon coordination
_shutdown_event = threading.Event()
_work_available_event = threading.Event()


def _monitor_stdin():
    """Monitor standard input for termination signal or pipe close (Parent Death)."""
    try:
        while not _shutdown_event.is_set():
            line = sys.stdin.readline()
            if not line:  # EOF (Pipe closed)
                logger.warning("Stdin Closed (Parent-Death Detected). Shutting down...")
                _shutdown_event.set()
                break
            if line.strip() == "STOP":
                logger.info("Received STOP command. Shutting down...")
                _shutdown_event.set()
                break
    except Exception as e:
        logger.warning("Stdin monitor error: %s", e)
        _shutdown_event.set()


def signal_work_available():
    """Signal daemons that new work is available. Called by watcher after queueing."""
    _work_available_event.set()


def run_session_loop():
    """Started by main.py, dies when main.py dies (via stdin pipe closure)."""
    from Programma_CS2_RENAN.backend.storage.state_manager import state_manager

    logger.info("Session Engine Starting [PID: %s]", os.getpid())

    # Ensure DB tables exist
    from Programma_CS2_RENAN.core.config import DATABASE_URL

    logger.debug("Session Engine using DATABASE_URL: %s", DATABASE_URL)
    init_database()

    # --- TASK 5.4: Automated Backup Strategy ---
    try:
        from Programma_CS2_RENAN.backend.storage.backup_manager import BackupManager

        bm = BackupManager()
        if bm.should_run_auto_backup():
            logger.info("Running Daily Automated Backup...")
            bm.create_checkpoint(label="startup_auto")
        else:
            logger.info("Daily Backup already exists. Skipping.")
    except Exception as e:
        logger.error("Backup Routine Failed: %s", e)
        # Non-blocking: We continue ensuring core functionality works

    # Start IPC Monitor (The Life-Line)
    threading.Thread(target=_monitor_stdin, daemon=True).start()

    # Reset Status via DAO
    state_manager.update_status("global", "Running", "Session Engine Started")
    _cleanup_zombie_tasks()

    # Start Daemons
    watcher = None
    try:
        from Programma_CS2_RENAN.backend.ingestion.watcher import IngestionWatcher

        watcher = IngestionWatcher()
        watcher.start()
    except Exception as e:
        logger.error("Failed to start IngestionWatcher: %s", e)

    threading.Thread(target=_scanner_daemon_loop, daemon=True).start()
    threading.Thread(target=_digester_daemon_loop, daemon=True).start()
    threading.Thread(target=_teacher_daemon_loop, daemon=True).start()
    threading.Thread(target=_pulse_daemon_loop, daemon=True).start()

    # Main Keep-Alive (Event Driven)
    try:
        while not _shutdown_event.is_set():
            _shutdown_event.wait(timeout=1.0)

    except KeyboardInterrupt:
        logger.info("Session Engine stopping via KeyboardInterrupt")
    except Exception as e:
        logger.critical("Session Engine Crashed: %s", e)
    finally:
        _shutdown_event.set()  # Signal all daemons to stop
        if watcher:
            watcher.stop()
        state_manager.update_status("global", "Offline", "Session Engine Exited")
        logger.info("Session Engine Exiting")


def _cleanup_zombie_tasks():
    """Reset any tasks left in 'processing' state from a previous crash."""
    db = get_db_manager()
    try:
        from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask

        with db.get_session() as s:
            zombies = s.exec(
                select(IngestionTask).where(IngestionTask.status == "processing")
            ).all()
            if zombies:
                logger.warning("Found %s zombie tasks. Resetting to 'queued'.", len(zombies))
                for task in zombies:
                    task.status = "queued"
                    s.add(task)
                s.commit()
    except Exception as e:
        logger.error("Failed to cleanup zombie tasks: %s", e)


def _scanner_daemon_loop():
    """DAEMON A: File Scanner (The Gatekeeper)"""
    # Responsibility: File System -> DB Queue (Ticket Creation)
    # Strictly isolated from processing logic.
    from Programma_CS2_RENAN.backend.storage.state_manager import state_manager
    from Programma_CS2_RENAN.core.config import refresh_settings
    from Programma_CS2_RENAN.run_ingestion import process_new_demos

    last_scan = 0
    SCAN_INTERVAL = 10  # Seconds between scans

    logger.info("Scanner Daemon Started")
    state_manager.update_status("hunter", "Active", "Scanner Running")

    while not _shutdown_event.is_set():
        try:
            # 1. Reload Settings to catch UI changes to folder paths
            refresh_settings()

            # 2. Check Play/Pause State (Global Master Switch)
            state = state_manager.get_state()
            is_active = state.ingest_status == "Scanning"

            # 3. Running Scan (Only if Active)
            current_time = time.time()
            if is_active and (current_time - last_scan > SCAN_INTERVAL):
                logger.debug("[Scanner] Active Cycle")
                state_manager.update_status("hunter", "Scanning")

                try:
                    # is_pro=True scan
                    process_new_demos(is_pro=True, limit=0)
                    # is_pro=False scan
                    process_new_demos(is_pro=False, limit=0)
                except Exception as scan_err:
                    logger.error("[Scanner] Scan Cycle Failed: %s", scan_err)
                    state_manager.set_error("hunter", str(scan_err))

                state_manager.update_status("hunter", "Active")
                last_scan = time.time()

            # Idle Sleep
            time.sleep(1)

        except Exception as e:
            logger.error("Scanner Daemon Error: %s", e)
            time.sleep(5)  # Backoff on error

    logger.info("Scanner Daemon Stopped")


def _digester_daemon_loop():
    """DAEMON B: Processing Worker (Queue Consumer)"""
    # Responsibility: DB Queue -> Match Stats (Heavy Lifting)
    # Does NOT touch the file system scanning logic.
    from Programma_CS2_RENAN.backend.storage.state_manager import state_manager
    from Programma_CS2_RENAN.backend.storage.storage_manager import StorageManager
    from Programma_CS2_RENAN.run_ingestion import process_queued_tasks

    db = get_db_manager()
    storage = StorageManager()

    logger.info("Digester Daemon Started")
    state_manager.update_status("digester", "Idle")

    # Prove Priority on Startup
    ResourceManager.log_current_priority()

    while not _shutdown_event.is_set():
        try:
            # Check for High Performance Mode requirement
            # (If queue is large, we might want to boost priority,
            # but for now we stick to simple queue consumption)

            # Process Queues
            # We process 1 item at a time to remain responsive to shutdown signals
            processed_pro = process_queued_tasks(
                db, storage, is_pro=True, high_priority=False, limit=1
            )
            processed_user = process_queued_tasks(
                db, storage, is_pro=False, high_priority=False, limit=1
            )

            if processed_pro == 0 and processed_user == 0:
                state_manager.update_status("digester", "Idle")
                _work_available_event.wait(timeout=2.0)
                _work_available_event.clear()
            else:
                state_manager.update_status("digester", "Processing")

        except Exception as e:
            logger.error("Digester Error: %s", e)
            state_manager.set_error("digester", str(e))
            time.sleep(5)

    logger.info("Digester Daemon Stopped")


def _teacher_daemon_loop():
    """DAEMON C: Cognitive ML Trainer"""
    from Programma_CS2_RENAN.backend.storage.state_manager import state_manager

    state_manager.update_status("teacher", "Idle")

    # Cache baseline snapshot for meta-shift detection (Proposal 11)
    _last_baseline = _get_current_baseline_snapshot()

    while not _shutdown_event.is_set():
        try:
            trigger_count = _check_retraining_trigger()
            if trigger_count > 0:
                state_manager.update_status("teacher", "Learning")
                from Programma_CS2_RENAN.backend.nn.coach_manager import CoachTrainingManager

                CoachTrainingManager().run_full_cycle()

                # Update sample count AFTER successful training (not before)
                _commit_trained_sample_count(trigger_count)

                # Meta-shift detection after retraining (Proposal 11)
                _last_baseline = _check_meta_shift(_last_baseline)

                # G-07: wire belief calibration to Teacher daemon after each retraining cycle
                try:
                    from Programma_CS2_RENAN.backend.analysis.belief_model import (
                        AdaptiveBeliefCalibrator,
                    )

                    calibrator = AdaptiveBeliefCalibrator()
                    calibrator.auto_calibrate(get_db_manager())
                    logger.info("Belief calibration completed after retraining")
                except Exception as cal_err:
                    logger.warning("Belief calibration non-fatal: %s", cal_err)
            else:
                logger.debug("Teacher: retraining not triggered this cycle")
        except Exception as e:
            logger.error("Teacher Error: %s", e)
            state_manager.set_error("teacher", str(e))

        # Check stop signal more frequently than 300s sleep
        for _ in range(300):
            if _shutdown_event.is_set():
                break
            time.sleep(1)

    logger.info("Teacher Daemon Stopped")


def _pulse_daemon_loop():
    """Update Heartbeat"""
    from Programma_CS2_RENAN.backend.storage.state_manager import state_manager

    while not _shutdown_event.is_set():
        try:
            state_manager.heartbeat()
        except Exception as e:
            logger.warning("Heartbeat failed: %s", e)
        time.sleep(5)


def _get_current_baseline_snapshot() -> dict:
    """Capture current temporal baseline for later comparison (Proposal 11)."""
    try:
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            TemporalBaselineDecay,
        )

        decay = TemporalBaselineDecay()
        return decay.get_temporal_baseline()
    except Exception as e:
        logger.debug("Baseline snapshot unavailable: %s", e)
        return {}


def _check_meta_shift(old_baseline: dict) -> dict:
    """Compare old baseline against current temporal baseline.

    Logs any detected meta shifts for observability.
    Returns the new baseline snapshot (for next comparison cycle).
    """
    try:
        from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
            TemporalBaselineDecay,
        )

        decay = TemporalBaselineDecay()
        new_baseline = decay.get_temporal_baseline()

        if old_baseline and new_baseline:
            shifted = decay.detect_meta_shift(old_baseline, new_baseline)
            if shifted:
                logger.info(
                    "Meta-shift detected after retraining: %d metrics shifted (%s)",
                    len(shifted),
                    ", ".join(shifted[:5]),
                )

        return new_baseline
    except Exception as e:
        logger.warning("Meta-shift detection failed (non-fatal): %s", e)
        return old_baseline


def _check_retraining_trigger() -> int:
    """Check if retraining should be triggered based on new pro sample count.

    Returns the pro_count (> 0) when retraining is needed, 0 otherwise.
    Does NOT update the DB — caller must call _commit_trained_sample_count()
    after successful training.
    """
    from sqlmodel import func

    from Programma_CS2_RENAN.backend.storage.state_manager import state_manager

    db = get_db_manager()

    with db.get_session("default") as s_telemetry:
        pro_count = s_telemetry.exec(
            select(func.count(PlayerMatchStats.id)).where(PlayerMatchStats.is_pro == True)
        ).one()

    state = state_manager.get_state()
    last_count = state.last_trained_sample_count

    if pro_count >= (last_count * 1.10) or (last_count == 0 and pro_count >= 10):
        return pro_count

    return 0


def _commit_trained_sample_count(count: int) -> None:
    """Persist the trained sample count AFTER successful training."""
    db = get_db_manager()
    try:
        with db.get_session() as s:
            st = s.exec(select(CoachState)).first()
            if st:
                st.last_trained_sample_count = count
                s.add(st)
                s.commit()  # F6-03: persist trained sample count; context manager does not auto-commit here
    except Exception as e:
        logger.error("Failed to commit trained sample count: %s", e)


if __name__ == "__main__":
    run_session_loop()
