"""Match Detail Screen — tabbed drill-down: Overview, Rounds, Economy, Highlights."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from Programma_CS2_RENAN.apps.qt_app.core.theme_engine import (
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    rating_color,
    rating_label,
    rgba_to_qcolor,
)
from Programma_CS2_RENAN.apps.qt_app.viewmodels.match_detail_vm import MatchDetailViewModel
from Programma_CS2_RENAN.apps.qt_app.widgets.charts.economy_chart import EconomyChart
from Programma_CS2_RENAN.apps.qt_app.widgets.charts.momentum_chart import MomentumChart
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_match_detail")

_COLOR_CT = QColor("#5C9EE8")
_COLOR_T = QColor("#E8C95C")

_MAP_PATTERN = re.compile(r"(de_\w+|cs_\w+|ar_\w+)")

_SEVERITY_COLORS = {
    "critical": rgba_to_qcolor(list(COLOR_RED)),
    "warning": rgba_to_qcolor(list(COLOR_YELLOW)),
    "info": _COLOR_CT,
}


def _extract_map_name(demo_name: str) -> str:
    m = _MAP_PATTERN.search(demo_name)
    return m.group(1) if m else "Unknown Map"


class MatchDetailScreen(QWidget):
    """Tabbed match detail: Overview, Round Timeline, Economy, Highlights."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm = MatchDetailViewModel()
        self._vm.data_changed.connect(self._on_data)
        self._vm.error_changed.connect(self._on_error)
        self._demo_name = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Title
        self._title = QLabel("Match Detail")
        self._title.setObjectName("section_title")
        self._title.setFont(QFont("Roboto", 20, QFont.Bold))
        layout.addWidget(self._title)

        # Status
        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet("color: #a0a0b0; font-size: 14px;")
        self._status.setVisible(False)
        layout.addWidget(self._status)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setVisible(False)
        layout.addWidget(self._tabs, 1)

    def load_demo(self, demo_name: str):
        """Called externally to load a specific match."""
        self._demo_name = demo_name
        self._title.setText(f"Match Detail — {_extract_map_name(demo_name)}")
        self._status.setText("Loading match details...")
        self._status.setVisible(True)
        self._tabs.setVisible(False)
        self._vm.load_detail(demo_name)

    def on_enter(self):
        if self._demo_name:
            self.load_demo(self._demo_name)

    def _on_data(self, stats: dict, rounds: list, insights: list, hltv: dict):
        self._status.setVisible(False)
        self._tabs.setVisible(True)
        self._tabs.clear()

        if not stats and not rounds:
            self._status.setText("No match data available.")
            self._status.setVisible(True)
            self._tabs.setVisible(False)
            return

        # Tab 1: Overview
        self._tabs.addTab(self._build_overview(stats, hltv), "Overview")

        # Tab 2: Rounds
        if rounds:
            self._tabs.addTab(self._build_rounds(rounds), "Rounds")

        # Tab 3: Economy
        if rounds:
            self._tabs.addTab(self._build_economy(rounds), "Economy")

        # Tab 4: Highlights
        self._tabs.addTab(self._build_highlights(rounds, insights), "Highlights")

    def _on_error(self, msg: str):
        if msg:
            self._status.setText(msg)
            self._status.setVisible(True)
            self._tabs.setVisible(False)

    # ── Tab builders ──

    def _build_overview(self, stats: dict, hltv: dict) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(8)

        rating = stats.get("rating", 1.0) or 1.0
        r_color = rating_color(rating)

        # Rating header
        header = QHBoxLayout()
        badge = QLabel(f"{rating:.2f} ({rating_label(rating)})")
        badge.setFont(QFont("Roboto", 24, QFont.Bold))
        badge.setStyleSheet(f"color: {r_color.name()};")
        header.addWidget(badge)

        map_name = _extract_map_name(stats.get("demo_name", ""))
        date_str = ""
        if stats.get("match_date"):
            try:
                date_str = stats["match_date"].strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = str(stats["match_date"])
        info = QLabel(f"{map_name}  |  {date_str}")
        info.setFont(QFont("Roboto", 14))
        info.setStyleSheet("color: #dcdcdc;")
        header.addWidget(info)
        header.addStretch()
        layout.addLayout(header)

        # Stats row
        kd = stats.get("kd_ratio", 0.0)
        adr = stats.get("avg_adr", 0.0)
        kast = stats.get("avg_kast", 0.0)
        hs = stats.get("avg_hs", 0.0)
        kills = stats.get("avg_kills", 0.0)
        deaths = stats.get("avg_deaths", 0.0)

        stats_lbl = QLabel(
            f"K/D: {kd:.2f}   ADR: {adr:.1f}   "
            f"KAST: {kast * 100:.0f}%   HS: {hs * 100:.0f}%   "
            f"Avg Kills: {kills:.1f}   Avg Deaths: {deaths:.1f}"
        )
        stats_lbl.setFont(QFont("Roboto", 11))
        stats_lbl.setStyleSheet("color: #a0a0b0;")
        stats_lbl.setWordWrap(True)
        layout.addWidget(stats_lbl)

        # HLTV breakdown
        if hltv:
            sep = QLabel("HLTV 2.0 Components")
            sep.setFont(QFont("Roboto", 14, QFont.Bold))
            sep.setStyleSheet("color: #dcdcdc; margin-top: 12px;")
            layout.addWidget(sep)

            for comp, val in hltv.items():
                row = QHBoxLayout()
                name_lbl = QLabel(comp.replace("_", " ").title())
                name_lbl.setFixedWidth(180)
                name_lbl.setStyleSheet("color: #a0a0b0;")
                row.addWidget(name_lbl)

                val_color = rating_color(val)
                val_lbl = QLabel(f"{val:.2f}")
                val_lbl.setStyleSheet(f"color: {val_color.name()};")
                val_lbl.setFont(QFont("Roboto", 11, QFont.Bold))
                row.addWidget(val_lbl)
                row.addStretch()
                layout.addLayout(row)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _build_rounds(self, rounds: list) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(2)

        # Header
        hdr = QLabel("Rnd   W/L   Side   K  D   DMG     $Equip")
        hdr.setFont(QFont("JetBrains Mono", 10, QFont.Bold))
        hdr.setStyleSheet("color: #a0a0b0;")
        layout.addWidget(hdr)

        for r in rounds:
            rnum = r.get("round_number", 0)
            side = r.get("side", "?")
            won = r.get("round_won", False)
            kills = r.get("kills", 0)
            deaths = r.get("deaths", 0)
            dmg = r.get("damage_dealt", 0)
            opening = r.get("opening_kill", False)
            equip = r.get("equipment_value", 0)

            side_color = _COLOR_CT.name() if side == "CT" else _COLOR_T.name()
            result_color = "#4CAF50" if won else "#F44336"
            result_text = "W" if won else "L"
            fk_text = "  FK" if opening else ""

            row_text = (
                f"R{rnum:<3}  "
                f'<span style="color:{result_color}">{result_text}</span>    '
                f'<span style="color:{side_color}">{side:>2}</span>    '
                f"{kills}  {deaths}   {dmg:>4}   ${equip:>5}"
                f'<span style="color:#ffaa00">{fk_text}</span>'
            )

            lbl = QLabel(row_text)
            lbl.setTextFormat(Qt.RichText)
            lbl.setFont(QFont("JetBrains Mono", 10))
            layout.addWidget(lbl)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _build_economy(self, rounds: list) -> QWidget:
        chart = EconomyChart()
        chart.plot(rounds)
        return chart

    def _build_highlights(self, rounds: list, insights: list) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(8)

        # Coaching insights
        if insights:
            sec = QLabel("Coaching Insights")
            sec.setFont(QFont("Roboto", 14, QFont.Bold))
            sec.setStyleSheet("color: #dcdcdc;")
            layout.addWidget(sec)

            for ins in insights:
                sev = ins.get("severity", "info")
                sev_color = _SEVERITY_COLORS.get(sev, _COLOR_CT)

                card = QFrame()
                card.setObjectName("dashboard_card")
                card_layout = QVBoxLayout(card)
                card_layout.setSpacing(4)

                title_lbl = QLabel(ins.get("title", ""))
                title_lbl.setFont(QFont("Roboto", 12, QFont.Bold))
                title_lbl.setStyleSheet(f"color: {sev_color.name()};")
                card_layout.addWidget(title_lbl)

                msg_lbl = QLabel(ins.get("message", ""))
                msg_lbl.setWordWrap(True)
                msg_lbl.setStyleSheet("color: #dcdcdc;")
                card_layout.addWidget(msg_lbl)

                focus = ins.get("focus_area", "")
                if focus:
                    focus_lbl = QLabel(f"Focus: {focus}")
                    focus_lbl.setStyleSheet("color: #666666; font-style: italic;")
                    card_layout.addWidget(focus_lbl)

                layout.addWidget(card)
        else:
            layout.addWidget(
                QLabel("No coaching insights for this match yet.")
            )

        # Momentum chart
        if rounds:
            sec = QLabel("Momentum")
            sec.setFont(QFont("Roboto", 14, QFont.Bold))
            sec.setStyleSheet("color: #dcdcdc; margin-top: 12px;")
            layout.addWidget(sec)

            momentum = MomentumChart()
            momentum.setMinimumHeight(250)
            momentum.plot(rounds)
            layout.addWidget(momentum)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll
