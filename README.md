run_benchmark.py
 ├── Seeds SemanticMemory (5 FAQ chunks)
 ├── For each of 10 scenarios:
 │    ├── NoMemoryAgent  → LLM(probe only, no context)
 │    └── MemoryAgent (LangGraph):
 │          setup turns (builds memory) → probe turn
 └── Writes BENCHMARK.md

LangGraph graph per turn:
  START
   ↓
  retrieve_memory  ← short_term (sliding window 10 msgs)
                   ← long_term  (profiles.json, profile facts)
                   ← episodic   (episodes.json, BM25 keyword search)
                   ← semantic   (semantic_store.json, BM25 scoring)
   ↓
  generate_response  ← injects all 4 memory sections into system prompt
                     ← enforces token budget (word-count trim)
                     ← LLM call → updates short_term
   ↓
  save_memory  ← LLM extracts profile facts → long_term upsert (last-write-wins = conflict fix)
               ← LLM summarises episode every 4 messages → episodic save
   ↓
  END

Memory backends:
  ShortTermMemory  → in-memory dict, sliding window max 10 msgs
  LongTermMemory   → data/profiles.json, key-value, last-write-wins
  EpisodicMemory   → data/episodes.json, list + BM25 keyword search
  SemanticMemory   → data/semantic_store.json, BM25 scoring (no external deps)

10 benchmark categories:
  1,5,6   profile recall       4,8   semantic retrieval
  2       conflict update       9     token budget / trim
  3,7     episodic recall      10    combined