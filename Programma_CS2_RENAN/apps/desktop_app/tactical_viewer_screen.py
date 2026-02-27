"""
Tactical Viewer Screen
======================
[TASK 8.4.1] Refactored to use ViewModel pattern.

This screen acts as a thin UI layer that coordinates between:
- TacticalPlaybackViewModel: Playback control
- TacticalGhostViewModel: AI ghost predictions
- TacticalChronovisorViewModel: Critical moment detection

The ViewModels handle business logic while this screen handles
UI binding and widget coordination.
"""

import os
from dataclasses import replace

from kivy.clock import Clock
from kivy.properties import (
    BooleanProperty,
    DictProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivymd.uix.screen import MDScreen

from Programma_CS2_RENAN.apps.desktop_app.player_sidebar import PlayerSidebar
from Programma_CS2_RENAN.apps.desktop_app.tactical_map import TacticalMap
from Programma_CS2_RENAN.apps.desktop_app.tactical_viewmodels import (
    TacticalChronovisorViewModel,
    TacticalGhostViewModel,
    TacticalPlaybackViewModel,
)
from Programma_CS2_RENAN.apps.desktop_app.timeline import TimelineScrubber
from Programma_CS2_RENAN.core.demo_frame import EventType, Team
from Programma_CS2_RENAN.core.playback_engine import InterpolatedFrame, PlaybackEngine
from Programma_CS2_RENAN.core.registry import registry
from Programma_CS2_RENAN.ingestion.demo_loader import DemoLoader


@registry.register("tactical_viewer")
class TacticalViewerScreen(MDScreen):
    """
    Integrated Tactical Analysis Viewer Screen.

    This screen coordinates the UI widgets with the underlying ViewModels:
    - Playback controls (play/pause, speed, seek)
    - Ghost AI predictions
    - Chronovisor critical moment navigation
    """

    segments = DictProperty({})
    ghost_active = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initialize ViewModels
        self._playback_vm = TacticalPlaybackViewModel()
        self._ghost_vm = TacticalGhostViewModel()
        self._chronovisor_vm = TacticalChronovisorViewModel()

        # Create playback engine and bind to ViewModel
        self.engine = PlaybackEngine()
        self._playback_vm.set_engine(self.engine)
        self._playback_vm.set_on_frame_update(self.on_frame_update)

        # Set up chronovisor callbacks
        self._chronovisor_vm.set_on_scan_complete(self._on_cm_scan_complete)
        self._chronovisor_vm.set_on_navigate(self._on_cm_navigate)

        # Data storage
        self.full_demo_data = {}
        self.game_events = []

        # Tick UI timer — started/stopped via on_enter/on_leave
        self._tick_event = None

    # --- Property bindings ---

    def on_ghost_active(self, instance, value):
        """Sync ghost_active property with ViewModel."""
        self._ghost_vm.set_active(value)

    # --- Lifecycle ---

    def on_enter(self):
        """Called when screen becomes active."""
        self.ids.timeline.set_seek_callback(self.on_seek)

        # [SYNC] Bind map selection to sidebar update
        self.ids.tactical_map.bind(selected_player_id=self.on_map_selection)

        # Start tick UI timer only while this screen is active
        if self._tick_event is None:
            self._tick_event = Clock.schedule_interval(self.update_tick_ui, 0.1)

        # Implementation of One-Click Selection Rule:
        # Trigger picker automatically when entering the screen if empty
        if not self.full_demo_data:
            from kivymd.app import MDApp

            def _safe_trigger_picker(dt):
                app = MDApp.get_running_app()
                if app and self.manager and self.manager.current == self.name:
                    app.trigger_viewer_picker()

            Clock.schedule_once(_safe_trigger_picker, 0.5)

    def on_leave(self):
        """Called when screen is left — release the tick timer."""
        if self._tick_event is not None:
            self._tick_event.cancel()
            self._tick_event = None

    # --- Data Loading ---

    def switch_map(self, map_name):
        """
        Switch to a different map's demo data.

        Args:
            map_name: The map identifier to switch to
        """
        if map_name not in self.full_demo_data:
            return

        frames, events, segments = self.full_demo_data[map_name]
        self.game_events = events
        self.segments = segments

        # Update UI widgets
        self.ids.map_spinner.text = map_name
        self.ids.tactical_map.map_name = map_name

        # Load frames via ViewModel
        self._playback_vm.load_frames(frames)

        # Update timeline
        self.ids.timeline.max_tick = self._playback_vm.total_ticks
        self.ids.timeline.set_events(events)

        # Reset round spinner
        self.ids.round_spinner.values = list(segments.keys())
        self.ids.round_spinner.text = "Full Match"

        # Seek to start
        self._playback_vm.seek_to_tick(0)
        self.ids.tactical_map._redraw()

        # Clear previous chronovisor results
        self._chronovisor_vm.clear()

    # --- Frame Rendering ---

    def on_frame_update(self, frame: InterpolatedFrame):
        """
        Handle frame updates from the playback engine.

        Coordinates rendering across TacticalMap and PlayerSidebars.
        """
        self.last_frame = frame

        # Get ghost predictions via ViewModel
        ghosts = self._ghost_vm.predict_ghosts(frame.players)

        # Update tactical map
        self.ids.tactical_map.update_map(frame.players, frame.nades, ghosts, frame.tick)

        # Update sidebars by team
        ct_players = [p for p in frame.players if p.team == Team.CT]
        t_players = [p for p in frame.players if p.team == Team.T]

        selected_id = self.ids.tactical_map.selected_player_id
        self.ids.ct_sidebar.update_players(ct_players, selected_id)
        self.ids.t_sidebar.update_players(t_players, selected_id)

    def update_tick_ui(self, dt):
        """Periodic UI update for tick display and button state."""
        # F7-27: Guard against stale callback firing after screen navigation
        if not self.manager or self.manager.current != self.name:
            return
        current = self._playback_vm.get_current_tick()
        self.ids.tick_label.text = f"Tick: {current}"
        self.ids.timeline.current_tick = current

        # Sync play button icon with actual playback state
        self.ids.play_btn.icon = "pause" if self._playback_vm.is_playing else "play"

    # --- Playback Controls ---

    def toggle_playback(self):
        """Toggle play/pause via ViewModel."""
        self._playback_vm.toggle_playback()
        self.ids.play_btn.icon = "pause" if self._playback_vm.is_playing else "play"

    def set_speed(self, speed):
        """Set playback speed via ViewModel."""
        self._playback_vm.set_speed(speed)

    def on_seek(self, tick):
        """Handle seek requests via ViewModel."""
        self._playback_vm.seek_to_tick(tick)

    def on_round_change(self, text):
        """Handle round/segment selection."""
        if text in self.segments:
            self.on_seek(self.segments[text])

    def select_player(self, player_id):
        """Handle player selection on tactical map."""
        self.ids.tactical_map.selected_player_id = player_id
        # Redraw is handled by property binding in map

    def on_map_selection(self, instance, value):
        """Handle selection changes from the map immediately."""
        if not hasattr(self, "last_frame") or not self.last_frame:
            return

        frame = self.last_frame
        # Update sidebars with current selection
        ct_players = [p for p in frame.players if p.team == Team.CT]
        t_players = [p for p in frame.players if p.team == Team.T]

        # Safe access to sidebar
        if hasattr(self.ids, "ct_sidebar") and hasattr(self.ids, "t_sidebar"):
            self.ids.ct_sidebar.update_players(ct_players, value)
            self.ids.t_sidebar.update_players(t_players, value)

    # --- Chronovisor Integration ---

    def scan_for_critical_moments(self, match_id):
        """
        Start scanning for critical moments.

        Args:
            match_id: The match identifier to scan
        """
        self._chronovisor_vm.scan_match(match_id)

    def _on_cm_scan_complete(self, cms, count):
        """Handle chronovisor scan completion."""
        from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText

        if count > 0:
            MDSnackbar(MDSnackbarText(text=f"Detected {count} critical moments")).open()
        else:
            error = getattr(self._chronovisor_vm, "scan_error", None)
            if error:
                MDSnackbar(MDSnackbarText(text=f"Scan failed: {error}")).open()
            else:
                MDSnackbar(MDSnackbarText(text="No critical moments detected")).open()

    def _on_cm_navigate(self, tick, description):
        """Handle chronovisor navigation."""
        self._playback_vm.seek_to_tick(tick)

    def jump_to_next_cm(self):
        """Jump to the next critical moment."""
        current = self._playback_vm.get_current_tick()
        result = self._chronovisor_vm.jump_to_next(current)
        if result is None:
            from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText

            MDSnackbar(MDSnackbarText(text="No further critical moments")).open()

    def jump_to_prev_cm(self):
        """Jump to the previous critical moment."""
        current = self._playback_vm.get_current_tick()
        result = self._chronovisor_vm.jump_to_prev(current)
        if result is None:
            from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText

            MDSnackbar(MDSnackbarText(text="Start of analysis reached")).open()

    # --- Legacy Compatibility ---

    @property
    def critical_moments(self):
        """Legacy property for backward compatibility."""
        return self._chronovisor_vm.critical_moments

    def _scan_for_cms(self, match_id):
        """Legacy method for backward compatibility."""
        self.scan_for_critical_moments(match_id)
