import hashlib
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Programma_CS2_RENAN.backend.coaching.correction_engine import generate_corrections
from Programma_CS2_RENAN.backend.data_sources.demo_parser import parse_demo, parse_sequential_ticks
from Programma_CS2_RENAN.backend.ingestion.resource_manager import ResourceManager
from Programma_CS2_RENAN.backend.nn.model import (
    RAPCoachModel,
    RAPCommunication,
    TeacherRefinementNN,
)
from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
    calculate_deviations,
    get_pro_baseline,
)
from Programma_CS2_RENAN.backend.processing.state_reconstructor import RAPStateReconstructor
from Programma_CS2_RENAN.backend.progress.longitudinal import FeatureTrend
from Programma_CS2_RENAN.backend.progress.trend_analysis import compute_trend
from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database
from Programma_CS2_RENAN.backend.storage.db_models import (
    CoachingInsight,
    PlayerMatchStats,
    PlayerTickState,
)
from Programma_CS2_RENAN.backend.storage.match_data_manager import (
    MatchEventState,
    MatchMetadata,
    get_match_data_manager,
)
from Programma_CS2_RENAN.backend.storage.state_manager import (  # NEW: For progress tracking
    get_state_manager,
)
from Programma_CS2_RENAN.backend.storage.storage_manager import StorageManager
from Programma_CS2_RENAN.core.config import MIN_DEMOS_FOR_COACHING, get_setting, refresh_settings
from Programma_CS2_RENAN.ingestion.steam_locator import sync_steam_demos
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.ingestion_runner")


def _check_duplicate_demo(db_manager, demo_name: str) -> bool:
    """Check if a demo has already been ingested.

    Args:
        db_manager: Database manager instance
        demo_name: Base name of the demo file (without extension)

    Returns:
        True if demo was already ingested, False otherwise
    """
    from sqlmodel import select

    # R3-04: Normalize to stem (strip .dem extension) for consistent matching
    normalized = Path(demo_name).stem if demo_name.endswith(".dem") else demo_name

    with db_manager.get_session() as session:
        stmt = select(PlayerMatchStats).where(PlayerMatchStats.demo_name == normalized)
        existing = session.exec(stmt).first()

        if existing:
            logger.warning(
                "Duplicate detected: Demo '%s' already ingested (found in PlayerMatchStats)",
                demo_name,
            )
            return True

    return False


def run_ml_pipeline(db_manager, player_name: str, current_demo_name: str, stats: dict):
    """Main ML Ingestion Pipeline."""
    if not _is_profile_ready(db_manager, player_name):
        return
    logger.info("Running ML pipeline for %s...", player_name)

    # 1. Resolve Skill & Curriculum (Phase 5)
    from Programma_CS2_RENAN.backend.processing.skill_assessment import SkillLatentModel
    from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

    # Wrap the stats dict into a model-like object for the skill calculator
    current_stats_obj = PlayerMatchStats(
        **stats, player_name=player_name, demo_name=current_demo_name
    )
    skill_vec = SkillLatentModel.calculate_skill_vector(current_stats_obj)
    curr_level = SkillLatentModel.get_curriculum_level(skill_vec)

    logger.info("Player Level Identified: %s/10 (Axes: %s)", curr_level, skill_vec)

    deviations = calculate_deviations(stats, get_pro_baseline())
    trends = _get_feature_trends(db_manager, player_name)

    # 2. Level-Conditioned RAP Inference
    rap_insights = _get_rap_inference(db_manager, player_name, skill_level=curr_level)

    _save_insights(
        db_manager,
        player_name,
        current_demo_name,
        deviations,
        trends,
        rap_insights,
        skill_level=curr_level,
    )


def _is_profile_ready(db_manager, player_name):
    from sqlmodel import func, select

    from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats, PlayerProfile

    with db_manager.get_session() as session:
        p = session.exec(
            select(PlayerProfile).where(PlayerProfile.player_name == player_name)
        ).first()
        if not p or not (p.steam_connected or p.faceit_connected):
            return False
        cnt = session.exec(
            select(func.count(PlayerMatchStats.id)).where(
                PlayerMatchStats.player_name == player_name, PlayerMatchStats.is_pro.is_(False)
            )
        ).one()
        return cnt >= MIN_DEMOS_FOR_COACHING


def _get_feature_trends(db_manager, player_name):
    from sqlmodel import select

    with db_manager.get_session() as session:
        stmt = (
            select(PlayerMatchStats)
            .where(PlayerMatchStats.player_name == player_name)
            .order_by(PlayerMatchStats.processed_at.desc())
            .limit(10)
        )
        history = session.exec(stmt).all()
    if len(history) < 3:
        return []
    trends = []
    for feat in ["avg_kills", "avg_adr", "avg_kast", "accuracy"]:
        values = [getattr(h, feat, 0) for h in reversed(history)]
        slope, vol, conf = compute_trend(values)
        trends.append(FeatureTrend(feature=feat, slope=slope, volatility=vol, confidence=conf))
    return trends


def _get_rap_inference(db_manager, player_name, skill_level: int = 5):
    try:
        return _execute_rap_logic(db_manager, player_name, skill_level)
    except Exception as e:
        logger.error("RAP Inference failed: %s", e)
        return []


def _execute_rap_logic(db_manager, player_name, skill_level: int = 5):
    from sqlmodel import select

    from Programma_CS2_RENAN.backend.nn.persistence import load_nn

    with db_manager.get_session() as session:
        stmt = select(PlayerTickState).where(PlayerTickState.player_name == player_name)
        ticks = session.exec(stmt).all()
    if not ticks:
        return []
    recon, model, comm = RAPStateReconstructor(), RAPCoachModel(), RAPCommunication()
    try:
        model = load_nn("latest_rap", model, user_id=player_name)
    except Exception:
        logger.warning("RAP model checkpoint incompatible for %s. Skipping RAP insights.", player_name)
        return []
    windows = recon.segment_match_into_windows(ticks)
    insights = []
    for window in windows[:5]:
        batch = recon.reconstruct_belief_tensors(window)
        out = model(batch["view"], batch["map"], batch["motion"], batch["metadata"])
        advice = comm.generate_advice(out["advice_probs"], confidence=0.85, skill_level=skill_level)
        if advice:
            insights.append(advice)
    return insights


