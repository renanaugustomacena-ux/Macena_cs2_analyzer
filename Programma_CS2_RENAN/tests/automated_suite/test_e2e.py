import os
import sys

import pytest

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Programma_CS2_RENAN.backend.storage.database import init_database
from Programma_CS2_RENAN.Train_ML_Cycle import run_training_cycle


@pytest.mark.integration
def test_e2e_user_journey():
    """
    End-to-End Test (E2E): Simulate full lifecycle using real DB data.
    1. Initialize System
    2. Configure User (with cleanup)
    3. Verify sufficient real data exists (skip-gate)
    4. Run ML Training
    """
    from sqlmodel import select

    from Programma_CS2_RENAN.backend.storage.database import get_db_manager
    from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats
    from Programma_CS2_RENAN.core.config import load_user_settings, save_user_setting

    # 1. Init
    init_database()

    # 2. Config — save and restore original value
    original_settings = load_user_settings()
    original_name = original_settings.get("CS2_PLAYER_NAME")

    try:
        save_user_setting("CS2_PLAYER_NAME", "E2E_Test_Player")

        # 3. Verify sufficient real data exists (skip-gate — no synthetic seeding)
        db = get_db_manager()
        with db.get_session() as session:
            real_stats = session.exec(select(PlayerMatchStats).limit(10)).all()
        if len(real_stats) < 5:
            pytest.skip(
                f"Not enough real data for E2E test (found {len(real_stats)}, need 5+). "
                "Run ingestion first to populate the database."
            )

        # 4. Run Training Cycle with real data
        try:
            run_training_cycle()
        except Exception as e:
            pytest.fail(f"E2E Lifecycle Failed during Training: {e}")

        print("E2E Backend Lifecycle Complete.")

    finally:
        # Restore original player name
        if original_name is not None:
            save_user_setting("CS2_PLAYER_NAME", original_name)
