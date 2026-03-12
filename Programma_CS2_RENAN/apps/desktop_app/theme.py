"""Shared UI theme constants for the desktop app."""

# Rating color coding
COLOR_GREEN = (0.30, 0.69, 0.31, 1)   # #4CAF50
COLOR_YELLOW = (1.0, 0.60, 0.0, 1)    # #FF9800
COLOR_RED = (0.96, 0.26, 0.21, 1)     # #F44336
COLOR_CARD_BG = (0.12, 0.12, 0.14, 1)

# Standard HLTV rating thresholds
RATING_GOOD = 1.10
RATING_BAD = 0.90


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
