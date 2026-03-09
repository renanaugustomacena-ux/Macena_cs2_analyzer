"""
Spatial Data Module for Macena CS2 Analyzer.

Provides map metadata for coordinate transformations between world space
and radar/UI space. Includes Z-axis verticality support for multi-level
maps like Nuke and Vertigo (TASK 4.3).
"""

import json
import os
import threading
from dataclasses import dataclass
from typing import Dict, Optional

from Programma_CS2_RENAN.observability.logger_setup import get_logger

_logger = get_logger("cs2analyzer.spatial_data")

# Z-axis distance penalties for multi-level maps (Nuke, Vertigo).
# Single source of truth — also imported by connect_map_context.py (R4-11-01).
Z_LEVEL_THRESHOLD = 200    # Relative Z units separating level floors
Z_PENALTY_FACTOR = 2.0     # Multiplier for cross-level distance


@dataclass(frozen=True)
class MapMetadata:
    """
    Immutable definition of a CS2 map's spatial properties.

    Attributes:
        pos_x (float): The X-coordinate of the top-left corner of the radar image in world space.
        pos_y (float): The Y-coordinate of the top-left corner of the radar image in world space.
        scale (float): The scale factor (world units per pixel) of the radar image.
        z_cutoff (Optional[float]): Z-axis threshold for level selection (multi-level maps).
                                    If player Z is above this, use "upper" level; below uses "lower".
        level (str): Level identifier - "default", "upper", or "lower".
    """

    pos_x: float
    pos_y: float
    scale: float
    z_cutoff: Optional[float] = None
    level: str = "default"

    def world_to_radar(self, x: float, y: float, radar_width: float = 1024) -> tuple[float, float]:
        """
        Converts Source 2 World Coordinates (x, y) to Normalized Radar Coordinates (0.0 - 1.0).
        """
        pixel_x = (x - self.pos_x) / self.scale
        pixel_y = (self.pos_y - y) / self.scale

        norm_x = pixel_x / radar_width
        norm_y = pixel_y / radar_width

        return norm_x, norm_y

    def radar_to_world(
        self, norm_x: float, norm_y: float, radar_width: float = 1024
    ) -> tuple[float, float]:
        """
        Converts Normalized Radar Coordinates (0.0 - 1.0) back to Source 2 World Coordinates.
        """
        pixel_x = norm_x * radar_width
        pixel_y = norm_y * radar_width

        x = (pixel_x * self.scale) + self.pos_x
        y = self.pos_y - (pixel_y * self.scale)

        return x, y

    @property
    def is_multi_level(self) -> bool:
        """Returns True if this is a multi-level map with Z cutoff defined."""
        return self.z_cutoff is not None


# Hardcoded fallbacks (used if JSON config is missing/corrupt)
# Source: Valve CS2 map radar .txt files (pos_x, pos_y, scale from overview files)
# Multi-level maps have separate entries for upper/lower with z_cutoff values
_FALLBACK_REGISTRY: Dict[str, MapMetadata] = {
    # Standard maps (single level)
    "de_mirage": MapMetadata(pos_x=-3230, pos_y=1713, scale=5.0),
    "de_inferno": MapMetadata(pos_x=-2087, pos_y=3870, scale=4.9),
    "de_dust2": MapMetadata(pos_x=-2476, pos_y=3239, scale=4.4),
    "de_overpass": MapMetadata(pos_x=-4831, pos_y=1781, scale=5.2),
    "de_ancient": MapMetadata(pos_x=-2953, pos_y=2164, scale=5.0),
    "de_anubis": MapMetadata(pos_x=-2796, pos_y=3328, scale=5.22),
    "de_train": MapMetadata(pos_x=-2477, pos_y=2392, scale=4.7),
    # Multi-level maps: Nuke (z_cutoff = -495)
    # Above z_cutoff: A-Site, Lobby, Outside, Ramp (upper level)
    # Below z_cutoff: B-Site, Secret, Vent, Tunnels (lower level)
    "de_nuke": MapMetadata(pos_x=-3453, pos_y=2887, scale=7.0, z_cutoff=-495, level="upper"),
    "de_nuke_lower": MapMetadata(pos_x=-3453, pos_y=2887, scale=7.0, level="lower"),
    # Multi-level maps: Vertigo (z_cutoff = 11700)
    # Above z_cutoff: A-Site, B-Site, CT Spawn (upper level)
    # Below z_cutoff: Lower construction, scaffolding (lower level)
    "de_vertigo": MapMetadata(pos_x=-3168, pos_y=1762, scale=4.0, z_cutoff=11700, level="upper"),
    "de_vertigo_lower": MapMetadata(pos_x=-3168, pos_y=1762, scale=4.0, level="lower"),
}

