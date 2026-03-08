import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

import os
import subprocess
import sys
from pathlib import Path

# --- Venv Guard (skip in frozen/PyInstaller builds) ---
# Only enforce when running as main entry point, not when imported (e.g. by headless_validator).
if __name__ == "__main__" and not getattr(sys, "frozen", False) and sys.prefix == sys.base_prefix:
    print("ERROR: Not in venv. Run: source ~/.venvs/cs2analyzer/bin/activate", file=sys.stderr)
    sys.exit(2)

# --- Early Integrity Audit (RASP) ---
# We verify the codebase before any heavy library imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root_dir = Path(os.path.dirname(script_dir))
if str(project_root_dir) not in sys.path:
    sys.path.insert(0, str(project_root_dir))

try:
    from Programma_CS2_RENAN.observability.rasp import run_rasp_audit

    if not run_rasp_audit(project_root_dir):
        if getattr(sys, "frozen", False):
            print("CRITICAL: Integrity Check Failed. Terminating.", file=sys.stderr)
            sys.exit(1)
        else:
            print("WARNING: Integrity mismatch detected in development. Continuing...")
except ImportError:
    # If we can't even import RASP, something is fundamentally wrong
    if getattr(sys, "frozen", False):
        print("CRITICAL: Security Module Missing.", file=sys.stderr)
        sys.exit(1)

import json
import threading
import traceback
import webbrowser

# --- Path Stabilization ---
from Programma_CS2_RENAN.core.config import stabilize_paths

PROJECT_ROOT = stabilize_paths()

# --- Database Migration Auto-Upgrade (TASK 2.20.1) ---
# Ensure database schema is current before any DB operations
try:
    from Programma_CS2_RENAN.backend.storage.db_migrate import ensure_database_current

    if not ensure_database_current():
        print("WARNING: Database migration failed. Some features may not work correctly.")
except ImportError:
    pass  # Migration module not available (frozen build without alembic)

# --- Sentry Error Reporting (Task 2.21.1) ---
try:
    from Programma_CS2_RENAN.core.config import get_setting
    from Programma_CS2_RENAN.observability.sentry_setup import init_sentry

    init_sentry(
        dsn=get_setting("SENTRY_DSN", ""),
        enabled=get_setting("SENTRY_ENABLED", False),
    )
except Exception:
    pass  # Sentry is optional — never block startup

# --- Resolution Settings (User Requested) ---
from kivy.config import Config

Config.set("graphics", "width", "1280")
Config.set("graphics", "height", "720")
Config.set("graphics", "resizable", "1")

# Suppress KivyMD Deprecation Warnings
os.environ["KIVY_NO_ARGS"] = "1"

from kivy.animation import Animation
from kivy.cache import Cache
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.screenmanager import FadeTransition, ScreenManager
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogContentContainer,
    MDDialogHeadlineText,
    MDDialogSupportingText,
)
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText
from sqlmodel import func, select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database
from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight, PlayerProfile

# --- Centralized Configuration ---
from Programma_CS2_RENAN.core.config import (
    DATABASE_URL,
    get_resource_path,
    get_setting,
    refresh_settings,
    save_user_setting,
)
from Programma_CS2_RENAN.core.localization import i18n
from Programma_CS2_RENAN.core.registry import registry
from Programma_CS2_RENAN.observability.logger_setup import get_logger

app_logger = get_logger("cs2analyzer.main")


class CoachingCard(MDCard):
    title, severity, message, focus_area = (
        StringProperty(),
        StringProperty(),
        StringProperty(),
        StringProperty(),
    )


@registry.register("home")
class HomeScreen(MDScreen):
    pass


@registry.register("coach")
class CoachScreen(MDScreen):
    chat_expanded = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._chat_vm = None

    def _ensure_chat_vm(self):
        """Lazy-load the chat ViewModel to avoid heavy imports at startup."""
        if self._chat_vm is None:
            from Programma_CS2_RENAN.apps.desktop_app.coaching_chat_vm import CoachingChatViewModel

            self._chat_vm = CoachingChatViewModel()
            self._chat_vm.bind(messages=self._on_messages_changed)
            self._chat_vm.bind(is_loading=self._on_loading_changed)
        return self._chat_vm

    def on_pre_enter(self):
        self.refresh_insights()
        # Trigger Graph Update
        Clock.schedule_once(lambda dt: self.refresh_analytics(), 0.5)

    def toggle_chat_panel(self):
        self.chat_expanded = not self.chat_expanded
        if self.chat_expanded:
            vm = self._ensure_chat_vm()
            vm.check_availability()
            if not vm.session_active:
                player_name = get_setting("CS2_PLAYER_NAME", "Player")
                vm.start_session(player_name)

    def send_chat_message(self):
        chat_input = self.ids.get("chat_input")
        if chat_input and chat_input.text.strip():
            self._ensure_chat_vm().send_message(chat_input.text)
            chat_input.text = ""

    def send_quick_action(self, text):
        self._ensure_chat_vm().send_message(text)

    def clear_chat(self):
        if self._chat_vm is not None:
            self._chat_vm.clear_session()
        messages_container = self.ids.get("chat_messages")
        if messages_container:
            messages_container.clear_widgets()
        status_label = self.ids.get("chat_status_label")
        if status_label:
            status_label.text = ""

    def _on_messages_changed(self, instance, messages):
        """Rebuild chat message widgets when messages list changes."""
        container = self.ids.get("chat_messages")
        scroll = self.ids.get("chat_scroll")
        if not container:
            return
        container.clear_widgets()
        for msg in messages:
            is_user = msg["role"] == "user"
            bubble = MDCard(
                orientation="vertical",
                padding=["12dp", "8dp"],
                radius=[12],
                size_hint_x=0.85,
                size_hint_y=None,
                md_bg_color=(0.15, 0.25, 0.45, 0.9) if is_user else (0.1, 0.12, 0.18, 0.9),
                pos_hint={"right": 1} if is_user else {"x": 0},
            )
            bubble.add_widget(
                MDLabel(
                    text=msg["content"],
                    adaptive_height=True,
                    theme_text_color="Custom",
                    text_color=(0.9, 0.9, 1, 1) if is_user else (0.8, 0.9, 0.85, 1),
                )
            )
            bubble.bind(minimum_height=bubble.setter("height"))
            container.add_widget(bubble)
        # Auto-scroll to bottom
        if scroll:
            Clock.schedule_once(lambda dt: setattr(scroll, "scroll_y", 0), 0.1)
        # Update status
        status_label = self.ids.get("chat_status_label")
        if status_label and self._chat_vm:
            status_label.text = "Online" if self._chat_vm.is_available else "Offline"

    def _on_loading_changed(self, instance, is_loading):
        typing_label = self.ids.get("chat_typing_label")
        if typing_label:
            typing_label.opacity = 1 if is_loading else 0

    def refresh_analytics(self):
        """Updates the analytic widgets (Graphs)."""
        from Programma_CS2_RENAN.apps.desktop_app.widgets import RadarChartWidget, TrendGraphWidget
        from Programma_CS2_RENAN.backend.reporting.analytics import analytics
        from Programma_CS2_RENAN.core.config import get_setting

        target_player = get_setting("CS2_PLAYER_NAME", "User")

        # 1. Trend Graph
        container = self.ids.get("analytics_container")
        if container:
            container.clear_widgets()

            # Get Data
            df = analytics.get_player_trends(target_player)
            if not df.empty:
                trend_widget = TrendGraphWidget(size_hint_y=None, height="200dp")
                trend_widget.plot(df)
                container.add_widget(trend_widget)
            else:
                pass  # Show "No Data" placeholder later

        # 2. Skill Radar
        # Radar is usually in a separate card or side-by-side
        # For now, we add it to the same container or a specific ID if available
        radar_container = self.ids.get("radar_container")
        if radar_container:
            radar_container.clear_widgets()
            skills = analytics.get_skill_radar(target_player)
            if skills:
                radar = RadarChartWidget(size_hint_y=None, height="240dp")
                radar.plot(skills)
                radar_container.add_widget(radar)

    def refresh_insights(self):
        self.ids.insights_list.clear_widgets()
        db = get_db_manager()
        with db.get_session() as session:
            # Use created_at instead of timestamp
            insights = session.exec(
                select(CoachingInsight).order_by(CoachingInsight.created_at.desc())
            ).all()
            for i in insights:
                # Map database message -> message property
                self.ids.insights_list.add_widget(
                    CoachingCard(
                        title=i.title,
                        message=i.message,
                        severity=i.severity,
                        focus_area=i.focus_area,
                    )
                )
            if not insights:
                self.ids.insights_list.add_widget(
                    MDLabel(
                        text=i18n.get_text("no_insights", MDApp.get_running_app().lang_trigger),
                        halign="center",
                    )
                )


