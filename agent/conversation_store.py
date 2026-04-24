"""ConversationStore — persists benchmark conversation history to JSON.

Schema (data/conversations.json)
---------------------------------
{
  "run_id": "<ISO timestamp>",
  "model": "gpt-4o-mini",
  "generated_at": "<ISO timestamp>",
  "scenarios": [
    {
      "scenario_id": 1,
      "description": "Recall user name after 6 turns",
      "category": "profile_recall",
      "started_at": "<ISO timestamp>",
      "finished_at": "<ISO timestamp>",
      "setup_turns": [
        {
          "turn": 1,
          "role": "user",
          "content": "Xin chào! Tôi tên là Linh.",
          "timestamp": "<ISO timestamp>"
        },
        {
          "turn": 1,
          "role": "assistant",
          "content": "Xin chào Linh! ...",
          "timestamp": "<ISO timestamp>"
        }
        // ... more turns
      ],
      "probe": {
        "question": "Bạn có nhớ tên tôi là gì không?",
        "no_memory_response": {
          "content": "Xin lỗi, tôi không biết tên bạn.",
          "word_count": 7
        },
        "with_memory_response": {
          "content": "Tên bạn là Linh.",
          "word_count": 5
        }
      },
      "result": {
        "passed": true,
        "expected_keywords": ["Linh"],
        "pass_condition": "any"
      }
    }
  ]
}
"""
from __future__ import annotations

import json
import os
from datetime import datetime


class ConversationStore:
    """Accumulates scenario conversation records and flushes them to JSON.

    Usage
    -----
        store = ConversationStore(path="data/conversations.json", model="gpt-4o-mini")
        store.start_scenario(scenario_id=1, description="...", category="...")

        store.add_setup_turn(turn=1, role="user", content="...")
        store.add_setup_turn(turn=1, role="assistant", content="...")

        store.add_probe(
            question="...",
            no_memory_content="...",
            with_memory_content="...",
        )
        store.finish_scenario(passed=True, expected_keywords=["Linh"], pass_condition="any")

        store.save()   # writes / overwrites the JSON file
    """

    def __init__(self, path: str, model: str) -> None:
        self.path = path
        self._run_id = datetime.now().isoformat(timespec="seconds")
        self._model = model
        self._scenarios: list[dict] = []
        self._current: dict | None = None

    # ------------------------------------------------------------------
    # Scenario lifecycle
    # ------------------------------------------------------------------

    def start_scenario(
        self, scenario_id: int, description: str, category: str
    ) -> None:
        """Open a new scenario record.  Must be called before add_* methods."""
        self._current = {
            "scenario_id": scenario_id,
            "description": description,
            "category": category,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
            "setup_turns": [],
            "probe": None,
            "result": None,
        }

    def add_setup_turn(self, turn: int, role: str, content: str) -> None:
        """Append one message (user or assistant) to the setup conversation."""
        if self._current is None:
            raise RuntimeError("Call start_scenario() before add_setup_turn().")
        self._current["setup_turns"].append(
            {
                "turn": turn,
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }
        )

    def add_probe(
        self,
        question: str,
        no_memory_content: str,
        with_memory_content: str,
    ) -> None:
        """Record the probe question and both agent responses."""
        if self._current is None:
            raise RuntimeError("Call start_scenario() before add_probe().")
        self._current["probe"] = {
            "question": question,
            "no_memory_response": {
                "content": no_memory_content,
                "word_count": len(no_memory_content.split()),
            },
            "with_memory_response": {
                "content": with_memory_content,
                "word_count": len(with_memory_content.split()),
            },
        }

    def finish_scenario(
        self,
        passed: bool,
        expected_keywords: list[str],
        pass_condition: str = "any",
    ) -> None:
        """Close the current scenario and move it to the completed list."""
        if self._current is None:
            raise RuntimeError("Call start_scenario() before finish_scenario().")
        self._current["finished_at"] = datetime.now().isoformat(timespec="seconds")
        self._current["result"] = {
            "passed": passed,
            "expected_keywords": expected_keywords,
            "pass_condition": pass_condition,
        }
        self._scenarios.append(self._current)
        self._current = None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write (or overwrite) the JSON file with all completed scenarios."""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {
            "run_id": self._run_id,
            "model": self._model,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "scenario_count": len(self._scenarios),
            "pass_count": sum(1 for s in self._scenarios if s["result"]["passed"]),
            "scenarios": self._scenarios,
        }
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
