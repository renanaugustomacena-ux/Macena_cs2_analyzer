"""
Tests for session_engine.py — Daemon lifecycle, zombie cleanup,
retraining triggers, meta-shift detection, and IPC.

CI-portable: uses in-memory SQLite with monkeypatched get_db_manager.
"""

import sys


import io
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from Programma_CS2_RENAN.backend.storage.db_models import (
    CoachState,
    IngestionTask,
    PlayerMatchStats,
)


# ---------------------------------------------------------------------------
# In-memory DB manager
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


# ===========================================================================
# _cleanup_zombie_tasks
# ===========================================================================


class TestCleanupZombieTasks:
    """Tests for _cleanup_zombie_tasks — reset stale 'processing' tasks."""

    def test_resets_old_processing_tasks(self, monkeypatch):
        from Programma_CS2_RENAN.core.session_engine import _cleanup_zombie_tasks

        engine = _make_engine()
        mock_db = _InMemoryDBManager(engine)
        monkeypatch.setattr(
            "Programma_CS2_RENAN.core.session_engine.get_db_manager", lambda: mock_db
        )

        # Create a zombie task (updated 10 minutes ago, still 'processing')
        with Session(engine) as session:
            session.add(
                IngestionTask(
                    demo_path="/old/demo.dem",
                    status="processing",
                    updated_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                )
            )
            session.commit()

        _cleanup_zombie_tasks()

        with Session(engine) as session:
            task = session.exec(select(IngestionTask)).first()
            assert task.status == "queued", "Zombie task should be reset to 'queued'"

    def test_does_not_reset_recent_processing_tasks(self, monkeypatch):
        from Programma_CS2_RENAN.core.session_engine import _cleanup_zombie_tasks

        engine = _make_engine()
        mock_db = _InMemoryDBManager(engine)
        monkeypatch.setattr(
            "Programma_CS2_RENAN.core.session_engine.get_db_manager", lambda: mock_db
        )

        # Create a legitimately-active task (updated 1 minute ago)
        with Session(engine) as session:
            session.add(
                IngestionTask(
                    demo_path="/active/demo.dem",
                    status="processing",
                    updated_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                )
            )
            session.commit()

        _cleanup_zombie_tasks()

        with Session(engine) as session:
            task = session.exec(select(IngestionTask)).first()
            assert task.status == "processing", "Active task should NOT be reset"

    def test_ignores_non_processing_tasks(self, monkeypatch):
        from Programma_CS2_RENAN.core.session_engine import _cleanup_zombie_tasks

        engine = _make_engine()
        mock_db = _InMemoryDBManager(engine)
        monkeypatch.setattr(
            "Programma_CS2_RENAN.core.session_engine.get_db_manager", lambda: mock_db
        )

        # Create old tasks that are NOT processing
        with Session(engine) as session:
            for status in ["queued", "completed", "failed"]:
                session.add(
                    IngestionTask(
                        demo_path=f"/{status}/demo.dem",
                        status=status,
                        updated_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                    )
                )
            session.commit()

        _cleanup_zombie_tasks()

        with Session(engine) as session:
            tasks = session.exec(select(IngestionTask)).all()
            for t in tasks:
                # None should be changed to 'queued' since they weren't 'processing'
                assert t.status in ("queued", "completed", "failed")

    def test_no_crash_on_empty_db(self, monkeypatch):
        from Programma_CS2_RENAN.core.session_engine import _cleanup_zombie_tasks

        engine = _make_engine()
        mock_db = _InMemoryDBManager(engine)
        monkeypatch.setattr(
            "Programma_CS2_RENAN.core.session_engine.get_db_manager", lambda: mock_db
        )
        _cleanup_zombie_tasks()  # Should not raise

    def test_multiple_zombies_all_reset(self, monkeypatch):
        from Programma_CS2_RENAN.core.session_engine import _cleanup_zombie_tasks

        engine = _make_engine()
        mock_db = _InMemoryDBManager(engine)
        monkeypatch.setattr(
            "Programma_CS2_RENAN.core.session_engine.get_db_manager", lambda: mock_db
        )

        with Session(engine) as session:
            for i in range(5):
                session.add(
                    IngestionTask(
                        demo_path=f"/zombie_{i}.dem",
                        status="processing",
                        updated_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                    )
                )
            session.commit()

        _cleanup_zombie_tasks()

        with Session(engine) as session:
            tasks = session.exec(select(IngestionTask)).all()
            assert all(t.status == "queued" for t in tasks)


