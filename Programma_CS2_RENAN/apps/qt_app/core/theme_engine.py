"""
Theme engine for Qt — loads QSS stylesheets and manages the CS2/CSGO/CS1.6 palette.

Reuses the palette data and rating functions from the existing theme.py (pure data,
no Kivy imports needed for the constants themselves).
"""

import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# ── Palette data (mirrored from desktop_app/theme.py to avoid Kivy import chain) ──

COLOR_GREEN = (0.30, 0.69, 0.31, 1)
COLOR_YELLOW = (1.0, 0.60, 0.0, 1)
COLOR_RED = (0.96, 0.26, 0.21, 1)
COLOR_CARD_BG = (0.12, 0.12, 0.14, 1)

RATING_GOOD = 1.10
RATING_BAD = 0.90

PALETTES = {
    "CS2": {
        "surface": [0.08, 0.08, 0.12, 0.85],
        "surface_alt": [0.06, 0.06, 0.18, 0.9],
        "accent_primary": [0.85, 0.4, 0.0, 1],
        "chart_bg": "#1a1a1a",
    },
    "CSGO": {
        "surface": [0.10, 0.11, 0.13, 0.85],
        "surface_alt": [0.08, 0.10, 0.14, 0.9],
        "accent_primary": [0.38, 0.49, 0.55, 1],
        "chart_bg": "#1c1e20",
    },
    "CS1.6": {
        "surface": [0.07, 0.10, 0.07, 0.85],
        "surface_alt": [0.05, 0.14, 0.08, 0.9],
        "accent_primary": [0.30, 0.69, 0.31, 1],
        "chart_bg": "#181e18",
    },
}

_THEMES_DIR = Path(__file__).parent.parent / "themes"
_ASSETS_DIR = Path(__file__).parent.parent.parent.parent / "PHOTO_GUI"

_THEME_WALLPAPER_FOLDER = {
    "CS2": "cs2theme",
    "CSGO": "csgotheme",
    "CS1.6": "cs16theme",
}

_FONT_FILES = {
    "Roboto": "Roboto-Regular.ttf",
    "JetBrains Mono": "JetBrainsMono-Regular.ttf",
    "New Hope": "NewHope.ttf",
    "CS Regular": "cs_regular.ttf",
    "YUPIX": "YUPIX.otf",
}


def rgba_to_qcolor(rgba: List[float]) -> QColor:
    """Convert [r, g, b, a] (0-1 floats) to QColor."""
    return QColor.fromRgbF(
        rgba[0], rgba[1], rgba[2], rgba[3] if len(rgba) > 3 else 1.0
    )


def rating_color(rating: float) -> QColor:
    """HLTV rating → green/yellow/red QColor."""
    if rating > RATING_GOOD:
        return rgba_to_qcolor(list(COLOR_GREEN))
    if rating < RATING_BAD:
        return rgba_to_qcolor(list(COLOR_RED))
    return rgba_to_qcolor(list(COLOR_YELLOW))


def rating_label(rating: float) -> str:
    """WCAG 1.4.1 color-blind accessible text label for ratings."""
    if rating >= 1.20:
        return "Excellent"
    if rating > RATING_GOOD:
        return "Good"
    if rating >= RATING_BAD:
        return "Average"
    return "Below Avg"


