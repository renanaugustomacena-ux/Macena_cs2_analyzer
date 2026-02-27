"""
Smoke tests for Macena CS2 Analyzer automated suite.

F9-08: These are import-only smoke tests — they verify that modules can be
imported without crashing. They do NOT assert behavioral correctness.
Behavioral tests are in the dedicated per-module test files.
"""

import os
import sys

import pytest

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_imports():
    """Smoke Test: Verify all major modules can be imported."""
    try:
        import kivy
        import pandas
        import torch

        from Programma_CS2_RENAN.backend.nn.model import TeacherRefinementNN
        from Programma_CS2_RENAN.backend.storage.database import init_database
        from Programma_CS2_RENAN.core.localization import i18n
    except ImportError as e:
        pytest.fail(f"Smoke Test Failed: Could not import Programma_CS2_RENAN.core module: {e}")


def test_database_init():
    """Smoke Test: Verify database initialization works."""
    from Programma_CS2_RENAN.backend.storage.database import init_database

    try:
        init_database()
    except Exception as e:
        pytest.fail(f"Smoke Test Failed: Database initialization failed: {e}")
