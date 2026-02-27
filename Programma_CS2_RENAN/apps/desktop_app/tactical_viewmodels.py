"""
Tactical Viewer ViewModels
==========================
[TASK 8.4.1] ViewModel pattern implementation for TacticalViewerScreen.

This module separates the concerns of the TacticalViewerScreen into
distinct, testable ViewModels following the MVVM pattern:

- TacticalPlaybackViewModel: Playback state, speed, seeking
- TacticalGhostViewModel: Ghost engine lazy loading and predictions
- TacticalChronovisorViewModel: Critical moment scanning and navigation

This refactoring reduces the "God Object" anti-pattern and improves
maintainability, testability, and separation of concerns.
"""

import logging
import threading
from dataclasses import is_dataclass, replace
from threading import Thread
from typing import Any, Callable, List, Optional, Tuple

from kivy.event import EventDispatcher

logger = logging.getLogger("cs2analyzer.tactical_viewmodels")

# Tick buffer to avoid getting stuck on same critical moment when navigating
CM_NAVIGATION_BUFFER_TICKS = 32
from kivy.clock import Clock
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)


class TacticalPlaybackViewModel(EventDispatcher):
    """
    ViewModel for playback control.

    Manages:
    - Play/pause state
    - Playback speed
    - Seeking to specific ticks
    - Current tick tracking
    """

    is_playing = BooleanProperty(False)
    current_tick = NumericProperty(0)
    total_ticks = NumericProperty(0)
    speed = NumericProperty(1.0)

    def __init__(self, engine=None, **kwargs):
        super().__init__(**kwargs)
        self._engine = engine
        self._on_frame_callback = None

    def set_engine(self, engine):
        """Bind to a PlaybackEngine instance."""
        self._engine = engine
        if engine:
            engine.set_on_frame_update(self._handle_frame_update)

    def set_on_frame_update(self, callback: Callable):
        """Set callback for frame updates."""
        self._on_frame_callback = callback

    def _handle_frame_update(self, frame):
        """Internal handler that updates state and calls external callback."""
        if self._engine:
            self.current_tick = self._engine.get_current_tick()
            self.is_playing = self._engine.is_playing()
        if self._on_frame_callback:
            self._on_frame_callback(frame)

    def load_frames(self, frames: List):
        """Load frames into the playback engine."""
        if self._engine:
            self._engine.load_frames(frames)
            self.total_ticks = self._engine.get_total_ticks()

    def toggle_playback(self):
        """Toggle play/pause state."""
        if self._engine:
            self._engine.toggle_play_pause()
            self.is_playing = self._engine.is_playing()

    def set_speed(self, speed: float):
        """Set playback speed multiplier."""
        self.speed = speed
        if self._engine:
            self._engine.set_speed(speed)

    def seek_to_tick(self, tick: int):
        """Seek to a specific tick."""
        if self._engine:
            self._engine.seek_to_tick(tick)
            self.current_tick = tick

    def get_current_tick(self) -> int:
        """Get the current playback tick."""
        if self._engine:
            return self._engine.get_current_tick()
        return 0


class TacticalGhostViewModel(EventDispatcher):
    """
    ViewModel for Ghost Engine predictions.

    Manages:
    - Lazy loading of GhostEngine (prevents torch import on startup)
    - Ghost position predictions for players
    - Ghost active/inactive state
    """

    ghost_active = BooleanProperty(False)
    is_loaded = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._engine = None

    def _ensure_loaded(self):
        """Lazy load the GhostEngine to prevent startup freeze."""
        if not self._engine and self.ghost_active:
            from Programma_CS2_RENAN.backend.nn.inference.ghost_engine import GhostEngine

            self._engine = GhostEngine()
            self.is_loaded = True

    def set_active(self, active: bool):
        """Enable or disable ghost predictions."""
        self.ghost_active = active
        if active:
            self._ensure_loaded()

    def predict_ghosts(self, players: List) -> List:
        """
        Generate ghost predictions for alive players.

        Args:
            players: List of InterpolatedPlayerState objects

        Returns:
            List of ghost player states with predicted positions
        """
        if not self.ghost_active:
            return []

        self._ensure_loaded()
        if not self._engine:
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
                        "Ghost prediction failed for player %s: %s", getattr(p, "name", "?"), e
                    )
        return ghosts

    def cleanup(self):
        """Release GhostEngine resources."""
        self._engine = None
        self.is_loaded = False


