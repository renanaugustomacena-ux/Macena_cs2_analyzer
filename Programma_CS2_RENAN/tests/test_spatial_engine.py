import sys


import pytest

from Programma_CS2_RENAN.core.spatial_data import SPATIAL_REGISTRY as MAP_DATA
from Programma_CS2_RENAN.core.spatial_engine import SpatialEngine


def test_dust2_canonical_points():
    """Verify known points on de_dust2."""
    # HLTV/Source Dust2 pos_x: -2476, pos_y: 3239, scale: 4.4

    # 1. The top-left corner of the overview image should be (0, 0)
    norm = SpatialEngine.world_to_normalized(-2476, 3239, "de_dust2")
    assert norm == (0.0, 0.0)

    # 2. A point far in the world (e.g. T-Spawn area)
    # T-Spawn is roughly (390, 930) in normalized pixels for a 1024 image
    # We verify the math:
    world_x = -2476 + (0.39 * 1024 * 4.4)  # ~ -718
    world_y = 3239 - (0.91 * 1024 * 4.4)  # ~ -861

    norm = SpatialEngine.world_to_normalized(world_x, world_y, "de_dust2")
    assert pytest.approx(norm[0], 0.01) == 0.39
    assert pytest.approx(norm[1], 0.01) == 0.91


def test_mirage_alignment():
    """Verify Mirage scale and offset."""
    # pos_x: -3230, pos_y: 1713, scale: 5.0
    norm = SpatialEngine.world_to_normalized(-3230, 1713, "de_mirage")
    assert norm == (0.0, 0.0)

    # Test a point at the center of the image (0.5, 0.5)
    world_x = -3230 + (0.5 * 1024 * 5.0)
    world_y = 1713 - (0.5 * 1024 * 5.0)
    norm = SpatialEngine.world_to_normalized(world_x, world_y, "de_mirage")
    assert norm == (0.5, 0.5)


def test_pixel_mapping():
    """Verify normalized to pixel mapping."""
    # 1080p target: 0.5 * 1920 = 960, 0.5 * 1080 = 540
    px = SpatialEngine.normalized_to_pixel(0.5, 0.5, 1920, 1080)
    assert px == (960.0, 540.0)

    # 4k target: 1.0 * 3840 = 3840, 1.0 * 2160 = 2160
    px = SpatialEngine.normalized_to_pixel(1.0, 1.0, 3840, 2160)
    assert px == (3840.0, 2160.0)


def test_invalid_map():
    """Ensure (0.5, 0.5) is returned for unknown maps as a safe fallback."""
    result = SpatialEngine.world_to_normalized(0, 0, "de_nonexistent")
    assert result == (0.5, 0.5)


def test_world_to_pixel_shortcut():
    """Verify the one-stop shop method."""
    # Dust2 center point to 1024x1024 image
    world_x = -2476 + (0.5 * 1024 * 4.4)
    world_y = 3239 - (0.5 * 1024 * 4.4)

    px = SpatialEngine.world_to_pixel(world_x, world_y, "de_dust2", 1024, 1024)
    assert px == (512, 512)
