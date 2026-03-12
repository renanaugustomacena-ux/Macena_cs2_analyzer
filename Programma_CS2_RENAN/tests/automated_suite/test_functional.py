import os
import sys

import pytest

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Programma_CS2_RENAN.core.config import load_user_settings, save_user_setting


def test_config_persistence(isolated_settings):
    """Functional Test: Verify user settings are saved and loaded correctly.

    Uses the isolated_settings fixture to redirect file I/O to a temp file,
    preventing any writes to the real user_settings.json.
    """
    test_key = "CS2_PLAYER_NAME"
    test_val = "Pytest_User"

    save_user_setting(test_key, test_val)
    settings = load_user_settings()
    assert settings[test_key] == test_val
