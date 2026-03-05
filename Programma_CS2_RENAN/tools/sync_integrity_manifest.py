#!/usr/bin/env python3
"""
Integrity Manifest Sync — Pre-commit hook for Macena CS2 Analyzer.

Modes:
  Default      : Regenerate core/integrity_manifest.json from production .py files
  --verify-only: Compare on-disk manifest with computed hashes, exit 1 if divergent

Hashing: SHA-256 of file content (normalized to UTF-8).
"""

import hashlib
import json
import sys
from pathlib import Path

from _infra import SOURCE_ROOT, BaseValidator, Severity

MANIFEST_PATH = SOURCE_ROOT / "core" / "integrity_manifest.json"

# Directories excluded from hashing (tools, tests, caches)
_HASH_EXCLUDES = {
    "tools",
    "tests",
    "__pycache__",
    "PHOTO_GUI",
    "data",
    "models",
}


def _compute_hashes() -> dict:
    """Walk SOURCE_ROOT and compute SHA-256 for all production .py files."""
    hashes = {}
    for f in sorted(SOURCE_ROOT.rglob("*.py")):
        rel = f.relative_to(SOURCE_ROOT)
        parts = rel.parts
        if any(d in parts for d in _HASH_EXCLUDES):
            continue
        if "__pycache__" in str(f):
            continue
        try:
            content = f.read_bytes()
            h = hashlib.sha256(content).hexdigest()
            hashes[rel.as_posix()] = h
        except (OSError, PermissionError):
            continue
    return hashes


def _load_manifest() -> dict:
    """Load the existing manifest from disk."""
    if not MANIFEST_PATH.exists():
        return {}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return data.get("hashes", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def _write_manifest(hashes: dict) -> None:
    """Write the manifest to disk."""
    manifest = {
        "version": "2.0",
        "generator": "sync_integrity_manifest.py",
        "file_count": len(hashes),
        "hashes": hashes,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class ManifestValidator(BaseValidator):

    def __init__(self):
        super().__init__("Integrity Manifest Sync", version="2.0")
        self._verify_only = False

    def _add_extra_args(self, parser):
        parser.add_argument(
            "--verify-only", action="store_true", help="Only verify, do not regenerate"
        )

    def define_checks(self):
        self._verify_only = getattr(self.args, "verify_only", False)

        if self._verify_only:
            self._verify_mode()
        else:
            self._regenerate_mode()

    def _verify_mode(self):
        self.console.section("Verify Integrity Manifest", 1, 1)

        self.check(
            "Manifest",
            "Manifest file exists",
            MANIFEST_PATH.exists(),
            error=f"Missing: {MANIFEST_PATH}",
        )

        if not MANIFEST_PATH.exists():
            return

        on_disk = _load_manifest()
        computed = _compute_hashes()

        # Check for files with changed hashes
        changed = []
        for path, h in computed.items():
            if path in on_disk and on_disk[path] != h:
                changed.append(path)

        # Check for new files not in manifest
        new_files = [p for p in computed if p not in on_disk]

        # Check for removed files still in manifest
        removed = [p for p in on_disk if p not in computed]

        total_drift = len(changed) + len(new_files) + len(removed)

        self.check(
            "Manifest",
            "Manifest in sync",
            total_drift == 0,
            error=(
                (
                    f"{len(changed)} changed, {len(new_files)} new, "
                    f"{len(removed)} removed — run sync_integrity_manifest.py to update"
                )
                if total_drift > 0
                else ""
            ),
            detail=f"{len(computed)} files tracked" if total_drift == 0 else "",
        )

    def _regenerate_mode(self):
        self.console.section("Regenerate Integrity Manifest", 1, 1)

        computed = _compute_hashes()

        self.check(
            "Manifest",
            "Files discovered",
            len(computed) > 0,
            detail=f"{len(computed)} production .py files",
        )

        _write_manifest(computed)

        self.check(
            "Manifest",
            "Manifest written",
            MANIFEST_PATH.exists(),
            detail=str(MANIFEST_PATH.relative_to(SOURCE_ROOT)),
        )


if __name__ == "__main__":
    validator = ManifestValidator()
    sys.exit(validator.run())
