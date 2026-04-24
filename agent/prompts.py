"""Prompt builder — assembles a system prompt from all four memory sections
and enforces a configurable word-count token budget."""


def build_system_prompt(
    user_profile: dict,
    episodes: list[dict],
    semantic_hits: list[str],
    memory_budget: int = 800,
) -> str:
    """Return a system-prompt string with memory context injected.

    The four sections (profile, episodic, semantic, recent-conversation
    note) are added only when they contain data.  The total word count
    is capped at *memory_budget* words; excess content is trimmed with a
    notice.
    """
    sections: list[str] = []

    # --- Long-term profile ---
    if user_profile:
        lines = [f"- {k}: {v}" for k, v in user_profile.items()]
        sections.append("## User Profile\n" + "\n".join(lines))

    # --- Episodic memories ---
    if episodes:
        lines = []
        for ep in episodes:
            date = ep.get("timestamp", "")[:10]
            topic = ep.get("topic", "")
            summary = ep.get("summary", "")
            outcome = ep.get("outcome", "")
            lines.append(f"- [{date}] {topic}: {summary} → {outcome}")
        sections.append("## Past Episodes\n" + "\n".join(lines))

    # --- Semantic knowledge ---
    if semantic_hits:
        lines = [f"- {chunk}" for chunk in semantic_hits]
        sections.append("## Relevant Knowledge\n" + "\n".join(lines))

    # --- Base prompt ---
    base = (
        "You are a helpful assistant with persistent memory about the user. "
        "Use the memory sections below to give personalised, consistent answers."
    )
    full = base + ("\n\n" + "\n\n".join(sections) if sections else "")

    # --- Token budget (word-count approximation) ---
    words = full.split()
    if len(words) > memory_budget:
        full = " ".join(words[:memory_budget]) + " ... [memory trimmed due to budget]"

    return full
