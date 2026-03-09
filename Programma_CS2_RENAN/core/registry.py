"""
Macena CS2 Analyzer - System Registry
Based on Senior Software Architecture registration patterns.
Handles decoupling of Screens, Models, and Tasks.
"""

import threading
from typing import Any, Dict, Optional, Type

from kivymd.uix.screen import MDScreen

# REG-01: Lock protects _mapping against concurrent register/get from multiple threads.
_registry_lock = threading.Lock()


class ScreenRegistry:
    """
    Central registry for KivyMD Screens.
    Prevents direct hardcoding of screen classes in the ScreenManager.
    """

    _mapping: Dict[str, Type[MDScreen]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a screen class."""

        def wrap(screen_cls):
            with _registry_lock:
                if name in cls._mapping:
                    raise KeyError(f"Screen '{name}' already registered for {cls._mapping[name]}")
                cls._mapping[name] = screen_cls
            return screen_cls

        return wrap

    @classmethod
    def get_screen_class(cls, name: str) -> Optional[Type[MDScreen]]:
        with _registry_lock:
            return cls._mapping.get(name)

    @classmethod
    def list_screens(cls):
        with _registry_lock:
            return sorted(cls._mapping.keys())


# Global registry instance
registry = ScreenRegistry()
