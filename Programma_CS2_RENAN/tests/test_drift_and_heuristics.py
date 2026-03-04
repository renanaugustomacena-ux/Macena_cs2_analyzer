"""
Phase 3 Verification Gate — Backend Intelligence & Analytics Tests

Validates:
- DriftMonitor.check_drift() and should_retrain()
- HeuristicConfig defaults and serialization
- Differential heatmap data generation
"""

import json
import sys
from datetime import datetime


import numpy as np
import pandas as pd
import pytest


class TestDriftMonitor:
    """Verify statistical drift detection logic."""

    def _make_reference_stats(self):
        """Reference statistics with known mean and std."""
        return {
            "avg_adr": {"mean": 80.0, "std": 10.0},
            "kd_ratio": {"mean": 1.1, "std": 0.3},
            "impact_rounds": {"mean": 5.0, "std": 2.0},
            "avg_hs": {"mean": 0.45, "std": 0.1},
            "avg_kast": {"mean": 0.70, "std": 0.08},
        }

    def test_detects_drift_on_shifted_batch(self):
        """A batch with significantly shifted means should trigger drift."""
        from Programma_CS2_RENAN.backend.processing.validation.drift import DriftMonitor

        monitor = DriftMonitor(z_threshold=2.5)
        ref = self._make_reference_stats()

        # Create batch that's 4 std devs above mean for avg_adr
        n = 20
        shifted = pd.DataFrame(
            {
                "avg_adr": np.full(n, 120.0),  # 4 std above 80
                "kd_ratio": np.full(n, 1.1),
                "impact_rounds": np.full(n, 5.0),
                "avg_hs": np.full(n, 0.45),
                "avg_kast": np.full(n, 0.70),
            }
        )

        report = monitor.check_drift(shifted, ref)
        assert report.is_drifted is True
        assert "avg_adr" in report.drifted_features
        assert report.max_z_score >= 2.5

    def test_no_drift_on_matching_batch(self):
        """A batch matching reference stats should not trigger drift."""
        from Programma_CS2_RENAN.backend.processing.validation.drift import DriftMonitor

        monitor = DriftMonitor(z_threshold=2.5)
        ref = self._make_reference_stats()

        rng = np.random.default_rng(seed=42)
        n = 20
        normal = pd.DataFrame(
            {
                "avg_adr": rng.normal(80.0, 10.0, n),
                "kd_ratio": rng.normal(1.1, 0.3, n),
                "impact_rounds": rng.normal(5.0, 2.0, n),
                "avg_hs": rng.normal(0.45, 0.1, n),
                "avg_kast": rng.normal(0.70, 0.08, n),
            }
        )

        report = monitor.check_drift(normal, ref)
        # With seeded RNG and n=20 near the mean, z-scores should stay under threshold
        assert (
            report.max_z_score < 2.5
        ), f"Seeded normal batch should not drift, but max_z_score={report.max_z_score}"
        assert report.is_drifted is False
        assert isinstance(report.timestamp, datetime)

    def test_drift_report_structure(self):
        """DriftReport has all expected fields."""
        from Programma_CS2_RENAN.backend.processing.validation.drift import DriftReport

        report = DriftReport(
            is_drifted=True,
            drifted_features=["avg_adr"],
            max_z_score=3.5,
            timestamp=datetime.now(),
        )
        assert report.is_drifted is True
        assert report.drifted_features == ["avg_adr"]
        assert report.max_z_score == 3.5


