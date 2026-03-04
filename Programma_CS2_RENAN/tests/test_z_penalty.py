"""
Unit tests for Z-Penalty vertical awareness functions.

Tests compute_z_penalty() and classify_vertical_level() from spatial_data.py,
plus FeatureExtractor integration (slot 15 of METADATA_DIM-dim vector, currently 25).

Z-cutoff values:
  - Nuke: -495 (upper above, lower below)
  - Vertigo: 11700 (upper above, lower below)
"""

import sys


import pytest

from Programma_CS2_RENAN.core.spatial_data import classify_vertical_level, compute_z_penalty

# ── compute_z_penalty ────────────────────────────────────────────────────────


class TestComputeZPenalty:

    def test_nuke_on_boundary(self):
        assert compute_z_penalty(-495.0, "de_nuke") == 0.0

    def test_nuke_deep_upper(self):
        # z=0 is 495 units above cutoff → 495/500 = 0.99
        result = compute_z_penalty(0.0, "de_nuke")
        assert result == pytest.approx(0.99, abs=0.01)

    def test_nuke_deep_lower(self):
        # z=-1000 is 505 units below cutoff → min(505/500, 1.0) = 1.0
        assert compute_z_penalty(-1000.0, "de_nuke") == 1.0

    def test_nuke_saturation(self):
        # Anything >=500 units away saturates at 1.0
        assert compute_z_penalty(100.0, "de_nuke") == 1.0
        assert compute_z_penalty(-2000.0, "de_nuke") == 1.0

    def test_nuke_transition_zone(self):
        # z=-445 is 50 units above cutoff → 50/500 = 0.1
        result = compute_z_penalty(-445.0, "de_nuke")
        assert result == pytest.approx(0.1, abs=0.01)

    def test_vertigo_on_boundary(self):
        assert compute_z_penalty(11700.0, "de_vertigo") == 0.0

    def test_vertigo_upper(self):
        # z=12200 is 500 units above cutoff → 1.0
        assert compute_z_penalty(12200.0, "de_vertigo") == 1.0

    def test_vertigo_lower(self):
        # z=11200 is 500 units below cutoff → 1.0
        assert compute_z_penalty(11200.0, "de_vertigo") == 1.0

    def test_single_level_map_returns_zero(self):
        assert compute_z_penalty(100.0, "de_mirage") == 0.0
        assert compute_z_penalty(-500.0, "de_dust2") == 0.0
        assert compute_z_penalty(0.0, "de_inferno") == 0.0

    def test_unknown_map_returns_zero(self):
        assert compute_z_penalty(0.0, "de_nonexistent") == 0.0

    def test_penalty_monotonically_increases(self):
        # Closer to boundary → lower penalty
        p_close = compute_z_penalty(-400.0, "de_nuke")  # 95 units away
        p_mid = compute_z_penalty(-200.0, "de_nuke")  # 295 units away
        p_far = compute_z_penalty(0.0, "de_nuke")  # 495 units away
        assert p_close < p_mid < p_far


# ── classify_vertical_level ──────────────────────────────────────────────────


class TestClassifyVerticalLevel:

    def test_nuke_upper(self):
        assert classify_vertical_level(0.0, "de_nuke") == "upper"

    def test_nuke_lower(self):
        assert classify_vertical_level(-1000.0, "de_nuke") == "lower"

    def test_nuke_transition(self):
        # z=-470 is 25 units above cutoff (-495), within default band of ±50
        assert classify_vertical_level(-470.0, "de_nuke") == "transition"

    def test_nuke_boundary_edge_within(self):
        # z=-445 is exactly 50 units above cutoff → within band (inclusive)
        assert classify_vertical_level(-445.0, "de_nuke") == "transition"

    def test_nuke_just_outside_band(self):
        # z=-444 is 51 units above cutoff → outside band
        assert classify_vertical_level(-444.0, "de_nuke") == "upper"

    def test_nuke_lower_boundary_edge(self):
        # z=-545 is exactly 50 units below cutoff → within band
        assert classify_vertical_level(-545.0, "de_nuke") == "transition"

    def test_vertigo_upper(self):
        assert classify_vertical_level(12000.0, "de_vertigo") == "upper"

    def test_vertigo_lower(self):
        assert classify_vertical_level(11000.0, "de_vertigo") == "lower"

    def test_vertigo_transition(self):
        assert classify_vertical_level(11700.0, "de_vertigo") == "transition"

    def test_single_level_map_returns_default(self):
        assert classify_vertical_level(100.0, "de_mirage") == "default"
        assert classify_vertical_level(0.0, "de_dust2") == "default"

    def test_unknown_map_returns_default(self):
        assert classify_vertical_level(0.0, "de_nonexistent") == "default"

    def test_custom_transition_band(self):
        # With band=100, z=-400 (95 units above cutoff) should be "transition"
        assert classify_vertical_level(-400.0, "de_nuke", transition_band=100.0) == "transition"
        # With band=10, z=-470 (25 units above cutoff) should be "upper" (outside narrow band)
        assert classify_vertical_level(-470.0, "de_nuke", transition_band=10.0) == "upper"


# ── FeatureExtractor integration ─────────────────────────────────────────────


class TestFeatureExtractorZPenalty:

    def test_nuke_slot15_nonzero(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
            METADATA_DIM,
            FeatureExtractor,
        )

        tick = {"health": 100, "armor": 100, "z": 0.0}
        vec = FeatureExtractor.extract(tick, map_name="de_nuke")
        assert len(vec) == METADATA_DIM
        assert vec[15] > 0.0  # Deep in upper level

    def test_mirage_slot15_zero(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
            FeatureExtractor,
        )

        tick = {"health": 100, "armor": 100, "z": 500.0}
        vec = FeatureExtractor.extract(tick, map_name="de_mirage")
        assert vec[15] == 0.0

    def test_no_map_slot15_zero(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
            FeatureExtractor,
        )

        tick = {"health": 100, "armor": 100, "z": 500.0}
        vec = FeatureExtractor.extract(tick, map_name=None)
        assert vec[15] == 0.0