def _save_insights(
    db_manager, p_name, demo_name, deviations, trends, rap_advices, skill_level: int = 5
):
    from sqlmodel import delete

    from Programma_CS2_RENAN.backend.coaching.longitudinal_engine import (
        generate_longitudinal_coaching,
    )

    nn_signals = {"stability_warning": any(t.volatility > 0.2 for t in trends)}
    long_i = generate_longitudinal_coaching(trends, nn_signals)
    corr = generate_corrections(deviations, 30)
    with db_manager.get_session() as session:
        session.exec(delete(CoachingInsight).where(CoachingInsight.demo_name == demo_name))
        _save_batch_insights(session, p_name, demo_name, rap_advices, corr, long_i, skill_level)
        session.commit()


def _save_batch_insights(session, p_name, demo_name, rap, corr, long_i, skill_level):
    from Programma_CS2_RENAN.backend.coaching.explainability import ExplanationGenerator
    from Programma_CS2_RENAN.backend.processing.skill_assessment import SkillAxes

    for r in rap:
        session.add(
            CoachingInsight(
                player_name=p_name,
                demo_name=demo_name,
                title="RAP Behavioral",
                severity="Medium",
                message=r,
                focus_area="Decision",
            )
        )

    # Map raw deviations to Grounded Narratives (Step 2 SAFETY)
    for c in corr:
        feat = c["feature"]
        # Map feature to category
        category = SkillAxes.DECISION
        if "hs" in feat or "accuracy" in feat:
            category = SkillAxes.MECHANICS
        elif "aggression" in feat or "deaths" in feat:
            category = SkillAxes.POSITIONING

        # Extract context from features (De-mocking Step 2)
        context = {
            "weapon": (
                feat.replace("avg_", "").split("_")[0]
                if "accuracy" in feat or "hs" in feat
                else "equipment"
            ),
            "location": "critical sectors" if category == SkillAxes.POSITIONING else "the site",
        }

        message = ExplanationGenerator.generate_narrative(
            category=category,
            feature=feat,
            delta=c["weighted_z"],
            context=context,
            skill_level=skill_level,
        )

        if message:  # Silence is a Valid Action
            session.add(
                CoachingInsight(
                    player_name=p_name,
                    demo_name=demo_name,
                    title=f"{feat.replace('avg_', '').replace('_', ' ').title()} Insight",
                    severity=ExplanationGenerator.classify_insight_severity(c["weighted_z"]),
                    message=message,
                    focus_area=category,
                )
            )

    for li in long_i:
        session.add(CoachingInsight(player_name=p_name, demo_name=demo_name, **li))


def process_new_demos(is_pro=False, high_priority=False, limit=0):
    """
    Scans for new demos manually placed in the ingest folders.
    Args:
        limit: Max number of demos to process in this cycle (0 = unlimited).
    """
    # CRITICAL: Reload settings from disk to catch dynamic folder changes from UI
    refresh_settings()

    storage = StorageManager()
    target_dir = storage.get_ingest_dir(is_pro)

    if not target_dir.exists():
        logger.error(
            "Ingest directory not found: %s. Please create it and place .dem files there.",
            target_dir,
        )
        return

    # Update process priority
    if high_priority:
        ResourceManager.set_high_priority()
    else:
        ResourceManager.set_low_priority()

    db_manager = get_db_manager()
    demo_files = storage.list_new_demos(is_pro)

    if not demo_files:
        # Change to debug to avoid spamming the log and causing Windows rotation locking errors
        logger.debug("No new %s demos found in %s", "Pro" if is_pro else "User", target_dir)
        return

    logger.info(
        "Found %s new %s demos. Starting ingestion...", len(demo_files), "Pro" if is_pro else "User"
    )

    with db_manager.get_session() as session:
        _queue_files(session, demo_files, is_pro)
        session.commit()

    # 3. Process the queue
    # HP Mode: unlimited limit when priority is high
    effective_limit = 0 if high_priority else limit
    process_queued_tasks(db_manager, storage, is_pro, high_priority, limit=effective_limit)


def process_queued_tasks(db_manager, storage, is_pro, high_priority, limit=0):
    """Orchestrates the ingestion of queued tasks with throttling."""
    from sqlmodel import select

    from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask

    with db_manager.get_session() as session:
        tasks = session.exec(
            select(IngestionTask)
            .where(IngestionTask.status == "queued", IngestionTask.is_pro == is_pro)
            .order_by(IngestionTask.id)
        ).all()

    if not tasks:
        return 0

    processed_count = 0
    total_tasks = len(tasks)
    for task in tasks:
        # F6-13: Objects fetched in one session; do not access lazy-loaded attrs after
        # session closes. Re-attach via session.add(task) before modifying, or
        # re-fetch in the new session if lazy-loaded attributes are needed.
        with db_manager.get_session() as session:
            session.add(task)
            task.status = "processing"
            task.updated_at = datetime.now(timezone.utc)
            session.commit()

        # Update progress in CoachState
        with db_manager.get_session("knowledge") as session_k:
            from Programma_CS2_RENAN.backend.storage.db_models import CoachState

            state = session_k.exec(select(CoachState)).first()
            if state:
                state.parsing_progress = (processed_count / total_tasks) * 100
                session_k.add(state)
                session_k.commit()

        # Check for duplicate before processing
        demo_path = Path(task.demo_path)
        demo_basename = demo_path.stem  # Filename without extension

        if _check_duplicate_demo(db_manager, demo_basename):
            logger.info("Skipping duplicate demo: %s", demo_basename)
            with db_manager.get_session() as session:
                session.add(task)
                task.status = "completed"  # Mark as completed to remove from queue
                task.error_message = "Duplicate - already ingested"
                task.updated_at = datetime.now(timezone.utc)
                session.commit()
            processed_count += 1
            continue  # Skip to next demo

        success, msg = _ingest_single_demo(db_manager, storage, demo_path, is_pro)

        with db_manager.get_session() as session:
            session.add(task)
            task.status = "completed" if success else "failed"
            task.error_message = msg
            task.updated_at = datetime.now(timezone.utc)
            session.commit()

        processed_count += 1

    # Reset progress when batch is done
    if processed_count == total_tasks:
        from Programma_CS2_RENAN.backend.storage.state_manager import get_state_manager

        get_state_manager().update_status("digester", "Idle", f"Processed {total_tasks} demos")


def _queue_files(session, files, is_pro):
    from sqlmodel import select

    from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask

    for p in files:
        p_str = str(p)
        exist = session.exec(select(IngestionTask).where(IngestionTask.demo_path == p_str)).first()
        if not exist:
            session.add(IngestionTask(demo_path=p_str, is_pro=is_pro))


