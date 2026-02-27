"""
Phase 2 Verification Gate — Database & Storage Backup Tests

Validates:
- db_backup.py: backup_monolith, restore_backup, rotate_backups
- backup_manager.py: BackupManager integrity check
- alembic/env.py: _pre_migration_backup hook
"""

import os
import sqlite3
from pathlib import Path

import pytest


@pytest.mark.skip(
    reason="F9-04/F9-01: backup_monolith() may hang waiting on a DB lock. "
    "Requires pytest-timeout plugin and production DB. "
    "Re-enable once BackupManager WAL-checkpoint timeout is bounded."
)
class TestBackupMonolith:
    """Verify WAL-safe monolith backup creates a valid database file."""

    def test_backup_creates_file(self, tmp_path):
        """backup_monolith() must produce a non-zero .db file."""
        from Programma_CS2_RENAN.backend.storage.db_backup import _MONOLITH_DB, backup_monolith

        if not _MONOLITH_DB.exists():
            pytest.skip("Monolith database not found on this machine")

        backup_path = backup_monolith(target_dir=tmp_path)
        assert backup_path.exists(), "Backup file was not created"
        assert backup_path.stat().st_size > 0, "Backup file is empty"
        assert backup_path.suffix == ".db"

    def test_backup_is_valid_sqlite(self, tmp_path):
        """The backup file must pass PRAGMA integrity_check."""
        from Programma_CS2_RENAN.backend.storage.db_backup import _MONOLITH_DB, backup_monolith

        if not _MONOLITH_DB.exists():
            pytest.skip("Monolith database not found on this machine")

        backup_path = backup_monolith(target_dir=tmp_path)
        conn = sqlite3.connect(str(backup_path), timeout=10)
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
            result = conn.execute("PRAGMA integrity_check").fetchone()
            assert result[0] == "ok", f"Integrity check failed: {result[0]}"
        finally:
            conn.close()


class TestRestoreBackup:
    """Verify backup restoration with integrity verification."""

    def _create_test_db(self, path: Path) -> None:
        """Create a minimal valid SQLite database."""
        conn = sqlite3.connect(str(path))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'hello')")
        conn.commit()
        conn.close()

    def test_restore_valid_backup(self, tmp_path):
        """Restoring a valid backup must return True and pass integrity check."""
        from Programma_CS2_RENAN.backend.storage.db_backup import restore_backup

        source = tmp_path / "source.db"
        target = tmp_path / "restored.db"
        self._create_test_db(source)

        result = restore_backup(source, target)
        assert result is True, "Restore returned False for valid backup"
        assert target.exists(), "Restored file does not exist"

        conn = sqlite3.connect(str(target), timeout=10)
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            assert integrity[0] == "ok"
            row = conn.execute("SELECT val FROM test WHERE id=1").fetchone()
            assert row[0] == "hello", "Data mismatch after restore"
        finally:
            conn.close()

    def test_restore_missing_file(self, tmp_path):
        """Restoring a non-existent backup must return False."""
        from Programma_CS2_RENAN.backend.storage.db_backup import restore_backup

        result = restore_backup(tmp_path / "missing.db", tmp_path / "target.db")
        assert result is False

    def test_restore_empty_file(self, tmp_path):
        """Restoring an empty file must return False."""
        from Programma_CS2_RENAN.backend.storage.db_backup import restore_backup

        empty = tmp_path / "empty.db"
        empty.write_bytes(b"")

        result = restore_backup(empty, tmp_path / "target.db")
        assert result is False


class TestRotateBackups:
    """Verify backup rotation deletes oldest files beyond keep_count."""

    def test_rotate_prunes_excess(self, tmp_path):
        """With 7 backups and keep_count=2, only 2 should remain."""
        from Programma_CS2_RENAN.backend.storage.db_backup import rotate_backups

        # Create subdirectory structure matching rotate_backups expectation
        sub = tmp_path / "database"
        sub.mkdir()

        for i in range(7):
            f = sub / f"backup_{i:03d}.db"
            f.write_text(f"backup-{i}")
            # Space out mtime so sort is deterministic
            os.utime(str(f), (i, i))

        deleted = rotate_backups(backup_dir=tmp_path, keep_count=2)
        remaining = list(sub.iterdir())

        assert len(remaining) == 2, f"Expected 2, got {len(remaining)}"
        assert deleted == 5, f"Expected 5 deleted, got {deleted}"

    def test_rotate_no_excess(self, tmp_path):
        """When files <= keep_count, nothing should be deleted."""
        from Programma_CS2_RENAN.backend.storage.db_backup import rotate_backups

        sub = tmp_path / "database"
        sub.mkdir()
        (sub / "one.db").write_text("data")
        (sub / "two.db").write_text("data")

        deleted = rotate_backups(backup_dir=tmp_path, keep_count=5)
        assert deleted == 0

    def test_rotate_empty_dir(self, tmp_path):
        """Rotation on non-existent dir should return 0."""
        from Programma_CS2_RENAN.backend.storage.db_backup import rotate_backups

        deleted = rotate_backups(backup_dir=tmp_path / "nonexistent", keep_count=3)
        assert deleted == 0


class TestAlembicPreMigrationHook:
    """Verify the Alembic pre-migration backup hook exists in env.py."""

    def test_hook_defined_in_source(self):
        """alembic/env.py must define _pre_migration_backup and call it in run_migrations_online."""
        env_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "alembic",
            "env.py",
        )
        if not os.path.exists(env_path):
            pytest.skip("alembic/env.py not found")

        with open(env_path, "r", encoding="utf-8") as f:
            source = f.read()

        assert (
            "def _pre_migration_backup()" in source
        ), "Missing _pre_migration_backup function definition"
        assert (
            "_pre_migration_backup()" in source.split("def run_migrations_online")[1]
        ), "_pre_migration_backup() not called inside run_migrations_online"
        assert "backup_monolith" in source, "backup_monolith import missing from alembic/env.py"


class TestBackupManagerIntegrity:
    """Verify BackupManager._verify_integrity works on real SQLite files."""

    def test_integrity_check_valid(self, tmp_path):
        """A fresh SQLite file must pass integrity check."""
        from Programma_CS2_RENAN.backend.storage.backup_manager import BackupManager

        mgr = BackupManager()

        db_path = tmp_path / "test_integrity.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()

        assert mgr._verify_integrity(str(db_path)) is True

    def test_integrity_check_corrupted(self, tmp_path):
        """A corrupted file should fail integrity check."""
        from Programma_CS2_RENAN.backend.storage.backup_manager import BackupManager

        mgr = BackupManager()

        corrupt_path = tmp_path / "corrupt.db"
        corrupt_path.write_bytes(b"this is not a database")

        assert mgr._verify_integrity(str(corrupt_path)) is False
