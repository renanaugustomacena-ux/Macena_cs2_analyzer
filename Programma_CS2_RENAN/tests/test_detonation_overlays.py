"""
Phase 7 — Detonation Radius Overlays Tests (Task 2.24.1)

Validates:
- Grenade radius constants are correct CS2 game values
- TacticalMap has show_detonation_overlays toggle
- Overlay colors are defined for all grenade types
- _draw_detonation_overlay method exists
"""

import sys


import pytest

from Programma_CS2_RENAN.core.demo_frame import NadeType


class TestGrenadeConstants:
    """Verify CS2 grenade radius constants and overlay colors from production."""

    @pytest.fixture(autouse=True)
    def _load_tactical_map(self):
        """Try importing TacticalMap; skip if Kivy unavailable."""
        try:
            from Programma_CS2_RENAN.apps.desktop_app.tactical_map import TacticalMap

            self.radii = TacticalMap.GRENADE_RADII
            self.colors = TacticalMap.GRENADE_OVERLAY_COLORS
        except Exception:
            pytest.skip("Kivy not available — cannot import TacticalMap")

    def test_all_nade_types_have_radii(self):
        """Every NadeType should have a defined radius in production constants."""
        expected_types = [NadeType.HE, NadeType.MOLOTOV, NadeType.SMOKE, NadeType.FLASH]
        for nt in expected_types:
            assert nt in self.radii, f"{nt} missing from GRENADE_RADII"

    def test_radius_values_match_cs2_game_data(self):
        """Radius values must match known CS2 game constants."""
        assert self.radii[NadeType.HE] == 350
        assert self.radii[NadeType.MOLOTOV] == 180
        assert self.radii[NadeType.SMOKE] == 144
        assert self.radii[NadeType.FLASH] == 1000

    def test_radius_values_are_positive(self):
        """All radius values must be positive."""
        for nade_type, radius in self.radii.items():
            assert radius > 0, f"{nade_type} has non-positive radius: {radius}"

    def test_overlay_colors_defined_for_all_types(self):
        """Every NadeType with a radius must have an overlay color."""
        for nade_type in self.radii:
            assert nade_type in self.colors, f"{nade_type} missing from GRENADE_OVERLAY_COLORS"

    def test_overlay_colors_are_rgb_tuples(self):
        """Overlay colors must be 3-element RGB tuples in [0, 1]."""
        for nade_type, color in self.colors.items():
            assert len(color) == 3, f"{nade_type} color has {len(color)} components"
            for i, c in enumerate(color):
                assert 0.0 <= c <= 1.0, f"{nade_type} color[{i}] = {c} out of [0,1]"


class TestTacticalMapOverlayProperty:
    """Verify the show_detonation_overlays property exists in the source."""

    def test_property_defined_in_source(self):
        """TacticalMap source must define show_detonation_overlays."""
        import os

        source_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "apps",
            "desktop_app",
            "tactical_map.py",
        )
        with open(source_path, "r", encoding="utf-8") as f:
            source = f.read()

        assert "show_detonation_overlays" in source
        assert "BooleanProperty" in source
        assert "GRENADE_RADII" in source
        assert "GRENADE_OVERLAY_COLORS" in source

    def test_draw_detonation_overlay_method_exists(self):
        """_draw_detonation_overlay must be defined in tactical_map.py."""
        import os

        source_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "apps",
            "desktop_app",
            "tactical_map.py",
        )
        with open(source_path, "r", encoding="utf-8") as f:
            source = f.read()

        assert "def _draw_detonation_overlay" in source

    def test_overlay_integrated_in_draw_nade(self):
        """_draw_detonation_overlay must be called from _draw_nade."""
        import os

        source_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "apps",
            "desktop_app",
            "tactical_map.py",
        )
        with open(source_path, "r", encoding="utf-8") as f:
            source = f.read()

        # Find the _draw_nade method and verify it calls _draw_detonation_overlay
        draw_nade_section = source.split("def _draw_nade")[1].split("def _draw_detonation_overlay")[
            0
        ]
        assert "_draw_detonation_overlay" in draw_nade_section
