import os
from pathlib import Path

from Programma_CS2_RENAN.core.config import get_resource_path


class HelpSystem:
    """
    Manages the in-app knowledge base.
    Reads markdown files from data/docs and provides search/retrieval.
    """

    def __init__(self):
        self.docs_dir = get_resource_path(os.path.join("data", "docs"))
        self._cache = {}  # id -> {title, content}
        self.refresh_index()

    def refresh_index(self):
        """Scans the docs directory and builds the index."""
        self._cache = {}
        if not os.path.exists(self.docs_dir):
            return

        for filename in os.listdir(self.docs_dir):
            if filename.endswith(".md"):
                topic_id = filename.replace(".md", "")
                path = os.path.join(self.docs_dir, filename)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        raw = f.read()

                        # Extract Title (First H1 #)
                        lines = raw.split("\n")
                        title = topic_id.replace("_", " ").title()
                        for line in lines:
                            if line.startswith("# "):
                                title = line.replace("# ", "").strip()
                                break

                        self._cache[topic_id] = {"title": title, "content": raw, "path": path}
                except Exception as e:
                    print(f"Error reading doc {filename}: {e}")

    def get_topic(self, topic_id):
        """Returns the content for a specific topic."""
        return self._cache.get(topic_id)

    def get_all_topics(self):
        """Returns a list of dicts {id, title, content} for the menu."""
        return [
            {"id": k, "title": v["title"], "content": v.get("content", "")}
            for k, v in self._cache.items()
        ]

    def search_topics(self, query):
        """Simple text search across titles and content."""
        query = query.lower()
        results = []
        for tid, data in self._cache.items():
            score = 0
            if query in data["title"].lower():
                score += 10
            if query in data["content"].lower():
                score += 1

            if score > 0:
                results.append({"id": tid, "title": data["title"], "score": score})

        # Sort by relevance
        return sorted(results, key=lambda x: x["score"], reverse=True)


# Lazy singleton — avoids file I/O at import time (C-54)
_help_system = None


def get_help_system() -> HelpSystem:
    """Return the cached HelpSystem singleton (lazy-initialized)."""
    global _help_system
    if _help_system is None:
        _help_system = HelpSystem()
    return _help_system
