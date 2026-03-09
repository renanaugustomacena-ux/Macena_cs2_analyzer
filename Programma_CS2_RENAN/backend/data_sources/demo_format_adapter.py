"""
Demo Format Adapter — Version-aware CS2 demo file handling.

Fusion Plan Proposal 12: Protobuf-Aware Demo Format Adapter.

Provides:
1. Demo file pre-validation (size, header, corruption detection)
2. Format version detection from demo headers
3. Field mapping for version-specific column names
4. Changelog tracking for known format transitions

This module WRAPS the existing demo_parser — it does not replace it.
The parser continues to work unchanged; this adapter adds a resilience
layer for handling format version differences.

Usage:
    from Programma_CS2_RENAN.backend.data_sources.demo_format_adapter import (
        DemoFormatAdapter, validate_demo_file
    )

    adapter = DemoFormatAdapter()
    validation = adapter.validate_demo(demo_path)
    if validation["valid"]:
        version = validation["version"]
        # proceed with parsing
"""

import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.demo_format_adapter")


# ---------------------------------------------------------------------------
# Demo file constants
# ---------------------------------------------------------------------------

# CS2 demo file magic bytes (first 8 bytes: "PBDEMS2\0")
DEMO_MAGIC_V2 = b"PBDEMS2\x00"
# CS:GO legacy format (for reference — we don't support parsing these)
DEMO_MAGIC_LEGACY = b"HL2DEMO\x00"

# Reasonable size bounds (bytes)
MIN_DEMO_SIZE = 10 * 1024 * 1024  # DS-12: 10 MB — real CS2 demos are 50+ MB
MAX_DEMO_SIZE = 5 * 1024**3  # 5 GB — safety cap


@dataclass(frozen=True)
class FormatVersion:
    """Known CS2 demo format version specification."""

    name: str
    magic: bytes
    description: str
    supported: bool


# Known demo format versions
FORMAT_VERSIONS: Dict[str, FormatVersion] = {
    "cs2_protobuf": FormatVersion(
        name="cs2_protobuf",
        magic=DEMO_MAGIC_V2,
        description="CS2 Protobuf demo format (Source 2)",
        supported=True,
    ),
    "csgo_legacy": FormatVersion(
        name="csgo_legacy",
        magic=DEMO_MAGIC_LEGACY,
        description="CS:GO legacy demo format (Source 1)",
        supported=False,
    ),
}


@dataclass(frozen=True)
class ProtoChange:
    """Record of a known protobuf schema change."""

    date: str
    description: str
    affected_events: Tuple[str, ...]  # F6-30: Tuple instead of List in frozen dataclass
    migration_notes: str


# Known protobuf schema changes (from awesome-cs2-master reference)
PROTO_CHANGELOG: List[ProtoChange] = [
    ProtoChange(
        date="2024-03-01",
        description="CS2 initial protobuf demo format stabilization",
        affected_events=("CSVCMsg_GameEvent", "CDemoFileInfo"),
        migration_notes="demoparser2 handles this natively.",
    ),
    ProtoChange(
        date="2024-09-15",
        description="Sub-tick movement data format update",
        affected_events=("CNETMsg_Tick",),
        migration_notes="Sub-tick interpolation fields added. Backward compatible.",
    ),
    ProtoChange(
        date="2025-06-01",
        description="Updated player_death event with additional flags",
        affected_events=("player_death",),
        migration_notes="Added 'wipe' and 'noreplay' fields. Older demos may not have these.",
    ),
]


