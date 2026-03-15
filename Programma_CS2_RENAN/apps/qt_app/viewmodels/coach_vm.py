"""CoachViewModel — loads coaching insights from DB."""

from PySide6.QtCore import QObject, QThreadPool, Signal

from Programma_CS2_RENAN.apps.qt_app.core.worker import Worker
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_coach_vm")


class CoachViewModel(QObject):
    """Loads CoachingInsight rows for the current player."""

    insights_loaded = Signal(list)
    is_loading_changed = Signal(bool)
    error_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_loading = False

    def load_insights(self):
        if self._is_loading:
            return
        self._is_loading = True
        self.is_loading_changed.emit(True)
        self.error_changed.emit("")

        worker = Worker(self._bg_load)
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def _bg_load(self):
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager
        from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight
        from Programma_CS2_RENAN.core.config import get_setting

        player = get_setting("CS2_PLAYER_NAME", "")
        if not player:
            return []

        with get_db_manager().get_session() as session:
            results = session.exec(
                select(CoachingInsight)
                .where(CoachingInsight.player_name == player)
                .order_by(CoachingInsight.created_at.desc())
                .limit(10)
            ).all()
            return [
                {
                    "title": r.title,
                    "message": r.message,
                    "severity": r.severity,
                    "focus_area": r.focus_area,
                    "created_at": str(r.created_at)[:16],
                }
                for r in results
            ]

    def _on_loaded(self, data):
        self._is_loading = False
        self.is_loading_changed.emit(False)
        if data is not None:
            self.insights_loaded.emit(data)

    def _on_error(self, msg):
        logger.error("coach_vm error: %s", msg)
        self._is_loading = False
        self.is_loading_changed.emit(False)
        self.error_changed.emit(str(msg))
