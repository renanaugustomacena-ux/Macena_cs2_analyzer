"""Settings screen — theme, paths, appearance, ingestion, font, language."""

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from Programma_CS2_RENAN.apps.qt_app.core.worker import Worker

from Programma_CS2_RENAN.apps.qt_app.core.i18n_bridge import i18n
from Programma_CS2_RENAN.apps.qt_app.core.theme_engine import ThemeEngine
from Programma_CS2_RENAN.core.config import get_setting, save_user_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_settings")

_FONT_SIZES = {"Small": 11, "Medium": 13, "Large": 16}


class SettingsScreen(QWidget):
    """User-facing settings: theme, paths, appearance, ingestion, font, language."""

    def __init__(self, theme_engine: ThemeEngine, parent=None):
        super().__init__(parent)
        self._theme_engine = theme_engine

        # Toggle button group references (key → QPushButton)
        self._theme_buttons: dict = {}
        self._wallpaper_buttons: dict = {}
        self._font_size_buttons: dict = {}
        self._font_type_buttons: dict = {}
        self._language_buttons: dict = {}
        self._ingest_mode_buttons: dict = {}

        # Value display widgets
        self._default_path_label: QLabel | None = None
        self._pro_path_label: QLabel | None = None
        self._interval_input: QLineEdit | None = None

        # Ingestion state
        self._ingestion_worker = None
        self._start_btn: QPushButton | None = None
        self._stop_btn: QPushButton | None = None
        self._ingest_status_label: QLabel | None = None

        self._build_ui()

    # ── Lifecycle ──

    def on_enter(self):
        """Refresh all controls from current config when screen becomes visible."""
        self._default_path_label.setText(get_setting("DEFAULT_DEMO_PATH", "Not Set"))
        self._pro_path_label.setText(get_setting("PRO_DEMO_PATH", "Not Set"))
        self._interval_input.setText(str(get_setting("INGEST_INTERVAL_MINUTES", 30)))
        self._refresh_all_toggles()

    def retranslate(self):
        """Update all translatable text when language changes."""
        self._title_label.setText(i18n.get_text("settings"))
        self._theme_section_label.setText(i18n.get_text("visual_theme"))
        self._wallpaper_section_label.setText(i18n.get_text("wallpaper"))
        self._paths_section_label.setText(i18n.get_text("analysis_paths"))
        self._appearance_section_label.setText(i18n.get_text("appearance"))
        self._font_size_label.setText(i18n.get_text("font_size") + ":")
        self._ingestion_section_label.setText(i18n.get_text("data_ingestion"))
        self._ingest_mode_label.setText(i18n.get_text("ingestion_mode") + ":")
        self._font_type_section_label.setText(i18n.get_text("font_type"))
        self._language_section_label.setText(i18n.get_text("language"))

    # ── UI Construction ──

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self._title_label = QLabel(i18n.get_text("settings"))
        self._title_label.setObjectName("section_title")
        self._title_label.setFont(QFont("Roboto", 20, QFont.Bold))
        layout.addWidget(self._title_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setSpacing(16)

        self._build_theme_section()
        self._build_wallpaper_section()
        self._build_paths_section()
        self._build_font_size_section()
        self._build_ingestion_section()
        self._build_font_type_section()
        self._build_language_section()

        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        layout.addWidget(scroll, 1)

    def _section(self, i18n_key: str) -> tuple[QFrame, QLabel]:
        """Create a titled dashboard card and add it to content layout."""
        card = QFrame()
        card.setObjectName("dashboard_card")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)

        lbl = QLabel(i18n.get_text(i18n_key))
        lbl.setFont(QFont("Roboto", 14, QFont.Bold))
        lbl.setStyleSheet("color: #dcdcdc;")
        card_layout.addWidget(lbl)

        self._content_layout.addWidget(card)
        return card, lbl

    # ── Section Builders ──

    def _build_theme_section(self):
        card, self._theme_section_label = self._section("visual_theme")
        row = self._make_toggle_group(
            {"CS2": "CS2", "CSGO": "CS:GO", "CS1.6": "CS 1.6"},
            self._theme_buttons,
            self._on_theme_selected,
        )
        card.layout().addLayout(row)

    def _build_wallpaper_section(self):
        card, self._wallpaper_section_label = self._section("wallpaper")
        self._wallpaper_card = card
        self._wallpaper_row = QHBoxLayout()
        self._wallpaper_row.setSpacing(8)
        self._rebuild_wallpaper_buttons()
        card.layout().addLayout(self._wallpaper_row)

    def _rebuild_wallpaper_buttons(self):
        """Rebuild wallpaper toggle buttons for the current theme."""
        # Clear existing buttons
        self._wallpaper_buttons.clear()
        while self._wallpaper_row.count() > 0:
            item = self._wallpaper_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        wallpapers = self._theme_engine.get_available_wallpapers()
        current_path = self._theme_engine.wallpaper_path
        for filename in wallpapers:
            # Shorten label: "16_9_wallpaper_cs2.jpg" → "16:9 A"
            short = filename.rsplit(".", 1)[0]
            if "16_9" in short:
                prefix = "16:9"
            elif "vertical" in short:
                prefix = "Vert"
            elif "mini" in short:
                prefix = "Mini"
            else:
                prefix = short[:8]
            # Extract variant letter (last char before extension if uppercase)
            variant = ""
            base = short.rsplit(".", 1)[0]
            if base and base[-1].isalpha() and base[-2] == "_":
                variant = f" {base[-1]}"
            label = f"{prefix}{variant}"

            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.setMinimumWidth(70)
            btn.clicked.connect(lambda _c, f=filename: self._on_wallpaper_selected(f))
            self._wallpaper_buttons[filename] = btn
            self._wallpaper_row.addWidget(btn)

        self._wallpaper_row.addStretch()
        self._update_wallpaper_toggles(current_path)

    def _update_wallpaper_toggles(self, current_path: str):
        """Highlight the active wallpaper button."""
        import os
        accent = self._theme_engine.get_color("accent_primary").name()
        for filename, btn in self._wallpaper_buttons.items():
            is_active = current_path.endswith(os.sep + filename) or current_path.endswith("/" + filename)
            if is_active:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {accent}; color: white; "
                    f"border: none; border-radius: 8px; padding: 8px 12px; font-weight: bold; }}"
                    f"QPushButton:hover {{ background-color: {accent}; }}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background-color: transparent; color: #a0a0b0; "
                    "border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; "
                    "padding: 8px 12px; }"
                    "QPushButton:hover { background-color: rgba(255,255,255,0.05); "
                    "color: #dcdcdc; }"
                )

    def _build_paths_section(self):
        card, self._paths_section_label = self._section("analysis_paths")

        # Demo path
        demo_row = QHBoxLayout()
        demo_row.setSpacing(8)
        lbl = QLabel("Demo Path:")
        lbl.setFixedWidth(90)
        lbl.setStyleSheet("color: #a0a0b0;")
        demo_row.addWidget(lbl)
        self._default_path_label = QLabel("Not Set")
        self._default_path_label.setStyleSheet("color: #dcdcdc;")
        self._default_path_label.setWordWrap(True)
        demo_row.addWidget(self._default_path_label, 1)
        btn = QPushButton("Change")
        btn.setFixedWidth(80)
        btn.clicked.connect(lambda: self._on_path_change("default"))
        demo_row.addWidget(btn)
        card.layout().addLayout(demo_row)

        # Pro path
        pro_row = QHBoxLayout()
        pro_row.setSpacing(8)
        lbl2 = QLabel("Pro Path:")
        lbl2.setFixedWidth(90)
        lbl2.setStyleSheet("color: #a0a0b0;")
        pro_row.addWidget(lbl2)
        self._pro_path_label = QLabel("Not Set")
        self._pro_path_label.setStyleSheet("color: #dcdcdc;")
        self._pro_path_label.setWordWrap(True)
        pro_row.addWidget(self._pro_path_label, 1)
        btn2 = QPushButton("Change")
        btn2.setFixedWidth(80)
        btn2.clicked.connect(lambda: self._on_path_change("pro"))
        pro_row.addWidget(btn2)
        card.layout().addLayout(pro_row)

    def _build_font_size_section(self):
        card, self._appearance_section_label = self._section("appearance")
        self._font_size_label = QLabel(i18n.get_text("font_size") + ":")
        self._font_size_label.setStyleSheet("color: #a0a0b0;")
        card.layout().addWidget(self._font_size_label)
        row = self._make_toggle_group(
            {"Small": "Small", "Medium": "Medium", "Large": "Large"},
            self._font_size_buttons,
            self._on_font_size_selected,
        )
        card.layout().addLayout(row)

    def _build_ingestion_section(self):
        card, self._ingestion_section_label = self._section("data_ingestion")

        # Mode toggle
        self._ingest_mode_label = QLabel(i18n.get_text("ingestion_mode") + ":")
        self._ingest_mode_label.setStyleSheet("color: #a0a0b0;")
        card.layout().addWidget(self._ingest_mode_label)
        mode_row = self._make_toggle_group(
            {"manual": "Manual", "auto": "Auto"},
            self._ingest_mode_buttons,
            self._on_ingest_mode_selected,
        )
        card.layout().addLayout(mode_row)

        # Interval
        interval_row = QHBoxLayout()
        interval_row.setSpacing(8)
        int_lbl = QLabel("Scan Interval (min):")
        int_lbl.setStyleSheet("color: #a0a0b0;")
        interval_row.addWidget(int_lbl)
        self._interval_input = QLineEdit()
        self._interval_input.setFixedWidth(80)
        self._interval_input.setPlaceholderText("30")
        interval_row.addWidget(self._interval_input)
        set_btn = QPushButton("Set")
        set_btn.setFixedWidth(60)
        set_btn.clicked.connect(self._on_interval_set)
        interval_row.addWidget(set_btn)
        interval_row.addStretch()
        card.layout().addLayout(interval_row)

        # Start/Stop ingestion
        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        self._start_btn = QPushButton("Start Ingestion")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setToolTip("Scan demo folders and ingest new demos")
        self._start_btn.clicked.connect(self._on_start_ingestion)
        action_row.addWidget(self._start_btn)
        self._ingest_status_label = QLabel("")
        self._ingest_status_label.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        action_row.addWidget(self._ingest_status_label)
        action_row.addStretch()
        card.layout().addLayout(action_row)

    def _build_font_type_section(self):
        card, self._font_type_section_label = self._section("font_type")
        row1 = self._make_toggle_group(
            {"Roboto": "Roboto", "Arial": "Arial", "JetBrains Mono": "JetBrains"},
            self._font_type_buttons,
            self._on_font_type_selected,
        )
        card.layout().addLayout(row1)
        row2 = self._make_toggle_group(
            {"New Hope": "New Hope", "CS Regular": "CS Regular", "YUPIX": "YUPIX"},
            self._font_type_buttons,
            self._on_font_type_selected,
        )
        card.layout().addLayout(row2)

    def _build_language_section(self):
        card, self._language_section_label = self._section("language")
        row = self._make_toggle_group(
            {"en": "English", "it": "Italiano", "pt": "Portugues"},
            self._language_buttons,
            self._on_language_selected,
        )
        card.layout().addLayout(row)

    # ── Toggle Button Helpers ──

    def _make_toggle_group(self, options: dict, button_dict: dict, callback) -> QHBoxLayout:
        """Create a horizontal row of exclusive toggle buttons."""
        row = QHBoxLayout()
        row.setSpacing(8)
        for key, label in options.items():
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.setMinimumWidth(80)
            btn.clicked.connect(lambda _checked, k=key: callback(k))
            button_dict[key] = btn
            row.addWidget(btn)
        row.addStretch()
        return row

    def _update_toggle_group(self, button_dict: dict, active_key: str):
        """Active button gets accent fill, rest get outlined style."""
        accent = self._theme_engine.get_color("accent_primary").name()
        for key, btn in button_dict.items():
            if key == active_key:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {accent}; color: white; "
                    f"border: none; border-radius: 8px; padding: 8px 20px; font-weight: bold; }}"
                    f"QPushButton:hover {{ background-color: {accent}; }}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background-color: transparent; color: #a0a0b0; "
                    "border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; "
                    "padding: 8px 20px; }"
                    "QPushButton:hover { background-color: rgba(255,255,255,0.05); "
                    "color: #dcdcdc; }"
                )

    def _refresh_all_toggles(self):
        """Re-read config and update all toggle groups."""
        self._update_toggle_group(self._theme_buttons, get_setting("ACTIVE_THEME", "CS2"))
        self._update_toggle_group(self._font_size_buttons, get_setting("FONT_SIZE", "Medium"))
        self._update_toggle_group(self._font_type_buttons, get_setting("FONT_TYPE", "Roboto"))
        self._update_toggle_group(self._language_buttons, get_setting("LANGUAGE", "en"))
        is_auto = get_setting("INGEST_MODE_AUTO", True)
        self._update_toggle_group(self._ingest_mode_buttons, "auto" if is_auto else "manual")

    # ── Action Handlers ──

    def _on_theme_selected(self, name: str):
        self._theme_engine.apply_theme(name, QApplication.instance())
        save_user_setting("ACTIVE_THEME", name)
        self._refresh_all_toggles()
        # Rebuild wallpaper buttons for new theme
        self._rebuild_wallpaper_buttons()
        # Update wallpaper in MainWindow
        win = self.window()
        if hasattr(win, "set_wallpaper"):
            win.set_wallpaper(self._theme_engine.wallpaper_path)
        logger.info("Theme changed to %s", name)

    def _on_path_change(self, target: str):
        config_key = "DEFAULT_DEMO_PATH" if target == "default" else "PRO_DEMO_PATH"
        current = get_setting(config_key, "")
        path = QFileDialog.getExistingDirectory(
            self,
            f"Select {'Demo' if target == 'default' else 'Pro Demo'} Folder",
            current,
        )
        if path:
            save_user_setting(config_key, path)
            label = self._default_path_label if target == "default" else self._pro_path_label
            label.setText(path)
            logger.info("%s path set to %s", config_key, path)

    def _on_font_size_selected(self, size: str):
        save_user_setting("FONT_SIZE", size)
        pt = _FONT_SIZES.get(size, 13)
        font_type = get_setting("FONT_TYPE", "Roboto")
        self._theme_engine.set_font(font_type, pt)
        self._update_toggle_group(self._font_size_buttons, size)
        logger.info("Font size changed to %s (%dpt)", size, pt)

    def _on_ingest_mode_selected(self, mode: str):
        save_user_setting("INGEST_MODE_AUTO", mode == "auto")
        self._update_toggle_group(self._ingest_mode_buttons, mode)
        logger.info("Ingestion mode set to %s", mode)

    def _on_interval_set(self):
        text = self._interval_input.text().strip()
        try:
            val = max(1, int(text))
        except (ValueError, TypeError):
            logger.warning("Invalid interval input: %s", text)
            return
        save_user_setting("INGEST_INTERVAL_MINUTES", val)
        self._interval_input.setText(str(val))
        logger.info("Ingest interval set to %d min", val)

    def _on_font_type_selected(self, font_name: str):
        save_user_setting("FONT_TYPE", font_name)
        pt = _FONT_SIZES.get(get_setting("FONT_SIZE", "Medium"), 13)
        self._theme_engine.set_font(font_name, pt)
        self._update_toggle_group(self._font_type_buttons, font_name)
        logger.info("Font type changed to %s", font_name)

    def _on_language_selected(self, lang_code: str):
        save_user_setting("LANGUAGE", lang_code)
        i18n.set_language(lang_code)
        self._update_toggle_group(self._language_buttons, lang_code)
        logger.info("Language changed to %s", lang_code)

    def _on_wallpaper_selected(self, filename: str):
        self._theme_engine.set_wallpaper(filename)
        self._update_wallpaper_toggles(self._theme_engine.wallpaper_path)
        win = self.window()
        if hasattr(win, "set_wallpaper"):
            win.set_wallpaper(self._theme_engine.wallpaper_path)
        logger.info("Wallpaper changed to %s", filename)

    def _on_start_ingestion(self):
        if self._ingestion_worker is not None:
            return  # Already running
        pro_path = get_setting("PRO_DEMO_PATH", "")
        demo_path = get_setting("DEFAULT_DEMO_PATH", "")
        if not pro_path and not demo_path:
            self._ingest_status_label.setText("Set a demo path first")
            self._ingest_status_label.setStyleSheet("color: #ff5555; font-size: 13px;")
            return

        self._start_btn.setEnabled(False)
        self._start_btn.setText("Ingesting...")
        self._ingest_status_label.setText("Scanning for demos...")
        self._ingest_status_label.setStyleSheet("color: #ffcc00; font-size: 13px;")

        def _run_ingestion():
            from Programma_CS2_RENAN.run_ingestion import process_new_demos
            results = []
            if pro_path:
                results.append(("pro", process_new_demos(is_pro=True)))
            if demo_path:
                results.append(("user", process_new_demos(is_pro=False)))
            return results

        worker = Worker(_run_ingestion)
        worker.signals.result.connect(self._on_ingestion_done)
        worker.signals.error.connect(self._on_ingestion_error)
        self._ingestion_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_ingestion_done(self, results):
        self._ingestion_worker = None
        self._start_btn.setEnabled(True)
        self._start_btn.setText("Start Ingestion")
        self._ingest_status_label.setText("Ingestion complete")
        self._ingest_status_label.setStyleSheet("color: #4caf50; font-size: 13px;")
        logger.info("Ingestion completed: %s", results)

    def _on_ingestion_error(self, error):
        self._ingestion_worker = None
        self._start_btn.setEnabled(True)
        self._start_btn.setText("Start Ingestion")
        self._ingest_status_label.setText(f"Error: {error}")
        self._ingest_status_label.setStyleSheet("color: #ff5555; font-size: 13px;")
        logger.error("Ingestion failed: %s", error)
