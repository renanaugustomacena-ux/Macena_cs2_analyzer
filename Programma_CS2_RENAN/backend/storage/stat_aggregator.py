"""
Stat Card Aggregator

Handles the persistence of HLTV spider data into the Pro database models.
Ensures that raw crawled data is correctly mapped to the persistent schema.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlmodel import select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import ProPlayer, ProPlayerStatCard, ProTeam

logger = logging.getLogger("cs2analyzer.stat_aggregator")


class StatCardAggregator:
    """
    Persistence layer for "Player Cards".
    Converts Spider output -> Database records.
    """

    def __init__(self):
        self.db = get_db_manager()

    def persist_player_card(self, spider_data: Dict[str, Any]):
        """
        Main entry point to save a complete player profile.
        """
        hltv_id = spider_data.get("player_id")
        nickname = spider_data.get("nickname")

        if not hltv_id or not nickname:
            logger.error("Cannot persist card: Missing player_id or nickname.")
            return

        with self.db.get_session() as session:
            # 1. Ensure Player exists
            player = session.exec(select(ProPlayer).where(ProPlayer.hltv_id == hltv_id)).first()
            if not player:
                player = ProPlayer(hltv_id=hltv_id, nickname=nickname)
                session.add(player)

            player.last_updated = datetime.now(timezone.utc)

            # 2. Update/Create Stat Card
            # We store one card per player per 'all_time' by default
            card = session.exec(
                select(ProPlayerStatCard).where(
                    ProPlayerStatCard.player_id == hltv_id,
                    ProPlayerStatCard.time_span == "all_time",
                )
            ).first()

            core = spider_data.get("core", {})

            if not card:
                card = ProPlayerStatCard(player_id=hltv_id, time_span="all_time")
                session.add(card)

            # Map core columns
            card.rating_2_0 = core.get("rating_2_0", 0.0)
            card.dpr = core.get("dpr", 0.0)
            card.kast = core.get("kast", 0.0)
            card.impact = core.get("impact", 0.0)
            card.adr = core.get("adr", 0.0)
            card.kpr = core.get("kpr", 0.0)

            # Store full blob in JSON for the Bridge to use later
            card.detailed_stats_json = json.dumps(spider_data)
            card.last_updated = datetime.now(timezone.utc)

            session.commit()
            logger.info("Persisted Player Card for %s [%s]", nickname, hltv_id)

    def persist_team(self, team_data: Dict[str, Any]):
        """
        Saves team-level information discovered during discovery cycles.
        """
        hltv_id = team_data.get("hltv_id")
        name = team_data.get("name")

        if not hltv_id or not name:
            logger.warning("persist_team called with missing hltv_id or name: %s", team_data)
            return

        with self.db.get_session() as session:
            team = session.exec(select(ProTeam).where(ProTeam.hltv_id == hltv_id)).first()
            if not team:
                team = ProTeam(hltv_id=hltv_id, name=name)
                session.add(team)

            team.world_rank = team_data.get("world_rank")
            team.last_updated = datetime.now(timezone.utc)
            session.commit()
