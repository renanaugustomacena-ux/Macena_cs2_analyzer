"""
Application entry point — launches the PySide6 Qt frontend.

Usage:
    python -m Programma_CS2_RENAN.apps.qt_app.app
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from Programma_CS2_RENAN.apps.qt_app.core.theme_engine import ThemeEngine
from Programma_CS2_RENAN.apps.qt_app.main_window import MainWindow
from Programma_CS2_RENAN.apps.qt_app.screens.placeholder import create_placeholder_screens


def main():
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Macena CS2 Analyzer")

    # Register custom fonts and apply theme + font
    theme = ThemeEngine()
    theme.register_fonts()

    from Programma_CS2_RENAN.core.config import get_setting

    font_type = get_setting("FONT_TYPE", "Roboto")
    font_sizes = {"Small": 11, "Medium": 13, "Large": 16}
    font_pt = font_sizes.get(get_setting("FONT_SIZE", "Medium"), 13)
    theme._font_family = font_type
    theme._font_size = font_pt

    active_theme = get_setting("ACTIVE_THEME", "CS2")
    theme.apply_theme(active_theme, app)

    # Create main window
    window = MainWindow()

    # Set initial wallpaper
    window.set_wallpaper(theme.wallpaper_path)

    # Register placeholder screens for pages not yet ported
    placeholders = create_placeholder_screens()

    # ── Phase 2: Real data screens ──
    from Programma_CS2_RENAN.apps.qt_app.screens.match_history_screen import (
        MatchHistoryScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.match_detail_screen import (
        MatchDetailScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.performance_screen import (
        PerformanceScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.settings_screen import (
        SettingsScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.wizard_screen import (
        WizardScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.user_profile_screen import (
        UserProfileScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.profile_screen import (
        ProfileScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.home_screen import (
        HomeScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.coach_screen import (
        CoachScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.steam_config_screen import (
        SteamConfigScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.faceit_config_screen import (
        FaceitConfigScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.help_screen import (
        HelpScreen,
    )
    from Programma_CS2_RENAN.apps.qt_app.screens.tactical_viewer_screen import (
        TacticalViewerScreen,
    )

    match_history = MatchHistoryScreen()
    match_detail = MatchDetailScreen()
    performance = PerformanceScreen()
    settings = SettingsScreen(theme_engine=theme)
    wizard = WizardScreen()
    user_profile = UserProfileScreen()
    profile = ProfileScreen()
    home = HomeScreen()
    coach = CoachScreen()
    steam_config = SteamConfigScreen()
    faceit_config = FaceitConfigScreen()
    help_screen = HelpScreen()
    tactical_viewer = TacticalViewerScreen()

    # Wire match selection: history → detail
    def _on_match_selected(demo_name: str):
        match_detail.load_demo(demo_name)
        window.switch_screen("match_detail")

    match_history.match_selected.connect(_on_match_selected)

    # Replace placeholders with real screens
    placeholders["match_history"] = match_history
    placeholders["match_detail"] = match_detail
    placeholders["performance"] = performance
    placeholders["settings"] = settings
    placeholders["wizard"] = wizard
    placeholders["user_profile"] = user_profile
    placeholders["profile"] = profile
    placeholders["home"] = home
    placeholders["coach"] = coach
    placeholders["steam_config"] = steam_config
    placeholders["faceit_config"] = faceit_config
    placeholders["help"] = help_screen
    placeholders["tactical_viewer"] = tactical_viewer

    # Wire wizard completion: wizard → home
    wizard.setup_completed.connect(lambda: window.switch_screen("home"))

    # Register all screens
    for name, widget in placeholders.items():
        window.register_screen(name, widget)

    # First-run gate: show wizard if setup not completed
    if get_setting("SETUP_COMPLETED", False):
        window.switch_screen("home")
    else:
        window.switch_screen("wizard")

    # Store references for theme switching later
    window._theme_engine = theme

    window.show()

    # Start background CoachState polling (10s interval)
    from Programma_CS2_RENAN.apps.qt_app.core.app_state import get_app_state

    get_app_state().start_polling()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
