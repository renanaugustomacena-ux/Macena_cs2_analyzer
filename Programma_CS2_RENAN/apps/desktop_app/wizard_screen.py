import os
from pathlib import Path

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.screenmanager import Screen
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from Programma_CS2_RENAN.core.config import get_setting, save_user_setting
from Programma_CS2_RENAN.core.platform_utils import get_available_drives
from Programma_CS2_RENAN.observability.logger_setup import get_logger

app_logger = get_logger("cs2analyzer.wizard_screen")
from kivy.utils import platform
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogContentContainer,
    MDDialogHeadlineText,
    MDDialogSupportingText,
)
from kivymd.uix.list import MDList, MDListItem, MDListItemHeadlineText
from kivymd.uix.scrollview import MDScrollView

from Programma_CS2_RENAN.core.localization import i18n
from Programma_CS2_RENAN.core.registry import registry


@registry.register("wizard")
class WizardScreen(MDScreen):
    step = StringProperty("intro")  # intro, brain_path, demo_path, finish
    brain_path = StringProperty("")
    demo_path = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = None
        self.file_manager = MDFileManager(
            exit_manager=self.exit_file_manager, select_path=self.select_path, selector="folder"
        )
        self.selection_target = ""

    def on_enter(self):
        self.app = MDApp.get_running_app()
        self.brain_path = get_setting("BRAIN_DATA_ROOT", "")
        self.demo_path = get_setting("DEFAULT_DEMO_PATH", "")
        # Defer to ensure IDs are populated
        Clock.schedule_once(lambda dt: self.load_step("intro"), 0)

    def load_step(self, step_name):
        app_logger.debug("Loading step %s", step_name)
        try:
            self.step = step_name
            self.ids.content_area.clear_widgets()

            if step_name == "intro":
                self.build_intro()
            elif step_name == "brain_path":
                self.build_brain_path()
            elif step_name == "demo_path":
                self.build_demo_path()
            elif step_name == "finish":
                self.build_finish()
        except Exception as e:
            app_logger.error("Critical error in load_step: %s", e, exc_info=True)
            dlg = MDDialog(
                MDDialogSupportingText(
                    text="An error occurred loading this step. Please try again."
                ),
                MDDialogButtonContainer(
                    MDButton(
                        MDButtonText(text="OK"), style="text", on_release=lambda x: dlg.dismiss()
                    ),
                ),
            )
            dlg.open()

    def build_intro(self):
        self.ids.title_label.text = i18n.get_text("wizard_intro_title", self.app.lang_trigger)
        l = MDLabel(
            text=i18n.get_text("wizard_intro_text", self.app.lang_trigger),
            halign="center",
            theme_text_color="Secondary",
            font_style="Body",
            role="large",
        )
        self.ids.content_area.add_widget(l)
        self.ids.next_btn.text = i18n.get_text("wizard_start_btn", self.app.lang_trigger)

    def build_brain_path(self):
        self.ids.title_label.text = i18n.get_text("wizard_step1_title", self.app.lang_trigger)
        box = MDBoxLayout(
            orientation="vertical", spacing="20dp", adaptive_height=True, pos_hint={"center_y": 0.5}
        )

        info = MDLabel(
            text=i18n.get_text("wizard_step1_desc", self.app.lang_trigger),
            halign="center",
            font_style="Body",
            role="medium",
        )

        box.add_widget(info)

        # Manual Entry Fallback
        self.brain_field = MDTextField(
            MDTextFieldHintText(text=i18n.get_text("wizard_step1_hint", self.app.lang_trigger)),
            text=self.brain_path,
            mode="outlined",
            on_text_validate=self.validate_brain_step,
        )
        box.add_widget(self.brain_field)

        path_lbl = MDLabel(
            text=f"{i18n.get_text('select_round', self.app.lang_trigger)}: {self.brain_path or 'None'}",
            halign="center",
            bold=True,
            theme_text_color="Primary",
            font_style="Body",
            role="small",
        )
        btn = MDButton(
            MDButtonText(text=i18n.get_text("wizard_select_folder", self.app.lang_trigger)),
            style="filled",
            pos_hint={"center_x": 0.5},
            on_release=lambda x: self.open_picker("brain"),
        )

        box.add_widget(path_lbl)
        box.add_widget(btn)

        self.ids.content_area.add_widget(box)
        self.ids.next_btn.text = i18n.get_text("next", self.app.lang_trigger)

    def build_finish(self):
        self.ids.title_label.text = i18n.get_text("wizard_finish_title", self.app.lang_trigger)
        l = MDLabel(
            text=i18n.get_text("wizard_finish_text", self.app.lang_trigger),
            halign="center",
            font_style="Body",
            role="large",
        )
        self.ids.content_area.add_widget(l)
        self.ids.next_btn.text = i18n.get_text("wizard_launch_btn", self.app.lang_trigger)

    def build_demo_path(self):
        from Programma_CS2_RENAN.core.localization import i18n

        self.ids.title_label.text = i18n.get_text("wizard_step2_title", self.app.lang_trigger)
        box = MDBoxLayout(
            orientation="vertical", spacing="20dp", adaptive_height=True, pos_hint={"center_y": 0.5}
        )

        info = MDLabel(
            text=i18n.get_text("wizard_step2_desc", self.app.lang_trigger),
            halign="center",
            font_style="Body",
            role="medium",
        )
        box.add_widget(info)

        self.demo_field = MDTextField(
            MDTextFieldHintText(text=i18n.get_text("wizard_step2_hint", self.app.lang_trigger)),
            text=self.demo_path,
            mode="outlined",
            on_text_validate=self.validate_demo_step,
        )
        box.add_widget(self.demo_field)

        path_lbl = MDLabel(
            text=f"{i18n.get_text('select_round', self.app.lang_trigger)}: {self.demo_path or 'None'}",
            halign="center",
            bold=True,
            theme_text_color="Primary",
            font_style="Body",
            role="small",
        )
        btn = MDButton(
            MDButtonText(text=i18n.get_text("wizard_select_folder", self.app.lang_trigger)),
            style="filled",
            pos_hint={"center_x": 0.5},
            on_release=lambda x: self.open_picker("demo"),
        )

        box.add_widget(path_lbl)
        box.add_widget(btn)

        self.ids.content_area.add_widget(box)
        self.ids.next_btn.text = i18n.get_text("next", self.app.lang_trigger)

    def validate_demo_step(self, *args):
        """Validate demo path and advance to finish step."""
        if hasattr(self, "demo_field") and self.demo_field.text:
            self.demo_path = self.demo_field.text

        if not self.demo_path:
            # Skip is acceptable — demo path is optional
            app_logger.debug("No demo path provided, skipping to finish")
            Clock.schedule_once(lambda dt: self.load_step("finish"), 0.1)
            return

        if not os.path.isdir(self.demo_path):
            try:
                os.makedirs(self.demo_path, exist_ok=True)
            except OSError as e:
                app_logger.warning("Cannot create demo path %s: %s", self.demo_path, e)

        save_user_setting("DEFAULT_DEMO_PATH", self.demo_path)
        app_logger.debug("Demo path saved: %s", self.demo_path)
        Clock.schedule_once(lambda dt: self.load_step("finish"), 0.1)

    def _show_drive_selector(self, drives):
        content = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint_y=None)
        scroll = MDScrollView(size_hint_y=None, height="200dp")
        list_view = MDList()

        dialog = None

        def _select_drive(drive_path):
            if dialog:
                dialog.dismiss()
            self.file_manager.show(drive_path)

        for drive in drives:
            item = MDListItem(
                MDListItemHeadlineText(text=drive), on_release=lambda x, d=drive: _select_drive(d)
            )
            list_view.add_widget(item)

        scroll.add_widget(list_view)
        content.add_widget(scroll)

        dialog = MDDialog(
            MDDialogHeadlineText(text="Select Drive"),
            MDDialogContentContainer(content),
        )
        dialog.open()

    def open_picker(self, target):
        app_logger.debug("Opening picker for %s", target)
        self.selection_target = target

        if platform == "win":
            drives = get_available_drives()
            if len(drives) > 1:
                self._show_drive_selector(drives)
                return
            else:
                start_path = drives[0]
        else:
            start_path = os.path.expanduser("~")

        if target == "brain" and self.brain_path and os.path.exists(self.brain_path):
            start_path = self.brain_path
        if target == "demo" and self.demo_path and os.path.exists(self.demo_path):
            start_path = self.demo_path

        app_logger.debug("FileManager showing at %s", start_path)
        self.file_manager.show(start_path)

    def select_path(self, path):
        path = os.path.normpath(path)
        app_logger.debug("Path selected: %s", path)
        self.exit_file_manager()
        if not os.path.exists(path):
            app_logger.warning("Selected path does not exist: %s", path)
            return
        if self.selection_target == "brain":
            self.brain_path = path
            app_logger.debug("brain_path set to %s", self.brain_path)
            self.load_step("brain_path")
        elif self.selection_target == "demo":
            self.demo_path = path
            self.load_step("demo_path")

    def exit_file_manager(self, *args):
        self.file_manager.close()

    def validate_brain_step(self, *args):
        app_logger.debug("validate_brain_step called")
        # Check text field first if manual entry
        if hasattr(self, "brain_field") and self.brain_field.text:
            # DA-WZ-01: Normalize path to prevent traversal and handle user shortcuts
            self.brain_path = os.path.normpath(os.path.expanduser(self.brain_field.text.strip()))
            app_logger.debug("Using manual text: %s", self.brain_path)
        else:
            app_logger.debug("Using selection: %s", self.brain_path)

        if not self.brain_path:
            app_logger.debug("No path provided")
            dlg = MDDialog(
                MDDialogSupportingText(text="Please select a folder or paste a path."),
                MDDialogButtonContainer(
                    MDButton(
                        MDButtonText(text="OK"), style="text", on_release=lambda x: dlg.dismiss()
                    ),
                ),
            )
            dlg.open()
            return

        # Validate and Create
        try:
            app_logger.debug("Attempting to create %s", self.brain_path)
            if not os.path.exists(self.brain_path):
                os.makedirs(self.brain_path)

            root = Path(self.brain_path)
            (root / "knowledge").mkdir(parents=True, exist_ok=True)
            (root / "models").mkdir(parents=True, exist_ok=True)
            (root / "datasets").mkdir(parents=True, exist_ok=True)

            app_logger.debug("Folders created. Saving setting.")
            save_user_setting("BRAIN_DATA_ROOT", self.brain_path)

            app_logger.debug("Loading next step 'demo_path'")
            # Force main thread update to prevent UI freeze
            Clock.schedule_once(lambda dt: self.load_step("demo_path"), 0.1)

        except OSError as e:
            app_logger.error("OSError creating brain folder: %s", e)
            if "Permission" in str(e) or "Access" in str(e):
                user_docs = Path(os.path.expanduser("~")) / "Documents" / "DataCoach"
                err_msg = f"Permission Denied for {self.brain_path}.\n\nPlease try: {user_docs}"
            else:
                err_msg = f"Error creating folder: {e}\n\nTry a different location (e.g. inside Documents)."

            dlg = MDDialog(
                MDDialogSupportingText(text=err_msg),
                MDDialogButtonContainer(
                    MDButton(
                        MDButtonText(text="OK"), style="text", on_release=lambda x: dlg.dismiss()
                    ),
                ),
            )
            dlg.open()
        except Exception as e:
            app_logger.error("General exception during validation: %s", e, exc_info=True)
            dlg = MDDialog(
                MDDialogSupportingText(
                    text="An unexpected error occurred. Please check your settings."
                ),
                MDDialogButtonContainer(
                    MDButton(
                        MDButtonText(text="OK"), style="text", on_release=lambda x: dlg.dismiss()
                    ),
                ),
            )
            dlg.open()

    def next_action(self):
        """Central dispatcher for the Next button."""
        app_logger.debug("next_action called for step %s", self.step)
        if self.step == "intro":
            self.load_step("brain_path")
        elif self.step == "brain_path":
            self.validate_brain_step()
        elif self.step == "demo_path":
            self.validate_demo_step()
        elif self.step == "finish":
            self.finish_setup()

    def finish_setup(self):
        save_user_setting("SETUP_COMPLETED", True)

        # Start Daemon with proper logging
        import subprocess
        import sys

        try:
            # We assume the daemon script is reachable.
            # In a real build, we might need a more robust path resolution (like RASP).
            app_logger.debug("Attempting to start daemon...")
            # For now, we trust the main app process to handle the daemon life-cycle
            # or just proceed to the home screen where the SessionEngine is running.

            if self.manager:
                self.manager.current = "home"
        except Exception as e:
            app_logger.error("Failed to transition after setup: %s", e)
            MDDialog(
                MDDialogSupportingText(text=f"Setup complete, but failed to load Home: {e}")
            ).open()
