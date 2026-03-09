import shutil
from pathlib import Path

from Programma_CS2_RENAN.backend.data_sources.demo_parser import parse_demo
from Programma_CS2_RENAN.backend.processing.feature_engineering.base_features import (
    extract_match_stats,
)
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats
from Programma_CS2_RENAN.core.config import get_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.user_ingest")


# F6-19: This pipeline stores basic PlayerMatchStats only. RoundStats, events, and
# tick-level data are not extracted here. Full enrichment requires calling
# enrich_from_demo() and _extract_and_store_events() from run_ingestion.py.
def ingest_user_demos(source_dir: Path, processed_dir: Path):
    db_manager = get_db_manager()
    demo_files = list(source_dir.glob("*.dem"))
    for demo_path in demo_files:
        _process_single_user_demo(demo_path, db_manager, processed_dir)


def _process_single_user_demo(demo_path, db_manager, processed_dir):
    try:
        logger.info("Ingesting user demo: %s", demo_path.name)
        rounds_df = parse_demo(str(demo_path))
        _map_and_pipeline_user(demo_path, rounds_df, db_manager, processed_dir)
    except Exception as e:
        logger.error("Failed to ingest user demo %s: %s", demo_path.name, e)


def _map_and_pipeline_user(demo_path, rounds_df, db_manager, processed_dir):
    match_stats_dict = extract_match_stats(rounds_df)
    if not match_stats_dict:
        return
    # R3-04: Use .stem (without .dem extension) for consistent demo_name normalization
    demo_name = demo_path.stem
    match_stats = PlayerMatchStats(
        player_name=get_setting("CS2_PLAYER_NAME", ""), demo_name=demo_name, is_pro=False, **match_stats_dict
    )
    db_manager.upsert(match_stats)
    _trigger_ml_pipeline(db_manager, demo_name, match_stats_dict)
    # R3-H03: Only archive after all pipeline steps succeed — if we get here, no exception was raised
    _archive_user_demo(demo_path, processed_dir)
    logger.info("Demo archived after successful pipeline: %s", demo_path.name)


def _trigger_ml_pipeline(db_manager, demo_name, stats):
    from Programma_CS2_RENAN.run_ingestion import run_ml_pipeline

    run_ml_pipeline(db_manager, get_setting("CS2_PLAYER_NAME", ""), demo_name, stats)


def _archive_user_demo(demo_path, processed_dir):
    processed_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(demo_path), processed_dir / demo_path.name)
