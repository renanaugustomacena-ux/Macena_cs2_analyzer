"""
Data ViewModels — MVVM separation for data-loading screens.

P4-03: Moves raw DB access out of Screen classes (View layer) into
ViewModel layer, following the same pattern as tactical_viewmodels.py
and coaching_chat_vm.py:
- EventDispatcher with Kivy Properties
- Daemon threads for background data loading
- Clock.schedule_once to marshal results back to the UI thread
"""

from threading import Event, Thread
from typing import Optional

from kivy.clock import Clock
from kivy.event import EventDispatcher
from kivy.properties import BooleanProperty, DictProperty, ListProperty, StringProperty

from Programma_CS2_RENAN.core.config import get_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.data_viewmodels")


# ---------------------------------------------------------------------------
# MatchHistoryViewModel
# ---------------------------------------------------------------------------


class MatchHistoryViewModel(EventDispatcher):
    """ViewModel for MatchHistoryScreen — owns match list loading."""

    matches = ListProperty([])
    is_loading = BooleanProperty(False)
    error_message = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # DV-01: Cancellation event to discard stale results from superseded loads
        self._cancel = Event()

    def load_matches(self):
        # DA-DV-01: Prevent duplicate background loads from rapid on_enter calls
        if self.is_loading:
            return
        self._cancel.clear()
        self.is_loading = True
        self.error_message = ""
        Thread(target=self._bg_load, daemon=True).start()

    def cancel(self):
        """DV-01: Signal background thread to discard results."""
        self._cancel.set()

    def _bg_load(self):
        try:
            player = get_setting("CS2_PLAYER_NAME", "")
            if not player:
                Clock.schedule_once(
                    lambda dt: self._on_error("Set your player name in Settings first."), 0
                )
                return

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
            # DV-01: Discard results if cancelled while loading
            if self._cancel.is_set():
                return
            Clock.schedule_once(lambda dt: self._on_loaded(match_data), 0)
        except Exception as e:
            logger.error("match_history_vm.load_failed: %s", e)
            Clock.schedule_once(lambda dt: self._on_error("Error loading matches."), 0)
        finally:
            # DV-02: Guarantee is_loading resets even on unexpected errors
            if self._cancel.is_set():
                Clock.schedule_once(lambda dt: setattr(self, "is_loading", False), 0)

    def _on_loaded(self, data):
        self.matches = data
        self.is_loading = False

    def _on_error(self, msg):
        self.error_message = msg
        self.is_loading = False


# ---------------------------------------------------------------------------
# MatchDetailViewModel
# ---------------------------------------------------------------------------


class MatchDetailViewModel(EventDispatcher):
    """ViewModel for MatchDetailScreen — owns match detail loading."""

    stats = DictProperty({})
    rounds = ListProperty([])
    insights = ListProperty([])
    hltv_breakdown = DictProperty({})
    is_loading = BooleanProperty(False)
    error_message = StringProperty("")

    def load_detail(self, demo_name: str):
        # DV-03: Validate demo_name before spawning background thread
        if not demo_name or not demo_name.strip():
            self.error_message = "No demo selected."
            return
        # DA-DV-01: Prevent duplicate background loads
        if self.is_loading:
            return
        self.is_loading = True
        self.error_message = ""
        Thread(target=self._bg_load, args=(demo_name,), daemon=True).start()

    def _bg_load(self, demo_name: str):
        try:
            player = get_setting("CS2_PLAYER_NAME", "")

            from Programma_CS2_RENAN.backend.storage.database import get_db_manager
            from Programma_CS2_RENAN.backend.storage.db_models import (
                CoachingInsight,
                PlayerMatchStats,
                RoundStats,
            )

            with get_db_manager().get_session() as session:
                match_stats = (
                    session.query(PlayerMatchStats)
                    .filter(
                        PlayerMatchStats.demo_name == demo_name,
                        PlayerMatchStats.player_name == player,
                    )
                    .first()
                )

                rounds = (
                    session.query(RoundStats)
                    .filter(
                        RoundStats.demo_name == demo_name,
                        RoundStats.player_name == player,
                    )
                    .order_by(RoundStats.round_number.asc())
                    .all()
                )

                insights = (
                    session.query(CoachingInsight)
                    .filter(CoachingInsight.demo_name == demo_name)
                    .order_by(CoachingInsight.created_at.desc())
                    .all()
                )

                # Detach from session
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

            # P4-06: Fetch HLTV breakdown in background thread
            breakdown = {}
            try:
                from Programma_CS2_RENAN.backend.reporting.analytics import analytics

                breakdown = analytics.get_hltv2_breakdown(player) or {}
            except Exception as e:
                logger.warning("hltv_breakdown.bg_fetch_failed: %s", e)

            Clock.schedule_once(
                lambda dt: self._on_loaded(stats_dict, rounds_data, insights_data, breakdown), 0
            )
        except Exception as e:
            logger.error("match_detail_vm.load_failed: %s", e, exc_info=False)
            Clock.schedule_once(lambda dt: self._on_error("Error loading match details."), 0)

    def _on_loaded(self, stats, rounds, insights, breakdown):
        self.stats = stats
        self.rounds = rounds
        self.insights = insights
        self.hltv_breakdown = breakdown
        self.is_loading = False

    def _on_error(self, msg):
        self.error_message = msg
        self.is_loading = False


# ---------------------------------------------------------------------------
# PerformanceViewModel
# ---------------------------------------------------------------------------


class PerformanceViewModel(EventDispatcher):
    """ViewModel for PerformanceScreen — owns performance data loading."""

    history = ListProperty([])
    map_stats = DictProperty({})
    strength_weakness = DictProperty({})
    utility = DictProperty({})
    is_loading = BooleanProperty(False)
    error_message = StringProperty("")

    def load_performance(self):
        # DA-DV-01: Prevent duplicate background loads
        if self.is_loading:
            return
        self.is_loading = True
        self.error_message = ""
        Thread(target=self._bg_load, daemon=True).start()

    def _bg_load(self):
        try:
            player = get_setting("CS2_PLAYER_NAME", "")
            if not player:
                Clock.schedule_once(
                    lambda dt: self._on_error("Set your player name in Settings first."), 0
                )
                return

            from Programma_CS2_RENAN.backend.reporting.analytics import analytics

            history = analytics.get_rating_history(player, limit=50)
            map_stats = analytics.get_per_map_stats(player)
            sw = analytics.get_strength_weakness(player)
            utility = analytics.get_utility_breakdown(player)

            Clock.schedule_once(
                lambda dt: self._on_loaded(history, map_stats, sw, utility), 0
            )
        except Exception as e:
            logger.error("performance_vm.load_failed: %s", e)
            Clock.schedule_once(
                lambda dt: self._on_error("Error loading performance data."), 0
            )
        finally:
            # Guarantee is_loading resets even on early return or unexpected error
            Clock.schedule_once(lambda dt: setattr(self, "is_loading", False), 0)

    def _on_loaded(self, history, map_stats, sw, utility):
        self.history = history or []
        self.map_stats = map_stats or {}
        self.strength_weakness = sw or {}
        self.utility = utility or {}
        self.is_loading = False

    def _on_error(self, msg):
        self.error_message = msg
        self.is_loading = False
