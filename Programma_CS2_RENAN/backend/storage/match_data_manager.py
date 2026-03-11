"""
Match Data Manager (Phase 2: Data Partitioning Reform)

Implements Tier 3 of the Three-Tier Storage Architecture:
- Each match's telemetry is stored in a separate SQLite file
- Location: PRO_DEMO_PATH/match_data/{match_id}.db (or in-project fallback)
- Solves the "Telemetry Cliff" problem (1.7M rows per match)

Architecture Benefits:
- B-Tree depth remains shallow for each file (fast queries)
- Deleting a match = deleting a file (simple management)
- Analyzing Match A doesn't lock Match B (concurrency)
- Infinite scalability limited only by disk space

Path Resolution:
- config.MATCH_DATA_PATH resolves to PRO_DEMO_PATH/match_data when available
- Falls back to backend/storage/match_data when external drive is disconnected
- On first startup after relocation, files are auto-migrated from old to new path
"""

import os
import threading
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, List, Optional

from sqlalchemy import event
from sqlmodel import Field, Session, SQLModel, create_engine, select

from Programma_CS2_RENAN.observability.logger_setup import get_logger

_logger = get_logger("cs2analyzer.match_data_manager")

# ============ Per-Match Telemetry Model ============


class MatchTickState(SQLModel, table=True):
    """
    Per-tick player state for a specific match.
    This model lives in individual match databases, NOT the main monolith.
    """

    __tablename__ = "match_tick_state"

    id: Optional[int] = Field(default=None, primary_key=True)
    tick: int = Field(index=True)
    round_number: int = Field(default=1, index=True)
    player_name: str = Field(index=True)
    steamid: int = Field(default=0, index=True)
    team: str = Field(default="CT")

    # Position
    pos_x: float = Field(default=0.0)
    pos_y: float = Field(default=0.0)
    pos_z: float = Field(default=0.0)
    yaw: float = Field(default=0.0)

    # State
    health: int = Field(default=100)
    armor: int = Field(default=0)
    is_alive: bool = Field(default=True)
    is_crouching: bool = Field(default=False)
    is_scoped: bool = Field(default=False)
    is_blinded: bool = Field(default=False)

    # Equipment
    active_weapon: str = Field(default="unknown")
    equipment_value: int = Field(default=0)
    money: int = Field(default=0)

    # Visibility (for Vision Bridge)
    enemies_visible: int = Field(default=0)

    # Outcome (for training labels)
    round_outcome: Optional[int] = None  # 1=Won, 0=Lost

    # --- WP6: Complete Data Extraction ---
    # Identity & Status
    has_helmet: bool = Field(default=False)
    has_defuser: bool = Field(default=False)
    ping: int = Field(default=0)

    # Round Context (Reset every round)
    kills_this_round: int = Field(default=0)
    deaths_this_round: int = Field(default=0)
    assists_this_round: int = Field(default=0)
    headshot_kills_this_round: int = Field(default=0)
    damage_this_round: int = Field(default=0)
    utility_damage_this_round: int = Field(default=0)
    enemies_flashed_this_round: int = Field(default=0)

    # Cumulative Stats (Total for match up to this tick)
    kills_total: int = Field(default=0)
    deaths_total: int = Field(default=0)
    assists_total: int = Field(default=0)
    headshot_kills_total: int = Field(default=0)
    mvps: int = Field(default=0)
    score: int = Field(default=0)

    # Economy (Granular)
    cash_spent_this_round: int = Field(default=0)
    cash_spent_total: int = Field(default=0)

    # --- Enriched Features (cross-player & contextual) ---
    pitch: float = Field(default=0.0)
    time_in_round: float = Field(default=0.0)
    bomb_planted: bool = Field(default=False)
    teammates_alive: int = Field(default=4)
    enemies_alive: int = Field(default=5)
    team_economy: int = Field(default=0)
    map_name: str = Field(default="de_unknown")

    # Timestamp for maintenance
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MatchEventState(SQLModel, table=True):
    """
    Per-event state for a specific match (Player-POV Perception System).

    Stores game events (weapon fire, grenade detonations, player damage/death,
    bomb interactions) for reconstructing the player's sensorial experience
    during training. The coach learns from SITUATIONS, not identities —
    player_name is used for intra-match player token creation only, NO steamid.
    """

    __tablename__ = "match_event_state"

    id: Optional[int] = Field(default=None, primary_key=True)
    tick: int = Field(index=True)
    round_number: int = Field(default=1, index=True)
    event_type: str = Field(index=True)

    # Actor identification (name for player tokens, NO steamid)
    player_name: str = Field(default="", index=True)
    player_team: str = Field(default="")

    # Actor situational state at time of event
    player_health: int = Field(default=100)
    player_armor: int = Field(default=0)
    player_equipment_value: int = Field(default=0)

    # Event position (world coordinates)
    pos_x: float = Field(default=0.0)
    pos_y: float = Field(default=0.0)
    pos_z: float = Field(default=0.0)

    # Event details
    weapon: str = Field(default="")
    damage: int = Field(default=0)
    is_headshot: bool = Field(default=False)

    # Victim info (for player_hurt / player_death events)
    victim_name: str = Field(default="")
    victim_team: str = Field(default="")
    victim_health: int = Field(default=100)
    victim_armor: int = Field(default=0)

    # Entity tracking (for smoke/molotov start→end pairing)
    # -1 is the sentinel for "entity_id not populated by parser" — avoids false pairing via default=0
    entity_id: int = Field(default=-1)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MatchMetadata(SQLModel, table=True):
    """
    Metadata about the match stored within the match database.
    Provides context without requiring access to main database.
    """

    __tablename__ = "match_metadata"

    id: Optional[int] = Field(default=None, primary_key=True)
    match_id: int = Field(index=True)
    demo_name: str
    map_name: str = Field(index=True)
    tick_count: int = Field(default=0)
    round_count: int = Field(default=0)
    player_count: int = Field(default=10)
    tick_rate: float = Field(default=64.0)

    # Teams
    team1_name: str = Field(default="Team 1")
    team2_name: str = Field(default="Team 2")
    team1_score: int = Field(default=0)
    team2_score: int = Field(default=0)

    # Processing info
    parser_version: str = Field(default="v1")
    is_pro_match: bool = Field(default=False)

    # Timestamps
    match_date: Optional[datetime] = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MatchDataManager:
    """
    Manager for per-match SQLite databases.

    Creates and manages individual database files for each match's telemetry,
    implementing Tier 3 of the Three-Tier Storage Architecture.

    Location is resolved via config.MATCH_DATA_PATH:
    - PRO_DEMO_PATH/match_data/ when the pro demo drive is available
    - backend/storage/match_data/ as fallback (in-project)
    """

    def __init__(self, match_data_path: str):
        """
        Initialize the match data manager.

        Args:
            match_data_path: Direct path to the match_data directory
                             (e.g., D:\\BASE_PER_DEMO\\DEMO_PRO_PLAYERS\\match_data)
        """
        self.match_data_path = match_data_path

        # Ensure match data directory exists
        os.makedirs(self.match_data_path, exist_ok=True)

        # M-18: True LRU cache using OrderedDict (was FIFO with plain dict)
        self._engines: OrderedDict = OrderedDict()
        self._engine_lock = threading.Lock()

    def _get_match_db_path(self, match_id: int) -> str:
        """Get the path to a match's database file."""
        return os.path.join(self.match_data_path, f"match_{match_id}.db")

    _MAX_CACHED_ENGINES = 50

    def _get_or_create_engine(self, match_id: int):
        """Get or create a SQLAlchemy engine for a match database."""
        with self._engine_lock:
            if match_id in self._engines:
                self._engines.move_to_end(match_id)  # M-18: mark as recently used
                return self._engines[match_id]

            # M-18: True LRU eviction — dispose least recently used (first item)
            if len(self._engines) >= self._MAX_CACHED_ENGINES:
                _, engine = self._engines.popitem(last=False)
                engine.dispose()

            db_path = self._get_match_db_path(match_id)
            db_url = f"sqlite:///{db_path}"

            engine = create_engine(
                db_url, echo=False, connect_args={"check_same_thread": False, "timeout": 30}
            )

            # Configure WAL mode for each match database
            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()

            # Create tables for this match.
            # R2-03: The tables= filter is CRITICAL. Removing it causes all ~20
            # global SQLModel tables to leak into every per-match database.
            _MATCH_TABLES = [
                MatchTickState.__table__,
                MatchEventState.__table__,
                MatchMetadata.__table__,
            ]
            SQLModel.metadata.create_all(engine, tables=_MATCH_TABLES)
            # Defensive check: verify only expected tables were created
            from sqlalchemy import inspect as sa_inspect
            created = set(sa_inspect(engine).get_table_names())
            expected = {t.name for t in _MATCH_TABLES}
            unexpected = created - expected
            if unexpected:
                logger.warning(
                    "R2-03: Unexpected tables in match DB %s: %s",
                    match_id, unexpected,
                )

            self._engines[match_id] = engine
            return engine

    def get_engine(self, match_id: int):
        """Public API to get or create a SQLAlchemy engine for a match database."""
        return self._get_or_create_engine(match_id)

    @contextmanager
    def get_match_session(self, match_id: int) -> Generator[Session, None, None]:
        """
        Get a session for a specific match database.

        Args:
            match_id: The match ID to get a session for

        Yields:
            SQLModel Session for the match database
        """
        engine = self._get_or_create_engine(match_id)
        with Session(engine, expire_on_commit=False) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def store_tick_batch(self, match_id: int, ticks: List[MatchTickState]) -> int:
        """
        Store a batch of tick states to a match database.

        Args:
            match_id: The match ID
            ticks: List of MatchTickState objects to store

        Returns:
            Number of ticks stored
        """
        if not ticks:
            return 0

        with self.get_match_session(match_id) as session:
            session.add_all(ticks)

        return len(ticks)

    def store_metadata(self, match_id: int, metadata: MatchMetadata) -> None:
        """Store match metadata."""
        with self.get_match_session(match_id) as session:
            # Replace existing metadata
            existing = session.exec(
                select(MatchMetadata).where(MatchMetadata.match_id == match_id)
            ).first()

            if existing:
                for key, value in metadata.model_dump(exclude_unset=True).items():
                    setattr(existing, key, value)
            else:
                session.add(metadata)

    def get_ticks_for_round(self, match_id: int, round_number: int) -> List[MatchTickState]:
        """Get all tick states for a specific round."""
        with self.get_match_session(match_id) as session:
            return list(
                session.exec(
                    select(MatchTickState)
                    .where(MatchTickState.round_number == round_number)
                    .order_by(MatchTickState.tick)
                ).all()
            )

    def get_player_ticks(
        self,
        match_id: int,
        steamid: int,
        start_tick: Optional[int] = None,
        end_tick: Optional[int] = None,
    ) -> List[MatchTickState]:
        """Get tick states for a specific player."""
        with self.get_match_session(match_id) as session:
            query = select(MatchTickState).where(MatchTickState.steamid == steamid)

            if start_tick is not None:
                query = query.where(MatchTickState.tick >= start_tick)
            if end_tick is not None:
                query = query.where(MatchTickState.tick <= end_tick)

            return list(session.exec(query.order_by(MatchTickState.tick)).all())

    def get_metadata(self, match_id: int) -> Optional[MatchMetadata]:
        """Get metadata for a match."""
        with self.get_match_session(match_id) as session:
            return session.exec(
                select(MatchMetadata).where(MatchMetadata.match_id == match_id)
            ).first()

    # ============ Event Storage & Query (Player-POV Perception) ============

    def store_event_batch(self, match_id: int, events: List[MatchEventState]) -> int:
        """Store a batch of game events to a match database.

        Returns:
            Number of events stored.
        """
        if not events:
            return 0

        with self.get_match_session(match_id) as session:
            session.add_all(events)

        return len(events)

    def get_events_for_tick_range(
        self,
        match_id: int,
        start_tick: int,
        end_tick: int,
        event_types: Optional[List[str]] = None,
    ) -> List[MatchEventState]:
        """Get events within a tick range, optionally filtered by type.

        Args:
            match_id: The match ID.
            start_tick: Start of tick range (inclusive).
            end_tick: End of tick range (inclusive).
            event_types: If provided, only return events of these types.

        Returns:
            List of MatchEventState records ordered by tick.
        """
        with self.get_match_session(match_id) as session:
            query = (
                select(MatchEventState)
                .where(MatchEventState.tick >= start_tick)
                .where(MatchEventState.tick <= end_tick)
            )
            if event_types:
                query = query.where(MatchEventState.event_type.in_(event_types))
            return list(session.exec(query.order_by(MatchEventState.tick)).all())

    def get_active_utilities(self, match_id: int, tick: int) -> List[MatchEventState]:
        """Get smoke/molotov events that are active at a given tick.

        An active utility is one where:
        - A smoke_start/molotov_start event exists with tick <= query tick
        - No matching smoke_end/molotov_end event exists with tick <= query tick
          (matched by entity_id)

        Returns:
            List of start events for utilities still active at the given tick.
        """
        with self.get_match_session(match_id) as session:
            # Get all utility start events up to this tick
            starts = list(
                session.exec(
                    select(MatchEventState)
                    .where(MatchEventState.tick <= tick)
                    .where(MatchEventState.event_type.in_(["smoke_start", "molotov_start"]))
                    .order_by(MatchEventState.tick)
                ).all()
            )

            if not starts:
                return []

            # Get all utility end events up to this tick
            ends = list(
                session.exec(
                    select(MatchEventState)
                    .where(MatchEventState.tick <= tick)
                    .where(MatchEventState.event_type.in_(["smoke_end", "molotov_end"]))
                ).all()
            )

            ended_entities = {e.entity_id for e in ends if e.entity_id != -1}
            valid_starts = [s for s in starts if s.entity_id != -1]
            unpopulated = len(starts) - len(valid_starts)
            if unpopulated > 0:
                _logger.warning(
                    "get_active_utilities: %d events have unpopulated entity_id (sentinel -1) "
                    "— parser failed to set entity_id for these events. Skipping them.",
                    unpopulated,
                )
            return [s for s in valid_starts if s.entity_id not in ended_entities]

    # ============ Multi-Player Query (Training Pipeline) ============

    def get_all_players_at_tick(self, match_id: int, tick: int) -> List[MatchTickState]:
        """Get all player states at a specific tick (~10 records).

        Used by PlayerKnowledgeBuilder to reconstruct the full game state
        from a single player's perspective.
        """
        with self.get_match_session(match_id) as session:
            return list(
                session.exec(select(MatchTickState).where(MatchTickState.tick == tick)).all()
            )

    def get_player_tick_window(
        self,
        match_id: int,
        player_name: str,
        center_tick: int,
        window_size: int = 320,
    ) -> List[MatchTickState]:
        """Get a player's ticks within a window around center_tick.

        Used for building temporal memory (last-known enemy positions).

        Args:
            match_id: The match ID.
            player_name: Player name to filter.
            center_tick: The center tick.
            window_size: Number of ticks before center_tick to include.

        Returns:
            List of MatchTickState ordered by tick.
        """
        start_tick = max(0, center_tick - window_size)
        with self.get_match_session(match_id) as session:
            return list(
                session.exec(
                    select(MatchTickState)
                    .where(MatchTickState.player_name == player_name)
                    .where(MatchTickState.tick >= start_tick)
                    .where(MatchTickState.tick <= center_tick)
                    .order_by(MatchTickState.tick)
                ).all()
            )

    def get_all_players_tick_window(
        self,
        match_id: int,
        center_tick: int,
        window_size: int = 320,
    ) -> dict:
        """Get ALL players' states within a tick window.

        Returns a dict mapping tick -> List[MatchTickState] for building
        enemy memory in PlayerKnowledgeBuilder. The window covers
        [center_tick - window_size, center_tick].

        At 64 tick/s with window_size=320 and 10 players, this returns
        ~3200 records. SQLite range scan with tick index: ~10ms.

        Args:
            match_id: The match ID.
            center_tick: The center tick.
            window_size: Number of ticks before center_tick to include.

        Returns:
            Dict[int, List[MatchTickState]] grouped by tick.
        """
        start_tick = max(0, center_tick - window_size)
        with self.get_match_session(match_id) as session:
            results = list(
                session.exec(
                    select(MatchTickState)
                    .where(MatchTickState.tick >= start_tick)
                    .where(MatchTickState.tick <= center_tick)
                    .order_by(MatchTickState.tick)
                ).all()
            )

        tick_groups: dict = {}
        for r in results:
            tick_groups.setdefault(r.tick, []).append(r)
        return tick_groups

    def list_available_matches(self) -> List[int]:
        """List all match IDs with stored data."""
        matches = []
        if os.path.exists(self.match_data_path):
            for filename in os.listdir(self.match_data_path):
                if filename.startswith("match_") and filename.endswith(".db"):
                    try:
                        match_id = int(filename[6:-3])  # Extract ID from "match_{id}.db"
                        matches.append(match_id)
                    except ValueError:
                        continue
        return sorted(matches)

    def delete_match(self, match_id: int) -> bool:
        """
        Delete a match's database file.

        Returns:
            True if deleted, False if not found
        """
        # Remove from engine cache (thread-safe — matches _get_or_create_engine)
        with self._engine_lock:
            if match_id in self._engines:
                self._engines[match_id].dispose()
                del self._engines[match_id]

        # Delete the file
        db_path = self._get_match_db_path(match_id)
        if os.path.exists(db_path):
            os.remove(db_path)
            # Also remove WAL files if they exist
            for ext in ["-wal", "-shm"]:
                wal_path = db_path + ext
                if os.path.exists(wal_path):
                    os.remove(wal_path)
            return True
        return False

    def get_match_size_bytes(self, match_id: int) -> int:
        """Get the size of a match database in bytes."""
        db_path = self._get_match_db_path(match_id)
        if os.path.exists(db_path):
            return os.path.getsize(db_path)
        return 0

    def get_total_storage_bytes(self) -> int:
        """Get total storage used by all match databases."""
        total = 0
        for match_id in self.list_available_matches():
            total += self.get_match_size_bytes(match_id)
        return total

    def close_all(self) -> None:
        """Close all cached engines."""
        for engine in self._engines.values():
            engine.dispose()
        self._engines.clear()


