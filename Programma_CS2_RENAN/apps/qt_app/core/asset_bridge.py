"""
Asset bridge for Qt — loads map images as QPixmap without Kivy dependencies.

Uses AssetAuthority for path resolution but bypasses Kivy texture creation.
"""

import os
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from Programma_CS2_RENAN.core.config import get_resource_path
from Programma_CS2_RENAN.observability.logger_setup import get_logger

_logger = get_logger("cs2analyzer.qt_assets")

# Map name normalization (same logic as AssetAuthority)
_MAP_ALIASES = {
    "mirage": "de_mirage",
    "dust2": "de_dust2",
    "inferno": "de_inferno",
    "nuke": "de_nuke",
    "overpass": "de_overpass",
    "ancient": "de_ancient",
    "vertigo": "de_vertigo",
    "anubis": "de_anubis",
    "train": "de_train",
    "cache": "de_cache",
}


def _normalize_map_name(name: str) -> str:
    """Normalize map name to canonical form (e.g., 'mirage' → 'de_mirage')."""
    lower = name.lower().strip()
    return _MAP_ALIASES.get(lower, lower)


def _checkered_fallback(size: int = 256) -> QPixmap:
    """Generate a magenta/black checkerboard fallback (same as AssetAuthority)."""
    img = QImage(size, size, QImage.Format_RGB888)
    tile = size // 8
    for y in range(size):
        for x in range(size):
            is_magenta = ((x // tile) + (y // tile)) % 2 == 0
            r, g, b = (255, 0, 255) if is_magenta else (0, 0, 0)
            img.setPixelColor(x, y, QColor(r, g, b))
    return QPixmap.fromImage(img)


_FALLBACK_PIXMAP: Optional[QPixmap] = None


class QtAssetBridge(QObject):
    """Loads map assets as QPixmap. Drop-in replacement for MapManager's Kivy Loader."""

    map_loaded = Signal(str, object)  # (map_name, QPixmap)

    def __init__(self):
        super().__init__()
        self._cache: dict = {}

    def get_map_pixmap(self, map_name: str, theme: str = "regular") -> QPixmap:
        """
        Get a QPixmap for a map. Returns checkered fallback if asset missing.

        Args:
            map_name: Map identifier (e.g., "de_mirage" or "mirage")
            theme: "regular", "dark", or "light"
        """
        canonical = _normalize_map_name(map_name)
        cache_key = f"{canonical}_{theme}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        # Build path (mirrors AssetAuthority logic)
        maps_dir = get_resource_path(os.path.join("PHOTO_GUI", "maps"))

        if theme == "regular":
            filename = f"{canonical}.png"
        else:
            filename = f"{canonical}_{theme}.png"

        filepath = os.path.join(maps_dir, filename)

        if os.path.exists(filepath):
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                self._cache[cache_key] = pixmap
                return pixmap
            _logger.warning("Failed to load map pixmap: %s", filepath)

        # Fallback
        fallback = self._get_fallback()
        self._cache[cache_key] = fallback
        return fallback

    def get_map_path(self, map_name: str, theme: str = "regular") -> str:
        """Return the filesystem path for a map asset (may not exist)."""
        canonical = _normalize_map_name(map_name)
        maps_dir = get_resource_path(os.path.join("PHOTO_GUI", "maps"))
        if theme == "regular":
            return os.path.join(maps_dir, f"{canonical}.png")
        return os.path.join(maps_dir, f"{canonical}_{theme}.png")

    @staticmethod
    def _get_fallback() -> QPixmap:
        global _FALLBACK_PIXMAP
        if _FALLBACK_PIXMAP is None:
            _FALLBACK_PIXMAP = _checkered_fallback()
        return _FALLBACK_PIXMAP

    def clear_cache(self):
        self._cache.clear()


# Singleton
assets = QtAssetBridge()
