"""
Tests for coach_manager.py — Training logic, maturity system, dataset splits,
delta calculations, prerequisite checks, skill radar, and module-level functions.

Complements test_coach_manager_tensors.py (feature list integrity, None handling,
tier constants, pro baseline defaults).

CI-portable: uses in-memory SQLite with monkeypatched get_db_manager.
"""

import sys


from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch
from sqlmodel import Session, SQLModel, create_engine, select

from Programma_CS2_RENAN.backend.nn.coach_manager import (
    MATCH_AGGREGATE_FEATURES,
    TARGET_INDICES,
    TRAINING_FEATURES,
    CoachTrainingManager,
    _apply_dynamic_window_targets,
    _calculate_pro_mean,
    _extract_feature_vector,
)
from Programma_CS2_RENAN.backend.storage.db_models import (
    CoachState,
    PlayerMatchStats,
    PlayerProfile,
)


# ---------------------------------------------------------------------------
# In-memory DB manager (same pattern as test_experience_bank_db.py)
# ---------------------------------------------------------------------------

class _InMemoryDBManager:
    def __init__(self, engine):
        self._engine = engine

    @contextmanager
    def get_session(self, engine_key="default"):
        with Session(self._engine, expire_on_commit=False) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise


def _make_engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


def _make_manager(monkeypatch):
    """Create a CoachTrainingManager backed by in-memory DB."""
    engine = _make_engine()
    mock_db = _InMemoryDBManager(engine)

    monkeypatch.setattr(
        "Programma_CS2_RENAN.backend.nn.coach_manager.get_db_manager", lambda: mock_db
    )

    mgr = CoachTrainingManager.__new__(CoachTrainingManager)
    mgr.db = mock_db
    mgr.pipeline = MagicMock()
    mgr.feature_names = TRAINING_FEATURES
    mgr.target_indices = TARGET_INDICES
    return mgr, engine


def _seed_matches(engine, pro_count=0, user_count=0):
    """Seed PlayerMatchStats."""
    with Session(engine) as session:
        base_dt = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        for i in range(pro_count):
            session.add(
                PlayerMatchStats(
                    player_name=f"Pro{i}",
                    demo_name=f"pro_demo_{i}.dem",
                    match_date=base_dt + timedelta(days=i),
                    is_pro=True,
                    avg_kills=22.0 + i,
                    avg_deaths=16.0,
                    avg_adr=85.0,
                    avg_hs=0.50,
                    avg_kast=0.72,
                    accuracy=0.28,
                    econ_rating=1.1,
                    kd_ratio=1.3,
                    kpr=0.75,
                    dpr=0.55,
                    rating=1.15,
                )
            )
        user_base_dt = datetime(2024, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        for i in range(user_count):
            session.add(
                PlayerMatchStats(
                    player_name="TestPlayer",
                    demo_name=f"user_demo_{i}.dem",
                    match_date=user_base_dt + timedelta(days=i),
                    is_pro=False,
                    avg_kills=17.0,
                    avg_deaths=18.0,
                    avg_adr=72.0,
                    avg_hs=0.45,
                    avg_kast=0.65,
                    accuracy=0.24,
                    econ_rating=0.95,
                    kd_ratio=0.94,
                    kpr=0.62,
                    dpr=0.65,
                    rating=0.94,
                )
            )
        session.commit()


def _seed_coach_state(engine, total_matches=0):
    """Insert a CoachState row with given match count."""
    with Session(engine) as session:
        state = CoachState(total_matches_processed=total_matches)
        session.add(state)
        session.commit()


# ===========================================================================
# Test classes
# ===========================================================================


class TestMaturityGate:
    """Tests for check_maturity_gate and related tier/confidence methods."""

    def test_no_coach_state_returns_not_mature(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        is_mature, count = mgr.check_maturity_gate()
        assert is_mature is False
        assert count == 0

    def test_below_threshold_returns_not_mature(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=30)
        is_mature, count = mgr.check_maturity_gate()
        assert is_mature is False
        assert count == 30

    def test_at_threshold_returns_mature(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=50)
        is_mature, count = mgr.check_maturity_gate()
        assert is_mature is True
        assert count == 50

    def test_above_threshold_returns_mature(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=250)
        is_mature, count = mgr.check_maturity_gate()
        assert is_mature is True
        assert count == 250

    def test_null_total_matches_treated_as_zero(self, monkeypatch):
        """CoachState with total_matches_processed=None should be treated as 0."""
        mgr, engine = _make_manager(monkeypatch)
        with Session(engine) as session:
            state = CoachState()
            state.total_matches_processed = None  # type: ignore[assignment]
            session.add(state)
            session.commit()
        # The `or 0` guard in check_maturity_gate handles this
        is_mature, count = mgr.check_maturity_gate()
        assert is_mature is False
        assert count == 0


class TestMaturityTier:
    """Tests for get_maturity_tier."""

    def test_calibrating_tier(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=10)
        assert mgr.get_maturity_tier() == "CALIBRATING"

    def test_learning_tier(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=100)
        assert mgr.get_maturity_tier() == "LEARNING"

    def test_mature_tier(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=300)
        assert mgr.get_maturity_tier() == "MATURE"

    def test_boundary_calibrating_to_learning(self, monkeypatch):
        """Exactly 50 demos → LEARNING (50 is the boundary)."""
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=50)
        assert mgr.get_maturity_tier() == "LEARNING"

    def test_boundary_learning_to_mature(self, monkeypatch):
        """Exactly 200 demos → MATURE."""
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=200)
        assert mgr.get_maturity_tier() == "MATURE"


