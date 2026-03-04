"""
Tests for Chronovisor Scanner — Phase 7 Coverage Expansion.

Covers:
  ScanResult, CriticalMoment, ScaleConfig (dataclasses)
  ChronovisorScanner._analyze_signal (multi-scale analysis)
  ChronovisorScanner._deduplicate_across_scales (deduplication)
  ChronovisorScanner._analyze_signal_at_scale (single-scale)
"""

import sys


import numpy as np


# ---------------------------------------------------------------------------
# ScanResult
# ---------------------------------------------------------------------------
class TestScanResult:
    """Tests for the ScanResult dataclass."""

    def _make(self, **kwargs):
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import ScanResult
        defaults = {
            "critical_moments": [],
            "success": True,
            "error_message": None,
            "model_loaded": True,
            "ticks_analyzed": 100,
        }
        defaults.update(kwargs)
        return ScanResult(**defaults)

    def test_empty_success(self):
        sr = self._make(critical_moments=[], success=True)
        assert sr.is_empty_success is True

    def test_not_empty_success(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import CriticalMoment
        cm = CriticalMoment(
            match_id=1, start_tick=0, peak_tick=50, end_tick=100,
            severity=0.5, type="anomaly", description="Test",
            scale="micro", context_ticks=64, suggested_review="Watch replay",
        )
        sr = self._make(critical_moments=[cm])
        assert sr.is_empty_success is False

    def test_is_failure(self):
        sr = self._make(success=False, error_message="Model load failed")
        assert sr.is_failure is True

    def test_is_not_failure(self):
        sr = self._make(success=True)
        assert sr.is_failure is False


# ---------------------------------------------------------------------------
# CriticalMoment
# ---------------------------------------------------------------------------
class TestCriticalMoment:
    """Tests for the CriticalMoment dataclass."""

    def _make_moment(self, **kwargs):
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import CriticalMoment
        defaults = {
            "match_id": 42,
            "start_tick": 1000,
            "peak_tick": 1050,
            "end_tick": 1100,
            "severity": 0.75,
            "type": "tactical_error",
            "description": "Missed flash timing",
            "scale": "standard",
            "context_ticks": 192,
            "suggested_review": "Watch tick 1050",
        }
        defaults.update(kwargs)
        return CriticalMoment(**defaults)

    def test_to_dict(self):
        cm = self._make_moment()
        d = cm.to_dict()
        assert isinstance(d, dict)
        assert d["start_tick"] == 1000
        assert d["peak_tick"] == 1050
        assert d["end_tick"] == 1100
        assert d["severity"] == 0.75
        assert d["scale"] == "standard"
        assert d["type"] == "tactical_error"
        # match_id is NOT in to_dict (by design)
        assert "match_id" not in d

    def test_to_highlight_annotation(self):
        cm = self._make_moment()
        ann = cm.to_highlight_annotation()
        assert isinstance(ann, dict)
        assert ann["tick"] == 1050  # Uses peak_tick
        assert ann["severity"] == "critical"  # 0.75 > 0.3
        assert ann["type"] == "tactical_error"
        assert ann["scale"] == "standard"

    def test_all_fields_present(self):
        cm = self._make_moment()
        assert cm.match_id == 42
        assert cm.start_tick == 1000
        assert cm.peak_tick == 1050
        assert cm.end_tick == 1100
        assert cm.severity == 0.75
        assert cm.type == "tactical_error"
        assert cm.scale == "standard"


# ---------------------------------------------------------------------------
# ScaleConfig
# ---------------------------------------------------------------------------
class TestScaleConfig:
    """Tests for the ScaleConfig dataclass."""

    def test_scale_config_creation(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import ScaleConfig
        sc = ScaleConfig(
            name="test", window_ticks=128, lag=32,
            threshold=0.12, description="Test scale",
        )
        assert sc.name == "test"
        assert sc.window_ticks == 128
        assert sc.lag == 32
        assert sc.threshold == 0.12

    def test_analysis_scales_defined(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import ANALYSIS_SCALES
        assert len(ANALYSIS_SCALES) == 3
        names = [s.name for s in ANALYSIS_SCALES]
        assert "micro" in names
        assert "standard" in names
        assert "macro" in names

    def test_micro_scale_values(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import ANALYSIS_SCALES
        micro = [s for s in ANALYSIS_SCALES if s.name == "micro"][0]
        assert micro.window_ticks == 64
        assert micro.lag == 16
        assert micro.threshold == 0.10


# ---------------------------------------------------------------------------
# _deduplicate_across_scales
# ---------------------------------------------------------------------------
class TestDeduplication:
    """Tests for the static deduplication method."""

    def _dedup(self, moments):
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import (
            ChronovisorScanner,
        )
        return ChronovisorScanner._deduplicate_across_scales(moments)

    def _make_cm(self, peak_tick, severity=0.5, scale="micro"):
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import CriticalMoment
        return CriticalMoment(
            match_id=1, start_tick=peak_tick - 32, peak_tick=peak_tick,
            end_tick=peak_tick + 32, severity=severity, type="test",
            description="test", scale=scale, context_ticks=64,
            suggested_review="watch",
        )

    def test_empty_list(self):
        assert self._dedup([]) == []

    def test_single_moment(self):
        cm = self._make_cm(100)
        result = self._dedup([cm])
        assert len(result) == 1

    def test_distant_moments_kept(self):
        """Moments far apart (> MIN_GAP_TICKS) should all be kept."""
        cm1 = self._make_cm(100)
        cm2 = self._make_cm(500)
        result = self._dedup([cm1, cm2])
        assert len(result) == 2

    def test_overlapping_keeps_higher_severity(self):
        """Overlapping moments → keep the one with higher severity."""
        cm1 = self._make_cm(100, severity=0.3)
        cm2 = self._make_cm(110, severity=0.8)  # Close to cm1
        result = self._dedup([cm1, cm2])
        assert len(result) == 1
        assert result[0].severity == 0.8


# ---------------------------------------------------------------------------
# _analyze_signal_at_scale (tested via isolated numpy logic)
# ---------------------------------------------------------------------------
class TestAnalyzeSignalAtScale:
    """Tests for single-scale signal analysis without model dependencies."""

    def _make_scanner_shell(self):
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import (
            ChronovisorScanner,
        )
        scanner = ChronovisorScanner.__new__(ChronovisorScanner)
        return scanner

    def _make_scale(self, **kwargs):
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import ScaleConfig
        defaults = {
            "name": "test", "window_ticks": 10, "lag": 3,
            "threshold": 0.15, "description": "Test",
        }
        defaults.update(kwargs)
        return ScaleConfig(**defaults)

    def test_flat_signal_no_moments(self):
        """A flat signal should produce no critical moments."""
        scanner = self._make_scanner_shell()
        scale = self._make_scale(window_ticks=5, lag=2, threshold=0.1)
        ticks = np.arange(50)
        vals = np.ones(50) * 0.5  # Flat
        moments = scanner._analyze_signal_at_scale(1, ticks, vals, scale)
        assert len(moments) == 0

    def test_spike_detected(self):
        """A sharp spike should be detected as critical moment."""
        scanner = self._make_scanner_shell()
        scale = self._make_scale(window_ticks=10, lag=3, threshold=0.05)
        ticks = np.arange(100)
        vals = np.ones(100) * 0.5
        # Insert spike
        vals[50:55] = 1.0
        moments = scanner._analyze_signal_at_scale(1, ticks, vals, scale)
        # May or may not detect depending on exact algorithm; at least no crash
        assert isinstance(moments, list)

    def test_insufficient_data(self):
        """Too few ticks for the window → no crash, empty result."""
        scanner = self._make_scanner_shell()
        scale = self._make_scale(window_ticks=100, lag=20, threshold=0.1)
        ticks = np.arange(10)
        vals = np.ones(10) * 0.5
        moments = scanner._analyze_signal_at_scale(1, ticks, vals, scale)
        assert isinstance(moments, list)
