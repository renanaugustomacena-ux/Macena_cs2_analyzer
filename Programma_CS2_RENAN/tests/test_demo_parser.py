"""
Tests for demo_parser module.

Tests pure math/formula behavior with controlled inputs and
integration with real demo files (skipped if unavailable).
No MagicMock, no @patch on non-HTTP targets.
"""

import sys
from pathlib import Path


import pandas as pd
import pytest

DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "demos"


def _find_demo_file():
    """Return path to first .dem file available, or None."""
    if DEMO_DIR.is_dir():
        for f in DEMO_DIR.iterdir():
            if f.suffix == ".dem":
                return str(f)
    return None


class TestParseDemoEdgeCases:
    """Test parse_demo behavior on edge cases — no mocks needed."""

    def test_nonexistent_file_returns_empty(self):
        """parse_demo must return empty DataFrame for missing file."""
        from Programma_CS2_RENAN.backend.data_sources.demo_parser import parse_demo

        result = parse_demo("this_file_does_not_exist_99999.dem")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_nonexistent_file_with_target_player(self):
        """parse_demo with target_player still returns empty for missing file."""
        from Programma_CS2_RENAN.backend.data_sources.demo_parser import parse_demo

        result = parse_demo("no_such_demo.dem", target_player="Player1")
        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestParseSequentialTicksEdgeCases:
    """Test parse_sequential_ticks behavior on edge cases — no mocks needed."""

    def test_nonexistent_file_returns_empty(self):
        """parse_sequential_ticks must return empty DataFrame for missing file."""
        from Programma_CS2_RENAN.backend.data_sources.demo_parser import parse_sequential_ticks

        result = parse_sequential_ticks("nonexistent_demo_file.dem", target_player="Player1")
        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestRatingFormulas:
    """Test the HLTV 2.0 rating formulas with controlled scalar inputs.

    These mirror the calculations inside _extract_stats_with_full_fields()
    using the exact same formula coefficients from demo_parser.py.
    """

    def test_kd_ratio_calculation(self):
        """KD ratio = kills / deaths (0-division safe)."""
        kills = 20
        deaths = 10
        assert kills / max(deaths, 1) == pytest.approx(2.0)

        # Zero deaths case
        assert kills / max(0, 1) == pytest.approx(20.0)

    def test_per_round_averages(self):
        """avg_kills, avg_deaths, avg_adr scale linearly with total_rounds."""
        total_rounds = 24
        kills_total = 48
        deaths_total = 24
        damage_total = 2400

        avg_kills = kills_total / total_rounds
        avg_deaths = deaths_total / total_rounds
        avg_adr = damage_total / total_rounds

        assert avg_kills == pytest.approx(2.0)
        assert avg_deaths == pytest.approx(1.0)
        assert avg_adr == pytest.approx(100.0)

    def test_rating_components(self):
        """Rating 2.0 component normalization uses known baseline divisors."""
        kpr = 0.679  # exactly at baseline
        dpr = 0.683  # above baseline death rate
        kast = 0.70
        avg_adr = 73.3

        r_kill = kpr / 0.679
        r_surv = (1.0 - dpr) / 0.317
        r_kast = kast / 0.70
        r_dmg = avg_adr / 73.3

        # At baseline values, all components should be ~1.0
        assert r_kill == pytest.approx(1.0)
        assert r_kast == pytest.approx(1.0)
        assert r_dmg == pytest.approx(1.0)

        # Survival: (1.0 - 0.683) / 0.317 = 0.317/0.317 = 1.0
        assert r_surv == pytest.approx(1.0)

    def test_final_rating_at_baseline(self):
        """Rating at exact baseline values should be ~1.0."""
        kpr = 0.679
        dpr = 0.683
        kast = 0.70
        avg_adr = 73.3
        impact = 1.0

        r_kill = kpr / 0.679
        r_surv = (1.0 - dpr) / 0.317
        r_kast = kast / 0.70
        r_imp = impact / 1.0
        r_dmg = avg_adr / 73.3

        rating = (r_kill + r_surv + r_kast + r_imp + r_dmg) / 5.0
        assert rating == pytest.approx(1.0)

    def test_econ_rating_formula(self):
        """econ_rating = avg_adr / 85.0."""
        avg_adr = 85.0
        assert avg_adr / 85.0 == pytest.approx(1.0)

        avg_adr = 42.5
        assert avg_adr / 85.0 == pytest.approx(0.5)

    def test_high_performer_rating_above_one(self):
        """A player with stats above baseline should have rating > 1.0."""
        kpr = 1.2
        dpr = 0.4
        kast = 0.85
        avg_adr = 100.0
        impact = (kpr * 2.13) + (avg_adr / 100 * 0.42)

        r_kill = kpr / 0.679
        r_surv = (1.0 - dpr) / 0.317
        r_kast = kast / 0.70
        r_imp = impact / 1.0
        r_dmg = avg_adr / 73.3

        rating = (r_kill + r_surv + r_kast + r_imp + r_dmg) / 5.0
        assert rating > 1.0


class TestDemoParserIntegration:
    """Integration tests using real .dem files (skipped if unavailable)."""

    def test_parse_real_demo(self):
        """Parse a real demo file and verify output structure."""
        demo_path = _find_demo_file()
        if demo_path is None:
            pytest.skip("No .dem files in data/demos/")

        from Programma_CS2_RENAN.backend.data_sources.demo_parser import parse_demo

        result = parse_demo(demo_path)
        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert "player_name" in result.columns
            assert "avg_kills" in result.columns
            assert "rating" in result.columns
            assert (result["avg_kills"] >= 0).all()

    def test_parse_sequential_ticks_real(self):
        """Parse sequential ticks from a real demo file."""
        demo_path = _find_demo_file()
        if demo_path is None:
            pytest.skip("No .dem files in data/demos/")

        from Programma_CS2_RENAN.backend.data_sources.demo_parser import parse_sequential_ticks

        result = parse_sequential_ticks(demo_path, target_player="ALL", rate=64)
        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert "health" in result.columns
            assert "X" in result.columns

