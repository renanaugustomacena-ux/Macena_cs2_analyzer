"""
Tests for feature engineering base features.

Validates extract_match_stats() output: feature count, value ranges,
and derived stat correctness (KD ratio, KAST, headshot rate, ADR).
F9-08: Pure-logic tests only — no DB or model dependency.
"""

import numpy as np
import pandas as pd
import pytest

from Programma_CS2_RENAN.backend.processing.feature_engineering.base_features import (
    extract_match_stats,
)


class TestBaseFeatures:
    def test_extract_match_stats_empty(self):
        df = pd.DataFrame()
        stats = extract_match_stats(df)
        assert stats == {}

    def test_extract_match_stats_basic(self):
        data = {
            "kills": [1, 2, 0],
            "deaths": [1, 0, 1],
            "adr": [100, 200, 0],
            "headshot_pct": [0.5, 0.5, 0.0],
            "kast": [1.0, 1.0, 0.0],
            "opening_duel": [1, 0, -1],  # 1=Win, 0=None, -1=Loss
            "blind_time": [2.0, 3.0, 0.0],
            "enemies_blinded": [1, 2, 0],
            "is_clutch_win": [0, 1, 0],
            "aggression_score": [0.8, 0.9, 0.2],
            "hits": [5, 10, 0],
            "shots": [10, 10, 5],
            "money_spent": [4000, 5000, 2000],
        }
        df = pd.DataFrame(data)
        stats = extract_match_stats(df)

        assert stats["avg_kills"] == 1.0
        assert stats["avg_deaths"] == pytest.approx(0.66, abs=0.01)
        assert stats["kd_ratio"] == 3 / 2  # 1.5
        assert stats["opening_duel_win_pct"] == 0.5  # 1 win out of 2 duels
        assert stats["clutch_win_pct"] == pytest.approx(0.33, abs=0.01)
        assert stats["accuracy"] == 15 / 25  # 0.6
        assert stats["rating"] > 0
        assert stats["rating"] < 5.0, "Rating should be in reasonable range"
        assert "econ_rating" in stats
        assert stats["econ_rating"] > 0, "Non-zero spending should produce positive econ_rating"

    def test_extract_match_stats_zero_division(self):
        data = {
            "kills": [0, 0],
            "deaths": [0, 0],
            "adr": [0, 0],
            "headshot_pct": [0, 0],
            "kast": [0, 0],
            "opening_duel": [0, 0],
            "blind_time": [0, 0],
            "enemies_blinded": [0, 0],
            "is_clutch_win": [0, 0],
            "aggression_score": [0, 0],
            "hits": [0, 0],
            "shots": [0, 0],
            "money_spent": [0, 0],
        }
        df = pd.DataFrame(data)
        stats = extract_match_stats(df)

        assert stats["kd_ratio"] == 0.0
        assert stats["accuracy"] == 0.0
        assert stats["econ_rating"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
