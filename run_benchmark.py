"""run_benchmark.py — Run 10 multi-turn conversations and write BENCHMARK.md.

Usage
-----
    python run_benchmark.py

Requires
--------
    OPENAI_API_KEY in .env (or environment variable)
    pip install langchain-openai langgraph python-dotenv

What it does
------------
1. Seeds SemanticMemory with 5 FAQ knowledge chunks.
2. For each of 10 scenarios:
   a. Creates a fresh MemoryAgent (user_id isolated per scenario).
   b. Runs the full *setup* conversation through the LangGraph agent,
      building up short-term, long-term, episodic, and semantic memory.
   c. Asks the *probe* question to:
      - NoMemoryAgent  (receives ONLY the probe question, no context)
      - MemoryAgent    (receives probe after full memory is built)
   d. Determines Pass/Fail by checking expected keywords in the
      with-memory response.
3. Writes BENCHMARK.md with a summary table + detailed per-scenario logs.

Benchmark categories covered
-----------------------------
  profile_recall       scenarios 1, 5, 6
  conflict_update      scenario 2
  episodic_recall      scenarios 3, 7
  semantic_retrieval   scenarios 4, 8
  trim_budget          scenario 9
  combined             scenario 10
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Validate API key early
if not os.getenv("OPENAI_API_KEY"):
    print("ERROR: OPENAI_API_KEY not set. Check your .env file.", file=sys.stderr)
    sys.exit(1)

from agent import MemoryAgent, NoMemoryAgent, get_semantic_memory  # noqa: E402
from agent.conversation_store import ConversationStore  # noqa: E402

_DATA_DIR = Path(__file__).parent / "data"

# ---------------------------------------------------------------------------
# Load knowledge base and scenarios from JSON files
# ---------------------------------------------------------------------------


def _load_json(filename: str) -> list:
    path = _DATA_DIR / filename
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


KNOWLEDGE_BASE: list[dict] = _load_json("knowledge_base.json")
SCENARIOS: list[dict] = _load_json("scenarios.json")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_pass(response: str, keywords: list[str], condition: str = "any") -> bool:
    lower = response.lower()
    matches = [kw.lower() in lower for kw in keywords]
    return any(matches) if condition == "any" else all(matches)


def _truncate(text: str, max_chars: int = 120) -> str:
    text = text.replace("\n", " ").replace("|", "\\|")
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def _word_count(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------------------
# Main benchmark runner
# ---------------------------------------------------------------------------


def run_benchmark() -> None:
    print("=== Multi-Memory Agent Benchmark ===")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Seed semantic knowledge base
    semantic = get_semantic_memory()
    print("Seeding semantic knowledge base...")
    for chunk in KNOWLEDGE_BASE:
        semantic.add_document(chunk["id"], chunk["text"])
    print(f"  {len(KNOWLEDGE_BASE)} documents loaded.\n")

    no_mem_agent = NoMemoryAgent()
    results: list[dict] = []
    conv_store = ConversationStore(
        path=str(_DATA_DIR / "conversations.json"),
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
    )

    for scenario in SCENARIOS:
        sid = scenario["id"]
        desc = scenario["description"]
        category = scenario["category"]
        setup_turns: list[str] = scenario["setup_turns"]
        probe: str = scenario["probe"]
        keywords: list[str] = scenario["expected_keywords"]
        condition: str = scenario.get("pass_condition", "any")

        print(f"--- Scenario {sid}: {desc} ---")
        user_id = f"benchmark_user_{sid}"
        mem_agent = MemoryAgent(user_id=user_id, memory_budget=600)
        mem_agent.clear_memory()
        conv_store.start_scenario(sid, desc, category)

        # Run setup turns through memory agent
        setup_responses: list[dict] = []
        for i, turn_msg in enumerate(setup_turns, 1):
            print(f"  [setup {i}/{len(setup_turns)}] {turn_msg[:60]}...")
            resp = mem_agent.chat(turn_msg)
            setup_responses.append({"user": turn_msg, "assistant": resp})
            conv_store.add_setup_turn(i, "user", turn_msg)
            conv_store.add_setup_turn(i, "assistant", resp)

        # Probe both agents
        print(f"  [probe] {probe}")
        no_mem_resp = no_mem_agent.chat(probe)
        with_mem_resp = mem_agent.chat(probe)

        passed = _check_pass(with_mem_resp, keywords, condition)
        status = "PASS" if passed else "FAIL"
        print(f"  Result: {status}")
        print(f"  No-memory  : {_truncate(no_mem_resp, 80)}")
        print(f"  With-memory: {_truncate(with_mem_resp, 80)}\n")

        conv_store.add_probe(probe, no_mem_resp, with_mem_resp)
        conv_store.finish_scenario(passed, keywords, condition)

        results.append(
            {
                "scenario": scenario,
                "setup_responses": setup_responses,
                "no_memory_response": no_mem_resp,
                "with_memory_response": with_mem_resp,
                "passed": passed,
            }
        )

    conv_store.save()
    print(f"Conversations saved to {_DATA_DIR / 'conversations.json'}")
    _write_benchmark(results)


def _write_benchmark(results: list[dict]) -> None:
    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []

    # Header
    lines += [
        "# BENCHMARK — Multi-Memory Agent với LangGraph",
        "",
        f"**Generated:** {now}  ",
        f"**Model:** {os.getenv('LLM_MODEL', 'gpt-4o-mini')}  ",
        f"**Result:** {passed_count}/{total} scenarios passed",
        "",
        "---",
        "",
    ]

    # Summary table
    lines += [
        "## Summary Table",
        "",
        "| # | Scenario | Category | No-memory result | With-memory result | Pass? |",
        "|---|----------|----------|------------------|---------------------|-------|",
    ]
    for r in results:
        s = r["scenario"]
        no_mem = _truncate(r["no_memory_response"], 80)
        with_mem = _truncate(r["with_memory_response"], 80)
        badge = "✅ Pass" if r["passed"] else "❌ Fail"
        lines.append(
            f"| {s['id']} | {s['description']} | {s['category']} "
            f"| {no_mem} | {with_mem} | {badge} |"
        )
    lines += [
        "",
        f"**Total: {passed_count}/{total} scenarios passed.**",
        "",
        "---",
        "",
    ]

    # Detailed per-scenario logs
    lines += ["## Detailed Results", ""]
    for r in results:
        s = r["scenario"]
        badge = "✅ Pass" if r["passed"] else "❌ Fail"

        lines += [
            f"### Scenario {s['id']}: {s['description']} {badge}",
            "",
            f"**Category:** `{s['category']}`  ",
            f"**Expected keywords (any):** {', '.join(f'`{k}`' for k in s['expected_keywords'])}",
            "",
            "#### Setup Conversation (with-memory agent)",
            "",
        ]
        for i, turn in enumerate(r["setup_responses"], 1):
            lines += [
                f"**Turn {i}**",
                f"> 🧑 {turn['user']}",
                "",
                f"> 🤖 {turn['assistant']}",
                "",
            ]

        # Probe
        lines += [
            "#### Probe Question",
            "",
            f"> 🧑 **{s['probe']}**",
            "",
            "**No-memory response:**",
            "",
            f"> {r['no_memory_response']}",
            "",
            "**With-memory response:**",
            "",
            f"> {r['with_memory_response']}",
            "",
            f"**Verdict:** {badge}  ",
            f"**Word count** — no-memory: {_word_count(r['no_memory_response'])}, "
            f"with-memory: {_word_count(r['with_memory_response'])}",
            "",
            "---",
            "",
        ]

    # Reflection section
    lines += [
        "## Reflection: Privacy & Limitations",
        "",
        "### 1. Memory nào giúp agent nhất?",
        "",
        "**Long-term profile memory** (LongTermMemory) mang lại giá trị cao nhất trong các cuộc trò chuyện nhiều phiên: "
        "agent không cần hỏi lại tên, nghề nghiệp, dị ứng của người dùng mỗi lần. "
        "**Episodic memory** đặc biệt hữu ích khi người dùng muốn tham chiếu lại một session trước.",
        "",
        "### 2. Memory nào rủi ro nhất nếu retrieve sai?",
        "",
        "**Long-term profile** là rủi ro nhất. Nếu extract sai (ví dụ: gán dị ứng của người A cho người B "
        "hoặc nhận nhầm thông tin y tế), agent có thể đưa ra lời khuyên nguy hiểm. "
        "**Semantic memory** cũng rủi ro nếu retrieve tài liệu lỗi thời hoặc sai ngữ cảnh.",
        "",
        "### 3. Nếu user yêu cầu xóa memory, xóa ở backend nào?",
        "",
        "- **ShortTermMemory**: `short_term.clear(user_id)` — xóa ngay khỏi RAM.",
        "- **LongTermMemory**: `long_term.clear(user_id)` — xóa record trong `data/profiles.json`.",
        "- **EpisodicMemory**: `episodic.clear(user_id)` — xóa tất cả episode trong `data/episodes.json`.",
        "- **SemanticMemory**: Cần xác định tài liệu nào thuộc user → "
        "`semantic.add_document` với nội dung rỗng hoặc filter theo metadata.",
        "",
        "### 4. Điều gì sẽ làm system fail khi scale?",
        "",
        "| Limitation | Mô tả |",
        "|------------|-------|",
        "| JSON file locking | `profiles.json` và `episodes.json` không thread-safe khi nhiều agent ghi đồng thời. Cần thay bằng Redis / SQLite với WAL. |",
        "| LLM extraction cost | Mỗi turn gọi thêm 1–2 LLM calls để extract facts và summarise episodes. Chi phí tăng tuyến tính. |",
        "| BM25 không semantic | Keyword search bỏ sót trường hợp đồng nghĩa (\"dị ứng\" vs \"không ăn được\"). Cần embedding thật (FAISS/Chroma) cho production. |",
        "| Không có TTL | Profile facts không hết hạn. Thông tin cũ (ví dụ địa chỉ đã thay đổi) tồn tại mãi. Cần TTL hoặc versioning. |",
        "| PII không mã hóa | Tên, dị ứng, nghề nghiệp lưu dạng plain-text JSON. Cần mã hóa at-rest và kiểm soát truy cập (consent + audit log). |",
        "",
        "### 5. PII và consent",
        "",
        "- Dữ liệu profile (tên, tuổi, dị ứng) là PII nhạy cảm — cần có explicit consent trước khi lưu.",
        "- Nên hiển thị cho user những gì đang được lưu (transparency).",
        "- Cần cơ chế Right-to-be-Forgotten: xóa toàn bộ data của một user theo yêu cầu.",
        "",
    ]

    content = "\n".join(lines)
    out_path = "BENCHMARK.md"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    print(f"Benchmark written to {out_path}  ({passed_count}/{total} passed)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_benchmark()
