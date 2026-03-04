"""
RAG Knowledge Base Module

Implements Retrieval-Augmented Generation for contextual coaching insights.

Components:
    - Vector embeddings (Sentence-BERT)
    - Semantic search (cosine similarity)
    - Knowledge retrieval
    - Contextual insight generation

Adheres to GEMINI.md principles:
    - Explicit state management
    - Performance optimization
    - Clear separation of concerns
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from sqlmodel import select

from Programma_CS2_RENAN.backend.knowledge.round_utils import infer_round_phase  # F5-20: shared utility
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import TacticalKnowledge
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.rag_knowledge")


class KnowledgeEmbedder:
    """
    Generate vector embeddings for tactical knowledge.

    Uses Sentence-BERT (all-MiniLM-L6-v2) for semantic embeddings.
    Falls back to simple TF-IDF if sentence-transformers not available.

    Task 2.10.1: Now tracks embedding version to detect stale embeddings
    and trigger automatic re-embedding when the model changes.
    """

    # Increment when embedding model changes (Task 2.10.1)
    CURRENT_VERSION = "v2"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None
        self.embedding_dim = 384

        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(model_name)
            logger.info("Loaded embedding model: %s", model_name)
        except ImportError:
            logger.warning("sentence-transformers not installed. Using fallback embeddings.")
            self.embedding_dim = 100  # Fallback dimension

    def embed(self, text: str) -> np.ndarray:
        """
        Generate embedding for text.

        Args:
            text: Input text

        Returns:
            Embedding vector [embedding_dim]
        """
        if self.model is not None:
            return self.model.encode(text, convert_to_numpy=True)
        else:
            # Fallback: Simple hash-based embedding
            return self._fallback_embed(text)

    def _fallback_embed(self, text: str) -> np.ndarray:
        """Simple fallback embedding using deterministic hashing."""
        import hashlib

        # Create deterministic embedding from text (hashlib is session-stable unlike hash())
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        seed = int(digest[:8], 16)
        rng = np.random.RandomState(seed)
        return rng.randn(self.embedding_dim).astype(np.float32)

    def check_embedding_compatibility(self, stored_dim: int) -> bool:
        """
        Check if stored embeddings are compatible with current model.

        Task 2.10.1: Returns False if dimension mismatch detected,
        indicating that embeddings need to be regenerated.

        Args:
            stored_dim: Dimension of stored embedding vector

        Returns:
            bool: True if compatible, False if re-embedding needed
        """
        return stored_dim == self.embedding_dim

    def trigger_reembedding(self) -> int:
        """
        Re-embed all TacticalKnowledge entries with mismatched dimensions.

        Task 2.10.1: Called when embedding model changes to ensure
        all stored embeddings are compatible with current model.

        Returns:
            int: Number of entries re-embedded
        """
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager
        from Programma_CS2_RENAN.backend.storage.db_models import TacticalKnowledge

        db = get_db_manager()
        count = 0

        # Limit to prevent OOM on large knowledge bases (F5-03).
        MAX_REEMBED_BATCH = 5_000
        with db.get_session() as session:
            entries = session.exec(select(TacticalKnowledge).limit(MAX_REEMBED_BATCH)).all()

            for entry in entries:
                try:
                    embedding = json.loads(entry.embedding)

                    # Check if re-embedding is needed
                    if len(embedding) != self.embedding_dim:
                        # Re-embed using title + description + situation
                        text = f"{entry.title}. {entry.description}. {entry.situation}"
                        new_embedding = self.embed(text)
                        entry.embedding = json.dumps(new_embedding.tolist())
                        session.add(entry)
                        count += 1
                        logger.info("Re-embedded: %s", entry.title)
                except Exception as e:
                    logger.warning("Failed to re-embed %s: %s", entry.id, e)

            session.commit()

        logger.info("Re-embedded %s knowledge entries", count)
        return count


class KnowledgeRetriever:
    """
    Semantic search over tactical knowledge base.

    Uses cosine similarity for ranking.
    """

    def __init__(self):
        # F5-23: init_database() removed — must be called once at app startup, not per-constructor.
        self.db = get_db_manager()
        self.embedder = KnowledgeEmbedder()

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        category: Optional[str] = None,
        map_name: Optional[str] = None,
    ) -> List[TacticalKnowledge]:
        """
        Retrieve most relevant tactical knowledge.

        Args:
            query: Search query (e.g., "low ADR on T-side")
            top_k: Number of results
            category: Filter by category
            map_name: Filter by map

        Returns:
            List of TacticalKnowledge entries, ranked by relevance
        """
        # Encode query
        query_embedding = self.embedder.embed(query)

        # Fetch all knowledge (with filters)
        with self.db.get_session() as session:
            stmt = select(TacticalKnowledge)

            if category:
                stmt = stmt.where(TacticalKnowledge.category == category)
            if map_name:
                stmt = stmt.where(TacticalKnowledge.map_name == map_name)

            stmt = stmt.limit(500)
            knowledge_entries = session.exec(stmt).all()

            if not knowledge_entries:
                logger.warning("No knowledge entries found")
                return []

            # Compute similarities
            similarities = []
            for entry in knowledge_entries:
                entry_embedding = np.array(json.loads(entry.embedding))
                similarity = self._cosine_similarity(query_embedding, entry_embedding)
                similarities.append((entry, similarity))

            # Sort by similarity (descending)
            similarities.sort(key=lambda x: x[1], reverse=True)

            # Return top-k
            top_entries = [entry for entry, _ in similarities[:top_k]]

            # Capture IDs to avoid DetachedInstanceError when updating counts
            top_ids = [e.id for e in top_entries]

        # Update usage count
        self._update_usage_counts(top_ids)

        return top_entries

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)

    def _update_usage_counts(self, knowledge_ids: List[int]):
        """Increment usage count for retrieved knowledge."""
        with self.db.get_session() as session:
            for kid in knowledge_ids:
                entry = session.get(TacticalKnowledge, kid)
                if entry:
                    entry.usage_count += 1
                    session.add(entry)
            session.commit()


class KnowledgePopulator:
    """
    Populate knowledge base with tactical insights.

    Sources:
        - Map-specific tactics (JSON files)
        - Pro demo analysis
        - Community best practices
    """

    def __init__(self):
        # F5-23: init_database() removed — must be called once at app startup, not per-constructor.
        self.db = get_db_manager()
        self.embedder = KnowledgeEmbedder()

    def add_knowledge(
        self,
        title: str,
        description: str,
        category: str,
        situation: str,
        map_name: Optional[str] = None,
        pro_example: Optional[str] = None,
    ) -> TacticalKnowledge:
        """
        Add new tactical knowledge to database.

        Args:
            title: Knowledge title
            description: Detailed description
            category: Category (positioning, economy, utility, aim)
            situation: Tactical situation
            map_name: Optional map name
            pro_example: Optional pro demo reference

        Returns:
            Created TacticalKnowledge entry
        """
        # Generate embedding
        text = f"{title}. {description}. {situation}"
        embedding = self.embedder.embed(text)

        # Create knowledge entry
        knowledge = TacticalKnowledge(
            title=title,
            description=description,
            category=category,
            situation=situation,
            map_name=map_name,
            pro_example=pro_example,
            embedding=json.dumps(embedding.tolist()),
        )

        # Save to database
        with self.db.get_session() as session:
            session.add(knowledge)
            session.commit()
            session.refresh(knowledge)

        logger.info("Added knowledge: %s", title)
        return knowledge

    def populate_from_json(self, json_path: Path):
        """
        Populate knowledge from JSON file.

        Expected format:
        {
            "knowledge": [
                {
                    "title": "...",
                    "description": "...",
                    "category": "...",
                    "situation": "...",
                    "map_name": "...",
                    "pro_example": "..."
                }
            ]
        }
        """
        with open(json_path, "r") as f:
            data = json.load(f)

        count = 0
        for entry in data.get("knowledge", []):
            self.add_knowledge(**entry)
            count += 1

        logger.info("Populated %s knowledge entries from %s", count, json_path)


def generate_rag_coaching_insight(
    player_stats: Dict[str, float], map_name: Optional[str] = None
) -> str:
    """
    Generate RAG-enhanced coaching insight.

    Args:
        player_stats: Player statistics (e.g., {"avg_adr": 65, "avg_kills": 15})
        map_name: Optional map name for context

    Returns:
        Contextual coaching insight
    """
    retriever = KnowledgeRetriever()

    # Construct query from stats
    query_parts = []
    if player_stats.get("avg_adr", 0) < 75:
        query_parts.append("low ADR")
    if player_stats.get("avg_kills", 0) < 18:
        query_parts.append("low kills")
    if player_stats.get("kd_ratio", 0) < 1.0:
        query_parts.append("negative K/D")

    query = " ".join(query_parts) if query_parts else "general improvement"

    # Retrieve relevant knowledge
    knowledge = retriever.retrieve(query, top_k=2, map_name=map_name)

    if not knowledge:
        return "Practice aim and positioning to improve your stats."

    # Generate contextual insight
    insight_parts = []
    for k in knowledge:
        insight_parts.append(f"{k.title}: {k.description}")  # Emoji stripped — presentation is UI concern
        if k.pro_example:
            insight_parts.append(f"   Pro example: {k.pro_example}")

    return "\n".join(insight_parts)


if __name__ == "__main__":
    # F5-27: NOTE — this __main__ block is a development self-test only.
    # The hardcoded knowledge entries below are SYNTHETIC test data, not real match data.
    # TODO: move this to tests/knowledge/test_rag_knowledge.py when a test harness is available.
    logger.info("=== RAG Knowledge Base Test (synthetic data — not for production) ===\n")

    # Populate sample knowledge
    populator = KnowledgePopulator()

    populator.add_knowledge(
        title="Mirage T-side: Control mid early",
        description="Pro teams boost ADR by taking mid control in first 30 seconds. Use connector smoke and window flash.",
        category="positioning",
        situation="T-side, low ADR",
        map_name="de_mirage",
        pro_example="Team Liquid vs NAVI - IEM Katowice 2024",
    )

    populator.add_knowledge(
        title="Economy management: Force buy timing",
        description="Force buy on round 3 if you lost pistol and first gun round. Maximize utility damage.",
        category="economy",
        situation="Lost pistol round",
        map_name=None,
    )

    # Test retrieval
    retriever = KnowledgeRetriever()
    results = retriever.retrieve("low ADR on Mirage", top_k=1, map_name="de_mirage")

    logger.info("Found %s results:", len(results))
    for r in results:
        logger.info("  - %s", r.title)
        logger.info("    %s", r.description)

    # Test RAG coaching
    stats = {"avg_adr": 65, "avg_kills": 15}
    insight = generate_rag_coaching_insight(stats, map_name="de_mirage")
    logger.info("RAG Insight: %s", insight)


def generate_unified_coaching_insight(
    player_stats: Dict[str, float],
    tick_data: Optional[Dict[str, Any]] = None,
    map_name: Optional[str] = None,
) -> str:
    """
    Generate unified coaching insight combining RAG knowledge + Experience Bank.

    This is the recommended entry point for COPER-style coaching that
    combines tactical knowledge with learned experiences.

    Args:
        player_stats: Player statistics (e.g., {"avg_adr": 65})
        tick_data: Optional current tick state for context
        map_name: Optional map name

    Returns:
        Unified coaching insight with pro references
    """
    insight_parts = []

    # 1. Get RAG tactical knowledge
    try:
        rag_insight = generate_rag_coaching_insight(player_stats, map_name)
        if rag_insight and "Practice aim" not in rag_insight:
            insight_parts.append("Tactical Knowledge:")
            insight_parts.append(rag_insight)
    except Exception as e:
        logger.warning("RAG retrieval failed: %s", e)

    # 2. Get Experience Bank insights (if tick data available)
    if tick_data:
        try:
            from Programma_CS2_RENAN.backend.knowledge.experience_bank import (
                ExperienceContext,
                get_experience_bank,
            )

            bank = get_experience_bank()  # Singleton — avoids re-loading SBERT model (F5-04)

            # Build context
            context = ExperienceContext(
                map_name=map_name or "unknown",
                round_phase=infer_round_phase(tick_data),
                side=tick_data.get("team", "T"),
                position_area=tick_data.get("position_area"),
            )

            # Get synthesized advice
            advice = bank.synthesize_advice(context)

            if advice.experiences_used > 0:
                insight_parts.append("\nExperience-Based Advice:")
                insight_parts.append(advice.narrative)

                if advice.pro_references:
                    insight_parts.append("\nPro References:")
                    for ref in advice.pro_references:
                        insight_parts.append(f"  - {ref}")

        except Exception as e:
            logger.warning("Experience Bank retrieval failed: %s", e)

    if not insight_parts:
        return "Keep practicing! Analyze your demos to build personalized coaching insights."

    return "\n".join(insight_parts)


# F5-20: _infer_round_phase extracted to round_utils.infer_round_phase (shared utility).
