"""
Localization bridge for Qt — wraps the existing translation system without Kivy deps.

Reuses the TRANSLATIONS dict and JSON loading from core/localization.py logic,
but without importing the Kivy-dependent LocalizationManager class.
"""

import json
import os
from typing import Dict

from PySide6.QtCore import QObject, Signal

from Programma_CS2_RENAN.core.config import get_resource_path
from Programma_CS2_RENAN.observability.logger_setup import get_logger

_logger = get_logger("cs2analyzer.qt_i18n")


def _get_home_dir() -> str:
    return os.path.expanduser("~")


# ── Hardcoded fallback translations (same as core/localization.py) ──
# We import them indirectly to avoid triggering the Kivy EventDispatcher import chain.
# The dict is duplicated here ONLY as a loading mechanism — the JSON files are primary.

_HARDCODED_EN = {
    "app_name": "Macena CS2 Analyzer",
    "dashboard": "Dashboard",
    "coaching": "Coaching Insights",
    "settings": "Settings",
    "profile": "Player Profile",
    "match_history_title": "Match History",
    "tactical_analysis": "TACTICAL ANALYSIS",
    "tactical_analyzer": "Tactical Analyzer",
    "rap_coach_dashboard": "AI Coach",
    "advanced_analytics": "Your Stats",
    "knowledge_engine": "Demo Processing",
    "training_progress": "Training Progress",
    "help": "Help",
}


def _load_json_translations() -> Dict[str, Dict[str, str]]:
    """Load translations from assets/i18n/*.json."""
    loaded = {}
    i18n_dir = get_resource_path(os.path.join("assets", "i18n"))
    for lang_code in ("en", "pt", "it"):
        path = os.path.join(i18n_dir, f"{lang_code}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if isinstance(v, str) and "{home_dir}" in v:
                    data[k] = v.format(home_dir=_get_home_dir())
            loaded[lang_code] = data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            _logger.debug("JSON translation for '%s' unavailable: %s", lang_code, e)
    return loaded


# Load once at import time
_JSON_TRANSLATIONS = _load_json_translations()

# Attempt to import the hardcoded dicts from the original module
# without triggering Kivy — fall back to our minimal subset if that fails.
try:
    # The TRANSLATIONS dict itself is pure data (no Kivy class instantiation)
    # but the module imports Kivy at the top. We try it and fall back.
    from Programma_CS2_RENAN.core.localization import TRANSLATIONS as _FULL_TRANSLATIONS
except ImportError:
    _FULL_TRANSLATIONS = {"en": _HARDCODED_EN}


class QtLocalizationManager(QObject):
    """Qt-native localization manager with Signal-based language change."""

    language_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._lang = "en"

    @property
    def lang(self) -> str:
        return self._lang

    def get_text(self, key: str) -> str:
        """Priority: JSON (current) → hardcoded (current) → hardcoded (en) → raw key."""
        # 1. JSON
        json_lang = _JSON_TRANSLATIONS.get(self._lang, {})
        val = json_lang.get(key)
        if val is not None:
            return val
        # 2. Hardcoded current lang
        hc_lang = _FULL_TRANSLATIONS.get(self._lang, {})
        val = hc_lang.get(key)
        if val is not None:
            return val
        # 3. English fallback
        en_val = _FULL_TRANSLATIONS.get("en", {}).get(key)
        if en_val is not None:
            return en_val
        return key

    def set_language(self, lang_code: str):
        if lang_code in _FULL_TRANSLATIONS or lang_code in _JSON_TRANSLATIONS:
            self._lang = lang_code
            self.language_changed.emit(lang_code)


# Singleton
i18n = QtLocalizationManager()
