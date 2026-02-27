"""
Knowledge Graph Manager

Implements "Doctorate-Level" structured memory for the tactical engine.
Stores entities and relations in a graph structure (SQLite-backed) to support
multi-hop reasoning and RAG.

Inspired by Model Context Protocol (MCP) Memory Server.
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from Programma_CS2_RENAN.core.config import USER_DATA_ROOT
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.knowledge_graph")


class KnowledgeGraphManager:
    """
    Manages the Knowledge Graph (Entities & Relations).

    Database: <USER_DATA_ROOT>/knowledge_graph.db
    Schema: Entities, Relations
    """

    # F5-08: Use config constant instead of fragile __file__ traversal.
    DB_PATH = str(Path(USER_DATA_ROOT) / "knowledge_graph.db")

    def __init__(self):
        self._init_db()

    def _init_db(self):
        """Initialize the graph database schema."""
        os.makedirs(os.path.dirname(self.DB_PATH), exist_ok=True)
        try:
            with sqlite3.connect(self.DB_PATH) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                # Entities Table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS entities (
                        name TEXT PRIMARY KEY,
                        type TEXT NOT NULL,
                        observations TEXT  -- JSON list of strings
                    )
                """
                )
                # Relations Table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS relations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        from_entity TEXT NOT NULL,
                        to_entity TEXT NOT NULL,
                        relation_type TEXT NOT NULL,
                        metadata TEXT,  -- JSON dict
                        FOREIGN KEY(from_entity) REFERENCES entities(name),
                        FOREIGN KEY(to_entity) REFERENCES entities(name),
                        UNIQUE(from_entity, to_entity, relation_type)
                    )
                """
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to initialize Knowledge Graph DB: %s", e)

    def add_entity(self, name: str, entity_type: str, observations: List[str] = None):  # F5-30: renamed from `type` to avoid shadowing builtin
        """
        Upsert an entity.

        Args:
            name: Unique name (e.g., "Mirage/Window")
            entity_type: Entity type (e.g., "Spot")
            observations: List of facts (e.g., ["Key control point", "Vulnerable to flashes"])
        """
        obs_json = json.dumps(observations or [])
        try:
            with sqlite3.connect(self.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO entities (name, type, observations)
                    VALUES (?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        type=excluded.type,
                        observations=excluded.observations
                """,
                    (name, entity_type, obs_json),
                )
                conn.commit()
            logger.info("Graph: Upserted Entity '%s' (%s)", name, entity_type)
        except Exception as e:
            logger.error("Failed to add entity %s: %s", name, e)

    def add_relation(self, from_e: str, to_e: str, relation: str, metadata: Dict = None):
        """
        Create a directed edge between entities.

        Args:
            from_e: Source entity name
            to_e: Target entity name
            relation: Predicate (e.g., "CONNECTS_TO")
        """
        meta_json = json.dumps(metadata or {})
        try:
            with sqlite3.connect(self.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO relations (from_entity, to_entity, relation_type, metadata)
                    VALUES (?, ?, ?, ?)
                """,
                    (from_e, to_e, relation, meta_json),
                )
                conn.commit()
            logger.debug("Graph: Linked '%s' --[%s]--> '%s'", from_e, relation, to_e)
        except Exception as e:
            logger.error("Failed to add relation %s->%s: %s", from_e, to_e, e)

    def query_subgraph(self, central_entity: str, depth: int = 1) -> Dict:
        """
        Retrieve the subgraph surrounding a central entity.
        Useful for RAG context retrieval.

        Args:
            central_entity: Name of the central node to query around.
            depth: Traversal depth. Currently only depth=1 (direct neighbors)
                is implemented. Multi-hop traversal is not yet implemented.

        Returns:
            Dict containing 'entity' (central node) and 'neighbors' (list of relations)
        """
        if depth > 1:
            logger.warning(
                "query_subgraph called with depth=%d but only depth=1 is implemented; "
                "returning 1-hop neighbors only",
                depth,
            )
        result = {"entity": None, "neighbors": []}

        try:
            with sqlite3.connect(self.DB_PATH) as conn:
                conn.row_factory = sqlite3.Row

                # Fetch Central Entity
                cursor = conn.execute("SELECT * FROM entities WHERE name = ?", (central_entity,))
                root = cursor.fetchone()
                if not root:
                    return result

                result["entity"] = {
                    "name": root["name"],
                    "type": root["type"],
                    "observations": json.loads(root["observations"]),
                }

                # Fetch 1-hop Neighbors (Outgoing)
                cursor = conn.execute(
                    """
                    SELECT r.relation_type, e.name, e.type, e.observations
                    FROM relations r
                    JOIN entities e ON r.to_entity = e.name
                    WHERE r.from_entity = ?
                """,
                    (central_entity,),
                )

                rows = cursor.fetchall()
                for row in rows:
                    result["neighbors"].append(
                        {
                            "relation": row["relation_type"],
                            "target": {
                                "name": row["name"],
                                "type": row["type"],
                                "observations": json.loads(row["observations"]),
                            },
                        }
                    )

        except Exception as e:
            logger.error("Graph query failed for %s: %s", central_entity, e)

        return result


# Singleton
_graph_instance = None


def get_knowledge_graph() -> KnowledgeGraphManager:
    global _graph_instance
    if not _graph_instance:
        _graph_instance = KnowledgeGraphManager()
    return _graph_instance
