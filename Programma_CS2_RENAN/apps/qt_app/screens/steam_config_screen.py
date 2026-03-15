"""Steam configuration screen — SteamID64 and API key setup."""

from PySide6.QtCore import QThreadPool, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
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
from Programma_CS2_RENAN.apps.qt_app.core.worker import Worker
from Programma_CS2_RENAN.core.config import get_credential, get_setting, save_user_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_steam_config")

try:
    import keyring  # noqa: F401

    _KEYRING_AVAILABLE = keyring is not None
except ImportError:
    _KEYRING_AVAILABLE = False


class SteamConfigScreen(QWidget):
    """Configure Steam integration: SteamID64 and API key."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def on_enter(self):
        """Pre-fill fields from saved config."""
        self._steam_id_input.setText(get_setting("STEAM_ID", ""))
        api_key = get_credential("STEAM_API_KEY")
        if api_key and api_key != "PROTECTED_BY_WINDOWS_VAULT":
            self._api_key_input.setText(api_key)
        self._saved_label.setVisible(False)

    def retranslate(self):
        """Update all translatable text when language changes."""
        self._title_label.setText(i18n.get_text("steam_integration"))
        self._id_card_title.setText(i18n.get_text("steam_id_title"))
        self._id_desc.setText(i18n.get_text("steam_desc"))
        self._id_link_btn.setText(i18n.get_text("find_steam_id"))
        self._key_card_title.setText(i18n.get_text("steam_api_key_title"))
        self._key_desc.setText(i18n.get_text("steam_api_key_desc"))
        self._key_link_btn.setText(i18n.get_text("get_steam_key"))
        self._save_btn.setText(i18n.get_text("save_config"))
        self._sync_btn.setText(i18n.get_text("sync_steam"))

    # ── UI ──

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._title_label = QLabel(i18n.get_text("steam_integration"))
        self._title_label.setObjectName("section_title")
        self._title_label.setFont(QFont("Roboto", 20, QFont.Bold))
        layout.addWidget(self._title_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)

        # ── Keyring Warning ──
        if not _KEYRING_AVAILABLE:
            warn = QLabel(
                "System keyring unavailable — API keys will be stored in plaintext on disk. "
                "Install the 'keyring' package for secure storage."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                "color: #ffcc00; background-color: #332b00; "
                "border: 1px solid #665500; border-radius: 4px; "
                "padding: 8px; font-size: 13px;"
            )
            content_layout.addWidget(warn)

        # ── SteamID64 Card ──
        id_card, self._id_card_title = self._make_card("steam_id_title")
        id_layout = id_card.layout()

        self._id_desc = QLabel(i18n.get_text("steam_desc"))
        self._id_desc.setWordWrap(True)
        self._id_desc.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        id_layout.addWidget(self._id_desc)

        self._id_link_btn = QPushButton(i18n.get_text("find_steam_id"))
        self._id_link_btn.setCursor(Qt.PointingHandCursor)
        self._id_link_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://steamid.io/"))
        )
        id_layout.addWidget(self._id_link_btn)

        self._steam_id_input = QLineEdit()
        self._steam_id_input.setPlaceholderText("17-digit SteamID64")
        self._steam_id_input.setMaxLength(20)
        id_layout.addWidget(self._steam_id_input)

        content_layout.addWidget(id_card)

        # ── Steam API Key Card ──
        key_card, self._key_card_title = self._make_card("steam_api_key_title")
        key_layout = key_card.layout()

        self._key_desc = QLabel(i18n.get_text("steam_api_key_desc"))
        self._key_desc.setWordWrap(True)
        self._key_desc.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        key_layout.addWidget(self._key_desc)

        self._key_link_btn = QPushButton(i18n.get_text("get_steam_key"))
        self._key_link_btn.setCursor(Qt.PointingHandCursor)
        self._key_link_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://steamcommunity.com/dev/apikey")
            )
        )
        key_layout.addWidget(self._key_link_btn)

        self._api_key_input = QLineEdit()
        self._api_key_input.setPlaceholderText("Paste your Steam API Key")
        self._api_key_input.setEchoMode(QLineEdit.Password)
        key_layout.addWidget(self._api_key_input)

        content_layout.addWidget(key_card)

        # ── Buttons Row ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._save_btn = QPushButton(i18n.get_text("save_config"))
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setFixedHeight(40)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        self._sync_btn = QPushButton(i18n.get_text("sync_steam"))
        self._sync_btn.setCursor(Qt.PointingHandCursor)
        self._sync_btn.setFixedHeight(40)
        self._sync_btn.setToolTip(i18n.get_text("sync_steam_tooltip"))
        self._sync_btn.clicked.connect(self._on_sync)
        btn_row.addWidget(self._sync_btn)

        btn_row.addStretch()
        content_layout.addLayout(btn_row)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setVisible(False)
        content_layout.addWidget(self._status_label)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def _make_card(self, i18n_key: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("dashboard_card")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)
        lbl = QLabel(i18n.get_text(i18n_key))
        lbl.setFont(QFont("Roboto", 14, QFont.Bold))
        lbl.setStyleSheet("color: #dcdcdc;")
        card_layout.addWidget(lbl)
        return card, lbl

    # ── Actions ──

    def _on_save(self):
        steam_id = self._steam_id_input.text().strip()
        api_key = self._api_key_input.text().strip()

        if steam_id:
            save_user_setting("STEAM_ID", steam_id)
        if api_key:
            save_user_setting("STEAM_API_KEY", api_key)

        self._show_status("Saved!", "#4caf50")
        logger.info("Steam configuration saved (ID=%s)", "set" if steam_id else "empty")

    def _on_sync(self):
        # Save first
        self._on_save()

        steam_id = self._steam_id_input.text().strip()
        if not steam_id:
            self._show_status("Enter your SteamID64 first.", "#ff5555")
            return

        self._sync_btn.setEnabled(False)
        self._sync_btn.setText("Syncing...")
        self._show_status("Connecting to Steam...", "#a0a0b0")

        worker = Worker(self._bg_sync, steam_id)
        worker.signals.result.connect(self._on_sync_result)
        worker.signals.error.connect(self._on_sync_error)
        QThreadPool.globalInstance().start(worker)

    def _bg_sync(self, steam_id: str):
        from Programma_CS2_RENAN.backend.services.profile_service import ProfileService

        svc = ProfileService()
        return svc.fetch_steam_stats(steam_id)

    def _on_sync_result(self, result):
        self._sync_btn.setEnabled(True)
        self._sync_btn.setText("Sync Now")

        if not result or "error" in result:
            err = result.get("error", "Unknown error") if result else "No response"
            self._show_status(f"Sync failed: {err}", "#ff5555")
            return

        nickname = result.get("nickname", "Unknown")
        hours = result.get("playtime_forever", 0)
        self._show_status(
            f"Synced! Steam: {nickname} | CS2: {hours:.0f} hours",
            "#4caf50",
        )
        logger.info("Steam sync success: %s (%.0fh)", nickname, hours)

    def _on_sync_error(self, error_msg: str):
        self._sync_btn.setEnabled(True)
        self._sync_btn.setText("Sync Now")
        self._show_status(f"Sync failed: {error_msg}", "#ff5555")
        logger.error("Steam sync error: %s", error_msg)

    def _show_status(self, text: str, color: str):
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: bold;"
        )
        self._status_label.setVisible(True)
        QTimer.singleShot(8000, lambda: self._status_label.setVisible(False))