# ===========================================================================
# _check_retraining_trigger
# ===========================================================================


class TestCheckRetrainingTrigger:
    """Tests for _check_retraining_trigger — threshold-based trigger."""

    def _setup(self, monkeypatch, pro_count=0, last_trained=0):
        from Programma_CS2_RENAN.core.session_engine import _check_retraining_trigger

        engine = _make_engine()
        mock_db = _InMemoryDBManager(engine)
        monkeypatch.setattr(
            "Programma_CS2_RENAN.core.session_engine.get_db_manager", lambda: mock_db
        )

        # Seed pro matches
        with Session(engine) as session:
            for i in range(pro_count):
                session.add(
                    PlayerMatchStats(
                        player_name=f"Pro{i}",
                        demo_name=f"pro_{i}.dem",
                        match_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                        is_pro=True,
                        avg_kills=20.0,
                        avg_deaths=16.0,
                        avg_adr=80.0,
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
            session.commit()

        # Mock state_manager
        mock_state = MagicMock()
        mock_state.last_trained_sample_count = last_trained
        mock_sm = MagicMock()
        mock_sm.get_state.return_value = mock_state
        monkeypatch.setattr(
            "Programma_CS2_RENAN.backend.storage.state_manager.state_manager",
            mock_sm,
        )

        return _check_retraining_trigger

    def test_triggers_when_initial_10_reached(self, monkeypatch):
        trigger = self._setup(monkeypatch, pro_count=10, last_trained=0)
        result = trigger()
        assert result == 10

    def test_triggers_with_any_pros_when_never_trained(self, monkeypatch):
        """When last_trained=0, even pro_count=5 triggers because 5 >= (0 * 1.10) = 0."""
        trigger = self._setup(monkeypatch, pro_count=5, last_trained=0)
        result = trigger()
        assert result == 5

    def test_triggers_on_10_percent_increase(self, monkeypatch):
        # Last trained on 100, now 111 → 11% increase → trigger
        trigger = self._setup(monkeypatch, pro_count=111, last_trained=100)
        result = trigger()
        assert result == 111

    def test_does_not_trigger_below_10_percent(self, monkeypatch):
        # Last trained on 100, now 105 → 5% increase → no trigger
        trigger = self._setup(monkeypatch, pro_count=105, last_trained=100)
        result = trigger()
        assert result == 0

    def test_zero_pro_count_returns_zero(self, monkeypatch):
        trigger = self._setup(monkeypatch, pro_count=0, last_trained=0)
        result = trigger()
        assert result == 0


# ===========================================================================
# _commit_trained_sample_count
# ===========================================================================


class TestCommitTrainedSampleCount:
    """Tests for _commit_trained_sample_count."""

    def test_updates_coach_state(self, monkeypatch):
        from Programma_CS2_RENAN.core.session_engine import _commit_trained_sample_count

        engine = _make_engine()
        mock_db = _InMemoryDBManager(engine)
        monkeypatch.setattr(
            "Programma_CS2_RENAN.core.session_engine.get_db_manager", lambda: mock_db
        )

        # Pre-create CoachState
        with Session(engine) as session:
            session.add(CoachState(last_trained_sample_count=50))
            session.commit()

        _commit_trained_sample_count(120)

        with Session(engine) as session:
            state = session.exec(select(CoachState)).first()
            assert state.last_trained_sample_count == 120

    def test_no_crash_when_no_coach_state(self, monkeypatch):
        from Programma_CS2_RENAN.core.session_engine import _commit_trained_sample_count

        engine = _make_engine()
        mock_db = _InMemoryDBManager(engine)
        monkeypatch.setattr(
            "Programma_CS2_RENAN.core.session_engine.get_db_manager", lambda: mock_db
        )

        # No CoachState → should not crash
        _commit_trained_sample_count(50)


# ===========================================================================
# _get_current_baseline_snapshot
# ===========================================================================


class TestGetBaselineSnapshot:
    """Tests for _get_current_baseline_snapshot."""

    def test_returns_empty_dict_on_error(self):
        from Programma_CS2_RENAN.core.session_engine import _get_current_baseline_snapshot

        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.TemporalBaselineDecay",
            side_effect=ImportError("not available"),
        ):
            result = _get_current_baseline_snapshot()
        assert result == {}

    def test_returns_baseline_when_available(self):
        from Programma_CS2_RENAN.core.session_engine import _get_current_baseline_snapshot

        mock_decay = MagicMock()
        mock_decay.return_value.get_temporal_baseline.return_value = {"avg_adr": 85.0}

        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.TemporalBaselineDecay",
            mock_decay,
        ):
            result = _get_current_baseline_snapshot()
        assert result == {"avg_adr": 85.0}


