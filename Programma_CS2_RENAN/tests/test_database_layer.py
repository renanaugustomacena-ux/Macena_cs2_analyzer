"""
Tests for Database Layer — Phase 3 Coverage Expansion.

Covers:
  DatabaseManager (database.py) — WAL mode, sessions, CRUD, upsert
  StateManager (state_manager.py) — daemon status, heartbeat, notifications
  StatCardAggregator (stat_aggregator.py) — pro player card persistence
"""

import sys


import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select


# ---------------------------------------------------------------------------
# DatabaseManager
# ---------------------------------------------------------------------------
class TestDatabaseManager:
    """Tests for the monolith database manager."""

    def _make_db_manager(self, tmp_path):
        """Create a DatabaseManager pointing to a temp file-based SQLite."""
        from Programma_CS2_RENAN.backend.storage.database import DatabaseManager

        db_file = tmp_path / "test_db.sqlite"
        url = f"sqlite:///{db_file}"
        with patch("Programma_CS2_RENAN.backend.storage.database.DATABASE_URL", url):
            return DatabaseManager()

    def test_create_db_and_tables(self, tmp_path):
        db = self._make_db_manager(tmp_path)
        db.create_db_and_tables()
        with db.get_session() as session:
            assert session is not None

    def test_get_session_yields_session(self, tmp_path):
        db = self._make_db_manager(tmp_path)
        db.create_db_and_tables()
        with db.get_session() as session:
            assert isinstance(session, Session)

    def test_get_session_commits_on_success(self, tmp_path):
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerProfile

        db = self._make_db_manager(tmp_path)
        db.create_db_and_tables()
        with db.get_session() as session:
            session.add(PlayerProfile(player_name="CommitTest", role="Entry"))
        with db.get_session() as session:
            result = session.exec(select(PlayerProfile)).first()
            assert result is not None
            assert result.player_name == "CommitTest"

    def test_get_session_rollbacks_on_error(self, tmp_path):
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerProfile

        db = self._make_db_manager(tmp_path)
        db.create_db_and_tables()
        try:
            with db.get_session() as session:
                session.add(PlayerProfile(player_name="RollbackTest", role="Entry"))
                raise ValueError("Forced error")
        except ValueError:
            pass
        with db.get_session() as session:
            result = session.exec(
                select(PlayerProfile).where(PlayerProfile.player_name == "RollbackTest")
            ).first()
            assert result is None

    def test_upsert_new_record(self, tmp_path):
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerProfile

        db = self._make_db_manager(tmp_path)
        db.create_db_and_tables()
        profile = PlayerProfile(player_name="UpsertNew", role="AWP")
        result = db.upsert(profile)
        assert result is not None

    def test_upsert_player_stats_new(self, tmp_path):
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

        db = self._make_db_manager(tmp_path)
        db.create_db_and_tables()
        stats = PlayerMatchStats(
            player_name="Tester", demo_name="test.dem",
            avg_kills=20.0, avg_deaths=15.0, avg_adr=80.0,
        )
        result = db.upsert(stats)
        assert result is not None
        with db.get_session() as session:
            found = session.exec(select(PlayerMatchStats)).first()
            assert found is not None
            assert found.player_name == "Tester"

    def test_upsert_player_stats_update(self, tmp_path):
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

        db = self._make_db_manager(tmp_path)
        db.create_db_and_tables()
        stats1 = PlayerMatchStats(
            player_name="Updater", demo_name="test.dem", avg_kills=10.0,
        )
        db.upsert(stats1)
        stats2 = PlayerMatchStats(
            player_name="Updater", demo_name="test.dem", avg_kills=25.0,
        )
        db.upsert(stats2)
        with db.get_session() as session:
            all_stats = session.exec(select(PlayerMatchStats)).all()
            assert len(all_stats) == 1
            assert all_stats[0].avg_kills == 25.0

    def test_get_existing_record(self, tmp_path):
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerProfile

        db = self._make_db_manager(tmp_path)
        db.create_db_and_tables()
        with db.get_session() as session:
            p = PlayerProfile(player_name="GetTest", role="Support")
            session.add(p)
            session.commit()
            session.refresh(p)
            pk = p.id
        result = db.get(PlayerProfile, pk)
        assert result is not None
        assert result.player_name == "GetTest"

    def test_get_nonexistent_returns_none(self, tmp_path):
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerProfile

        db = self._make_db_manager(tmp_path)
        db.create_db_and_tables()
        result = db.get(PlayerProfile, 99999)
        assert result is None


