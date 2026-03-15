"""Home / Dashboard screen — central hub with 4 cards and live CoachState polling."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from Programma_CS2_RENAN.apps.qt_app.core.app_state import get_app_state
from Programma_CS2_RENAN.apps.qt_app.core.i18n_bridge import i18n
from Programma_CS2_RENAN.core.config import get_setting, save_user_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_home")

_DISABLED_TIP_ENGINE = "Session engine not connected (Phase 3)"
_DISABLED_TIP_VIEWER = "Tactical Viewer coming in Phase 4"


class HomeScreen(QWidget):
    """Dashboard with 4 cards: Demo Analysis, Pro Ingestion, Connectivity, Tactical."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._build_ui()

    def on_enter(self):
        """Called by MainWindow.switch_screen — refresh paths and connect signals."""
        self._demo_path_label.setText(
            get_setting("DEFAULT_DEMO_PATH", "Not set")
        )
        self._pro_path_label.setText(
            get_setting("PRO_DEMO_PATH", "Not set")
        )
        if not self._connected:
            state = get_app_state()
            state.service_active_changed.connect(self._on_service_active)
            state.coach_status_changed.connect(self._on_coach_status)
            state.parsing_progress_changed.connect(self._on_parsing_progress)
            state.training_changed.connect(self._on_training)
            state.total_matches_changed.connect(self._on_total_matches)
            self._connected = True

    # ── UI Construction ──

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Title
        self._title_label = QLabel(i18n.get_text("dashboard"))
        self._title_label.setObjectName("section_title")
        self._title_label.setFont(QFont("Roboto", 20, QFont.Bold))
        root.addWidget(self._title_label)

        # Status bar
        self._status_bar = self._build_status_bar()
        root.addWidget(self._status_bar)

        # Scrollable card area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self._cards_layout = QVBoxLayout(content)
        self._cards_layout.setSpacing(16)

        self._build_demo_card()
        self._build_pro_card()
        self._build_connectivity_card()
        self._build_tactical_card()
        self._build_training_card()

        self._cards_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    # ── Status Bar ──

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("dashboard_card")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(16)

        self._status_label = QLabel("Coach Status: Idle")
        self._status_label.setFont(QFont("Roboto", 13))
        self._status_label.setStyleSheet("color: #a0a0b0;")
        layout.addWidget(self._status_label)

        self._service_label = QLabel("Service: Offline")
        self._service_label.setFont(QFont("Roboto", 13))
        self._service_label.setStyleSheet("color: #ff5555;")
        layout.addWidget(self._service_label)

        self._matches_label = QLabel("Matches: 0")
        self._matches_label.setFont(QFont("Roboto", 13))
        self._matches_label.setStyleSheet("color: #a0a0b0;")
        layout.addWidget(self._matches_label)

        layout.addStretch()
        return bar

    # ── Card 1: Demo Analysis ──

    def _build_demo_card(self):
        card, self._demo_card_title = self._make_card("demo_analysis")
        layout = card.layout()

        self._demo_desc = QLabel(i18n.get_text("demo_analysis_desc"))
        self._demo_desc.setWordWrap(True)
        self._demo_desc.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        layout.addWidget(self._demo_desc)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_lbl = QLabel("Path:")
        path_lbl.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        path_row.addWidget(path_lbl)
        self._demo_path_label = QLabel("Not set")
        self._demo_path_label.setStyleSheet("color: #dcdcdc; font-size: 13px;")
        self._demo_path_label.setWordWrap(True)
        path_row.addWidget(self._demo_path_label, 1)
        layout.addLayout(path_row)

        self._parsing_bar = QProgressBar()
        self._parsing_bar.setRange(0, 100)
        self._parsing_bar.setValue(0)
        self._parsing_bar.setVisible(False)
        self._parsing_bar.setFixedHeight(18)
        layout.addWidget(self._parsing_bar)

        self._demo_btn = QPushButton(i18n.get_text("select_demo_folder"))
        self._demo_btn.setCursor(Qt.PointingHandCursor)
        self._demo_btn.setFixedWidth(180)
        self._demo_btn.clicked.connect(self._pick_demo_folder)
        layout.addWidget(self._demo_btn)

        self._cards_layout.addWidget(card)

    # ── Card 2: Pro Ingestion Hub ──

    def _build_pro_card(self):
        card, self._pro_card_title = self._make_card("pro_demo_ingestion")
        layout = card.layout()

        self._pro_desc = QLabel(i18n.get_text("pro_demo_ingestion_desc"))
        self._pro_desc.setWordWrap(True)
        self._pro_desc.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        layout.addWidget(self._pro_desc)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_lbl = QLabel("Path:")
        path_lbl.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        path_row.addWidget(path_lbl)
        self._pro_path_label = QLabel("Not set")
        self._pro_path_label.setStyleSheet("color: #dcdcdc; font-size: 13px;")
        self._pro_path_label.setWordWrap(True)
        path_row.addWidget(self._pro_path_label, 1)
        layout.addLayout(path_row)

        # Speed buttons (disabled — session engine not connected)
        speed_row = QHBoxLayout()
        speed_row.setSpacing(8)
        speed_lbl = QLabel("Ingest Speed:")
        speed_lbl.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        speed_row.addWidget(speed_lbl)
        for label in ("Turbo", "Normal", "Pause"):
            btn = QPushButton(label)
            btn.setEnabled(False)
            btn.setToolTip(_DISABLED_TIP_ENGINE)
            btn.setFixedWidth(80)
            speed_row.addWidget(btn)
        speed_row.addStretch()
        layout.addLayout(speed_row)

        toggle_btn = QPushButton("Start / Stop")
        toggle_btn.setEnabled(False)
        toggle_btn.setToolTip(_DISABLED_TIP_ENGINE)
        toggle_btn.setFixedWidth(140)
        layout.addWidget(toggle_btn)

        self._cards_layout.addWidget(card)

    # ── Card 3: API & Profile Connectivity ──

    def _build_connectivity_card(self):
        card, self._conn_card_title = self._make_card("connectivity")
        layout = card.layout()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._profile_btn = QPushButton(i18n.get_text("profile"))
        self._profile_btn.setCursor(Qt.PointingHandCursor)
        self._profile_btn.clicked.connect(lambda: self._navigate("user_profile"))
        btn_row.addWidget(self._profile_btn)

        self._steam_btn = QPushButton(i18n.get_text("steam_config"))
        self._steam_btn.setCursor(Qt.PointingHandCursor)
        self._steam_btn.clicked.connect(lambda: self._navigate("steam_config"))
        btn_row.addWidget(self._steam_btn)

        self._faceit_btn = QPushButton(i18n.get_text("faceit_config"))
        self._faceit_btn.setCursor(Qt.PointingHandCursor)
        self._faceit_btn.clicked.connect(lambda: self._navigate("faceit_config"))
        btn_row.addWidget(self._faceit_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._cards_layout.addWidget(card)

    # ── Card 4: Tactical Analysis ──

    def _build_tactical_card(self):
        card, self._tact_card_title = self._make_card("tactical_analysis")
        layout = card.layout()

        self._tact_desc = QLabel(i18n.get_text("tactical_desc"))
        self._tact_desc.setWordWrap(True)
        self._tact_desc.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        layout.addWidget(self._tact_desc)

        self._tact_btn = QPushButton(i18n.get_text("open_tactical_viewer"))
        self._tact_btn.setCursor(Qt.PointingHandCursor)
        self._tact_btn.setFixedWidth(200)
        self._tact_btn.clicked.connect(lambda: self._navigate("tactical_viewer"))
        layout.addWidget(self._tact_btn)

        self._cards_layout.addWidget(card)

    # ── Training Status Card (hidden until training active) ──

    def _build_training_card(self):
        self._training_card, self._training_card_title = self._make_card("training_status")
        layout = self._training_card.layout()

        self._epoch_label = QLabel("Epoch: 0 / 0")
        self._epoch_label.setStyleSheet("color: #dcdcdc; font-size: 13px;")
        layout.addWidget(self._epoch_label)

        self._train_loss_label = QLabel("Train Loss: —")
        self._train_loss_label.setStyleSheet("color: #dcdcdc; font-size: 13px;")
        layout.addWidget(self._train_loss_label)

        self._val_loss_label = QLabel("Val Loss: —")
        self._val_loss_label.setStyleSheet("color: #dcdcdc; font-size: 13px;")
        layout.addWidget(self._val_loss_label)

        self._eta_label = QLabel("ETA: —")
        self._eta_label.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        layout.addWidget(self._eta_label)

        self._training_card.setVisible(False)
        self._cards_layout.addWidget(self._training_card)

    # ── Helpers ──

    def _make_card(self, i18n_key: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("dashboard_card")
        layout = QVBoxLayout(card)
        layout.setSpacing(8)
        lbl = QLabel(i18n.get_text(i18n_key))
        lbl.setFont(QFont("Roboto", 14, QFont.Bold))
        lbl.setStyleSheet("color: #dcdcdc;")
        layout.addWidget(lbl)
        return card, lbl

    def _navigate(self, screen_name: str):
        win = self.window()
        if win and hasattr(win, "switch_screen"):
            win.switch_screen(screen_name)

    def retranslate(self):
        """Update all translatable text when language changes."""
        self._title_label.setText(i18n.get_text("dashboard"))
        # Card titles
        self._demo_card_title.setText(i18n.get_text("demo_analysis"))
        self._pro_card_title.setText(i18n.get_text("pro_demo_ingestion"))
        self._conn_card_title.setText(i18n.get_text("connectivity"))
        self._tact_card_title.setText(i18n.get_text("tactical_analysis"))
        self._training_card_title.setText(i18n.get_text("training_status"))
        # Descriptions
        self._demo_desc.setText(i18n.get_text("demo_analysis_desc"))
        self._pro_desc.setText(i18n.get_text("pro_demo_ingestion_desc"))
        self._tact_desc.setText(i18n.get_text("tactical_desc"))
        # Buttons
        self._demo_btn.setText(i18n.get_text("select_demo_folder"))
        self._tact_btn.setText(i18n.get_text("open_tactical_viewer"))
        self._profile_btn.setText(i18n.get_text("profile"))
        self._steam_btn.setText(i18n.get_text("steam_config"))
        self._faceit_btn.setText(i18n.get_text("faceit_config"))

    def _pick_demo_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Demo Folder")
        if folder:
            save_user_setting("DEFAULT_DEMO_PATH", folder)
            self._demo_path_label.setText(folder)
            logger.info("Demo folder set: %s", folder)

    @staticmethod
    def _format_eta(seconds: float) -> str:
        if seconds <= 0:
            return "—"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m {s}s"

    # ── Signal Slots ──

    def _on_service_active(self, active: bool):
        if active:
            self._service_label.setText("Service: Online")
            self._service_label.setStyleSheet("color: #4caf50; font-size: 13px;")
        else:
            self._service_label.setText("Service: Offline")
            self._service_label.setStyleSheet("color: #ff5555; font-size: 13px;")

    def _on_coach_status(self, status: str):
        self._status_label.setText(f"Coach Status: {status}")

    def _on_parsing_progress(self, progress: float):
        if 0 < progress < 100:
            self._parsing_bar.setValue(int(progress))
            self._parsing_bar.setVisible(True)
        else:
            self._parsing_bar.setVisible(False)

    def _on_training(self, data: dict):
        epoch = data.get("current_epoch", 0)
        total = data.get("total_epochs", 0)
        visible = total > 0

        self._training_card.setVisible(visible)
        if not visible:
            return

        self._epoch_label.setText(f"Epoch: {epoch} / {total}")
        self._train_loss_label.setText(
            f"Train Loss: {data.get('train_loss', 0):.4f}"
        )
        self._val_loss_label.setText(
            f"Val Loss: {data.get('val_loss', 0):.4f}"
        )
        self._eta_label.setText(
            f"ETA: {self._format_eta(data.get('eta_seconds', 0))}"
        )

    def _on_total_matches(self, count: int):
        self._matches_label.setText(f"Matches: {count}")
