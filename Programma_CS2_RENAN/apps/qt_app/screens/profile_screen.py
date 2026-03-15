"""Profile screen — edit in-game name (CS2_PLAYER_NAME config key)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from Programma_CS2_RENAN.core.config import get_setting, save_user_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_profile")


class ProfileScreen(QWidget):
    """Simple form for setting the in-game player name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def on_enter(self):
        self._name_input.setText(get_setting("CS2_PLAYER_NAME", ""))
        self._saved_label.setVisible(False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("In-Game Name")
        title.setObjectName("section_title")
        title.setFont(QFont("Roboto", 20, QFont.Bold))
        layout.addWidget(title)

        desc = QLabel(
            "Set your CS2 in-game name. This is used to identify your stats\n"
            "in demo files and match history."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        layout.addWidget(desc)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Enter your in-game nickname...")
        self._name_input.returnPressed.connect(self._save)
        layout.addWidget(self._name_input)

        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(120)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        self._saved_label = QLabel("Saved!")
        self._saved_label.setStyleSheet("color: #4caf50; font-size: 13px;")
        self._saved_label.setVisible(False)
        layout.addWidget(self._saved_label)

        layout.addStretch()

    def _save(self):
        name = self._name_input.text().strip()
        if not name:
            return
        save_user_setting("CS2_PLAYER_NAME", name)
        self._saved_label.setVisible(True)
        logger.info("Player name saved: %s", name)