# ---------------------------------------------------------------------------
# StateManager
# ---------------------------------------------------------------------------
class TestStateManager:
    """Tests for centralized application state DAO."""

    def _make_state_manager(self):
        """Create a StateManager backed by an in-memory DB."""
        from Programma_CS2_RENAN.backend.storage.state_manager import StateManager

        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)

        from contextlib import contextmanager

        class InMemDB:
            def __init__(self):
                self.engine = engine

            @contextmanager
            def get_session(self, engine_key="default"):
                with Session(engine, expire_on_commit=False) as session:
                    try:
                        yield session
                        session.commit()
                    except Exception:
                        session.rollback()
                        raise

        sm = StateManager.__new__(StateManager)
        sm.db = InMemDB()
        sm._lock = __import__("threading").Lock()
        return sm

    def test_get_state_creates_default(self):
        sm = self._make_state_manager()
        state = sm.get_state()
        assert state is not None
        assert state.id is not None

    def test_get_state_returns_existing(self):
        sm = self._make_state_manager()
        s1 = sm.get_state()
        s2 = sm.get_state()
        assert s1.id == s2.id

    def test_update_status_hunter(self):
        sm = self._make_state_manager()
        sm.get_state()  # Ensure state exists
        sm.update_status("hunter", "Running", "Scanning HLTV")
        status = sm.get_status("hunter")
        assert status["status"] == "Running"

    def test_update_status_digester(self):
        sm = self._make_state_manager()
        sm.get_state()
        sm.update_status("digester", "Processing")
        status = sm.get_status("digester")
        assert status["status"] == "Processing"

    def test_update_status_teacher(self):
        sm = self._make_state_manager()
        sm.get_state()
        sm.update_status("teacher", "Training")
        status = sm.get_status("teacher")
        assert status["status"] == "Training"

    def test_update_status_global_valid(self):
        sm = self._make_state_manager()
        sm.get_state()
        sm.update_status("global", "Training")
        status = sm.get_status("global")
        assert status["status"] == "Training"

    def test_update_parsing_progress(self):
        from Programma_CS2_RENAN.backend.storage.db_models import CoachState

        sm = self._make_state_manager()
        sm.get_state()
        sm.update_parsing_progress(55.5)
        with sm.db.get_session() as session:
            state = session.exec(select(CoachState)).first()
            assert state.parsing_progress == 55.5

    def test_update_training_progress(self):
        from Programma_CS2_RENAN.backend.storage.db_models import CoachState

        sm = self._make_state_manager()
        sm.get_state()
        sm.update_training_progress(epoch=5, total_epochs=20, train_loss=0.45, val_loss=0.52, eta=120.0)
        with sm.db.get_session() as session:
            state = session.exec(select(CoachState)).first()
            assert state.current_epoch == 5
            assert state.total_epochs == 20
            assert abs(state.train_loss - 0.45) < 1e-5

    def test_heartbeat(self):
        from Programma_CS2_RENAN.backend.storage.db_models import CoachState

        sm = self._make_state_manager()
        sm.get_state()
        before = datetime.now(timezone.utc)
        sm.heartbeat()
        with sm.db.get_session() as session:
            state = session.exec(select(CoachState)).first()
            assert state.last_heartbeat is not None

    def test_set_error_creates_notification(self):
        from Programma_CS2_RENAN.backend.storage.db_models import ServiceNotification

        sm = self._make_state_manager()
        sm.get_state()
        sm.set_error("hunter", "Connection refused")
        with sm.db.get_session() as session:
            note = session.exec(select(ServiceNotification)).first()
            assert note is not None
            assert note.daemon == "hunter"
            assert note.severity == "ERROR"
            assert "Connection refused" in note.message

    def test_add_notification(self):
        from Programma_CS2_RENAN.backend.storage.db_models import ServiceNotification

        sm = self._make_state_manager()
        sm.add_notification("teacher", "INFO", "Training started")
        with sm.db.get_session() as session:
            note = session.exec(select(ServiceNotification)).first()
            assert note is not None
            assert note.daemon == "teacher"
            assert note.severity == "INFO"

    def test_get_status_unknown_daemon(self):
        sm = self._make_state_manager()
        sm.get_state()
        status = sm.get_status("unknown_daemon")
        assert status["status"] == "Unknown"

    def test_get_status_no_state(self):
        sm = self._make_state_manager()
        # Don't call get_state() — no CoachState row exists
        status = sm.get_status("hunter")
        assert status["status"] == "Unknown"


