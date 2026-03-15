"""User Profile screen — displays player name, role, bio with edit dialog."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from Programma_CS2_RENAN.apps.qt_app.core.i18n_bridge import i18n
from Programma_CS2_RENAN.apps.qt_app.viewmodels.user_profile_vm import (
    UserProfileViewModel,
)
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_user_profile")

_ROLE_COLORS = {
    "entry": "#ff3333",
    "entry fragger": "#ff3333",
    "awper": "#3399ff",
    "lurker": "#9933cc",
    "support": "#33cc33",
    "igl": "#ffcc00",
    "all-rounder": "#808080",
}


class UserProfileScreen(QWidget):
    """Displays player profile from DB with edit capability."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm = UserProfileViewModel()
        self._vm.profile_loaded.connect(self._on_profile)
        self._vm.error_changed.connect(self._on_error)
        self._vm.is_loading_changed.connect(self._on_loading)
        self._current = {"name": "Player", "bio": "", "role": "All-Rounder"}
        self._build_ui()

    def on_enter(self):
        self._status.setVisible(False)
        self._vm.load_profile()

    def retranslate(self):
        """Update all translatable text when language changes."""
        self._title_label.setText(i18n.get_text("profile"))
        self._bio_title.setText(i18n.get_text("bio"))
        self._edit_btn.setText(i18n.get_text("dialog_edit_profile"))
        self._steam_sync_btn.setText(i18n.get_text("sync_steam"))

    # ── UI Construction ──

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self._title_label = QLabel(i18n.get_text("profile"))
        self._title_label.setObjectName("section_title")
        self._title_label.setFont(QFont("Roboto", 20, QFont.Bold))
        layout.addWidget(self._title_label)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet("color: #a0a0b0; font-size: 14px;")
        self._status.setVisible(False)
        layout.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setSpacing(16)

        # Avatar section (centered)
        avatar_section = QVBoxLayout()
        avatar_section.setAlignment(Qt.AlignCenter)
        avatar_section.setSpacing(4)

        self._avatar_icon = QLabel("\u263a")  # Smiley as fallback
        self._avatar_icon.setAlignment(Qt.AlignCenter)
        self._avatar_icon.setStyleSheet("color: #666680; font-size: 64px;")
        avatar_section.addWidget(self._avatar_icon)

        self._name_label = QLabel("Player")
        self._name_label.setAlignment(Qt.AlignCenter)
        self._name_label.setFont(QFont("Roboto", 18, QFont.Bold))
        self._name_label.setStyleSheet("color: #dcdcdc;")
        avatar_section.addWidget(self._name_label)

        self._role_label = QLabel("All-Rounder")
        self._role_label.setAlignment(Qt.AlignCenter)
        self._role_label.setStyleSheet("color: #808080; font-size: 14px; font-weight: bold;")
        avatar_section.addWidget(self._role_label)

        self._content_layout.addLayout(avatar_section)

        # Bio card
        bio_card = QFrame()
        bio_card.setObjectName("dashboard_card")
        bio_layout = QVBoxLayout(bio_card)
        bio_layout.setSpacing(4)
        self._bio_title = QLabel(i18n.get_text("bio"))
        self._bio_title.setFont(QFont("Roboto", 14, QFont.Bold))
        self._bio_title.setStyleSheet("color: #dcdcdc;")
        bio_layout.addWidget(self._bio_title)
        self._bio_label = QLabel("No description yet.")
        self._bio_label.setWordWrap(True)
        self._bio_label.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        bio_layout.addWidget(self._bio_label)
        self._content_layout.addWidget(bio_card)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self._edit_btn = QPushButton(i18n.get_text("dialog_edit_profile"))
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.clicked.connect(self._open_edit_dialog)
        btn_row.addWidget(self._edit_btn)

        self._steam_sync_btn = QPushButton(i18n.get_text("sync_steam"))
        self._steam_sync_btn.setEnabled(False)
        self._steam_sync_btn.setToolTip(i18n.get_text("sync_steam_tooltip"))
        btn_row.addWidget(self._steam_sync_btn)

        btn_row.addStretch()
        self._content_layout.addLayout(btn_row)

        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        layout.addWidget(scroll, 1)

    # ── Data Slots ──

    def _on_profile(self, data: dict):
        self._status.setVisible(False)
        self._current = data
        name = data.get("name", "Player")
        role = data.get("role", "All-Rounder")
        bio = data.get("bio", "No description yet.")

        self._name_label.setText(name)
        self._bio_label.setText(bio)

        # Role with color
        color = _ROLE_COLORS.get(role.lower(), "#808080")
        self._role_label.setText(role)
        self._role_label.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: bold;"
        )

        # Avatar fallback: first letter of name
        if name:
            self._avatar_icon.setText(name[0].upper())

    def _on_error(self, msg: str):
        if msg:
            self._status.setText(f"Error: {msg}")
            self._status.setVisible(True)

    def _on_loading(self, loading: bool):
        if loading:
            self._status.setText("Loading profile...")
            self._status.setVisible(True)

    # ── Edit Dialog ──

    def _open_edit_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Profile")
        dialog.setMinimumWidth(350)
        lay = QVBoxLayout(dialog)
        lay.setSpacing(12)

        # Bio field
        bio_lbl = QLabel("Bio:")
        bio_lbl.setStyleSheet("color: #a0a0b0;")
        lay.addWidget(bio_lbl)
        bio_input = QLineEdit(self._current.get("bio", ""))
        bio_input.setPlaceholderText("Tell us about yourself...")
        lay.addWidget(bio_input)

        # Role field
        role_lbl = QLabel("Role:")
        role_lbl.setStyleSheet("color: #a0a0b0;")
        lay.addWidget(role_lbl)
        role_input = QLineEdit(self._current.get("role", "All-Rounder"))
        role_input.setPlaceholderText("Entry Fragger, AWPer, IGL, Support, Lurker...")
        lay.addWidget(role_input)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        lay.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            self._vm.save_profile(bio_input.text(), role_input.text())
