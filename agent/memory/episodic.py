"""Episodic memory — JSON-backed timestamped episode log.

Each episode is a dict: {timestamp, topic, summary, outcome}.
Retrieval uses keyword overlap scoring so no external vector library
is required.
"""
import json
import os
from datetime import datetime


class EpisodicMemory:
    """Append-only episode log with keyword-based search."""

    def __init__(self, path: str = "data/episodes.json") -> None:
        self.path = path
        self._store: dict[str, list[dict]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Internal persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                self._store = json.load(fh)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self._store, fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_episode(
        self, user_id: str, topic: str, summary: str, outcome: str
    ) -> None:
        if user_id not in self._store:
            self._store[user_id] = []
        self._store[user_id].append(
            {
                "timestamp": datetime.now().isoformat(),
                "topic": topic,
                "summary": summary,
                "outcome": outcome,
            }
        )
        self._save()

    def clear(self, user_id: str) -> None:
        self._store[user_id] = []
        self._save()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def retrieve_recent(self, user_id: str, n: int = 3) -> list[dict]:
        return list(self._store.get(user_id, []))[-n:]

    def search(self, user_id: str, query: str, n: int = 3) -> list[dict]:
        """Return up to n episodes with the highest keyword overlap."""
        episodes = self._store.get(user_id, [])
        if not episodes:
            return []
        query_tokens = set(query.lower().split())
        scored: list[tuple[int, dict]] = []
        for ep in episodes:
            text = " ".join(
                [ep.get("topic", ""), ep.get("summary", ""), ep.get("outcome", "")]
            ).lower()
            score = sum(1 for w in query_tokens if w in text)
            scored.append((score, ep))
        scored.sort(key=lambda x: x[0], reverse=True)
        # Only return episodes with at least one keyword match
        return [ep for score, ep in scored[:n] if score > 0]
