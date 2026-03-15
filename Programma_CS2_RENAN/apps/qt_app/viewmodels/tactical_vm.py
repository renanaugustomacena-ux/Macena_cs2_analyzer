"""Tactical Viewer ViewModels — Qt port of desktop_app/tactical_viewmodels.py."""

import threading
from dataclasses import is_dataclass, replace
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from Programma_CS2_RENAN.core.playback_engine import InterpolatedFrame
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_tactical_vm")

CM_NAVIGATION_BUFFER_TICKS = 32


class _WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)


class _Worker(QRunnable):
    def __init__(self, fn, *args):
        super().__init__()
        self.fn = fn
        self.args = args
        self.signals = _WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


# ── Playback ViewModel ──


class TacticalPlaybackVM(QObject):
    """Playback control: play/pause, speed, seek, tick tracking."""

    is_playing_changed = Signal(bool)
    current_tick_changed = Signal(int)
    total_ticks_changed = Signal(int)
    speed_changed = Signal(float)
    frame_updated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = None
        self._is_playing = False
        self._current_tick = 0
        self._total_ticks = 0
        self._speed = 1.0

    def set_engine(self, engine):
        self._engine = engine
        if engine:
            engine.set_on_frame_update(self._handle_frame)

    def _handle_frame(self, frame: InterpolatedFrame):
        if self._engine:
            tick = self._engine.get_current_tick()
            if tick != self._current_tick:
                self._current_tick = tick
                self.current_tick_changed.emit(tick)
            playing = self._engine.is_playing()
            if playing != self._is_playing:
                self._is_playing = playing
                self.is_playing_changed.emit(playing)
        self.frame_updated.emit(frame)

    def load_frames(self, frames: List):
        if self._engine:
            self._engine.load_frames(frames)
            self._total_ticks = self._engine.get_total_ticks()
            self.total_ticks_changed.emit(self._total_ticks)

    def toggle_playback(self):
        if self._engine:
            self._engine.toggle_play_pause()
            self._is_playing = self._engine.is_playing()
            self.is_playing_changed.emit(self._is_playing)

    def set_speed(self, speed: float):
        self._speed = speed
        if self._engine:
            self._engine.set_speed(speed)
        self.speed_changed.emit(speed)

    def seek_to_tick(self, tick: int):
        if self._engine:
            self._engine.seek_to_tick(tick)
            self._current_tick = tick
            self.current_tick_changed.emit(tick)

    def get_current_tick(self) -> int:
        if self._engine:
            return self._engine.get_current_tick()
        return 0

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def total_ticks(self) -> int:
        return self._total_ticks


# ── Ghost ViewModel ──


class TacticalGhostVM(QObject):
    """Ghost AI predictions — lazy-loads GhostEngine."""

    ghost_active_changed = Signal(bool)
    is_loaded_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = None
        self._ghost_active = False
        self._is_loaded = False

    def set_active(self, active: bool):
        self._ghost_active = active
        self.ghost_active_changed.emit(active)
        if active:
            self._ensure_loaded()

    def _ensure_loaded(self):
        if not self._engine and self._ghost_active:
            try:
                from Programma_CS2_RENAN.backend.nn.inference.ghost_engine import (
                    GhostEngine,
                )

                self._engine = GhostEngine()
                self._is_loaded = True
                self.is_loaded_changed.emit(True)
            except Exception as e:
                logger.warning("GhostEngine load failed: %s", e)

    def predict_ghosts(self, players: List) -> List:
        if not self._ghost_active or not self._engine:
            return []

        ghosts = []
        for p in players:
            if p.is_alive and is_dataclass(p):
                try:
                    gx, gy = self._engine.predict_tick(p)
                    ghost = replace(p, x=gx, y=gy, is_ghost=True)
                    ghosts.append(ghost)
                except Exception as e:
                    logger.warning(
                        "Ghost prediction failed for %s: %s",
                        getattr(p, "name", "?"),
                        e,
                    )
        return ghosts

    def cleanup(self):
        self._engine = None
        self._is_loaded = False


# ── Chronovisor ViewModel ──


class TacticalChronovisorVM(QObject):
    """Critical moment scanning and navigation."""

    is_scanning_changed = Signal(bool)
    scan_complete = Signal(list, int)
    navigate_to = Signal(int, str)
    scan_error_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._critical_moments: List = []
        self._is_scanning = False
        self._scan_cancel = threading.Event()

    @property
    def critical_moments(self) -> List:
        return self._critical_moments

    def scan_match(self, match_id):
        if self._is_scanning:
            return
        self._is_scanning = True
        self.is_scanning_changed.emit(True)
        self._scan_cancel.clear()

        def _do_scan():
            if self._scan_cancel.is_set():
                return []

            from Programma_CS2_RENAN.core.config import get_setting

            if not get_setting("USE_RAP_MODEL", default=False):
                raise RuntimeError("RAP model disabled (USE_RAP_MODEL=False)")

            from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import (
                ChronovisorScanner,
            )

            scanner = ChronovisorScanner()
            result = scanner.scan_match(match_id)
            if result.success:
                cms = result.critical_moments
                cms.sort(key=lambda x: x.start_tick)
                return cms
            raise RuntimeError(result.error_message)

        worker = _Worker(_do_scan)
        worker.signals.result.connect(self._on_scan_done)
        worker.signals.error.connect(self._on_scan_error)
        QThreadPool.globalInstance().start(worker)

    def _on_scan_done(self, cms):
        self._critical_moments = cms if cms else []
        self._is_scanning = False
        self.is_scanning_changed.emit(False)
        self.scan_complete.emit(self._critical_moments, len(self._critical_moments))

    def _on_scan_error(self, error_msg: str):
        self._critical_moments = []
        self._is_scanning = False
        self.is_scanning_changed.emit(False)
        self.scan_error_changed.emit(error_msg)
        self.scan_complete.emit([], 0)

    def jump_to_next(self, current_tick: int) -> Optional[Tuple[int, str]]:
        if not self._critical_moments:
            return None
        for cm in self._critical_moments:
            if cm.peak_tick > current_tick + CM_NAVIGATION_BUFFER_TICKS:
                desc = f"{cm.type.upper()}: {cm.description}"
                self.navigate_to.emit(cm.start_tick, desc)
                return (cm.start_tick, desc)
        return None

    def jump_to_prev(self, current_tick: int) -> Optional[Tuple[int, str]]:
        if not self._critical_moments:
            return None
        target = None
        for cm in self._critical_moments:
            if cm.peak_tick < current_tick - CM_NAVIGATION_BUFFER_TICKS:
                target = cm
            else:
                break
        if target:
            desc = f"{target.type.upper()}: {target.description}"
            self.navigate_to.emit(target.start_tick, desc)
            return (target.start_tick, desc)
        return None

    def cancel_scan(self):
        self._scan_cancel.set()

    def clear(self):
        self._critical_moments = []