def _ingest_single_demo(db_manager, storage, demo_path, is_pro):
    from sqlmodel import select

    from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask
    from Programma_CS2_RENAN.core.config import get_setting

    demo_path_str = str(demo_path)
    with db_manager.get_session() as session:
        task = session.exec(
            select(IngestionTask).where(IngestionTask.demo_path == demo_path_str)
        ).first()
        start_tick = task.last_tick_processed if task else 0
        task_exists = task is not None

    target = "ALL" if is_pro else get_setting("CS2_PLAYER_NAME")

    # 1. Parse aggregate stats (only if starting from 0)
    if start_tick == 0:
        df = parse_demo(str(demo_path), target_player=target)
        if df.empty:
            logger.warning(
                "parse_demo returned empty DataFrame for %s (target=%s)",
                demo_path.name,
                target,
            )
            return False, f"Empty data for '{target}'"
        for _, row in df.iterrows():
            _save_player_stats(db_manager, row, demo_path.name, is_pro)

    # 2. Parse sequential data (incremental)
    last_processed = _save_sequential_data(db_manager, demo_path, target, start_tick=start_tick)

    # Update task progress — re-fetch inside new session to avoid DetachedInstanceError
    if task_exists:
        with db_manager.get_session() as session:
            fresh_task = session.exec(
                select(IngestionTask).where(IngestionTask.demo_path == demo_path_str)
            ).first()
            if fresh_task:
                fresh_task.last_tick_processed = last_processed

    if last_processed > start_tick:
        storage.archive_demo(demo_path, is_pro)
        return True, "Success"
    else:
        return True, "No new ticks"


def _save_player_stats(db_manager, row, demo_name, is_pro):
    from Programma_CS2_RENAN.core.config import get_setting

    p_name = row["player_name"]
    stats_dict = row.to_dict()
    stats_dict.pop("player_name", None)

    # R3-H09: Sanitize NaN/Inf in aggregate stats before DB insertion
    import math
    for key, val in list(stats_dict.items()):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            logger.warning("Sanitized NaN/Inf in '%s' for player '%s'", key, p_name)
            stats_dict[key] = 0.0

    # Clamp rating to DB constraint range [0, 5.0] — HLTV 2.0 can produce
    # negative values for partial demos or extreme underperformance
    if "rating" in stats_dict:
        raw_rating = stats_dict["rating"]
        stats_dict["rating"] = max(0.0, min(5.0, float(raw_rating)))
        if raw_rating != stats_dict["rating"]:
            logger.info("Clamped rating %.3f → %.3f for '%s'", raw_rating, stats_dict["rating"], p_name)

    # Clamp avg_kills and avg_adr to >= 0 (DB CHECK constraints)
    for field in ("avg_kills", "avg_adr"):
        if field in stats_dict and stats_dict[field] < 0:
            stats_dict[field] = 0.0

    # Use clean stem to align with PlayerTickState and enable AI Coach linking
    clean_demo_name = Path(demo_name).stem if str(demo_name).endswith(".dem") else demo_name

    match_stats = PlayerMatchStats(
        player_name=p_name, demo_name=clean_demo_name, is_pro=is_pro, **stats_dict
    )
    db_manager.upsert(match_stats)
    current_name = get_setting("CS2_PLAYER_NAME")
    if not is_pro and str(p_name).lower() == str(current_name).lower():
        run_ml_pipeline(db_manager, p_name, clean_demo_name, stats_dict)


def _sanitize_value(value, default, value_type=float):
    """Sanitization bridge: Cleans NaN/None/invalid values before DB insertion."""
    import math

    if value is None:
        return default
    if value_type == float and (math.isnan(value) or math.isinf(value)):
        logger.debug("Sanitized NaN/Inf value to default=%s", default)
        return default
    if value_type == str and (not value or str(value).lower() == "nan"):
        return default
    return value_type(value)


def _interpolate_position(df_ticks):
    """
    Intelligent position interpolation:
    For missing positions, interpolate between last known and next known positions.
    Uses CIRCULAR interpolation for angles (yaw/pitch) to handle wrap-around correctly.
    """
    import numpy as np
    import pandas as pd

    # Convert to numeric, coercing errors to NaN
    for col in ["X", "Y", "Z", "yaw", "pitch", "health", "armor", "equipment_value"]:
        if col in df_ticks.columns:
            df_ticks[col] = pd.to_numeric(df_ticks[col], errors="coerce")

    # Linear interpolation for position (X, Y, Z)
    for col in ["X", "Y", "Z"]:
        if col in df_ticks.columns:
            df_ticks[col] = df_ticks[col].interpolate(method="linear", limit_direction="both")
            df_ticks[col] = df_ticks[col].ffill().bfill()
            df_ticks[col] = df_ticks[col].fillna(0.0)

    # R4-14-01: Count rows where all position axes fell back to (0,0,0)
    if all(c in df_ticks.columns for c in ("X", "Y", "Z")):
        _zero_pos = ((df_ticks["X"] == 0.0) & (df_ticks["Y"] == 0.0) & (df_ticks["Z"] == 0.0)).sum()
        if _zero_pos > 0:
            from Programma_CS2_RENAN.observability.logger_setup import get_logger as _gl
            _gl("cs2analyzer.ingestion").warning(
                "R4-14-01: %d/%d ticks have (0,0,0) position after interpolation (%.1f%%)",
                _zero_pos, len(df_ticks), 100.0 * _zero_pos / max(len(df_ticks), 1),
            )

    # CIRCULAR interpolation for angles (yaw wraps at 360, pitch wraps at 180)
    for col, wrap_range in [("yaw", 360.0), ("pitch", 180.0)]:
        if col not in df_ticks.columns:
            continue

        # Convert angles to unit circle coordinates (sin/cos)
        angles_rad = np.deg2rad(df_ticks[col].values)
        sin_vals = pd.Series(np.sin(angles_rad))
        cos_vals = pd.Series(np.cos(angles_rad))

        # Interpolate sin and cos separately (they are continuous)
        sin_interp = (
            sin_vals.interpolate(method="linear", limit_direction="both")
            .ffill()
            .bfill()
            .fillna(0.0)
        )
        cos_interp = (
            cos_vals.interpolate(method="linear", limit_direction="both")
            .ffill()
            .bfill()
            .fillna(1.0)
        )

        # Convert back to angles using arctan2
        angles_interp = np.rad2deg(np.arctan2(sin_interp.values, cos_interp.values))

        # Normalize to positive range if needed (yaw: 0-360, pitch: -90 to 90)
        if col == "yaw":
            angles_interp = np.mod(angles_interp, 360.0)
        # pitch remains in (-90, 90) which is correct for arctan2 output

        df_ticks[col] = angles_interp

    # Forward fill for integer fields (health, armor, equipment, WP6 fields)
    for col in [
        "health",
        "armor",
        "equipment_value",
        "balance",
        "total_cash_spent",
        "kills_total",
        "deaths_total",
        "assists_total",
        "score",
        "mvps",
    ]:
        if col in df_ticks.columns:
            df_ticks[col] = df_ticks[col].ffill().bfill()
            if col == "health":
                df_ticks[col] = df_ticks[col].fillna(100.0)
            else:
                df_ticks[col] = df_ticks[col].fillna(0.0)

    return df_ticks


