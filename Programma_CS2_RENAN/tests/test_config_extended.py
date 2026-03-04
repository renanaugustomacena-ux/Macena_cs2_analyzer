"""
Tests for Core Config Module — Phase 9 Coverage Expansion.

Covers:
  config.py — stabilize_paths, get_base_dir, mask_secret,
               get_setting, get_all_settings, save_user_setting,
               constants, DATABASE_URL format
"""

import sys


import json
import os

import pytest


# ---------------------------------------------------------------------------
# stabilize_paths / get_base_dir
# ---------------------------------------------------------------------------
class TestPaths:
    """Tests for path stabilization."""

    def test_stabilize_paths_returns_string(self):
        from Programma_CS2_RENAN.core.config import stabilize_paths
        root = stabilize_paths()
        assert isinstance(root, str)
        assert os.path.isdir(root)

    def test_stabilize_paths_adds_to_sys_path(self):
        from Programma_CS2_RENAN.core.config import stabilize_paths
        root = stabilize_paths()
        assert root in sys.path

    def test_get_base_dir_returns_string(self):
        from Programma_CS2_RENAN.core.config import get_base_dir
        bd = get_base_dir()
        assert isinstance(bd, str)
        assert os.path.isdir(bd)

    def test_base_dir_is_programma_parent(self):
        from Programma_CS2_RENAN.core.config import BASE_DIR
        # BASE_DIR should be parent of Programma_CS2_RENAN
        assert os.path.isdir(os.path.join(BASE_DIR, "core"))

    def test_get_resource_path(self):
        from Programma_CS2_RENAN.core.config import get_resource_path
        path = get_resource_path("core")
        assert isinstance(path, str)
        assert "core" in path


# ---------------------------------------------------------------------------
# mask_secret
# ---------------------------------------------------------------------------
class TestMaskSecret:
    """Tests for secret masking utility."""

    def test_short_secret(self):
        from Programma_CS2_RENAN.core.config import mask_secret
        assert mask_secret("abc") == "****"
        assert mask_secret("") == "****"

    def test_long_secret(self):
        from Programma_CS2_RENAN.core.config import mask_secret
        result = mask_secret("ABCDEFGH12345678")
        assert result.startswith("ABCD")
        assert result.endswith("5678")
        assert "..." in result

    def test_exactly_8_chars(self):
        from Programma_CS2_RENAN.core.config import mask_secret
        result = mask_secret("12345678")
        assert result == "1234...5678"

    def test_none_input(self):
        from Programma_CS2_RENAN.core.config import mask_secret
        assert mask_secret(None) == "****"


# ---------------------------------------------------------------------------
# get_setting / get_all_settings
# ---------------------------------------------------------------------------
class TestSettings:
    """Tests for settings access."""

    def test_get_setting_existing(self):
        from Programma_CS2_RENAN.core.config import get_setting
        # LANGUAGE always exists in defaults
        lang = get_setting("LANGUAGE")
        assert isinstance(lang, str)

    def test_get_setting_default(self):
        from Programma_CS2_RENAN.core.config import get_setting
        result = get_setting("NONEXISTENT_KEY_XYZ", "fallback")
        assert result == "fallback"

    def test_get_setting_none_default(self):
        from Programma_CS2_RENAN.core.config import get_setting
        result = get_setting("NONEXISTENT_KEY_XYZ")
        assert result is None

    def test_get_all_settings_returns_dict(self):
        from Programma_CS2_RENAN.core.config import get_all_settings
        s = get_all_settings()
        assert isinstance(s, dict)
        assert "LANGUAGE" in s
        assert "CS2_PLAYER_NAME" in s

    def test_get_all_settings_is_copy(self):
        from Programma_CS2_RENAN.core.config import get_all_settings
        s1 = get_all_settings()
        s2 = get_all_settings()
        assert s1 is not s2  # Must be a copy


# ---------------------------------------------------------------------------
# save_user_setting (uses tmp_path to avoid real file mutation)
# ---------------------------------------------------------------------------
class TestSaveUserSetting:
    """Tests for save_user_setting (isolated with temp path)."""

    def test_save_and_read_roundtrip(self, tmp_path):
        import Programma_CS2_RENAN.core.config as cfg

        original_path = cfg.SETTINGS_PATH
        original_settings = cfg._settings.copy()
        test_file = str(tmp_path / "test_settings.json")

        try:
            cfg.SETTINGS_PATH = test_file
            cfg.save_user_setting("TEST_KEY_ROUNDTRIP", "test_value")
            # Verify written to disk
            with open(test_file) as f:
                data = json.load(f)
            assert data["TEST_KEY_ROUNDTRIP"] == "test_value"
            # Verify in-memory
            assert cfg._settings["TEST_KEY_ROUNDTRIP"] == "test_value"
        finally:
            cfg.SETTINGS_PATH = original_path
            cfg._settings.update(original_settings)
            # Clean up test key
            cfg._settings.pop("TEST_KEY_ROUNDTRIP", None)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
class TestConstants:
    """Tests for module-level constants."""

    def test_min_demos_for_coaching(self):
        from Programma_CS2_RENAN.core.config import MIN_DEMOS_FOR_COACHING
        assert MIN_DEMOS_FOR_COACHING == 10

    def test_max_demos_per_month(self):
        from Programma_CS2_RENAN.core.config import MAX_DEMOS_PER_MONTH
        assert MAX_DEMOS_PER_MONTH == 10

    def test_database_url_format(self):
        from Programma_CS2_RENAN.core.config import DATABASE_URL
        assert DATABASE_URL.startswith("sqlite:///")
        assert "database.db" in DATABASE_URL

    def test_dirs_exist(self):
        from Programma_CS2_RENAN.core.config import DB_DIR, LOG_DIR, DATA_DIR, MODELS_DIR
        for d in [DB_DIR, LOG_DIR, DATA_DIR, MODELS_DIR]:
            assert os.path.isdir(d)

    def test_get_writeable_dir(self):
        from Programma_CS2_RENAN.core.config import get_writeable_dir
        wd = get_writeable_dir()
        assert isinstance(wd, str)
        assert os.path.isdir(wd)
