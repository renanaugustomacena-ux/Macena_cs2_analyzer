from Programma_CS2_RENAN.fetch_hltv_stats import HLTVStatFetcher
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.hltv_orchestrator")


class HLTVOrchestrator:
    """
    Coordination layer for HLTV scraping.
    Decides *when* and *who* to scrape, preventing spam.
    """

    def __init__(self):
        self.fetcher = HLTVStatFetcher()

    def run_sync_cycle(self, limit=10):
        """
        Main entry point for periodic sync.
        For V1, we focus on keeping the Top 50 player stats fresh.
        """
        logger.info("Orchestrator: Starting Sync Cycle")

        # 1. Discover targets (Top 50)
        # In a real heavy implementation, we'd also parse Match Results pages
        # but for Profile Analytics, the Top 50 + Specifics is enough.
        targets = self.fetcher.fetch_top_players()

        if not targets:
            logger.warning("Orchestrator: No targets found.")
            return

        # 2. Process targets
        # The fetcher inside the service loop might call fetch_top_players directly,
        # but the orchestrator pattern allows us to inject custom URLs later (e.g. from DB request).

        # We don't need to double-scrape here if the service loop calls the fetcher directly.
        # But `hltv_sync_service.py` calls `orchestrator.run_sync_cycle`.

        count = 0
        for url in targets:
            if count >= limit:
                break

            # Helper to actually fetch and save
            data = self.fetcher.fetch_player_stats(url)
            if data:
                self._save_to_db(data)
                count += 1

    def _save_to_db(self, data):
        import time

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

        db = get_db_manager()
        data = dict(data)  # Avoid mutating caller's dict
        p_name = data.pop("player_name")

        stat_record = PlayerMatchStats(
            player_name=p_name,
            demo_name=f"HLTV_ORCHESTRATOR_{int(time.time())}",
            is_pro=True,
            kill_std=0.0,
            adr_std=0.0,
            econ_rating=1.0,
            **data,
        )
        db.upsert(stat_record)
        logger.info("Orchestrator: Updated %s", p_name)
