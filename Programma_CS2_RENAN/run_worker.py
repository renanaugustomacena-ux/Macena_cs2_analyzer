import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import func, select

# Add project root to path
SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = SCRIPT_DIR
sys.path.insert(0, str(PROJECT_ROOT))

from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database
from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask, PlayerMatchStats
from Programma_CS2_RENAN.backend.storage.storage_manager import StorageManager
from Programma_CS2_RENAN.observability.logger_setup import get_logger
from Programma_CS2_RENAN.run_ingestion import _ingest_single_demo

logger = get_logger("cs2analyzer.worker")


def _recover_stale_tasks(db):
    with db.get_session() as session:
        stmt = select(IngestionTask).where(IngestionTask.status == "processing")
        stale_tasks = session.exec(stmt).all()
        for stale in stale_tasks:
            stale.status = "queued"
            session.add(stale)
        session.commit()
        if stale_tasks:
            logger.info("Recovered %s tasks.", len(stale_tasks))


def _fetch_next_task_data(db):
    """Fetches next task and returns data as a dict to avoid DetachedInstanceError."""
    with db.get_session() as session:
        stmt = (
            select(IngestionTask)
            .where(IngestionTask.status == "queued")
            .order_by(IngestionTask.created_at.asc())
        )
        task = session.exec(stmt).first()
        if not task:
            return None
        # Extract data while session is alive
        return {"id": task.id, "is_pro": task.is_pro, "demo_path": task.demo_path}


def _mark_task_status(db, task_id, status):
    with db.get_session() as session:
        t = session.get(IngestionTask, task_id)
        if t:
            t.status = status
            t.updated_at = datetime.now(timezone.utc)
            session.add(t)
            session.commit()


def _should_skip_pro_task(db, is_pro):
    if not is_pro:
        return False
    with db.get_session() as session:
        q_cnt = session.exec(
            select(func.count(IngestionTask.id)).where(
                IngestionTask.is_pro == True, IngestionTask.status == "queued"
            )
        ).one()
        d_cnt = session.exec(
            select(func.count(PlayerMatchStats.id)).where(PlayerMatchStats.is_pro == True)
        ).one()
        return d_cnt == 0 and q_cnt < 10


def _execute_task(db, storage, task_id, demo_path, is_pro):
    _mark_task_status(db, task_id, "processing")
    logger.info("Worker processing: %s", demo_path)

    try:
        from pathlib import Path

        p = Path(demo_path)
        if not p.exists():
            archive_p = p.parent / "processed" / p.name
            if archive_p.exists():
                p = archive_p
            else:
                raise FileNotFoundError(f"Demo file missing: {demo_path}")

        success, message = _ingest_single_demo(db, storage, p, is_pro)

        if success:
            _mark_task_status(db, task_id, "completed")
            logger.info("Task finished: %s", demo_path)
        else:
            _mark_task_status_failed(db, task_id, message)

    except Exception as e:
        logger.error("Task Failed: %s - %s", demo_path, e)
        _mark_task_status_failed(db, task_id, str(e))


def _mark_task_status_failed(db, task_id, error_msg):
    with db.get_session() as session:
        t = session.get(IngestionTask, task_id)
        if t:
            t.status = "failed"
            t.error_message = error_msg
            t.updated_at = datetime.now(timezone.utc)
            session.add(t)
            session.commit()


def _process_next_task_cycle(db, storage):
    task_data = _fetch_next_task_data(db)
    if not task_data:
        return time.sleep(5)

    task_id = task_data["id"]
    is_pro = task_data["is_pro"]
    demo_path = task_data["demo_path"]

    if _should_skip_pro_task(db, is_pro):
        return time.sleep(10)

    _execute_task(db, storage, task_id, demo_path, is_pro)


def run_worker():
    """Background worker with self-healing capabilities."""
    init_database()
    db, storage = get_db_manager(), StorageManager()
    _recover_stale_tasks(db)
    logger.info("Ingestion Worker started. Waiting for tasks...")

    # Shared signal file with hltv_sync_service
    stop_signal = Path(os.path.dirname(os.path.abspath(__file__))) / "hltv_sync.stop"

    while not stop_signal.exists():
        try:
            _process_next_task_cycle(db, storage)
        except Exception as e:
            logger.error("Worker Loop Error: %s", e)
            time.sleep(10)
    logger.info("Worker gracefully shutting down.")


if __name__ == "__main__":
    run_worker()