class DemoFormatAdapter:
    """
    Adapts demo file handling for version differences and provides
    pre-parse validation to catch corrupted or unsupported files early.
    """

    def validate_demo(self, demo_path: str) -> Dict:
        """
        Comprehensive pre-parse validation of a demo file.

        Checks:
        1. File exists and is readable
        2. File size is within reasonable bounds
        3. Magic bytes match a known format
        4. Format is supported by our parser

        Args:
            demo_path: Path to the .dem file.

        Returns:
            Dict with keys:
                valid (bool): Whether the file can be parsed
                version (str): Detected format version name
                file_size (int): Size in bytes
                error (str|None): Error message if invalid
                warnings (List[str]): Non-fatal warnings
        """
        result = {
            "valid": False,
            "version": "unknown",
            "file_size": 0,
            "error": None,
            "warnings": [],
        }

        # Check existence
        if not os.path.isfile(demo_path):
            result["error"] = f"File not found: {demo_path}"
            return result

        # Check file size
        file_size = os.path.getsize(demo_path)
        result["file_size"] = file_size

        if file_size < MIN_DEMO_SIZE:
            result["error"] = f"File too small ({file_size} bytes) — likely corrupted"
            return result

        if file_size > MAX_DEMO_SIZE:
            result["error"] = f"File too large ({file_size / 1024**3:.1f} GB) — exceeds safety cap"
            return result

        # Read magic bytes
        try:
            with open(demo_path, "rb") as f:
                header = f.read(8)
        except (IOError, OSError) as e:
            result["error"] = f"Cannot read file: {e}"
            return result

        if len(header) < 8:
            result["error"] = "File too small to contain valid header"
            return result

        # Detect format version
        version = self._detect_version(header)
        result["version"] = version

        if version == "unknown":
            result["error"] = f"Unknown demo format (header: {header[:8].hex()})"
            return result

        fmt = FORMAT_VERSIONS.get(version)
        if fmt and not fmt.supported:
            result["error"] = f"Unsupported format: {fmt.description}"
            return result

        # Check for known corruption patterns
        corruption_warnings = self._check_corruption_patterns(demo_path, file_size)
        result["warnings"].extend(corruption_warnings)

        result["valid"] = True
        logger.info(  # F6-09: %s format instead of f-string
            "Demo validated: %s — %s, %.1f MB, %s warnings",
            Path(demo_path).name,
            version,
            file_size / 1024**2,
            len(corruption_warnings),
        )
        return result

    def _detect_version(self, header: bytes) -> str:
        """Detect demo format version from file header magic bytes."""
        for version_name, fmt in FORMAT_VERSIONS.items():
            if header[: len(fmt.magic)] == fmt.magic:
                return version_name
        return "unknown"

    def _check_corruption_patterns(self, demo_path: str, file_size: int) -> List[str]:
        """Check for known corruption patterns in demo files."""
        warnings = []

        # Pattern 1: File size not aligned to protobuf message boundaries
        # (CS2 demos are typically multiples of 4 bytes)
        if file_size % 4 != 0:
            warnings.append(f"File size ({file_size}) not 4-byte aligned — possible truncation")

        # Pattern 2: Extremely small file relative to typical match
        # A full match is usually > 50 MB
        if file_size < 1024 * 1024:  # < 1 MB
            warnings.append("File under 1 MB — may be a partial/corrupted recording")

        return warnings

    def get_field_mapping(self, version: str) -> Dict[str, str]:
        """
        Map canonical Macena field names to version-specific field names.

        Currently CS2 has stable field names via demoparser2 abstraction,
        but this mapping enables future adaptation if Valve changes fields.

        Args:
            version: Format version name.

        Returns:
            Dict mapping canonical names to actual field names.
        """
        # Default mapping (current demoparser2 conventions)
        return {
            "player_name": "player_name",
            "player_health": "health",
            "player_armor": "armor",
            "player_position_x": "X",
            "player_position_y": "Y",
            "player_position_z": "Z",
            "player_yaw": "yaw",
            "player_pitch": "pitch",
            "kill_attacker": "attacker_name",
            "kill_victim": "user_name",
            "kill_weapon": "weapon",
            "kill_headshot": "headshot",
            "kill_penetrated": "penetrated",
            "kill_thrusmoke": "thrusmoke",
            "kill_noscope": "noscope",
            "kill_attackerblind": "attackerblind",
            "damage_attacker": "attacker_name",
            "damage_weapon": "weapon",
            "damage_health": "dmg_health",
        }

    def get_changelog(self) -> List[ProtoChange]:
        """Return the known protobuf changelog."""
        return list(PROTO_CHANGELOG)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def validate_demo_file(demo_path: str) -> Dict:
    """
    Quick validation of a demo file. Convenience wrapper around DemoFormatAdapter.

    Args:
        demo_path: Path to .dem file.

    Returns:
        Validation result dict (see DemoFormatAdapter.validate_demo).
    """
    return DemoFormatAdapter().validate_demo(demo_path)
