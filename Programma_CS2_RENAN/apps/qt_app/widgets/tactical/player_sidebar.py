"""Player sidebar — team roster with widget pooling and live detail card."""

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from Programma_CS2_RENAN.core.demo_frame import Team
from Programma_CS2_RENAN.core.playback_engine import InterpolatedPlayerState


class _PlayerItem(QFrame):
    """Single player row in the sidebar."""

    clicked = Signal(object)  # Steam IDs exceed int32

    def __init__(self, player_id: int, parent=None):
        super().__init__(parent)
        self._player_id = player_id
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QFrame { background: transparent; border-radius: 6px; padding: 4px; }"
            "QFrame:hover { background: rgba(255,255,255,0.05); }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setFixedWidth(20)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setStyleSheet("background: transparent;")
        layout.addWidget(self._icon_label)

        info = QVBoxLayout()
        info.setSpacing(0)
        self._name_label = QLabel()
        self._name_label.setFont(QFont("Roboto", 10, QFont.Bold))
        self._name_label.setStyleSheet("color: #dcdcdc; background: transparent;")
        info.addWidget(self._name_label)

        self._stats_label = QLabel()
        self._stats_label.setStyleSheet("color: #a0a0b0; font-size: 11px; background: transparent;")
        info.addWidget(self._stats_label)
        layout.addLayout(info, 1)

        self._weapon_label = QLabel()
        self._weapon_label.setStyleSheet("color: #808090; font-size: 10px; background: transparent;")
        self._weapon_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._weapon_label)

    def update_data(self, player: InterpolatedPlayerState, is_selected: bool):
        is_ct = player.team == Team.CT if isinstance(player.team, Team) else "CT" in str(player.team).upper()

        if not player.is_alive:
            self._icon_label.setText("\u2620")
            self._icon_label.setStyleSheet("color: #808080; background: transparent;")
            self._name_label.setStyleSheet("color: #808080; background: transparent;")
        elif is_ct:
            self._icon_label.setText("\u2694")
            self._icon_label.setStyleSheet("color: #4d80ff; background: transparent;")
            self._name_label.setStyleSheet("color: #dcdcdc; background: transparent;")
        else:
            self._icon_label.setText("\u25ce")
            self._icon_label.setStyleSheet("color: #ff9933; background: transparent;")
            self._name_label.setStyleSheet("color: #dcdcdc; background: transparent;")

        self._name_label.setText(player.name)
        info = f"${player.money}"
        if player.is_alive:
            info += f" | HP: {player.hp}"
        self._stats_label.setText(info)
        self._weapon_label.setText(player.weapon or "")

        if is_selected:
            self.setStyleSheet(
                "QFrame { background: rgba(40, 50, 70, 0.8); border-radius: 6px; padding: 4px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background: transparent; border-radius: 6px; padding: 4px; }"
                "QFrame:hover { background: rgba(255,255,255,0.05); }"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._player_id)
        super().mousePressEvent(event)


