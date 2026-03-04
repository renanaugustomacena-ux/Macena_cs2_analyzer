"""
Unit tests for TensorFactory — Player-POV Perception System.

Tests tensor generation in both Legacy mode (no PlayerKnowledge) and
Player-POV mode (with PlayerKnowledge), covering all three tensor types:
map, view, and motion.

All tests are CI-portable: no database, no real demo files, no GPU required.
"""

import sys
import threading


from types import SimpleNamespace

import numpy as np
import pytest
import torch

from Programma_CS2_RENAN.backend.processing.player_knowledge import (
    LastKnownEnemy,
    PlayerKnowledge,
    UtilityZone,
    VisibleEntity,
)
from Programma_CS2_RENAN.backend.processing.tensor_factory import (
    BOMB_MARKER_INTENSITY,
    BOMB_MARKER_RADIUS,
    MAX_SPEED_UNITS_PER_TICK,
    MAX_YAW_DELTA_DEG,
    TRAJECTORY_WINDOW,
    VELOCITY_FALLOFF_RADIUS,
    TensorConfig,
    TensorFactory,
    TrainingTensorConfig,
    get_tensor_factory,
)
from Programma_CS2_RENAN.core.spatial_data import MapMetadata


# ============ Helpers ============


def _make_tick(
    pos_x: float = 0.0,
    pos_y: float = 0.0,
    pos_z: float = 0.0,
    yaw: float = 0.0,
    team: str = "CT",
    tick: int = 0,
) -> SimpleNamespace:
    """Create a tick-like object for testing.

    Uses SimpleNamespace because TensorFactory reads attributes via getattr()
    with defaults, and PlayerTickState (SQLModel) does not have 'yaw' or 'team'
    columns — attempting to set them raises ValueError.
    """
    return SimpleNamespace(
        tick=tick,
        player_name="TestPlayer",
        demo_name="test.dem",
        pos_x=pos_x,
        pos_y=pos_y,
        pos_z=pos_z,
        view_x=yaw,
        view_y=0.0,
        yaw=yaw,
        team=team,
        health=100,
        armor=100,
        is_crouching=False,
        is_scoped=False,
        active_weapon="ak47",
        equipment_value=4750,
        enemies_visible=0,
        is_blinded=False,
    )


def _make_knowledge(
    own_x: float = 0.0,
    own_y: float = 0.0,
    teammates: list | None = None,
    visible_enemies: list | None = None,
    last_known_enemies: list | None = None,
    utility_zones: list | None = None,
    bomb_planted: bool = False,
    bomb_x: float = 0.0,
    bomb_y: float = 0.0,
) -> PlayerKnowledge:
    """Create a PlayerKnowledge instance for testing."""
    return PlayerKnowledge(
        own_pos_x=own_x,
        own_pos_y=own_y,
        own_yaw=90.0,
        teammate_positions=teammates or [],
        visible_enemies=visible_enemies or [],
        last_known_enemies=last_known_enemies or [],
        utility_zones=utility_zones or [],
        bomb_planted=bomb_planted,
        bomb_pos_x=bomb_x,
        bomb_pos_y=bomb_y,
    )


# Known map metadata for deterministic coordinate tests.
# de_mirage: pos_x=-3230, pos_y=1713, scale=5.0
MIRAGE_META = MapMetadata(pos_x=-3230, pos_y=1713, scale=5.0)


# ============ TensorConfig / TrainingTensorConfig ============


class TestTensorConfig:
    """Test configuration dataclasses."""

    def test_default_values(self):
        """TensorConfig has correct defaults."""
        cfg = TensorConfig()
        assert cfg.map_resolution == 128
        assert cfg.view_resolution == 224
        assert cfg.sigma == 3.0
        assert cfg.fov_degrees == 90.0
        assert cfg.view_distance == 2000.0

    def test_custom_values(self):
        """TensorConfig accepts custom values."""
        cfg = TensorConfig(map_resolution=64, view_resolution=64, sigma=0.0)
        assert cfg.map_resolution == 64
        assert cfg.view_resolution == 64
        assert cfg.sigma == 0.0

    def test_training_config_defaults(self):
        """TrainingTensorConfig uses smaller resolutions for training efficiency."""
        cfg = TrainingTensorConfig()
        assert cfg.map_resolution == 64
        assert cfg.view_resolution == 64
        assert cfg.sigma == 3.0  # Inherited from TensorConfig

    def test_training_config_inherits(self):
        """TrainingTensorConfig inherits all TensorConfig fields."""
        cfg = TrainingTensorConfig()
        assert hasattr(cfg, "fov_degrees")
        assert hasattr(cfg, "view_distance")
        assert cfg.fov_degrees == 90.0


