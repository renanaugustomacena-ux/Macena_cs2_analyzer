import threading
from datetime import datetime, timezone
from enum import Enum

from sqlmodel import select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import CoachState, CoachStatus, ServiceNotification
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.state_manager")


# R2-13: Typed enum for daemon names — prevents typo-driven bugs in status updates.
class DaemonName(str, Enum):
    HUNTER = "hunter"
    DIGESTER = "digester"
    TEACHER = "teacher"
    GLOBAL = "global"


class StateManager:
    """
    Centralized DAO for managing Global Application State (CoachState).
    Prevents race conditions and ensures consistent status updates across daemons.
    """

    def __init__(self):
        self.db = get_db_manager()
        self._lock = threading.Lock()

    def get_state(self) -> CoachState:
        """
        Retrieves the singleton CoachState. Creates it if it doesn't exist.
        P0-04: Lock acquired to prevent duplicate row creation under concurrent access.
        SM-01: Expunge before return so the object is safely detached from the session.
        """
        with self._lock, self.db.get_session() as session:
            state = session.exec(select(CoachState)).first()
            if not state:
                state = CoachState()
                session.add(state)
                session.commit()
                session.refresh(state)
            session.expunge(state)
            return state

    def update_status(self, daemon: str, status: str, detail: str = ""):
        """
        Updates the status of a specific daemon.

        Args:
            daemon: DaemonName value or string ('hunter', 'digester', 'teacher', 'global')
            status: Status string (e.g., 'Running', 'Idle', 'Error')
            detail: Optional detail message
        """
        # R2-13: Normalize to string value (accepts both DaemonName enum and raw str)
        daemon_key = daemon.value if isinstance(daemon, DaemonName) else daemon
        try:
            with self._lock, self.db.get_session() as session:
                state = session.exec(select(CoachState)).first()
                if not state:
                    state = CoachState()
                    session.add(state)

                if daemon_key == DaemonName.HUNTER:
                    state.hltv_status = status
                elif daemon_key == DaemonName.DIGESTER:
                    state.ingest_status = status
                elif daemon_key == DaemonName.TEACHER:
                    state.ml_status = status
                elif daemon_key == DaemonName.GLOBAL:
                    valid_statuses = {s.value for s in CoachStatus}
                    if status not in valid_statuses:
                        raise ValueError(
                            f"Invalid global status {status!r}. Valid values: {valid_statuses}"
                        )
                    state.status = status

                if detail:
                    state.detail = detail

                state.last_updated = datetime.now(timezone.utc)
                session.add(state)
                session.commit()

        except Exception as e:
            logger.error("Failed to update status for %s: %s", daemon, e)

    def update_parsing_progress(self, progress: float):
        """Updates the progress percentage of the current file (0.0 - 100.0)."""
        try:
            with self._lock, self.db.get_session() as session:
                state = session.exec(select(CoachState)).first()
                if state:
                    state.parsing_progress = progress
                    state.last_updated = datetime.now(timezone.utc)
                    session.add(state)
                    session.commit()
        except Exception as e:
            logger.error("Failed to update parsing progress: %s", e)

    def update_training_progress(
        self, epoch: int, total_epochs: int, train_loss: float, val_loss: float, eta: float = 0.0
    ):
        """Atomic update for training telemetry."""
        try:
            with self._lock, self.db.get_session() as session:
                state = session.exec(select(CoachState)).first()
                if state:
                    state.current_epoch = epoch
                    state.total_epochs = total_epochs
                    state.train_loss = train_loss
                    state.val_loss = val_loss
                    state.eta_seconds = eta
                    state.last_updated = datetime.now(timezone.utc)
                    session.add(state)
                    session.commit()
        except Exception as e:
            # Don't crash training for telemetry failure
            logger.warning("Telemetry update failed: %s", e)

    def heartbeat(self):
        """Updates the last_heartbeat timestamp to indicate liveness."""
        try:
            with self._lock, self.db.get_session() as session:
                state = session.exec(select(CoachState)).first()
                if state:
                    state.last_heartbeat = datetime.now(timezone.utc)
                    session.add(state)
                    session.commit()
        except Exception as e:
            logger.error("Heartbeat failed: %s", e)

    def set_error(self, daemon: str, message: str):
        """
        Sets a daemon to Error state and logs a notification.
        """
        self.update_status(daemon, "Error", detail=message)
        self.add_notification(daemon, "ERROR", message)
        logger.error("[%s] Error: %s", daemon.upper(), message)

    def add_notification(self, daemon: str, severity: str, message: str):
        """Adds a service notification for the UI."""
        try:
            with self.db.get_session() as session:
                note = ServiceNotification(daemon=daemon, severity=severity, message=message)
                session.add(note)
                session.commit()
        except Exception as e:
            logger.error("Failed to add notification: %s", e)

    def prune_old_notifications(self, max_age_days: int = 30) -> int:
        """P2-06: Delete notifications older than max_age_days to prevent unbounded growth.

        Returns:
            Number of notifications deleted.
        """
        from datetime import timedelta

        from sqlmodel import delete

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        try:
            with self.db.get_session() as session:
                stmt = delete(ServiceNotification).where(
                    ServiceNotification.created_at < cutoff
                )
                result = session.exec(stmt)
                session.commit()
                deleted = result.rowcount  # type: ignore[union-attr]
                if deleted:
                    logger.info("Pruned %d old notifications (older than %d days)", deleted, max_age_days)
                return deleted
        except Exception as e:
            logger.error("Failed to prune notifications: %s", e)
            return 0

    def get_status(self, daemon: str) -> dict:
        """Retrieves the current status and detail for a daemon."""
        daemon_key = daemon.value if isinstance(daemon, DaemonName) else daemon
        try:
            with self.db.get_session() as session:
                state = session.exec(select(CoachState)).first()
                if not state:
                    return {"status": "Unknown", "detail": ""}

                status = "Unknown"
                if daemon_key == DaemonName.HUNTER:
                    status = state.hltv_status
                elif daemon_key == DaemonName.DIGESTER:
                    status = state.ingest_status
                elif daemon_key == DaemonName.TEACHER:
                    status = state.ml_status
                elif daemon_key == DaemonName.GLOBAL:
                    status = state.status

                return {"status": status, "detail": state.detail or ""}
        except Exception as e:
            logger.error("Failed to get status for %s: %s", daemon, e)
            return {"status": "Error", "detail": str(e)}


# P0-04: Lazy singleton with double-checked locking (AR-5).
# Replaces module-level `state_manager = StateManager()` which called
# get_db_manager() at import time, before init_database() was guaranteed.
from typing import Optional

_state_manager: Optional[StateManager] = None
_state_manager_lock = threading.Lock()


def get_state_manager() -> StateManager:
    """Thread-safe lazy singleton factory for StateManager."""
    global _state_manager
    if _state_manager is None:
        with _state_manager_lock:
            if _state_manager is None:
                _state_manager = StateManager()
    return _state_manager
