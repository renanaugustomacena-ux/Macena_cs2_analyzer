"""
TensorFactory: Player-POV Perception System

Converts game state data into PyTorch tensors for neural network consumption.
Implements a NO-WALLHACK sensorial model: the AI coach sees only what
the player legitimately knows at each tick.

Architecture:
- MapRasterizer: Tactical knowledge map (teammates, last-known enemies, utility)
- VisionRasterizer: Player's visual experience (FOV, visible entities, utility zones)
- MotionEncoder: Movement context (trajectory, velocity gradient, crosshair movement)

When PlayerKnowledge is provided, tensors encode the player-POV experience.
When PlayerKnowledge is None, falls back to legacy behavior for backward compat.
"""

import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

# R4-02-03: Lazy-import scipy to avoid hard crash on minimal installs.
# gaussian_filter is used in multiple methods; import once at first use.
_gaussian_filter = None


def _get_gaussian_filter():
    global _gaussian_filter
    if _gaussian_filter is None:
        from scipy.ndimage import gaussian_filter as _gf
        _gaussian_filter = _gf
    return _gaussian_filter

from Programma_CS2_RENAN.backend.processing.player_knowledge import PlayerKnowledge
from Programma_CS2_RENAN.backend.storage.db_models import PlayerTickState
from Programma_CS2_RENAN.core.spatial_data import MapMetadata, get_map_metadata

# ============ Constants ============

OWN_POSITION_INTENSITY = 1.5
"""Own position marker is brighter than teammates on map tensor."""

ENTITY_TEAMMATE_DIMMING = 0.7
"""Teammates rendered slightly dimmer than enemies on view tensor."""

ENTITY_MIN_INTENSITY = 0.2
"""Minimum intensity for visible entities (even at max distance)."""

ENEMY_MIN_INTENSITY = 0.3
"""Minimum intensity for visible enemies."""

BOMB_MARKER_RADIUS = 50.0
"""World-unit radius for bomb marker on map tensor."""

BOMB_MARKER_INTENSITY = 0.8
"""Intensity of the bomb marker circle."""

TRAJECTORY_WINDOW = 32
"""Number of ticks for trajectory trail (~0.5s at 64 tick/s)."""

VELOCITY_FALLOFF_RADIUS = 20.0
"""Grid cells over which velocity radial gradient fades to zero."""

MAX_SPEED_UNITS_PER_TICK = 4.0
"""CS2 max player speed in world units per tick at 64 tick/s (~250 units/s).
NOTE (F2-03): Calibrated for 64 tick/s. On 128 tick/s demos (FACEIT/ESEA)
per-tick displacement is halved (~2.0 units/tick), compressing velocity
features into the lower half of [0, 1]. Accept as known limitation until
tick-rate-aware normalisation is implemented.
"""

MAX_YAW_DELTA_DEG = 45.0
"""Maximum yaw delta per tick for normalization (flick threshold)."""


@dataclass
class TensorConfig:
    """Configuration for tensor generation."""

    map_resolution: int = 128  # Output resolution for map tensor
    view_resolution: int = 224  # Output resolution for view tensor
    sigma: float = 3.0  # Gaussian blur for heatmaps
    fov_degrees: float = 90.0  # H-10: matches core.constants.FOV_DEGREES
    view_distance: float = 2000.0  # Max view distance in world units


@dataclass
class TrainingTensorConfig(TensorConfig):
    """Lower resolution for training efficiency.

    AdaptiveAvgPool2d((1,1)) in RAPPerception ensures output 128-dim
    regardless of input resolution. 64x64 during training saves ~12x
    memory vs 224x224.

    NOTE (F2-02): The 128-dim output contract depends on RAPPerception's
    AdaptiveAvgPool2d layer. If that layer is changed or removed, the
    contract breaks silently. A runtime assertion `assert output.shape[-1] == 128`
    in RAPPerception's forward() is recommended to catch regressions.
    """

    map_resolution: int = 64
    view_resolution: int = 64


