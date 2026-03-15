"""QPainter-based 2D tactical map — renders players, grenades, and ghosts."""

import math
import os
from typing import List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

from Programma_CS2_RENAN.core.config import get_resource_path
from Programma_CS2_RENAN.core.demo_frame import NadeType, Team
from Programma_CS2_RENAN.core.playback_engine import InterpolatedPlayerState
from Programma_CS2_RENAN.core.spatial_engine import SpatialEngine

TICK_RATE = 64
PLAYER_RADIUS = 8
HITBOX_MULTIPLIER = 2.5

CT_COLOR = QColor(77, 128, 255)
T_COLOR = QColor(255, 153, 51)
DEAD_COLOR = QColor(128, 128, 128, 128)
SELECTED_COLOR = QColor(255, 255, 255, 204)

GRENADE_RADII = {
    NadeType.HE: 350,
    NadeType.MOLOTOV: 180,
    NadeType.SMOKE: 144,
    NadeType.FLASH: 1000,
}
GRENADE_OVERLAY_COLORS = {
    NadeType.HE: QColor(255, 51, 51),
    NadeType.MOLOTOV: QColor(255, 128, 0),
    NadeType.SMOKE: QColor(153, 153, 153),
    NadeType.FLASH: QColor(255, 255, 77),
}


