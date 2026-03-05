"""
HLTV Statistics Sync Entry Point

Fetches PRO PLAYER STATISTICS from HLTV.org (Rating, K/D, ADR, etc.).
Saves to ProPlayer + ProPlayerStatCard in hltv_metadata.db.

This is NOT related to demo downloads — only statistics scraping.
"""

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.hltv")


def run_hltv_sync_cycle(limit=50):
    """
    Run HLTV statistics sync cycle using HLTVStatFetcher.

    Fetches pro player statistics (Rating 2.0, K/D, ADR, KAST, etc.) from HLTV.org
    and saves to ProPlayerStatCard in hltv_metadata.db.

    Args:
        limit: Maximum number of players to sync (default: 50)

    Returns:
        Number of players synced
    """
    try:
        from Programma_CS2_RENAN.backend.data_sources.hltv.stat_fetcher import HLTVStatFetcher

        logger.info("Starting HLTV Statistics Sync (limit=%s)", limit)
        fetcher = HLTVStatFetcher()

        # Discover top players
        player_urls = fetcher.fetch_top_players()
        if not player_urls:
            logger.warning("No players discovered from HLTV")
            return 0

        # Sync each player (up to limit)
        synced = 0
        for url in player_urls[:limit]:
            if fetcher.fetch_and_save_player(url):
                synced += 1

        logger.info("HLTV Statistics Sync completed: %s players synced", synced)
        return synced

    except ImportError as e:
        logger.error("Failed to import HLTVStatFetcher: %s", e)
        logger.error(
            "Ensure beautifulsoup4 is installed: pip install beautifulsoup4"
        )
        return 0
    except Exception as e:
        logger.error("HLTV Statistics Sync failed: %s", e)
        return 0
