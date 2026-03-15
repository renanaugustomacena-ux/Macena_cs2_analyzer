"""MatchHistoryViewModel — QObject port of data_viewmodels.MatchHistoryViewModel."""

from threading import Event

from PySide6.QtCore import QObject, QThreadPool, Signal

from Programma_CS2_RENAN.apps.qt_app.core.worker import Worker
from Programma_CS2_RENAN.core.config import get_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_match_history_vm")


class MatchHistoryViewModel(QObject):
    """Loads user match list in background. Signals auto-marshal to main thread."""

    matches_changed = Signal(list)
    is_loading_changed = Signal(bool)
    error_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_loading = False
        self._cancel = Event()

    @property
    def is_loading(self):
        return self._is_loading

    def load_matches(self):
        if self._is_loading:
            return
        self._cancel.clear()
        self._is_loading = True
        self.is_loading_changed.emit(True)
        self.error_changed.emit("")

        worker = Worker(self._bg_load)
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def cancel(self):
        self._cancel.set()

    def _bg_load(self):
        player = get_setting("CS2_PLAYER_NAME", "")
        if not player:
            raise ValueError(
                "Player name not set. Go to Settings \u2192 Profile to set your in-game name."
            )

        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

        with get_db_manager().get_session() as session:
            results = session.exec(
                select(PlayerMatchStats)
                .where(
                    PlayerMatchStats.player_name == player,
                    PlayerMatchStats.is_pro == False,  # noqa: E712
                )
                .order_by(PlayerMatchStats.match_date.desc())
                .limit(50)
            ).all()
            match_data = [
                {
                    "demo_name": m.demo_name,
                    "match_date": m.match_date,
                    "rating": m.rating,
                    "avg_kills": m.avg_kills,
                    "avg_deaths": m.avg_deaths,
                    "avg_adr": m.avg_adr,
                    "avg_kast": m.avg_kast,
                    "kd_ratio": m.kd_ratio,
                }
                for m in results
            ]

        if self._cancel.is_set():
            return []
        return match_data

    def _on_loaded(self, data):
        self._is_loading = False
        self.is_loading_changed.emit(False)
        if data is not None:
            self.matches_changed.emit(data)

    def _on_error(self, msg):
        logger.error("match_history_vm.load_failed: %s", msg)
        self._is_loading = False
        self.is_loading_changed.emit(False)
        self.error_changed.emit(str(msg))
