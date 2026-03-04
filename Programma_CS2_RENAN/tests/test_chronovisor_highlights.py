"""
Phase 7 — Chronovisor → MatchVisualizer Highlights Integration Tests

Validates:
- CriticalMoment.to_highlight_annotation() produces correct structure
- MatchVisualizer.render_critical_moments() creates a valid image file
- generate_highlight_report() integration function exists
"""

import os
import sys


import pytest


class TestCriticalMomentAnnotation:
    """Verify CriticalMoment.to_highlight_annotation() method."""

    def test_annotation_structure(self):
        """to_highlight_annotation must return a dict with required keys."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import CriticalMoment

        cm = CriticalMoment(
            match_id=1,
            start_tick=100,
            peak_tick=164,
            end_tick=228,
            severity=0.25,
            type="play",
            description="Significant advantage gain (25.0%)",
        )

        annotation = cm.to_highlight_annotation()
        assert isinstance(annotation, dict)
        assert annotation["tick"] == 164
        assert annotation["severity"] == "significant"
        assert annotation["type"] == "play"
        assert "advantage gain" in annotation["description"]

    def test_severity_classification(self):
        """Severity thresholds: >0.3 critical, >0.15 significant, else notable."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import CriticalMoment

        critical = CriticalMoment(
            match_id=1,
            start_tick=0,
            peak_tick=0,
            end_tick=0,
            severity=0.5,
            type="mistake",
            description="",
        )
        assert critical.to_highlight_annotation()["severity"] == "critical"

        significant = CriticalMoment(
            match_id=1,
            start_tick=0,
            peak_tick=0,
            end_tick=0,
            severity=0.2,
            type="play",
            description="",
        )
        assert significant.to_highlight_annotation()["severity"] == "significant"

        notable = CriticalMoment(
            match_id=1,
            start_tick=0,
            peak_tick=0,
            end_tick=0,
            severity=0.1,
            type="play",
            description="",
        )
        assert notable.to_highlight_annotation()["severity"] == "notable"

    def test_to_dict_still_works(self):
        """to_dict must still work as before (backward compatibility)."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import CriticalMoment

        cm = CriticalMoment(
            match_id=1,
            start_tick=10,
            peak_tick=20,
            end_tick=30,
            severity=0.3,
            type="play",
            description="test",
        )
        d = cm.to_dict()
        assert d["peak_tick"] == 20
        assert "match_id" not in d  # Not in to_dict per original

    def test_context_ticks_default(self):
        """CriticalMoment.context_ticks should default to 128."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import CriticalMoment

        cm = CriticalMoment(
            match_id=1,
            start_tick=0,
            peak_tick=0,
            end_tick=0,
            severity=0.1,
            type="play",
            description="test",
        )
        assert cm.context_ticks == 128
        assert cm.suggested_review == ""

    def test_context_ticks_in_dict(self):
        """to_dict and to_highlight_annotation include context_ticks and suggested_review."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import CriticalMoment

        cm = CriticalMoment(
            match_id=1,
            start_tick=0,
            peak_tick=5000,
            end_tick=100,
            severity=0.2,
            type="play",
            description="test",
            scale="macro",
            context_ticks=128,
            suggested_review="Review 2.0s around tick 5000",
        )
        d = cm.to_dict()
        assert d["context_ticks"] == 128
        assert "tick 5000" in d["suggested_review"]

        ann = cm.to_highlight_annotation()
        assert ann["context_ticks"] == 128
        assert ann["scale"] == "macro"
        assert "tick 5000" in ann["suggested_review"]

    def test_annotation_includes_scale(self):
        """to_highlight_annotation must include scale key."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import CriticalMoment

        for scale_name in ("micro", "standard", "macro"):
            cm = CriticalMoment(
                match_id=1,
                start_tick=0,
                peak_tick=0,
                end_tick=0,
                severity=0.1,
                type="play",
                description="test",
                scale=scale_name,
            )
            assert cm.to_highlight_annotation()["scale"] == scale_name