# ============ Singleton Instance ============

_match_data_manager: Optional[MatchDataManager] = None
_mdm_lock = threading.Lock()


def get_match_data_manager(match_data_path: Optional[str] = None) -> MatchDataManager:
    """
    Get the singleton MatchDataManager instance.

    Args:
        match_data_path: Direct path to match_data directory.
                         Only used on first call. Defaults to config.MATCH_DATA_PATH.
    """
    global _match_data_manager

    if _match_data_manager is not None:
        return _match_data_manager

    with _mdm_lock:
        if _match_data_manager is not None:
            return _match_data_manager
        if match_data_path is None:
            from Programma_CS2_RENAN.core.config import MATCH_DATA_PATH

            match_data_path = MATCH_DATA_PATH

        # One-time migration: move data from old in-project location if needed
        _OLD_IN_PROJECT = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "backend",
            "storage",
            "match_data",
        )
        if (
            os.path.normpath(match_data_path) != os.path.normpath(_OLD_IN_PROJECT)
            and os.path.isdir(_OLD_IN_PROJECT)
            and any(
                f.startswith("match_") and f.endswith(".db") for f in os.listdir(_OLD_IN_PROJECT)
            )
        ):
            from Programma_CS2_RENAN.observability.logger_setup import get_logger

            _logger = get_logger("cs2analyzer.match_data_migration")
            _logger.info("One-time migration: %s -> %s", _OLD_IN_PROJECT, match_data_path)
            result = migrate_match_data(_OLD_IN_PROJECT, match_data_path, logger=_logger)
            _logger.info(
                "Migration result: %d moved, %d skipped, %d errors",
                result["moved"],
                result["skipped"],
                len(result["errors"]),
            )

        _match_data_manager = MatchDataManager(match_data_path)

    return _match_data_manager