@registry.register("user_profile")
class UserProfileScreen(MDScreen):
    def on_enter(self):
        self.load_profile_data()

    def load_profile_data(self):
        """Implementation of Step 1 [OPERABILITY]: Non-blocking DB load."""
        threading.Thread(target=self._threaded_load, daemon=True).start()

    def _threaded_load(self):
        db = get_db_manager()
        try:
            with db.get_session() as s:
                p = s.exec(select(PlayerProfile)).first()
                if p:
                    # Extract data before session closes to avoid DetachedInstanceError
                    profile_data = {
                        "player_name": p.player_name,
                        "bio": p.bio,
                        "role": p.role,
                        "steam_avatar_url": getattr(p, "steam_avatar_url", None),
                        "pc_specs_json": getattr(p, "pc_specs_json", None),
                    }
                    Clock.schedule_once(lambda dt: self._apply_profile_to_ui(profile_data), 0)
        except Exception as e:
            app_logger.debug("Profile Load Fail: %s", e)

    def _apply_profile_to_ui(self, p):
        self.ids.name_label.text = p["player_name"] or "Player"
        self.ids.bio_label.text = p["bio"] or "..."
        self.ids.role_label.text = f"Role: {p['role']}"
        self._update_role_badge(p["role"])
        if p.get("steam_avatar_url"):
            self.ids.avatar_image.source = p["steam_avatar_url"]
        if p.get("pc_specs_json"):
            # DA-01-03: Guard against malformed JSON from DB
            try:
                specs = json.loads(p["pc_specs_json"])
            except (json.JSONDecodeError, TypeError):
                specs = {}
            self.ids.specs_label.text = (
                f"CPU: {specs.get('cpu', 'N/A')} | GPU: {specs.get('gpu', 'N/A')}"
            )

    def _update_role_badge(self, r):
        # P3-01: Keys match canonical PlayerRole.value (lowercase) + legacy display names
        colors = {
            "entry": (1, 0.2, 0.2, 1),
            "Entry Fragger": (1, 0.2, 0.2, 1),
            "awper": (0.2, 0.6, 1, 1),
            "AWPer": (0.2, 0.6, 1, 1),
            "lurker": (0.6, 0.2, 0.8, 1),
            "Lurker": (0.6, 0.2, 0.8, 1),
            "support": (0.2, 0.8, 0.2, 1),
            "Support": (0.2, 0.8, 0.2, 1),
            "igl": (1, 0.8, 0, 1),
            "IGL": (1, 0.8, 0, 1),
        }
        self.ids.role_badge.md_bg_color = colors.get(r, (0.5, 0.5, 0.5, 1))

    def open_edit_dialog(self):
        content = MDBoxLayout(orientation="vertical", spacing="12dp", adaptive_height=True)
        self.bio_f = MDTextField(MDTextFieldHintText(text="Bio"), text=self.ids.bio_label.text)
        self.role_f = MDTextField(
            MDTextFieldHintText(text="Role"), text=self.ids.role_label.text.replace("Role: ", "")
        )
        content.add_widget(self.bio_f)
        content.add_widget(self.role_f)
        self.edit_dialog = MDDialog(
            MDDialogHeadlineText(text=i18n.get_text("dialog_edit_profile", self.lang_trigger)),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text=i18n.get_text("dialog_cancel", self.lang_trigger)),
                    style="text",
                    on_release=lambda x: self.edit_dialog.dismiss(),
                ),
                MDButton(
                    MDButtonText(text=i18n.get_text("dialog_save", self.lang_trigger)),
                    style="filled",
                    on_release=lambda x: self.save_profile(),
                ),
            ),
        )
        self.edit_dialog.open()

    def save_profile(self):
        """Implementation of Step 1 [OPERABILITY]: Non-blocking profile save."""
        bio, role = self.bio_f.text, self.role_f.text
        threading.Thread(target=self._threaded_profile_save, args=(bio, role), daemon=True).start()
        self.edit_dialog.dismiss()

    def _threaded_profile_save(self, bio, role):
        db = get_db_manager()
        try:
            with db.get_session() as s:
                p = s.exec(select(PlayerProfile)).first()
                if not p:
                    p = PlayerProfile(player_name="User")
                p.bio, p.role = bio, role
                s.add(p)
                s.commit()
            Clock.schedule_once(lambda dt: self.load_profile_data(), 0)
        except Exception as e:
            app_logger.debug("Profile Save Fail: %s", e)


@registry.register("settings")
class SettingsScreen(MDScreen):
    current_default_folder = StringProperty("")
    current_pro_folder = StringProperty("")
    current_font_size = StringProperty("Medium")
    current_font_type = StringProperty("Roboto")

    def on_pre_enter(self):
        self.current_default_folder = get_setting("DEFAULT_DEMO_PATH", "Not Set")
        self.current_pro_folder = get_setting("PRO_DEMO_PATH", "Not Set")
        self.current_font_size = get_setting("FONT_SIZE", "Medium")
        self.current_font_type = get_setting("FONT_TYPE", "Roboto")


@registry.register("profile")
class ProfileScreen(MDScreen):
    pass


@registry.register("steam_config")
class SteamConfigScreen(MDScreen):
    pass


@registry.register("faceit_config")
class FaceitConfigScreen(MDScreen):
    pass


