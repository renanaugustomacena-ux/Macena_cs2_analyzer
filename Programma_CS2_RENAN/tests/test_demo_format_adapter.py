"""
Tests for Proposal 12: Protobuf-Aware Demo Format Adapter.

Every test uses real temp files on disk — no mocking of file I/O.
Every assertion checks a SPECIFIC value, never just `assert True`.
"""

import os
import sys
import tempfile


import pytest

from Programma_CS2_RENAN.backend.data_sources.demo_format_adapter import (
    DEMO_MAGIC_LEGACY,
    DEMO_MAGIC_V2,
    FORMAT_VERSIONS,
    MIN_DEMO_SIZE,
    DemoFormatAdapter,
    ProtoChange,
    validate_demo_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_temp_demo(content: bytes, suffix: str = ".dem") -> str:
    """Create a real temp file with given content. Caller must delete."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, content)
    os.close(fd)
    return path


def _make_cs2_demo(size: int = 2048) -> str:
    """Create a temp file with valid CS2 header and specified size."""
    header = DEMO_MAGIC_V2
    padding = b"\x00" * (size - len(header))
    return _make_temp_demo(header + padding)


# ---------------------------------------------------------------------------
# Unit Tests — DemoFormatAdapter in isolation
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for validate_demo() method."""

    def test_validate_nonexistent_file(self):
        adapter = DemoFormatAdapter()
        result = adapter.validate_demo("/nonexistent/path/fake_demo.dem")
        assert result["valid"] is False
        assert result["error"] is not None
        assert "not found" in result["error"].lower()

    def test_validate_empty_file(self):
        path = _make_temp_demo(b"")
        try:
            result = DemoFormatAdapter().validate_demo(path)
            assert result["valid"] is False
            assert result["error"] is not None
            assert "too small" in result["error"].lower()
            assert result["file_size"] == 0
        finally:
            os.unlink(path)

    def test_validate_tiny_file(self):
        path = _make_temp_demo(b"\x00" * 500)
        try:
            result = DemoFormatAdapter().validate_demo(path)
            assert result["valid"] is False
            assert result["error"] is not None
            assert result["file_size"] == 500
            assert result["file_size"] < MIN_DEMO_SIZE
        finally:
            os.unlink(path)

    def test_validate_valid_cs2_header(self):
        path = _make_cs2_demo(size=2048)
        try:
            result = DemoFormatAdapter().validate_demo(path)
            assert result["valid"] is True
            assert result["error"] is None
            assert result["version"] == "cs2_protobuf"
            assert result["file_size"] == 2048
        finally:
            os.unlink(path)

    def test_validate_legacy_csgo_header(self):
        content = DEMO_MAGIC_LEGACY + b"\x00" * (MIN_DEMO_SIZE + 100)
        path = _make_temp_demo(content)
        try:
            result = DemoFormatAdapter().validate_demo(path)
            assert result["valid"] is False
            assert result["error"] is not None
            assert "unsupported" in result["error"].lower()
            assert result["version"] == "csgo_legacy"
        finally:
            os.unlink(path)

    def test_validate_unknown_header(self):
        content = b"GARBAGE!" + b"\x00" * MIN_DEMO_SIZE
        path = _make_temp_demo(content)
        try:
            result = DemoFormatAdapter().validate_demo(path)
            assert result["valid"] is False
            assert result["error"] is not None
            assert "unknown" in result["error"].lower()
            assert result["version"] == "unknown"
        finally:
            os.unlink(path)

    def test_corruption_warning_unaligned(self):
        # Size 2049 is not divisible by 4
        path = _make_cs2_demo(size=2049)
        try:
            result = DemoFormatAdapter().validate_demo(path)
            assert result["valid"] is True
            assert len(result["warnings"]) >= 1
            alignment_warnings = [w for w in result["warnings"] if "aligned" in w.lower()]
            assert len(alignment_warnings) >= 1
        finally:
            os.unlink(path)

    def test_corruption_warning_small_file(self):
        # Size 2048 is < 1 MB threshold for small-file warning
        path = _make_cs2_demo(size=2048)
        try:
            result = DemoFormatAdapter().validate_demo(path)
            assert result["valid"] is True
            small_warnings = [w for w in result["warnings"] if "1 mb" in w.lower()]
            assert len(small_warnings) >= 1
        finally:
            os.unlink(path)


class TestFieldMapping:
    """Tests for get_field_mapping() method."""

    def test_field_mapping_returns_dict(self):
        mapping = DemoFormatAdapter().get_field_mapping("cs2_protobuf")
        assert isinstance(mapping, dict)
        assert len(mapping) > 10

    def test_field_mapping_key_coverage(self):
        """Mapping must contain all canonical field names the demo_parser uses."""
        mapping = DemoFormatAdapter().get_field_mapping("cs2_protobuf")
        required_keys = [
            "player_name",
            "player_health",
            "player_armor",
            "player_position_x",
            "player_position_y",
            "player_position_z",
            "kill_attacker",
            "kill_victim",
            "kill_weapon",
            "kill_headshot",
        ]
        for key in required_keys:
            assert key in mapping, f"Missing canonical key: {key}"
            assert isinstance(mapping[key], str), f"Value for {key} is not str"


class TestChangelog:
    """Tests for get_changelog() method."""

    def test_changelog_not_empty(self):
        changelog = DemoFormatAdapter().get_changelog()
        assert len(changelog) > 0
        assert all(isinstance(c, ProtoChange) for c in changelog)

    def test_changelog_dates_ordered(self):
        changelog = DemoFormatAdapter().get_changelog()
        dates = [c.date for c in changelog]
        assert dates == sorted(dates), "Changelog dates not in chronological order"


class TestFormatVersions:
    """Tests for FORMAT_VERSIONS registry."""

    def test_format_versions_has_entries(self):
        assert len(FORMAT_VERSIONS) >= 2

    def test_cs2_protobuf_supported(self):
        assert "cs2_protobuf" in FORMAT_VERSIONS
        assert FORMAT_VERSIONS["cs2_protobuf"].supported is True

    def test_csgo_legacy_not_supported(self):
        assert "csgo_legacy" in FORMAT_VERSIONS
        assert FORMAT_VERSIONS["csgo_legacy"].supported is False


# ---------------------------------------------------------------------------
# Integration Tests — adapter wired into consumers
# ---------------------------------------------------------------------------


class TestIntegration:
    """Tests that consumers actually import and use the adapter."""

    def test_demo_parser_imports_kast_estimator(self):
        """demo_parser module must import estimate_kast_from_stats for KAST calculation."""
        import Programma_CS2_RENAN.backend.data_sources.demo_parser as dp

        source = open(dp.__file__).read()
        assert "estimate_kast_from_stats" in source
        assert "kast" in source

    def test_integrity_delegates_to_adapter(self):
        """integrity.validate_dem_file() must use adapter, not legacy magic."""
        import Programma_CS2_RENAN.ingestion.integrity as integ

        source = open(integ.__file__).read()
        # Must import the adapter
        assert "demo_format_adapter" in source
        # Must NOT have legacy CS:GO magic as validation constant
        assert 'DEM_MAGIC = b"HL2DEMO"' not in source

    def test_integrity_accepts_cs2_rejects_legacy(self):
        """validate_dem_file: CS2 header passes, legacy header raises."""
        from Programma_CS2_RENAN.ingestion.integrity import validate_dem_file

        # CS2 demo should pass
        cs2_path = _make_cs2_demo(size=2048)
        try:
            validate_dem_file(cs2_path)  # Should not raise
        finally:
            os.unlink(cs2_path)

        # Legacy CS:GO demo should raise ValueError
        legacy_content = DEMO_MAGIC_LEGACY + b"\x00" * (MIN_DEMO_SIZE + 100)
        legacy_path = _make_temp_demo(legacy_content)
        try:
            with pytest.raises(ValueError, match="[Uu]nsupported"):
                validate_dem_file(legacy_path)
        finally:
            os.unlink(legacy_path)

    def test_validate_demo_file_convenience(self):
        """Convenience function produces same result as class method."""
        path = _make_cs2_demo(size=4096)
        try:
            result_func = validate_demo_file(path)
            result_class = DemoFormatAdapter().validate_demo(path)
            assert result_func["valid"] == result_class["valid"]
            assert result_func["version"] == result_class["version"]
            assert result_func["file_size"] == result_class["file_size"]
        finally:
            os.unlink(path)
