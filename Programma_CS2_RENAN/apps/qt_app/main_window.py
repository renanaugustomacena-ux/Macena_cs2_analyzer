"""
Main window — QMainWindow with navigation sidebar and QStackedWidget.

Replaces the Kivy ScreenManager + layout.kv root FloatLayout.
"""

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from Programma_CS2_RENAN.apps.qt_app.core.i18n_bridge import i18n


# ── Navigation definition ──
# (screen_key, icon_char, i18n_key)
NAV_ITEMS = [
    ("home", "\u2302", "dashboard"),
    ("coach", "\u2691", "rap_coach_dashboard"),
    ("match_history", "\u2630", "match_history_title"),
    ("performance", "\u2606", "advanced_analytics"),
    ("tactical_viewer", "\u2316", "tactical_analyzer"),
    ("settings", "\u2699", "settings"),
    ("help", "\u2753", "help"),
]


class _BackgroundWidget(QWidget):
    """Paints a wallpaper image behind its children with configurable opacity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._scaled_cache: QPixmap | None = None
        self._opacity: float = 0.25

    def set_image(self, path: str):
        if path and __import__("os").path.exists(path):
            self._pixmap = QPixmap(path)
        else:
            self._pixmap = None
        self._scaled_cache = None
        self.update()

    def resizeEvent(self, event):
        self._scaled_cache = None  # Invalidate cache on resize
        super().resizeEvent(event)

    def paintEvent(self, event):
        if self._pixmap and not self._pixmap.isNull():
            if self._scaled_cache is None or self._scaled_cache.size() != self.size():
                scaled = self._pixmap.scaled(
                    self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                # Center-crop the scaled image
                x = (scaled.width() - self.width()) // 2
                y = (scaled.height() - self.height()) // 2
                self._scaled_cache = scaled.copy(x, y, self.width(), self.height())
            painter = QPainter(self)
            painter.setOpacity(self._opacity)
            painter.drawPixmap(0, 0, self._scaled_cache)
            painter.end()
        super().paintEvent(event)


class _NavButton(QPushButton):
    """Checkable sidebar button for navigation."""

    def __init__(self, icon_char: str, label: str, key: str):
        super().__init__(f"  {icon_char}  {label}")
        self.screen_key = key
        self.setObjectName("nav_button")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)


class MainWindow(QMainWindow):
    """Root application window with sidebar navigation."""

    screen_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Macena CS2 Analyzer")
        self.setMinimumSize(1280, 720)

        # Central container
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Sidebar ──
        self._sidebar = QWidget()
        self._sidebar.setObjectName("nav_sidebar")
        self._sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(8, 16, 8, 16)
        sidebar_layout.setSpacing(4)

        # App title
        title = QLabel("MACENA CS2")
        title.setObjectName("accent_label")
        title.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(title)
        sidebar_layout.addSpacing(20)

        # Nav buttons
        self._nav_buttons: dict[str, _NavButton] = {}
        for key, icon, i18n_key in NAV_ITEMS:
            btn = _NavButton(icon, i18n.get_text(i18n_key), key)
            btn.clicked.connect(self._on_nav_clicked)
            sidebar_layout.addWidget(btn)
            self._nav_buttons[key] = btn

        sidebar_layout.addItem(
            QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        # Version label at bottom
        ver = QLabel("v1.0.0-qt")
        ver.setObjectName("section_subtitle")
        ver.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(ver)

        root_layout.addWidget(self._sidebar)

        # ── Content area with background image ──
        content_wrapper = QWidget()
        overlay = QStackedLayout(content_wrapper)
        overlay.setStackingMode(QStackedLayout.StackAll)

        # Layer 0: background wallpaper (painted behind everything)
        self._bg_widget = _BackgroundWidget()
        overlay.addWidget(self._bg_widget)

        # Layer 1: actual screen stack (on top, transparent background)
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("QStackedWidget { background: transparent; }")
        overlay.addWidget(self._stack)

        # Raise the stack above the background
        overlay.setCurrentWidget(self._stack)

        root_layout.addWidget(content_wrapper, 1)

        # Screen registry
        self._screens: dict[str, int] = {}

        # Connect i18n changes
        i18n.language_changed.connect(self._refresh_nav_labels)

    def set_wallpaper(self, path: str):
        """Set the background wallpaper image path."""
        self._bg_widget.set_image(path)

    def register_screen(self, name: str, widget: QWidget):
        """Add a screen widget to the stack."""
        idx = self._stack.addWidget(widget)
        self._screens[name] = idx

    def switch_screen(self, name: str):
        """Navigate to a named screen."""
        if name not in self._screens:
            return
        self._stack.setCurrentIndex(self._screens[name])

        # Update button states
        for key, btn in self._nav_buttons.items():
            btn.setChecked(key == name)

        # Notify the screen
        widget = self._stack.currentWidget()
        if hasattr(widget, "on_enter"):
            widget.on_enter()

        self.screen_changed.emit(name)

    def _on_nav_clicked(self):
        btn = self.sender()
        if isinstance(btn, _NavButton):
            self.switch_screen(btn.screen_key)

    def _refresh_nav_labels(self, _lang: str):
        """Update button labels and screen content when language changes."""
        for key, icon, i18n_key in NAV_ITEMS:
            if key in self._nav_buttons:
                self._nav_buttons[key].setText(
                    f"  {icon}  {i18n.get_text(i18n_key)}"
                )
        # Notify all screens
        for i in range(self._stack.count()):
            widget = self._stack.widget(i)
            if hasattr(widget, "retranslate"):
                widget.retranslate()
