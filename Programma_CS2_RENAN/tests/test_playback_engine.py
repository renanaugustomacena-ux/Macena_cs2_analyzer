"""
Unit tests for the PlaybackEngine and DemoFrame data models.
"""

import sys


import pytest

from Programma_CS2_RENAN.core.demo_frame import DemoFrame, NadeState, NadeType, PlayerState, Team
from Programma_CS2_RENAN.core.playback_engine import InterpolatedPlayerState, PlaybackEngine


class TestDemoFrame:
    """Tests for the DemoFrame data models."""

    def test_player_state_creation(self):
        """Test PlayerState dataclass creation."""
        player = PlayerState(
            player_id=1,
            name="TestPlayer",
            team=Team.CT,
            x=100.0,
            y=200.0,
            z=0.0,
            yaw=90.0,
            hp=100,
            armor=100,
            is_alive=True,
            is_flashed=False,
            has_defuser=True,
            weapon="ak47",
            money=4500,
        )
        assert player.player_id == 1
        assert player.team == Team.CT
        assert player.is_alive is True

    def test_nade_state_smoke(self):
        """Test NadeState for smoke grenade."""
        smoke = NadeState(
            base_id=1,
            nade_type=NadeType.SMOKE,
            x=500.0,
            y=-300.0,
            z=0.0,
            starting_tick=100,
            ending_tick=500,
        )
        assert smoke.nade_type == NadeType.SMOKE

    def test_demo_frame_with_players(self):
        """Test DemoFrame with multiple players."""
        players = [
            PlayerState(
                player_id=i,
                name=f"Player{i}",
                team=Team.CT if i < 5 else Team.T,
                x=float(i * 100),
                y=float(i * 50),
                z=0.0,
                yaw=0.0,
                hp=100,
                armor=0,
                is_alive=True,
                is_flashed=False,
                has_defuser=False,
                weapon="ak47",
                money=800,
            )
            for i in range(10)
        ]
        frame = DemoFrame(
            tick=128, round_number=1, time_in_round=15.5, map_name="de_dust2", players=players
        )
        assert len(frame.players) == 10
        assert frame.tick == 128


class TestPlaybackEngine:
    """Tests for the PlaybackEngine."""

    def _create_test_frames(self, count: int = 100) -> list:
        """Helper to create a sequence of test frames."""
        frames = []
        for tick in range(count):
            players = [
                PlayerState(
                    player_id=0,
                    name="Tester",
                    team=Team.CT,
                    x=float(tick * 10),  # Moving player
                    y=float(tick * 5),
                    z=0.0,
                    yaw=float(tick % 360),
                    hp=100,
                    armor=0,
                    is_alive=True,
                    is_flashed=False,
                    has_defuser=False,
                    weapon="ak47",
                    money=4500,
                )
            ]
            frames.append(
                DemoFrame(
                    tick=tick,
                    round_number=1,
                    time_in_round=tick / 64.0,
                    map_name="de_dust2",
                    players=players,
                )
            )
        return frames

    def test_load_frames(self):
        """Test loading frames into the engine."""
        engine = PlaybackEngine()
        frames = self._create_test_frames(50)
        engine.load_frames(frames)
        assert engine.get_total_ticks() == 49  # Last tick index

    def test_seek_to_tick(self):
        """Test seeking to a specific tick."""
        engine = PlaybackEngine()
        frames = self._create_test_frames(100)
        engine.load_frames(frames)

        engine.seek_to_tick(50)
        assert engine.get_current_tick() == 50

    def test_speed_clamping(self):
        """Test speed is clamped to valid range."""
        engine = PlaybackEngine()
        engine.set_speed(100.0)
        assert engine._speed == 8.0  # Max clamp
        engine.set_speed(0.01)
        assert engine._speed == 0.25  # Min clamp

    def test_angle_interpolation_wrap(self):
        """Test angle interpolation handles 360 wraparound."""
        # From 350 to 10 at t=0.5: diff=-340 → +20 (via wrap) → 350+10=360
        result = PlaybackEngine._interpolate_angle(350, 10, 0.5)
        assert result == pytest.approx(360.0, abs=1.0)

    def test_interpolated_player_state(self):
        """Test the InterpolatedPlayerState creation."""
        state = InterpolatedPlayerState(
            player_id=1,
            name="Interp",
            team=Team.CT,
            x=150.5,
            y=275.3,
            z=0.0,
            yaw=45.0,
            hp=87,
            armor=100,
            is_alive=True,
            is_flashed=False,
            weapon="m4a1",
            money=16000,
            kills=0,
            deaths=0,
            assists=0,
            mvps=0,
        )
        assert state.hp == 87
        assert state.team == Team.CT
