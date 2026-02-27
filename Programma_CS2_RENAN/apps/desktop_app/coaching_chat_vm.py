"""
Coaching Chat ViewModel
=======================
MVVM ViewModel for the coaching dialogue chat panel on CoachScreen.

Follows the same pattern as tactical_viewmodels.py:
- EventDispatcher with Kivy Properties
- Daemon threads for backend calls
- Clock.schedule_once to marshal results back to the UI thread
"""

import threading
from threading import Thread
from typing import Optional

from kivy.clock import Clock
from kivy.event import EventDispatcher
from kivy.properties import BooleanProperty, ListProperty

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.coaching_chat_vm")


class CoachingChatViewModel(EventDispatcher):
    """ViewModel for the coaching dialogue chat panel."""

    messages = ListProperty([])
    is_loading = BooleanProperty(False)
    is_available = BooleanProperty(False)
    session_active = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._engine = None
        self._messages_lock = threading.Lock()  # F7-24: protect messages list from concurrent access

    # ------------------------------------------------------------------
    # Lazy engine access (avoids heavy import at startup)
    # ------------------------------------------------------------------

    def _ensure_engine(self):
        if self._engine is None:
            from Programma_CS2_RENAN.backend.services.coaching_dialogue import get_dialogue_engine

            self._engine = get_dialogue_engine()

    # ------------------------------------------------------------------
    # Public API — called from CoachScreen
    # ------------------------------------------------------------------

    def check_availability(self):
        """Check Ollama availability in a background thread."""

        def _check():
            try:
                self._ensure_engine()
                available = self._engine.is_available
                Clock.schedule_once(lambda dt: self._set_available(available), 0)
            except Exception as e:
                logger.error("Availability check failed: %s", e)
                Clock.schedule_once(lambda dt: self._set_available(False), 0)

        Thread(target=_check, daemon=True).start()

    def start_session(
        self,
        player_name: str,
        demo_name: Optional[str] = None,
    ):
        """Start a coaching session (background thread)."""
        if self.session_active:
            return

        self.is_loading = True

        def _start():
            try:
                self._ensure_engine()
                opening = self._engine.start_session(player_name, demo_name)
                Clock.schedule_once(lambda dt: self._on_session_started(opening), 0)
            except Exception as e:
                logger.error("Session start failed: %s", e)
                fallback = "Coach is currently offline. I can still help with cached knowledge — ask me anything!"
                Clock.schedule_once(lambda dt: self._on_session_started(fallback), 0)

        Thread(target=_start, daemon=True).start()

    def send_message(self, text: str):
        """Send a user message and get a coaching response."""
        text = text.strip()
        if not text or self.is_loading:
            return

        # Immediately show user message in UI
        with self._messages_lock:  # F7-24: guard concurrent message list access
            self.messages.append({"role": "user", "content": text})
        self.is_loading = True

        def _respond():
            try:
                self._ensure_engine()
                response = self._engine.respond(text)
            except Exception as e:
                logger.error("Chat response failed: %s", e)
                response = "[Coach offline] Unable to generate response. Please check if Ollama is running."
            Clock.schedule_once(lambda dt: self._on_response(response), 0)

        Thread(target=_respond, daemon=True).start()

    def clear_session(self):
        """Clear the conversation and reset state."""
        if self._engine is not None:
            self._engine.clear_session()
        self.messages = []
        self.session_active = False
        self.is_loading = False
        logger.info("Chat session cleared via ViewModel")

    # ------------------------------------------------------------------
    # Internal callbacks (run on main/UI thread via Clock.schedule_once)
    # ------------------------------------------------------------------

    def _set_available(self, available: bool):
        self.is_available = available

    def _on_session_started(self, opening: str):
        self.messages.append({"role": "assistant", "content": opening})
        self.session_active = True
        self.is_loading = False
        logger.info("Chat session started")

    def _on_response(self, response: str):
        with self._messages_lock:  # F7-24: lock before appending assistant response
            self.messages.append({"role": "assistant", "content": response})
        self.is_loading = False