class TestShouldRetrain:
    """Verify retraining trigger logic."""

    def test_triggers_on_3_of_5_drifted(self):
        """3 drifted reports out of 5 should trigger retraining."""
        from Programma_CS2_RENAN.backend.processing.validation.drift import (
            DriftReport,
            should_retrain,
        )

        history = [
            DriftReport(
                is_drifted=True,
                drifted_features=["avg_adr"],
                max_z_score=3.0,
                timestamp=datetime.now(),
            ),
            DriftReport(
                is_drifted=False, drifted_features=[], max_z_score=1.0, timestamp=datetime.now()
            ),
            DriftReport(
                is_drifted=True,
                drifted_features=["kd_ratio"],
                max_z_score=3.5,
                timestamp=datetime.now(),
            ),
            DriftReport(
                is_drifted=False, drifted_features=[], max_z_score=0.5, timestamp=datetime.now()
            ),
            DriftReport(
                is_drifted=True,
                drifted_features=["avg_hs"],
                max_z_score=4.0,
                timestamp=datetime.now(),
            ),
        ]
        assert should_retrain(history, window=5) is True

    def test_no_trigger_on_2_of_5_drifted(self):
        """Only 2 drifted reports out of 5 should NOT trigger retraining."""
        from Programma_CS2_RENAN.backend.processing.validation.drift import (
            DriftReport,
            should_retrain,
        )

        history = [
            DriftReport(
                is_drifted=True,
                drifted_features=["avg_adr"],
                max_z_score=3.0,
                timestamp=datetime.now(),
            ),
            DriftReport(
                is_drifted=False, drifted_features=[], max_z_score=1.0, timestamp=datetime.now()
            ),
            DriftReport(
                is_drifted=True,
                drifted_features=["kd_ratio"],
                max_z_score=3.5,
                timestamp=datetime.now(),
            ),
            DriftReport(
                is_drifted=False, drifted_features=[], max_z_score=0.5, timestamp=datetime.now()
            ),
            DriftReport(
                is_drifted=False, drifted_features=[], max_z_score=1.0, timestamp=datetime.now()
            ),
        ]
        assert should_retrain(history, window=5) is False

    def test_insufficient_history(self):
        """Fewer than window reports should return False."""
        from Programma_CS2_RENAN.backend.processing.validation.drift import (
            DriftReport,
            should_retrain,
        )

        history = [
            DriftReport(
                is_drifted=True,
                drifted_features=["avg_adr"],
                max_z_score=5.0,
                timestamp=datetime.now(),
            ),
        ]
        assert should_retrain(history, window=5) is False


class TestHeuristicConfig:
    """Verify HeuristicConfig defaults and serialization."""

    def test_defaults_instantiate(self):
        """Default HeuristicConfig must instantiate without errors."""
        from Programma_CS2_RENAN.backend.processing.feature_engineering.base_features import (
            HeuristicConfig,
        )

        cfg = HeuristicConfig()
        assert cfg.impact_kill_threshold == 1.0
        assert cfg.impact_adr_threshold == 100.0
        assert cfg.health_max == 100.0
        assert cfg.context_gate_l1_weight == 1e-4

    def test_serialization_roundtrip(self):
        """to_dict() -> JSON -> from_dict() must preserve values."""
        from Programma_CS2_RENAN.backend.processing.feature_engineering.base_features import (
            HeuristicConfig,
        )

        original = HeuristicConfig(impact_kill_threshold=2.5, equipment_value_max=12000.0)
        data = original.to_dict()
        json_str = json.dumps(data)
        loaded = HeuristicConfig.from_dict(json.loads(json_str))

        assert loaded.impact_kill_threshold == 2.5
        assert loaded.equipment_value_max == 12000.0
        assert loaded.health_max == 100.0  # Default preserved

    def test_from_dict_ignores_unknown_keys(self):
        """from_dict should silently ignore unknown keys."""
        from Programma_CS2_RENAN.backend.processing.feature_engineering.base_features import (
            HeuristicConfig,
        )

        data = {"impact_kill_threshold": 1.5, "future_key": 999}
        cfg = HeuristicConfig.from_dict(data)
        assert cfg.impact_kill_threshold == 1.5

    def test_load_learned_heuristics_defaults(self):
        """load_learned_heuristics on missing path returns defaults."""
        from pathlib import Path

        from Programma_CS2_RENAN.backend.processing.feature_engineering.base_features import (
            load_learned_heuristics,
        )

        cfg = load_learned_heuristics(Path("/nonexistent/path/config.json"))
        assert cfg.impact_kill_threshold == 1.0


class TestDifferentialHeatmap:
    """Verify differential heatmap data generation."""

    def test_differential_heatmap_static_import(self):
        """DifferentialHeatmapData class should be importable."""
        from Programma_CS2_RENAN.backend.processing.heatmap_engine import DifferentialHeatmapData

        assert DifferentialHeatmapData is not None

    def test_heatmap_engine_has_differential_method(self):
        """HeatmapEngine must expose generate_differential_heatmap_data."""
        from Programma_CS2_RENAN.backend.processing.heatmap_engine import HeatmapEngine

        assert hasattr(
            HeatmapEngine, "generate_differential_heatmap_data"
        ), "HeatmapEngine is missing generate_differential_heatmap_data method"