class CS2AnalyzerApp(MDApp):
    background_source, coach_status = StringProperty(""), StringProperty("Initializing...")
    background_source_next = StringProperty("")
    background_opacity_current = NumericProperty(0.3)
    background_opacity_next = NumericProperty(0.0)
    belief_confidence = NumericProperty(0)
    service_active = BooleanProperty(False)
    parsing_progress = NumericProperty(0)
    knowledge_reservoir_ticks = NumericProperty(0)
    total_matches_processed = NumericProperty(0)
    selected_demo = StringProperty("")

    # Real-Time Training Metrics
    # F7-19: Properties required by TrainingStatusCard in layout.kv
    current_epoch = NumericProperty(0)
    total_epochs = NumericProperty(0)
    train_loss = NumericProperty(0.0)
    val_loss = NumericProperty(0.0)
    eta_seconds = NumericProperty(0.0)

    # Ingestion Control (Task 3)
    ingest_mode_auto = BooleanProperty(True)
    ingest_interval = NumericProperty(30)

    auth_active = BooleanProperty(False)
    is_pro, is_picker, is_viewer_load = (
        BooleanProperty(False),
        BooleanProperty(False),
        BooleanProperty(False),
    )
    lang_trigger = StringProperty("")
    upload_dialog = ObjectProperty(None, allownone=True)
    parsing_dialog = ObjectProperty(None, allownone=True)
    _last_completed_tasks = []

    @property
    def sm(self) -> MDScreenManager:
        """Safe access to the ScreenManager, regardless of root layout structure."""
        if not self.root:
            return None
        # Handle cases where ScreenManager is the root OR inside a FloatLayout/Registry
        if isinstance(self.root, MDScreenManager):
            return self.root
        if hasattr(self.root, "ids") and "screen_manager" in self.root.ids:
            return self.root.ids.screen_manager
        return None

    def open_url(self, url):
        dialog = MDDialog(
            MDDialogHeadlineText(text=i18n.get_text("dialog_open_link", self.lang_trigger)),
            MDDialogSupportingText(text=url),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text=i18n.get_text("dialog_cancel_lower", self.lang_trigger)),
                    style="text",
                    on_release=lambda x: dialog.dismiss(),
                ),
                MDButton(
                    MDButtonText(text=i18n.get_text("dialog_open", self.lang_trigger)),
                    style="filled",
                    on_release=lambda x: (dialog.dismiss(), webbrowser.open(url)),
                ),
            ),
        )
        dialog.open()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.daemon_process = None
        self._register_fonts()
        self._update_background_source()

        # 1. Standard Manager (for Ingestion/Folders) - Requires Confirmation
        self.file_manager = MDFileManager(
            exit_manager=self.exit_file_manager, select_path=self.select_path
        )

        # 2. Dedicated Viewer Manager - NO CONFIRMATION BUTTON
        # Isolated instance to prevent state pollution and library UI lag
        self.viewer_manager = MDFileManager(
            exit_manager=self.exit_viewer_manager,
            select_path=self.select_viewer_path,
            selection_button=False,
        )

        self.apply_font_settings(
            get_setting("FONT_SIZE", "Medium"), get_setting("FONT_TYPE", "Roboto")
        )
        i18n.set_language(get_setting("LANGUAGE", "en"))
        self.console = None
        self.parsing_dialog = None
        self.folder_picker_target = None  # P0-07: Initialize to prevent AttributeError

    def _update_background_source(self):
        img = get_setting("BACKGROUND_IMAGE", "vertical_wallpaper_cs2_A.jpg")
        theme = get_setting("ACTIVE_THEME", "CS2")
        folder = {"CS2": "cs2theme", "CSGO": "csgotheme", "CS1.6": "cs16theme"}.get(
            theme, "cs2theme"
        )
        path = get_resource_path(os.path.join("PHOTO_GUI", folder, img))
        if not os.path.exists(path):
            path = get_resource_path(os.path.join("PHOTO_GUI", img))
        if os.path.exists(path):
            self.background_source = path
        else:
            # Fallback to any valid file in the theme folder if specific one fails
            bg_list = self.get_available_backgrounds(theme)
            if bg_list:
                self.background_source = get_resource_path(
                    os.path.join("PHOTO_GUI", folder, bg_list[0])
                )

    def _register_fonts(self):
        f = {
            "JetBrains Mono": "JetBrainsMono-Regular.ttf",
            "Arial": "arial.ttf",
            "New Hope": "NewHope.ttf",
            "CS Regular": "cs_regular.ttf",
            "YUPIX": "YUPIX.otf",
        }
        for name, file in f.items():
            self._register_single_font(name, file)

    def _register_single_font(self, name, file):
        p = get_resource_path(os.path.join("PHOTO_GUI", file))
        if os.path.exists(p):
            LabelBase.register(name=name, fn_regular=p)

    def build(self):
        try:
            from Programma_CS2_RENAN.apps.desktop_app.help_screen import HelpScreen
            from Programma_CS2_RENAN.apps.desktop_app.match_detail_screen import MatchDetailScreen
            from Programma_CS2_RENAN.apps.desktop_app.match_history_screen import MatchHistoryScreen
            from Programma_CS2_RENAN.apps.desktop_app.performance_screen import PerformanceScreen
            from Programma_CS2_RENAN.apps.desktop_app.tactical_viewer_screen import (
                TacticalViewerScreen,
            )
            from Programma_CS2_RENAN.apps.desktop_app.wizard_screen import WizardScreen

            kv_path = get_resource_path(os.path.join("apps", "desktop_app", "layout.kv"))
            root = Builder.load_file(kv_path)
            if root:
                root.transition = FadeTransition(duration=0.2)
            return root
        except Exception as e:
            app_logger.critical("KV layout failed to load: %s", e, exc_info=True)
            fallback = MDScreenManager()
            from kivymd.uix.label import MDLabel
            from kivymd.uix.screen import MDScreen

            err_screen = MDScreen(name="error")
            err_screen.add_widget(
                MDLabel(
                    text=f"[b]UI Load Error[/b]\n\n{e}\n\nCheck logs for details.",
                    halign="center",
                    markup=True,
                    theme_text_color="Error",
                )
            )
            fallback.add_screen(err_screen)
            return fallback

    def on_start(self):
        # SERIALIZED STARTUP: Init DB -> Then Launch Daemon
        self._update_background_source()

        # FIX: Enforce Resolution (Overrides saved config)
        from kivy.core.window import Window

        Window.size = (1280, 720)

        # STARTUP LOCK CHECK (New Task 17 Feature)
        from Programma_CS2_RENAN.core.lifecycle import lifecycle

        if not lifecycle.ensure_single_instance():
            if sys.platform == "win32":
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    0, "Macena CS2 Analyzer is already running!", "Startup Error", 0x10
                )
            else:
                app_logger.error("Macena CS2 Analyzer is already running!")
            sys.exit(0)

        # FIX: Suppress Notification Spam (Pre-load existing completed tasks) - ASYNC
        def _load_startup_tasks():
            try:
                db = get_db_manager()
                # Small delay to let DB initialize
                import time

                from sqlmodel import select

                from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask

                time.sleep(0.5)
                with db.get_session("default") as s:
                    exist_tasks = s.exec(
                        select(IngestionTask.id).where(IngestionTask.status == "completed")
                    ).all()
                    self._last_completed_tasks = list(exist_tasks)
            except Exception as e:
                app_logger.warning("Startup task load error: %s", e)

        threading.Thread(target=_load_startup_tasks, daemon=True).start()

        if not (hasattr(self.root, "ids") and "screen_manager" in self.root.ids):
            app_logger.error("Fallback layout active — screen_manager unavailable")
            return
        sm = self.root.ids.screen_manager
        Clock.schedule_once(lambda dt: self._apply_runtime_settings(), 0.5)
        if get_setting("ENABLE_SLIDESHOW", False):
            self.start_slideshow()
        if not get_setting("SETUP_COMPLETED"):
            sm.current = "wizard"
            # Default High Performance for new users
            self.save_hardware_budget("cpu", 100)
            self.save_hardware_budget("ram", 100)
            self.save_hardware_budget("gpu", 100)
        else:
            sm.current = "home"

        self.refresh_quotas()
        Clock.schedule_interval(self._update_ml_status, 10)
        Clock.schedule_interval(self._check_service_notifications, 15)

        # Start the serialized infrastructure sequence
        self._init_infrastructure()

    def on_stop(self):
        """Graceful shutdown hook."""
        from Programma_CS2_RENAN.core.lifecycle import lifecycle

        lifecycle.shutdown()

        # --- Unified Control Console Shutdown ---
        from Programma_CS2_RENAN.backend.control.console import get_console

        get_console().shutdown()

    def _ensure_daemon_running(self):
        """Ensures the Session Engine (Ingestion/ML) is running via Lifecycle Manager."""
        from Programma_CS2_RENAN.core.lifecycle import lifecycle

        # Delegate to robust manager
        # This handles Popen, env vars, logging redirection, and zombie prevention
        proc = lifecycle.launch_daemon()

        if proc:
            self.daemon_process = proc
            self.service_active = True
            # Initialize console after daemon is confirmed running
            from Programma_CS2_RENAN.backend.control.console import get_console

            self.console = get_console()
        else:
            self.service_active = False
            app_logger.error("Session Engine failed to start (Lifecycle Manager)")
            self.show_error_dialog(
                "Daemon Startup Failed",
                "The background service could not start.\n"
                "Navigation and settings still work.\n"
                "Ingestion and ML features require a restart.",
            )

    def set_ingest_mode(self, auto: bool):
        """Toggles between Manual and Continuous ingestion mode."""
        self.ingest_mode_auto = auto
        # Import locally to avoid circular deps
        from Programma_CS2_RENAN.backend.control.ingest_manager import IngestMode

        mode = IngestMode.CONTINUOUS if auto else IngestMode.SINGLE
        if not self.console:
            app_logger.warning("Console not yet initialized — ignoring ingest mode change")
            return
        self.console.ingest_manager.set_mode(mode, int(self.ingest_interval))
        app_logger.info("Ingestion mode set to %s", "Auto" if auto else "Manual")

    def update_ingest_interval(self, text):
        """Updates the scan interval for Auto mode."""
        try:
            val = int(text)
            if val < 1:
                val = 1
            self.ingest_interval = val

            # Update backend if currently in Auto mode to reflect change immediately
            if self.ingest_mode_auto:
                self.set_ingest_mode(True)

            app_logger.info("Ingest interval set to %s min", val)
        except ValueError:
            app_logger.warning("Invalid interval input")

    def start_manual_ingestion(self):
        """Manually triggers the ingestion cycle."""
        if not self.console:
            self.show_error_dialog("Service Offline", "Backend not initialized yet. Wait for startup to complete.")
            return
        app_logger.info("Starting manual ingestion")
        self.console.ingest_manager.scan_all(high_priority=False)
        self.show_success_dialog("Ingestion Started", "The background digester is now active.")

    def stop_manual_ingestion(self):
        """Signals the ingestion process to stop."""
        if not self.console:
            self.show_error_dialog("Service Offline", "Backend not initialized yet.")
            return
        app_logger.info("Stopping ingestion")
        self.console.ingest_manager.stop()
        self.show_success_dialog(
            "Ingestion Stopped", "The background digester has been signalled to stop."
        )

    def _init_infrastructure(self):
        def _sequence():
            try:
                app_logger.info("Initializing Database Schema...")
                init_database()
                app_logger.info("Database Schema Ready.")
                Clock.schedule_once(lambda dt: self._ensure_daemon_running(), 0.5)
            except Exception as e:
                app_logger.critical("Infrastructure Init Failed: %s", e, exc_info=True)
                Clock.schedule_once(
                    lambda dt, err=str(e): self.show_error_dialog(
                        "Infrastructure Error",
                        f"Database initialization failed: {err}\n\n"
                        "Some features will be unavailable.",
                    ),
                    0,
                )

        threading.Thread(target=_sequence, daemon=True).start()

    _ml_status_running = False
    # F7-23: Progressive backoff when daemon is offline
    _poll_offline_strikes = 0
    _POLL_INTERVALS = [10, 30, 60]  # seconds: normal, first-strike, max backoff

    def _update_ml_status(self, dt):
        """Implementation of Step 1 [OPERABILITY]: Trigger background status refresh."""
        if self._ml_status_running:
            return
        self._ml_status_running = True
        threading.Thread(target=self._threaded_status_update, daemon=True).start()

    def _threaded_status_update(self):
        from datetime import datetime, timezone  # F7-04: timezone for utcnow replacement

        from Programma_CS2_RENAN.backend.storage.db_models import (
            CoachState,
            IngestionTask,
            PlayerProfile,
        )

        try:
            db = get_db_manager()

            # 1. Gather Coach State (from Knowledge Engine)
            is_active = False
            status_text = "Offline"
            confidence = 0.0
            progress = 0.0
            knowledge_ticks = 0
            matches_done = 0
            t_epoch, t_total, t_loss, v_loss, eta = 0, 0, 0.0, 0.0, 0.0
            active_tasks = []
            try:
                with db.get_session("knowledge") as s_k:
                    c_state = s_k.exec(select(CoachState)).first()
                    if c_state:
                        if c_state.last_heartbeat:
                            now = datetime.now(timezone.utc)  # F7-04: utcnow() deprecated
                            delta = (now - c_state.last_heartbeat).total_seconds()
                            is_active = delta < 300
                            status_text = (
                                c_state.ingest_status or "Idle"
                                if is_active
                                else f"Disconnected ({int(delta)}s ago)"
                            )
                        else:
                            status_text = "No Heartbeat"
                        confidence = getattr(c_state, "belief_confidence", 0.0)
                        progress = getattr(c_state, "parsing_progress", 0.0)
                        matches_done = getattr(c_state, "total_matches_processed", 0)

                        # Training Metrics
                        t_epoch = getattr(c_state, "current_epoch", 0)
                        t_total = getattr(c_state, "total_epochs", 0)
                        t_loss = getattr(c_state, "train_loss", 0.0)
                        v_loss = getattr(c_state, "val_loss", 0.0)
                        eta = getattr(c_state, "eta_seconds", 0.0)

            except Exception as e_k:
                app_logger.debug("Knowledge Session Fail: %s", e_k)
                t_epoch, t_total, t_loss, v_loss, eta = 0, 0, 0.0, 0.0, 0.0

            # 2. Gather Ingestion Queue Status
            try:
                with db.get_session() as s_q:
                    from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask

                    raw_tasks = s_q.exec(
                        select(IngestionTask)
                        .where(IngestionTask.status.in_(["processing", "queued"]))
                        .limit(20)
                    ).all()
                    # Materialize to plain dicts while session is open to avoid
                    # DetachedInstanceError when Clock callback fires after close.
                    active_tasks = [
                        {"demo_path": t.demo_path, "status": t.status}
                        for t in raw_tasks
                    ]
                    knowledge_ticks = s_q.exec(
                        select(func.sum(IngestionTask.last_tick_processed))
                        .where(IngestionTask.status == "complete")
                    ).one() or 0
            except Exception as e_q:
                app_logger.debug("Queue Status Fail: %s", e_q)

            # 3. Update UI
            Clock.schedule_once(
                lambda dt: self._apply_ml_status(
                    is_active,
                    status_text,
                    confidence,
                    progress,
                    knowledge_ticks,
                    matches_done,
                    t_epoch,
                    t_total,
                    t_loss,
                    v_loss,
                    eta,
                ),
                0,
            )
            Clock.schedule_once(lambda dt: self._populate_active_tasks(active_tasks), 0)

        except Exception as e:
            app_logger.debug("Global Status Update Fail: %s", e)
        finally:
            self._ml_status_running = False

    def _apply_ml_status(
        self,
        active,
        status,
        confidence,
        progress,
        ticks=0,
        matches=0,
        epoch=0,
        total_ep=0,
        t_loss=0.0,
        v_loss=0.0,
        eta=0.0,
    ):
        self.service_active = active
        self.coach_status = status
        self.belief_confidence = confidence
        self.parsing_progress = progress
        self.knowledge_reservoir_ticks = ticks
        self.total_matches_processed = matches

        # Update Training Metrics
        self.current_epoch = epoch
        self.total_epochs = total_ep
        self.train_loss = t_loss
        self.val_loss = v_loss
        self.eta_seconds = eta

        # F7-23: Progressive backoff when daemon is offline
        if not active:
            self._poll_offline_strikes = min(self._poll_offline_strikes + 1, 2)
            next_interval = self._POLL_INTERVALS[self._poll_offline_strikes]
            Clock.unschedule(self._update_ml_status)
            Clock.schedule_interval(self._update_ml_status, next_interval)
        elif self._poll_offline_strikes > 0:
            self._poll_offline_strikes = 0
            Clock.unschedule(self._update_ml_status)
            Clock.schedule_interval(self._update_ml_status, self._POLL_INTERVALS[0])

    def _populate_active_tasks(self, tasks):
        """Updates the ingestion task list on the Coach Dashboard."""
        from kivymd.uix.boxlayout import MDBoxLayout
        from kivymd.uix.label import MDIcon, MDLabel

        if not self.root:
            return
        sm = self.sm
        if not sm or sm.current != "coach":
            return

        container = sm.get_screen("coach").ids.get("active_tasks_list")
        if not container:
            return

        container.clear_widgets()
        if not tasks:
            container.add_widget(
                MDLabel(
                    text="No active ingestion flows.",
                    font_style="Body",
                    role="small",
                    theme_text_color="Hint",
                    halign="center",
                )
            )
            return

        for t in tasks:
            fname = os.path.basename(t["demo_path"])
            status = t["status"]
            status_color = (0.2, 0.8, 0.4, 1) if status == "processing" else (0.8, 0.6, 0.2, 1)
            row = MDBoxLayout(adaptive_height=True, spacing="10dp")
            row.add_widget(
                MDIcon(
                    icon="loading" if status == "processing" else "clock-outline",
                    theme_text_color="Custom",
                    text_color=status_color,
                    font_size="16sp",
                )
            )
            row.add_widget(
                MDLabel(
                    text=f"{fname} ({status})",
                    font_style="Body",
                    role="small",
                    theme_text_color="Secondary",
                )
            )
            container.add_widget(row)

    def _check_service_notifications(self, dt):
        """Implementation of Step 0 [ANALYSABILITY]: Real-time, non-blocking UI alerts."""
        threading.Thread(target=self._threaded_notification_check, daemon=True).start()

    def _threaded_notification_check(self):
        """Background DB I/O for service notifications — never blocks UI thread."""
        from Programma_CS2_RENAN.backend.storage.db_models import ServiceNotification

        try:
            db = get_db_manager()
            with db.get_session() as s:
                notifs = s.exec(
                    select(ServiceNotification)
                    .where(ServiceNotification.is_read == False)
                    .order_by(ServiceNotification.created_at.asc())
                ).all()

                if not notifs:
                    return

                latest_title = f"Service Alert: {notifs[-1].daemon.upper()}"
                latest_message = notifs[-1].message
                latest_severity = notifs[-1].severity

                # F7-37: Notifications are marked as read immediately on retrieval,
                # even if the user is not on CoachScreen. This means notifications can
                # be silently consumed. For guaranteed delivery acknowledgment, mark read
                # only in CoachScreen.on_enter().
                for n in notifs:
                    n.is_read = True
                    s.add(n)
                s.commit()

            # Schedule UI update on main thread
            def _show(dt):
                if latest_severity in ("ERROR", "CRITICAL"):
                    self.show_error_dialog(latest_title, latest_message)
                else:
                    self.show_success_dialog(latest_title, latest_message)

            Clock.schedule_once(_show, 0)
        except Exception as e:
            app_logger.debug("Notification Sync Fail: %s", e)

    def _apply_runtime_settings(self):
        self.apply_theme_styles(get_setting("ACTIVE_THEME", "CS2"))
        self.apply_font_settings(
            get_setting("FONT_SIZE", "Medium"), get_setting("FONT_TYPE", "Roboto")
        )
        i18n.set_language(get_setting("LANGUAGE", "en"))
        self.lang_trigger = get_setting("LANGUAGE", "en")

    def apply_font_settings(self, size, font_type):
        try:
            CoreLabel.flush_all()
            Cache.remove("kv.loader")
            Cache.remove("kv.image")
            Cache.remove("kv.texture")
        except Exception as e:
            app_logger.debug("Kivy cleanup error: %s", e)
        import copy

        base = {"Small": 12, "Medium": 16, "Large": 20}.get(size, 16)
        scale = base / 16.0
        allowed_fonts = ["JetBrains Mono", "Arial", "New Hope", "CS Regular", "YUPIX"]
        f_name = font_type if font_type in allowed_fonts else "Roboto"
        if not hasattr(self, "_original_font_styles"):
            self._original_font_styles = copy.deepcopy(dict(self.theme_cls.font_styles))
        new_styles = copy.deepcopy(self._original_font_styles)
        for style_name in new_styles:
            if style_name == "Icon":
                continue
            for role_name in new_styles[style_name]:
                entry = new_styles[style_name][role_name]
                entry["font-name"] = f_name
                entry["font-size"] = entry["font-size"] * scale
        self.theme_cls.font_styles = new_styles
        self._refresh_ui_text()

    def _refresh_ui_text(self):
        if not self.root:
            return
        sm = self.root.ids.screen_manager
        for screen in sm.screens:
            self._deep_widget_refresh(screen)

    def _deep_widget_refresh(self, widget, _max_depth=50):
        # F7-16: Iterative BFS to avoid stack overflow on deep widget trees
        queue = [(widget, 0)]
        while queue:
            current, depth = queue.pop(0)
            if depth > _max_depth:
                app_logger.warning("_deep_widget_refresh: max depth %s reached, stopping", _max_depth)
                break
            if hasattr(current, "font_style"):
                s = current.font_style
                current.font_style = "Body"
                current.font_style = s
            if hasattr(current, "canvas"):
                current.canvas.ask_update()
            # Explicit theme refresh for MDLabel
            if hasattr(current, "_on_theme_cls_update"):
                current._on_theme_cls_update(self.theme_cls, None)
            if hasattr(current, "children"):
                queue.extend((child, depth + 1) for child in current.children)

    def apply_theme_styles(self, name):
        # KivyMD 2.x requires hex colors or CSS color names (not old palette names)
        themes = {
            "CS2": "#FF9800",  # Orange 500
            "CSGO": "#607D8B",  # BlueGray 500
            "CS1.6": "#4CAF50",  # Green 500
        }
        p = themes.get(name, "#FF9800")

        try:
            app_logger.debug("Applying theme style: %s -> %s", name, p)
            self.theme_cls.primary_palette = p
        except Exception as e:
            app_logger.error("Could not set primary_palette to '%s'. Error: %s", p, e)
            try:
                self.theme_cls.primary_palette = "#2196F3"  # Blue 500 fallback
            except Exception as e2:
                app_logger.error("Fallback theme failed. Error: %s", e2)

        self.theme_cls.theme_style = "Dark"

    def set_app_theme(self, name):
        save_user_setting("ACTIVE_THEME", name)
        self.apply_theme_styles(name)
        self._apply_theme_wallpaper(name)
        self.show_success_dialog(
            i18n.get_text("visual_theme", self.lang_trigger), f"Switched to {name}"
        )

    def _apply_theme_wallpaper(self, name):
        bg_list = self.get_available_backgrounds(name)
        if bg_list:
            self.set_app_background(bg_list[0])

    def set_font_size(self, name):
        save_user_setting("FONT_SIZE", name)
        self.apply_font_settings(name, get_setting("FONT_TYPE", "Roboto"))
        self.show_success_dialog(
            i18n.get_text("appearance", self.lang_trigger), i18n.get_text("save", self.lang_trigger)
        )

    def set_font_type(self, name):
        save_user_setting("FONT_TYPE", name)
        current_size = get_setting("FONT_SIZE", "Medium")
        self.apply_font_settings(current_size, name)
        self.show_success_dialog(
            i18n.get_text("appearance", self.lang_trigger), i18n.get_text("save", self.lang_trigger)
        )

    def set_language(self, l):
        save_user_setting("LANGUAGE", l)
        i18n.set_language(l)
        self.lang_trigger = l
        self._refresh_ui_text()
        self.show_success_dialog(
            i18n.get_text("language", self.lang_trigger), i18n.get_text("save", self.lang_trigger)
        )

    def get_available_backgrounds(self, theme=None):
        if not theme:
            theme = get_setting("ACTIVE_THEME", "CS2")
        folder = {"CS2": "cs2theme", "CSGO": "csgotheme", "CS1.6": "cs16theme"}.get(
            theme, "cs2theme"
        )
        p_dir = get_resource_path(os.path.join("PHOTO_GUI", folder))
        if not os.path.exists(p_dir):
            p_dir = get_resource_path("PHOTO_GUI")
        exts = (".jpg", ".jpeg", ".png")
        return [f for f in os.listdir(p_dir) if f.lower().endswith(exts)]

    def set_app_background(self, img):
        theme = get_setting("ACTIVE_THEME", "CS2")
        folder = {"CS2": "cs2theme", "CSGO": "csgotheme", "CS1.6": "cs16theme"}.get(
            theme, "cs2theme"
        )
        path = get_resource_path(os.path.join("PHOTO_GUI", folder, img))
        if not os.path.exists(path):
            path = get_resource_path(os.path.join("PHOTO_GUI", img))
        if os.path.exists(path):
            # If already has a background, cross-fade to new one
            if self.background_source and self.background_source != path:
                self._animate_background_transition(path)
            else:
                self.background_source = path
            save_user_setting("BACKGROUND_IMAGE", img)

    def _animate_background_transition(self, new_path):
        """Implementation of Step 4.3: Cross-Fade animation between backgrounds."""
        self.background_source_next = new_path
        self.background_opacity_next = 0.0

        # 1. Start fade-in of next and fade-out of current
        anim = Animation(
            background_opacity_current=0.0,
            background_opacity_next=0.3,
            duration=2.0,
            t="in_out_quad",
        )

        def on_complete(*args):
            # 2. Swap sources and reset opacities silently
            self.background_source = new_path
            self.background_opacity_current = 0.3
            self.background_opacity_next = 0.0

        anim.bind(on_complete=on_complete)
        anim.start(self)

    def open_file_manager_direct(self):
        """Implementation of Step 30%: Fail-Safe Error Propagation - Direct User Upload."""
        from Programma_CS2_RENAN.backend.storage.storage_manager import StorageManager

        if not StorageManager().can_user_upload():
            return self.show_error_dialog("Limit", "You reached your monthly quota.")

        self.is_pro, self.is_picker, self.is_viewer_load = False, False, False
        self.file_manager.selector, self.file_manager.ext = "file", [".dem"]
        p = get_setting("DEFAULT_DEMO_PATH")
        if not p or not os.path.exists(p):
            p = os.path.expanduser("~")
        self.file_manager.show(p)

    def open_pro_file_manager_direct(self):
        """Implementation of Pillar 2: Professional Knowledge - Direct Pro Upload."""
        self.is_pro, self.is_picker, self.is_viewer_load = True, False, False
        self.file_manager.selector, self.file_manager.ext = "file", [".dem"]
        p = get_setting("PRO_DEMO_PATH")
        if not p or not os.path.exists(p):
            p = os.path.expanduser("~")
        self.file_manager.show(p)

    def manual_ingest_trigger(self):
        """Manually signals the daemon to start a sync cycle immediately."""
        threading.Thread(target=self._threaded_manual_ingest, daemon=True).start()

    def _threaded_manual_ingest(self):
        from Programma_CS2_RENAN.backend.storage.db_models import CoachState

        try:
            db = get_db_manager()
            with db.get_session("database") as s:  # FIX: CoachState is in database.db
                state = s.exec(select(CoachState)).first()
                if not state:
                    state = CoachState()
                    s.add(state)

                # Check monthly quota before triggering
                from Programma_CS2_RENAN.backend.storage.storage_manager import StorageManager

                if not StorageManager().can_user_upload():
                    Clock.schedule_once(
                        lambda dt: self.show_error_dialog(
                            "Quota Limit", "You have reached your 10-demo monthly limit."
                        ),
                        0,
                    )
                    return

                state.ingest_status = "Trigger Manual"
                s.add(state)
                s.commit()
            Clock.schedule_once(
                lambda dt: self.show_success_dialog(
                    "Ingestion", "Manual Sync Triggered. The coach is now scanning your folder."
                ),
                0,
            )
        except Exception as e:
            Clock.schedule_once(
                lambda dt, err=str(e): self.show_error_dialog("Trigger Failed", err), 0
            )

    def open_pro_file_manager(self):
        """Refactored to select Folder for Pro Demos."""
        self.open_folder_picker(target="pro")

    def set_pro_ingest_speed(self, interval_hours):
        """Updates the ingestion check interval for professional demos."""
        from Programma_CS2_RENAN.backend.storage.db_models import CoachState

        try:
            db = get_db_manager()
            with db.get_session(
                "database"
            ) as s:  # FIX: CoachState is in database.db, not knowledge.db
                state = s.exec(select(CoachState)).first()
                if not state:
                    state = CoachState()
                state.pro_ingest_interval = float(interval_hours)
                if float(interval_hours) == 0:
                    state.ingest_status = "Turbo Ingestion"
                s.add(state)
                s.commit()
            self.show_success_dialog("Speed Updated", f"Flux speed set to {interval_hours}h.")
        except Exception as e:
            self.show_error_dialog("Setting Fail", str(e))

    def open_folder_picker(self, target="default"):
        self.is_picker, self.folder_picker_target = True, target
        self.file_manager.selector, self.file_manager.ext = "folder", []

        # UX Upgrade: Show Drive Selector on Windows if multiple drives exist
        # instead of jumping to a potentially trapped folder
        if platform == "win":
            from Programma_CS2_RENAN.core.platform_utils import get_available_drives
            drives = get_available_drives()
            if len(drives) > 1:
                # Show Drive Selection Dialog
                self._show_drive_selector(drives)
                return
            else:
                p = drives[0]  # First available writable drive
        else:
            p = os.path.expanduser("~")  # Linux/Mac

        self.file_manager.show(p)

    def _show_drive_selector(self, drives):
        from kivymd.uix.list import MDList, MDListItem, MDListItemHeadlineText
        from kivymd.uix.scrollview import MDScrollView

        content = MDBoxLayout(orientation="vertical", size_hint_y=None, height="250dp")
        scroll = MDScrollView(size_hint_y=None, height="200dp")
        list_view = MDList()

        # Forward-declare so closure can reference it
        drive_dialog = None

        def _select_drive(drive_path):
            nonlocal drive_dialog  # F7-02: explicit nonlocal reference prevents stale closure capture
            if drive_dialog:
                drive_dialog.dismiss()
            self.file_manager.show(drive_path)

        for drive in drives:
            item = MDListItem(
                MDListItemHeadlineText(text=drive),
                on_release=lambda x, d=drive: _select_drive(d),
            )
            list_view.add_widget(item)

        scroll.add_widget(list_view)
        content.add_widget(scroll)

        drive_dialog = MDDialog(
            MDDialogHeadlineText(text=i18n.get_text("dialog_select_drive", self.lang_trigger)),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text=i18n.get_text("dialog_cancel_lower", self.lang_trigger)),
                    style="text",
                    on_release=lambda x: drive_dialog.dismiss(),
                ),
            ),
        )
        drive_dialog.open()

    def select_path(self, path):
        """
        Callback for MDFileManager.
        Handles both folder selection (ingestion path) and single .dem file upload.
        """
        self.exit_file_manager()

        if os.path.isdir(path):
            self.handle_folder_selection(path)
        elif os.path.isfile(path) and path.lower().endswith(".dem"):
            self._enqueue_single_demo(path)
        else:
            self.show_error_dialog("Invalid Selection", "Please select a folder or a .dem file.")

    def _enqueue_single_demo(self, path):
        """Enqueue a single .dem file for ingestion."""
        from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask

        db = get_db_manager()
        try:
            with db.get_session() as session:
                # P0-02: get_session() auto-commits on successful exit (database.py:120).
                # No explicit session.commit() needed.
                session.add(IngestionTask(demo_path=path, is_pro=self.is_pro))
            self.show_success_dialog("Queued", f"Demo queued for analysis: {os.path.basename(path)}")
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to queue demo: {e}")

    def toggle_ai_service(self):
        """
        Master Switch: Play/Pause Ingestion.
        Zero-Assumption: We store the state in DB. Scanning happens automatically if Active.
        """
        # Toggle local UI state logic
        self.service_active = not self.service_active
        active = self.service_active

        from datetime import datetime, timezone  # F7-04: timezone for utcnow replacement

        from Programma_CS2_RENAN.backend.storage.db_models import CoachState

        try:
            db = get_db_manager()
            with db.get_session("database") as s:
                state = s.exec(select(CoachState)).first()
                if not state:
                    state = CoachState()
                    s.add(state)

                # Update State
                state.ingest_status = "Scanning" if active else "Paused"
                state.last_updated = datetime.now(timezone.utc)  # F7-04: utcnow() deprecated
                s.add(state)
                s.commit()

        except Exception as e:
            self.show_error_dialog("Control Error", str(e))
            self.service_active = not active  # Revert on error

    def handle_folder_selection(self, path):
        # P0-07: Guard against missing folder_picker_target when called from
        # paths other than open_folder_picker (e.g., open_file_manager_direct).
        if self.folder_picker_target is None:
            return
        k = "DEFAULT_DEMO_PATH" if self.folder_picker_target == "default" else "PRO_DEMO_PATH"

        # Capture old MATCH_DATA_PATH before saving (for migration)
        old_match_data_path = None
        if k == "PRO_DEMO_PATH":
            from Programma_CS2_RENAN.core.config import MATCH_DATA_PATH

            old_match_data_path = MATCH_DATA_PATH

        save_user_setting(k, path)

        # Migrate match_data if PRO_DEMO_PATH changed
        if k == "PRO_DEMO_PATH" and old_match_data_path is not None:
            refresh_settings()
            from Programma_CS2_RENAN.core.config import MATCH_DATA_PATH as new_mdp

            if os.path.normpath(old_match_data_path) != os.path.normpath(new_mdp):
                try:
                    from Programma_CS2_RENAN.backend.storage.match_data_manager import (
                        migrate_match_data,
                        reset_match_data_manager,
                    )

                    result = migrate_match_data(old_match_data_path, new_mdp)
                    reset_match_data_manager()
                    msg = f"Match data migrated: {result['moved']} moved"
                    if result["skipped"]:
                        msg += f", {result['skipped']} skipped"
                    if result["errors"]:
                        msg += f", {len(result['errors'])} errors"
                    app_logger.info(msg)
                except Exception as e:
                    app_logger.error("Match data migration failed: %s", e)

        # UX: Just show confirmation. Scanner picks it up automatically.
        self.show_success_dialog("Folder Set", f"New path: {path}")
        if hasattr(self.root, "ids") and "screen_manager" in self.root.ids:
            sm = self.root.ids.screen_manager
            if sm.current == "settings":
                sm.get_screen("settings").on_pre_enter()

    def exit_file_manager(self, *args):
        self.file_manager.close()
        self.file_manager.selector = "any"

    def refresh_quotas(self):
        """Implementation of Step 1 [OPERABILITY]: Non-blocking quota refresh."""
        threading.Thread(target=self._threaded_quota_refresh, daemon=True).start()

    def _threaded_quota_refresh(self):
        from sqlmodel import func, select

        from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask, PlayerProfile

        try:
            db = get_db_manager()
            with db.get_session() as s:
                p = s.exec(select(PlayerProfile)).first()

                # Check for active processing
                processing_count = s.exec(
                    select(func.count()).where(IngestionTask.status == "processing")
                ).one()
                failed_count = s.exec(
                    select(func.count()).where(IngestionTask.status == "failed")
                ).one()

                # Fetch specific active tasks for the monitor
                active_tasks = s.exec(
                    select(IngestionTask)
                    .where(IngestionTask.status.in_(["processing", "queued"]))
                    .limit(5)
                ).all()

                task_data = [
                    {"file": os.path.basename(t.demo_path), "status": t.status}
                    for t in active_tasks
                ]

                status_text = i18n.get_text("upload_status", self.lang_trigger)
                if processing_count > 0:
                    status_text = f"Coach is Analyzing {processing_count} Demo(s)... 🧠"
                elif failed_count > 0:
                    status_text = f"Warning: {failed_count} Demos Failed Analysis."

                quota_text = ""
                if p and hasattr(p, "monthly_upload_count"):
                    quota_text = (
                        f"Quota: {p.monthly_upload_count}/10 | Total: {p.total_upload_count}/100"
                    )
                Clock.schedule_once(
                    lambda dt: self._apply_quota_text(quota_text, status_text, task_data), 0
                )
        except Exception as e:
            app_logger.debug("Quota Refresh Error: %s", e)

    def _apply_quota_text(self, quota_text, status_text, task_data=None):
        """Implementation of Step 21.2: Interactive Ingestion Monitoring."""
        # Home Screen Status
        if self.sm and self.sm.has_screen("home"):
            h = self.sm.get_screen("home")
            h.ids.quota_label.text = quota_text
            h.ids.upload_status_label.text = status_text
            if "Analyzing" in status_text:
                h.ids.upload_status_label.theme_text_color = "Custom"
                h.ids.upload_status_label.text_color = (0.2, 1, 0.5, 1)  # Green
            else:
                h.ids.upload_status_label.theme_text_color = "Secondary"

        # Coach Screen Task List
        if self.sm and self.sm.has_screen("coach") and task_data is not None:
            c = self.sm.get_screen("coach")
            try:
                tlist = c.ids.active_tasks_list
                pcard = c.ids.ingestion_progress_card

                tlist.clear_widgets()
                if not task_data:
                    pcard.opacity = 0
                    pcard.height = "0dp"
                else:
                    from kivymd.uix.label import MDLabel

                    pcard.opacity = 1
                    pcard.height = "160dp"
                    for t in task_data:
                        icon = "⏳" if t["status"] == "queued" else "🔄"
                        color = [0.5, 0.5, 0.5, 1] if t["status"] == "queued" else [0.2, 1, 0.5, 1]
                        tlist.add_widget(
                            MDLabel(
                                text=f"{icon} {t['file']} - {t['status'].upper()}",
                                font_style="Body",
                                role="small",
                                theme_text_color="Custom",
                                text_color=color,
                                adaptive_height=True,
                            )
                        )
            except Exception as e:
                app_logger.debug("Progress UI update failed: %s", e)

    def launch_tactical_viewer(self):
        """Implementation of Step 100%: Total Tactical Laboratory - Entry Point."""
        self.switch_screen("tactical_viewer")

    def trigger_viewer_picker(self):
        """Opens the dedicated Viewer Manager (One-Click flow)."""
        self.is_viewer_load = True
        self.is_pro, self.is_picker = False, False

        # Ensure it's filtered for demos
        self.viewer_manager.ext = [".dem"]

        p = get_setting("DEFAULT_DEMO_PATH")
        if not p or not os.path.exists(p):
            p = os.path.expanduser("~")

        app_logger.debug("Launching One-Click Viewer Picker at %s", p)
        self.viewer_manager.show(p)

    def select_viewer_path(self, path):
        """Dedicated One-Click callback for the Tactical Viewer."""
        app_logger.debug("select_viewer_path (Immediate) triggered: %s", path)
        self.exit_viewer_manager()

        target_path = path[0] if isinstance(path, list) and len(path) > 0 else path
        if target_path and os.path.exists(target_path):
            # Start parsing immediately
            Clock.schedule_once(lambda dt: self._handle_viewer_load(target_path), 0.1)

        self.is_viewer_load = False

    def exit_viewer_manager(self, *args):
        app_logger.debug("Exiting Viewer Manager.")
        self.viewer_manager.close()

    def _handle_viewer_load(self, path):
        """Implementation of Step 70%: Tactical Timeline Sync - Viewer Entry."""
        self.is_viewer_load = False
        paths = path if isinstance(path, list) else [path]
        if not paths:
            return
        if self.parsing_dialog:
            return

        from kivymd.uix.progressindicator import MDCircularProgressIndicator

        content = MDBoxLayout(
            orientation="vertical", spacing="20dp", padding="20dp", adaptive_height=True
        )
        content.add_widget(
            MDCircularProgressIndicator(
                size_hint=(None, None), size=("48dp", "48dp"), pos_hint={"center_x": 0.5}
            )
        )
        content.add_widget(
            MDLabel(
                text=i18n.get_text("dialog_reconstructing", self.lang_trigger),
                halign="center", theme_text_color="Secondary",
            )
        )
        self.parsing_dialog = MDDialog(
            MDDialogHeadlineText(text=i18n.get_text("dialog_tactical_lab", self.lang_trigger)),
            MDDialogContentContainer(content),
            auto_dismiss=False,
        )
        self.parsing_dialog.open()

        # Use a dedicated thread for the heavy demoparser2 lifting
        threading.Thread(target=lambda: self._execute_viewer_parse(paths[0]), daemon=True).start()

    def _execute_viewer_parse(self, path):
        from Programma_CS2_RENAN.ingestion.demo_loader import DemoLoader

        try:
            data = DemoLoader.load_demo(path)
            Clock.schedule_once(lambda dt: self._on_viewer_parse_complete(data, path), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt, err=str(e): self._on_viewer_parse_fail(err), 0)

    def _on_viewer_parse_complete(self, data, path):
        if self.parsing_dialog:
            self.parsing_dialog.dismiss()
            self.parsing_dialog = None
        sm = self.root.ids.screen_manager
        sm.current = "tactical_viewer"
        viewer = sm.get_screen("tactical_viewer")
        viewer.full_demo_data = data
        map_list = list(data.keys())
        viewer.ids.map_spinner.values = map_list
        if map_list:
            viewer.switch_map(map_list[0])
        self.show_success_dialog("Ready", f"Loaded: {os.path.basename(path)}")

    def _on_viewer_parse_fail(self, error):
        if self.parsing_dialog:
            self.parsing_dialog.dismiss()
            self.parsing_dialog = None
        self.show_error_dialog(
            i18n.get_text("dialog_analysis_failed", self.lang_trigger), str(error)
        )

    def show_error_dialog(self, t, txt):
        ok = i18n.get_text("dialog_ok", self.lang_trigger)
        dlg = MDDialog(
            MDDialogHeadlineText(text=t),
            MDDialogSupportingText(text=txt),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text=ok), style="text", on_release=lambda x: dlg.dismiss()),
            ),
        )
        dlg.open()

    def show_success_dialog(self, t, txt):
        ok = i18n.get_text("dialog_ok", self.lang_trigger)
        dlg = MDDialog(
            MDDialogHeadlineText(text=t),
            MDDialogSupportingText(text=txt),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text=ok), style="filled", on_release=lambda x: dlg.dismiss()
                ),
            ),
        )
        dlg.open()

    def show_upload_rules(self):
        self.show_success_dialog(
            i18n.get_text("upload_rules_title", self.lang_trigger),
            i18n.get_text("upload_rules_text", self.lang_trigger),
        )

    def show_skill_radar(self):
        """Visualizes multi-dimensional player growth."""
        from Programma_CS2_RENAN.backend.nn.coach_manager import CoachTrainingManager
        from Programma_CS2_RENAN.backend.services.visualization_service import (
            generate_performance_radar,
        )

        manager = CoachTrainingManager()
        data = manager.get_skill_radar_data()

        if data.get("status") == "error":
            return self.show_error_dialog(
                "No User Data",
                "Upload your demos first to generate skill radar.\n\n"
                "Your personal matches need to be analyzed before comparison with pro players.",
            )

        # Generate radar plot
        import atexit
        out_path = os.path.join(get_resource_path("data"), "temp_radar.png")
        # F7-11: Register temp file for cleanup on app exit
        atexit.register(lambda: os.path.exists(out_path) and os.unlink(out_path))
        try:
            generate_performance_radar(data["user_stats"], data["pro_baseline"], out_path)
        except Exception as e:
            return self.show_error_dialog(
                "Visualization Error", f"Could not generate radar: {str(e)}"
            )

        from kivy.uix.image import AsyncImage
        from kivymd.uix.boxlayout import MDBoxLayout

        content = MDBoxLayout(orientation="vertical", size_hint_y=None, height="400dp")
        content.add_widget(AsyncImage(source=out_path, allow_stretch=True, keep_ratio=True))

        dlg = MDDialog(
            MDDialogHeadlineText(text=i18n.get_text("dialog_skill_radar", self.lang_trigger)),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text=i18n.get_text("dialog_close", self.lang_trigger)),
                    style="text", on_release=lambda x: dlg.dismiss(),
                ),
            ),
        )
        dlg.open()

    def show_interactive_overlay(self):
        """Shows tactical decision maps."""
        self.show_success_dialog(
            "Tactical Overlay",
            "Tactical Overlay is a planned feature for future releases.\n\n"
            "Current Status: In Development\n"
            "Expected: Phase 2 updates",
        )

    def show_pro_comparison_dialog(self):
        """
        Shows educational context if the model is not yet trained.
        """
        threading.Thread(target=self._threaded_pro_comparison_check, daemon=True).start()

    def _threaded_pro_comparison_check(self):
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.db_models import CoachState

        count = 0
        try:
            db = get_db_manager()
            with db.get_session("knowledge") as s:
                st = s.exec(select(CoachState)).first()
                if st:
                    count = st.last_trained_sample_count
        except Exception as e:
            app_logger.debug("CoachState query failed: %s", e)

        # Prepare dialogue on main thread
        if count < 10:
            Clock.schedule_once(
                lambda dt: self.show_success_dialog(
                    "Technical Audit: Decision Path",
                    f"This view visualizes the [b]Explainable AI (XAI)[/b] trace.\n\n"
                    "The path identifies which behavioral neurons are driving the current tactical advice. This requires high neural stability to generate.\n\n"
                    "[color=FFAA00][b]CALIBRATION IN PROGRESS:[/b][/color]\n"
                    "Ingesting professional matches to build neural baseline.\n"
                    "(Steam/FACEIT connection NOT required for Pro Analysis)\n\n"
                    f"[i]Current Pipeline Progress: {count} / 10 Matches[/i]",
                ),
                0,
            )
        else:
            Clock.schedule_once(
                lambda dt: self.show_success_dialog(
                    i18n.get_text("pro_comparison", self.lang_trigger),
                    "Visualizing Neural Activation Map...",
                ),
                0,
            )

    def show_brain_dialog(self):
        try:
            from Programma_CS2_RENAN.backend.nn.config import get_brain_dir
            from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

            ckpt = get_brain_dir() / ModelFactory.get_checkpoint_name(ModelFactory.TYPE_RAP)
            if ckpt.exists():
                status = "ACTIVE (trained checkpoint found)"
            else:
                status = "NOT TRAINED (no checkpoint — predictions use random weights)"
        except Exception:
            status = "UNAVAILABLE (could not query brain status)"
        self.show_success_dialog("The Brain", f"Neural Engine: {status}")

    def soft_restart_service(self):
        """Trigger a re-launch and PID cleanup for the background daemons."""
        try:
            # Kill existing daemon if tracked
            if self.daemon_process:
                try:
                    self.daemon_process.terminate()
                    self.daemon_process.wait(timeout=1)
                except Exception as e:
                    app_logger.debug("Daemon terminate failed: %s", e)
                self.daemon_process = None

            # Relaunch Session Engine
            self._ensure_daemon_running()

            self.show_success_dialog("Service Restart", "Session Engine restarted.")
        except Exception as e:
            self.show_error_dialog("Restart Fail", str(e))

    def save_hardware_budget(self, budget_type, value):
        """Update global hardware limits in the database. DEPRECATED - Sliders should be removed from UI."""
        import warnings
        import threading
        from datetime import datetime, timezone  # F7-04: timezone for utcnow replacement

        # F7-08: deprecation warning — kept for backward compatibility
        warnings.warn(
            "save_hardware_budget() is deprecated. Use save_user_setting('HARDWARE_BUDGET', ...) directly.",
            DeprecationWarning,
            stacklevel=2,
        )

        from Programma_CS2_RENAN.backend.storage.db_models import CoachState

        def _bg_update():
            try:
                db = get_db_manager()
                with db.get_session("database") as s:  # FIX: CoachState is in database.db
                    state = s.exec(select(CoachState)).first()
                    if state:
                        val = float(value) / 100.0
                        if budget_type == "cpu":
                            state.cpu_limit = val
                        elif budget_type == "ram":
                            state.ram_limit = val
                        elif budget_type == "gpu":
                            state.gpu_limit = val
                        state.last_updated = datetime.now(timezone.utc)  # F7-04: utcnow() deprecated
                        s.add(state)
                        s.commit()
            except Exception as e:
                app_logger.error("Failed to save hardware budget: %s", e)

        threading.Thread(target=_bg_update, daemon=True).start()

    # P4-10: Navigation back-stack for proper history-based back navigation
    _nav_stack: list = []

    def switch_screen(self, n, push_history: bool = True):
        if self.root:
            sm = self.root.ids.screen_manager
            if push_history and sm.current != n:
                self._nav_stack.append(sm.current)
            sm.current = n

    def go_back(self):
        """Navigate to the previous screen in the history stack."""
        if self._nav_stack and self.root:
            self.root.ids.screen_manager.current = self._nav_stack.pop()

    def save_multiple_configs(self, cfg):
        for k, v in cfg.items():
            save_user_setting(k, v)
        self.show_success_dialog(
            i18n.get_text("settings", self.lang_trigger), i18n.get_text("save", self.lang_trigger)
        )

    def save_user_config(self, key, value):
        save_user_setting(key, value)
        self.show_success_dialog(
            i18n.get_text("settings", self.lang_trigger), i18n.get_text("save", self.lang_trigger)
        )

    def start_slideshow(self):
        Clock.schedule_interval(self._slideshow_tick, 20)

    def stop_slideshow(self):
        Clock.unschedule(self._slideshow_tick)

    def _slideshow_tick(self, dt):
        self.cycle_wallpaper()

    def toggle_slideshow(self, active):
        save_user_setting("ENABLE_SLIDESHOW", active)
        if active:
            self.start_slideshow()
        else:
            self.stop_slideshow()

    def cycle_wallpaper(self):
        b = self.get_available_backgrounds()
        if not b:
            return
        c = os.path.basename(self.background_source)
        try:
            n = b[(b.index(c) + 1) % len(b)]
        except (ValueError, IndexError):
            n = b[0]
        self.set_app_background(n)

    def sync_profile_with_steam(self):
        """Implementation of Step 1 [OPERABILITY]: Non-blocking Network Sync."""
        threading.Thread(target=self._threaded_steam_sync, daemon=True).start()

    def _threaded_steam_sync(self):
        try:
            from Programma_CS2_RENAN.backend.data_sources.steam_api import fetch_steam_profile

            s_id, s_key = get_setting("STEAM_ID", ""), get_setting("STEAM_API_KEY", "")
            if not s_id or not s_key:
                raise ValueError("Missing Steam ID/Key")

            data = fetch_steam_profile(s_id, s_key)

            db = get_db_manager()
            with db.get_session() as s:
                p = s.exec(select(PlayerProfile)).first()
                if not p:
                    p = PlayerProfile(player_name=data.get("personaname", "User"))
                    s.add(p)
                    s.commit()
            app_logger.info("Steam profile synced for %s", data.get("personaname", "Unknown"))

            Clock.schedule_once(lambda dt: self._on_steam_sync_success(), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt, err=str(e): self.show_error_dialog("Failed", err), 0)

    def _on_steam_sync_success(self):
        if self.sm and self.sm.current == "user_profile":
            self.sm.get_screen("user_profile").load_profile_data()
        self.show_success_dialog("Steam", "Synced.")


if __name__ == "__main__":
    try:
        # --- Unified Control Console Integration ---
        from Programma_CS2_RENAN.backend.control.console import get_console

        console = get_console()

        # Special mode: HLTV Service Loop (Legacy support for detached mode)
        if "--hltv-service" in sys.argv:
            from Programma_CS2_RENAN.hltv_sync_service import run_sync_loop

            run_sync_loop()
            sys.exit(0)

        # Standard Mode: Boot Console (which handles background services and DB)
        console.boot()

        CS2AnalyzerApp().run()
    except Exception:
        app_logger.critical("Fatal error:\n%s", traceback.format_exc())
