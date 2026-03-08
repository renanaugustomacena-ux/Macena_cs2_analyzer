from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import field_validator
from sqlalchemy import CheckConstraint, Column, Index, String, UniqueConstraint
from sqlmodel import Field, SQLModel

# Maximum allowed size (bytes) for game_state_json in CoachingExperience.
# 10 players × ~30 fields ≈ 5–10 KB per snapshot. Cap prevents unbounded DB growth.
MAX_GAME_STATE_JSON_BYTES = 16_384  # 16 KB


# --- Enums for Data Integrity ---
class DatasetSplit(str, Enum):
    """Valid dataset split values for ML pipelines."""

    TRAIN = "train"
    VAL = "val"
    TEST = "test"
    UNASSIGNED = "unassigned"


class CoachStatus(str, Enum):
    """Valid status values for the ML coaching pipeline."""

    PAUSED = "Paused"
    TRAINING = "Training"
    IDLE = "Idle"
    ERROR = "Error"


class PlayerMatchStats(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("demo_name", "player_name", name="ux_playermatchstats_demo_player"),
        CheckConstraint("avg_kills >= 0", name="ck_playermatchstats_avg_kills_positive"),
        CheckConstraint("avg_adr >= 0", name="ck_playermatchstats_avg_adr_positive"),
        CheckConstraint("rating >= 0 AND rating <= 5.0", name="ck_playermatchstats_rating_range"),
        {"extend_existing": True},
    )
    id: Optional[int] = Field(default=None, primary_key=True)

    player_name: str = Field(index=True)
    demo_name: str = Field(index=True)
    match_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )  # Task 2.17.2: Chronological Sort
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    dataset_split: DatasetSplit = Field(
        default=DatasetSplit.UNASSIGNED, index=True
    )  # Enum-validated

    avg_kills: float = Field(default=0.0)
    avg_deaths: float = Field(default=0.0)
    avg_adr: float = Field(default=0.0)
    avg_hs: float = Field(default=0.0)
    avg_kast: float = Field(default=0.0)

    accuracy: float = Field(default=0.0)
    econ_rating: float = Field(default=0.0)

    kill_std: float = Field(default=0.0)
    adr_std: float = Field(default=0.0)
    kd_ratio: float = Field(default=0.0)
    impact_rounds: float = Field(default=0.0)

    utility_blind_time: float = Field(default=0.0)
    utility_enemies_blinded: float = Field(default=0.0)
    flash_assists: float = Field(default=0.0)  # For analytics skill radar
    opening_duel_win_pct: float = Field(default=0.0)
    clutch_win_pct: float = Field(default=0.0)
    positional_aggression_score: float = Field(default=0.0)

    # --- HLTV 2.0 Components ---
    kpr: float = Field(default=0.0)  # Kills Per Round
    dpr: float = Field(default=0.0)  # Deaths Per Round
    rating_impact: float = Field(default=0.0)
    rating_survival: float = Field(default=0.0)
    rating_kast: float = Field(default=0.0)
    rating_kpr: float = Field(default=0.0)
    rating_adr: float = Field(default=0.0)

    # --- Trade Kill Metrics ---
    trade_kill_ratio: float = Field(default=0.0)  # trade_kills / total_kills
    was_traded_ratio: float = Field(default=0.0)  # deaths_traded / total_deaths
    avg_trade_response_ticks: float = Field(default=0.0)  # Lower = faster team response

    # --- Kill Enrichment ---
    thrusmoke_kill_pct: float = Field(default=0.0)  # % of kills through smoke
    wallbang_kill_pct: float = Field(default=0.0)  # % of kills through walls
    noscope_kill_pct: float = Field(default=0.0)  # % of kills without scoping
    blind_kill_pct: float = Field(default=0.0)  # % of kills while attacker blinded

    # --- Utility Breakdown ---
    he_damage_per_round: float = Field(default=0.0)
    molotov_damage_per_round: float = Field(default=0.0)
    smokes_per_round: float = Field(default=0.0)
    unused_utility_per_round: float = Field(default=0.0)

    anomaly_score: float = Field(default=0.0)
    sample_weight: float = Field(default=1.0)
    is_pro: bool = Field(default=False)
    rating: float = Field(default=0.0)
    pro_player_id: Optional[int] = Field(default=None, index=True)  # Logical ref to ProPlayer.hltv_id (separate DB — no FK)