class TestConfidenceMultiplier:
    """Tests for get_confidence_multiplier."""

    def test_calibrating_confidence(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=20)
        assert mgr.get_confidence_multiplier() == 0.5

    def test_learning_confidence(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=100)
        assert mgr.get_confidence_multiplier() == 0.8

    def test_mature_confidence(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=250)
        assert mgr.get_confidence_multiplier() == 1.0


class TestIncrementMaturityCounter:
    """Tests for increment_maturity_counter."""

    def test_creates_state_if_missing(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        mgr.increment_maturity_counter()
        with Session(engine) as session:
            state = session.exec(select(CoachState)).first()
            assert state is not None
            assert state.total_matches_processed == 1

    def test_increments_existing_counter(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=42)
        mgr.increment_maturity_counter()
        with Session(engine) as session:
            state = session.exec(select(CoachState)).first()
            assert state.total_matches_processed == 43

    def test_multiple_increments(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=0)
        for _ in range(5):
            mgr.increment_maturity_counter()
        with Session(engine) as session:
            state = session.exec(select(CoachState)).first()
            assert state.total_matches_processed == 5


class TestDatasetSplits:
    """Tests for _assign_dataset_splits — chronological 70/15/15."""

    def test_empty_db_no_crash(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        mgr._assign_dataset_splits()  # Should not raise

    def test_splits_assigned_correctly_for_10_matches(self, monkeypatch):
        """10 matches → 7 train, 1 val, 2 test (int(10*0.70)=7, int(10*0.85)=8)."""
        mgr, engine = _make_manager(monkeypatch)
        _seed_matches(engine, pro_count=10)
        mgr._assign_dataset_splits()
        with Session(engine) as session:
            matches = session.exec(
                select(PlayerMatchStats).order_by(PlayerMatchStats.match_date)
            ).all()
            splits = [m.dataset_split for m in matches]
            assert splits.count("train") == 7
            assert splits.count("val") == 1
            assert splits.count("test") == 2

    def test_splits_preserve_temporal_order(self, monkeypatch):
        """Train must come before val, val before test (temporal split)."""
        mgr, engine = _make_manager(monkeypatch)
        _seed_matches(engine, pro_count=20)
        mgr._assign_dataset_splits()
        with Session(engine) as session:
            matches = session.exec(
                select(PlayerMatchStats).order_by(PlayerMatchStats.match_date)
            ).all()
            last_train_idx = -1
            first_val_idx = len(matches)
            last_val_idx = -1
            first_test_idx = len(matches)
            for i, m in enumerate(matches):
                if m.dataset_split == "train":
                    last_train_idx = i
                elif m.dataset_split == "val":
                    first_val_idx = min(first_val_idx, i)
                    last_val_idx = i
                elif m.dataset_split == "test":
                    first_test_idx = min(first_test_idx, i)
            assert last_train_idx < first_val_idx, "Train must come before val"
            assert last_val_idx < first_test_idx, "Val must come before test"

    def test_splits_independent_for_pro_and_user(self, monkeypatch):
        """Pro and user matches get independent splits."""
        mgr, engine = _make_manager(monkeypatch)
        _seed_matches(engine, pro_count=10, user_count=10)
        mgr._assign_dataset_splits()
        with Session(engine) as session:
            pros = session.exec(
                select(PlayerMatchStats).where(PlayerMatchStats.is_pro == True)
            ).all()
            users = session.exec(
                select(PlayerMatchStats).where(PlayerMatchStats.is_pro == False)
            ).all()
            # Both groups should have all three splits
            pro_splits = set(m.dataset_split for m in pros)
            user_splits = set(m.dataset_split for m in users)
            assert "train" in pro_splits
            assert "val" in pro_splits
            assert "test" in pro_splits
            assert "train" in user_splits
            assert "val" in user_splits
            assert "test" in user_splits

    def test_single_match_goes_to_test(self, monkeypatch):
        """1 match → int(1*0.70)=0 train, int(1*0.85)=0 val, 1 test."""
        mgr, engine = _make_manager(monkeypatch)
        _seed_matches(engine, pro_count=1)
        mgr._assign_dataset_splits()
        with Session(engine) as session:
            m = session.exec(select(PlayerMatchStats)).first()
            assert m.dataset_split == "test"

    def test_two_matches_one_train_one_test(self, monkeypatch):
        """2 matches → int(2*0.70)=1 train, int(2*0.85)=1 val(=test), 1 test."""
        mgr, engine = _make_manager(monkeypatch)
        _seed_matches(engine, pro_count=2)
        mgr._assign_dataset_splits()
        with Session(engine) as session:
            matches = session.exec(
                select(PlayerMatchStats).order_by(PlayerMatchStats.match_date)
            ).all()
            splits = [m.dataset_split for m in matches]
            assert splits[0] == "train"
            # Second match: i=1, train_idx=1, val_idx=1 → test
            assert splits[1] == "test"


class TestCalculateDeltas:
    """Tests for _calculate_deltas — Z-score normalized improvement deltas."""

    def test_zero_delta_when_equal_to_baseline(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        pro_vec = np.zeros(len(MATCH_AGGREGATE_FEATURES), dtype=np.float32)
        pro_vec[0] = 20.0  # avg_kills
        pro_vec[2] = 80.0  # avg_adr
        pro_vec[4] = 0.72  # avg_kast
        pro_vec[11] = 1.05  # rating

        player_vec = pro_vec.copy()
        deltas = mgr._calculate_deltas(player_vec, pro_vec)

        assert len(deltas) == len(TARGET_INDICES)
        for d in deltas:
            assert abs(d) < 1e-4, f"Delta should be ~0 when equal to baseline, got {d}"

    def test_negative_delta_when_below_baseline(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        pro_vec = np.zeros(len(MATCH_AGGREGATE_FEATURES), dtype=np.float32)
        pro_vec[0] = 20.0
        pro_vec[2] = 80.0
        pro_vec[4] = 0.72
        pro_vec[11] = 1.05

        player_vec = pro_vec.copy()
        player_vec[2] = 60.0  # ADR below baseline

        deltas = mgr._calculate_deltas(player_vec, pro_vec)
        # TARGET_INDICES[1] = 2 (avg_adr) → delta should be positive (target - current > 0)
        adr_delta = deltas[1]
        assert adr_delta > 0, f"ADR delta should be positive (need improvement), got {adr_delta}"

    def test_deltas_clipped_to_minus_one_plus_one(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        pro_vec = np.zeros(len(MATCH_AGGREGATE_FEATURES), dtype=np.float32)
        pro_vec[0] = 20.0
        pro_vec[2] = 80.0
        pro_vec[4] = 0.72
        pro_vec[11] = 1.05

        player_vec = pro_vec.copy()
        player_vec[0] = 0.0  # Extremely low kills → huge delta

        deltas = mgr._calculate_deltas(player_vec, pro_vec)
        for d in deltas:
            assert -1.0 <= d <= 1.0, f"Delta must be clipped to [-1, 1], got {d}"

    def test_delta_output_length_matches_target_indices(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        pro_vec = np.ones(len(MATCH_AGGREGATE_FEATURES), dtype=np.float32)
        player_vec = np.ones(len(MATCH_AGGREGATE_FEATURES), dtype=np.float32)
        deltas = mgr._calculate_deltas(player_vec, pro_vec)
        assert len(deltas) == len(TARGET_INDICES)


class TestPrepareTensorsFlow:
    """Tests for _prepare_tensors — full flow from mock stats to tensors."""

    def _make_fake_stats_list(self, n=3):
        """Create a list of mock objects mimicking PlayerMatchStats."""
        items = []
        for i in range(n):
            base = {f: 0.5 + i * 0.01 for f in MATCH_AGGREGATE_FEATURES}
            base["avg_kills"] = 18.0 + i
            base["avg_adr"] = 75.0 + i
            base["avg_kast"] = 0.68 + i * 0.01
            base["rating"] = 1.0 + i * 0.05

            class FakeStats:
                def __init__(self, data):
                    self._data = data

                def model_dump(self):
                    return self._data

            items.append(FakeStats(base))
        return items

    def test_output_shapes(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        with patch(
            "Programma_CS2_RENAN.backend.nn.coach_manager.CoachTrainingManager._get_pro_baseline_vector",
            return_value=np.ones(len(MATCH_AGGREGATE_FEATURES), dtype=np.float32),
        ):
            X, y = mgr._prepare_tensors(self._make_fake_stats_list(5))
        assert X.shape == (5, len(MATCH_AGGREGATE_FEATURES))
        assert y.shape == (5, len(TARGET_INDICES))

    def test_output_types_are_float32_tensors(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        with patch(
            "Programma_CS2_RENAN.backend.nn.coach_manager.CoachTrainingManager._get_pro_baseline_vector",
            return_value=np.ones(len(MATCH_AGGREGATE_FEATURES), dtype=np.float32),
        ):
            X, y = mgr._prepare_tensors(self._make_fake_stats_list(2))
        assert X.dtype == torch.float32
        assert y.dtype == torch.float32

    def test_no_nan_in_output(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        with patch(
            "Programma_CS2_RENAN.backend.nn.coach_manager.CoachTrainingManager._get_pro_baseline_vector",
            return_value=np.ones(len(MATCH_AGGREGATE_FEATURES), dtype=np.float32),
        ):
            X, y = mgr._prepare_tensors(self._make_fake_stats_list(3))
        assert not torch.any(torch.isnan(X)), "X should have no NaN"
        assert not torch.any(torch.isnan(y)), "y should have no NaN"

    def test_y_values_clipped(self, monkeypatch):
        """All y (delta) values should be in [-1, 1] due to clipping."""
        mgr, _engine = _make_manager(monkeypatch)
        with patch(
            "Programma_CS2_RENAN.backend.nn.coach_manager.CoachTrainingManager._get_pro_baseline_vector",
            return_value=np.ones(len(MATCH_AGGREGATE_FEATURES), dtype=np.float32) * 100,
        ):
            X, y = mgr._prepare_tensors(self._make_fake_stats_list(3))
        assert torch.all(y >= -1.0) and torch.all(y <= 1.0)


class TestProBaselineVector:
    """Tests for _get_pro_baseline_vector with mocked get_pro_baseline."""

    def test_returns_correct_shape(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.get_pro_baseline",
            return_value={},
        ):
            vec = mgr._get_pro_baseline_vector()
        assert vec.shape == (len(MATCH_AGGREGATE_FEATURES),)
        assert vec.dtype == np.float32

    def test_uses_db_baseline_when_available(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        # Simulate a DB baseline with dict format (mean/std)
        fake_baseline = {
            "avg_kills": {"mean": 25.0, "std": 3.0},
            "avg_adr": {"mean": 90.0, "std": 10.0},
        }
        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.get_pro_baseline",
            return_value=fake_baseline,
        ):
            vec = mgr._get_pro_baseline_vector()
        # avg_kills is index 0
        assert vec[0] == 25.0, "Should use mean from DB baseline dict"
        # avg_adr is index 2
        assert vec[2] == 90.0, "Should use mean from DB baseline dict"

    def test_uses_defaults_for_missing_features(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.get_pro_baseline",
            return_value={},
        ):
            vec = mgr._get_pro_baseline_vector()
        # avg_kills default = 0.75, avg_adr default = 80.0
        assert vec[0] == pytest.approx(0.75)
        assert vec[2] == pytest.approx(80.0)

    def test_scalar_baseline_value(self, monkeypatch):
        """If baseline value is a scalar (not dict), use it directly."""
        mgr, _engine = _make_manager(monkeypatch)
        fake_baseline = {"avg_kills": 30.0}
        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.get_pro_baseline",
            return_value=fake_baseline,
        ):
            vec = mgr._get_pro_baseline_vector()
        assert vec[0] == 30.0


class TestCheckPrerequisites:
    """Tests for check_prerequisites and _check_db_prerequisites."""

    def test_ready_with_enough_pro_demos(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_matches(engine, pro_count=10)
        mock_sm = MagicMock()
        monkeypatch.setattr(
            "Programma_CS2_RENAN.backend.storage.state_manager.state_manager",
            mock_sm,
        )
        ok, msg = mgr.check_prerequisites()
        assert ok is True
        assert msg == "Ready"

    def test_not_ready_without_ids_and_no_pro_demos(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        # No pro demos, no profile → stalled
        mock_sm = MagicMock()
        monkeypatch.setattr(
            "Programma_CS2_RENAN.backend.storage.state_manager.state_manager",
            mock_sm,
        )
        ok, msg = mgr.check_prerequisites()
        assert ok is False
        assert "Steam" in msg or "FACEIT" in msg or "required" in msg.lower()

    def test_gathering_pro_baseline_with_partial_pros(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_matches(engine, pro_count=5)  # 5/10 pro demos
        mock_sm = MagicMock()
        monkeypatch.setattr(
            "Programma_CS2_RENAN.backend.storage.state_manager.state_manager",
            mock_sm,
        )
        ok, msg = mgr.check_prerequisites()
        assert ok is False
        assert "5/10" in msg or "Gathering" in msg

    def test_user_demos_insufficient_with_profile_present(self, monkeypatch):
        """With a profile but insufficient pro demos, still returns not ready.

        Note: PlayerProfile does NOT have steam_connected/faceit_connected fields.
        _check_db_prerequisites accesses them → AttributeError caught by outer try/except.
        This documents a known dead-code path in _check_db_prerequisites.
        """
        mgr, engine = _make_manager(monkeypatch)
        _seed_matches(engine, pro_count=5, user_count=3)
        # Add profile without steam/faceit (model doesn't have those fields)
        with Session(engine) as session:
            session.add(PlayerProfile(player_name="TestPlayer", role="Entry", bio="test"))
            session.commit()
        mock_sm = MagicMock()
        monkeypatch.setattr(
            "Programma_CS2_RENAN.backend.storage.state_manager.state_manager",
            mock_sm,
        )
        ok, msg = mgr.check_prerequisites()
        assert ok is False
        # AttributeError from missing steam_connected → caught as "Prerequisite Check Failed"
        assert "Failed" in msg or "5/10" in msg or "Gathering" in msg

    def test_exception_returns_false(self, monkeypatch):
        """If DB access throws, check_prerequisites should return (False, error msg)."""
        mgr, _engine = _make_manager(monkeypatch)
        # Break the DB
        mgr.db = MagicMock()
        mgr.db.get_session.side_effect = RuntimeError("DB down")
        ok, msg = mgr.check_prerequisites()
        assert ok is False
        assert "Failed" in msg or "DB down" in msg


class TestGetUserBaselineVector:
    """Tests for _get_user_baseline_vector."""

    def test_fallback_to_pro_when_insufficient_data(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        # No user data → fallback to pro baseline
        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.get_pro_baseline",
            return_value={},
        ):
            vec = mgr._get_user_baseline_vector()
        assert vec.shape == (len(MATCH_AGGREGATE_FEATURES),)

    def test_returns_mean_of_user_data(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_matches(engine, user_count=10)
        # Assign splits so _fetch_training_data works
        mgr._assign_dataset_splits()
        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.get_pro_baseline",
            return_value={},
        ):
            vec = mgr._get_user_baseline_vector()
        assert vec.shape == (len(MATCH_AGGREGATE_FEATURES),)
        # All user matches have avg_kills=17.0 → mean should be 17.0
        kills_idx = MATCH_AGGREGATE_FEATURES.index("avg_kills")
        assert vec[kills_idx] == pytest.approx(17.0, abs=0.1)


class TestGetSkillRadarData:
    """Tests for get_skill_radar_data."""

    def test_calibrating_returns_status(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=10)
        result = mgr.get_skill_radar_data()
        assert result["status"] == "calibrating"
        assert result["maturity_progress"] == 10
        assert result["data"] == {}

    def test_mature_returns_radar_data(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=250)
        _seed_matches(engine, user_count=5)
        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.get_pro_baseline",
            return_value={
                "avg_adr": {"mean": 80.0, "std": 10.0},
                "impact_rounds": {"mean": 0.7, "std": 0.1},
                "avg_kast": {"mean": 0.72, "std": 0.05},
                "accuracy": {"mean": 0.50, "std": 0.05},
                "rating": {"mean": 1.05, "std": 0.1},
                "econ_rating": {"mean": 0.75, "std": 0.1},
            },
        ):
            result = mgr.get_skill_radar_data()
        assert result["status"] == "success"
        assert "data" in result
        assert "ADR" in result["data"]
        assert "Rating" in result["data"]
        # All radar values should be clipped to [-100, 100]
        for skill, val in result["data"].items():
            assert -100 <= val <= 100, f"{skill} radar value {val} out of range"

    def test_error_returns_status(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=250)
        # Force an error by breaking get_pro_baseline
        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.get_pro_baseline",
            side_effect=RuntimeError("baseline error"),
        ):
            result = mgr.get_skill_radar_data()
        assert result["status"] == "error"


class TestGetInteractiveOverlayData:
    """Tests for get_interactive_overlay_data."""

    def test_calibrating_returns_locked(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_coach_state(engine, total_matches=10)
        result = mgr.get_interactive_overlay_data(match_id=1)
        assert result["status"] == "calibrating"
        assert "locked" in result["message"].lower() or "10/200" in result["message"]


class TestFetchTrainingData:
    """Tests for _fetch_training_data."""

    def test_returns_only_matching_split_and_pro_flag(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        _seed_matches(engine, pro_count=10, user_count=5)
        mgr._assign_dataset_splits()
        train_pro = mgr._fetch_training_data(is_pro=True, split="train")
        train_user = mgr._fetch_training_data(is_pro=False, split="train")
        # All returned records should be pro or user respectively
        assert all(r.is_pro for r in train_pro)
        assert all(not r.is_pro for r in train_user)

    def test_empty_db_returns_empty_list(self, monkeypatch):
        mgr, _engine = _make_manager(monkeypatch)
        result = mgr._fetch_training_data(is_pro=True, split="train")
        assert result == []


class TestModuleLevelFunctions:
    """Tests for module-level helper functions."""

    def test_extract_feature_vector(self):
        """_extract_feature_vector extracts values in feature_names order."""

        class FakeP:
            def model_dump(self):
                return {"avg_kills": 20.0, "avg_adr": 85.0, "rating": 1.1}

        vec = _extract_feature_vector(FakeP(), ["avg_kills", "avg_adr", "rating"])
        assert vec == [20.0, 85.0, 1.1]

    def test_extract_feature_vector_missing_key_defaults_to_zero(self):
        class FakeP:
            def model_dump(self):
                return {"avg_kills": 20.0}

        vec = _extract_feature_vector(FakeP(), ["avg_kills", "missing_feature"])
        assert vec == [20.0, 0]

    def test_calculate_pro_mean(self):
        class FakeP:
            def __init__(self, kills, adr):
                self._data = {"avg_kills": kills, "avg_adr": adr}

            def model_dump(self):
                return self._data

        pro_raw = [FakeP(20.0, 80.0), FakeP(24.0, 90.0), FakeP(22.0, 85.0)]
        mean = _calculate_pro_mean(pro_raw, ["avg_kills", "avg_adr"])
        assert mean[0] == pytest.approx(22.0)
        assert mean[1] == pytest.approx(85.0)

    def test_apply_dynamic_window_targets(self):
        """_apply_dynamic_window_targets populates target_val and target_strat."""
        batch = {}
        window_ticks = [
            SimpleNamespace(round_outcome=1.0, equipment_value=5000),
            SimpleNamespace(round_outcome=0.0, equipment_value=3000),
            SimpleNamespace(round_outcome=1.0, equipment_value=4000),
        ]
        _apply_dynamic_window_targets(batch, window_ticks)

        assert "target_val" in batch
        assert "target_strat" in batch
        assert batch["target_val"].shape == (1, 1)
        assert batch["target_strat"].shape == (1, 10)
        # Mean of [1.0, 0.0, 1.0] = 0.667
        assert batch["target_val"].item() == pytest.approx(2 / 3, abs=0.01)
        # target_strat should be one-hot
        assert batch["target_strat"].sum().item() == pytest.approx(1.0)

    def test_apply_dynamic_window_targets_no_outcomes(self):
        """When no round_outcome data, should use 0.5 fallback."""
        batch = {}
        window_ticks = [
            SimpleNamespace(round_outcome=None, equipment_value=4000),
        ]
        _apply_dynamic_window_targets(batch, window_ticks)
        assert batch["target_val"].item() == pytest.approx(0.5)

    def test_apply_dynamic_window_targets_strat_index_clamped(self):
        """Equipment value > 10000 should not cause index out of bounds."""
        batch = {}
        window_ticks = [
            SimpleNamespace(round_outcome=1.0, equipment_value=15000),
        ]
        _apply_dynamic_window_targets(batch, window_ticks)
        # strat = 15000/10000 = 1.5, idx = min(int(1.5*9), 9) = 9
        assert batch["target_strat"][0, 9] == 1.0


class TestRunFullCycleGuards:
    """Tests for run_full_cycle edge cases (without executing actual training)."""

    def test_skips_when_prerequisites_fail(self, monkeypatch):
        mgr, engine = _make_manager(monkeypatch)
        # No data → prerequisites fail
        mock_sm = MagicMock()
        monkeypatch.setattr(
            "Programma_CS2_RENAN.backend.storage.state_manager.state_manager",
            mock_sm,
        )
        mgr.run_full_cycle()
        # Should have set status to Idle (not Running)
        mock_sm.update_status.assert_called()
        last_call = mock_sm.update_status.call_args_list[-1]
        assert last_call[0][1] == "Idle"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