# ============ TensorFactory Initialization ============


class TestTensorFactoryInit:
    """Test factory instantiation."""

    def test_default_config(self):
        """TensorFactory uses default config when none provided."""
        factory = TensorFactory()
        assert factory.config.map_resolution == 128
        assert factory.config.view_resolution == 224

    def test_custom_config(self):
        """TensorFactory accepts custom config."""
        cfg = TrainingTensorConfig()
        factory = TensorFactory(config=cfg)
        assert factory.config.map_resolution == 64
        assert factory.config.view_resolution == 64


# ============ generate_map_tensor — Legacy Mode ============


class TestMapTensorLegacy:
    """Test map tensor generation in legacy mode (no PlayerKnowledge)."""

    @pytest.fixture
    def factory(self):
        return TensorFactory(config=TensorConfig(map_resolution=32, sigma=0.0))

    def test_empty_ticks_returns_zeros(self, factory):
        """Empty tick list produces zero tensor."""
        result = factory.generate_map_tensor([], map_name="de_mirage")
        assert result.shape == (3, 32, 32)
        assert torch.all(result == 0)

    def test_output_shape(self, factory):
        """Map tensor has shape (3, res, res)."""
        ticks = [_make_tick(pos_x=-3230, pos_y=1713)]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage")
        assert result.shape == (3, 32, 32)
        assert result.dtype == torch.float32

    def test_unknown_map_returns_zeros(self, factory):
        """Unknown map name returns zero tensor (get_map_metadata returns None)."""
        ticks = [_make_tick()]
        result = factory.generate_map_tensor(ticks, map_name="de_nonexistent_map_xyz")
        assert result.shape == (3, 32, 32)
        assert torch.all(result == 0)

    def test_single_tick_player_channel(self, factory):
        """Single tick populates the player position channel (Ch2)."""
        # Position inside de_mirage bounds (not at exact edge which falls out-of-grid)
        ticks = [_make_tick(pos_x=-2000.0, pos_y=800.0, team="CT")]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage")
        # Player channel (Ch2) should have at least one non-zero pixel
        assert result[2].max() > 0, "Player channel should contain the player marker"

    def test_values_in_valid_range(self, factory):
        """All output values in [0, 1] after normalization."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=500, team="CT"),
            _make_tick(pos_x=-1800, pos_y=600, team="T"),
        ]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage")
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_no_nan_or_inf(self, factory):
        """Output contains no NaN or Inf values."""
        ticks = [_make_tick(pos_x=-2000, pos_y=500)]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage")
        assert not torch.isnan(result).any()
        assert not torch.isinf(result).any()

    def test_multiple_ticks_accumulate(self, factory):
        """Multiple ticks accumulate on enemy/team channels."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, team="CT"),
            _make_tick(pos_x=-2100, pos_y=900, team="CT"),
            _make_tick(pos_x=-2200, pos_y=1000, team="CT"),
        ]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage")
        # All same team → team channel (Ch1) should have signal
        assert result[1].max() > 0, "Team channel should have accumulated positions"


# ============ generate_map_tensor — POV Mode ============


