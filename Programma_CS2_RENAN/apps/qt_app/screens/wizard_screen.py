"""Setup Wizard — first-run 4-step flow for brain path and demo path configuration."""

import errno
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from Programma_CS2_RENAN.core.config import save_user_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_wizard")

_BRAIN_SUBDIRS = ("knowledge", "models", "datasets")


class WizardScreen(QWidget):
    """4-step setup wizard: Intro → Brain Path → Demo Path → Finish."""

    setup_completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._brain_path = ""
        self._demo_path = ""

        self._build_ui()

    def on_enter(self):
        """Reset to first step when entering the wizard."""
        self._stack.setCurrentIndex(0)
        self._next_btn.setText("Get Started")
        self._next_btn.setVisible(True)

    # ── UI Construction ──

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Setup Wizard")
        title.setObjectName("section_title")
        title.setFont(QFont("Roboto", 20, QFont.Bold))
        layout.addWidget(title)

        # 4-page stack
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_intro_page())
        self._stack.addWidget(self._build_brain_page())
        self._stack.addWidget(self._build_demo_page())
        self._stack.addWidget(self._build_finish_page())
        layout.addWidget(self._stack, 1)

        # Bottom bar with Next button
        bottom = QHBoxLayout()
        bottom.addStretch()
        self._next_btn = QPushButton("Get Started")
        self._next_btn.setFixedHeight(40)
        self._next_btn.setMinimumWidth(140)
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.clicked.connect(self._on_next)
        bottom.addWidget(self._next_btn)
        layout.addLayout(bottom)

    def _build_intro_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(16)

        welcome = QLabel("Welcome to Macena CS2 Analyzer")
        welcome.setFont(QFont("Roboto", 18, QFont.Bold))
        welcome.setAlignment(Qt.AlignCenter)
        welcome.setStyleSheet("color: #dcdcdc;")
        lay.addWidget(welcome)

        desc = QLabel(
            "This wizard will help you configure the essential paths.\n\n"
            "You'll choose where to store your AI models and knowledge base,\n"
            "and optionally point to your CS2 demo folder."
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a0a0b0; font-size: 14px;")
        lay.addWidget(desc)

        return page

    def _build_brain_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)

        desc = QLabel(
            "Select a folder for the AI brain data.\n"
            "This is where models, knowledge base, and datasets will be stored."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        lay.addWidget(desc)

        # Manual entry
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._brain_input = QLineEdit()
        self._brain_input.setPlaceholderText("Enter path or use Select Folder...")
        self._brain_input.returnPressed.connect(self._on_next)
        input_row.addWidget(self._brain_input, 1)
        browse_btn = QPushButton("Select Folder")
        browse_btn.clicked.connect(self._pick_brain_folder)
        input_row.addWidget(browse_btn)
        lay.addLayout(input_row)

        # Selected path display
        self._brain_path_label = QLabel("")
        self._brain_path_label.setStyleSheet("color: #dcdcdc; font-size: 12px;")
        self._brain_path_label.setWordWrap(True)
        lay.addWidget(self._brain_path_label)

        # Error display
        self._brain_error = QLabel("")
        self._brain_error.setStyleSheet("color: #f44336; font-size: 12px;")
        self._brain_error.setWordWrap(True)
        self._brain_error.setVisible(False)
        lay.addWidget(self._brain_error)

        lay.addStretch()
        return page

    def _build_demo_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)

        desc = QLabel(
            "Select your CS2 demo folder (optional).\n"
            "This is where your .dem replay files are located.\n"
            "You can skip this step and set it later in Settings."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        lay.addWidget(desc)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._demo_input = QLineEdit()
        self._demo_input.setPlaceholderText("Enter path or use Select Folder...")
        self._demo_input.returnPressed.connect(self._on_next)
        input_row.addWidget(self._demo_input, 1)
        browse_btn = QPushButton("Select Folder")
        browse_btn.clicked.connect(self._pick_demo_folder)
        input_row.addWidget(browse_btn)
        lay.addLayout(input_row)

        self._demo_path_label = QLabel("")
        self._demo_path_label.setStyleSheet("color: #dcdcdc; font-size: 12px;")
        self._demo_path_label.setWordWrap(True)
        lay.addWidget(self._demo_path_label)

        self._demo_error = QLabel("")
        self._demo_error.setStyleSheet("color: #f44336; font-size: 12px;")
        self._demo_error.setWordWrap(True)
        self._demo_error.setVisible(False)
        lay.addWidget(self._demo_error)

        lay.addStretch()
        return page

    def _build_finish_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(16)

        done = QLabel("You're all set!")
        done.setFont(QFont("Roboto", 18, QFont.Bold))
        done.setAlignment(Qt.AlignCenter)
        done.setStyleSheet("color: #dcdcdc;")
        lay.addWidget(done)

        info = QLabel(
            "Your brain data and demo paths have been configured.\n"
            "You can change these anytime in Settings."
        )
        info.setAlignment(Qt.AlignCenter)
        info.setWordWrap(True)
        info.setStyleSheet("color: #a0a0b0; font-size: 14px;")
        lay.addWidget(info)

        return page

    # ── Navigation ──

    def _on_next(self):
        step = self._stack.currentIndex()
        if step == 0:
            self._go_to(1)
            self._next_btn.setText("Next")
        elif step == 1:
            if self._validate_brain():
                self._go_to(2)
        elif step == 2:
            self._validate_demo()
            self._go_to(3)
            self._next_btn.setText("Launch App")
        elif step == 3:
            self._finish()

    def _go_to(self, index: int):
        self._stack.setCurrentIndex(index)

    # ── Folder Pickers ──

    def _pick_brain_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Brain Data Folder", os.path.expanduser("~")
        )
        if path:
            self._brain_input.setText(path)
            self._brain_path = path
            self._brain_path_label.setText(f"Selected: {path}")

    def _pick_demo_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Demo Folder", os.path.expanduser("~")
        )
        if path:
            self._demo_input.setText(path)
            self._demo_path = path
            self._demo_path_label.setText(f"Selected: {path}")

    # ── Validation ──

    def _validate_brain(self) -> bool:
        """Validate brain path, create subdirectories. Returns True on success."""
        self._brain_error.setVisible(False)
        text = self._brain_input.text().strip()
        if not text:
            self._brain_error.setText("Please select or enter a brain data path.")
            self._brain_error.setVisible(True)
            return False

        # WZ-01: normalize
        path = os.path.normpath(os.path.expanduser(text))

        try:
            os.makedirs(path, exist_ok=True)
            for sub in _BRAIN_SUBDIRS:
                os.makedirs(os.path.join(path, sub), exist_ok=True)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EPERM):
                # WZ-04: try fallback paths
                fallback = self._find_writable_fallback()
                if fallback:
                    path = fallback
                    try:
                        os.makedirs(path, exist_ok=True)
                        for sub in _BRAIN_SUBDIRS:
                            os.makedirs(os.path.join(path, sub), exist_ok=True)
                    except OSError as e2:
                        self._brain_error.setText(f"Cannot create directories: {e2}")
                        self._brain_error.setVisible(True)
                        return False
                    self._brain_path_label.setText(f"Using fallback: {path}")
                else:
                    self._brain_error.setText(f"Permission denied and no fallback available: {e}")
                    self._brain_error.setVisible(True)
                    return False
            else:
                self._brain_error.setText(f"Cannot create directory: {e}")
                self._brain_error.setVisible(True)
                return False

        self._brain_path = path
        save_user_setting("BRAIN_DATA_ROOT", path)
        logger.info("Brain data root set to %s", path)
        return True

    def _validate_demo(self):
        """Validate demo path (optional). Non-blocking on error."""
        self._demo_error.setVisible(False)
        text = self._demo_input.text().strip()
        if not text:
            return  # Optional — skip

        # WZ-01: normalize
        path = os.path.normpath(os.path.expanduser(text))

        # WZ-03: non-blocking directory creation
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            logger.warning("Could not create demo path %s: %s", path, e)
            self._demo_error.setText(f"Warning: could not create folder ({e}). Path saved anyway.")
            self._demo_error.setVisible(True)

        self._demo_path = path
        save_user_setting("DEFAULT_DEMO_PATH", path)
        logger.info("Demo path set to %s", path)

    def _find_writable_fallback(self) -> str:
        """WZ-04: find a writable fallback path for brain data."""
        home = os.path.expanduser("~")
        for candidate in (
            os.path.join(home, "Documents", "DataCoach"),
            os.path.join(home, "DataCoach"),
        ):
            parent = os.path.dirname(candidate)
            if os.path.isdir(parent) and os.access(parent, os.W_OK):
                return candidate
        return ""

    # ── Finish ──

    def _finish(self):
        save_user_setting("SETUP_COMPLETED", True)
        logger.info("Setup wizard completed")
        self.setup_completed.emit()
