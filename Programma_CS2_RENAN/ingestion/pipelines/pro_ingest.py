import shutil
from pathlib import Path

from Programma_CS2_RENAN.backend.data_sources.demo_parser import parse_demo
from Programma_CS2_RENAN.backend.processing.feature_engineering.base_features import (
    extract_match_stats,
)
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.pro_ingest")


# F6-19: This pipeline stores basic PlayerMatchStats only. RoundStats, events, and
# tick-level data are not extracted here. Full enrichment requires calling
# enrich_from_demo() and _extract_and_store_events() from run_ingestion.py.
def ingest_pro_demos(source_dir: Path, processed_dir: Path):
    db_manager = get_db_manager()
    demo_files = list(source_dir.glob("*.dem"))
    for demo_path in demo_files:
        _process_single_pro_demo(demo_path, db_manager, processed_dir)


def _process_single_pro_demo(demo_path, db_manager, processed_dir):
    try:
        logger.info("Ingesting pro demo: %s", demo_path.name)
        rounds_df = parse_demo(str(demo_path))
        _map_and_archive_pro(demo_path, rounds_df, db_manager, processed_dir)
    except Exception as e:
        logger.error("Failed to ingest pro demo %s: %s", demo_path.name, e)


def _map_and_archive_pro(demo_path, rounds_df, db_manager, processed_dir):
    match_stats_dict = extract_match_stats(rounds_df)
    if not match_stats_dict:
        return
    # Derive player identity from demo filename (e.g. "s1mple_navi_vs_faze_mirage.dem")
    # Falls back to stem of filename to avoid merging all pro stats into one record.
    player_name = demo_path.stem.split("_")[0] if "_" in demo_path.stem else demo_path.stem
    match_stats = PlayerMatchStats(
        player_name=player_name, demo_name=demo_path.name, is_pro=True, **match_stats_dict
    )
    db_manager.upsert(match_stats)
    processed_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(demo_path), processed_dir / demo_path.name)
