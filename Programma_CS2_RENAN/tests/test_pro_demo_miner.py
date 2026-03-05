"""
Tests for pro stats mining pipeline.

Tests knowledge extraction from ProPlayerStatCard and database integration.
Non-destructive: only cleans up records created by each test.
"""

import pytest
from sqlmodel import select

from Programma_CS2_RENAN.backend.knowledge.pro_demo_miner import (
    ProStatsMiner,
    auto_populate_from_pro_demos,
)
from Programma_CS2_RENAN.backend.storage.database import get_db_manager, get_hltv_db_manager, init_database
from Programma_CS2_RENAN.backend.storage.db_models import (
    ProPlayer,
    ProPlayerStatCard,
    TacticalKnowledge,
)

_TEST_PREFIX = "/__test_pro_miner__/"


@pytest.mark.integration
class TestProStatsMiner:
    """Test suite for pro stats mining."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Initialize DB and track created records for cleanup."""
        init_database()
        self._created_player_ids = []
        self._created_card_ids = []
        self._created_knowledge_ids = []
        yield
        # Cleanup: TacticalKnowledge in monolith, ProPlayer/ProPlayerStatCard in hltv_metadata.db
        db = get_db_manager()
        with db.get_session() as session:
            for kid in self._created_knowledge_ids:
                k = session.get(TacticalKnowledge, kid)
                if k:
                    session.delete(k)
            session.commit()
        hltv_db = get_hltv_db_manager()
        with hltv_db.get_session() as session:
            for cid in self._created_card_ids:
                c = session.get(ProPlayerStatCard, cid)
                if c:
                    session.delete(c)
            for pid in self._created_player_ids:
                p = session.get(ProPlayer, pid)
                if p:
                    session.delete(p)
            session.commit()

    def _create_player_and_card(
        self,
        session,
        hltv_id,
        nickname,
        rating=1.10,
        kpr=0.75,
        dpr=0.65,
        adr=80.0,
        kast=70.0,
        impact=1.05,
        headshot_pct=50.0,
        maps_played=100,
    ):
        """Helper: create ProPlayer + ProPlayerStatCard and track for cleanup."""
        player = ProPlayer(
            hltv_id=hltv_id,
            nickname=f"{_TEST_PREFIX}{nickname}",
        )
        session.add(player)
        session.commit()
        session.refresh(player)
        self._created_player_ids.append(player.id)

        card = ProPlayerStatCard(
            player_id=hltv_id,
            rating_2_0=rating,
            kpr=kpr,
            dpr=dpr,
            adr=adr,
            kast=kast,
            impact=impact,
            headshot_pct=headshot_pct,
            maps_played=maps_played,
            time_span="all_time",
        )
        session.add(card)
        session.commit()
        session.refresh(card)
        self._created_card_ids.append(card.id)
        return player, card

    def _track_knowledge(self):
        """Record knowledge IDs created by test for cleanup."""
        db = get_db_manager()
        with db.get_session() as session:
            all_k = session.exec(
                select(TacticalKnowledge).where(
                    TacticalKnowledge.pro_example.contains(_TEST_PREFIX)
                )
            ).all()
            for k in all_k:
                if k.id not in self._created_knowledge_ids:
                    self._created_knowledge_ids.append(k.id)

    def test_miner_initialization(self):
        """Test miner can be initialized."""
        miner = ProStatsMiner()
        assert miner.db is not None
        assert miner.populator is not None

    def test_classify_archetype_star_fragger(self):
        """Test archetype classification for star fragger."""
        miner = ProStatsMiner()
        card = ProPlayerStatCard(
            player_id=99999,
            rating_2_0=1.25,
            impact=1.20,
            kast=72.0,
            headshot_pct=55.0,
            opening_duel_win_pct=50.0,
        )
        assert miner._classify_archetype(card) == "Star Fragger"

    def test_classify_archetype_support(self):
        """Test archetype classification for support anchor."""
        miner = ProStatsMiner()
        card = ProPlayerStatCard(
            player_id=99999,
            rating_2_0=1.00,
            impact=0.95,
            kast=75.0,
            headshot_pct=50.0,
            opening_duel_win_pct=45.0,
        )
        assert miner._classify_archetype(card) == "Support Anchor"

    def test_generate_player_knowledge(self):
        """Test knowledge generation from a stat card."""
        miner = ProStatsMiner()
        card = ProPlayerStatCard(
            player_id=99999,
            rating_2_0=1.15,
            kpr=0.80,
            dpr=0.62,
            adr=85.0,
            kast=72.0,
            impact=1.10,
            headshot_pct=52.0,
            maps_played=200,
            opening_kill_ratio=1.2,
            opening_duel_win_pct=54.0,
            clutch_win_count=65,
            multikill_round_pct=12.5,
            time_span="all_time",
        )

        entries = miner._generate_player_knowledge(card, f"{_TEST_PREFIX}TestPlayer")

        # Should generate: baseline + opening duels + clutch/multikill = 3 entries
        assert len(entries) == 3, f"Expected 3 knowledge entries, got {len(entries)}"
        assert any(e["category"] == "pro_baseline" for e in entries)
        assert any(e["category"] == "opening_duels" for e in entries)
        assert any(e["category"] == "clutch_performance" for e in entries)

    def test_mine_single_player_integration(self):
        """Test mining knowledge from a real DB record."""
        hltv_db = get_hltv_db_manager()
        with hltv_db.get_session() as session:
            self._create_player_and_card(
                session,
                hltv_id=99901,
                nickname="test_miner_player",
                rating=1.20,
                impact=1.15,
            )

        miner = ProStatsMiner()
        count = miner.mine_all_pro_stats(limit=50)
        self._track_knowledge()

        # At least 1 entry for our test player (baseline)
        assert count >= 1, f"Expected at least 1 knowledge entry, got {count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