class TacticalMapWidget(QWidget):
    """2D tactical map with player/grenade rendering via QPainter."""

    selected_player_changed = Signal(object)  # int or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._map_name = "de_dust2"
        self._map_pixmap: Optional[QPixmap] = None
        self._players: List[InterpolatedPlayerState] = []
        self._ghosts: List[InterpolatedPlayerState] = []
        self._nades: List = []
        self._current_tick = 0
        self._selected_player_id: Optional[int] = None

        self._name_font = QFont("Roboto", 7)
        self._name_fm = QFontMetrics(self._name_font)

        self.setMinimumSize(200, 200)
        self.setMouseTracking(False)

    # ── Public API ──

    def set_map(self, map_name: str):
        self._map_name = map_name
        self._load_map_image()
        self.update()

    def update_map(
        self,
        players: List[InterpolatedPlayerState],
        nades: List = None,
        ghosts: List = None,
        tick: int = 0,
    ):
        self._players = players
        self._nades = nades or []
        self._ghosts = ghosts or []
        self._current_tick = tick
        self.update()

    @property
    def selected_player_id(self) -> Optional[int]:
        return self._selected_player_id

    @selected_player_id.setter
    def selected_player_id(self, value):
        if self._selected_player_id != value:
            self._selected_player_id = value
            self.selected_player_changed.emit(value)
            self.update()

    # ── Map Loading ──

    def _load_map_image(self):
        """Load map radar image as QPixmap — no Kivy dependency."""
        clean = self._map_name.lower().strip()
        clean = clean.replace(".dem", "").replace(".vpk", "").replace("maps/", "")

        maps_dir = get_resource_path(os.path.join("PHOTO_GUI", "maps"))

        # Try exact name, then with de_ prefix
        for candidate in [clean, f"de_{clean}"]:
            path = os.path.join(maps_dir, f"{candidate}.png")
            if os.path.exists(path):
                self._map_pixmap = QPixmap(path)
                return

        # Partial match
        if os.path.isdir(maps_dir):
            for fname in os.listdir(maps_dir):
                if clean in fname and fname.endswith(".png"):
                    self._map_pixmap = QPixmap(os.path.join(maps_dir, fname))
                    return

        self._map_pixmap = None

    # ── Coordinate Transform ──

    def _map_geometry(self):
        """Return (map_size, offset_x, offset_y) for centered square map."""
        ms = min(self.width(), self.height())
        ox = (self.width() - ms) / 2
        oy = (self.height() - ms) / 2
        return ms, ox, oy

    def _world_to_screen(self, x: float, y: float) -> tuple:
        nx, ny = SpatialEngine.world_to_normalized(x, y, self._map_name)
        ms, ox, oy = self._map_geometry()
        # Qt top-left origin matches radar image origin — no Y inversion
        return (nx * ms + ox, ny * ms + oy)

    # ── Paint ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        ms, ox, oy = self._map_geometry()

        # Layer 1: Map image
        if self._map_pixmap and not self._map_pixmap.isNull():
            scaled = self._map_pixmap.scaled(
                int(ms), int(ms), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            painter.drawPixmap(int(ox), int(oy), scaled)
        else:
            painter.fillRect(QRectF(ox, oy, ms, ms), QColor(25, 25, 30))
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(
                QRectF(ox, oy, ms, ms),
                Qt.AlignCenter,
                f"Map: {self._map_name}",
            )

        # Layer 2: Grenades
        for nade in self._nades:
            self._draw_nade(painter, nade)

        # Layer 3: Ghosts
        for ghost in self._ghosts:
            self._draw_player(painter, ghost, is_ghost=True)

        # Layer 4: Players
        for player in self._players:
            self._draw_player(painter, player)

        painter.end()

    # ── Player Drawing ──

    def _draw_player(self, p: QPainter, player: InterpolatedPlayerState, is_ghost=False):
        px, py = self._world_to_screen(player.x, player.y)

        is_ct = player.team == Team.CT if isinstance(player.team, Team) else "CT" in str(player.team).upper()

        if not player.is_alive:
            color = QColor(DEAD_COLOR)
        elif is_ct:
            color = QColor(CT_COLOR)
        else:
            color = QColor(T_COLOR)

        if is_ghost or getattr(player, "is_ghost", False):
            color.setAlpha(77)

        r = PLAYER_RADIUS

        # Selection highlight
        if player.player_id == self._selected_player_id:
            p.setPen(Qt.NoPen)
            p.setBrush(SELECTED_COLOR)
            p.drawEllipse(QPointF(px, py), r + 4, r + 4)

        # Player circle
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(px, py), r, r)

        # FoV cone (alive only)
        if player.is_alive:
            p.save()
            p.translate(px, py)
            p.rotate(90 - player.yaw)

            cone_color = QColor(color)
            cone_color.setAlpha(77)
            p.setPen(Qt.NoPen)
            p.setBrush(cone_color)

            # Triangle pointing up (-Y in Qt = north on map)
            cone = QPolygonF([
                QPointF(0, 0),
                QPointF(-15, -30),
                QPointF(15, -30),
            ])
            p.drawPolygon(cone)
            p.restore()

        # Player name (above)
        p.setPen(QColor(255, 255, 255))
        p.setFont(self._name_font)
        tw = self._name_fm.horizontalAdvance(player.name)
        p.drawText(int(px - tw / 2), int(py - r - 4), player.name)

        # Health bar (below)
        if player.is_alive:
            bar_w = r * 2
            bar_h = 2
            bar_x = px - r
            bar_y = py + r + 2
            p.fillRect(QRectF(bar_x, bar_y, bar_w, bar_h), QColor(0, 0, 0, 128))
            hp_color = QColor(0, 255, 0, 204) if player.hp > 50 else QColor(255, 0, 0, 204)
            p.fillRect(QRectF(bar_x, bar_y, bar_w * (player.hp / 100.0), bar_h), hp_color)

    # ── Grenade Drawing ──

    def _draw_nade(self, p: QPainter, nade):
        start_vis = nade.throw_tick or nade.starting_tick
        end_vis = nade.ending_tick + (5 * TICK_RATE)
        if not (start_vis <= self._current_tick <= end_vis):
            return

        # Interpolate position if in flight
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

        sx, sy = self._world_to_screen(nx, ny)

        # Trajectory
        if nade.throw_tick and self._current_tick >= nade.throw_tick:
            self._draw_trajectory(p, nade)

        # Detonation radius overlay
        if nade.starting_tick <= self._current_tick <= nade.ending_tick:
            self._draw_detonation_overlay(p, nade, sx, sy)

        # Active effect
        if nade.starting_tick <= self._current_tick <= nade.ending_tick:
            if nade.nade_type == NadeType.SMOKE:
                age = (self._current_tick - nade.starting_tick) / float(TICK_RATE)
                size = min(85, 20 + age * 18) if age > 0 else 60
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(179, 179, 204, 89))
                p.drawEllipse(QPointF(sx, sy), size / 2, size / 2)
                p.setBrush(QColor(230, 230, 255, 26))
                p.drawEllipse(QPointF(sx, sy), size * 0.4, size * 0.4)
            elif nade.nade_type == NadeType.MOLOTOV:
                pulse = 0.5 + 0.15 * math.sin(self._current_tick / TICK_RATE * 8)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 77, 0, int(pulse * 255)))
                p.drawEllipse(QPointF(sx, sy), 25, 25)
                p.setBrush(QColor(255, 179, 0, int((0.2 + pulse * 0.2) * 255)))
                p.drawEllipse(QPointF(sx, sy), 15, 15)

            # Duration progress arc
            total_ticks = nade.ending_tick - nade.starting_tick
            if total_ticks > 0:
                progress = 1.0 - ((self._current_tick - nade.starting_tick) / total_ticks)
                if progress > 0:
                    p.setPen(QPen(QColor(255, 255, 255, 153), 2))
                    p.setBrush(Qt.NoBrush)
                    span = int(progress * 360 * 16)
                    p.drawArc(QRectF(sx - 10, sy - 10, 20, 20), 90 * 16, span)

        # Central dot
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QPointF(sx, sy), 3, 3)

    def _draw_detonation_overlay(self, p: QPainter, nade, sx, sy):
        radius_units = GRENADE_RADII.get(nade.nade_type)
        if radius_units is None:
            return

        color = GRENADE_OVERLAY_COLORS.get(nade.nade_type, QColor(255, 255, 255))
        origin_px, _ = self._world_to_screen(nade.x, nade.y)
        edge_px, _ = self._world_to_screen(nade.x + radius_units, nade.y)
        pixel_radius = abs(edge_px - origin_px)
        if pixel_radius < 2:
            return

        base_alpha = 25 if nade.nade_type == NadeType.FLASH else 38

        # Radius fill
        fill = QColor(color)
        fill.setAlpha(base_alpha)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawEllipse(QPointF(sx, sy), pixel_radius, pixel_radius)

        # Border ring
        border = QColor(color)
        border.setAlpha(base_alpha + 38)
        p.setPen(QPen(border, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(sx, sy), pixel_radius, pixel_radius)

        # Flash inner zone (300 units)
        if nade.nade_type == NadeType.FLASH:
            inner_edge, _ = self._world_to_screen(nade.x + 300, nade.y)
            inner_r = abs(inner_edge - origin_px)
            if inner_r > 2:
                inner_fill = QColor(color)
                inner_fill.setAlpha(51)
                p.setPen(Qt.NoPen)
                p.setBrush(inner_fill)
                p.drawEllipse(QPointF(sx, sy), inner_r, inner_r)

    def _draw_trajectory(self, p: QPainter, nade):
        if not nade.trajectory or len(nade.trajectory) < 2:
            return

        fade_start = nade.starting_tick + (3 * TICK_RATE)
        base_alpha = 0.5
        if self._current_tick > fade_start:
            base_alpha = max(0, 0.5 - (self._current_tick - fade_start) / (2 * float(TICK_RATE)))
        if base_alpha <= 0:
            return

        if nade.nade_type == NadeType.SMOKE:
            rgb = (179, 179, 204)
        elif nade.nade_type == NadeType.MOLOTOV:
            rgb = (255, 102, 0)
        elif nade.nade_type == NadeType.FLASH:
            rgb = (255, 255, 255)
        else:
            rgb = (255, 51, 51)

        min_z = min(pt[2] for pt in nade.trajectory)
        max_z = max(pt[2] for pt in nade.trajectory)
        z_range = max(1.0, max_z - min_z)

        last_sx, last_sy = None, None
        apex_idx = 0
        cur_max_z = float("-inf")

        for i, (wx, wy, wz) in enumerate(nade.trajectory):
            sx, sy = self._world_to_screen(wx, wy)
            if wz > cur_max_z:
                cur_max_z = wz
                apex_idx = i

            if i > 0 and last_sx is not None:
                rel_h = (wz - min_z) / z_range
                seg_width = 1.0 + rel_h * 2.5
                seg_alpha = int(base_alpha * (0.6 + rel_h * 0.4) * 255)
                p.setPen(QPen(QColor(rgb[0], rgb[1], rgb[2], seg_alpha), seg_width))
                p.drawLine(QPointF(last_sx, last_sy), QPointF(sx, sy))

            last_sx, last_sy = sx, sy

        # Apex marker
        if apex_idx < len(nade.trajectory):
            ax, ay, _ = nade.trajectory[apex_idx]
            apx, apy = self._world_to_screen(ax, ay)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, int(base_alpha * 0.8 * 255)))
            p.drawEllipse(QPointF(apx, apy), 3, 3)

    # ── Mouse Handling ──

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        mx = event.position().x()
        my = event.position().y()

        for player in self._players:
            px, py = self._world_to_screen(player.x, player.y)
            if math.hypot(mx - px, my - py) < PLAYER_RADIUS * HITBOX_MULTIPLIER:
                new_id = player.player_id if self._selected_player_id != player.player_id else None
                self.selected_player_id = new_id
                return

        self.selected_player_id = None
