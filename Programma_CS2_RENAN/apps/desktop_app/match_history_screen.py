"""Match History Screen — navigable list of user's matches."""

import re

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen

from Programma_CS2_RENAN.apps.desktop_app.data_viewmodels import MatchHistoryViewModel
from Programma_CS2_RENAN.apps.desktop_app.theme import (
    COLOR_CARD_BG as _COLOR_CARD_BG,
    rating_color as _rating_color,
    rating_label as _rating_label,
)
from Programma_CS2_RENAN.core.registry import registry
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.match_history")

# Map name extraction from demo filenames (e.g. "match_de_dust2_12345.dem")
_MAP_PATTERN = re.compile(r"(de_\w+|cs_\w+|ar_\w+)")


def _extract_map_name(demo_name: str) -> str:
    m = _MAP_PATTERN.search(demo_name)
    return m.group(1) if m else "Unknown Map"


@registry.register("match_history")
class MatchHistoryScreen(MDScreen):
    """User's match list, ordered by date, with color-coded HLTV rating."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # P4-03: Delegate DB access to ViewModel (MVVM)
        self._vm = MatchHistoryViewModel()
        self._vm.bind(matches=self._on_matches_loaded)
        self._vm.bind(error_message=self._on_vm_error)

    def on_pre_enter(self):
        # P4-04: Show loading indicator while data loads
        self._show_placeholder("Loading matches...")
        self._vm.load_matches()

    def _on_matches_loaded(self, instance, matches):
        if not matches:
            # DA-MH-01: Clear "Loading..." state when result is empty
            self._show_placeholder("No matches found. Play some games!")
            return
        self._populate(matches)

    def _on_vm_error(self, instance, msg):
        if msg:
            self._show_placeholder(msg)

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

        # Rating badge (P4-07: includes text label for color-blind accessibility)
        rating_label = MDLabel(
            text=f"{rating:.2f}\n{_rating_label(rating)}",
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
