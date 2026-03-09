"""
Knowledge Base Initialization Script

Populates the RAG knowledge base with:
1. Manual tactical knowledge (tactical_knowledge.json)
2. Automated pro demo mining
3. Validation and deduplication

Run this once to initialize the knowledge base.
"""

from pathlib import Path

# AC-34-01: Removed sys.path hack — module is imported as a package.
PROJECT_ROOT = Path(__file__).parent.parent.parent

from sqlalchemy import func
from sqlmodel import select

from Programma_CS2_RENAN.backend.knowledge.pro_demo_miner import auto_populate_from_pro_demos
from Programma_CS2_RENAN.backend.knowledge.rag_knowledge import KnowledgePopulator
from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database
from Programma_CS2_RENAN.backend.storage.db_models import TacticalKnowledge
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.knowledge_init")


def initialize_knowledge_base():
    """
    Initialize knowledge base with all sources.

    Steps:
    1. Initialize database
    2. Load manual knowledge from JSON
    3. Mine knowledge from pro demos
    4. Report statistics
    """
    logger.info("=== Knowledge Base Initialization ===\n")

    # Step 1: Initialize database
    logger.info("Step 1: Initializing database...")
    init_database()

    # Step 2: Load manual knowledge
    logger.info("Step 2: Loading manual tactical knowledge...")
    populator = KnowledgePopulator()

    json_path = (
        PROJECT_ROOT / "Programma_CS2_RENAN" / "backend" / "knowledge" / "tactical_knowledge.json"
    )

    if json_path.exists():
        try:
            populator.populate_from_json(json_path)
            logger.info("✓ Loaded manual knowledge from %s", json_path)
        except Exception as e:
            logger.error("Failed to load manual knowledge: %s", e)
    else:
        logger.warning("Manual knowledge file not found: %s", json_path)

    # Step 3: Mine pro demos
    logger.info("Step 3: Mining knowledge from pro demos...")
    try:
        count = auto_populate_from_pro_demos(limit=10)
        logger.info("✓ Mined %s entries from pro demos", count)
    except Exception as e:
        logger.error("Failed to mine pro demos: %s", e)

    # Step 4: Report statistics
    logger.info("\nStep 4: Knowledge Base Statistics")
    db = get_db_manager()

    with db.get_session() as session:
        # Use COUNT query — avoid loading all rows into memory (F5-03).
        total_count = session.exec(
            select(func.count()).select_from(TacticalKnowledge)
        ).one()

        # Count by category (aggregate, no full table scan)
        cat_rows = session.exec(
            select(TacticalKnowledge.category, func.count().label("cnt"))
            .group_by(TacticalKnowledge.category)
            .order_by(func.count().desc())
        ).all()

        map_rows = session.exec(
            select(TacticalKnowledge.map_name, func.count().label("cnt"))
            .where(TacticalKnowledge.map_name.isnot(None))
            .group_by(TacticalKnowledge.map_name)
            .order_by(func.count().desc())
        ).all()

        logger.info("=" * 50)
        logger.info("Total Knowledge Entries: %s", total_count)
        logger.info("=" * 50)
        logger.info("By Category:")
        for cat, cnt in cat_rows:
            logger.info("  %-15s: %3d entries", cat, cnt)
        logger.info("By Map:")
        for map_name, cnt in map_rows:
            logger.info("  %-15s: %3d entries", map_name, cnt)
        logger.info("=" * 50)

    # Step 5: Build FAISS vector indexes (AC-36-02)
    try:
        from Programma_CS2_RENAN.backend.knowledge.vector_index import get_vector_index_manager

        index_mgr = get_vector_index_manager()
        if index_mgr:
            k_count = index_mgr.rebuild_from_db("knowledge")
            e_count = index_mgr.rebuild_from_db("experience")
            logger.info("FAISS indexes built: %d knowledge, %d experience vectors", k_count, e_count)
    except Exception as e:
        logger.warning("FAISS index build skipped (non-fatal): %s", e)

    logger.info("Knowledge base initialization complete!")


if __name__ == "__main__":
    initialize_knowledge_base()
