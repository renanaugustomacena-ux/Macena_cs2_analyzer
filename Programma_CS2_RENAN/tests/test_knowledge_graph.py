"""
Tests for Knowledge Graph Manager — Phase 5 Coverage Expansion.

Covers:
  KnowledgeGraphManager (graph.py) — SQLite-backed entity/relation graph
  - Schema initialization, WAL mode
  - Entity CRUD (add, get, upsert)
  - Relation CRUD (add, uniqueness)
  - Subgraph queries (1-hop)
"""

import sys


import json
import sqlite3

import pytest


class TestKnowledgeGraphManager:
    """Tests for the SQLite-backed knowledge graph."""

    def _make_graph(self, tmp_path):
        """Create a KnowledgeGraphManager pointing to a temp DB."""
        from Programma_CS2_RENAN.backend.knowledge.graph import KnowledgeGraphManager

        graph = KnowledgeGraphManager.__new__(KnowledgeGraphManager)
        graph.DB_PATH = str(tmp_path / "test_kg.db")
        graph._init_db()
        return graph

    # --- Schema ---

    def test_init_creates_tables(self, tmp_path):
        graph = self._make_graph(tmp_path)
        conn = sqlite3.connect(graph.DB_PATH)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "entities" in tables
        assert "relations" in tables

    def test_init_wal_mode(self, tmp_path):
        graph = self._make_graph(tmp_path)
        conn = sqlite3.connect(graph.DB_PATH)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_init_idempotent(self, tmp_path):
        """Calling _init_db twice must not crash or duplicate tables."""
        graph = self._make_graph(tmp_path)
        graph._init_db()  # Second call
        conn = sqlite3.connect(graph.DB_PATH)
        cursor = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='entities'"
        )
        assert cursor.fetchone()[0] == 1
        conn.close()

    # --- Entity CRUD ---

    def test_add_entity_basic(self, tmp_path):
        graph = self._make_graph(tmp_path)
        graph.add_entity("Mirage/Window", "Spot", ["Key control point"])
        conn = sqlite3.connect(graph.DB_PATH)
        row = conn.execute(
            "SELECT * FROM entities WHERE name = ?", ("Mirage/Window",)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "Mirage/Window"
        assert row[1] == "Spot"
        obs = json.loads(row[2])
        assert "Key control point" in obs

    def test_add_entity_no_observations(self, tmp_path):
        graph = self._make_graph(tmp_path)
        graph.add_entity("Dust2/Long", "Spot")
        conn = sqlite3.connect(graph.DB_PATH)
        row = conn.execute(
            "SELECT observations FROM entities WHERE name = ?", ("Dust2/Long",)
        ).fetchone()
        conn.close()
        assert json.loads(row[0]) == []

    def test_add_entity_upsert_updates(self, tmp_path):
        graph = self._make_graph(tmp_path)
        graph.add_entity("Mid", "Zone", ["Control area"])
        graph.add_entity("Mid", "HotZone", ["Updated", "Multi-entry"])
        conn = sqlite3.connect(graph.DB_PATH)
        row = conn.execute(
            "SELECT type, observations FROM entities WHERE name = ?", ("Mid",)
        ).fetchone()
        conn.close()
        assert row[0] == "HotZone"
        obs = json.loads(row[1])
        assert "Updated" in obs
        assert "Multi-entry" in obs

    def test_add_entity_preserves_existing(self, tmp_path):
        """Adding a new entity should NOT overwrite other entities."""
        graph = self._make_graph(tmp_path)
        graph.add_entity("A-site", "Site")
        graph.add_entity("B-site", "Site")
        conn = sqlite3.connect(graph.DB_PATH)
        count = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        conn.close()
        assert count == 2

    # --- Relation CRUD ---

    def test_add_relation_basic(self, tmp_path):
        graph = self._make_graph(tmp_path)
        graph.add_entity("A-site", "Site")
        graph.add_entity("Short", "Zone")
        graph.add_relation("A-site", "Short", "CONNECTS_TO")
        conn = sqlite3.connect(graph.DB_PATH)
        row = conn.execute(
            "SELECT * FROM relations WHERE from_entity = ? AND to_entity = ?",
            ("A-site", "Short"),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[3] == "CONNECTS_TO"

    def test_add_relation_with_metadata(self, tmp_path):
        graph = self._make_graph(tmp_path)
        graph.add_entity("Window", "Spot")
        graph.add_entity("Catwalk", "Spot")
        meta = {"distance": 15.5, "smoke_blocks": True}
        graph.add_relation("Window", "Catwalk", "OVERLOOKS", metadata=meta)
        conn = sqlite3.connect(graph.DB_PATH)
        row = conn.execute(
            "SELECT metadata FROM relations WHERE from_entity = ? AND to_entity = ?",
            ("Window", "Catwalk"),
        ).fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert parsed["distance"] == 15.5
        assert parsed["smoke_blocks"] is True

    def test_add_relation_ignores_duplicate(self, tmp_path):
        graph = self._make_graph(tmp_path)
        graph.add_entity("A", "Node")
        graph.add_entity("B", "Node")
        graph.add_relation("A", "B", "LINK")
        graph.add_relation("A", "B", "LINK")  # Duplicate — INSERT OR IGNORE
        conn = sqlite3.connect(graph.DB_PATH)
        count = conn.execute(
            "SELECT count(*) FROM relations WHERE from_entity = ? AND to_entity = ? AND relation_type = ?",
            ("A", "B", "LINK"),
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_add_relation_different_types_allowed(self, tmp_path):
        """Same entity pair with different relation types should be distinct."""
        graph = self._make_graph(tmp_path)
        graph.add_entity("X", "Node")
        graph.add_entity("Y", "Node")
        graph.add_relation("X", "Y", "CONNECTS_TO")
        graph.add_relation("X", "Y", "OVERLOOKS")
        conn = sqlite3.connect(graph.DB_PATH)
        count = conn.execute(
            "SELECT count(*) FROM relations WHERE from_entity = ? AND to_entity = ?",
            ("X", "Y"),
        ).fetchone()[0]
        conn.close()
        assert count == 2

    # --- Subgraph Query ---

    def test_query_subgraph_nonexistent_entity(self, tmp_path):
        graph = self._make_graph(tmp_path)
        result = graph.query_subgraph("DoesNotExist")
        assert result["entity"] is None
        assert result["neighbors"] == []

    def test_query_subgraph_entity_only(self, tmp_path):
        """Entity exists but has no outgoing relations."""
        graph = self._make_graph(tmp_path)
        graph.add_entity("Isolated", "Node", ["Alone"])
        result = graph.query_subgraph("Isolated")
        assert result["entity"] is not None
        assert result["entity"]["name"] == "Isolated"
        assert result["entity"]["type"] == "Node"
        assert "Alone" in result["entity"]["observations"]
        assert result["neighbors"] == []

    def test_query_subgraph_with_neighbors(self, tmp_path):
        graph = self._make_graph(tmp_path)
        graph.add_entity("A-site", "Site", ["Plant zone"])
        graph.add_entity("Short", "Zone", ["Fast rotate"])
        graph.add_entity("Ramp", "Zone", ["T approach"])
        graph.add_relation("A-site", "Short", "CONNECTS_TO")
        graph.add_relation("A-site", "Ramp", "CONNECTS_TO")

        result = graph.query_subgraph("A-site")
        assert result["entity"]["name"] == "A-site"
        assert len(result["neighbors"]) == 2

        neighbor_names = {n["target"]["name"] for n in result["neighbors"]}
        assert neighbor_names == {"Short", "Ramp"}

        for neighbor in result["neighbors"]:
            assert neighbor["relation"] == "CONNECTS_TO"
            assert "name" in neighbor["target"]
            assert "type" in neighbor["target"]
            assert "observations" in neighbor["target"]

    def test_query_subgraph_outgoing_only(self, tmp_path):
        """query_subgraph should only return outgoing relations."""
        graph = self._make_graph(tmp_path)
        graph.add_entity("Center", "Node")
        graph.add_entity("Left", "Node")
        graph.add_entity("Right", "Node")
        graph.add_relation("Center", "Right", "GOES_TO")
        graph.add_relation("Left", "Center", "GOES_TO")  # Incoming — not returned

        result = graph.query_subgraph("Center")
        assert len(result["neighbors"]) == 1
        assert result["neighbors"][0]["target"]["name"] == "Right"

    def test_query_subgraph_depth_warning(self, tmp_path):
        """Depth > 1 should still work (returns 1-hop) but logs a warning."""
        graph = self._make_graph(tmp_path)
        graph.add_entity("Root", "Node")
        graph.add_entity("Child", "Node")
        graph.add_relation("Root", "Child", "HAS")
        result = graph.query_subgraph("Root", depth=3)
        # Should still return 1-hop results without error
        assert result["entity"]["name"] == "Root"
        assert len(result["neighbors"]) == 1

    def test_query_subgraph_observations_parsed(self, tmp_path):
        """Observations should be parsed from JSON into Python list."""
        graph = self._make_graph(tmp_path)
        graph.add_entity("Spot", "Position", ["High ground", "AWP angle", "Vulnerable to flash"])
        result = graph.query_subgraph("Spot")
        obs = result["entity"]["observations"]
        assert isinstance(obs, list)
        assert len(obs) == 3
        assert "High ground" in obs
