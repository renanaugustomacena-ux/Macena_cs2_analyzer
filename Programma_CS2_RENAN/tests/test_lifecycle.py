"""
Tests for AppLifecycleManager — Phase 9 Coverage Expansion.

Covers:
  AppLifecycleManager (lifecycle.py)
  - __init__ defaults, project_root
  - ensure_single_instance (platform-dependent)
  - shutdown without daemon (no-op safety)
"""

import sys


import os

import pytest


class TestAppLifecycleManager:
    """Tests for the lifecycle manager."""

    def _make_lifecycle(self):
        from Programma_CS2_RENAN.core.lifecycle import AppLifecycleManager
        return AppLifecycleManager()

    def test_init_mutex_name(self):
        lm = self._make_lifecycle()
        assert lm.mutex_name == "Global\\MacenaCS2Analyzer_Unique_Lock_v1"

    def test_init_project_root_is_directory(self):
        lm = self._make_lifecycle()
        assert os.path.isdir(str(lm.project_root))

    def test_init_daemon_process_none(self):
        lm = self._make_lifecycle()
        assert lm._daemon_process is None

    def test_init_instance_mutex_none(self):
        lm = self._make_lifecycle()
        assert lm._instance_mutex is None

    def test_ensure_single_instance_returns_bool(self):
        lm = self._make_lifecycle()
        result = lm.ensure_single_instance()
        assert isinstance(result, bool)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only mutex test")
    def test_ensure_single_instance_windows(self):
        """On Windows, returns bool (True if first instance, False if mutex held)."""
        lm = self._make_lifecycle()
        result = lm.ensure_single_instance()
        # The module-level `lifecycle` singleton may already hold the mutex,
        # so we only assert the return type is bool (not the value).
        assert isinstance(result, bool)

    def test_shutdown_no_daemon(self):
        """Shutdown without a daemon process should not crash."""
        lm = self._make_lifecycle()
        lm._daemon_process = None
        lm.shutdown()  # Should be a no-op

    def test_shutdown_with_already_exited_daemon(self):
        """Shutdown with a daemon that already exited should not crash."""
        from unittest.mock import MagicMock
        lm = self._make_lifecycle()
        fake_proc = MagicMock()
        fake_proc.poll.return_value = 0  # Already exited
        lm._daemon_process = fake_proc
        lm._instance_mutex = None
        lm.shutdown()
        # terminate() should NOT be called since poll() != None
        fake_proc.terminate.assert_not_called()

    def test_launch_daemon_missing_script(self):
        """launch_daemon with nonexistent script path returns None."""
        from pathlib import Path
        lm = self._make_lifecycle()
        lm.project_root = Path("/nonexistent/path")
        result = lm.launch_daemon()
        assert result is None
