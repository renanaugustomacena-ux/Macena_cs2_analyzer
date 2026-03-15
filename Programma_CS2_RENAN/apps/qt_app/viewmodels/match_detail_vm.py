"""MatchDetailViewModel — QObject port of data_viewmodels.MatchDetailViewModel."""

from PySide6.QtCore import QObject, QThreadPool, Signal

from Programma_CS2_RENAN.apps.qt_app.core.worker import Worker
from Programma_CS2_RENAN.core.config import get_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_match_detail_vm")


class MatchDetailViewModel(QObject):
    """Loads match stats, rounds, insights, HLTV breakdown in background."""

    data_changed = Signal(dict, list, list, dict)  # stats, rounds, insights, hltv
    is_loading_changed = Signal(bool)
    error_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_loading = False

    @property
    def is_loading(self):
        return self._is_loading

    def load_detail(self, demo_name: str):
        if not demo_name or not demo_name.strip():
            self.error_changed.emit("No demo selected.")
            return
        if self._is_loading:
            return
        self._is_loading = True
        self.is_loading_changed.emit(True)
        self.error_changed.emit("")

        worker = Worker(self._bg_load, demo_name)
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def _bg_load(self, demo_name: str):
        player = get_setting("CS2_PLAYER_NAME", "")
        if not player:
            raise ValueError(
                "Player name not set. Go to Settings \u2192 Profile to set your in-game name."
            )

        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager
        from Programma_CS2_RENAN.backend.storage.db_models import (
            CoachingInsight,
            PlayerMatchStats,
            RoundStats,
        )

        with get_db_manager().get_session() as session:
            match_stats = session.exec(
                select(PlayerMatchStats).where(
                    PlayerMatchStats.demo_name == demo_name,
                    PlayerMatchStats.player_name == player,
                )
            ).first()

            rounds = session.exec(
                select(RoundStats)
                .where(
                    RoundStats.demo_name == demo_name,
                    RoundStats.player_name == player,
                )
                .order_by(RoundStats.round_number.asc())
            ).all()

            insights = session.exec(
                select(CoachingInsight)
                .where(CoachingInsight.demo_name == demo_name)
                .order_by(CoachingInsight.created_at.desc())
            ).all()

            stats_dict = {}
            if match_stats:
                stats_dict = {
                    "demo_name": match_stats.demo_name,
                    "match_date": match_stats.match_date,
                    "rating": match_stats.rating,
                    "avg_kills": match_stats.avg_kills,
                    "avg_deaths": match_stats.avg_deaths,
                    "avg_adr": match_stats.avg_adr,
                    "avg_kast": match_stats.avg_kast,
                    "kd_ratio": match_stats.kd_ratio,
                    "avg_hs": match_stats.avg_hs,
                    "kpr": match_stats.kpr,
                    "dpr": match_stats.dpr,
                }

            rounds_data = [
                {
                    "round_number": r.round_number,
                    "side": r.side,
                    "kills": r.kills,
                    "deaths": r.deaths,
                    "damage_dealt": r.damage_dealt,
                    "opening_kill": r.opening_kill,
                    "equipment_value": r.equipment_value,
                    "round_won": r.round_won,
                }
                for r in rounds
            ]

            insights_data = [
                {
                    "title": i.title,
                    "message": i.message,
                    "severity": i.severity,
                    "focus_area": i.focus_area,
                }
                for i in insights
            ]

        breakdown = {}
        try:
            from Programma_CS2_RENAN.backend.reporting.analytics import analytics

            breakdown = analytics.get_hltv2_breakdown(player) or {}
        except Exception as e:
            logger.warning("hltv_breakdown.bg_fetch_failed: %s", e)

        return (stats_dict, rounds_data, insights_data, breakdown)

    def _on_loaded(self, result):
        self._is_loading = False
        self.is_loading_changed.emit(False)
        if result:
            stats, rounds, insights, breakdown = result
            self.data_changed.emit(stats, rounds, insights, breakdown)

    def _on_error(self, msg):
        logger.error("match_detail_vm.load_failed: %s", msg)
        self._is_loading = False
        self.is_loading_changed.emit(False)
        self.error_changed.emit(str(msg))