class TestMapTensorPOV:
    """Test map tensor generation in Player-POV mode (with PlayerKnowledge)."""

    @pytest.fixture
    def factory(self):
        return TensorFactory(config=TensorConfig(map_resolution=32, sigma=0.0))

    def test_teammate_channel(self, factory):
        """Ch0 contains teammate positions."""
        teammates = [VisibleEntity(pos_x=-2000, pos_y=800, pos_z=0, distance=500, is_teammate=True)]
        knowledge = _make_knowledge(own_x=-2500, own_y=1000, teammates=teammates)
        ticks = [_make_tick(pos_x=-2500, pos_y=1000)]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage", knowledge=knowledge)
        assert result[0].max() > 0, "Teammate channel should have signal"

    def test_visible_enemy_channel(self, factory):
        """Ch1 contains visible enemy positions."""
        enemies = [VisibleEntity(pos_x=-1500, pos_y=500, pos_z=0, distance=800, is_teammate=False)]
        knowledge = _make_knowledge(own_x=-2500, own_y=1000, visible_enemies=enemies)
        ticks = [_make_tick(pos_x=-2500, pos_y=1000)]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage", knowledge=knowledge)
        assert result[1].max() > 0, "Enemy channel should have visible enemy"

    def test_last_known_enemy_decayed(self, factory):
        """Ch1 contains last-known enemy with decayed intensity."""
        last_known = [LastKnownEnemy(pos_x=-1500, pos_y=500, pos_z=0, decay_factor=0.5)]
        knowledge = _make_knowledge(own_x=-2500, own_y=1000, last_known_enemies=last_known)
        ticks = [_make_tick(pos_x=-2500, pos_y=1000)]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage", knowledge=knowledge)
        assert result[1].max() > 0, "Enemy channel should have decayed last-known enemy"

    def test_utility_zone_channel(self, factory):
        """Ch2 contains utility zones."""
        zones = [UtilityZone(pos_x=-2000, pos_y=800, pos_z=0, radius=200.0, utility_type="smoke")]
        knowledge = _make_knowledge(own_x=-2500, own_y=1000, utility_zones=zones)
        ticks = [_make_tick(pos_x=-2500, pos_y=1000)]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage", knowledge=knowledge)
        assert result[2].max() > 0, "Utility channel should have smoke zone"

    def test_bomb_marker(self, factory):
        """Ch2 contains bomb marker when bomb is planted."""
        knowledge = _make_knowledge(
            own_x=-2500, own_y=1000, bomb_planted=True, bomb_x=-1500, bomb_y=500
        )
        ticks = [_make_tick(pos_x=-2500, pos_y=1000)]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage", knowledge=knowledge)
        assert result[2].max() > 0, "Utility channel should have bomb marker"

    def test_empty_knowledge_produces_zeros(self, factory):
        """Empty PlayerKnowledge (no entities) produces all-zero channels."""
        knowledge = _make_knowledge(own_x=-2500, own_y=1000)
        ticks = [_make_tick(pos_x=-2500, pos_y=1000)]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage", knowledge=knowledge)
        # Ch0 should still have own position marker
        assert result[0].max() > 0, "Own position should always be marked on teammate channel"
        # Ch1 (enemies) and Ch2 (utility) should be zero
        assert result[1].max() == 0, "No enemies → enemy channel should be zero"
        assert result[2].max() == 0, "No utility → utility channel should be zero"


# ============ generate_view_tensor — Legacy Mode ============


class TestViewTensorLegacy:
    """Test view tensor generation in legacy mode."""

    @pytest.fixture
    def factory(self):
        return TensorFactory(config=TensorConfig(view_resolution=32, sigma=0.0))

    def test_empty_ticks_returns_zeros(self, factory):
        """Empty tick list produces zero tensor."""
        result = factory.generate_view_tensor([], map_name="de_mirage")
        assert result.shape == (3, 32, 32)
        assert torch.all(result == 0)

    def test_output_shape(self, factory):
        """View tensor has shape (3, view_res, view_res)."""
        ticks = [_make_tick(pos_x=-2000, pos_y=800)]
        result = factory.generate_view_tensor(ticks, map_name="de_mirage")
        assert result.shape == (3, 32, 32)
        assert result.dtype == torch.float32

    def test_fov_mask_channel_nonzero(self, factory):
        """Ch0 (FOV mask) has non-zero pixels when tick position is on map."""
        ticks = [_make_tick(pos_x=-2000, pos_y=800, yaw=45.0)]
        result = factory.generate_view_tensor(ticks, map_name="de_mirage")
        assert result[0].max() > 0, "FOV mask should have non-zero pixels"

    def test_danger_zone_channel(self, factory):
        """Ch1 (danger zone) contains areas NOT covered by FOV."""
        ticks = [_make_tick(pos_x=-2000, pos_y=800, yaw=90.0)]
        result = factory.generate_view_tensor(ticks, map_name="de_mirage")
        # Danger zone = 1 - accumulated_fov → should be non-zero outside FOV cone
        assert result[1].max() > 0, "Danger zone should exist outside FOV"

    def test_values_in_valid_range(self, factory):
        """All values in [0, 1]."""
        ticks = [_make_tick(pos_x=-2000, pos_y=800, yaw=180.0)]
        result = factory.generate_view_tensor(ticks, map_name="de_mirage")
        assert result.min() >= 0.0
        assert result.max() <= 1.0 + 1e-6  # Small epsilon for float rounding

    def test_multiple_ticks_reduce_danger(self, factory):
        """More ticks covering different angles should reduce danger zone."""
        tick1 = _make_tick(pos_x=-2000, pos_y=800, yaw=0.0, tick=1)
        tick2 = _make_tick(pos_x=-2000, pos_y=800, yaw=90.0, tick=2)
        tick3 = _make_tick(pos_x=-2000, pos_y=800, yaw=180.0, tick=3)

        result_one = factory.generate_view_tensor([tick1], map_name="de_mirage")
        result_multi = factory.generate_view_tensor([tick1, tick2, tick3], map_name="de_mirage")

        danger_one = result_one[1].sum().item()
        danger_multi = result_multi[1].sum().item()
        assert danger_multi <= danger_one, "More FOV coverage should reduce danger zone"