# ===========================================================================
# _check_meta_shift
# ===========================================================================


class TestCheckMetaShift:
    """Tests for _check_meta_shift."""

    def test_returns_new_baseline_when_available(self):
        from Programma_CS2_RENAN.core.session_engine import _check_meta_shift

        mock_decay_instance = MagicMock()
        mock_decay_instance.get_temporal_baseline.return_value = {"avg_adr": 90.0}
        mock_decay_instance.detect_meta_shift.return_value = []

        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.TemporalBaselineDecay",
            return_value=mock_decay_instance,
        ):
            result = _check_meta_shift({"avg_adr": 85.0})
        assert result == {"avg_adr": 90.0}

    def test_returns_old_baseline_on_error(self):
        from Programma_CS2_RENAN.core.session_engine import _check_meta_shift

        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.TemporalBaselineDecay",
            side_effect=RuntimeError("DB error"),
        ):
            old = {"avg_adr": 85.0}
            result = _check_meta_shift(old)
        assert result == old

    def test_detects_shifted_metrics(self):
        from Programma_CS2_RENAN.core.session_engine import _check_meta_shift

        mock_decay_instance = MagicMock()
        mock_decay_instance.get_temporal_baseline.return_value = {"avg_adr": 90.0}
        mock_decay_instance.detect_meta_shift.return_value = ["avg_adr", "rating"]

        with patch(
            "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline.TemporalBaselineDecay",
            return_value=mock_decay_instance,
        ):
            result = _check_meta_shift({"avg_adr": 80.0})
        # Should return new baseline even when shifts detected
        assert result == {"avg_adr": 90.0}


# ===========================================================================
# signal_work_available
# ===========================================================================


class TestSignalWorkAvailable:
    """Tests for signal_work_available — thread event signaling."""

    def test_sets_event(self):
        from Programma_CS2_RENAN.core.session_engine import (
            _work_available_event,
            signal_work_available,
        )

        _work_available_event.clear()
        assert not _work_available_event.is_set()

        signal_work_available()
        assert _work_available_event.is_set()

        # Cleanup
        _work_available_event.clear()


# ===========================================================================
# _monitor_stdin
# ===========================================================================


class TestMonitorStdin:
    """Tests for _monitor_stdin — IPC via stdin pipe."""

    def test_stop_command_sets_shutdown(self, monkeypatch):
        from Programma_CS2_RENAN.core.session_engine import (
            _monitor_stdin,
            _shutdown_event,
        )

        _shutdown_event.clear()

        # Mock stdin to return "STOP\n" then EOF
        mock_stdin = io.StringIO("STOP\n")
        monkeypatch.setattr("sys.stdin", mock_stdin)

        _monitor_stdin()
        assert _shutdown_event.is_set()

        # Cleanup
        _shutdown_event.clear()

    def test_eof_sets_shutdown(self, monkeypatch):
        from Programma_CS2_RENAN.core.session_engine import (
            _monitor_stdin,
            _shutdown_event,
        )

        _shutdown_event.clear()

        # Mock stdin to return EOF immediately
        mock_stdin = io.StringIO("")
        monkeypatch.setattr("sys.stdin", mock_stdin)

        _monitor_stdin()
        assert _shutdown_event.is_set()

        # Cleanup
        _shutdown_event.clear()


# ===========================================================================
# Constants
# ===========================================================================


class TestSessionEngineConstants:
    """Verify session engine constants are reasonable."""

    def test_zombie_threshold_is_positive(self):
        from Programma_CS2_RENAN.core.session_engine import _ZOMBIE_THRESHOLD_SECONDS

        assert _ZOMBIE_THRESHOLD_SECONDS > 0

    def test_zombie_threshold_is_reasonable(self):
        """Threshold should be between 1 min and 30 min."""
        from Programma_CS2_RENAN.core.session_engine import _ZOMBIE_THRESHOLD_SECONDS

        assert 60 <= _ZOMBIE_THRESHOLD_SECONDS <= 1800


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
