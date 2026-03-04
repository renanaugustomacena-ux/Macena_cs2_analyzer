"""
Tests for the ingestion feature extraction pipeline.

Validates extract_match_stats with controlled scalar inputs
(pure math/formula tests — protocol-compliant).
"""

import sys


import pandas as pd
import pytest


class TestExtractMatchStats:
    """Validate feature extraction from controlled round DataFrames."""

    def test_basic_aggregation(self):
        """Controlled 2-round input produces correct averages."""
        from Programma_CS2_RENAN.backend.processing.feature_engineering.base_features import (
            extract_match_stats,
        )

        df = pd.DataFrame(
            {
                "player_name": ["Player1", "Player1"],
                "kills": [1, 2],
                "deaths": [1, 0],
                "adr": [100, 200],
                "headshot_pct": [0.5, 0.5],
                "kast": [1.0, 1.0],
                "opening_duel": [1, 0],
                "blind_time": [2.0, 3.0],
                "enemies_blinded": [1, 2],
                "is_clutch_win": [0, 1],
                "aggression_score": [0.8, 0.9],
                "hits": [5, 10],
                "shots": [10, 10],
                "money_spent": [4000, 5000],
            }
        )
        stats = extract_match_stats(df)
        assert stats["avg_kills"] == pytest.approx(1.5)
        assert stats["avg_deaths"] == pytest.approx(0.5)
        # kd_ratio = sum(kills) / max(1, sum(deaths)) = 3/1 = 3.0
        assert stats["kd_ratio"] == pytest.approx(3.0)

    def test_empty_dataframe_returns_empty_dict(self):
        """Empty input produces empty result."""
        from Programma_CS2_RENAN.backend.processing.feature_engineering.base_features import (
            extract_match_stats,
        )

        stats = extract_match_stats(pd.DataFrame())
        assert stats == {}

    def test_zero_division_safety(self):
        """All-zero input does not raise division errors."""
        from Programma_CS2_RENAN.backend.processing.feature_engineering.base_features import (
            extract_match_stats,
        )

        df = pd.DataFrame(
            {
                "player_name": ["P1"],
                "kills": [0],
                "deaths": [0],
                "adr": [0],
                "headshot_pct": [0],
                "kast": [0],
                "opening_duel": [0],
                "blind_time": [0],
                "enemies_blinded": [0],
                "is_clutch_win": [0],
                "aggression_score": [0],
                "hits": [0],
                "shots": [0],
                "money_spent": [0],
            }
        )
        stats = extract_match_stats(df)
        assert stats["kd_ratio"] == 0.0
        assert stats["accuracy"] == 0.0