class PlayerTickState(SQLModel, table=True):
    __table_args__ = (
        Index("ix_tick_demo_tick", "demo_name", "tick"),
        Index("ix_pts_player_demo", "player_name", "demo_name"),  # P2-05: Composite index for common query pattern
        {"extend_existing": True},
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    id: Optional[int] = Field(default=None, primary_key=True)
    match_id: Optional[int] = Field(
        default=None, foreign_key="matchresult.match_id", index=True
    )  # FK: None instead of 0 to avoid FK violation
    tick: int = Field(index=True)
    player_name: str = Field(index=True)
    demo_name: str = Field(default="unknown", index=True)  # NEW: Enable proper split filtering

    pos_x: float = Field(default=0.0)
    pos_y: float = Field(default=0.0)
    pos_z: float = Field(default=0.0)
    view_x: float = Field(default=0.0)
    view_y: float = Field(default=0.0)

    health: int = Field(default=0)
    armor: int = Field(default=0)
    is_crouching: bool = Field(default=False)
    is_scoped: bool = Field(default=False)
    active_weapon: str = Field(default="unknown")
    equipment_value: int = Field(default=0)

    enemies_visible: int = Field(default=0)
    is_blinded: bool = Field(default=False)
    round_outcome: Optional[int] = None

    # --- Enriched Features (cross-player & contextual) ---
    round_number: int = Field(default=1)
    time_in_round: float = Field(default=0.0)
    bomb_planted: bool = Field(default=False)
    teammates_alive: int = Field(default=4)
    enemies_alive: int = Field(default=5)
    team_economy: int = Field(default=0)
    map_name: str = Field(default="de_unknown")


class PlayerProfile(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    player_name: str = Field(index=True, unique=True)

    bio: Optional[str] = Field(default="No description yet.", max_length=500)
    profile_pic_path: Optional[str] = None
    role: Optional[str] = Field(default="All-Rounder")


# --- External Data Extensions (Task 2.17.3) ---
class Ext_TeamRoundStats(SQLModel, table=True):
    """
    Stores team-level round statistics from external CSVs (e.g. tournament_advanced_stats.csv).
    """

    __table_args__ = {"extend_existing": True}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    id: Optional[int] = Field(default=None, primary_key=True)
    match_id: int = Field(index=True)  # Linked to internal Match ID if possible, or external ID
    external_match_id: int = Field(index=True)  # ID from the CSV
    map_name: str = Field(index=True)
    round_num: int
    team_name: str = Field(index=True)

    # Economy & Damage
    equipment_value: float = Field(default=0.0)
    money_spent: float = Field(default=0.0)
    utility_value: float = Field(default=0.0)
    damage: float = Field(default=0.0)
    hits: int = Field(default=0)
    shots: int = Field(default=0)

    # Kills/Deaths
    kills: int = Field(default=0)
    deaths: int = Field(default=0)
    headshots: int = Field(default=0)
    first_kills: int = Field(default=0)
    first_deaths: int = Field(default=0)

    # Calculated
    accuracy: float = Field(default=0.0)
    econ_rating: float = Field(default=0.0)


class Ext_PlayerPlaystyle(SQLModel, table=True):
    """
    Stores aggregated playstyle roles from external sources (e.g. cs2_playstyle_roles_2024.csv).
    """

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    player_name: str = Field(index=True)
    steamid: Optional[str] = Field(
        default=None, index=True
    )  # Legacy CSV import field; prefer steam_id
    team_name: str = Field(index=True)

    # Role Probabilities / Assignments
    role_lurker: float = Field(default=0.0)
    role_entry: float = Field(default=0.0)
    role_support: float = Field(default=0.0)
    role_awper: float = Field(default=0.0)
    role_anchor: float = Field(default=0.0)
    role_igl: float = Field(default=0.0)

    assigned_role: str = Field(default="Flex")  # The dominant role

    # Aggregated Metrics (from the CSV usually)
    rating_impact: float = Field(default=0.0)
    aggression_score: float = Field(default=0.0)

    # Raw Metrics from cs2_playstyle_roles_2024
    tapd: float = Field(default=0.0)  # Time Alive Per Death? Or Team Adjusted Player Damage?
    oap: float = Field(default=0.0)  # Opening Action Participation?
    podt: float = Field(default=0.0)  # Percentage Trade?

    # NOTE: User-profile fields are mixed into this playstyle model for historical reasons.
    # The table conflates CS2 playstyle statistics with user account metadata.
    # Candidate for a future migration that splits user profile fields into a separate table.
    social_links_json: Optional[str] = Field(default="{}")
    pc_specs_json: Optional[str] = Field(default="{}")
    graphic_settings_json: Optional[str] = Field(default="{}")
    cfg_file_path: Optional[str] = None

    steam_id: Optional[str] = Field(
        default=None, unique=True, index=True
    )  # Unique constraint added
    steam_avatar_url: Optional[str] = None
    steam_connected: bool = Field(default=False)
    faceit_connected: bool = Field(default=False)

    monthly_upload_count: int = Field(default=0)
    total_upload_count: int = Field(default=0)
    last_upload_month: int = Field(default_factory=lambda: datetime.now(timezone.utc).month)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CoachingInsight(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)

    player_name: str = Field(index=True)
    demo_name: str = Field(index=True)

    title: str
    severity: str
    message: str
    focus_area: str
    user_id: Optional[str] = Field(default="default_user", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestionTask(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    demo_path: str = Field(index=True, unique=True)
    is_pro: bool = Field(default=False)
    status: str = Field(default="queued", index=True)
    last_tick_processed: int = Field(default=0)
    retry_count: int = Field(default=0)
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # MAINTENANCE TRAP: updated_at has no ORM-level auto-refresh.
    # Any code path that updates an IngestionTask MUST manually set:
    #   task.updated_at = datetime.now(timezone.utc)
    # Failing to do so leaves stale timestamps silently.
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))



class TacticalKnowledge(SQLModel, table=True):
    """RAG Knowledge Base for tactical coaching insights."""

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)

    # Content
    title: str = Field(index=True)
    description: str
    category: str = Field(index=True)  # "positioning", "economy", "utility", "aim"
    map_name: Optional[str] = Field(default=None, index=True)

    # Context
    situation: str  # "T-side pistol round", "CT retake A site"
    pro_example: Optional[str] = None  # Reference to pro demo

    # Vector embedding (JSON-encoded for SQLite compatibility)
    embedding: str  # JSON array of floats [384-dim]

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    usage_count: int = Field(default=0)


class CoachState(SQLModel, table=True):
    """Detailed status of the ML pipeline for the GUI.

    Singleton: exactly one row with id=1 enforced by CHECK constraint (P2-01).
    """

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_coachstate_singleton"),
        {"extend_existing": True},
    )
    id: Optional[int] = Field(default=1, primary_key=True)

    # Global View
    # sa_column=String to store enum .value ("Paused") not .name ("PAUSED") — backward-compatible with existing DB rows
    status: CoachStatus = Field(
        default=CoachStatus.PAUSED, sa_column=Column("status", String, default="Paused")
    )
    belief_confidence: float = Field(default=0.0)

    # Triple-Daemon Tracking
    hltv_status: str = Field(default="Idle")  # Hunter
    ingest_status: str = Field(default="Idle")  # Digester
    ml_status: str = Field(default="Idle")  # Teacher

    # Training Progress - Real-Time Feedback
    current_epoch: int = Field(default=0)
    total_epochs: int = Field(default=0)
    train_loss: float = Field(default=0.0)
    val_loss: float = Field(default=0.0)
    eta_seconds: float = Field(default=0.0)

    detail: str = Field(default="System ready")

    # Heartbeat Telemetry
    service_pid: Optional[int] = Field(default=None)
    system_load_cpu: float = Field(default=0.0)
    system_load_mem: float = Field(default=0.0)

    last_trained_sample_count: int = Field(default=0)
    last_heartbeat: Optional[datetime] = Field(default=None)
    last_ingest_sync: Optional[datetime] = Field(default=None)
    last_pro_ingest_sync: Optional[datetime] = Field(default=None)
    pro_ingest_interval: float = Field(default=1.0)  # Hours between pro parses
    parsing_progress: float = Field(default=0.0)  # 0.0 to 100.0

    # Maturity Gating for Professional Corrections
    total_matches_processed: int = Field(default=0)

    # Global System Performance (0.0 to 1.0)
    cpu_limit: float = Field(default=0.5)
    ram_limit: float = Field(default=0.5)
    gpu_limit: float = Field(default=0.5)

    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ServiceNotification(SQLModel, table=True):
    """Queue for background errors and events to be shown in the UI."""

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    daemon: str = Field(index=True)  # "hunter", "digester", "teacher"
    severity: str = Field(default="ERROR")  # "INFO", "WARNING", "ERROR", "CRITICAL"
    message: str
    is_read: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProTeam(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    hltv_id: int = Field(index=True, unique=True)
    name: str = Field(index=True)
    world_rank: Optional[int] = None
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProPlayer(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    hltv_id: int = Field(index=True, unique=True)
    nickname: str = Field(index=True)
    real_name: Optional[str] = None
    country: Optional[str] = None
    age: Optional[int] = None
    team_id: Optional[int] = Field(default=None, foreign_key="proteam.hltv_id")
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProPlayerStatCard(SQLModel, table=True):
    """
    Comprehensive statistical profile derived from HLTV crawling.
    Represents a snapshot of a player's form over a specific period.
    """

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    player_id: int = Field(foreign_key="proplayer.hltv_id", index=True)

    # Core Stats (Main Page)
    rating_2_0: float = Field(default=0.0)
    dpr: float = Field(default=0.0)  # Deaths per round
    kast: float = Field(default=0.0)
    impact: float = Field(default=0.0)
    adr: float = Field(default=0.0)
    kpr: float = Field(default=0.0)
    headshot_pct: float = Field(default=0.0)
    maps_played: int = Field(default=0)

    # Opening Duels (Static Baseline)
    opening_kill_ratio: float = Field(default=0.0)
    opening_duel_win_pct: float = Field(default=0.0)

    # Clutches & Multi-kills (Summary)
    clutch_win_count: int = Field(default=0)
    multikill_round_pct: float = Field(default=0.0)

    # Granular Dimensions (Stored as JSON for flexibility)
    # Includes weapon usage, map win rates, and specific clutch tiers (1v1, 1v2).
    detailed_stats_json: str = Field(default="{}")

    time_span: str = Field(default="all_time")  # "last_3_months", "2024", etc.
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MatchResult(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    match_id: int = Field(primary_key=True)  # From external ID or auto
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    team_a_id: Optional[int] = None
    team_b_id: Optional[int] = None
    winner_id: Optional[int] = None
    event_name: str = Field(index=True)
    map_picks: Optional[str] = None  # JSON string for flexibility if needed quick


class MapVeto(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    id: Optional[int] = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matchresult.match_id", index=True)
    map_name: str
    action: str = Field(default="unknown")  # 'pick', 'ban', 'leftover'
    team_id: Optional[int] = None


class CoachingExperience(SQLModel, table=True):
    """
    COPER Framework: Experience Bank for contextual coaching.

    Stores learned experiences from gameplay to enable:
    - Retrieval of similar past situations
    - Pro player reference linking
    - Narrative advice synthesis with context

    Adheres to GEMINI.md: Explicit state, high-fidelity data.
    """

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)

    # Context Identification
    context_hash: str = Field(index=True)  # Hash of game state for fast lookup
    map_name: str = Field(index=True)
    round_phase: str = Field(default="unknown")  # "pistol", "eco", "full_buy", "force"
    side: str = Field(default="unknown")  # "T" or "CT"
    position_area: Optional[str] = Field(default=None, index=True)  # "A-site", "Mid", etc.

    # Game State Snapshot (JSON for flexibility)
    game_state_json: str = Field(default="{}")  # Full tick data at moment of experience

    # P2-02: Enforce MAX_GAME_STATE_JSON_BYTES to prevent unbounded DB growth
    @field_validator("game_state_json")
    @classmethod
    def validate_json_size(cls, v: str) -> str:
        if v and len(v.encode("utf-8")) > MAX_GAME_STATE_JSON_BYTES:
            raise ValueError(
                f"game_state_json exceeds {MAX_GAME_STATE_JSON_BYTES} bytes "
                f"({len(v.encode('utf-8'))} bytes)"
            )
        return v

    # Action & Outcome
    action_taken: str  # "pushed", "held_angle", "rotated", "used_utility", etc.
    outcome: str = Field(index=True)  # "kill", "death", "trade", "objective", "survived"
    delta_win_prob: float = Field(default=0.0)  # Win probability change from this action

    # Quality Metrics
    confidence: float = Field(default=0.5)  # How reliable/generalizable (0.0-1.0)
    usage_count: int = Field(default=0)  # How often retrieved for coaching

    # Pro Reference Linking
    pro_match_id: Optional[int] = Field(default=None, foreign_key="matchresult.match_id")
    pro_player_name: Optional[str] = Field(default=None, index=True)

    # Vector Embedding for Semantic Search (JSON-encoded 384-dim)
    embedding: Optional[str] = Field(default=None)

    # Metadata
    source_demo: Optional[str] = Field(default=None)  # Which demo this came from
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Feedback Loop Tracking (COPER Intelligence)
    outcome_validated: bool = Field(default=False)
    effectiveness_score: float = Field(default=0.0)  # -1.0 to 1.0
    follow_up_match_id: Optional[int] = Field(default=None)
    times_advice_given: int = Field(default=0)
    times_advice_followed: int = Field(default=0)
    last_feedback_at: Optional[datetime] = Field(default=None)


class RoundStats(SQLModel, table=True):
    """
    Per-round, per-player statistical isolation layer (Fusion Plan Proposal 4).

    Provides explicit round-level aggregation that prevents cross-round stat
    contamination and enables round-by-round coaching drill-down.

    Data flow: Raw ticks → RoundStats → PlayerMatchStats (aggregation)
    """

    __table_args__ = (
        Index("ix_rs_demo_player", "demo_name", "player_name"),
        Index("ix_rs_demo_round", "demo_name", "round_number"),  # P2-05: Composite index for round queries
        {"extend_existing": True},
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    id: Optional[int] = Field(default=None, primary_key=True)
    demo_name: str = Field(index=True)
    round_number: int = Field(index=True)
    player_name: str = Field(index=True)
    side: str = Field(default="unknown")  # "CT" or "T"

    # Core stats
    kills: int = Field(default=0)
    deaths: int = Field(default=0)  # 0 or 1
    assists: int = Field(default=0)
    damage_dealt: int = Field(default=0)

    # Kill enrichment (Proposal 1)
    headshot_kills: int = Field(default=0)
    trade_kills: int = Field(default=0)
    was_traded: bool = Field(default=False)
    thrusmoke_kills: int = Field(default=0)
    wallbang_kills: int = Field(default=0)

    # Opening duel
    opening_kill: bool = Field(default=False)
    opening_death: bool = Field(default=False)

    # Utility (Proposal 2)
    he_damage: float = Field(default=0.0)
    molotov_damage: float = Field(default=0.0)
    flashes_thrown: int = Field(default=0)
    smokes_thrown: int = Field(default=0)

    # Economy
    equipment_value: int = Field(default=0)

    # Outcome
    round_won: bool = Field(default=False)
    mvp: bool = Field(default=False)

    # Computed
    round_rating: Optional[float] = Field(default=None)


class CalibrationSnapshot(SQLModel, table=True):
    """
    Tracks belief model calibration history (Fusion Plan Proposal 6).

    Stores calibrated parameters at each calibration epoch to enable
    observability, regression detection, and rollback.
    """

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    calibration_type: str = Field(index=True)  # "hp_priors", "weapon_lethality", "threat_decay"
    parameters_json: str = Field(default="{}")  # JSON-encoded parameter dict
    sample_count: int = Field(default=0)
    source: str = Field(default="auto")  # "auto", "manual", "pro_data"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleThresholdRecord(SQLModel, table=True):
    """Persisted role classification thresholds learned from pro data."""

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)

    stat_name: str = Field(index=True, unique=True)  # e.g., "awp_kill_ratio"
    value: float
    sample_count: int = Field(default=0)
    source: str = Field(default="unknown")  # "hltv", "demo_parser", "ml_model"
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
