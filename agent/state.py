"""MemoryState — shared state dict passed through every LangGraph node."""
from typing import TypedDict


class MemoryState(TypedDict):
    # Short-term: sliding-window conversation history (updated each turn)
    messages: list[dict]
    # Identifier for this user / benchmark scenario
    user_id: str
    # Long-term: profile key-value facts loaded from JSON store
    user_profile: dict
    # Episodic: relevant past episodes retrieved for this turn
    episodes: list[dict]
    # Semantic: relevant knowledge chunks retrieved for this turn
    semantic_hits: list[str]
    # Max words allowed in the memory section of the system prompt
    memory_budget: int
    # Current user message (set before invoking the graph)
    current_input: str
    # Agent's response (set by generate_response node)
    response: str
