"""
Tests for MapManager and AssetAuthority.

Verifies the unified asset management system correctly resolves
map images, handles fallbacks, and provides spatial metadata.
"""

import os
import sys


import pytest

from Programma_CS2_RENAN.core.asset_manager import AssetAuthority, SmartAsset
from Programma_CS2_RENAN.core.map_manager import MapManager


def test_map_path_resolution():
    """Verify that a valid map resolves to a real file path."""
    # We know de_dust2.png exists
    path = MapManager.get_map_path("de_dust2")
    assert os.path.isabs(path)
    assert path.endswith("de_dust2.png")
    assert os.path.exists(path)


def test_smart_asset_creation():
    """Verify SmartAsset is created with correct attributes."""
    asset = AssetAuthority.get_map_asset("de_mirage")
    assert isinstance(asset, SmartAsset)
    assert asset.theme == "regular"
    assert asset.is_fallback == False
    assert asset.exists == True
    assert asset.path.endswith("de_mirage.png")


def test_fallback_behavior():
    """Verify that an unknown map returns a checkered fallback SmartAsset."""
    asset = AssetAuthority.get_map_asset("de_mars_mission_99")

    # Should be marked as fallback
    assert asset.is_fallback == True
    assert asset.theme == "fallback"
    assert asset.exists == False  # Actual file doesn't exist

    # Path should still be set for logging purposes
    assert "FALLBACK_CHECKERED" in asset.path


def test_metadata_passthrough():
    """Ensure manager can still provide spatial metadata."""
    meta = MapManager.get_map_metadata("de_dust2")
    assert meta is not None
    assert meta.scale == 4.4


def test_asset_registry_completeness():
    """Verify that all core competitive maps have assets available."""
    core_maps = [
        "de_dust2",
        "de_mirage",
        "de_inferno",
        "de_nuke",
        "de_overpass",
        "de_ancient",
        "de_anubis",
        "de_vertigo",
    ]
    for m in core_maps:
        asset = AssetAuthority.get_map_asset(m)
        assert not asset.is_fallback, f"Missing asset for {m}"
        assert asset.path.endswith(f"{m}.png"), f"Wrong filename for {m}"
        assert os.path.exists(asset.path), f"File missing for {m}"


def test_normalized_map_names():
    """Verify various input formats normalize to the same asset."""
    # All these should resolve to de_mirage
    inputs = ["de_mirage", "mirage", "de_mirage.dem", "maps/de_mirage"]
    paths = [AssetAuthority.get_map_asset(name).path for name in inputs]

    # All should resolve to the same file
    assert len(set(paths)) == 1, "Different inputs should normalize to same asset"


def test_theme_variants():
    """Verify theme variants are properly handled."""
    regular = AssetAuthority.get_map_asset("de_mirage", theme="regular")
    assert not regular.is_fallback
    assert regular.theme == "regular"

    dark = AssetAuthority.get_map_asset("de_mirage", theme="dark")
    assert not dark.is_fallback
    assert dark.theme == "dark", f"Expected dark theme, got '{dark.theme}'"
    assert dark.path != regular.path, "Dark and regular variants should resolve to different files"


def test_backward_compatible_map_asset_manager():
    """Verify deprecated MapAssetManager still works."""
    from Programma_CS2_RENAN.core.asset_manager import MapAssetManager

    path = MapAssetManager.get_map_source("de_dust2")
    assert os.path.exists(path)
    assert path.endswith("de_dust2.png")