_FALLBACK_LANDMARKS: Dict[str, Dict[str, tuple[float, float]]] = {
    "de_mirage": {
        "T-Spawn": (-3200, -650),
        "CT-Spawn": (1000, -2350),
        "A-Site": (1030, -350),
        "B-Site": (-1900, -300),
        "Mid-Window": (-150, -750),
    },
    "de_dust2": {
        "T-Spawn": (-1500, -1000),
        "CT-Spawn": (50, 2500),
        "A-Site": (1100, 2400),
        "B-Site": (-1500, 2500),
        "Mid-Doors": (0, 0),
    },
    "de_nuke": {
        "T-Spawn": (-955, -960),
        "CT-Spawn": (800, 1100),
        "A-Site": (640, 960),
        "B-Site": (470, -215),  # Lower level
        "Outside": (-1560, 1760),
    },
}

_FALLBACK_COMPETITIVE_MAPS = [
    "de_nuke",
    "de_inferno",
    "de_mirage",
    "de_dust2",
    "de_ancient",
    "de_overpass",
    "de_vertigo",
    "de_anubis",
    "de_train",
]

_loader_lock = threading.Lock()


class SpatialConfigLoader:
    """
    Singleton loader for map spatial configuration.
    Loads from JSON file with fallback to hardcoded defaults.
    """

    _instance: Optional["SpatialConfigLoader"] = None
    _loaded: bool = False

    def __new__(cls):
        if cls._instance is None:
            with _loader_lock:
                # Double-checked locking: re-test inside the lock in case another
                # thread already created the instance while we were waiting.
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # SD-01: Protect _loaded flag with lock to prevent duplicate _load_config()
        # from concurrent __init__ calls racing on the unlocked check.
        with _loader_lock:
            if not SpatialConfigLoader._loaded:
                self._load_config()
                SpatialConfigLoader._loaded = True

    def _load_config(self):
        """Load configuration from JSON file with fallback."""
        self.registry: Dict[str, MapMetadata] = {}
        self.landmarks: Dict[str, Dict[str, tuple[float, float]]] = {}
        self.competitive_maps: list[str] = []

        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "map_config.json"
        )

        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                # Parse maps
                for map_name, map_data in config.get("maps", {}).items():
                    self.registry[map_name] = MapMetadata(
                        pos_x=map_data["pos_x"],
                        pos_y=map_data["pos_y"],
                        scale=map_data["scale"],
                        z_cutoff=map_data.get("z_cutoff"),
                        level=map_data.get("level", "default"),
                    )

                    # Parse landmarks
                    if "landmarks" in map_data:
                        self.landmarks[map_name] = {
                            name: tuple(coords) for name, coords in map_data["landmarks"].items()
                        }

                self.competitive_maps = config.get("competitive_pool", _FALLBACK_COMPETITIVE_MAPS)
                return
        except Exception as e:
            _logger.warning(
                "Failed to load map config from %s: %s — using fallback registry",
                config_path,
                e,
            )

        # Use fallbacks
        self.registry = _FALLBACK_REGISTRY.copy()
        self.landmarks = _FALLBACK_LANDMARKS.copy()
        self.competitive_maps = _FALLBACK_COMPETITIVE_MAPS.copy()

    def reload(self):
        """Force reload of configuration."""
        SpatialConfigLoader._loaded = False
        self._load_config()
        SpatialConfigLoader._loaded = True


# Module-level accessor functions
def _get_loader() -> SpatialConfigLoader:
    return SpatialConfigLoader()


# Public API - maintains backward compatibility
# Symbols are handled by __getattr__ below for lazy loading
# SPATIAL_REGISTRY: Dict[str, MapMetadata]
# LANDMARKS: Dict[str, Dict[str, tuple[float, float]]]
# COMPETITIVE_MAPS: list[str]


