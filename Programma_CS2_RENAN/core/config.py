import json
import os
import sys
import threading
from pathlib import Path

from Programma_CS2_RENAN.observability.logger_setup import get_logger

app_logger = get_logger("cs2analyzer.config")

# --- Environment Detection ---
IS_FROZEN = getattr(sys, "frozen", False)
_settings_lock = threading.RLock()


def stabilize_paths():
    """
    Standardizes sys.path and returns the project root.
    Ensures that root-level imports and asset paths are bit-perfect.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # core/ folder is inside Programma_CS2_RENAN/ which is inside root/
    root = os.path.dirname(os.path.dirname(script_dir))
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def get_base_dir():
    if IS_FROZEN:
        return os.path.dirname(sys.executable)
    # Parent of core/ folder
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = get_base_dir()


def get_writeable_dir():
    """Returns a directory where the application has write permissions."""
    if IS_FROZEN:
        app_data = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MacenaCS2Analyzer"
        )
        os.makedirs(app_data, exist_ok=True)
        return app_data
    return BASE_DIR


STORAGE_ROOT = get_writeable_dir()
SETTINGS_PATH = os.path.join(STORAGE_ROOT, "user_settings.json")


def get_resource_path(relative_path):
    """Returns absolute path to a read-only resource."""
    if IS_FROZEN:
        # PyInstaller temporary extraction folder
        base_path = getattr(sys, "_MEIPASS", BASE_DIR)
        return os.path.join(base_path, relative_path)
    # In source mode, relative_path is already relative to BASE_DIR (Programma_CS2_RENAN)
    return os.path.join(BASE_DIR, relative_path)


try:
    import keyring
except ImportError:
    keyring = None


def get_secret(key, default=""):
    """
    Retrieve secret from system keyring.

    Args:
        key: Secret key name
        default: Default value if secret not found

    Returns:
        Secret value or default

    Raises:
        RuntimeError: If keyring access fails (not if secret is missing)
    """
    if not keyring:
        app_logger.warning("Keyring unavailable, using default for secret '%s'", key)
        return default

    try:
        val = keyring.get_password("MacenaCS2Analyzer", key)
        if val is not None:
            app_logger.debug("Secret '%s' retrieved from keyring", key)
            return val
        else:
            app_logger.debug("Secret '%s' not found in keyring, using default", key)
            return default
    except Exception as e:
        # Keyring failures should not crash the app at import time.
        # Log visibly and fall back to default. Features requiring secrets
        # will fail at point-of-use with clear error messages.
        app_logger.error("Failed to retrieve secret '%s' from keyring: %s", key, e)
        return default


def set_secret(key, value):
    """
    Store secret in system keyring.

    Args:
        key: Secret key name
        value: Secret value to store

    Returns:
        True if successful, False if keyring unavailable

    Raises:
        RuntimeError: If keyring storage fails
    """
    if not keyring:
        app_logger.warning("Keyring unavailable, cannot store secret '%s'", key)
        return False

    try:
        keyring.set_password("MacenaCS2Analyzer", key, value)
        app_logger.info("Secret '%s' stored in keyring", key)
        return True
    except Exception as e:
        app_logger.error("Failed to store secret '%s' in keyring: %s", key, e)
        raise RuntimeError(f"Keyring storage failed for '{key}': {e}") from e


def mask_secret(value: str) -> str:
    """Returns a redacted version of a sensitive string for logging."""
    if not value or len(value) < 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def load_user_settings():
    with _settings_lock:
        defaults = {
            "CS2_PLAYER_NAME": "",
            "STEAM_ID": "",
            "STEAM_API_KEY": "",
            "FACEIT_API_KEY": "",
            "DEFAULT_DEMO_PATH": os.path.expanduser("~"),
            "PRO_DEMO_PATH": os.path.expanduser("~"),
            "BRAIN_DATA_ROOT": "",
            "CUSTOM_STORAGE_PATH": "",
            "ACTIVE_THEME": "CS2",
            "BACKGROUND_IMAGE": "vertical_wallpaper_cs2_A.jpg",
            "ENABLE_SLIDESHOW": False,
            "FONT_SIZE": "Medium",
            "FONT_TYPE": "Roboto",
            "LANGUAGE": "en",
            "SENTRY_DSN": "",
            "SENTRY_ENABLED": False,
            "ENABLE_HLTV_SYNC": True,
            # --- Settings referenced via get_setting() across the codebase ---
            "COACH_SYSTEM_PROMPT": "",
            "COACH_WEIGHT_OVERRIDES": {},
            "CUDA_DEVICE": "auto",
            "DEMO_ARCHIVE_PATH": "",
            "INGEST_INTERVAL_MINUTES": 30,
            "LOCAL_QUOTA_GB": 10.0,
            "ML_INTENSITY": "Medium",
            "SETUP_COMPLETED": False,
            "STORAGE_API_KEY": "",
            "THEME": "CS2",
            "USER_DEMO_PATH": "",
            "USE_COPER_COACHING": True,
            "USE_HYBRID_COACHING": False,
            "USE_JEPA_MODEL": False,
            "USE_OLLAMA_COACHING": False,
            "USE_RAG_COACHING": False,
        }

        # File I/O and keyring retrieval are inside the lock to prevent
        # interleaving with concurrent save_user_setting() calls from daemon threads.
        current = defaults.copy()
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r") as f:
                    data = json.load(f)
                    current.update(data)
            except Exception as e:
                app_logger.warning("Failed to load user settings from %s: %s", SETTINGS_PATH, e)

        current["STEAM_API_KEY"] = get_secret("STEAM_API_KEY", current["STEAM_API_KEY"])
        current["FACEIT_API_KEY"] = get_secret("FACEIT_API_KEY", current["FACEIT_API_KEY"])
        return current


# --- Constants ---
MIN_DEMOS_FOR_COACHING = 10
MAX_DEMOS_PER_MONTH = 10
MAX_TOTAL_DEMOS_PER_USER = 100

_settings = load_user_settings()

# Globals
CS2_PLAYER_NAME = _settings["CS2_PLAYER_NAME"]
STEAM_ID = _settings["STEAM_ID"]
STEAM_API_KEY = _settings["STEAM_API_KEY"]
FACEIT_API_KEY = _settings["FACEIT_API_KEY"]
DEFAULT_DEMO_PATH = _settings.get("DEFAULT_DEMO_PATH", os.path.expanduser("~"))
PRO_DEMO_PATH = _settings.get("PRO_DEMO_PATH", os.path.expanduser("~"))
BRAIN_DATA_ROOT = _settings.get("BRAIN_DATA_ROOT", "")


def _resolve_match_data_path() -> str:
    """Resolve match_data directory: PRO_DEMO_PATH/match_data if available, else in-project."""
    pro_path = _settings.get("PRO_DEMO_PATH", "")
    if pro_path and os.path.isdir(pro_path):
        return os.path.join(pro_path, "match_data")
    return os.path.join(os.path.join(get_base_dir(), "backend", "storage"), "match_data")


MATCH_DATA_PATH = _resolve_match_data_path()
CUSTOM_STORAGE_PATH = _settings.get("CUSTOM_STORAGE_PATH", "")
ACTIVE_THEME = _settings["ACTIVE_THEME"]
BACKGROUND_IMAGE = _settings["BACKGROUND_IMAGE"]
FONT_SIZE = _settings["FONT_SIZE"]
FONT_TYPE = _settings["FONT_TYPE"]
LANGUAGE = _settings["LANGUAGE"]
CURRENT_USER_ID = "default_user"

# --- CRITICAL PATH ARCHITECTURE ---
# The CORE DATABASE (training data, stats, ticks) ALWAYS lives in the PROJECT folder
# for portability. Changing BRAIN_DATA_ROOT should NOT break existing training data.
#
# User-specified BRAIN_DATA_ROOT is used for:
# - Neural network models (regeneratable)
# - Logs
# - Cache
# - User-specific configs
#
# This ensures: if user changes BRAIN_DATA_ROOT, they only lose models (которые can retrain),
# but never the raw training data (which is hard to recreate).

# CORE DB: Always in project folder (Single Source of Truth)
CORE_DB_DIR = os.path.join(BASE_DIR, "backend", "storage")
os.makedirs(CORE_DB_DIR, exist_ok=True)

# User data: Uses BRAIN_DATA_ROOT if available, else project folder
if BRAIN_DATA_ROOT and os.path.exists(BRAIN_DATA_ROOT):
    USER_DATA_ROOT = BRAIN_DATA_ROOT
elif CUSTOM_STORAGE_PATH and os.path.exists(CUSTOM_STORAGE_PATH):
    USER_DATA_ROOT = CUSTOM_STORAGE_PATH
else:
    USER_DATA_ROOT = BASE_DIR
    if BRAIN_DATA_ROOT:
        app_logger.warning(
            "Brain root path %s not found. Using project folder for user data.", BRAIN_DATA_ROOT
        )
    elif CUSTOM_STORAGE_PATH:
        app_logger.warning(
            "Custom path %s not found. Using project folder for user data.", CUSTOM_STORAGE_PATH
        )

# STORAGE_ROOT re-assigned here to USER_DATA_ROOT for backwards compatibility.
# NOTE: SETTINGS_PATH (line 51) intentionally used the pre-reassignment value
# (get_writeable_dir()) so settings remain readable even if BRAIN_DATA_ROOT is invalid.
STORAGE_ROOT = USER_DATA_ROOT

# Core database ALWAYS in project folder
DB_DIR = CORE_DB_DIR
# User data directories in user-specified folder
LOG_DIR = os.path.join(USER_DATA_ROOT, "logs")
DATA_DIR = os.path.join(USER_DATA_ROOT, "data")
MODELS_DIR = os.path.join(USER_DATA_ROOT, "models")

# Wire resolved LOG_DIR into logger_setup (breaks circular import dependency).
# Safe: logger_setup is already in sys.modules from line 7 import.
from Programma_CS2_RENAN.observability.logger_setup import configure_log_dir  # noqa: E402

configure_log_dir(LOG_DIR)

for d in [DB_DIR, LOG_DIR, DATA_DIR, MODELS_DIR]:
    os.makedirs(d, exist_ok=True)

# SINGLE DATABASE - always in project folder
DATABASE_URL = f"sqlite:///{os.path.join(CORE_DB_DIR, 'database.db')}"
KNOWLEDGE_DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'knowledge_base.db')}"
HLTV_DATABASE_URL = f"sqlite:///{os.path.join(CORE_DB_DIR, 'hltv_metadata.db')}"


def get_setting(key, default=None):
    """Dynamic setting lookup."""
    return _settings.get(key, default)


def refresh_settings():
    """Reloads settings from disk. Critical for background process sync."""
    global _settings, CS2_PLAYER_NAME, STEAM_ID, STEAM_API_KEY, FACEIT_API_KEY
    global DEFAULT_DEMO_PATH, PRO_DEMO_PATH, CUSTOM_STORAGE_PATH, LANGUAGE
    global MATCH_DATA_PATH

    with _settings_lock:
        _settings = load_user_settings()
        CS2_PLAYER_NAME = _settings.get("CS2_PLAYER_NAME", "")
        STEAM_ID = _settings.get("STEAM_ID", "")
        STEAM_API_KEY = _settings.get("STEAM_API_KEY", "")
        FACEIT_API_KEY = _settings.get("FACEIT_API_KEY", "")
        DEFAULT_DEMO_PATH = _settings.get("DEFAULT_DEMO_PATH", os.path.expanduser("~"))
        PRO_DEMO_PATH = _settings.get("PRO_DEMO_PATH", os.path.expanduser("~"))
        CUSTOM_STORAGE_PATH = _settings.get("CUSTOM_STORAGE_PATH", "")
        LANGUAGE = _settings.get("LANGUAGE", "en")
        MATCH_DATA_PATH = _resolve_match_data_path()


def get_all_settings():
    """Returns a copy of all current settings."""
    return _settings.copy()


_SETTING_NAME_TO_GLOBAL = {
    "CS2_PLAYER_NAME",
    "STEAM_ID",
    "STEAM_API_KEY",
    "FACEIT_API_KEY",
    "DEFAULT_DEMO_PATH",
    "PRO_DEMO_PATH",
    "CUSTOM_STORAGE_PATH",
    "LANGUAGE",
    "ACTIVE_THEME",
    "BACKGROUND_IMAGE",
    "FONT_SIZE",
    "FONT_TYPE",
}


def save_user_setting(key, value):
    """Saves setting without importing external modules to avoid loops."""
    original_value = value
    with _settings_lock:
        if key in ["STEAM_API_KEY", "FACEIT_API_KEY"]:
            if set_secret(key, value):
                value = "PROTECTED_BY_WINDOWS_VAULT"

        data = {}
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r") as f:
                    data = json.load(f)
            except Exception as e:
                app_logger.warning("Failed to read settings in save_user_setting: %s", e)

        data[key] = value
        with open(SETTINGS_PATH, "w") as f:
            json.dump(data, f, indent=4)

        # Keep the original unmasked value in memory for the current session
        _settings[key] = original_value
        if key in _SETTING_NAME_TO_GLOBAL:
            globals()[key] = original_value
