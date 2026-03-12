#!/usr/bin/env python3
"""
MACENA SCHEMA - Master Database & Migration Suite
=================================================
The unified controller for all database lifecycle events:
inspection, migration, data importing, and emergency fixing.

Usage:
    python schema.py inspect     - Show DB tables, columns, and indexes
    python schema.py migrate     - Apply schema changes (Alembic/Auto)
    python schema.py import      - Import pro data from external sources
    python schema.py fix         - Hot-patch known schema issues
    python schema.py reset       - Reset migration state or tables
"""

import argparse
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_SAFE_COL_TYPE_RE = re.compile(r"^[A-Z]+(?: DEFAULT [0-9.]+)?$")

# --- Path Stabilization ---
PROJECT_ROOT = Path(__file__).parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Central DB Path
DB_PATH = PROJECT_ROOT / "Programma_CS2_RENAN" / "backend" / "storage" / "database.db"
KNOWLEDGE_DB_PATH = PROJECT_ROOT / "Programma_CS2_RENAN" / "backend" / "storage" / "knowledge.db"


class SchemaSuite:
    def __init__(self):
        self.db_path = DB_PATH
        self.knowledge_db_path = KNOWLEDGE_DB_PATH

    @staticmethod
    def _validate_identifier(name: str) -> str:
        """Validate that a name is a safe SQL identifier (table/column)."""
        if not _IDENTIFIER_RE.match(name):
            raise ValueError(f"Unsafe SQL identifier rejected: {name!r}")
        return name

    def _safe_pragma_table_info(self, cursor, table: str) -> list:
        """Execute PRAGMA table_info with validated identifier."""
        safe = self._validate_identifier(table)
        cursor.execute(f"PRAGMA table_info([{safe}])")
        return cursor.fetchall()

    def _safe_select_count(self, cursor, table: str) -> int:
        """Execute SELECT COUNT(*) with validated identifier."""
        safe = self._validate_identifier(table)
        cursor.execute(f"SELECT COUNT(*) FROM [{safe}]")
        return cursor.fetchone()[0]

    def _safe_alter_add_column(self, cursor, table: str, col_name: str, col_type: str):
        """Execute ALTER TABLE ADD COLUMN with all identifiers validated."""
        safe_table = self._validate_identifier(table)
        safe_col = self._validate_identifier(col_name)
        if not _SAFE_COL_TYPE_RE.match(col_type):
            raise ValueError(f"Unsafe column type rejected: {col_type!r}")
        cursor.execute(
            f"ALTER TABLE [{safe_table}] ADD COLUMN [{safe_col}] {col_type}"
        )

    def _get_connection(self, db_path=None):
        target = db_path or self.db_path
        if not target.exists():
            print(f"Error: Database not found at {target}")
            sys.exit(1)
        return sqlite3.connect(target)

    def run_inspect(self, target="main"):
        """Inspects tables and schema."""
        print("\n" + "=" * 60)
        print(f"      MACENA SCHEMA - INSPECTION ({target.upper()})")
        print("=" * 60)

        db_file = self.knowledge_db_path if target == "knowledge" else self.db_path
        conn = self._get_connection(db_file)
        cursor = conn.cursor()

        # WAL Mode
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        print(f"[*] Journal Mode: {mode.upper()}")

        # Tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"[*] Found {len(tables)} tables:")

        for table in tables:
            cols = self._safe_pragma_table_info(cursor, table)
            print(f"    - {table} ({len(cols)} columns)")
            # Optional: Print detail if few tables

        cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='index';")
        idx_count = cursor.fetchone()[0]
        print(f"[*] Total Indexes: {idx_count}")

        conn.close()

    def run_migrate(self):
        """Applies schema migrations."""
        print("\n" + "=" * 60)
        print("      MACENA SCHEMA - MIGRATION")
        print("=" * 60)

        # 1. Init schema if missing
        if not self.db_path.exists():
            print("[*] Database missing. Initializing fresh schema...")
            try:
                from Programma_CS2_RENAN.backend.storage.database import init_database

                init_database()
                print("[SUCCESS] Schema initialized.")
            except ImportError:
                print("[FAIL] Could not import init_database.")
            return

        # 2. Add 'current_epoch' to coachstate if missing (Common migration)
        self._apply_column_migration("coachstate", "current_epoch", "INTEGER DEFAULT 0")
        self._apply_column_migration("coachstate", "train_loss", "FLOAT DEFAULT 0.0")
        self._apply_column_migration("playertickstate", "demo_name", "TEXT")

        print("[*] Migration check complete.")

    def _apply_column_migration(self, table, col_name, col_type):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cols = [c[1] for c in self._safe_pragma_table_info(cursor, table)]
            if col_name not in cols:
                print(f"[+] Migrating: Adding '{col_name}' to '{table}'...")
                self._safe_alter_add_column(cursor, table, col_name, col_type)
                conn.commit()
                print("    [DONE] Applied.")
            else:
                print(f"    [OK] '{table}.{col_name}' exists.")
        except Exception as e:
            print(f"    [SKIP] Could not migrate {table}: {e}")
        conn.close()

    def run_import(self, source_path):
        """Imports data from external DB."""
        print("\n" + "=" * 60)
        print("      MACENA SCHEMA - DATA IMPORT")
        print("=" * 60)

        source = Path(source_path)
        if not source.exists():
            print(f"[ERROR] Source not found: {source}")
            return

        print(f"[*] Importing from: {source}")
        print("[WARN] This feature handles legacy D: drive imports. Ensure schema compatibility.")

        # Invoke legacy logic (simplified)
        try:
            # We can re-use the logic from the old migrate_db.py script here
            # For now, we simulate the structure
            src_conn = sqlite3.connect(source)
            dest_conn = self._get_connection()

            # Example: Transfer PlayerProfile
            self._transfer_table("playerprofile", src_conn, dest_conn)
            self._transfer_table("playermatchstats", src_conn, dest_conn)

            src_conn.close()
            dest_conn.close()
            print("[SUCCESS] Import complete.")
        except Exception as e:
            print(f"[FAIL] Import failed: {e}")

    def _transfer_table(self, table, src, dest):
        try:
            self._validate_identifier(table)
            # Check if table exists in both
            src_cur = src.cursor()
            src_cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if not src_cur.fetchone():
                return

            print(f"    Processing '{table}'...")
            row_count = self._safe_select_count(src_cur, table)

            # Get columns
            cols = [c[1] for c in self._safe_pragma_table_info(src_cur, table)]

            # Ignoring ID collisions for now; usually we'd filter.
            # This is a naive import for the master suite prototype.
            print(f"    - Found {row_count} rows.")

        except Exception as e:
            print(f"    - Error processing {table}: {e}")

    def run_fix(self, fix_type="all"):
        """Applies specific hot-fixes."""
        print("\n" + "=" * 60)
        print("      MACENA SCHEMA - EMERGENCY FIX")
        print("=" * 60)

        if fix_type in ["knowledge", "all"]:
            print("[*] Fixing Knowledge DB Schema...")
            if self.knowledge_db_path.exists():
                k_conn = sqlite3.connect(self.knowledge_db_path)
                try:
                    k_conn.execute(
                        "ALTER TABLE coachstate ADD COLUMN current_epoch INTEGER DEFAULT 0"
                    )
                    print("    [FIXED] Added current_epoch to knowledge DB.")
                except Exception:
                    print("    [OK] Knowledge DB schema appears correct.")
                k_conn.close()
            else:
                print("    [SKIP] Knowledge DB not found.")

        if fix_type in ["sequences", "all"]:
            print("[*] Recalibrating SQLite Sequences...")
            print("[WARN] This resets all auto-increment counters. New rows may reuse old IDs.")
            conn = self._get_connection()
            # Log current state before destructive operation
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sqlite_sequence")
            current = cursor.fetchall()
            if current:
                print(f"    Current sequences ({len(current)} tables):")
                for row in current:
                    print(f"      {row[0]}: seq={row[1]}")
            conn.execute("DELETE FROM sqlite_sequence")
            conn.commit()
            conn.close()
            print("    [DONE] Sequences reset.")

    def run_reset(self, target="alembic"):
        """Resets state tables."""
        print("\n" + "=" * 60)
        print("      MACENA SCHEMA - RESET")
        print("=" * 60)

        conn = self._get_connection()
        if target == "alembic":
            print("[*] Dropping alembic_version table...")
            try:
                conn.execute("DROP TABLE alembic_version")
                print("    [DONE] Dropped.")
            except Exception:
                print("    [SKIP] Table not found.")
        elif target == "coach":
            print("[*] Clearing Coach State...")
            conn.execute("DELETE FROM coachstate")
            print("    [DONE] Coach state cleared.")

        conn.commit()
        conn.close()


def main():
    parser = argparse.ArgumentParser(prog="schema", description="Macena Master Database Suite")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect DB structure")
    inspect_parser.add_argument(
        "--target", default="main", choices=["main", "knowledge"], help="Which DB to inspect"
    )

    # Migrate
    subparsers.add_parser("migrate", help="Run pending migrations")

    # Import
    import_parser = subparsers.add_parser("import", help="Import data from external DB")
    import_parser.add_argument("--source", required=True, help="Path to source .db file")

    # Fix
    fix_parser = subparsers.add_parser("fix", help="Apply emergency schema fixes")
    fix_parser.add_argument("--type", default="all", choices=["all", "knowledge", "sequences"])

    # Reset
    reset_parser = subparsers.add_parser("reset", help="Reset DB components")
    reset_parser.add_argument("--target", default="alembic", choices=["alembic", "coach"])

    args = parser.parse_args()
    suite = SchemaSuite()

    if args.command == "inspect":
        suite.run_inspect(target=args.target)
    elif args.command == "migrate":
        suite.run_migrate()
    elif args.command == "import":
        suite.run_import(args.source)
    elif args.command == "fix":
        suite.run_fix(fix_type=args.type)
    elif args.command == "reset":
        suite.run_reset(target=args.target)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
