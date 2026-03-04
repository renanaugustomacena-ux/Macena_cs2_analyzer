import os
import sys

# --- Venv Guard ---
if sys.prefix == sys.base_prefix:
    if "pytest" in sys.modules:
        pass  # Let pytest handle this
    else:
        print("ERROR: Not in venv.", file=sys.stderr)
        sys.exit(2)

from sqlalchemy import inspect

# --- Path Stabilization ---
script_dir = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(script_dir))
if root not in sys.path:
    sys.path.insert(0, root)

from Programma_CS2_RENAN.backend.storage.database import get_db_manager


def probe_tables():
    inspector = inspect(get_db_manager().engine)
    tables = inspector.get_table_names()
    print(f"Existing tables: {tables}")

    for table in tables:
        columns = [c["name"] for c in inspector.get_columns(table)]
        print(f"Table '{table}' columns: {columns}")


if __name__ == "__main__":
    probe_tables()
