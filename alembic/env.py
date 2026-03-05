import logging
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

alembic_logger = logging.getLogger("alembic.env")

# --- Path Stabilization (Manual Injection) ---
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Add project root to sys.path
from Programma_CS2_RENAN.core.config import stabilize_paths

PROJECT_ROOT = stabilize_paths()

# Import SQLModel and your models
from sqlmodel import SQLModel

from Programma_CS2_RENAN.backend.storage.db_models import (
    CoachingInsight,
    CoachState,
    IngestionTask,
    PlayerMatchStats,
    PlayerProfile,
    PlayerTickState,
    TacticalKnowledge,
)
from Programma_CS2_RENAN.core.config import DATABASE_URL

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = SQLModel.metadata

# Set the sqlalchemy.url from our config.py
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _pre_migration_backup() -> None:
    """Task [5.5]: Automatically backup monolith before schema migration."""
    try:
        from Programma_CS2_RENAN.backend.storage.db_backup import backup_monolith

        backup_path = backup_monolith()
        alembic_logger.info(f"Pre-migration backup created: {backup_path}")
    except Exception as e:
        alembic_logger.warning(f"Pre-migration backup failed (non-fatal): {e}")


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    _pre_migration_backup()

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
