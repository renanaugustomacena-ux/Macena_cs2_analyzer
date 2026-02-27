from typing import List, Optional

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle
from kivy.properties import ListProperty, NumericProperty
from kivy.uix.widget import Widget

from Programma_CS2_RENAN.core.demo_frame import EventType, GameEvent


class TimelineScrubber(Widget):
    """
    Interactive timeline widget for the tactical viewer.
    Displays match progress and event markers (kills, plants).
    """

    current_tick = NumericProperty(0)
    max_tick = NumericProperty(1000)

    # Event Colors
    COLOR_KILL = (0.9, 0.2, 0.2, 0.8)  # Red
    COLOR_PLANT = (0.9, 0.8, 0.2, 0.8)  # Yellow
    COLOR_DEFUSE = (0.2, 0.6, 0.9, 0.8)  # Blue
    COLOR_BG = (0.2, 0.2, 0.2, 1)
    COLOR_PROGRESS = (0.3, 0.7, 0.3, 1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game_events: List[GameEvent] = []
        self.bind(pos=self._redraw, size=self._redraw, current_tick=self._redraw)
        self.metadata_textures = {}
        self._callback_seek = None

    def set_events(self, events: List[GameEvent]):
        """Load game events to display markers."""
        self.game_events = events
        self._redraw()

    def set_seek_callback(self, callback):
        """Callback(tick: int) when user interacts."""
        self._callback_seek = callback

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._handle_touch(touch)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.collide_point(*touch.pos):
            self._handle_touch(touch)
            return True
        return super().on_touch_move(touch)

    def _handle_touch(self, touch):
        """Calculate tick from touch x position."""
        if self.width <= 0:
            return

        # Normalized x (0.0 to 1.0)
        nx = (touch.x - self.x) / self.width
        nx = max(0.0, min(1.0, nx))  # F7-33: clamp to [0.0, 1.0] — prevents out-of-range seeks

        target_tick = int(nx * self.max_tick)

        # Snap to event? (Optional enhancement)

        if self._callback_seek:
            self._callback_seek(target_tick)

    def _redraw(self, *args):
        self.canvas.clear()

        if self.max_tick <= 0:
            return

        with self.canvas:
            # 1. Background Bar
            Color(*self.COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)

            # 2. Progress Bar
            progress_ratio = self.current_tick / self.max_tick
            bar_width = self.width * progress_ratio
            Color(*self.COLOR_PROGRESS)
            Rectangle(pos=self.pos, size=(bar_width, self.height))

            # 3. Draw Event Markers
            # Optimization: Don't draw if too many? For now logic is simple.
            for evt in self.game_events:
                # Determine color
                if evt.event_type == EventType.KILL:
                    Color(*self.COLOR_KILL)
                    h_factor = 0.5  # Half height for kills
                elif evt.event_type == EventType.BOMB_PLANT:
                    Color(*self.COLOR_PLANT)
                    h_factor = 1.0
                elif evt.event_type == EventType.BOMB_DEFUSE:
                    Color(*self.COLOR_DEFUSE)
                    h_factor = 1.0
                else:
                    continue

                # Position
                evt_ratio = evt.tick / self.max_tick
                ex = self.x + evt_ratio * self.width
                ey = self.y
                ew = 2  # 2px wide marker
                eh = self.height * h_factor

                Rectangle(pos=(ex, ey), size=(ew, eh))
