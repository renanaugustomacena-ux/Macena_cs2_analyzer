"""
Shared test fixtures for Macena CS2 Analyzer test suite.

Provides:
- Path stabilization (centralized, replaces per-file setup)
- Database fixtures (in-memory for schema tests, real DB for data tests)
- Real-data fixtures with skip gates (no synthetic/mock data)
- Torch utilities

F9-05: real_db_session, real_player_stats, and real_round_stats use skip gates that are
MACHINE-DEPENDENT. On a developer machine with populated database.db: tests execute and
produce real coverage. On CI/CD or a fresh clone: tests skip silently — this is NOT a
passing verdict, merely an absence of test signal. True portability requires seeded
test fixtures; this is tracked as future work.

F9-07: Modules with NO dedicated test file (6500+ LOC of critical business logic):
  - backend/nn/training_orchestrator.py (733 LOC)
  - core/session_engine.py (538 LOC)  — Tri-Daemon (Hunter/Digester/Teacher)
  - backend/services/coaching_service.py (585 LOC)
  - backend/knowledge/experience_bank.py (751 LOC)
  - backend/processing/tensor_factory.py (686 LOC)
  - backend/nn/coach_manager.py (878 LOC)
Creating dedicated test files for these modules is tracked as future work.
"""

import os
import sys
from pathlib import Path

import pytest

# --- Path Stabilization (centralized for all tests) ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Prevent Kivy from hijacking CLI args
os.environ["KIVY_NO_ARGS"] = "1"


@pytest.fixture
def in_memory_db():
    """Create an isolated in-memory SQLite database with all tables.

    Useful for testing schema creation and ORM operations
    without touching the real database.
    """
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


@pytest.fixture
def real_db_session():
    """Open a session to the real database.db.

    Skips the test if the database file doesn't exist.
    Uses the production init_database() to ensure schema is current.
    """
    from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database

    db_path = PROJECT_ROOT / "Programma_CS2_RENAN" / "backend" / "storage" / "database.db"
    if not db_path.exists():
        pytest.skip("No real database.db found — cannot run data-dependent test")

    init_database()
    db = get_db_manager()
    with db.get_session() as session:
        yield session


@pytest.fixture
def real_player_stats(real_db_session):
    """Query the first real PlayerMatchStats record from the database.

    Skips if no match data exists.
    """
    from sqlmodel import select

    from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

    record = real_db_session.exec(select(PlayerMatchStats).limit(1)).first()
    if record is None:
        pytest.skip("No real PlayerMatchStats in DB — cannot run data-dependent test")
    return record


@pytest.fixture
def real_round_stats(real_db_session):
    """Query the first real RoundStats record from the database.

    Skips if no round data exists.
    """
    from sqlmodel import select

    from Programma_CS2_RENAN.backend.storage.db_models import RoundStats

    record = real_db_session.exec(select(RoundStats).limit(1)).first()
    if record is None:
        pytest.skip("No real RoundStats in DB — cannot run data-dependent test")
    return record


@pytest.fixture
def torch_no_grad():
    """Context manager that wraps test in torch.no_grad()."""
    import torch

    with torch.no_grad():
        yield
