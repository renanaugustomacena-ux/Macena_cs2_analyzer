"""
Unit tests for RAG knowledge base.

Tests embeddings, retrieval, and knowledge population.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from sqlmodel import select

from Programma_CS2_RENAN.backend.knowledge.rag_knowledge import (
    KnowledgeEmbedder,
    KnowledgePopulator,
    KnowledgeRetriever,
    generate_rag_coaching_insight,
)
from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database
from Programma_CS2_RENAN.backend.storage.db_models import TacticalKnowledge


class TestKnowledgeEmbedder:
    """Test suite for knowledge embedder."""

    def test_embedder_initialization(self):
        """Test embedder can be initialized."""
        embedder = KnowledgeEmbedder()
        assert embedder.embedding_dim > 0

    def test_embed_text(self):
        """Test text embedding generation."""
        embedder = KnowledgeEmbedder()

        text = "Mirage T-side mid control"
        embedding = embedder.embed(text)

        assert isinstance(embedding, np.ndarray)
        assert embedding.shape[0] == embedder.embedding_dim
        assert not np.isnan(embedding).any()

    def test_embed_consistency(self):
        """Test same text produces same embedding."""
        embedder = KnowledgeEmbedder()

        text = "Test consistency"
        emb1 = embedder.embed(text)
        emb2 = embedder.embed(text)

        assert np.allclose(emb1, emb2)


class TestKnowledgePopulator:
    """Test suite for knowledge population."""

    _TEST_PREFIX = "_TEST_RAG_"

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Initialize test database before each test — only touches test-prefixed rows."""
        init_database()

        # Clean up only test-specific knowledge rows (never production data)
        db = get_db_manager()
        with db.get_session() as session:
            test_rows = session.exec(
                select(TacticalKnowledge).where(
                    TacticalKnowledge.title.startswith(self._TEST_PREFIX)
                )
            ).all()
            for k in test_rows:
                session.delete(k)
            session.commit()
        yield
        # Teardown: clean up again
        with db.get_session() as session:
            test_rows = session.exec(
                select(TacticalKnowledge).where(
                    TacticalKnowledge.title.startswith(self._TEST_PREFIX)
                )
            ).all()
            for k in test_rows:
                session.delete(k)
            session.commit()

    def test_add_knowledge(self):
        """Test adding knowledge to database."""
        populator = KnowledgePopulator()

        knowledge = populator.add_knowledge(
            title=f"{self._TEST_PREFIX}knowledge",
            description="Test description",
            category="positioning",
            situation="Test situation",
            map_name="de_mirage",
        )

        assert knowledge.id is not None
        assert knowledge.title == f"{self._TEST_PREFIX}knowledge"
        assert knowledge.embedding is not None

    def test_knowledge_has_embedding(self):
        """Test knowledge has valid embedding."""
        populator = KnowledgePopulator()

        knowledge = populator.add_knowledge(
            title=f"{self._TEST_PREFIX}embed", description="Test", category="aim", situation="Test"
        )

        embedding = json.loads(knowledge.embedding)
        assert isinstance(embedding, list)
        assert len(embedding) == populator.embedder.embedding_dim