# ============ generate_view_tensor — POV Mode ============


class TestViewTensorPOV:
    """Test view tensor generation in Player-POV mode."""

    @pytest.fixture
    def factory(self):
        return TensorFactory(config=TensorConfig(view_resolution=32, sigma=0.0))

    def test_entity_channel_with_visible_enemies(self, factory):
        """Ch1 contains visible enemies in POV mode."""
        enemies = [VisibleEntity(pos_x=-1500, pos_y=500, pos_z=0, distance=300, is_teammate=False)]
        knowledge = _make_knowledge(own_x=-2000, own_y=800, visible_enemies=enemies)
        ticks = [_make_tick(pos_x=-2000, pos_y=800)]
        result = factory.generate_view_tensor(ticks, map_name="de_mirage", knowledge=knowledge)
        assert result[1].max() > 0, "Entity channel should show visible enemies"

    def test_entity_channel_with_teammates(self, factory):
        """Ch1 contains teammates (dimmed) in POV mode."""
        teammates = [VisibleEntity(pos_x=-1800, pos_y=700, pos_z=0, distance=200, is_teammate=True)]
        knowledge = _make_knowledge(own_x=-2000, own_y=800, teammates=teammates)
        ticks = [_make_tick(pos_x=-2000, pos_y=800)]
        result = factory.generate_view_tensor(ticks, map_name="de_mirage", knowledge=knowledge)
        assert result[1].max() > 0, "Entity channel should show teammates"

    def test_utility_channel(self, factory):
        """Ch2 contains utility zones in POV mode."""
        zones = [UtilityZone(pos_x=-1800, pos_y=600, pos_z=0, radius=200.0, utility_type="molotov")]
        knowledge = _make_knowledge(own_x=-2000, own_y=800, utility_zones=zones)
        ticks = [_make_tick(pos_x=-2000, pos_y=800)]
        result = factory.generate_view_tensor(ticks, map_name="de_mirage", knowledge=knowledge)
        assert result[2].max() > 0, "Utility channel should show molotov zone"


# ============ generate_motion_tensor ============


