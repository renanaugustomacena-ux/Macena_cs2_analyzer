"""
Tests for spatial distance calculations, fuzzy nickname matching,
outlier trimming, and maturity tier classification.
"""

import sys


import numpy as np
import pandas as pd
import pytest

from Programma_CS2_RENAN.backend.nn.coach_manager import DEMO_TIERS, TIER_CONFIDENCE
from Programma_CS2_RENAN.backend.processing.baselines.nickname_resolver import NicknameResolver
from Programma_CS2_RENAN.backend.processing.connect_map_context import distance_with_z_penalty
from Programma_CS2_RENAN.backend.processing.validation.sanity import LIMITS, validate_and_trim


class TestVerticality:
    def test_z_penalty_logic(self):
        """Test that Z-axis difference applies penalty on multi-level maps."""
        # Case 1: Same level (Z diff < 200)
        pos_a = (0, 0, 0)
        pos_b = (100, 0, 100)
        dist_3d = np.linalg.norm(np.array(pos_a) - np.array(pos_b))

        result_same_level = distance_with_z_penalty(pos_a, pos_b, z_threshold=200)
        assert pytest.approx(result_same_level, 0.1) == dist_3d

        # Case 2: Different levels (Z diff > 200)
        pos_c = (0, 0, 0)
        pos_d = (100, 0, 300)  # Z diff 300
        # Expected: XY_dist + (Z_diff * factor) = 100 + (300 * 2.0) = 700
        result_diff_level = distance_with_z_penalty(
            pos_c, pos_d, z_threshold=200, z_penalty_factor=2.0
        )
        assert pytest.approx(result_diff_level, 0.1) == 700.0


class TestFuzzyNickname:
    def test_fuzzy_match_logic(self):
        """Test Levenshtein fuzzy matching logic.

        Note: _fuzzy_match is tested directly as a pure function with
        controlled inputs — no DB or external dependencies involved.
        """
        candidates = ["s1mple", "ZywOo", "NiKo", "m0NESY", "donk"]

        # Exact match
        assert NicknameResolver._fuzzy_match("s1mple", candidates) == "s1mple"

        # Case insensitive
        assert NicknameResolver._fuzzy_match("zywoo", candidates) == "ZywOo"

        # Fuzzy match (typo — threshold 0.8 requires close similarity)
        assert NicknameResolver._fuzzy_match("simple", candidates) == "s1mple"
        # "monsey" vs "m0nesy" scores ~0.67 (leet-speak gap), below 0.8 threshold
        assert NicknameResolver._fuzzy_match("monsey", candidates) is None
        # Near-match with higher similarity
        assert NicknameResolver._fuzzy_match("m0nesy", candidates) == "m0NESY"

        # No match
        assert NicknameResolver._fuzzy_match("Renan", candidates) is None


class TestOutlierTrimming:
    def test_trimming_outliers(self):
        """Test that validate_and_trim clamps values."""
        df = pd.DataFrame({"adr": [-50.0, 100.0, 300.0], "kills": [5, 5, 5], "round": [1, 2, 3]})

        # Strict mode should raise
        with pytest.raises(ValueError):
            validate_and_trim(df, strict=True)

        # Trim mode should clamp
        trimmed = validate_and_trim(df, strict=False)

        assert trimmed["adr"].iloc[0] == 0.0  # Clamped min
        assert trimmed["adr"].iloc[1] == 100.0  # Unchanged
        assert trimmed["adr"].iloc[2] == 200.0  # Clamped max


class TestSoftGate:
    """Test maturity tier classification using DEMO_TIERS and TIER_CONFIDENCE directly.

    This tests the pure lookup logic without mocking DB queries.
    """

    def _tier_for_count(self, count: int) -> str:
        """Reproduce the tier lookup from CoachTrainingManager.get_maturity_tier."""
        for tier_name, (min_demos, max_demos) in DEMO_TIERS.items():
            if min_demos <= count < max_demos:
                return tier_name
        return "MATURE"

    def test_calibrating_tier(self):
        assert self._tier_for_count(0) == "CALIBRATING"
        assert self._tier_for_count(20) == "CALIBRATING"
        assert self._tier_for_count(49) == "CALIBRATING"
        assert TIER_CONFIDENCE["CALIBRATING"] == 0.5

    def test_learning_tier(self):
        assert self._tier_for_count(50) == "LEARNING"
        assert self._tier_for_count(100) == "LEARNING"
        assert self._tier_for_count(199) == "LEARNING"
        assert TIER_CONFIDENCE["LEARNING"] == 0.8

    def test_mature_tier(self):
        assert self._tier_for_count(200) == "MATURE"
        assert self._tier_for_count(250) == "MATURE"
        assert self._tier_for_count(1000) == "MATURE"
        assert TIER_CONFIDENCE["MATURE"] == 1.0

    def test_tier_boundaries_contiguous(self):
        """Verify no gaps between tier boundaries."""
        boundaries = list(DEMO_TIERS.values())
        for i in range(len(boundaries) - 1):
            assert boundaries[i][1] == boundaries[i + 1][0], (
                f"Gap between tier {i} end ({boundaries[i][1]}) "
                f"and tier {i+1} start ({boundaries[i+1][0]})"
            )

    def test_all_tiers_have_confidence(self):
        """Every tier in DEMO_TIERS must have a TIER_CONFIDENCE entry."""
        for tier_name in DEMO_TIERS:
            assert tier_name in TIER_CONFIDENCE, f"Missing confidence for tier {tier_name}"
            assert 0.0 < TIER_CONFIDENCE[tier_name] <= 1.0

