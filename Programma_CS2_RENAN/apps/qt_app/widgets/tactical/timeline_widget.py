"""Interactive timeline scrubber with event markers."""

from typing import Callable, List, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from Programma_CS2_RENAN.core.demo_frame import EventType, GameEvent

COLOR_BG = QColor(51, 51, 51)
COLOR_PROGRESS = QColor(77, 179, 77)
COLOR_KILL = QColor(230, 51, 51, 204)
COLOR_PLANT = QColor(230, 204, 51, 204)
COLOR_DEFUSE = QColor(51, 153, 230, 204)


class TimelineWidget(QWidget):
    """QPainter-based timeline with event markers and seek interaction."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_tick = 0
        self._max_tick = 0
        self._game_events: List[GameEvent] = []
        self._seek_callback: Optional[Callable[[int], None]] = None

        self.setFixedHeight(40)
        self.setMouseTracking(False)

    # ── Public API ──

    @property
    def current_tick(self) -> int:
        return self._current_tick

    @current_tick.setter
    def current_tick(self, value: int):
        if self._current_tick != value:
            self._current_tick = value
            self.update()

    @property
    def max_tick(self) -> int:
        return self._max_tick

    @max_tick.setter
    def max_tick(self, value: int):
        self._max_tick = value
        self.update()

    def set_events(self, events: List[GameEvent]):
        self._game_events = events
        self.update()

    def set_seek_callback(self, callback: Callable[[int], None]):
        self._seek_callback = callback

    # ── Paint ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()

        # Background
        p.fillRect(0, 0, w, h, COLOR_BG)

        if self._max_tick <= 0:
            # Empty state
            p.setPen(QColor(128, 128, 128, 204))
            p.setFont(QFont("Roboto", 10))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "Load a demo to enable timeline")
            p.end()
            return

        # Progress bar
        ratio = self._current_tick / self._max_tick
        p.fillRect(QRectF(0, 0, w * ratio, h), COLOR_PROGRESS)

        # Event markers
        for evt in self._game_events:
            if evt.event_type == EventType.KILL:
                p.fillRect(self._marker_rect(evt, w, h, 0.5), COLOR_KILL)
            elif evt.event_type == EventType.BOMB_PLANT:
                p.fillRect(self._marker_rect(evt, w, h, 1.0), COLOR_PLANT)
            elif evt.event_type == EventType.BOMB_DEFUSE:
                p.fillRect(self._marker_rect(evt, w, h, 1.0), COLOR_DEFUSE)

        p.end()

    def _marker_rect(self, evt: GameEvent, w: float, h: float, h_factor: float) -> QRectF:
        evt_x = (evt.tick / self._max_tick) * w
        return QRectF(evt_x, 0, 2, h * h_factor)

    # ── Mouse Handling ──

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._handle_seek(event.position().x())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._handle_seek(event.position().x())

    def _handle_seek(self, x: float):
        if self._max_tick <= 0 or self.width() <= 0:
            return
        ratio = max(0.0, min(1.0, x / self.width()))
        target_tick = int(ratio * self._max_tick)
        if self._seek_callback:
            self._seek_callback(target_tick)
