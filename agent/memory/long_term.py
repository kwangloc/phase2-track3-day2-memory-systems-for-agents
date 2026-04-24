"""Long-term profile memory — JSON-backed key-value store.

Conflict handling: last-write-wins.  Calling ``update`` with a new value
for an existing key silently overwrites the old value (no duplicates /
contradictions accumulate in the profile).
"""
import json
import os


class LongTermMemory:
    """Persistent profile store backed by a JSON file."""

    def __init__(self, path: str = "data/profiles.json") -> None:
        self.path = path
        self._store: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Internal persistence helpers
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
    # Read
    # ------------------------------------------------------------------

    def get_profile(self, user_id: str) -> dict:
        """Return a copy of the stored profile (empty dict if none)."""
        return dict(self._store.get(user_id, {}))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update(self, user_id: str, key: str, value: str) -> None:
        """Upsert a single fact.  New value always replaces old one."""
        if user_id not in self._store:
            self._store[user_id] = {}
        self._store[user_id][key] = value
        self._save()

    def update_many(self, user_id: str, facts: dict) -> None:
        """Upsert multiple facts at once."""
        for k, v in facts.items():
            if isinstance(v, str) and v.strip():
                self.update(user_id, k, v.strip())

    def clear(self, user_id: str) -> None:
        self._store[user_id] = {}
        self._save()
