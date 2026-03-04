import sys
from datetime import datetime


import pytest

from Programma_CS2_RENAN.backend.storage.db_models import (
    CoachingInsight,
    CoachState,
    IngestionTask,
    PlayerMatchStats,
    PlayerProfile,
    PlayerTickState,
    ProPlayer,
    ProTeam,
    ServiceNotification,
)


class TestDBModels:
    def test_player_match_stats_defaults(self):
        stats = PlayerMatchStats(player_name="TestPlayer", demo_name="test.dem")
        assert stats.player_name == "TestPlayer"
        assert stats.avg_kast == 0.0
        assert stats.rating == 0.0
        assert isinstance(stats.processed_at, datetime)

    def test_player_tick_state_defaults(self):
        state = PlayerTickState(match_id=1, tick=128, player_name="TestPlayer")
        assert state.health == 0
        assert state.armor == 0
        assert state.pos_x == 0.0

    def test_player_profile_defaults(self):
        profile = PlayerProfile(player_name="TestUser")
        assert profile.role == "All-Rounder"
        assert profile.bio == "No description yet."

    def test_coaching_insight_creation(self):
        insight = CoachingInsight(
            player_name="TestUser",
            demo_name="test.dem",
            title="Good Aim",
            severity="INFO",
            message="Keep it up",
            focus_area="aim",
        )
        assert insight.severity == "INFO"
        assert insight.title == "Good Aim"
        assert insight.focus_area == "aim"
        assert insight.player_name == "TestUser"

    def test_ingestion_task_defaults(self):
        task = IngestionTask(demo_path="/path/to/demo.dem")
        assert task.status == "queued"
        assert task.retry_count == 0

    def test_coach_state_defaults(self):
        state = CoachState()
        assert state.status == "Paused"
        assert state.cpu_limit == 0.5
        assert state.pro_ingest_interval == 1.0

    def test_service_notification_defaults(self):
        note = ServiceNotification(daemon="hunter", message="Test")
        assert note.severity == "ERROR"
        assert note.is_read == False

    def test_pro_models(self):
        team = ProTeam(hltv_id=123, name="ProTeam")
        player = ProPlayer(hltv_id=456, nickname="ProPlayer", team_id=123)
        assert team.name == "ProTeam"
        assert player.nickname == "ProPlayer"
        assert player.team_id == 123

