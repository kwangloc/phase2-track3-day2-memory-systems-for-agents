"""LangGraph multi-memory agent.

Graph topology
--------------
  START → retrieve_memory → generate_response → save_memory → END

Node responsibilities
---------------------
  retrieve_memory   Pull profile (long-term), episodes (episodic),
                    semantic hits (semantic), and recent history
                    (short-term) into the state dict.

  generate_response Build a memory-injected system prompt, call the
                    LLM, update short-term memory.

  save_memory       LLM-based extraction of new profile facts
                    (last-write-wins conflict handling) and periodic
                    episode summarisation.

Public interface
----------------
  MemoryAgent   – wraps the compiled graph; one instance per user/session.
  NoMemoryAgent – baseline; single LLM call with no memory context.
  get_semantic_memory() – expose the shared SemanticMemory backend so
                          run_benchmark.py can pre-seed knowledge chunks.
"""
from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from .memory.episodic import EpisodicMemory
from .memory.long_term import LongTermMemory
from .memory.semantic import SemanticMemory
from .memory.short_term import ShortTermMemory
from .prompts import build_system_prompt
from .state import MemoryState

# ---------------------------------------------------------------------------
# Module-level memory backend singletons
# (shared across all MemoryAgent instances; isolated by user_id)
# ---------------------------------------------------------------------------
_short_term = ShortTermMemory(max_messages=10)
_long_term = LongTermMemory()
_episodic = EpisodicMemory()
_semantic = SemanticMemory()


def get_semantic_memory() -> SemanticMemory:
    """Return the shared semantic memory backend (for pre-seeding)."""
    return _semantic


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def retrieve_memory(state: MemoryState) -> dict:
    """Load all memory backends into the state."""
    user_id = state["user_id"]
    query = state["current_input"]

    profile = _long_term.get_profile(user_id)

    # Prefer relevant episodes; fall back to recent ones
    episodes = _episodic.search(user_id, query, n=3)
    if not episodes:
        episodes = _episodic.retrieve_recent(user_id, n=2)

    hits = _semantic.search(query, n=3)
    recent = _short_term.get(user_id)

    return {
        "user_profile": profile,
        "episodes": episodes,
        "semantic_hits": hits,
        "messages": recent,
    }


def generate_response(state: MemoryState) -> dict:
    """Build the injected prompt and call the LLM."""
    system_content = build_system_prompt(
        user_profile=state["user_profile"],
        episodes=state["episodes"],
        semantic_hits=state["semantic_hits"],
        memory_budget=state.get("memory_budget", 800),
    )

    lc_msgs: list = [SystemMessage(content=system_content)]
    for m in state.get("messages", []):
        if m["role"] == "user":
            lc_msgs.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            lc_msgs.append(AIMessage(content=m["content"]))
    lc_msgs.append(HumanMessage(content=state["current_input"]))

    result = _get_llm().invoke(lc_msgs)
    response_text: str = result.content

    user_id = state["user_id"]
    _short_term.add(user_id, "user", state["current_input"])
    _short_term.add(user_id, "assistant", response_text)

    return {
        "response": response_text,
        "messages": _short_term.get(user_id),
    }


def save_memory(state: MemoryState) -> dict:
    """Extract new facts and persist memory updates."""
    user_id = state["user_id"]
    user_input = state["current_input"]
    llm = _get_llm()

    # --- Profile fact extraction (last-write-wins = conflict resolution) ---
    extraction_prompt = (
        "Extract personal facts about the user from the following single message. "
        "Return a JSON object only (e.g. {\"name\": \"Linh\", \"allergy\": \"đậu nành\"}). "
        "Only include facts explicitly stated by the user. "
        "If the user corrects a previous statement, reflect the corrected value. "
        "If no personal facts are present, return {}.\n\n"
        f"User message: {user_input}\n\nJSON:"
    )
    try:
        raw = llm.invoke([HumanMessage(content=extraction_prompt)]).content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        facts: dict = json.loads(raw)
        if isinstance(facts, dict) and facts:
            _long_term.update_many(user_id, facts)
    except Exception:
        pass  # Extraction failure is non-fatal

    # --- Episodic memory: summarise every 4 messages (2 full turns) ---
    messages = _short_term.get(user_id)
    if len(messages) >= 4 and len(messages) % 4 == 0:
        recent_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in messages[-4:]
        )
        episode_prompt = (
            "Summarise the following short conversation as an episode entry. "
            "Return JSON with exactly these keys: topic, summary, outcome. "
            "Keep each value under 25 words.\n\n"
            f"{recent_text}\n\nJSON:"
        )
        try:
            raw = llm.invoke([HumanMessage(content=episode_prompt)]).content.strip()
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            ep: dict = json.loads(raw)
            if isinstance(ep, dict):
                _episodic.save_episode(
                    user_id,
                    ep.get("topic", "General"),
                    ep.get("summary", ""),
                    ep.get("outcome", ""),
                )
        except Exception:
            pass  # Episode save failure is non-fatal

    return {}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def _build_graph() -> Any:
    graph = StateGraph(MemoryState)
    graph.add_node("retrieve_memory", retrieve_memory)
    graph.add_node("generate_response", generate_response)
    graph.add_node("save_memory", save_memory)
    graph.set_entry_point("retrieve_memory")
    graph.add_edge("retrieve_memory", "generate_response")
    graph.add_edge("generate_response", "save_memory")
    graph.add_edge("save_memory", END)
    return graph.compile()


# ---------------------------------------------------------------------------
# Agent interfaces
# ---------------------------------------------------------------------------

class MemoryAgent:
    """Full memory-stack agent backed by the LangGraph graph."""

    def __init__(self, user_id: str, memory_budget: int = 800) -> None:
        self.user_id = user_id
        self.memory_budget = memory_budget
        self._app = _build_graph()

    def chat(self, message: str) -> str:
        """Process one user turn and return the assistant response."""
        initial: MemoryState = {
            "messages": [],
            "user_id": self.user_id,
            "user_profile": {},
            "episodes": [],
            "semantic_hits": [],
            "memory_budget": self.memory_budget,
            "current_input": message,
            "response": "",
        }
        result = self._app.invoke(initial)
        return result["response"]

    def clear_memory(self) -> None:
        """Wipe all memory for this user (call before each benchmark run)."""
        _short_term.clear(self.user_id)
        _long_term.clear(self.user_id)
        _episodic.clear(self.user_id)


class NoMemoryAgent:
    """Baseline agent: single-turn LLM call with no memory context."""

    def __init__(self) -> None:
        self._llm = _get_llm()

    def chat(self, message: str) -> str:
        msgs = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content=message),
        ]
        return self._llm.invoke(msgs).content
