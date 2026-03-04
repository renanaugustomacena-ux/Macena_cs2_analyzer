import os
import sys

# --- Venv Guard ---
if sys.prefix == sys.base_prefix:
    if "pytest" in sys.modules:
        pass  # Let pytest handle this
    else:
        print("ERROR: Not in venv.", file=sys.stderr)
        sys.exit(2)

# --- Path Stabilization ---
# Calculate root manually since we can't import core.config yet
script_dir = os.path.dirname(os.path.abspath(__file__))
# script is in tests/forensics
# root is up 2 levels
root = os.path.dirname(os.path.dirname(script_dir))
if root not in sys.path:
    sys.path.insert(0, root)

from sqlmodel import func, select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask, PlayerMatchStats

db = get_db_manager()
with db.get_session() as s:
    u_cnt = s.exec(
        select(func.count(PlayerMatchStats.id)).where(PlayerMatchStats.is_pro == False)
    ).one()
    p_cnt = s.exec(
        select(func.count(PlayerMatchStats.id)).where(PlayerMatchStats.is_pro == True)
    ).one()
    print(f"User Demos: {u_cnt}")
    print(f"Pro Demos: {p_cnt}")

    queued = s.exec(
        select(func.count(IngestionTask.id)).where(IngestionTask.status == "queued")
    ).one()
    proc = s.exec(
        select(func.count(IngestionTask.id)).where(IngestionTask.status == "processing")
    ).one()
    done = s.exec(
        select(func.count(IngestionTask.id)).where(IngestionTask.status == "completed")
    ).one()
    fail = s.exec(
        select(func.count(IngestionTask.id)).where(IngestionTask.status == "failed")
    ).one()
    print(f"Tasks - Queued: {queued}, Processing: {proc}, Done: {done}, Failed: {fail}")

    if fail > 0:
        print("\n--- Failed Task Samples ---")
        fails = s.exec(select(IngestionTask).where(IngestionTask.status == "failed").limit(5)).all()
        for f in fails:
            print(f"Path: {f.demo_path} | Error: {f.error_message}")