# For backward compatibility, expose as module-level dicts
# These will be populated on first import
def __getattr__(name: str):
    """Lazy loading of module-level constants."""
    loader = _get_loader()
    if name == "SPATIAL_REGISTRY":
        return loader.registry
    elif name == "LANDMARKS":
        return loader.landmarks
    elif name == "COMPETITIVE_MAPS":
        return loader.competitive_maps
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_map_metadata(map_name: str) -> MapMetadata | None:
    """Safely retrieve map metadata, handling variations in naming."""
    if not map_name:
        return None

    loader = _get_loader()

    # 1. Clean name: lowercase, remove extensions and prefixes
    clean_name = (
        map_name.lower().replace(".dem", "").replace(".vpk", "").replace("maps/", "").strip()
    )

    # 2. Try exact match
    if clean_name in loader.registry:
        return loader.registry[clean_name]

    # 3. Try partial match (e.g. "train" -> "de_train")
    # Note: Short inputs (< 4 chars) are skipped for the reverse match
    # (clean_name in key) to avoid false positives like "over" matching "de_overpass".
    for key, meta in loader.registry.items():
        # Skip lower-level variants for default lookup
        if "_lower" in key:
            continue
        if key in clean_name or (len(clean_name) >= 4 and clean_name in key):
            return meta

    return None


def get_map_metadata_for_z(map_name: str, z: float) -> MapMetadata | None:
    """
    Retrieve map metadata with automatic level selection based on Z coordinate.

    For multi-level maps (Nuke, Vertigo), this selects the correct level
    based on whether the player is above or below the z_cutoff threshold.

    Args:
        map_name: Map identifier (e.g., "de_nuke")
        z: Player's Z-axis coordinate (height)

    Returns:
        MapMetadata for the appropriate level, or None if map unknown.
    """
    if not map_name:
        return None

    loader = _get_loader()
    clean_name = (
        map_name.lower().replace(".dem", "").replace(".vpk", "").replace("maps/", "").strip()
    )

    # Remove any existing level suffix for base lookup
    base_name = clean_name.replace("_lower", "").replace("_upper", "")

    # Get the base/upper metadata first
    base_meta = None
    if base_name in loader.registry:
        base_meta = loader.registry[base_name]
    else:
        # Try partial match
        for key, meta in loader.registry.items():
            if "_lower" in key:
                continue
            if key in base_name or base_name in key:
                base_meta = meta
                base_name = key
                break

    if base_meta is None:
        return None

    # If not a multi-level map or no z_cutoff, return the base metadata
    if base_meta.z_cutoff is None:
        return base_meta

    # Check Z position against cutoff
    lower_key = f"{base_name}_lower"
    if z < base_meta.z_cutoff and lower_key in loader.registry:
        return loader.registry[lower_key]

    return base_meta


def is_multi_level_map(map_name: str) -> bool:
    """Check if a map has multiple Z levels requiring level selection.

    Consults the dynamic map registry (JSON config + fallback) instead of a
    hardcoded set, so newly added multi-level maps are detected automatically.
    """
    meta = get_map_metadata(map_name)
    return meta is not None and meta.z_cutoff is not None


def get_landmarks(map_name: str) -> Dict[str, tuple[float, float]]:
    """Get landmarks for a specific map."""
    loader = _get_loader()
    clean_name = (
        map_name.lower().replace(".dem", "").replace(".vpk", "").replace("maps/", "").strip()
    )
    return loader.landmarks.get(clean_name, {})


def reload_spatial_config():
    """Force reload of spatial configuration from JSON."""
    _get_loader().reload()


def classify_vertical_level(z_position: float, map_name: str, transition_band: float = 50.0) -> str:
    """
    Classify the vertical level of a position on multi-level maps.

    Args:
        z_position: Z-coordinate in game units.
        map_name: Map identifier (e.g., "de_nuke").
        transition_band: Vertical buffer around z_cutoff to define "transition" zone.

    Returns:
        "upper", "lower", "transition", or "default" (for single-level maps).
    """
    meta = get_map_metadata(map_name)
    if not meta or meta.z_cutoff is None:
        return "default"

    if abs(z_position - meta.z_cutoff) <= transition_band:
        return "transition"

    return "upper" if z_position > meta.z_cutoff else "lower"


def compute_z_penalty(z_position: float, map_name: str) -> float:
    """
    Compute a normalized penalty [0.0, 1.0] based on vertical distance from the level boundary.
    Used for neural network supervision to distinguish verticality.

    Args:
        z_position: Z-coordinate in game units.
        map_name: Map identifier.

    Returns:
        0.0 for single-level maps.
        normalized distance for multi-level maps.
    """
    meta = get_map_metadata(map_name)
    if not meta or meta.z_cutoff is None:
        return 0.0

    # Distance from the vertical cutoff plane, normalized to [0, 1].
    # 0.0 = exactly on the boundary; 1.0 = ≥500 units away (deep into a level).
    # Saturation at 500 units covers typical CS2 vertical play space.
    dist = abs(z_position - meta.z_cutoff)
    normalized = min(dist / 500.0, 1.0)
    return normalized