class ThemeEngine:
    """Loads and applies QSS themes + QPalette colors + fonts + wallpapers."""

    def __init__(self):
        self._active: str = "CS2"
        self._fonts_registered = False
        self._wallpaper_path: str = ""
        self._font_family: str = "Roboto"
        self._font_size: int = 13

    @property
    def active_theme(self) -> str:
        return self._active

    @property
    def chart_bg(self) -> str:
        return PALETTES.get(self._active, PALETTES["CS2"])["chart_bg"]

    def get_color(self, slot: str) -> QColor:
        """Return QColor for a palette slot (surface, surface_alt, accent_primary)."""
        palette = PALETTES.get(self._active, PALETTES["CS2"])
        rgba = palette.get(slot, [0.08, 0.08, 0.12, 0.85])
        return rgba_to_qcolor(rgba)

    def apply_theme(self, name: str, app: Optional[QApplication] = None):
        """Switch to a named theme. Loads QSS and sets QPalette."""
        if name not in PALETTES:
            return
        self._active = name
        target = app or QApplication.instance()
        if target is None:
            return

        # Load QSS stylesheet with font injection
        qss_file = _THEMES_DIR / f"{name.lower().replace('.', '')}.qss"
        if qss_file.exists():
            qss = qss_file.read_text(encoding="utf-8")
            # Append font rule AFTER QSS so it wins the cascade (same specificity, last wins)
            font_rule = (
                f'\nQWidget {{ font-family: "{self._font_family}", "Segoe UI", "Arial", sans-serif; '
                f'font-size: {self._font_size}px; }}\n'
            )
            target.setStyleSheet(qss + font_rule)

        # Set QPalette for widgets that don't use QSS
        palette_data = PALETTES[name]
        p = QPalette()

        surface = rgba_to_qcolor(palette_data["surface"])
        surface_alt = rgba_to_qcolor(palette_data["surface_alt"])
        accent = rgba_to_qcolor(palette_data["accent_primary"])
        text_color = QColor(220, 220, 220)
        dim_text = QColor(160, 160, 160)

        p.setColor(QPalette.Window, surface)
        p.setColor(QPalette.WindowText, text_color)
        p.setColor(QPalette.Base, surface_alt)
        p.setColor(QPalette.AlternateBase, surface)
        p.setColor(QPalette.Text, text_color)
        p.setColor(QPalette.BrightText, QColor(255, 255, 255))
        p.setColor(QPalette.Button, surface)
        p.setColor(QPalette.ButtonText, text_color)
        p.setColor(QPalette.Highlight, accent)
        p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        p.setColor(QPalette.ToolTipBase, surface_alt)
        p.setColor(QPalette.ToolTipText, text_color)
        p.setColor(QPalette.PlaceholderText, dim_text)
        p.setColor(QPalette.Link, accent)

        target.setPalette(p)

        # Update wallpaper for the new theme
        self._update_wallpaper(name)

    # ── Font Management ──

    def set_font(self, family: str, size_pt: int):
        """Change the app font and re-apply stylesheet to propagate everywhere."""
        self._font_family = family
        self._font_size = size_pt
        self.apply_theme(self._active)

    def register_fonts(self):
        """Register all custom font files with Qt. Call once at startup."""
        if self._fonts_registered:
            return
        for name, filename in _FONT_FILES.items():
            path = _ASSETS_DIR / filename
            if path.exists():
                font_id = QFontDatabase.addApplicationFont(str(path))
                if font_id < 0:
                    print(f"Warning: Failed to load font {name} from {path}")
            else:
                print(f"Warning: Font file not found: {path}")
        self._fonts_registered = True

    # ── Wallpaper ──

    @property
    def wallpaper_path(self) -> str:
        """Current wallpaper image path (empty string if none)."""
        return self._wallpaper_path

    def _update_wallpaper(self, theme_name: str):
        """Set wallpaper to the first image in the theme's folder."""
        folder = _THEME_WALLPAPER_FOLDER.get(theme_name, "cs2theme")
        theme_dir = _ASSETS_DIR / folder
        if not theme_dir.is_dir():
            self._wallpaper_path = ""
            return

        # Pick the first vertical wallpaper, or first image found
        images = sorted(
            f for f in os.listdir(theme_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        )
        # Prefer vertical wallpapers (they match the app's portrait-ish layout better)
        vertical = [f for f in images if "vertical" in f.lower()]
        pick = vertical[0] if vertical else (images[0] if images else "")
        if pick:
            self._wallpaper_path = str(theme_dir / pick)
        else:
            self._wallpaper_path = ""

    def get_available_wallpapers(self, theme_name: str | None = None) -> list[str]:
        """Return list of wallpaper filenames for a theme."""
        name = theme_name or self._active
        folder = _THEME_WALLPAPER_FOLDER.get(name, "cs2theme")
        theme_dir = _ASSETS_DIR / folder
        if not theme_dir.is_dir():
            return []
        return sorted(
            f for f in os.listdir(theme_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        )

    def set_wallpaper(self, filename: str):
        """Set a specific wallpaper by filename."""
        folder = _THEME_WALLPAPER_FOLDER.get(self._active, "cs2theme")
        path = _ASSETS_DIR / folder / filename
        if path.exists():
            self._wallpaper_path = str(path)
