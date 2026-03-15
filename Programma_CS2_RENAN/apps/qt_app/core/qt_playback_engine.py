"""Qt-compatible PlaybackEngine — replaces Kivy Clock with QTimer."""

import time

from PySide6.QtCore import QTimer

from Programma_CS2_RENAN.core.playback_engine import PlaybackEngine


class QtPlaybackEngine(PlaybackEngine):
    """PlaybackEngine subclass using QTimer instead of kivy.clock.Clock."""

    def __init__(self):
        super().__init__()
        self._timer = QTimer()
        self._timer.setInterval(16)  # ~60 FPS
        self._timer.timeout.connect(self._qt_tick)
        self._last_time = 0.0
        self._clock_event = None  # Prevent parent from using Kivy Clock

    def play(self):
        if not self._is_playing and len(self._frames) > 0:
            if self._current_index >= len(self._frames) - 1:
                self._current_index = 0
                self._sub_tick = 0.0
            self._is_playing = True
            self._last_time = time.monotonic()
            self._timer.start()

    def pause(self):
        if self._is_playing:
            self._is_playing = False
            self._timer.stop()

    def _qt_tick(self):
        now = time.monotonic()
        dt = now - self._last_time
        self._last_time = now
        self._tick(dt)
