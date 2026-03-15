"""Shared UI theme constants and palette registry for the desktop app."""

# Rating color coding
COLOR_GREEN = (0.30, 0.69, 0.31, 1)   # #4CAF50
COLOR_YELLOW = (1.0, 0.60, 0.0, 1)    # #FF9800
COLOR_RED = (0.96, 0.26, 0.21, 1)     # #F44336
COLOR_CARD_BG = (0.12, 0.12, 0.14, 1)

# Standard HLTV rating thresholds
RATING_GOOD = 1.10
RATING_BAD = 0.90

# Chart background (single source of truth for all matplotlib widgets)
CHART_BG = "#1a1a1a"

# --- Palette Registry ---
# Each theme defines surface colors used across layout.kv and widgets.
_PALETTES = {
    "CS2": {
        "surface": [0.08, 0.08, 0.12, 0.85],
        "surface_alt": [0.06, 0.06, 0.18, 0.9],
        "accent_primary": [0.85, 0.4, 0.0, 1],      # Orange
        "chart_bg": "#1a1a1a",
    },
    "CSGO": {
        "surface": [0.10, 0.11, 0.13, 0.85],
        "surface_alt": [0.08, 0.10, 0.14, 0.9],
        "accent_primary": [0.38, 0.49, 0.55, 1],     # BlueGray
        "chart_bg": "#1c1e20",
    },
    "CS1.6": {
        "surface": [0.07, 0.10, 0.07, 0.85],
        "surface_alt": [0.05, 0.14, 0.08, 0.9],
        "accent_primary": [0.30, 0.69, 0.31, 1],     # Green
        "chart_bg": "#181e18",
    },
}

_active_theme = "CS2"


def set_active_theme(name: str) -> None:
    """Set the active palette by name."""
    global _active_theme, CHART_BG
    if name in _PALETTES:
        _active_theme = name
        CHART_BG = _PALETTES[name]["chart_bg"]


def get_color(slot: str) -> list:
    """Return a color list for the given slot from the active palette."""
    palette = _PALETTES.get(_active_theme, _PALETTES["CS2"])
    return list(palette.get(slot, [0.08, 0.08, 0.12, 0.85]))


def rating_color(rating: float) -> tuple:
    """Return color tuple based on HLTV rating thresholds."""
    if rating > RATING_GOOD:
        return COLOR_GREEN
    if rating < RATING_BAD:
        return COLOR_RED
    return COLOR_YELLOW


def rating_label(rating: float) -> str:
    """P4-07: Text label alongside color for WCAG 1.4.1 color-blind accessibility."""
    if rating >= 1.20:
        return "Excellent"
    if rating > RATING_GOOD:
        return "Good"
    if rating >= RATING_BAD:
        return "Average"
    return "Below Avg"
