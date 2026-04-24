"""Short-term memory — sliding-window conversation buffer.

Stores the last ``max_messages`` (role, content) pairs per session_id.
No persistence: lives only in-process memory.
"""


class ShortTermMemory:
    """In-memory sliding-window buffer keyed by session_id."""

    def __init__(self, max_messages: int = 10) -> None:
        self.max_messages = max_messages
        self._store: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(self, session_id: str, role: str, content: str) -> None:
        """Append a message and trim to the window size."""
        if session_id not in self._store:
            self._store[session_id] = []
        self._store[session_id].append({"role": role, "content": content})
        if len(self._store[session_id]) > self.max_messages:
            self._store[session_id] = self._store[session_id][-self.max_messages :]

    def clear(self, session_id: str) -> None:
        self._store[session_id] = []

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, session_id: str) -> list[dict]:
        """Return a copy of the current window."""
        return list(self._store.get(session_id, []))

    def word_count(self, session_id: str) -> int:
        msgs = self._store.get(session_id, [])
        return sum(len(m["content"].split()) for m in msgs)