class TestKnowledgeRetriever:
    """Test suite for knowledge retrieval."""

    _TEST_PREFIX = "_TEST_RAG_"

    @pytest.fixture(autouse=True)
    def setup_knowledge(self):
        """Populate test knowledge before each test — only touches test-prefixed rows."""
        init_database()

        db = get_db_manager()
        # Clean up only test rows
        with db.get_session() as session:
            test_rows = session.exec(
                select(TacticalKnowledge).where(
                    TacticalKnowledge.title.startswith(self._TEST_PREFIX)
                )
            ).all()
            for k in test_rows:
                session.delete(k)
            session.commit()

        # Add test knowledge
        populator = KnowledgePopulator()

        populator.add_knowledge(
            title=f"{self._TEST_PREFIX}Mirage mid control",
            description="Take mid control early for ADR boost",
            category="positioning",
            situation="T-side, low ADR",
            map_name="de_mirage",
        )

        populator.add_knowledge(
            title=f"{self._TEST_PREFIX}Economy management",
            description="Force buy on round 3",
            category="economy",
            situation="Lost pistol round",
        )
        yield
        # Teardown
        with db.get_session() as session:
            test_rows = session.exec(
                select(TacticalKnowledge).where(
                    TacticalKnowledge.title.startswith(self._TEST_PREFIX)
                )
            ).all()
            for k in test_rows:
                session.delete(k)
            session.commit()

    def test_retrieve_knowledge(self):
        """Test basic knowledge retrieval."""
        retriever = KnowledgeRetriever()

        results = retriever.retrieve("low ADR", top_k=1)

        assert len(results) > 0
        assert isinstance(results[0], TacticalKnowledge)

    def test_retrieve_with_map_filter(self):
        """Test retrieval with map filter."""
        retriever = KnowledgeRetriever()

        results = retriever.retrieve("mid control", top_k=1, map_name="de_mirage")

        assert len(results) > 0
        assert results[0].map_name == "de_mirage"

    def test_retrieve_with_category_filter(self):
        """Test retrieval with category filter."""
        retriever = KnowledgeRetriever()

        results = retriever.retrieve("force buy", top_k=1, category="economy")

        assert len(results) > 0
        assert results[0].category == "economy"

    def test_usage_count_increments(self):
        """Test usage count increments on retrieval."""
        retriever = KnowledgeRetriever()

        # First retrieval
        results = retriever.retrieve("mid control", top_k=1)
        initial_count = results[0].usage_count

        # Second retrieval
        results = retriever.retrieve("mid control", top_k=1)

        # Refresh from database
        db = get_db_manager()
        with db.get_session() as session:
            knowledge = session.get(TacticalKnowledge, results[0].id)
            assert knowledge.usage_count > initial_count


class TestRAGCoaching:
    """Test suite for RAG-enhanced coaching."""

    # F9-20: prefix isolates test rows from production data
    _COACHING_TEST_PREFIX = "_TEST_RAG_COACHING_"

    @pytest.fixture(autouse=True)
    def setup_knowledge(self):
        """Populate test knowledge — only touches rows prefixed with _COACHING_TEST_PREFIX."""
        init_database()

        # Pre-cleanup: remove any leftover test rows from previous runs
        db = get_db_manager()
        with db.get_session() as session:
            test_rows = session.exec(
                select(TacticalKnowledge).where(
                    TacticalKnowledge.title.startswith(self._COACHING_TEST_PREFIX)
                )
            ).all()
            for k in test_rows:
                session.delete(k)
            session.commit()

        populator = KnowledgePopulator()
        populator.add_knowledge(
            title=f"{self._COACHING_TEST_PREFIX}Improve ADR",
            description="Focus on mid control",
            category="positioning",
            situation="Low ADR",
            map_name="de_mirage",
        )
        yield
        # F9-20: teardown — delete prefixed test rows to prevent DB pollution
        with db.get_session() as session:
            test_rows = session.exec(
                select(TacticalKnowledge).where(
                    TacticalKnowledge.title.startswith(self._COACHING_TEST_PREFIX)
                )
            ).all()
            for k in test_rows:
                session.delete(k)
            session.commit()

    def test_generate_rag_insight(self):
        """Test RAG coaching insight generation."""
        stats = {"avg_adr": 60, "avg_kills": 12}

        insight = generate_rag_coaching_insight(stats, map_name="de_mirage")

        assert isinstance(insight, str)
        assert len(insight) > 0

    def test_insight_contains_knowledge(self):
        """Test insight contains retrieved knowledge relevant to the map."""
        stats = {"avg_adr": 60}

        insight = generate_rag_coaching_insight(stats, map_name="de_mirage")

        # Insight should reference the map or contain coaching content
        insight_lower = insight.lower()
        assert any(
            term in insight_lower
            for term in [
                "mirage",
                "adr",
                "mid control",
                "positioning",
                "pro",
                "strategy",
            ]
        ), f"Insight should contain map/coaching context, got: {insight[:120]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
