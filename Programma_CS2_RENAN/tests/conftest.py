"""
Shared test fixtures for Macena CS2 Analyzer test suite.

Provides:
- Path stabilization (centralized, replaces per-file setup)
- Database fixtures (in-memory for schema tests, real DB for data tests)
- Seeded fixtures for CI-portable tests (no machine-dependent skip gates)
- Real-data fixtures with skip gates for integration tests
- Torch utilities

Fixture hierarchy:
  in_memory_db        — empty schema, for ORM/migration tests
  seeded_db_session   — in-memory DB with realistic CS2 data, CI-portable
  real_db_session      — production database.db, developer-machine only (integration)
"""

import os
import sys
from pathlib import Path

# --- Venv Guard ---
if sys.prefix == sys.base_prefix:
    import pytest
    pytest.exit("Not running in virtualenv — activate before running tests", returncode=2)

import pytest

# --- Path Stabilization (centralized for all tests) ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Prevent Kivy from hijacking CLI args
os.environ["KIVY_NO_ARGS"] = "1"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: tests that read/write production database.db"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless CS2_INTEGRATION_TESTS=1 is set."""
    if os.environ.get("CS2_INTEGRATION_TESTS") == "1":
        return
    skip_integration = pytest.mark.skip(
        reason="Set CS2_INTEGRATION_TESTS=1 to run integration tests on production DB"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture
def in_memory_db():
    """Create an isolated in-memory SQLite database with all tables.

    Useful for testing schema creation and ORM operations
    without touching the real database.

    Note (PT2-18): This fixture uses SQLModel.metadata.create_all() rather than
    init_database(). This is intentional: init_database() is designed for the real
    WAL-mode SQLite file and performs operations (PRAGMA journal_mode=WAL, default
    row inserts) that are not meaningful for an in-memory session. The schema created
    here is equivalent for ORM testing purposes — all SQLModel-registered tables are
    created. If init_database() ever adds schema that is NOT reflected in SQLModel
    metadata (e.g. raw CREATE TABLE via sqlite3), this fixture must be updated.
    """
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


@pytest.fixture
def seeded_db_session():
    """In-memory DB pre-populated with realistic CS2 match data.

    CI-portable: works on any machine without database.db.
    Contains 6 PlayerMatchStats, 12 RoundStats, 1 PlayerProfile.
    Data values are derived from realistic CS2 gameplay ranges.
    """
    from datetime import datetime, timezone

    from sqlmodel import Session, SQLModel, create_engine

    from Programma_CS2_RENAN.backend.storage.db_models import (
        PlayerMatchStats,
        PlayerProfile,
        RoundStats,
    )

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # --- PlayerProfile ---
        session.add(
            PlayerProfile(player_name="TestPlayer", role="Entry", bio="Test profile")
        )

        # --- PlayerMatchStats: 6 records across 3 demos, 2 players ---
        _fixed_dt = datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        _demos = [
            ("demo_dust2_20240615.dem", _fixed_dt),
            ("demo_mirage_20240616.dem", datetime(2024, 6, 16, 18, 0, 0, tzinfo=timezone.utc)),
            ("demo_inferno_20240617.dem", datetime(2024, 6, 17, 20, 0, 0, tzinfo=timezone.utc)),
        ]
        _players = [
            {
                "player_name": "TestPlayer",
                "stats": [
                    # dust2: solid game
                    dict(avg_kills=22.0, avg_deaths=16.0, avg_adr=85.3, avg_hs=0.52,
                         avg_kast=0.72, accuracy=0.28, econ_rating=1.12, kd_ratio=1.375,
                         kpr=0.75, dpr=0.55, rating=1.15, opening_duel_win_pct=0.55,
                         clutch_win_pct=0.33, trade_kill_ratio=0.18, was_traded_ratio=0.25),
                    # mirage: average game
                    dict(avg_kills=17.0, avg_deaths=18.0, avg_adr=72.1, avg_hs=0.45,
                         avg_kast=0.65, accuracy=0.24, econ_rating=0.95, kd_ratio=0.944,
                         kpr=0.62, dpr=0.65, rating=0.94, opening_duel_win_pct=0.40,
                         clutch_win_pct=0.00, trade_kill_ratio=0.12, was_traded_ratio=0.33),
                    # inferno: great game
                    dict(avg_kills=28.0, avg_deaths=14.0, avg_adr=98.7, avg_hs=0.60,
                         avg_kast=0.80, accuracy=0.31, econ_rating=1.25, kd_ratio=2.0,
                         kpr=0.90, dpr=0.45, rating=1.45, opening_duel_win_pct=0.65,
                         clutch_win_pct=0.50, trade_kill_ratio=0.22, was_traded_ratio=0.14),
                ],
            },
            {
                "player_name": "Teammate1",
                "stats": [
                    dict(avg_kills=15.0, avg_deaths=19.0, avg_adr=65.0, avg_hs=0.38,
                         avg_kast=0.60, accuracy=0.22, econ_rating=0.88, kd_ratio=0.789,
                         kpr=0.54, dpr=0.68, rating=0.82),
                    dict(avg_kills=20.0, avg_deaths=15.0, avg_adr=80.0, avg_hs=0.50,
                         avg_kast=0.70, accuracy=0.26, econ_rating=1.05, kd_ratio=1.333,
                         kpr=0.71, dpr=0.54, rating=1.10),
                    dict(avg_kills=12.0, avg_deaths=20.0, avg_adr=55.0, avg_hs=0.35,
                         avg_kast=0.55, accuracy=0.20, econ_rating=0.75, kd_ratio=0.6,
                         kpr=0.43, dpr=0.71, rating=0.68),
                ],
            },
        ]
        for player_data in _players:
            for i, (demo_name, match_date) in enumerate(_demos):
                s = player_data["stats"][i]
                session.add(
                    PlayerMatchStats(
                        player_name=player_data["player_name"],
                        demo_name=demo_name,
                        match_date=match_date,
                        processed_at=match_date,
                        **s,
                    )
                )

        # --- RoundStats: 4 rounds × 2 players for first demo ---
        for rnd in range(1, 5):
            for pname, side in [("TestPlayer", "CT"), ("Teammate1", "T")]:
                session.add(
                    RoundStats(
                        demo_name="demo_dust2_20240615.dem",
                        round_number=rnd,
                        player_name=pname,
                        side=side,
                        kills=min(rnd, 3),
                        deaths=1 if rnd % 2 == 0 else 0,
                        assists=1 if rnd > 2 else 0,
                        damage_dealt=55 + rnd * 15,
                        headshot_kills=1 if rnd % 2 == 1 else 0,
                        equipment_value=1000 + rnd * 1500,
                        round_won=rnd % 2 == 1,
                    )
                )

        session.commit()
        yield session


@pytest.fixture
def seeded_player_stats(seeded_db_session):
    """First PlayerMatchStats record from the seeded database."""
    from sqlmodel import select

    from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

    return seeded_db_session.exec(select(PlayerMatchStats).limit(1)).first()


@pytest.fixture
def seeded_round_stats(seeded_db_session):
    """First RoundStats record from the seeded database."""
    from sqlmodel import select

    from Programma_CS2_RENAN.backend.storage.db_models import RoundStats

    return seeded_db_session.exec(select(RoundStats).limit(1)).first()


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


@pytest.fixture
def rap_model():
    """Deterministic RAPCoachModel for unit testing (CPU-only, seed=42)."""
    import torch

    from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel
    from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

    torch.manual_seed(42)
    model = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
    model.eval()
    return model


@pytest.fixture
def rap_inputs():
    """Deterministic input tensors for RAP model testing.

    Shapes follow TrainingTensorConfig:
      view/map/motion: (batch=2, 3, 64, 64)
      metadata: (batch=2, seq_len=5, METADATA_DIM)
      skill_vec: (batch=2, 10)
    """
    import torch

    from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

    torch.manual_seed(42)
    batch_size, seq_len = 2, 5
    return {
        "view": torch.randn(batch_size, 3, 64, 64),
        "map": torch.randn(batch_size, 3, 64, 64),
        "motion": torch.randn(batch_size, 3, 64, 64),
        "metadata": torch.randn(batch_size, seq_len, METADATA_DIM),
        "skill_vec": torch.zeros(batch_size, 10),
    }


@pytest.fixture
def mock_db_manager():
    """In-memory DatabaseManager replacement for testing DB-dependent code.

    Provides get_session() context manager and get() method without touching
    the real database.db file. Uses SQLModel.metadata.create_all() to build
    the full schema in :memory:.
    """
    from contextlib import contextmanager

    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    class InMemoryDBManager:
        def __init__(self):
            self.engine = engine

        @contextmanager
        def get_session(self, engine_key="default"):
            with Session(engine, expire_on_commit=False) as session:
                try:
                    yield session
                    session.commit()
                except Exception:
                    session.rollback()
                    raise

        def get(self, model_class, pk):
            with self.get_session() as session:
                return session.get(model_class, pk)

        def create_db_and_tables(self):
            SQLModel.metadata.create_all(engine)

        def upsert(self, model_instance):
            with self.get_session() as session:
                return session.merge(model_instance)

    return InMemoryDBManager()
