"""
tactical_map.py
The "Living Map" Widget - A Kivy widget that renders the 2D tactical view.

[OPTIMIZATION]
Round 4: Rewritten to use InstructionGroup layers for performance.
Static layers (Map, Heatmap) are drawn ONCE and updated only on resize/map change.
Dynamic layers (Players, Nades) are cleared and redrawn every frame.
This avoids re-uploading the map texture to the GPU ~64 times per second.
"""

import math
import os
import threading
import time
from typing import List

from kivy.graphics import Color, Ellipse, Line, PopMatrix, PushMatrix, Rectangle, Rotate
from kivy.graphics.instructions import InstructionGroup
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.widget import Widget

from Programma_CS2_RENAN.apps.desktop_app.ghost_pixel import GhostPixelValidator
from Programma_CS2_RENAN.core.demo_frame import EventType, GameEvent, NadeType, Team
from Programma_CS2_RENAN.core.map_manager import MapManager
from Programma_CS2_RENAN.core.playback_engine import InterpolatedPlayerState
from Programma_CS2_RENAN.core.spatial_engine import SpatialEngine


class TacticalMap(Widget):
    """
    The Living Map Widget.
    Renders players, utilities, and tactical overlays on a 2D map.
    """

    map_name = StringProperty("de_dust2")
    debug_mode = BooleanProperty(False)
    selected_player_id = NumericProperty(None, allownone=True)
    show_detonation_overlays = BooleanProperty(True)

    CT_COLOR = (0.3, 0.5, 1.0, 1.0)
    T_COLOR = (1.0, 0.6, 0.2, 1.0)
    DEAD_COLOR = (0.5, 0.5, 0.5, 0.5)
    SELECTED_COLOR = (1, 1, 1, 0.8)

    # [VISUAL] Reduced from 12 to 8 (User Request)
    PLAYER_RADIUS = 8
    HITBOX_MULTIPLIER = 2.5  # Click hitbox relative to visual radius

    # CS2 Grenade Effect Radii (in game units) — Task 2.24.1
    GRENADE_RADII = {
        NadeType.HE: 350,
        NadeType.MOLOTOV: 180,
        NadeType.SMOKE: 144,
        NadeType.FLASH: 1000,
    }
    GRENADE_OVERLAY_COLORS = {
        NadeType.HE: (1.0, 0.2, 0.2),  # Red
        NadeType.MOLOTOV: (1.0, 0.5, 0.0),  # Orange
        NadeType.SMOKE: (0.6, 0.6, 0.6),  # Gray
        NadeType.FLASH: (1.0, 1.0, 0.3),  # Yellow
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._nades = []
        self._players: List[InterpolatedPlayerState] = []
        self._current_tick = 0
        # self.selected_player_id = None  <-- Removed, handled by Property
        self._map_texture = None
        self._heatmap_texture = None
        self._name_textures = {}

        # --- Optimization: Render Layers ---
        self.map_group = InstructionGroup()
        self.heatmap_group = InstructionGroup()
        self.dynamic_group = InstructionGroup()

        self.canvas.add(self.map_group)
        self.canvas.add(self.heatmap_group)
        self.canvas.add(self.dynamic_group)

        self._ghost = GhostPixelValidator()
        self.add_widget(self._ghost)

        self._load_map_texture()
        self.bind(size=self._on_size, pos=self._on_size)

    def on_debug_mode(self, instance, value):
        self._ghost.active = value
        self._ghost.map_name = self.map_name
        self._ghost.map_meta = MapManager.get_map_metadata(self.map_name)

    _NAME_TEXTURE_CACHE_LIMIT = 64

    def on_map_name(self, instance, value):
        self._load_map_texture()
        self._heatmap_texture = None  # Clear heatmap on map change
        self._name_textures.clear()  # Clear stale name textures
        self._ghost.map_name = value
        if self.debug_mode:
            self._ghost.map_meta = MapManager.get_map_metadata(value)

    def _load_map_texture(self):
        # Asynchronous loading to prevent UI freeze
        MapManager.load_map_async(self.map_name, self._on_map_loaded)

    def _on_map_loaded(self, proxy_image, *args):
        # Callback when image is loaded
        if proxy_image.image.texture:
            self._map_texture = proxy_image.image.texture
            self._update_static_layers()

    def _on_size(self, *args):
        # Update static geometry on resize
        self._update_static_layers()
        self._redraw()

        # Ensure Ghost Validator matches the Map Image geometry perfectly
        map_size = min(self.width, self.height)
        offset_x = (self.width - map_size) / 2
        offset_y = (self.height - map_size) / 2

        if hasattr(self, "_ghost"):
            self._ghost.size = (map_size, map_size)
            self._ghost.pos = (self.x + offset_x, self.y + offset_y)

    def update_map(
        self,
        players: List[InterpolatedPlayerState],
        nades: List = None,
        ghosts: List = None,
        tick: int = 0,
    ):
        self._players = players
        self._ghosts = ghosts or []
        self._nades = nades or []
        self._current_tick = tick
        self._redraw()

    def update_heatmap(self, events: List[GameEvent]):
        """Legacy sync method - deprecated"""
        self.update_heatmap_async(events)

    def update_heatmap_async(self, events: List[GameEvent]):
        self._heatmap_points = events
        self._heatmap_texture = None
        # Redraw immediately (clears old heatmap)
        self._update_static_layers()
        threading.Thread(target=self._generate_heatmap_thread, args=(events,), daemon=True).start()

    def _generate_heatmap_thread(self, events):
        from kivy.clock import Clock

        from Programma_CS2_RENAN.backend.processing.heatmap_engine import HeatmapEngine

        # 1. Compute raw data in background (CPU heavy, Thread Safe)
        points = [(e.x, e.y) for e in events]
        data = HeatmapEngine.generate_heatmap_data(self.map_name, points)

        if data:
            # 2. Schedule texture creation on Main Thread (OpenGL required)
            Clock.schedule_once(lambda dt: self._on_heatmap_data_ready(data), 0)

    def _on_heatmap_data_ready(self, data):
        """Called on Main Thread to create texture."""
        from Programma_CS2_RENAN.backend.processing.heatmap_engine import HeatmapEngine

        texture = HeatmapEngine.create_texture_from_data(data)
        self._apply_heatmap_texture(texture)

    def _apply_heatmap_texture(self, texture):
        self._heatmap_texture = texture
        self._update_static_layers()

    def _update_static_layers(self):
        """Draws the Map and Heatmap. Called only on resize or texture update."""
        # 1. Map Layer
        self.map_group.clear()
        if self._map_texture:
            map_size = min(self.width, self.height)
            offset_x = (self.width - map_size) / 2
            offset_y = (self.height - map_size) / 2

            self.map_group.add(Color(1, 1, 1, 1))
            self.map_group.add(
                Rectangle(
                    texture=self._map_texture,
                    pos=(self.x + offset_x, self.y + offset_y),
                    size=(map_size, map_size),
                )
            )

        # 2. Heatmap Layer
        self.heatmap_group.clear()
        if self._heatmap_texture:
            map_size = min(self.width, self.height)
            offset_x = (self.width - map_size) / 2
            offset_y = (self.height - map_size) / 2

            self.heatmap_group.add(Color(1, 1, 1, 1))
            self.heatmap_group.add(
                Rectangle(
                    texture=self._heatmap_texture,
                    pos=(self.x + offset_x, self.y + offset_y),
                    size=(map_size, map_size),
                )
            )

    def _redraw(self):
        """Draws dynamic elements (Players, Nades). Called every tick."""
        self.dynamic_group.clear()

        # Utilities
        for nade in self._nades:
            self._draw_nade(nade, self.dynamic_group)

        # Ghosts (AI Prediction)
        if hasattr(self, "_ghosts"):
            for ghost in self._ghosts:
                ghost.is_ghost = True
                self._draw_player(ghost, self.dynamic_group)

        # Real Players
        for player in self._players:
            self._draw_player(player, self.dynamic_group)

    def _draw_player(self, player: InterpolatedPlayerState, group: InstructionGroup):
        px, py = self._world_to_screen(player.x, player.y)

        is_ct = False
        if isinstance(player.team, Team):
            is_ct = player.team == Team.CT
        else:
            is_ct = "CT" in str(player.team).upper()

        color = self.CT_COLOR if is_ct else self.T_COLOR
        if not player.is_alive:
            color = self.DEAD_COLOR

        # Ghost Override
        if getattr(player, "is_ghost", False):
            color = (color[0], color[1], color[2], 0.3)

        # Selection highlight
        if player.player_id == self.selected_player_id:
            group.add(Color(*self.SELECTED_COLOR))
            group.add(
                Ellipse(
                    pos=(px - self.PLAYER_RADIUS - 4, py - self.PLAYER_RADIUS - 4),
                    size=(self.PLAYER_RADIUS * 2 + 8, self.PLAYER_RADIUS * 2 + 8),
                )
            )

        group.add(Color(*color))
        group.add(
            Ellipse(
                pos=(px - self.PLAYER_RADIUS, py - self.PLAYER_RADIUS),
                size=(self.PLAYER_RADIUS * 2, self.PLAYER_RADIUS * 2),
            )
        )

        if player.is_alive:
            # FoV Cone
            group.add(PushMatrix())
            group.add(Rotate(origin=(px, py), angle=player.yaw - 90))
            group.add(Color(color[0], color[1], color[2], 0.3))

            # Adjusted for smaller radius: Cone starts at center, extends 30px (was 40)
            length = 30
            width_half = 15
            group.add(
                Line(
                    points=[px, py, px - width_half, py + length, px + width_half, py + length],
                    width=1.5,
                    close=True,
                )
            )

            group.add(PopMatrix())

        self._draw_player_name(px, py, player.name, group)
        if player.is_alive:
            self._draw_health_bar(px, py, player.hp, color, group)

    def _draw_player_name(self, px, py, name, group: InstructionGroup):
        from kivy.core.text import Label as CoreLabel

        if name not in self._name_textures:
            if len(self._name_textures) >= self._NAME_TEXTURE_CACHE_LIMIT:
                # F7-21: Evict oldest entry (FIFO). clear() is too aggressive.
                oldest_key = next(iter(self._name_textures))
                del self._name_textures[oldest_key]
            # [VISUAL] Smaller font for smaller player icons
            lbl = CoreLabel(text=name, font_size=9, color=(1, 1, 1, 1))
            lbl.refresh()
            self._name_textures[name] = lbl.texture
        tex = self._name_textures.get(name)
        if tex:
            group.add(Color(1, 1, 1, 1))
            # [VISUAL] Offset adjusted for smaller radius
            group.add(
                Rectangle(
                    texture=tex,
                    pos=(px - tex.width / 2.0, py + self.PLAYER_RADIUS + 2),
                    size=tex.size,
                )
            )

    def _draw_health_bar(self, px, py, hp, color, group: InstructionGroup):
        w = self.PLAYER_RADIUS * 2
        h = 2  # [VISUAL] Thinner bar
        group.add(Color(0, 0, 0, 0.5))
        # [VISUAL] Offset adjusted
        group.add(
            Rectangle(pos=(px - self.PLAYER_RADIUS, py - self.PLAYER_RADIUS - 5), size=(w, h))
        )

        h_color = (0, 1, 0, 0.8) if hp > 50 else (1, 0, 0, 0.8)
        group.add(Color(*h_color))
        group.add(
            Rectangle(
                pos=(px - self.PLAYER_RADIUS, py - self.PLAYER_RADIUS - 5),
                size=(w * (hp / 100.0), h),
            )
        )

    def _draw_nade(self, nade, group: InstructionGroup):
        # 0. Visibility Window check (Throw -> Detonate + 5s Fade)
        start_vis = nade.throw_tick or nade.starting_tick
        end_vis = nade.ending_tick + (5 * 64)
        if not (start_vis <= self._current_tick <= end_vis):
            return

        # Calculate current position (Interpolate if in flight)
        nx, ny = nade.x, nade.y
        if (
            nade.throw_tick
            and nade.throw_tick <= self._current_tick < nade.starting_tick
            and len(nade.trajectory) >= 2
        ):
            duration = nade.starting_tick - nade.throw_tick
            t = 1.0 if duration == 0 else (self._current_tick - nade.throw_tick) / duration
            p1, p2 = nade.trajectory[0], nade.trajectory[1]
            nx = p1[0] + (p2[0] - p1[0]) * t
            ny = p1[1] + (p2[1] - p1[1]) * t

        px, py = self._world_to_screen(nx, ny)

        # 1. Trajectory (3s fade-out window)
        # We only draw the trajectory AFTER the throw has occurred
        if nade.throw_tick and self._current_tick >= nade.throw_tick:
            self._draw_trajectory(nade, group)

        # 2. Detonation Radius Overlay (Task 2.24.1)
        if (
            self.show_detonation_overlays
            and nade.starting_tick <= self._current_tick <= nade.ending_tick
        ):
            self._draw_detonation_overlay(nade, px, py, group)

        # 3. Main Animation (Only if active)
        if nade.starting_tick <= self._current_tick <= nade.ending_tick:
            if nade.nade_type == NadeType.SMOKE:
                # Smoke expansion
                age = (self._current_tick - nade.starting_tick) / 64.0
                size = min(85, 20 + age * 18) if age > 0 else 60
                group.add(Color(0.7, 0.7, 0.8, 0.35))
                group.add(Ellipse(pos=(px - size / 2, py - size / 2), size=(size, size)))
                group.add(Color(0.9, 0.9, 1.0, 0.1))
                group.add(
                    Ellipse(pos=(px - size * 0.4, py - size * 0.4), size=(size * 0.8, size * 0.8))
                )
            elif nade.nade_type == NadeType.MOLOTOV:
                # Molotov pulsing
                pulse = 0.5 + 0.15 * math.sin(time.time() * 8)
                group.add(Color(1, 0.3, 0, pulse))
                group.add(Ellipse(pos=(px - 25, py - 25), size=(50, 50)))
                group.add(Color(1, 0.7, 0, 0.2 + pulse * 0.2))
                group.add(Ellipse(pos=(px - 15, py - 15), size=(30, 30)))

            # 4. Duration Progress Bar (Circular)
            total_ticks = nade.ending_tick - nade.starting_tick
            if total_ticks > 0:
                progress = 1.0 - ((self._current_tick - nade.starting_tick) / total_ticks)
                if progress > 0:
                    group.add(Color(1, 1, 1, 0.6))
                    group.add(Line(circle=(px, py, 10, 0, 360 * progress), width=2))

        # 5. Central dot (Always visible while projectile is tracked)
        group.add(Color(1, 1, 1, 1))
        group.add(Ellipse(pos=(px - 3, py - 3), size=(6, 6)))

    def _draw_detonation_overlay(self, nade, px, py, group: InstructionGroup):
        """
        Draw a semi-transparent circle showing the grenade's effective radius.

        Task 2.24.1: Converts game-unit radius to pixel radius using map scale,
        color-coded by grenade type.
        """
        radius_units = self.GRENADE_RADII.get(nade.nade_type)
        if radius_units is None:
            return

        color = self.GRENADE_OVERLAY_COLORS.get(nade.nade_type, (1, 1, 1))

        # Convert game units to pixel radius
        # _world_to_screen maps world coords to screen coords via SpatialEngine.
        # We compute how many pixels correspond to the radius in game units.
        origin_px, origin_py = self._world_to_screen(nade.x, nade.y)
        edge_px, edge_py = self._world_to_screen(nade.x + radius_units, nade.y)
        pixel_radius = abs(edge_px - origin_px)

        if pixel_radius < 2:
            return

        # Base opacity — flash fades from center, others uniform
        base_alpha = 0.15
        if nade.nade_type == NadeType.FLASH:
            base_alpha = 0.10

        # Draw the radius circle
        group.add(Color(color[0], color[1], color[2], base_alpha))
        group.add(
            Ellipse(
                pos=(px - pixel_radius, py - pixel_radius),
                size=(pixel_radius * 2, pixel_radius * 2),
            )
        )

        # Draw a thin border ring for clarity
        group.add(Color(color[0], color[1], color[2], base_alpha + 0.15))
        group.add(
            Line(
                circle=(px, py, pixel_radius),
                width=1.2,
            )
        )

        # Flash: add inner high-opacity zone (effective blind range ~300 units)
        if nade.nade_type == NadeType.FLASH:
            inner_edge_px, _ = self._world_to_screen(nade.x + 300, nade.y)
            inner_radius = abs(inner_edge_px - origin_px)
            if inner_radius > 2:
                group.add(Color(color[0], color[1], color[2], 0.20))
                group.add(
                    Ellipse(
                        pos=(px - inner_radius, py - inner_radius),
                        size=(inner_radius * 2, inner_radius * 2),
                    )
                )

    def _draw_trajectory(self, nade, group: InstructionGroup):
        if not nade.trajectory or len(nade.trajectory) < 2:
            return

        # Fade out starting 3s after detonation
        fade_start = nade.starting_tick + (3 * 64)
        base_alpha = 0.5
        if self._current_tick > fade_start:
            base_alpha = max(0, 0.5 - (self._current_tick - fade_start) / (2 * 64.0))

        if base_alpha <= 0:
            return

        from Programma_CS2_RENAN.core.demo_frame import NadeType

        if nade.nade_type == NadeType.SMOKE:
            color = [0.7, 0.7, 0.8]
        elif nade.nade_type == NadeType.MOLOTOV:
            color = [1.0, 0.4, 0]
        elif nade.nade_type == NadeType.FLASH:
            color = [1.0, 1.0, 1.0]
        else:
            color = [1.0, 0.2, 0.2]

        min_z = min(pt[2] for pt in nade.trajectory)
        max_z = max(pt[2] for pt in nade.trajectory)
        z_range = max(1.0, max_z - min_z)

        last_px, last_py = None, None

        for i, (wx, wy, wz) in enumerate(nade.trajectory):
            px, py = self._world_to_screen(wx, wy)

            if i > 0:
                rel_h = (wz - min_z) / z_range

                # Dynamic Visuals based on height
                seg_width = 1.0 + (rel_h * 2.5)
                seg_alpha = base_alpha * (0.6 + rel_h * 0.4)

                group.add(Color(color[0], color[1], color[2], seg_alpha))
                group.add(Line(points=[last_px, last_py, px, py], width=seg_width))

            last_px, last_py = px, py

        # Draw Apex Marker
        # Find index of max Z
        apex_idx = 0
        cur_max = -99999
        for i, pt in enumerate(nade.trajectory):
            if pt[2] > cur_max:
                cur_max = pt[2]
                apex_idx = i

        if apex_idx < len(nade.trajectory):
            ax, ay, az = nade.trajectory[apex_idx]
            apx, apy = self._world_to_screen(ax, ay)
            group.add(Color(1, 1, 1, base_alpha * 0.8))
            group.add(Ellipse(pos=(apx - 3, apy - 3), size=(6, 6)))

    def _world_to_screen(self, x, y):
        # F7-22: Uses min(width, height) for uniform scaling — correctly handles non-square
        # widgets by centering the 1024×1024 map area and applying offset_x/offset_y.
        map_size = min(self.width, self.height)
        offset_x = (self.width - map_size) / 2
        offset_y = (self.height - map_size) / 2
        nx, ny = SpatialEngine.world_to_normalized(x, y, self.map_name)
        # We must add self.x and self.y because the widget might be shifted in a layout
        return (self.x + nx * map_size + offset_x, self.y + (1.0 - ny) * map_size + offset_y)

    def _screen_to_world(self, sx, sy):
        map_size = min(self.width, self.height)
        offset_x = (self.width - map_size) / 2
        offset_y = (self.height - map_size) / 2
        # Subtract self.x/y to get widget-relative coords
        nx = (sx - self.x - offset_x) / map_size
        ny = 1.0 - ((sy - self.y - offset_y) / map_size)
        return SpatialEngine.pixel_to_world(
            nx * map_size, ny * map_size, self.map_name, map_size, map_size
        )

    def on_selected_player_id(self, instance, value):
        self._redraw()

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)

        # 1. If debug mode is active, let children (Ghost Validator) handle it first
        if self.debug_mode:
            if super().on_touch_down(touch):
                return True

        # 2. Player selection logic
        for p in self._players:
            px, py = self._world_to_screen(p.x, p.y)
            # Hitbox slightly larger than visual radius
            if math.hypot(touch.x - px, touch.y - py) < self.PLAYER_RADIUS * self.HITBOX_MULTIPLIER:
                self.selected_player_id = (
                    p.player_id if self.selected_player_id != p.player_id else None
                )
                self._redraw()
                return True

        # 3. Deselect if clicked empty space
        self.selected_player_id = None
        self._redraw()
        return True