class TensorFactory:
    """
    Factory for converting game state into neural network tensors.

    Player-POV mode (knowledge provided):
    - map_tensor (3, res, res): Ch0=teammates, Ch1=last-known enemies (decayed),
      Ch2=utility zones + bomb
    - view_tensor (3, res, res): Ch0=FOV mask, Ch1=visible entities (distance-weighted),
      Ch2=active utility zones
    - motion_tensor (3, res, res): Ch0=trajectory trail, Ch1=velocity gradient,
      Ch2=crosshair movement

    Legacy mode (knowledge=None):
    - map_tensor (3, res, res): Ch0=enemies, Ch1=teammates, Ch2=player position
    - view_tensor (3, res, res): Ch0=FOV mask, Ch1=zeros, Ch2=safe zones
    - motion_tensor (3, res, res): Ch0=vx uniform, Ch1=vy uniform, Ch2=speed uniform
    """

    def __init__(self, config: Optional[TensorConfig] = None):
        self.config = config or TensorConfig()

    # ============ Public Tensor Generation ============

    def generate_map_tensor(
        self,
        ticks: List[PlayerTickState],
        map_name: str = "de_mirage",
        knowledge: Optional[PlayerKnowledge] = None,
    ) -> torch.Tensor:
        """Generate tactical knowledge map tensor.

        Player-POV channels (when knowledge is provided):
        - Ch0: Teammate positions (always known via radar/comms)
        - Ch1: Last-known enemy positions (memory with temporal decay)
        - Ch2: Utility zones + bomb overlay

        Legacy channels (when knowledge is None):
        - Ch0: Enemy positions, Ch1: Teammate positions, Ch2: Player position

        Args:
            ticks: List of PlayerTickState for current sequence.
            map_name: Map name for coordinate projection.
            knowledge: Optional PlayerKnowledge for player-POV mode.

        Returns:
            torch.Tensor of shape (3, map_resolution, map_resolution).
        """
        meta = get_map_metadata(map_name)
        resolution = self.config.map_resolution

        if meta is None or not ticks:
            return torch.zeros((3, resolution, resolution), dtype=torch.float32)

        # --- Player-POV mode ---
        if knowledge is not None:
            return self._generate_pov_map(knowledge, meta, resolution)

        # --- Legacy mode (backward compat) ---
        enemy_channel = np.zeros((resolution, resolution), dtype=np.float32)
        team_channel = np.zeros((resolution, resolution), dtype=np.float32)
        player_channel = np.zeros((resolution, resolution), dtype=np.float32)

        current_tick = ticks[-1]
        player_team = getattr(current_tick, "team", "CT")

        for tick in ticks:
            gx, gy = self._world_to_grid(tick.pos_x, tick.pos_y, meta, resolution)
            if 0 <= gx < resolution and 0 <= gy < resolution:
                tick_team = getattr(tick, "team", "CT")
                if tick_team != player_team:
                    enemy_channel[gy, gx] += 1.0
                else:
                    team_channel[gy, gx] += 1.0

        px, py = self._world_to_grid(current_tick.pos_x, current_tick.pos_y, meta, resolution)
        if 0 <= px < resolution and 0 <= py < resolution:
            player_channel[py, px] = 1.0

        if self.config.sigma > 0:
            gf = _get_gaussian_filter()
            enemy_channel = gf(enemy_channel, sigma=self.config.sigma)
            team_channel = gf(team_channel, sigma=self.config.sigma)
            player_channel = gf(player_channel, sigma=self.config.sigma)

        enemy_channel = self._normalize(enemy_channel)
        team_channel = self._normalize(team_channel)
        player_channel = self._normalize(player_channel)

        result = torch.tensor(
            np.stack([enemy_channel, team_channel, player_channel], axis=0),
            dtype=torch.float32,
        )
        # P-X-02: Shape assertion on generated map tensor
        assert result.shape == (3, resolution, resolution), (
            f"P-X-02: map_tensor shape {result.shape}, "
            f"expected (3, {resolution}, {resolution})"
        )
        return result

    def generate_view_tensor(
        self,
        ticks: List[PlayerTickState],
        map_name: str = "de_mirage",
        knowledge: Optional[PlayerKnowledge] = None,
    ) -> torch.Tensor:
        """Generate field-of-view tensor.

        Player-POV channels (when knowledge is provided):
        - Ch0: FOV mask (geometric cone from player's look direction)
        - Ch1: Visible entities — teammates (always, dimmed) + enemies (only
          when visible per PlayerKnowledge), gaussian blobs with intensity
          inversely proportional to distance
        - Ch2: Active utility zones (smoke/molotov/flash circles)

        Legacy channels (when knowledge is None):
        - Ch0: FOV mask
        - Ch1: Uncovered danger zones (areas not in recent FOV history — potential enemy positions)
        - Ch2: Safe zones (recently covered but not currently in FOV)

        Args:
            ticks: List of PlayerTickState for current sequence.
            map_name: Map name for coordinate projection.
            knowledge: Optional PlayerKnowledge for player-POV mode.

        Returns:
            torch.Tensor of shape (3, view_resolution, view_resolution).
        """
        meta = get_map_metadata(map_name)
        resolution = self.config.view_resolution

        if meta is None or not ticks:
            return torch.zeros((3, resolution, resolution), dtype=torch.float32)

        current_tick = ticks[-1]
        player_x = current_tick.pos_x
        player_y = current_tick.pos_y
        yaw = getattr(current_tick, "yaw", 0.0)

        # Ch0: FOV mask (same geometry for both modes)
        fov_mask = self._generate_fov_mask(player_x, player_y, yaw, meta, resolution)

        # --- Player-POV mode ---
        if knowledge is not None:
            return self._generate_pov_view(knowledge, fov_mask, meta, resolution)

        # --- Legacy mode (backward compat) ---
        # G-02: Ch1 = danger zone — map areas NOT covered by accumulated player FOV.
        # Unchecked angles represent potential enemy positions (danger).
        # Cap history to 8 ticks (~125ms at 64 Hz) to keep path performant.
        _LEGACY_TICK_CAP = 8
        accumulated_fov = fov_mask.copy()
        for tick in ticks[:-1][-_LEGACY_TICK_CAP:]:
            tick_yaw = getattr(tick, "view_x", getattr(tick, "yaw", 0.0))
            tick_fov = self._generate_fov_mask(
                tick.pos_x, tick.pos_y, tick_yaw, meta, resolution
            )
            accumulated_fov = np.maximum(accumulated_fov, tick_fov)
        danger_zone = np.clip(1.0 - accumulated_fov, 0, 1)
        safe_zone = np.clip(1.0 - fov_mask - danger_zone, 0, 1)
        view_tensor = np.stack([fov_mask, danger_zone, safe_zone], axis=0)

        result = torch.tensor(view_tensor, dtype=torch.float32)
        # P-X-02: Shape assertion on generated view tensor
        assert result.shape == (3, resolution, resolution), (
            f"P-X-02: view_tensor shape {result.shape}, "
            f"expected (3, {resolution}, {resolution})"
        )
        return result

    def generate_motion_tensor(
        self,
        ticks: List[PlayerTickState],
        map_name: str = "de_mirage",
    ) -> torch.Tensor:
        """Generate motion encoding tensor.

        Player-POV channels (when map metadata available and multiple ticks):
        - Ch0: Recent trajectory — last N tick positions as a trail on the map,
          intensity proportional to recency (newest = 1.0, oldest → 0)
        - Ch1: Velocity field — radial gradient centered on player position,
          overall intensity modulated by current movement speed
        - Ch2: Crosshair movement — yaw delta magnitude encoding. Slow aim
          produces low uniform value, flick produces bright spot at player
          position

        Fallback (< 2 ticks or no map metadata):
        Returns zeros.

        Args:
            ticks: List of PlayerTickState (need at least 2 for deltas).
            map_name: Map name for coordinate projection.

        Returns:
            torch.Tensor of shape (3, view_resolution, view_resolution).
        """
        resolution = self.config.view_resolution

        if len(ticks) < 2:
            return torch.zeros((3, resolution, resolution), dtype=torch.float32)

        meta = get_map_metadata(map_name)
        if meta is None:
            return self._generate_legacy_motion(ticks, resolution)

        curr_tick = ticks[-1]
        prev_tick = ticks[-2]

        # --- Ch0: Trajectory trail ---
        trajectory_ch = self._build_trajectory_channel(ticks, meta, resolution)

        # --- Ch1: Velocity radial gradient ---
        velocity_ch = self._build_velocity_channel(curr_tick, prev_tick, meta, resolution)

        # --- Ch2: Crosshair movement ---
        crosshair_ch = self._build_crosshair_channel(curr_tick, prev_tick, meta, resolution)

        result = torch.tensor(
            np.stack([trajectory_ch, velocity_ch, crosshair_ch], axis=0),
            dtype=torch.float32,
        )
        # P-X-02: Shape assertion on generated motion tensor
        assert result.shape == (3, resolution, resolution), (
            f"P-X-02: motion_tensor shape {result.shape}, "
            f"expected (3, {resolution}, {resolution})"
        )
        return result

    def generate_all_tensors(
        self,
        ticks: List[PlayerTickState],
        map_name: str = "de_mirage",
        knowledge: Optional[PlayerKnowledge] = None,
    ) -> Dict[str, torch.Tensor]:
        """Generate complete tensor set for neural network input.

        Args:
            ticks: List of PlayerTickState for current sequence.
            map_name: Map name for coordinate projection.
            knowledge: Optional PlayerKnowledge for player-POV mode.

        Returns:
            Dict with 'map', 'view', 'motion' tensors.
        """
        return {
            "map": self.generate_map_tensor(ticks, map_name, knowledge=knowledge),
            "view": self.generate_view_tensor(ticks, map_name, knowledge=knowledge),
            "motion": self.generate_motion_tensor(ticks, map_name),
        }

    # ============ Player-POV Generators ============

    def _generate_pov_map(
        self, knowledge: PlayerKnowledge, meta: MapMetadata, resolution: int
    ) -> torch.Tensor:
        """Generate player-POV tactical map.

        Ch0: Teammate positions (always known via radar/comms) + own position
        Ch1: Enemy positions — currently visible (full intensity) + last-known
             (intensity = decay_factor, exponentially decaying with time)
        Ch2: Active utility zones (smoke/molotov circles) + bomb overlay
        """
        teammate_ch = np.zeros((resolution, resolution), dtype=np.float32)
        enemy_ch = np.zeros((resolution, resolution), dtype=np.float32)
        utility_ch = np.zeros((resolution, resolution), dtype=np.float32)

        # --- Ch0: Teammates (always known via radar) ---
        for tm in knowledge.teammate_positions:
            gx, gy = self._world_to_grid(tm.pos_x, tm.pos_y, meta, resolution)
            if 0 <= gx < resolution and 0 <= gy < resolution:
                teammate_ch[gy, gx] += 1.0

        # Own position (brighter marker) — skip if fallback (0,0,0)
        if not getattr(knowledge, "position_is_fallback", False):
            px, py = self._world_to_grid(knowledge.own_pos_x, knowledge.own_pos_y, meta, resolution)
            if 0 <= px < resolution and 0 <= py < resolution:
                teammate_ch[py, px] = max(teammate_ch[py, px], OWN_POSITION_INTENSITY)

        # --- Ch1: Enemies (visible = full, last-known = decayed) ---
        for enemy in knowledge.visible_enemies:
            gx, gy = self._world_to_grid(enemy.pos_x, enemy.pos_y, meta, resolution)
            if 0 <= gx < resolution and 0 <= gy < resolution:
                enemy_ch[gy, gx] += 1.0

        for enemy in knowledge.last_known_enemies:
            gx, gy = self._world_to_grid(enemy.pos_x, enemy.pos_y, meta, resolution)
            if 0 <= gx < resolution and 0 <= gy < resolution:
                enemy_ch[gy, gx] = max(enemy_ch[gy, gx], enemy.decay_factor)

        # --- Ch2: Utility zones + bomb ---
        for zone in knowledge.utility_zones:
            self._draw_circle(utility_ch, zone.pos_x, zone.pos_y, zone.radius, meta, resolution)

        if knowledge.bomb_planted:
            bx, by = self._world_to_grid(
                knowledge.bomb_pos_x, knowledge.bomb_pos_y, meta, resolution
            )
            if 0 <= bx < resolution and 0 <= by < resolution:
                utility_ch[by, bx] = 1.0
            self._draw_circle(
                utility_ch,
                knowledge.bomb_pos_x,
                knowledge.bomb_pos_y,
                BOMB_MARKER_RADIUS,
                meta,
                resolution,
                intensity=BOMB_MARKER_INTENSITY,
            )

        # Spatial smoothing
        if self.config.sigma > 0:
            gf = _get_gaussian_filter()
            teammate_ch = gf(teammate_ch, sigma=self.config.sigma)
            enemy_ch = gf(enemy_ch, sigma=self.config.sigma)
            utility_ch = gf(utility_ch, sigma=self.config.sigma)

        teammate_ch = self._normalize(teammate_ch)
        enemy_ch = self._normalize(enemy_ch)
        utility_ch = self._normalize(utility_ch)

        return torch.tensor(
            np.stack([teammate_ch, enemy_ch, utility_ch], axis=0),
            dtype=torch.float32,
        )

    def _generate_pov_view(
        self,
        knowledge: PlayerKnowledge,
        fov_mask: np.ndarray,
        meta: MapMetadata,
        resolution: int,
    ) -> torch.Tensor:
        """Generate player-POV view tensor.

        Ch0: FOV mask (geometric cone, already computed)
        Ch1: Visible entities — teammates (always, dimmed) + visible enemies
             (only those in PlayerKnowledge.visible_enemies), rendered as
             gaussian blobs with intensity inversely proportional to distance
        Ch2: Active utility zones (smoke/molotov/flash circles)
        """
        entity_ch = np.zeros((resolution, resolution), dtype=np.float32)
        utility_ch = np.zeros((resolution, resolution), dtype=np.float32)

        max_view_dist = self.config.view_distance

        # Teammates (always visible on radar, slightly dimmer)
        for tm in knowledge.teammate_positions:
            gx, gy = self._world_to_grid(tm.pos_x, tm.pos_y, meta, resolution)
            if 0 <= gx < resolution and 0 <= gy < resolution:
                intensity = max(ENTITY_MIN_INTENSITY, 1.0 - tm.distance / max_view_dist)
                entity_ch[gy, gx] = max(entity_ch[gy, gx], intensity * ENTITY_TEAMMATE_DIMMING)

        # Visible enemies (only those the player actually sees)
        for enemy in knowledge.visible_enemies:
            gx, gy = self._world_to_grid(enemy.pos_x, enemy.pos_y, meta, resolution)
            if 0 <= gx < resolution and 0 <= gy < resolution:
                intensity = max(ENEMY_MIN_INTENSITY, 1.0 - enemy.distance / max_view_dist)
                entity_ch[gy, gx] = max(entity_ch[gy, gx], intensity)

        # Active utility zones
        for zone in knowledge.utility_zones:
            self._draw_circle(utility_ch, zone.pos_x, zone.pos_y, zone.radius, meta, resolution)

        # Spatial smoothing
        if self.config.sigma > 0:
            gf = _get_gaussian_filter()
            entity_ch = gf(entity_ch, sigma=self.config.sigma)
            utility_ch = gf(utility_ch, sigma=self.config.sigma)

        entity_ch = self._normalize(entity_ch)
        utility_ch = self._normalize(utility_ch)

        return torch.tensor(
            np.stack([fov_mask, entity_ch, utility_ch], axis=0),
            dtype=torch.float32,
        )

    # ============ Motion Sub-Channels ============

    def _build_trajectory_channel(
        self,
        ticks: List[PlayerTickState],
        meta: MapMetadata,
        resolution: int,
    ) -> np.ndarray:
        """Build trajectory trail channel (Ch0 of motion tensor).

        Plots last N tick positions on the grid with intensity proportional
        to recency: newest tick = 1.0, oldest → 0.
        """
        channel = np.zeros((resolution, resolution), dtype=np.float32)
        n_trail = min(len(ticks), TRAJECTORY_WINDOW)

        for i, tick in enumerate(ticks[-n_trail:]):
            gx, gy = self._world_to_grid(tick.pos_x, tick.pos_y, meta, resolution)
            if 0 <= gx < resolution and 0 <= gy < resolution:
                recency = (i + 1) / n_trail
                channel[gy, gx] = max(channel[gy, gx], recency)

        # Light blur for smooth trail
        if self.config.sigma > 0:
            channel = _get_gaussian_filter()(channel, sigma=max(1.0, self.config.sigma * 0.5))

        return self._normalize(channel)

    def _build_velocity_channel(
        self,
        curr_tick: PlayerTickState,
        prev_tick: PlayerTickState,
        meta: MapMetadata,
        resolution: int,
    ) -> np.ndarray:
        """Build velocity gradient channel (Ch1 of motion tensor).

        Radial gradient centered on player position, with overall intensity
        modulated by current movement speed. Stationary player → dark.
        Moving player → bright gradient centered on position.
        """
        channel = np.zeros((resolution, resolution), dtype=np.float32)

        dx = curr_tick.pos_x - prev_tick.pos_x
        dy = curr_tick.pos_y - prev_tick.pos_y
        speed = np.sqrt(dx**2 + dy**2)
        norm_speed = min(speed / MAX_SPEED_UNITS_PER_TICK, 1.0)

        if norm_speed < 0.01:
            return channel

        px, py = self._world_to_grid(curr_tick.pos_x, curr_tick.pos_y, meta, resolution)
        y_coords, x_coords = np.ogrid[:resolution, :resolution]
        dist_from_player = np.sqrt((x_coords - px) ** 2 + (y_coords - py) ** 2).astype(np.float32)

        radial = np.clip(1.0 - dist_from_player / VELOCITY_FALLOFF_RADIUS, 0, 1)
        channel = radial * norm_speed

        return channel

    def _build_crosshair_channel(
        self,
        curr_tick: PlayerTickState,
        prev_tick: PlayerTickState,
        meta: MapMetadata,
        resolution: int,
    ) -> np.ndarray:
        """Build crosshair movement channel (Ch2 of motion tensor).

        Encodes yaw delta magnitude as a gaussian blob at the player's
        position. Slow aim → dim spot. Flick → bright spot.
        Stationary crosshair → dark channel.
        """
        channel = np.zeros((resolution, resolution), dtype=np.float32)

        curr_yaw = float(getattr(curr_tick, "yaw", 0.0))
        prev_yaw = float(getattr(prev_tick, "yaw", 0.0))

        yaw_delta = abs(curr_yaw - prev_yaw)
        if yaw_delta > 180:
            yaw_delta = 360 - yaw_delta

        norm_yaw = min(yaw_delta / MAX_YAW_DELTA_DEG, 1.0)

        if norm_yaw < 0.01:
            return channel

        # Gaussian blob at player position with intensity = yaw delta
        px, py = self._world_to_grid(curr_tick.pos_x, curr_tick.pos_y, meta, resolution)
        if 0 <= px < resolution and 0 <= py < resolution:
            channel[py, px] = norm_yaw

        # Spread with gaussian blur
        channel = _get_gaussian_filter()(channel, sigma=max(2.0, self.config.sigma))

        return self._normalize(channel)

    def _generate_legacy_motion(
        self, ticks: List[PlayerTickState], resolution: int
    ) -> torch.Tensor:
        """Legacy motion tensor: uniform scalar velocity encoding.

        Used when map metadata is unavailable.
        """
        prev_tick = ticks[-2]
        curr_tick = ticks[-1]

        dx = curr_tick.pos_x - prev_tick.pos_x
        dy = curr_tick.pos_y - prev_tick.pos_y
        magnitude = np.sqrt(dx**2 + dy**2)

        norm_dx = np.clip(dx / MAX_SPEED_UNITS_PER_TICK, -1, 1)
        norm_dy = np.clip(dy / MAX_SPEED_UNITS_PER_TICK, -1, 1)
        norm_mag = np.clip(magnitude / MAX_SPEED_UNITS_PER_TICK, 0, 1)

        motion_x = np.full((resolution, resolution), norm_dx, dtype=np.float32)
        motion_y = np.full((resolution, resolution), norm_dy, dtype=np.float32)
        motion_mag = np.full((resolution, resolution), norm_mag, dtype=np.float32)

        return torch.tensor(
            np.stack([motion_x, motion_y, motion_mag], axis=0),
            dtype=torch.float32,
        )

    # ============ Private Helper Methods ============

    def _world_to_grid(
        self, x: float, y: float, meta: MapMetadata, resolution: int
    ) -> Tuple[int, int]:
        """Convert world coordinates to grid coordinates."""
        scale_factor = 1.0 / (meta.scale * 1024.0)

        nx = (x - meta.pos_x) * scale_factor
        ny = (meta.pos_y - y) * scale_factor

        gx = int(nx * resolution)
        gy = int(ny * resolution)  # C-03: single Y-flip only (meta.pos_y - y already inverts)

        return gx, gy

    _MIN_NORMALIZATION_THRESHOLD = 1.0

    def _normalize(self, arr: np.ndarray) -> np.ndarray:
        """Normalize array to [0, 1] range.

        M-10: Uses max(max_val, threshold) to prevent amplification of
        noise in sparse channels (single non-zero pixel).
        """
        max_val = np.max(arr)
        if max_val > 0:
            return arr / max(max_val, self._MIN_NORMALIZATION_THRESHOLD)
        return arr

    def _draw_circle(
        self,
        channel: np.ndarray,
        world_x: float,
        world_y: float,
        radius: float,
        meta: MapMetadata,
        resolution: int,
        intensity: float = 1.0,
    ) -> None:
        """Draw a filled circle on a channel in grid coordinates.

        Converts world-space position and radius to grid coordinates,
        then fills all grid cells within the radius.
        """
        cx, cy = self._world_to_grid(world_x, world_y, meta, resolution)

        # Convert radius from world units to grid units
        scale_factor = 1.0 / (meta.scale * 1024.0)
        grid_radius = max(1, int(radius * scale_factor * resolution))

        y_coords, x_coords = np.ogrid[:resolution, :resolution]
        dist = np.sqrt(((x_coords - cx) ** 2 + (y_coords - cy) ** 2).astype(np.float32))
        mask = dist <= grid_radius

        np.maximum(channel, intensity * mask, out=channel)

    def _generate_fov_mask(
        self,
        player_x: float,
        player_y: float,
        yaw: float,
        meta: MapMetadata,
        resolution: int,
    ) -> np.ndarray:
        """Generate a field-of-view mask.

        Creates a cone-shaped mask centered on the player's look direction.
        This is a top-down 2D approximation of the player's rectangular
        viewport — geometrically reasonable for representing "where the
        player is looking" but does not account for wall occlusion.
        """
        mask = np.zeros((resolution, resolution), dtype=np.float32)

        # Convert player position to grid
        px, py = self._world_to_grid(player_x, player_y, meta, resolution)

        # Half FOV in radians
        half_fov = np.radians(self.config.fov_degrees / 2)
        yaw_rad = np.radians(yaw)

        # View distance in grid units
        view_dist_grid = int(self.config.view_distance / (meta.scale * 1024.0 / resolution))

        # Generate coordinates for masking
        y_coords, x_coords = np.ogrid[:resolution, :resolution]

        # Calculate angle from player to each point
        dx = x_coords - px
        dy = y_coords - py
        distance = np.sqrt(dx**2 + dy**2)

        # Angle from player to point
        angle_to_point = np.arctan2(dy, dx)

        # Angle difference (handling wraparound)
        angle_diff = np.abs(
            np.arctan2(
                np.sin(angle_to_point - yaw_rad),
                np.cos(angle_to_point - yaw_rad),
            )
        )

        # Create mask: within FOV cone and within view distance
        in_fov = angle_diff <= half_fov
        in_range = distance <= view_dist_grid

        mask[in_fov & in_range] = 1.0

        # Apply slight blur for smooth edges
        mask = _get_gaussian_filter()(mask, sigma=1.5)

        return mask


# Singleton instance for convenience
_factory_instance: Optional[TensorFactory] = None
_factory_lock = threading.Lock()


def get_tensor_factory() -> TensorFactory:
    """Get the singleton TensorFactory instance (thread-safe double-checked locking)."""
    global _factory_instance
    if _factory_instance is None:
        with _factory_lock:
            if _factory_instance is None:
                _factory_instance = TensorFactory()
    return _factory_instance