class TestMotionTensor:
    """Test motion tensor generation."""

    @pytest.fixture
    def factory(self):
        return TensorFactory(config=TensorConfig(view_resolution=32, sigma=0.0))

    def test_single_tick_returns_zeros(self, factory):
        """< 2 ticks produces zero tensor."""
        result = factory.generate_motion_tensor([_make_tick()], map_name="de_mirage")
        assert result.shape == (3, 32, 32)
        assert torch.all(result == 0)

    def test_empty_ticks_returns_zeros(self, factory):
        """Empty tick list produces zero tensor."""
        result = factory.generate_motion_tensor([], map_name="de_mirage")
        assert result.shape == (3, 32, 32)
        assert torch.all(result == 0)

    def test_output_shape(self, factory):
        """Motion tensor has shape (3, view_res, view_res)."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, yaw=0.0, tick=1),
            _make_tick(pos_x=-1998, pos_y=802, yaw=5.0, tick=2),
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_mirage")
        assert result.shape == (3, 32, 32)
        assert result.dtype == torch.float32

    def test_stationary_player_zero_velocity(self, factory):
        """Stationary player: velocity channel (Ch1) should be ~zero."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, yaw=90.0, tick=1),
            _make_tick(pos_x=-2000, pos_y=800, yaw=90.0, tick=2),
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_mirage")
        assert result[1].max() < 0.02, "Stationary player should have ~zero velocity"

    def test_moving_player_nonzero_velocity(self, factory):
        """Moving player: velocity channel (Ch1) should have signal."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, tick=1),
            _make_tick(pos_x=-1996, pos_y=800, tick=2),  # 4 units = max speed
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_mirage")
        assert result[1].max() > 0.5, "Moving player should have velocity signal"

    def test_stationary_crosshair_zero(self, factory):
        """Stationary crosshair: Ch2 should be ~zero."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, yaw=90.0, tick=1),
            _make_tick(pos_x=-1998, pos_y=802, yaw=90.0, tick=2),
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_mirage")
        assert result[2].max() < 0.02, "No yaw change → crosshair channel should be ~zero"

    def test_flick_crosshair_nonzero(self, factory):
        """Large yaw delta (flick): Ch2 should have bright signal."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, yaw=0.0, tick=1),
            _make_tick(pos_x=-1998, pos_y=800, yaw=45.0, tick=2),  # 45° flick = max
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_mirage")
        assert result[2].max() > 0, "Flick yaw should produce crosshair signal"

    def test_trajectory_channel_with_many_ticks(self, factory):
        """Trajectory channel (Ch0) plots recent positions."""
        ticks = [
            _make_tick(pos_x=-2000 + i * 10, pos_y=800, tick=i)
            for i in range(10)
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_mirage")
        assert result[0].max() > 0, "Trajectory channel should have trail"

    def test_no_nan_or_inf(self, factory):
        """Output contains no NaN or Inf values."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, yaw=0.0, tick=1),
            _make_tick(pos_x=-1990, pos_y=810, yaw=30.0, tick=2),
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_mirage")
        assert not torch.isnan(result).any()
        assert not torch.isinf(result).any()

    def test_values_in_valid_range(self, factory):
        """All values in [0, 1] (or [-1, 1] for legacy velocity)."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, yaw=10.0, tick=1),
            _make_tick(pos_x=-1997, pos_y=803, yaw=25.0, tick=2),
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_mirage")
        assert result.min() >= 0.0
        assert result.max() <= 1.0 + 1e-6


# ============ Legacy Motion (no map metadata) ============


class TestLegacyMotion:
    """Test legacy motion tensor when map metadata is unavailable."""

    @pytest.fixture
    def factory(self):
        return TensorFactory(config=TensorConfig(view_resolution=32))

    def test_unknown_map_uses_legacy(self, factory):
        """Unknown map falls back to legacy motion encoding."""
        ticks = [
            _make_tick(pos_x=100, pos_y=200, tick=1),
            _make_tick(pos_x=102, pos_y=201, tick=2),
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_nonexistent_map_xyz")
        assert result.shape == (3, 32, 32)
        # Legacy mode: uniform channels
        # Ch0 = norm_dx (uniform), Ch1 = norm_dy (uniform), Ch2 = speed (uniform)
        # Each channel should have a single uniform value
        ch0_vals = result[0].unique()
        assert len(ch0_vals) == 1, "Legacy Ch0 should be uniform"

    def test_legacy_values_range(self, factory):
        """Legacy motion values in [-1, 1] for velocity, [0, 1] for magnitude."""
        ticks = [
            _make_tick(pos_x=0, pos_y=0, tick=1),
            _make_tick(pos_x=3.0, pos_y=-2.0, tick=2),
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_nonexistent_map_xyz")
        assert result[0].min() >= -1.0  # dx channel
        assert result[0].max() <= 1.0
        assert result[1].min() >= -1.0  # dy channel
        assert result[1].max() <= 1.0
        assert result[2].min() >= 0.0  # magnitude channel
        assert result[2].max() <= 1.0

    def test_stationary_legacy(self, factory):
        """Stationary player in legacy mode → all zeros."""
        ticks = [
            _make_tick(pos_x=100, pos_y=200, tick=1),
            _make_tick(pos_x=100, pos_y=200, tick=2),
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_nonexistent_map_xyz")
        assert torch.all(result == 0), "Stationary player → zero motion"


# ============ generate_all_tensors ============


class TestGenerateAllTensors:
    """Test the combined tensor generation."""

    @pytest.fixture
    def factory(self):
        return TensorFactory(config=TensorConfig(map_resolution=16, view_resolution=16, sigma=0.0))

    def test_returns_dict_with_correct_keys(self, factory):
        """Returns dict with 'map', 'view', 'motion' keys."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, tick=1),
            _make_tick(pos_x=-1998, pos_y=802, tick=2),
        ]
        result = factory.generate_all_tensors(ticks, map_name="de_mirage")
        assert isinstance(result, dict)
        assert set(result.keys()) == {"map", "view", "motion"}

    def test_tensor_shapes(self, factory):
        """All tensors have 3-channel shape with correct resolution."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, tick=1),
            _make_tick(pos_x=-1998, pos_y=802, tick=2),
        ]
        result = factory.generate_all_tensors(ticks, map_name="de_mirage")
        assert result["map"].shape == (3, 16, 16)
        assert result["view"].shape == (3, 16, 16)
        assert result["motion"].shape == (3, 16, 16)

    def test_all_tensors_with_knowledge(self, factory):
        """POV mode produces non-zero map and view tensors."""
        enemies = [VisibleEntity(pos_x=-1500, pos_y=500, pos_z=0, distance=800, is_teammate=False)]
        knowledge = _make_knowledge(own_x=-2000, own_y=800, visible_enemies=enemies)
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, tick=1),
            _make_tick(pos_x=-1998, pos_y=802, tick=2),
        ]
        result = factory.generate_all_tensors(ticks, map_name="de_mirage", knowledge=knowledge)
        assert result["map"].max() > 0, "POV map should have signal"
        assert result["view"].max() > 0, "POV view should have signal"

    def test_empty_ticks(self, factory):
        """Empty ticks → all zero tensors."""
        result = factory.generate_all_tensors([], map_name="de_mirage")
        for key in ("map", "view", "motion"):
            assert torch.all(result[key] == 0), f"{key} tensor should be zero for empty ticks"


# ============ Private Helper: _world_to_grid ============


class TestWorldToGrid:
    """Test coordinate conversion from world space to grid space."""

    def test_origin_maps_correctly(self):
        """Map origin (top-left in world) maps to grid (0, res)."""
        factory = TensorFactory()
        meta = MapMetadata(pos_x=-3230, pos_y=1713, scale=5.0)
        gx, gy = factory._world_to_grid(-3230, 1713, meta, 128)
        assert gx == 0, "Map origin X should map to grid 0"
        # Y is flipped: ny = (1713 - 1713)/(5.0*1024) = 0, gy = int((1-0)*128) = 128
        assert gy == 128, f"Map origin Y should map to grid {128}"

    def test_center_maps_to_center(self):
        """Mid-point of the map should map near grid center."""
        factory = TensorFactory()
        # Map spans: x = [-3230, -3230 + 5*1024] = [-3230, 1890]
        # Map spans: y = [1713 - 5*1024, 1713] = [-3407, 1713]
        # Center world: x = (-3230+1890)/2 = -670, y = (-3407+1713)/2 = -847
        meta = MapMetadata(pos_x=-3230, pos_y=1713, scale=5.0)
        mid_x = (-3230 + (-3230 + 5.0 * 1024)) / 2
        mid_y = (1713 + (1713 - 5.0 * 1024)) / 2
        gx, gy = factory._world_to_grid(mid_x, mid_y, meta, 128)
        assert 55 <= gx <= 75, f"Center X should be near 64, got {gx}"
        assert 55 <= gy <= 75, f"Center Y should be near 64, got {gy}"

    def test_out_of_bounds_negative(self):
        """Coordinates far outside map return negative grid values."""
        factory = TensorFactory()
        meta = MapMetadata(pos_x=0, pos_y=0, scale=1.0)
        gx, gy = factory._world_to_grid(-5000, 5000, meta, 64)
        assert gx < 0, "Negative world x should produce negative grid x"


# ============ Private Helper: _normalize ============


class TestNormalize:
    """Test array normalization."""

    def test_zero_array_unchanged(self):
        """All-zero array stays zero (no division by zero)."""
        factory = TensorFactory()
        arr = np.zeros((10, 10), dtype=np.float32)
        result = factory._normalize(arr)
        assert np.all(result == 0)

    def test_positive_array_scaled_to_one(self):
        """Max value becomes 1.0."""
        factory = TensorFactory()
        arr = np.array([[0.0, 5.0], [2.5, 10.0]], dtype=np.float32)
        result = factory._normalize(arr)
        assert result.max() == pytest.approx(1.0)
        assert result[0, 0] == pytest.approx(0.0)
        assert result[0, 1] == pytest.approx(0.5)

    def test_single_value_array(self):
        """Array with single non-zero value normalizes to 1.0."""
        factory = TensorFactory()
        arr = np.zeros((4, 4), dtype=np.float32)
        arr[2, 3] = 42.0
        result = factory._normalize(arr)
        assert result[2, 3] == pytest.approx(1.0)


# ============ Private Helper: _generate_fov_mask ============


class TestFOVMask:
    """Test field-of-view mask generation."""

    @pytest.fixture
    def factory(self):
        return TensorFactory(config=TensorConfig(
            view_resolution=32,
            fov_degrees=90.0,
            view_distance=2000.0,
            sigma=0.0,
        ))

    def test_output_shape(self, factory):
        """FOV mask has shape (resolution, resolution)."""
        meta = MapMetadata(pos_x=-3230, pos_y=1713, scale=5.0)
        mask = factory._generate_fov_mask(-2000, 800, 90.0, meta, 32)
        assert mask.shape == (32, 32)

    def test_fov_covers_forward_direction(self, factory):
        """FOV mask should have non-zero pixels in the look direction."""
        meta = MapMetadata(pos_x=-3230, pos_y=1713, scale=5.0)
        mask = factory._generate_fov_mask(-2000, 800, 0.0, meta, 32)
        assert mask.max() > 0, "FOV mask should cover some area"

    def test_fov_mask_values_range(self, factory):
        """All FOV mask values in [0, 1]."""
        meta = MapMetadata(pos_x=-3230, pos_y=1713, scale=5.0)
        mask = factory._generate_fov_mask(-2000, 800, 45.0, meta, 32)
        assert mask.min() >= 0.0
        assert mask.max() <= 1.0 + 1e-6


# ============ Private Helper: _draw_circle ============


class TestDrawCircle:
    """Test circle drawing on channels."""

    def test_circle_modifies_channel(self):
        """Drawing a circle adds non-zero values."""
        factory = TensorFactory()
        meta = MapMetadata(pos_x=-3230, pos_y=1713, scale=5.0)
        channel = np.zeros((64, 64), dtype=np.float32)
        factory._draw_circle(channel, -2000, 800, 200.0, meta, 64)
        assert channel.max() > 0, "Circle should add values to channel"

    def test_circle_default_intensity(self):
        """Default intensity is 1.0."""
        factory = TensorFactory()
        meta = MapMetadata(pos_x=-3230, pos_y=1713, scale=5.0)
        channel = np.zeros((64, 64), dtype=np.float32)
        factory._draw_circle(channel, -2000, 800, 200.0, meta, 64)
        assert channel.max() == pytest.approx(1.0)

    def test_circle_custom_intensity(self):
        """Custom intensity is respected."""
        factory = TensorFactory()
        meta = MapMetadata(pos_x=-3230, pos_y=1713, scale=5.0)
        channel = np.zeros((64, 64), dtype=np.float32)
        factory._draw_circle(channel, -2000, 800, 200.0, meta, 64, intensity=0.5)
        assert channel.max() == pytest.approx(0.5)


# ============ Singleton: get_tensor_factory ============


class TestSingleton:
    """Test the singleton accessor."""

    def test_returns_tensor_factory(self):
        """get_tensor_factory returns a TensorFactory instance."""
        import Programma_CS2_RENAN.backend.processing.tensor_factory as tf_module

        # Reset singleton for clean test
        tf_module._factory_instance = None
        factory = get_tensor_factory()
        assert isinstance(factory, TensorFactory)

    def test_same_instance(self):
        """Repeated calls return the same instance."""
        import Programma_CS2_RENAN.backend.processing.tensor_factory as tf_module

        tf_module._factory_instance = None
        f1 = get_tensor_factory()
        f2 = get_tensor_factory()
        assert f1 is f2

    def test_thread_safety(self):
        """Concurrent calls all get the same instance."""
        import Programma_CS2_RENAN.backend.processing.tensor_factory as tf_module

        tf_module._factory_instance = None
        instances = []
        errors = []

        def get_instance():
            try:
                instances.append(get_tensor_factory())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Thread errors: {errors}"
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances), "All threads should get same instance"


# ============ Gaussian Blur (sigma > 0) ============


class TestGaussianBlur:
    """Test that gaussian blur is applied when sigma > 0."""

    def test_blur_applied_map_tensor(self):
        """Map tensor with sigma > 0 produces smoother output than sigma = 0."""
        ticks = [_make_tick(pos_x=-2000, pos_y=800, team="CT")]

        factory_no_blur = TensorFactory(config=TensorConfig(map_resolution=32, sigma=0.0))
        factory_blur = TensorFactory(config=TensorConfig(map_resolution=32, sigma=2.0))

        result_no_blur = factory_no_blur.generate_map_tensor(ticks, map_name="de_mirage")
        result_blur = factory_blur.generate_map_tensor(ticks, map_name="de_mirage")

        # Blurred result should have more non-zero pixels (spread)
        nnz_no_blur = (result_no_blur[2] > 0.01).sum().item()
        nnz_blur = (result_blur[2] > 0.01).sum().item()
        assert nnz_blur >= nnz_no_blur, "Blur should spread signal to more pixels"


# ============ Resolution Independence ============


class TestResolutionIndependence:
    """Test that tensor generation works at different resolutions."""

    @pytest.mark.parametrize("map_res,view_res", [(16, 16), (32, 32), (64, 64), (128, 128)])
    def test_various_resolutions(self, map_res, view_res):
        """Tensors are generated correctly at various resolutions."""
        cfg = TensorConfig(map_resolution=map_res, view_resolution=view_res, sigma=0.0)
        factory = TensorFactory(config=cfg)
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, tick=1),
            _make_tick(pos_x=-1998, pos_y=802, tick=2),
        ]
        result = factory.generate_all_tensors(ticks, map_name="de_mirage")
        assert result["map"].shape == (3, map_res, map_res)
        assert result["view"].shape == (3, view_res, view_res)
        assert result["motion"].shape == (3, view_res, view_res)


# ============ Edge Cases ============


class TestEdgeCases:
    """Test boundary and edge conditions."""

    @pytest.fixture
    def factory(self):
        return TensorFactory(config=TensorConfig(map_resolution=16, view_resolution=16, sigma=0.0))

    def test_extreme_coordinates(self, factory):
        """Very large world coordinates don't crash (out-of-grid silently ignored)."""
        ticks = [_make_tick(pos_x=99999, pos_y=99999)]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage")
        assert result.shape == (3, 16, 16)
        assert not torch.isnan(result).any()

    def test_negative_coordinates(self, factory):
        """Negative coordinates outside map bounds handled gracefully."""
        ticks = [_make_tick(pos_x=-99999, pos_y=-99999)]
        result = factory.generate_map_tensor(ticks, map_name="de_mirage")
        assert result.shape == (3, 16, 16)
        assert not torch.isnan(result).any()

    def test_zero_yaw(self, factory):
        """Yaw = 0 (looking East) is valid."""
        ticks = [_make_tick(pos_x=-2000, pos_y=800, yaw=0.0)]
        result = factory.generate_view_tensor(ticks, map_name="de_mirage")
        assert result.shape == (3, 16, 16)

    def test_yaw_wraparound(self, factory):
        """Yaw values crossing 360° are handled correctly in motion tensor."""
        ticks = [
            _make_tick(pos_x=-2000, pos_y=800, yaw=350.0, tick=1),
            _make_tick(pos_x=-1998, pos_y=800, yaw=10.0, tick=2),  # 20° delta via wraparound
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_mirage")
        # Should register a 20° yaw delta, not 340°
        assert result[2].max() > 0, "Yaw wraparound should produce crosshair signal"

    def test_many_ticks_trajectory_window(self, factory):
        """More ticks than TRAJECTORY_WINDOW are handled (only last N used)."""
        ticks = [
            _make_tick(pos_x=-2000 + i * 5, pos_y=800, tick=i)
            for i in range(TRAJECTORY_WINDOW + 20)
        ]
        result = factory.generate_motion_tensor(ticks, map_name="de_mirage")
        assert result.shape == (3, 16, 16)
        assert not torch.isnan(result).any()
