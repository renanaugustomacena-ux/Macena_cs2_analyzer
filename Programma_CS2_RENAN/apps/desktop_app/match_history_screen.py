"""Match History Screen — navigable list of user's matches."""

import re
from threading import Thread

from kivy.clock import Clock
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen

from sqlmodel import select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats
from Programma_CS2_RENAN.core.config import get_setting
from Programma_CS2_RENAN.core.registry import registry
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.match_history")

# Standard HLTV rating thresholds
_RATING_GOOD = 1.10
_RATING_BAD = 0.90

# Map name extraction from demo filenames (e.g. "match_de_dust2_12345.dem")
_MAP_PATTERN = re.compile(r"(de_\w+|cs_\w+|ar_\w+)")

# Rating color coding
# F7-13: COLOR_GREEN/YELLOW/RED duplicated in match_detail_screen.py. Consolidate to
# apps/desktop_app/theme.py when UI theming is refactored.
_COLOR_GREEN = (0.30, 0.69, 0.31, 1)  # #4CAF50
_COLOR_YELLOW = (1.0, 0.60, 0.0, 1)  # #FF9800
_COLOR_RED = (0.96, 0.26, 0.21, 1)  # #F44336
_COLOR_CARD_BG = (0.12, 0.12, 0.14, 1)  # Dark card


def _rating_color(rating: float):
    if rating > _RATING_GOOD:
        return _COLOR_GREEN
    if rating < _RATING_BAD:
        return _COLOR_RED
    return _COLOR_YELLOW


def _extract_map_name(demo_name: str) -> str:
    m = _MAP_PATTERN.search(demo_name)
    return m.group(1) if m else "Unknown Map"


@registry.register("match_history")
class MatchHistoryScreen(MDScreen):
    """User's match list, ordered by date, with color-coded HLTV rating."""

    def on_pre_enter(self):
        Thread(target=self._load_matches, daemon=True).start()

    def _load_matches(self):
        try:
            player = get_setting("CS2_PLAYER_NAME", "")
            if not player:
                Clock.schedule_once(
                    lambda dt: self._show_placeholder("Set your player name in Settings first."), 0
                )
                return

            with get_db_manager().get_session() as session:
                # F7-05: Migrated from legacy session.query() to SQLModel convention
                matches = session.exec(
                    select(PlayerMatchStats)
                    .where(
                        PlayerMatchStats.player_name == player,
                        PlayerMatchStats.is_pro == False,  # noqa: E712
                    )
                    .order_by(PlayerMatchStats.match_date.desc())
                    .limit(50)
                ).all()
                # Detach from session before scheduling UI update
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
                    for m in matches
                ]
            Clock.schedule_once(lambda dt: self._populate(match_data), 0)
        except Exception as e:
            logger.error("match_history.load_failed", error=str(e))
            Clock.schedule_once(lambda dt: self._show_placeholder("Error loading matches."), 0)

    def _populate(self, matches: list):
        container = self.ids.get("match_list_container")
        if not container:
            return
        container.clear_widgets()
        if not matches:
            self._show_placeholder("No matches found. Play some games!")
            return
        for m in matches:
            card = self._build_match_card(m)
            container.add_widget(card)

    def _show_placeholder(self, text: str):
        container = self.ids.get("match_list_container")
        if not container:
            return
        container.clear_widgets()
        container.add_widget(
            MDLabel(
                text=text,
                halign="center",
                theme_text_color="Hint",
                adaptive_height=True,
            )
        )

    def _build_match_card(self, m: dict) -> MDCard:
        rating = m.get("rating", 1.0) or 1.0
        map_name = _extract_map_name(m.get("demo_name", ""))
        date_str = ""
        if m.get("match_date"):
            try:
                date_str = m["match_date"].strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = str(m["match_date"])

        card = MDCard(
            style="elevated",
            size_hint_y=None,
            height="80dp",
            padding="12dp",
            md_bg_color=_COLOR_CARD_BG,
            ripple_behavior=True,
        )
        demo_name = m.get("demo_name", "")
        card.bind(on_release=lambda inst, d=demo_name: self._on_match_selected(d))

        row = MDBoxLayout(
            orientation="horizontal",
            adaptive_height=True,
            spacing="12dp",
        )

        # Rating badge
        rating_label = MDLabel(
            text=f"{rating:.2f}",
            halign="center",
            theme_text_color="Custom",
            text_color=_rating_color(rating),
            font_style="Headline",
            role="small",
            size_hint_x=None,
            width="60dp",
            adaptive_height=True,
        )

        # Match info column
        info_col = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            spacing="2dp",
        )
        info_col.add_widget(
            MDLabel(
                text=f"{map_name}  |  {date_str}",
                font_style="Body",
                role="medium",
                theme_text_color="Primary",
                adaptive_height=True,
            )
        )

        avg_kills = m.get("avg_kills", 0.0)
        avg_deaths = m.get("avg_deaths", 0.0)
        avg_adr = m.get("avg_adr", 0.0)
        kd = m.get("kd_ratio", 0.0)

        info_col.add_widget(
            MDLabel(
                text=f"K/D: {kd:.2f}  |  ADR: {avg_adr:.1f}  |  Kills: {avg_kills:.1f}  Deaths: {avg_deaths:.1f}",
                font_style="Body",
                role="small",
                theme_text_color="Secondary",
                adaptive_height=True,
            )
        )

        row.add_widget(rating_label)
        row.add_widget(info_col)
        card.add_widget(row)
        return card

    def _on_match_selected(self, demo_name: str):
        app = MDApp.get_running_app()
        app.selected_demo = demo_name
        app.switch_screen("match_detail")
