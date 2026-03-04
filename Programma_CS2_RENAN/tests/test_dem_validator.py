"""
Unit tests for DEM file validator.

Tests validation logic, magic number detection, and error handling.
"""

import sys
import tempfile
from pathlib import Path


import pytest

from Programma_CS2_RENAN.backend.processing.validation.dem_validator import (
    DEMValidationError,
    DEMValidator,
    validate_dem_file,
)


class TestDEMValidator:
    """Test suite for DEMValidator class."""

    def test_validate_cs2_demo(self, tmp_path):
        """Test validation of valid CS2 demo file."""
        # Create mock CS2 demo
        demo_file = tmp_path / "test_cs2.dem"
        with open(demo_file, "wb") as f:
            f.write(b"PBDEMS2\x00")  # CS2 magic
            f.write(b"\x00" * (200 * 1024))  # Pad to 200KB

        validator = DEMValidator()
        is_valid, version, error = validator.validate(demo_file)

        assert is_valid is True
        assert version == "CS2"
        assert error is None

    def test_validate_csgo_demo(self, tmp_path):
        """Test validation of valid CSGO demo file."""
        demo_file = tmp_path / "test_csgo.dem"
        with open(demo_file, "wb") as f:
            f.write(b"HL2DEMO\x00")  # CSGO magic
            f.write(b"\x00" * (200 * 1024))

        validator = DEMValidator()
        is_valid, version, error = validator.validate(demo_file)

        assert is_valid is True
        assert version == "CSGO"
        assert error is None

    def test_file_not_found(self):
        """Test validation fails for non-existent file."""
        validator = DEMValidator()
        is_valid, version, error = validator.validate(Path("/nonexistent/file.dem"))

        assert is_valid is False
        assert version is None
        assert "not found" in error.lower()

    def test_file_too_small(self, tmp_path):
        """Test validation fails for files below minimum size."""
        demo_file = tmp_path / "tiny.dem"
        with open(demo_file, "wb") as f:
            f.write(b"PBDEMS2\x00")
            f.write(b"\x00" * 1000)  # Only 1KB

        validator = DEMValidator()
        is_valid, version, error = validator.validate(demo_file)

        assert is_valid is False
        assert "too small" in error.lower()

    def test_file_too_large(self, tmp_path):
        """Test validation fails for files above maximum size."""
        # Create a file slightly above a lowered MAX_FILE_SIZE (no mock needed)
        demo_file = tmp_path / "huge.dem"
        lowered_max = 300 * 1024  # 300 KB
        file_size = lowered_max + 1024  # Exceeds by 1 KB

        with open(demo_file, "wb") as f:
            f.write(b"PBDEMS2\x00")
            f.write(b"\x00" * (file_size - 8))

        validator = DEMValidator()
        validator.MAX_FILE_SIZE = lowered_max  # Override class attr on instance
        is_valid, version, error = validator.validate(demo_file)

        assert is_valid is False
        assert "too large" in error.lower()

    def test_invalid_magic_number(self, tmp_path):
        """Test validation fails for invalid file header."""
        demo_file = tmp_path / "invalid.dem"
        with open(demo_file, "wb") as f:
            f.write(b"INVALID\x00")  # Wrong magic
            f.write(b"\x00" * (200 * 1024))

        validator = DEMValidator()
        is_valid, version, error = validator.validate(demo_file)

        assert is_valid is False
        assert "invalid" in error.lower() or "header" in error.lower()

    def test_processing_time_estimation(self, tmp_path):
        """Test processing time estimation."""
        demo_file = tmp_path / "test.dem"
        with open(demo_file, "wb") as f:
            f.write(b"PBDEMS2\x00")
            f.write(b"\x00" * (50 * 1024 * 1024))  # 50 MB

        validator = DEMValidator()
        est_time = validator.estimate_processing_time(demo_file)

        # 50 MB should take ~5 seconds (1s per 10MB)
        assert est_time >= 4
        assert est_time <= 6

    def test_convenience_function(self, tmp_path):
        """Test validate_dem_file convenience function."""
        demo_file = tmp_path / "test.dem"
        with open(demo_file, "wb") as f:
            f.write(b"PBDEMS2\x00")
            f.write(b"\x00" * (200 * 1024))

        is_valid, version, error = validate_dem_file(str(demo_file))

        assert is_valid is True
        assert version == "CS2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