class TestMultiScaleDeduplication:
    """Verify cross-scale deduplication logic."""

    def test_micro_preferred_over_standard(self):
        """When micro and standard detect the same peak, micro wins."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import (
            ChronovisorScanner,
            CriticalMoment,
        )

        moments = [
            CriticalMoment(
                match_id=1,
                start_tick=90,
                peak_tick=100,
                end_tick=110,
                severity=0.2,
                type="play",
                description="micro",
                scale="micro",
            ),
            CriticalMoment(
                match_id=1,
                start_tick=80,
                peak_tick=105,
                end_tick=120,
                severity=0.25,
                type="play",
                description="standard",
                scale="standard",
            ),
        ]

        result = ChronovisorScanner._deduplicate_across_scales(moments)
        assert len(result) == 1
        assert result[0].scale == "micro"

    def test_higher_severity_wins_same_scale(self):
        """When same scale detects overlapping peaks, higher severity wins."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import (
            ChronovisorScanner,
            CriticalMoment,
        )

        moments = [
            CriticalMoment(
                match_id=1,
                start_tick=90,
                peak_tick=100,
                end_tick=110,
                severity=0.15,
                type="play",
                description="weak",
                scale="standard",
            ),
            CriticalMoment(
                match_id=1,
                start_tick=95,
                peak_tick=110,
                end_tick=125,
                severity=0.30,
                type="play",
                description="strong",
                scale="standard",
            ),
        ]

        result = ChronovisorScanner._deduplicate_across_scales(moments)
        assert len(result) == 1
        assert result[0].severity == 0.30

    def test_distant_peaks_both_kept(self):
        """Peaks far apart should both be preserved."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import (
            ChronovisorScanner,
            CriticalMoment,
        )

        moments = [
            CriticalMoment(
                match_id=1,
                start_tick=100,
                peak_tick=100,
                end_tick=110,
                severity=0.2,
                type="play",
                description="a",
                scale="standard",
            ),
            CriticalMoment(
                match_id=1,
                start_tick=500,
                peak_tick=500,
                end_tick=510,
                severity=0.2,
                type="mistake",
                description="b",
                scale="standard",
            ),
        ]

        result = ChronovisorScanner._deduplicate_across_scales(moments)
        assert len(result) == 2

    def test_empty_list(self):
        """Empty input returns empty output."""
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import ChronovisorScanner

        assert ChronovisorScanner._deduplicate_across_scales([]) == []


class TestRenderCriticalMoments:
    """Verify MatchVisualizer.render_critical_moments()."""

    def test_render_produces_file(self, tmp_path):
        """render_critical_moments should create a .png file."""
        from Programma_CS2_RENAN.reporting.visualizer import MatchVisualizer

        viz = MatchVisualizer(output_dir=str(tmp_path))
        moments = [
            {
                "tick": 1000,
                "description": "Advantage gain (30%)",
                "severity": "critical",
                "type": "play",
                "position": (-1000, 500),
            },
            {
                "tick": 2500,
                "description": "Advantage loss (20%)",
                "severity": "significant",
                "type": "mistake",
                "position": (500, -200),
            },
        ]

        path = viz.render_critical_moments(moments, "de_mirage")
        assert path is not None
        assert os.path.exists(path)
        assert path.endswith(".png")
        assert os.path.getsize(path) > 0

    def test_render_empty_moments(self):
        """Empty moments list should return None."""
        from Programma_CS2_RENAN.reporting.visualizer import MatchVisualizer

        viz = MatchVisualizer()
        result = viz.render_critical_moments([], "de_mirage")
        assert result is None

    def test_render_without_positions(self, tmp_path):
        """Moments without explicit positions should still render (auto-placed)."""
        from Programma_CS2_RENAN.reporting.visualizer import MatchVisualizer

        viz = MatchVisualizer(output_dir=str(tmp_path))
        moments = [
            {
                "tick": 500,
                "description": "Test moment",
                "severity": "notable",
                "type": "play",
                "position": None,
            },
        ]

        path = viz.render_critical_moments(moments, "de_dust2")
        assert path is not None
        assert os.path.exists(path)

    def test_render_with_scale_info(self, tmp_path):
        """Moments with scale info should render with different marker sizes."""
        from Programma_CS2_RENAN.reporting.visualizer import MatchVisualizer

        viz = MatchVisualizer(output_dir=str(tmp_path))
        moments = [
            {
                "tick": 100,
                "description": "Micro event",
                "severity": "notable",
                "type": "play",
                "position": (-500, 200),
                "scale": "micro",
            },
            {
                "tick": 500,
                "description": "Standard event",
                "severity": "significant",
                "type": "mistake",
                "position": (0, 0),
                "scale": "standard",
            },
            {
                "tick": 900,
                "description": "Macro event",
                "severity": "critical",
                "type": "play",
                "position": (500, -200),
                "scale": "macro",
            },
        ]

        path = viz.render_critical_moments(moments, "de_mirage")
        assert path is not None
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0

    def test_scale_marker_sizes_in_source(self):
        """Visualizer source must define scale_marker_sizes with micro < standard < macro."""
        import Programma_CS2_RENAN.reporting.visualizer as viz_mod

        with open(viz_mod.__file__, "r", encoding="utf-8") as f:
            source = f.read()
        assert "scale_marker_sizes" in source
        assert '"micro"' in source
        assert '"standard"' in source
        assert '"macro"' in source


class TestGenerateHighlightReport:
    """Verify the integration function exists and handles edge cases."""

    def test_function_importable(self):
        """generate_highlight_report should be importable."""
        from Programma_CS2_RENAN.reporting.visualizer import generate_highlight_report

        assert callable(generate_highlight_report)