# ---------------------------------------------------------------------------
# StatCardAggregator
# ---------------------------------------------------------------------------
class TestStatCardAggregator:
    """Tests for pro player stat card persistence."""

    def _make_aggregator(self):
        """Create a StatCardAggregator backed by in-memory DB."""
        from Programma_CS2_RENAN.backend.storage.stat_aggregator import StatCardAggregator

        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)

        from contextlib import contextmanager

        class InMemDB:
            def __init__(self):
                self.engine = engine

            @contextmanager
            def get_session(self, engine_key="default"):
                with Session(engine, expire_on_commit=False) as session:
                    try:
                        yield session
                        session.commit()
                    except Exception:
                        session.rollback()
                        raise

        agg = StatCardAggregator.__new__(StatCardAggregator)
        agg.db = InMemDB()
        return agg, engine

    def test_persist_player_card_new(self):
        from Programma_CS2_RENAN.backend.storage.db_models import ProPlayer, ProPlayerStatCard

        agg, engine = self._make_aggregator()
        spider_data = {
            "player_id": 7998,
            "nickname": "s1mple",
            "core": {"rating_2_0": 1.30, "dpr": 0.62, "kast": 73.5, "impact": 1.30, "adr": 87.2, "kpr": 0.85},
        }
        agg.persist_player_card(spider_data)
        with Session(engine) as session:
            player = session.exec(select(ProPlayer).where(ProPlayer.hltv_id == 7998)).first()
            assert player is not None
            assert player.nickname == "s1mple"
            card = session.exec(
                select(ProPlayerStatCard).where(ProPlayerStatCard.player_id == 7998)
            ).first()
            assert card is not None
            assert abs(card.rating_2_0 - 1.30) < 1e-5
            assert abs(card.adr - 87.2) < 1e-1

    def test_persist_player_card_update(self):
        from Programma_CS2_RENAN.backend.storage.db_models import ProPlayerStatCard

        agg, engine = self._make_aggregator()
        spider_data = {
            "player_id": 7998, "nickname": "s1mple",
            "core": {"rating_2_0": 1.20},
        }
        agg.persist_player_card(spider_data)
        # Update with new rating
        spider_data["core"]["rating_2_0"] = 1.35
        agg.persist_player_card(spider_data)
        with Session(engine) as session:
            cards = session.exec(select(ProPlayerStatCard)).all()
            assert len(cards) == 1
            assert abs(cards[0].rating_2_0 - 1.35) < 1e-5

    def test_persist_player_card_missing_id(self):
        agg, _ = self._make_aggregator()
        # Should not crash, just log
        agg.persist_player_card({"nickname": "NoID"})
        agg.persist_player_card({"player_id": 123})

    def test_persist_team_new(self):
        from Programma_CS2_RENAN.backend.storage.db_models import ProTeam

        agg, engine = self._make_aggregator()
        agg.persist_team({"hltv_id": 4608, "name": "Natus Vincere", "world_rank": 1})
        with Session(engine) as session:
            team = session.exec(select(ProTeam).where(ProTeam.hltv_id == 4608)).first()
            assert team is not None
            assert team.name == "Natus Vincere"
            assert team.world_rank == 1

    def test_persist_team_update(self):
        from Programma_CS2_RENAN.backend.storage.db_models import ProTeam

        agg, engine = self._make_aggregator()
        agg.persist_team({"hltv_id": 4608, "name": "NaVi", "world_rank": 1})
        agg.persist_team({"hltv_id": 4608, "name": "NaVi", "world_rank": 3})
        with Session(engine) as session:
            teams = session.exec(select(ProTeam)).all()
            assert len(teams) == 1
            assert teams[0].world_rank == 3

    def test_persist_team_missing_data(self):
        agg, _ = self._make_aggregator()
        agg.persist_team({"name": "NoHltvId"})
        agg.persist_team({"hltv_id": 123})

    def test_core_stats_mapping(self):
        from Programma_CS2_RENAN.backend.storage.db_models import ProPlayerStatCard

        agg, engine = self._make_aggregator()
        core = {"rating_2_0": 1.15, "dpr": 0.70, "kast": 68.0, "impact": 1.10, "adr": 78.5, "kpr": 0.72}
        agg.persist_player_card({"player_id": 100, "nickname": "TestPro", "core": core})
        with Session(engine) as session:
            card = session.exec(select(ProPlayerStatCard)).first()
            assert abs(card.dpr - 0.70) < 1e-5
            assert abs(card.kast - 68.0) < 1e-1
            assert abs(card.impact - 1.10) < 1e-5
            assert abs(card.kpr - 0.72) < 1e-5
            blob = json.loads(card.detailed_stats_json)
            assert blob["nickname"] == "TestPro"