def _extract_and_store_events(demo_path, match_id, match_manager, df_ticks):
    """Extract game events from demo and persist as MatchEventState records.

    Parses weapon_fire, player_hurt, player_death, grenade/smoke/molotov/flash
    events and stores them in the per-match database for Player-POV perception.

    Player state (health, armor, equipment) is cross-referenced from df_ticks
    at the event tick to capture the situational context.
    """
    from demoparser2 import DemoParser

    try:
        parser = DemoParser(str(demo_path))
    except Exception as e:
        logger.error("Failed to create DemoParser for event extraction: %s", e)
        return 0

    # F6-14: Bounded state_lookup to prevent OOM on large match files (>50k tick rows).
    _STATE_LOOKUP_CAP = 50_000
    # Build a lookup: (tick, player_name_lower) -> {health, armor, equipment_value, team}
    # for cross-referencing player state at event time
    state_lookup = {}
    if not df_ticks.empty and "player_name" in df_ticks.columns:
        for _, row in df_ticks.iterrows():
            if len(state_lookup) >= _STATE_LOOKUP_CAP:
                logger.warning(
                    "state_lookup hit cap (%s); older entries evicted to prevent OOM",
                    _STATE_LOOKUP_CAP,
                )
                keys = list(state_lookup.keys())
                for k in keys[: len(keys) // 2]:
                    del state_lookup[k]
            key = (int(row["tick"]), str(row["player_name"]).strip().lower())
            state_lookup[key] = {
                "health": int(row.get("health", 100)),
                "armor": int(row.get("armor", 0)),
                "equipment_value": int(row.get("equipment_value", 0)),
                "team": str(row.get("team_name", "")),
            }

    # Build steamid -> player_name mapping from tick data
    sid_to_name = {}
    if not df_ticks.empty and "player_steamid" in df_ticks.columns:
        for _, row in df_ticks.iterrows():
            sid = int(row.get("player_steamid", 0))
            if sid:
                sid_to_name[sid] = str(row["player_name"]).strip()

    def _lookup_state(tick, player_name):
        """Get player state at a tick, with nearest-tick fallback."""
        key = (tick, player_name.strip().lower())
        if key in state_lookup:
            return state_lookup[key]
        # Fallback: search within ±5 ticks
        for offset in range(1, 6):
            for t in (tick - offset, tick + offset):
                fallback_key = (t, player_name.strip().lower())
                if fallback_key in state_lookup:
                    return state_lookup[fallback_key]
        return {"health": 100, "armor": 0, "equipment_value": 0, "team": ""}

    def _resolve_name(row, name_cols):
        """Resolve player name from event row trying multiple column names."""
        for col in name_cols:
            val = getattr(row, col, None)
            if val and str(val).strip() and str(val).lower() != "nan":
                return str(val).strip()
        # Fallback: try steamid mapping
        sid = getattr(row, "user_steamid", None) or getattr(row, "attacker_steamid", None)
        if sid:
            return sid_to_name.get(int(sid), "")
        return ""

    def _get_round(row):
        """Extract round number from event row."""
        return int(getattr(row, "total_rounds_played", 1) or 1)

    events = []

    # --- 1. weapon_fire events ---
    try:
        res = parser.parse_events(["weapon_fire"])
        if res:
            wf_df = res[0][1] if isinstance(res[0], tuple) else pd.DataFrame(res)
            if not wf_df.empty:
                for row in wf_df.itertuples():
                    tick = int(row.tick)
                    name = _resolve_name(row, ["player_name", "user_name", "name"])
                    if not name:
                        continue
                    state = _lookup_state(tick, name)
                    events.append(
                        MatchEventState(
                            tick=tick,
                            round_number=_get_round(row),
                            event_type="weapon_fire",
                            player_name=name,
                            player_team=state["team"],
                            player_health=state["health"],
                            player_armor=state["armor"],
                            player_equipment_value=state["equipment_value"],
                            pos_x=float(getattr(row, "x", 0) or 0),
                            pos_y=float(getattr(row, "y", 0) or 0),
                            pos_z=float(getattr(row, "z", 0) or 0),
                            weapon=str(getattr(row, "weapon", "") or ""),
                        )
                    )
    except Exception as e:
        logger.warning("Event extraction failed for weapon_fire: %s", e)

    # --- 2. player_hurt events ---
    try:
        res = parser.parse_events(["player_hurt"])
        if res:
            ph_df = res[0][1] if isinstance(res[0], tuple) else pd.DataFrame(res)
            if not ph_df.empty:
                for row in ph_df.itertuples():
                    tick = int(row.tick)
                    attacker = _resolve_name(row, ["attacker_name", "user_name"])
                    victim = _resolve_name(row, ["user_name", "player_name"])
                    if not attacker and not victim:
                        continue
                    att_state = _lookup_state(tick, attacker) if attacker else {}
                    vic_state = _lookup_state(tick, victim) if victim else {}
                    dmg = int(getattr(row, "dmg_health", 0) or getattr(row, "damage", 0) or 0)
                    events.append(
                        MatchEventState(
                            tick=tick,
                            round_number=_get_round(row),
                            event_type="player_hurt",
                            player_name=attacker,
                            player_team=att_state.get("team", ""),
                            player_health=att_state.get("health", 100),
                            player_armor=att_state.get("armor", 0),
                            player_equipment_value=att_state.get("equipment_value", 0),
                            pos_x=float(getattr(row, "x", 0) or 0),
                            pos_y=float(getattr(row, "y", 0) or 0),
                            pos_z=float(getattr(row, "z", 0) or 0),
                            weapon=str(getattr(row, "weapon", "") or ""),
                            damage=dmg,
                            victim_name=victim,
                            victim_team=vic_state.get("team", ""),
                            victim_health=vic_state.get("health", 100),
                            victim_armor=vic_state.get("armor", 0),
                        )
                    )
    except Exception as e:
        logger.warning("Event extraction failed for player_hurt: %s", e)

    # --- 3. player_death events ---
    try:
        res = parser.parse_events(["player_death"])
        if res:
            pd_df = res[0][1] if isinstance(res[0], tuple) else pd.DataFrame(res)
            if not pd_df.empty:
                for row in pd_df.itertuples():
                    tick = int(row.tick)
                    attacker = _resolve_name(row, ["attacker_name", "user_name"])
                    victim = _resolve_name(row, ["user_name", "player_name"])
                    att_state = _lookup_state(tick, attacker) if attacker else {}
                    vic_state = _lookup_state(tick, victim) if victim else {}
                    events.append(
                        MatchEventState(
                            tick=tick,
                            round_number=_get_round(row),
                            event_type="player_death",
                            player_name=attacker,
                            player_team=att_state.get("team", ""),
                            player_health=att_state.get("health", 100),
                            player_armor=att_state.get("armor", 0),
                            player_equipment_value=att_state.get("equipment_value", 0),
                            pos_x=float(getattr(row, "x", 0) or 0),
                            pos_y=float(getattr(row, "y", 0) or 0),
                            pos_z=float(getattr(row, "z", 0) or 0),
                            weapon=str(getattr(row, "weapon", "") or ""),
                            is_headshot=bool(getattr(row, "headshot", False)),
                            victim_name=victim,
                            victim_team=vic_state.get("team", ""),
                            victim_health=vic_state.get("health", 0),
                            victim_armor=vic_state.get("armor", 0),
                        )
                    )
    except Exception as e:
        logger.warning("Event extraction failed for player_death: %s", e)

    # --- 4. Smoke grenades (start/end pairing) ---
    try:
        res = parser.parse_events(["smokegrenade_detonate", "smokegrenade_expired"])
        if res:
            for evt_name, evt_df in res:
                if evt_df.empty:
                    continue
                etype = "smoke_start" if "detonate" in evt_name else "smoke_end"
                for row in evt_df.itertuples():
                    tick = int(row.tick)
                    sid = int(getattr(row, "user_steamid", 0) or 0)
                    name = sid_to_name.get(sid, "")
                    state = _lookup_state(tick, name) if name else {}
                    events.append(
                        MatchEventState(
                            tick=tick,
                            round_number=_get_round(row),
                            event_type=etype,
                            player_name=name,
                            player_team=state.get("team", ""),
                            player_health=state.get("health", 100),
                            player_armor=state.get("armor", 0),
                            player_equipment_value=state.get("equipment_value", 0),
                            pos_x=float(getattr(row, "x", 0) or 0),
                            pos_y=float(getattr(row, "y", 0) or 0),
                            pos_z=float(getattr(row, "z", 0) or 0),
                            weapon="smokegrenade",
                            entity_id=int(getattr(row, "entityid", 0) or 0),
                        )
                    )
    except Exception as e:
        logger.warning("Event extraction failed for smoke events: %s", e)

    # --- 5. Molotov/incendiary (start/end pairing) ---
    try:
        res = parser.parse_events(["inferno_startburn", "inferno_expire"])
        if res:
            for evt_name, evt_df in res:
                if evt_df.empty:
                    continue
                etype = "molotov_start" if "startburn" in evt_name else "molotov_end"
                for row in evt_df.itertuples():
                    tick = int(row.tick)
                    sid = int(getattr(row, "user_steamid", 0) or 0)
                    name = sid_to_name.get(sid, "")
                    state = _lookup_state(tick, name) if name else {}
                    events.append(
                        MatchEventState(
                            tick=tick,
                            round_number=_get_round(row),
                            event_type=etype,
                            player_name=name,
                            player_team=state.get("team", ""),
                            player_health=state.get("health", 100),
                            player_armor=state.get("armor", 0),
                            player_equipment_value=state.get("equipment_value", 0),
                            pos_x=float(getattr(row, "x", 0) or 0),
                            pos_y=float(getattr(row, "y", 0) or 0),
                            pos_z=float(getattr(row, "z", 0) or 0),
                            weapon="molotov",
                            entity_id=int(getattr(row, "entityid", 0) or 0),
                        )
                    )
    except Exception as e:
        logger.warning("Event extraction failed for molotov events: %s", e)

    # --- 6. Flashbang detonation ---
    try:
        res = parser.parse_events(["flashbang_detonate"])
        if res:
            fb_df = res[0][1] if isinstance(res[0], tuple) else pd.DataFrame(res)
            if not fb_df.empty:
                for row in fb_df.itertuples():
                    tick = int(row.tick)
                    sid = int(getattr(row, "user_steamid", 0) or 0)
                    name = sid_to_name.get(sid, "")
                    state = _lookup_state(tick, name) if name else {}
                    events.append(
                        MatchEventState(
                            tick=tick,
                            round_number=_get_round(row),
                            event_type="flash_detonate",
                            player_name=name,
                            player_team=state.get("team", ""),
                            player_health=state.get("health", 100),
                            player_armor=state.get("armor", 0),
                            player_equipment_value=state.get("equipment_value", 0),
                            pos_x=float(getattr(row, "x", 0) or 0),
                            pos_y=float(getattr(row, "y", 0) or 0),
                            pos_z=float(getattr(row, "z", 0) or 0),
                            weapon="flashbang",
                            entity_id=int(getattr(row, "entityid", 0) or 0),
                        )
                    )
    except Exception as e:
        logger.warning("Event extraction failed for flashbang events: %s", e)

    # --- 7. HE grenade detonation ---
    try:
        res = parser.parse_events(["hegrenade_detonate"])
        if res:
            he_df = res[0][1] if isinstance(res[0], tuple) else pd.DataFrame(res)
            if not he_df.empty:
                for row in he_df.itertuples():
                    tick = int(row.tick)
                    sid = int(getattr(row, "user_steamid", 0) or 0)
                    name = sid_to_name.get(sid, "")
                    state = _lookup_state(tick, name) if name else {}
                    events.append(
                        MatchEventState(
                            tick=tick,
                            round_number=_get_round(row),
                            event_type="he_detonate",
                            player_name=name,
                            player_team=state.get("team", ""),
                            player_health=state.get("health", 100),
                            player_armor=state.get("armor", 0),
                            player_equipment_value=state.get("equipment_value", 0),
                            pos_x=float(getattr(row, "x", 0) or 0),
                            pos_y=float(getattr(row, "y", 0) or 0),
                            pos_z=float(getattr(row, "z", 0) or 0),
                            weapon="hegrenade",
                            entity_id=int(getattr(row, "entityid", 0) or 0),
                        )
                    )
    except Exception as e:
        logger.warning("Event extraction failed for HE grenade events: %s", e)

    # --- 8. Bomb events ---
    try:
        for bomb_event in ["bomb_planted", "bomb_defused"]:
            res = parser.parse_events([bomb_event])
            if res:
                b_df = res[0][1] if isinstance(res[0], tuple) else pd.DataFrame(res)
                if not b_df.empty:
                    etype = "bomb_planted" if "planted" in bomb_event else "bomb_defused"
                    for row in b_df.itertuples():
                        tick = int(row.tick)
                        name = _resolve_name(row, ["user_name", "player_name"])
                        state = _lookup_state(tick, name) if name else {}
                        events.append(
                            MatchEventState(
                                tick=tick,
                                round_number=_get_round(row),
                                event_type=etype,
                                player_name=name,
                                player_team=state.get("team", ""),
                                player_health=state.get("health", 100),
                                player_armor=state.get("armor", 0),
                                player_equipment_value=state.get("equipment_value", 0),
                                pos_x=float(getattr(row, "x", 0) or 0),
                                pos_y=float(getattr(row, "y", 0) or 0),
                                pos_z=float(getattr(row, "z", 0) or 0),
                            )
                        )
    except Exception as e:
        logger.warning("Event extraction failed for bomb events: %s", e)

    # Store all events in batch
    if events:
        stored = match_manager.store_event_batch(match_id, events)
        logger.info("Stored %d game events to match database (ID: %s)", stored, match_id)
    else:
        logger.debug("No game events extracted for match %s", match_id)

    return len(events)


def _save_sequential_data(db_manager, demo_path, target_player, start_tick=0):
    import time as _time

    from demoparser2 import DemoParser as _DemoParser

    from Programma_CS2_RENAN.backend.data_sources.demo_parser import parse_sequential_ticks
    from Programma_CS2_RENAN.backend.processing.tick_enrichment import enrich_tick_data

    t_pipeline = _time.monotonic()

    # PROGRESS: 10% - Sending to Rust Parser
    get_state_manager().update_parsing_progress(10.0)

    # Parse ALL players — required for cross-player feature computation
    # (teammates_alive, enemies_alive, team_economy, enemies_visible).
    # demoparser2 parsing is O(file_size) regardless of player filter;
    # the filter only affects post-parse DataFrame slicing.
    df_ticks = parse_sequential_ticks(str(demo_path), "ALL", start_tick=start_tick)

    if df_ticks.empty:
        get_state_manager().update_parsing_progress(100.0)
        return start_tick

    # PROGRESS: 20% - Interpolation
    get_state_manager().update_parsing_progress(20.0)
    t_interp = _time.monotonic()

    # Apply intelligent interpolation to fill missing positions
    df_ticks = _interpolate_position(df_ticks)

    logger.info("Interpolation completed in %.2fs for %s rows", _time.monotonic() - t_interp, f"{len(df_ticks):,}")

    # PROGRESS: 25% - Tick Enrichment (cross-player features)
    get_state_manager().update_parsing_progress(25.0)
    t_enrich = _time.monotonic()

    # Resolve map_name from demo header (demoparser2 exposes it via parse_header())
    _meta_map_name = "de_unknown"
    try:
        _header = _DemoParser(str(demo_path)).parse_header()
        _meta_map_name = _header.get("map_name", "de_unknown")
        if not _meta_map_name or _meta_map_name == "unknown":
            _meta_map_name = "de_unknown"
        logger.info("Map name from demo header: %s", _meta_map_name)
    except Exception as e:
        logger.warning("Failed to extract map_name from demo header: %s", e)

    # Enrich with cross-player features: round_number, time_in_round,
    # bomb_planted, teammates_alive, enemies_alive, team_economy, enemies_visible
    df_ticks = enrich_tick_data(
        df_ticks,
        demo_path=str(demo_path),
        tick_rate=64.0,
        map_name=_meta_map_name,
    )

    logger.info("Enrichment completed in %.2fs", _time.monotonic() - t_enrich)

    # PROGRESS: 40% - Database Insertion Start
    get_state_manager().update_parsing_progress(40.0)
    t_db = _time.monotonic()

    demo_name = demo_path.stem
    # DA-03-01: SHA-256 with 63-bit modulo (~3 billion demos before 50%
    # birthday-paradox collision). SQLite INTEGER supports signed 64-bit.
    match_id = int(hashlib.sha256(demo_name.encode()).hexdigest(), 16) % (2**63 - 1)
    match_manager = get_match_data_manager()

    total_ticks = len(df_ticks)
    last_tick = int(df_ticks["tick"].max()) if total_ticks > 0 else start_tick

    _meta_player_count = (
        df_ticks["player_name"].nunique() if "player_name" in df_ticks.columns else 10
    )

    # ================================================================
    # BULK INSERT via pandas to_sql() — bypasses ORM object creation.
    # Previous per-row ORM loop took ~736s for 2.4M rows (96.6% of total).
    # Vectorized DataFrame operations + to_sql() reduce this to ~15-20s.
    # ================================================================

    import numpy as np

    BATCH_SIZE = 10000 if os.environ.get("HP_MODE") == "1" else 2000

    # --- Build MatchTickState DataFrame (vectorized column mapping) ---
    t_build = _time.monotonic()

    _int_defaults = {
        "round_number": 1, "player_steamid": 0, "armor": 0,
        "equipment_value": 0, "balance": 0, "enemies_visible": 0,
        "ping": 0, "kills_this_round": 0, "deaths_this_round": 0,
        "assists_this_round": 0, "headshot_kills_this_round": 0,
        "damage_this_round": 0, "utility_damage_this_round": 0,
        "enemies_flashed_this_round": 0, "kills_total": 0,
        "deaths_total": 0, "assists_total": 0, "headshot_kills_total": 0,
        "mvps": 0, "score": 0, "cash_spent_this_round": 0,
        "total_cash_spent": 0,
        "teammates_alive": 4, "enemies_alive": 5, "team_economy": 0,
    }
    _float_defaults = {"X": 0.0, "Y": 0.0, "Z": 0.0, "yaw": 0.0, "pitch": 0.0, "time_in_round": 0.0}
    _bool_defaults = {
        "is_crouching": False, "is_scoped": False, "is_blinded": False,
        "has_helmet": False, "has_defuser": False, "bomb_planted": False,
    }

    # Fill NaN/None with defaults (vectorized, ~100ms for 2.4M rows)
    for col, default in _int_defaults.items():
        if col in df_ticks.columns:
            original_na = df_ticks[col].isna().sum()
            numeric = pd.to_numeric(df_ticks[col], errors="coerce")
            coerced_count = numeric.isna().sum() - original_na
            if coerced_count > 0:
                logger.warning("Column '%s': %d non-numeric values coerced to default %s", col, coerced_count, default)
            df_ticks[col] = numeric.fillna(default).astype(int)
    for col, default in _float_defaults.items():
        if col in df_ticks.columns:
            original_na = df_ticks[col].isna().sum()
            numeric = pd.to_numeric(df_ticks[col], errors="coerce")
            coerced_count = numeric.isna().sum() - original_na
            if coerced_count > 0:
                logger.warning("Column '%s': %d non-numeric values coerced to default %s", col, coerced_count, default)
            df_ticks[col] = numeric.fillna(default).astype(float)
    for col, default in _bool_defaults.items():
        if col in df_ticks.columns:
            df_ticks[col] = df_ticks[col].fillna(default).astype(bool)

    # R3-02: Warn about critical columns missing from demoparser2 output
    _critical_cols = ["balance", "health", "X", "Y", "Z"]
    _missing_critical = [c for c in _critical_cols if c not in df_ticks.columns]
    if _missing_critical:
        logger.warning(
            "Critical columns absent from demo data (defaulted to 0): %s",
            _missing_critical,
        )

    # Fill missing health default (100, not 0)
    if "health" in df_ticks.columns:
        df_ticks["health"] = pd.to_numeric(df_ticks["health"], errors="coerce").fillna(100).astype(int)
    # Fill is_alive default (True)
    if "is_alive" in df_ticks.columns:
        df_ticks["is_alive"] = df_ticks["is_alive"].fillna(True).astype(bool)
    # Fill string defaults
    if "team_name" in df_ticks.columns:
        df_ticks["team_name"] = df_ticks["team_name"].fillna("CT").astype(str)
    if "active_weapon" in df_ticks.columns:
        df_ticks["active_weapon"] = df_ticks["active_weapon"].fillna("unknown").astype(str)
        df_ticks.loc[df_ticks["active_weapon"].str.lower() == "nan", "active_weapon"] = "unknown"
    if "player_name" in df_ticks.columns:
        df_ticks["player_name"] = df_ticks["player_name"].astype(str)
    if "map_name" in df_ticks.columns:
        df_ticks["map_name"] = df_ticks["map_name"].fillna(_meta_map_name).astype(str)
    else:
        df_ticks["map_name"] = _meta_map_name

    # Build MatchTickState DataFrame with renamed columns (ALL players)
    df_match = pd.DataFrame({
        "tick": df_ticks["tick"].astype(int),
        "round_number": df_ticks.get("round_number", pd.Series(1, index=df_ticks.index)).astype(int),
        "player_name": df_ticks["player_name"],
        "steamid": df_ticks.get("player_steamid", pd.Series(0, index=df_ticks.index)).astype(int),
        "team": df_ticks.get("team_name", pd.Series("CT", index=df_ticks.index)),
        "pos_x": df_ticks["X"].astype(float),
        "pos_y": df_ticks["Y"].astype(float),
        "pos_z": df_ticks["Z"].astype(float),
        "yaw": df_ticks["yaw"].astype(float),
        "health": df_ticks["health"].astype(int),
        "armor": df_ticks.get("armor", pd.Series(0, index=df_ticks.index)).astype(int),
        "is_alive": df_ticks.get("is_alive", pd.Series(True, index=df_ticks.index)).astype(bool),
        "is_crouching": df_ticks.get("is_crouching", pd.Series(False, index=df_ticks.index)).astype(bool),
        "is_scoped": df_ticks.get("is_scoped", pd.Series(False, index=df_ticks.index)).astype(bool),
        "is_blinded": df_ticks.get("is_blinded", pd.Series(False, index=df_ticks.index)).astype(bool),
        "active_weapon": df_ticks.get("active_weapon", pd.Series("unknown", index=df_ticks.index)),
        "equipment_value": df_ticks.get("equipment_value", pd.Series(0, index=df_ticks.index)).astype(int),
        "money": df_ticks.get("balance", pd.Series(0, index=df_ticks.index)).astype(int),
        "enemies_visible": df_ticks.get("enemies_visible", pd.Series(0, index=df_ticks.index)).astype(int),
        "has_helmet": df_ticks.get("has_helmet", pd.Series(False, index=df_ticks.index)).astype(bool),
        "has_defuser": df_ticks.get("has_defuser", pd.Series(False, index=df_ticks.index)).astype(bool),
        "ping": df_ticks.get("ping", pd.Series(0, index=df_ticks.index)).astype(int),
        "kills_this_round": df_ticks.get("kills_this_round", pd.Series(0, index=df_ticks.index)).astype(int),
        "deaths_this_round": df_ticks.get("deaths_this_round", pd.Series(0, index=df_ticks.index)).astype(int),
        "assists_this_round": df_ticks.get("assists_this_round", pd.Series(0, index=df_ticks.index)).astype(int),
        "headshot_kills_this_round": df_ticks.get("headshot_kills_this_round", pd.Series(0, index=df_ticks.index)).astype(int),
        "damage_this_round": df_ticks.get("damage_this_round", pd.Series(0, index=df_ticks.index)).astype(int),
        "utility_damage_this_round": df_ticks.get("utility_damage_this_round", pd.Series(0, index=df_ticks.index)).astype(int),
        "enemies_flashed_this_round": df_ticks.get("enemies_flashed_this_round", pd.Series(0, index=df_ticks.index)).astype(int),
        "kills_total": df_ticks.get("kills_total", pd.Series(0, index=df_ticks.index)).astype(int),
        "deaths_total": df_ticks.get("deaths_total", pd.Series(0, index=df_ticks.index)).astype(int),
        "assists_total": df_ticks.get("assists_total", pd.Series(0, index=df_ticks.index)).astype(int),
        "headshot_kills_total": df_ticks.get("headshot_kills_total", pd.Series(0, index=df_ticks.index)).astype(int),
        "mvps": df_ticks.get("mvps", pd.Series(0, index=df_ticks.index)).astype(int),
        "score": df_ticks.get("score", pd.Series(0, index=df_ticks.index)).astype(int),
        "cash_spent_this_round": df_ticks.get("cash_spent_this_round", pd.Series(0, index=df_ticks.index)).astype(int),
        "cash_spent_total": df_ticks.get("total_cash_spent", pd.Series(0, index=df_ticks.index)).astype(int),
        # --- Enriched features ---
        "pitch": df_ticks.get("pitch", pd.Series(0.0, index=df_ticks.index)).astype(float),
        "time_in_round": df_ticks.get("time_in_round", pd.Series(0.0, index=df_ticks.index)).astype(float),
        "bomb_planted": df_ticks.get("bomb_planted", pd.Series(False, index=df_ticks.index)).astype(bool),
        "teammates_alive": df_ticks.get("teammates_alive", pd.Series(4, index=df_ticks.index)).astype(int),
        "enemies_alive": df_ticks.get("enemies_alive", pd.Series(5, index=df_ticks.index)).astype(int),
        "team_economy": df_ticks.get("team_economy", pd.Series(0, index=df_ticks.index)).astype(int),
        "map_name": df_ticks["map_name"],
    })

    # Build legacy PlayerTickState DataFrame — filtered to target_player
    # for user demos, ALL players for pro demos
    df_legacy_source = df_ticks
    if target_player and target_player != "ALL":
        target_lower = str(target_player).strip().lower()
        df_legacy_source = df_ticks[
            df_ticks["player_name"].astype(str).str.strip().str.lower() == target_lower
        ]

    df_legacy = pd.DataFrame({
        "demo_name": demo_name,
        "tick": df_legacy_source["tick"].astype(int),
        "player_name": df_legacy_source["player_name"],
        "pos_x": df_legacy_source["X"].astype(float),
        "pos_y": df_legacy_source["Y"].astype(float),
        "pos_z": df_legacy_source["Z"].astype(float),
        "view_x": df_legacy_source["yaw"].astype(float),
        "view_y": df_legacy_source.get("pitch", pd.Series(0.0, index=df_legacy_source.index)).astype(float),
        "health": df_legacy_source["health"].astype(int),
        "armor": df_legacy_source.get("armor", pd.Series(0, index=df_legacy_source.index)).astype(int),
        "is_crouching": df_legacy_source.get("is_crouching", pd.Series(False, index=df_legacy_source.index)).astype(bool),
        "is_scoped": df_legacy_source.get("is_scoped", pd.Series(False, index=df_legacy_source.index)).astype(bool),
        "active_weapon": df_legacy_source.get("active_weapon", pd.Series("unknown", index=df_legacy_source.index)),
        "equipment_value": df_legacy_source.get("equipment_value", pd.Series(0, index=df_legacy_source.index)).astype(int),
        "enemies_visible": df_legacy_source.get("enemies_visible", pd.Series(0, index=df_legacy_source.index)).astype(int),
        "is_blinded": df_legacy_source.get("is_blinded", pd.Series(False, index=df_legacy_source.index)).astype(bool),
        # --- Enriched features ---
        "round_number": df_legacy_source.get("round_number", pd.Series(1, index=df_legacy_source.index)).astype(int),
        "time_in_round": df_legacy_source.get("time_in_round", pd.Series(0.0, index=df_legacy_source.index)).astype(float),
        "bomb_planted": df_legacy_source.get("bomb_planted", pd.Series(False, index=df_legacy_source.index)).astype(bool),
        "teammates_alive": df_legacy_source.get("teammates_alive", pd.Series(4, index=df_legacy_source.index)).astype(int),
        "enemies_alive": df_legacy_source.get("enemies_alive", pd.Series(5, index=df_legacy_source.index)).astype(int),
        "team_economy": df_legacy_source.get("team_economy", pd.Series(0, index=df_legacy_source.index)).astype(int),
        "map_name": df_legacy_source.get("map_name", pd.Series(_meta_map_name, index=df_legacy_source.index)),
        "created_at": datetime.now(timezone.utc),
    })

    logger.info("DataFrame construction: %.2fs", _time.monotonic() - t_build)

    # --- Write to databases in chunks with progress tracking ---
    match_engine = match_manager.get_engine(match_id)
    monolith_engine = db_manager.engine
    n_chunks = (total_ticks + BATCH_SIZE - 1) // BATCH_SIZE

    for chunk_idx in range(n_chunks):
        start = chunk_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total_ticks)

        # Update progress: map chunk_idx/n_chunks -> 40..95%
        pct = 40.0 + (chunk_idx / n_chunks) * 55.0
        get_state_manager().update_parsing_progress(pct)

        # Write chunk to per-match database
        df_match.iloc[start:end].to_sql(
            "matchtickstate", match_engine, if_exists="append", index=False,         )
        # Write chunk to legacy monolith
        df_legacy.iloc[start:end].to_sql(
            "playertickstate", monolith_engine, if_exists="append", index=False,         )

    db_elapsed = _time.monotonic() - t_db

    # Store match metadata
    meta = MatchMetadata(
        match_id=match_id,
        demo_name=demo_name,
        map_name=_meta_map_name,
        tick_count=int(last_tick - start_tick),
        player_count=_meta_player_count,
    )
    match_manager.store_metadata(match_id, meta)

    total_elapsed = _time.monotonic() - t_pipeline
    logger.info(
        "Ingestion complete for %s: %s ticks, %d chunks, "
        "DB insertion %.1fs, total pipeline %.1fs",
        demo_name, f"{total_ticks:,}", n_chunks,
        db_elapsed, total_elapsed,
    )

    # Extract and persist game events (Player-POV Perception System)
    # Only on fresh ingestion (start_tick == 0) to avoid duplicate events
    if start_tick == 0:
        _extract_and_store_events(demo_path, match_id, match_manager, df_ticks)

    return last_tick


if __name__ == "__main__":
    init_database()
    process_new_demos(is_pro=True)
    process_new_demos(is_pro=False)