class _LivePlayerCard(QFrame):
    """Detailed stats card for selected player."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashboard_card")
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._name_label = QLabel()
        self._name_label.setFont(QFont("Roboto", 12, QFont.Bold))
        self._name_label.setAlignment(Qt.AlignCenter)
        self._name_label.setStyleSheet("color: #dcdcdc;")
        layout.addWidget(self._name_label)

        # HP bar
        hp_row = QHBoxLayout()
        hp_row.setSpacing(4)
        hp_lbl = QLabel("HP")
        hp_lbl.setFixedWidth(30)
        hp_lbl.setStyleSheet("color: #a0a0b0; font-size: 11px;")
        hp_row.addWidget(hp_lbl)
        self._hp_bar = QProgressBar()
        self._hp_bar.setRange(0, 100)
        self._hp_bar.setFixedHeight(10)
        self._hp_bar.setTextVisible(False)
        hp_row.addWidget(self._hp_bar)
        layout.addLayout(hp_row)

        # Armor bar
        armor_row = QHBoxLayout()
        armor_row.setSpacing(4)
        armor_lbl = QLabel("ARM")
        armor_lbl.setFixedWidth(30)
        armor_lbl.setStyleSheet("color: #a0a0b0; font-size: 11px;")
        armor_row.addWidget(armor_lbl)
        self._armor_bar = QProgressBar()
        self._armor_bar.setRange(0, 100)
        self._armor_bar.setFixedHeight(10)
        self._armor_bar.setTextVisible(False)
        armor_row.addWidget(self._armor_bar)
        layout.addLayout(armor_row)

        # Money + KDA
        self._money_label = QLabel("$0")
        self._money_label.setStyleSheet("color: #80ff80; font-size: 13px;")
        self._money_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._money_label)

        self._kda_label = QLabel("0 / 0 / 0")
        self._kda_label.setStyleSheet("color: #dcdcdc; font-size: 13px;")
        self._kda_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._kda_label)

    def show_player(self, player: InterpolatedPlayerState, team_color: str):
        self.setVisible(True)
        prefix = "[DEAD] " if not player.is_alive else ""
        self._name_label.setText(f"{prefix}{player.name}")
        self._name_label.setStyleSheet(f"color: {team_color};")

        self._hp_bar.setValue(player.hp)
        self._armor_bar.setValue(player.armor)
        self._money_label.setText(f"${player.money}")
        self._kda_label.setText(f"{player.kills} / {player.deaths} / {player.assists}")

        self.setStyleSheet(
            "QFrame#dashboard_card { opacity: %s; }" % ("0.6" if not player.is_alive else "1.0")
        )

    def hide_card(self):
        self.setVisible(False)


class PlayerSidebar(QWidget):
    """Team sidebar with player list and detail card."""

    player_clicked = Signal(object)  # Steam IDs exceed int32

    def __init__(self, team_name: str = "TEAM", team_color: str = "#dcdcdc", parent=None):
        super().__init__(parent)
        self._team_name = team_name
        self._team_color = team_color
        self._player_items: Dict[int, _PlayerItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel(team_name)
        header.setFont(QFont("Roboto", 12, QFont.Bold))
        header.setStyleSheet(f"color: {team_color}; padding: 8px;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Scroll area for player list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(4, 4, 4, 4)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        layout.addWidget(scroll, 1)

        # Live card
        self._card = _LivePlayerCard()
        layout.addWidget(self._card)

    def update_players(self, players: List[InterpolatedPlayerState], selected_id=None):
        active_ids = {p.player_id for p in players}

        # Evict stale
        for pid in list(self._player_items.keys()):
            if pid not in active_ids:
                item = self._player_items.pop(pid)
                self._list_layout.removeWidget(item)
                item.deleteLater()

        sorted_players = sorted(players, key=lambda x: (not x.is_alive, x.player_id))
        target_player = None

        for p_data in sorted_players:
            is_selected = p_data.player_id == selected_id
            if is_selected:
                target_player = p_data

            if p_data.player_id in self._player_items:
                item = self._player_items[p_data.player_id]
                item.update_data(p_data, is_selected)
            else:
                item = _PlayerItem(p_data.player_id)
                item.clicked.connect(self._on_item_clicked)
                item.update_data(p_data, is_selected)
                # Insert before stretch
                self._list_layout.insertWidget(self._list_layout.count() - 1, item)
                self._player_items[p_data.player_id] = item

        if target_player:
            self._card.show_player(target_player, self._team_color)
        else:
            self._card.hide_card()

    def clear_all(self):
        for pid in list(self._player_items.keys()):
            item = self._player_items.pop(pid)
            self._list_layout.removeWidget(item)
            item.deleteLater()
        self._card.hide_card()

    def _on_item_clicked(self, pid: int):
        self.player_clicked.emit(pid)
