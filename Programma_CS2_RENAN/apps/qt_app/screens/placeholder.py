"""
Placeholder screens — temporary widgets for all 13 screens during Phase 1.

Each will be replaced with its real implementation in Phases 2-4.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderScreen(QWidget):
    """Generic placeholder with centered title. Replace in later phases."""

    def __init__(self, title: str, description: str = ""):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        lbl = QLabel(title)
        lbl.setObjectName("placeholder_label")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)

        if description:
            desc = QLabel(description)
            desc.setObjectName("section_subtitle")
            desc.setAlignment(Qt.AlignCenter)
            layout.addWidget(desc)

    def on_enter(self):
        """Called when this screen becomes visible. Override in real screens."""
        pass


def create_placeholder_screens() -> dict:
    """Create all 13 placeholder screens. Returns {name: widget}."""
    return {
        "home": PlaceholderScreen(
            "Dashboard", "Training status, coaching hub, connectivity"
        ),
        "coach": PlaceholderScreen(
            "AI Coach", "Coaching insights and interactive chat"
        ),
        "match_history": PlaceholderScreen(
            "Match History", "Your analyzed matches with HLTV ratings"
        ),
        "match_detail": PlaceholderScreen(
            "Match Detail", "Per-match stats, rounds, economy, insights"
        ),
        "performance": PlaceholderScreen(
            "Your Stats", "Rating trends, skill radar, utility analysis"
        ),
        "tactical_viewer": PlaceholderScreen(
            "Tactical Analyzer", "2D map visualization with playback"
        ),
        "settings": PlaceholderScreen(
            "Settings", "Theme, paths, language, ingestion config"
        ),
        "wizard": PlaceholderScreen(
            "Setup Wizard", "First-time configuration"
        ),
        "profile": PlaceholderScreen(
            "Player Profile", "View player stats and role analysis"
        ),
        "user_profile": PlaceholderScreen(
            "Edit Profile", "Avatar, bio, system specs"
        ),
        "steam_config": PlaceholderScreen(
            "Steam Integration", "SteamID64 and API key"
        ),
        "faceit_config": PlaceholderScreen(
            "FaceIT Integration", "FaceIT API key"
        ),
        "help": PlaceholderScreen(
            "Help", "Searchable documentation and FAQ"
        ),
    }
