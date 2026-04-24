"""agent — Multi-Memory Agent package.

Public exports
--------------
MemoryAgent       Full LangGraph-backed agent with 4 memory types.
NoMemoryAgent     Baseline stateless agent for benchmark comparison.
get_semantic_memory   Access the shared SemanticMemory backend.
"""
from .graph import MemoryAgent, NoMemoryAgent, get_semantic_memory

__all__ = ["MemoryAgent", "NoMemoryAgent", "get_semantic_memory"]