class TacticalChronovisorViewModel(EventDispatcher):
    """
    ViewModel for Chronovisor Critical Moment detection and navigation.

    Manages:
    - Background scanning for critical moments
    - Navigation between critical moments
    - Scan state and results
    """

    is_scanning = BooleanProperty(False)
    scan_complete = BooleanProperty(False)
    cm_count = NumericProperty(0)
    scan_error = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._critical_moments: List = []
        self._on_scan_complete_callback: Optional[Callable] = None
        self._on_navigate_callback: Optional[Callable] = None
        self._scan_cancel = threading.Event()  # F7-25: cooperative cancellation flag

    def set_on_scan_complete(self, callback: Callable):
        """Set callback for when scan completes. Receives (cms, count)."""
        self._on_scan_complete_callback = callback

    def set_on_navigate(self, callback: Callable):
        """Set callback for navigation. Receives (tick, description)."""
        self._on_navigate_callback = callback

    @property
    def critical_moments(self) -> List:
        """Get the list of detected critical moments."""
        return self._critical_moments

    def scan_match(self, match_id: Any):
        """
        Start background scan for critical moments.

        Args:
            match_id: The match identifier to scan
        """
        if self.is_scanning:
            return

        self.is_scanning = True
        self.scan_complete = False
        self.scan_error = ""
        self._scan_cancel.clear()  # F7-25: reset cancellation flag before new scan

        def _scan():
            try:
                if self._scan_cancel.is_set():  # F7-25: pre-scan cancellation check
                    Clock.schedule_once(lambda dt: self._on_scan_done([]), 0)
                    return

                from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import (
                    ChronovisorScanner,
                )

                scanner = ChronovisorScanner()
                result = scanner.scan_match(match_id)

                if result.success:
                    cms = result.critical_moments
                    cms.sort(key=lambda x: x.start_tick)
                    Clock.schedule_once(lambda dt: self._on_scan_done(cms), 0)
                else:
                    Clock.schedule_once(lambda dt: self._on_scan_error(result.error_message), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_scan_error(f"Unexpected error: {e}"), 0)

        Thread(target=_scan, daemon=True).start()

    def _on_scan_done(self, cms: List):
        """Handle scan completion on main thread."""
        self._critical_moments = cms
        self.cm_count = len(cms)
        self.is_scanning = False
        self.scan_complete = True
        self.scan_error = ""

        if self._on_scan_complete_callback:
            self._on_scan_complete_callback(cms, len(cms))

    def _on_scan_error(self, error_message: str):
        """Handle scan failure on main thread."""
        self._critical_moments = []
        self.cm_count = 0
        self.is_scanning = False
        self.scan_complete = True
        self.scan_error = error_message or "Unknown scan error"

        if self._on_scan_complete_callback:
            self._on_scan_complete_callback([], 0)

    def jump_to_next(self, current_tick: int) -> Optional[Tuple[int, str]]:
        """
        Find and navigate to the next critical moment.

        Args:
            current_tick: Current playback tick

        Returns:
            Tuple of (tick, description) if found, None otherwise
        """
        if not self._critical_moments:
            return None

        buffer = CM_NAVIGATION_BUFFER_TICKS
        for cm in self._critical_moments:
            if cm.peak_tick > current_tick + buffer:
                if self._on_navigate_callback:
                    self._on_navigate_callback(
                        cm.start_tick, f"{cm.type.upper()}: {cm.description}"
                    )
                return (cm.start_tick, f"{cm.type.upper()}: {cm.description}")
        return None

    def jump_to_prev(self, current_tick: int) -> Optional[Tuple[int, str]]:
        """
        Find and navigate to the previous critical moment.

        Args:
            current_tick: Current playback tick

        Returns:
            Tuple of (tick, description) if found, None otherwise
        """
        if not self._critical_moments:
            return None

        buffer = CM_NAVIGATION_BUFFER_TICKS
        target = None
        for cm in self._critical_moments:
            if cm.peak_tick < current_tick - buffer:
                target = cm
            else:
                break

        if target:
            if self._on_navigate_callback:
                self._on_navigate_callback(
                    target.start_tick, f"{target.type.upper()}: {target.description}"
                )
            return (target.start_tick, f"{target.type.upper()}: {target.description}")
        return None

    def cancel_scan(self):
        """Request cancellation of an in-progress scan."""
        # F7-25: Sets the cancel event; background thread checks it cooperatively
        self._scan_cancel.set()

    def clear(self):
        """Clear all critical moments."""
        self._critical_moments = []
        self.cm_count = 0
        self.scan_complete = False
