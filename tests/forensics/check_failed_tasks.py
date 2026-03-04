import os
import sys
from pathlib import Path

# --- Venv Guard ---
if sys.prefix == sys.base_prefix:
    if "pytest" in sys.modules:
        pass  # Let pytest handle this
    else:
        print("ERROR: Not in venv.", file=sys.stderr)
        sys.exit(2)

# --- Path Stabilization ---
script_dir = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(script_dir))
if root not in sys.path:
    sys.path.insert(0, root)

from sqlmodel import select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask


def check_failed():
    db = get_db_manager()
    with db.get_session() as s:
        tasks = s.exec(select(IngestionTask).where(IngestionTask.status == "failed")).all()
        print(f"Found {len(tasks)} failed tasks.")
        for t in tasks:
            print(f"Task {t.id} ({os.path.basename(t.demo_path)}): {t.error_message}")


if __name__ == "__main__":
    check_failed()
