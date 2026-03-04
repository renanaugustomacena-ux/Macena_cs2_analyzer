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

from sqlmodel import Session, func, select

# Add project root to sys.path
sys.path.append(str(Path(__file__).parents[1]))

from Programma_CS2_RENAN.backend.storage.database import DatabaseManager
from Programma_CS2_RENAN.backend.storage.db_models import Ext_PlayerPlaystyle, Ext_TeamRoundStats


def verify_ingestion():
    db = DatabaseManager()

    print("Verifying CSV Ingestion...")

    with db.get_session() as session:
        # Check Team Round Stats
        team_stats_count = session.exec(select(func.count(Ext_TeamRoundStats.id))).one()
        print(f"Ext_TeamRoundStats Count: {team_stats_count}")

        if team_stats_count > 0:
            sample = session.exec(select(Ext_TeamRoundStats).limit(1)).first()
            print(
                f"Sample Team Stat: Match {sample.external_match_id} - {sample.team_name} - Round {sample.round_num} - Money {sample.money_spent}"
            )
        else:
            print("WARNING: Ext_TeamRoundStats is empty!")

        # Check Player Playstyles
        playstyle_count = session.exec(select(func.count(Ext_PlayerPlaystyle.id))).one()
        print(f"Ext_PlayerPlaystyle Count: {playstyle_count}")

        if playstyle_count > 0:
            sample = session.exec(select(Ext_PlayerPlaystyle).limit(1)).first()
            print(
                f"Sample Playstyle: {sample.player_name} ({sample.team_name}) - Role: {sample.assigned_role} - Lurker Score: {sample.role_lurker}"
            )
        else:
            print("WARNING: Ext_PlayerPlaystyle is empty!")

    if team_stats_count > 0 and playstyle_count > 0:
        print("SUCCESS: Data ingestion verified.")
        return True
    else:
        print("SKIP: No ingested data found (run CSV ingestion first).")
        return False


if __name__ == "__main__":
    if not verify_ingestion():
        sys.exit(1)
