from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.graphics.instructions import InstructionGroup
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from Programma_CS2_RENAN.core.spatial_data import LANDMARKS, MapMetadata
from Programma_CS2_RENAN.core.spatial_engine import SpatialEngine

RADAR_REFERENCE_SIZE = 1024  # Standard radar image pixel dimensions


class GhostPixelValidator(Widget):
    """
    Debug overlay for validating coordinate transformations.
    Enable via console or hidden trigger.

    F7-38: GhostPixel debug overlay is importable in production. No functional risk
    unless explicitly instantiated. Gate with DEBUG config flag when hardening for release.
    """

    map_meta = ObjectProperty(None, allownone=True)
    map_name = StringProperty("de_dust2")
    active = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.lbl = Label(
            text="GHOST VALIDATOR: ACTIVE",
            pos=(10, 10),
            size_hint=(None, None),
            color=(1, 1, 1, 1),
            bold=True,
            font_size="12sp",
        )
        # Background for the label
        with self.lbl.canvas.before:
            Color(0, 0, 0, 0.7)
            self.bg_rect = Rectangle(pos=self.lbl.pos, size=self.lbl.size)

        self.add_widget(self.lbl)

        # Separate InstructionGroups to avoid flicker on crosshair updates
        self._landmark_group = InstructionGroup()
        self._crosshair_group = InstructionGroup()
        self.canvas.after.add(self._landmark_group)
        self.canvas.after.add(self._crosshair_group)

        self.bind(pos=self._update_bg, size=self._update_bg)

    def _update_bg(self, *args):
        self.bg_rect.pos = self.lbl.pos
        self.bg_rect.size = self.lbl.size
        self._render_landmarks()

    def on_active(self, instance, value):
        if value:
            self._render_landmarks()
        else:
            self._landmark_group.clear()
            self._crosshair_group.clear()

    def _render_landmarks(self):
        if not self.active or not self.map_meta:
            return

        self._landmark_group.clear()
        landmarks = LANDMARKS.get(self.map_name, {})

        for name, (wx, wy) in landmarks.items():
            nx, ny = self.map_meta.world_to_radar(wx, wy)
            lx = nx * self.width
            ly = (1.0 - ny) * self.height

            self._landmark_group.add(Color(0, 1, 1, 0.6))
            self._landmark_group.add(Line(circle=(self.x + lx, self.y + ly, 5), width=1))

    def on_touch_down(self, touch):
        if not self.active:
            return False
        if not self.collide_point(*touch.pos):
            return False

        self.update_debug_info(touch)
        return True

    def on_touch_move(self, touch):
        if not self.active:
            return False
        if not self.collide_point(*touch.pos):
            return False

        self.update_debug_info(touch)
        return True

    def update_debug_info(self, touch):
        if not self.map_meta:
            self.lbl.text = "GHOST: NO METADATA"
            self.lbl.size = self.lbl.texture_size
            return

        # 1. Coordinate Reverse Mapping (Pixel -> World)
        # Using the standardized SpatialEngine logic

        # Normalize touch relative to this widget
        nx = (touch.x - self.x) / self.width
        ny = (touch.y - self.y) / self.height

        # Apply Y-flip (Kivy bottom-up -> Valve top-down)
        v_ny = 1.0 - ny

        # Reverse projection
        sz = RADAR_REFERENCE_SIZE
        wx, wy = SpatialEngine.pixel_to_world(nx * sz, v_ny * sz, self.map_name, sz, sz)

        self.lbl.text = (
            f" [ GHOST CALIBRATION ] \n"
            f" MAP: {self.map_name}\n"
            f" NRM: {nx:.3f}, {ny:.3f}\n"
            f" WLD: {wx:.1f}, {wy:.1f}"
        )
        self.lbl.size = self.lbl.texture_size
        self.lbl.pos = (touch.x + 20, touch.y + 20)
        self._update_bg()

        # Visual Crosshair — only redraws crosshair group, landmarks untouched
        self._crosshair_group.clear()
        self._crosshair_group.add(Color(1, 0, 1, 1))
        self._crosshair_group.add(Line(circle=(touch.x, touch.y, 10), width=1.5))
        self._crosshair_group.add(
            Line(points=[touch.x - 20, touch.y, touch.x + 20, touch.y], width=1)
        )
        self._crosshair_group.add(
            Line(points=[touch.x, touch.y - 20, touch.x, touch.y + 20], width=1)
        )