def reset_match_data_manager() -> None:
    """
    Reset the singleton so the next call to get_match_data_manager()
    re-reads MATCH_DATA_PATH from config.

    Required after PRO_DEMO_PATH changes. Callers must ensure
    no active sessions exist before calling.
    """
    global _match_data_manager
    if _match_data_manager is not None:
        _match_data_manager.close_all()
        _match_data_manager = None


def migrate_match_data(
    old_path: str,
    new_path: str,
    logger=None,
) -> dict:
    """
    Migrate match_data files from old location to new location.

    Steps:
    1. Close all open engines (flush WAL)
    2. For each match_*.db file in old_path: move to new_path (skip if exists)
    3. Move WAL/SHM files too
    4. Remove old directory if empty

    Returns:
        dict with keys: moved (int), skipped (int), errors (list[str])
    """
    import shutil

    result: dict = {"moved": 0, "skipped": 0, "errors": []}

    if not os.path.isdir(old_path):
        return result

    os.makedirs(new_path, exist_ok=True)

    # Close existing singleton to release all file handles
    global _match_data_manager
    if _match_data_manager is not None:
        _match_data_manager.close_all()
        _match_data_manager = None

    for filename in os.listdir(old_path):
        if not filename.startswith("match_"):
            continue
        if not (
            filename.endswith(".db") or filename.endswith(".db-wal") or filename.endswith(".db-shm")
        ):
            continue

        src = os.path.join(old_path, filename)
        dst = os.path.join(new_path, filename)

        if os.path.exists(dst):
            if logger:
                logger.warning("Skipping %s: already exists at destination", filename)
            result["skipped"] += 1
            continue

        try:
            shutil.move(src, dst)
            if filename.endswith(".db"):  # Only count main DB files
                result["moved"] += 1
            if logger:
                logger.info("Migrated %s", filename)
        except Exception as e:
            result["errors"].append(f"{filename}: {e}")
            if logger:
                logger.error("Failed to migrate %s: %s", filename, e)

    # Clean up empty source directory
    try:
        remaining = os.listdir(old_path)
        if not remaining:
            os.rmdir(old_path)
            if logger:
                logger.info("Removed empty source directory: %s", old_path)
    except OSError as e:
        if logger:
            logger.debug("Could not remove old match data dir %s: %s", old_path, e)

    return result
