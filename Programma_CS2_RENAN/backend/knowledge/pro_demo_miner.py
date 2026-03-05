"""
Pro Player Knowledge Mining Pipeline

Extracts tactical knowledge from professional player statistics (ProPlayerStatCard).
Generates knowledge entries for the RAG coaching knowledge base based on real
HLTV-sourced player data.

Pipeline:
    1. Read pro player stat cards from hltv_metadata.db
    2. Identify standout performance patterns
    3. Generate knowledge entries (archetypes, baselines, traits)
    4. Add to RAG knowledge base
"""

from typing import Dict, List

from sqlmodel import select

from Programma_CS2_RENAN.backend.knowledge.rag_knowledge import KnowledgePopulator
from Programma_CS2_RENAN.backend.storage.database import get_hltv_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import ProPlayer, ProPlayerStatCard
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.pro_demo_miner")

# Archetype classification thresholds
_STAR_FRAGGER_IMPACT = 1.15
_SNIPER_HS_THRESHOLD = 0.35
_SUPPORT_KAST_THRESHOLD = 0.72
_ENTRY_OPENING_THRESHOLD = 0.52


class ProStatsMiner:
    """
    Extract tactical knowledge from professional player statistics.

    Uses real HLTV-sourced data in ProPlayerStatCard to generate
    coaching knowledge about pro playstyles, baselines, and archetypes.
    """

    def __init__(self):
        self.db = get_hltv_db_manager()
        self.populator = KnowledgePopulator()

    def mine_all_pro_stats(self, limit: int = 50) -> int:
        """
        Mine knowledge from all pro player stat cards.

        Args:
            limit: Maximum number of players to process

        Returns:
            Number of knowledge entries created
        """
        logger.info("Starting pro stats mining (limit=%s)", limit)

        with self.db.get_session() as session:
            stat_cards = session.exec(
                select(ProPlayerStatCard)
                .order_by(ProPlayerStatCard.last_updated.desc())
                .limit(limit)
            ).all()

            if not stat_cards:
                logger.warning("No pro stat cards found to mine")
                return 0

            total_knowledge = 0

            for card in stat_cards:
                player = session.exec(
                    select(ProPlayer).where(ProPlayer.hltv_id == card.player_id)
                ).first()
                nickname = player.nickname if player else f"Player_{card.player_id}"

                try:
                    entries = self._generate_player_knowledge(card, nickname)
                    for entry in entries:
                        try:
                            self.populator.add_knowledge(**entry)
                        except Exception as e:
                            logger.error("Failed to add knowledge for %s: %s", nickname, e)
                    total_knowledge += len(entries)
                    logger.info("Mined %s entries for %s", len(entries), nickname)
                except Exception as e:
                    logger.error("Failed to mine stats for %s: %s", nickname, e)

        logger.info("Total knowledge mined: %s entries", total_knowledge)
        return total_knowledge

    def _generate_player_knowledge(
        self, card: ProPlayerStatCard, nickname: str
    ) -> List[Dict]:
        """Generate knowledge entries from a player's stat card."""
        knowledge = []

        archetype = self._classify_archetype(card)

        # Baseline knowledge entry
        knowledge.append(
            {
                "title": f"Pro baseline: {nickname} ({archetype})",
                "description": (
                    f"{nickname} — Rating 2.0: {card.rating_2_0:.2f}, "
                    f"KPR: {card.kpr:.2f}, DPR: {card.dpr:.2f}, "
                    f"ADR: {card.adr:.1f}, KAST: {card.kast:.1f}%, "
                    f"HS: {card.headshot_pct:.1f}%, Impact: {card.impact:.2f}. "
                    f"Maps played: {card.maps_played}. "
                    f"Time span: {card.time_span}."
                ),
                "category": "pro_baseline",
                "situation": f"Pro player reference — {archetype}",
                "map_name": None,
                "pro_example": f"{nickname} (HLTV stats)",
            }
        )

        # Opening duels entry (if data available)
        if card.opening_kill_ratio > 0 or card.opening_duel_win_pct > 0:
            knowledge.append(
                {
                    "title": f"Opening duels: {nickname}",
                    "description": (
                        f"{nickname} opening kill ratio: {card.opening_kill_ratio:.2f}, "
                        f"opening duel win rate: {card.opening_duel_win_pct:.1f}%. "
                        f"{'Aggressive entry fragger.' if card.opening_duel_win_pct > 52 else 'Disciplined opener.'}"
                    ),
                    "category": "opening_duels",
                    "situation": "Entry fragging reference",
                    "map_name": None,
                    "pro_example": f"{nickname} (HLTV stats)",
                }
            )

        # Clutch/multikill entry (if data available)
        if card.clutch_win_count > 0 or card.multikill_round_pct > 0:
            knowledge.append(
                {
                    "title": f"Clutch & multikills: {nickname}",
                    "description": (
                        f"{nickname} clutch wins: {card.clutch_win_count}, "
                        f"multikill round %: {card.multikill_round_pct:.1f}%. "
                        f"{'High clutch performer.' if card.clutch_win_count > 50 else 'Standard clutch rate.'}"
                    ),
                    "category": "clutch_performance",
                    "situation": "Clutch situation reference",
                    "map_name": None,
                    "pro_example": f"{nickname} (HLTV stats)",
                }
            )

        return knowledge

    def _classify_archetype(self, card: ProPlayerStatCard) -> str:
        """Classify player archetype based on stat profile."""
        if card.impact >= _STAR_FRAGGER_IMPACT and card.rating_2_0 >= 1.10:
            return "Star Fragger"
        if card.headshot_pct < _SNIPER_HS_THRESHOLD and card.impact >= 1.05:
            return "AWP Specialist"
        if card.kast >= _SUPPORT_KAST_THRESHOLD and card.impact < 1.05:
            return "Support Anchor"
        if card.opening_duel_win_pct >= _ENTRY_OPENING_THRESHOLD:
            return "Entry Fragger"
        return "Versatile"


# Keep backward-compatible alias for init_knowledge_base.py
ProDemoMiner = ProStatsMiner


def auto_populate_from_pro_demos(limit: int = 50) -> int:
    """
    Convenience function for automated knowledge population.

    Args:
        limit: Maximum number of players to process

    Returns:
        Number of knowledge entries created
    """
    miner = ProStatsMiner()
    return miner.mine_all_pro_stats(limit=limit)


if __name__ == "__main__":
    logger.info("=== Pro Stats Mining Test ===\n")
    count = auto_populate_from_pro_demos(limit=10)
    logger.info("Mined %s knowledge entries from pro stats", count)
