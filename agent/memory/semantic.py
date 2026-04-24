"""Semantic memory — BM25-scored document store backed by JSON.

Uses pure-Python BM25 scoring (no external vector library required).
Documents are stored with their token lists; retrieval scores every
document against the query and returns the top-n.
"""
import json
import math
import os
import re
from collections import Counter


class SemanticMemory:
    """BM25 keyword-based document store with JSON persistence."""

    # BM25 hyper-parameters
    K1: float = 1.5
    B: float = 0.75

    def __init__(self, path: str = "data/semantic_store.json") -> None:
        self.path = path
        self._documents: list[dict] = []  # [{id, text, tokens}]
        self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def _load(self) -> None:
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
                self._documents = data.get("documents", [])

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(
                {"documents": self._documents}, fh, ensure_ascii=False, indent=2
            )

    def _avg_dl(self) -> float:
        if not self._documents:
            return 0.0
        return sum(len(d["tokens"]) for d in self._documents) / len(self._documents)

    def _bm25(self, query_tokens: list[str], doc: dict) -> float:
        N = len(self._documents)
        if N == 0:
            return 0.0
        avg_dl = self._avg_dl()
        dl = len(doc["tokens"])
        tf = Counter(doc["tokens"])
        score = 0.0
        for token in query_tokens:
            f = tf.get(token, 0)
            if f == 0:
                continue
            df = sum(1 for d in self._documents if token in d["tokens"])
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            denom = f + self.K1 * (1 - self.B + self.B * dl / max(avg_dl, 1))
            tf_norm = (f * (self.K1 + 1)) / denom
            score += idf * tf_norm
        return score

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_document(self, doc_id: str, text: str) -> None:
        """Add or replace a document (upsert by id)."""
        self._documents = [d for d in self._documents if d["id"] != doc_id]
        self._documents.append(
            {"id": doc_id, "text": text, "tokens": self._tokenize(text)}
        )
        self._save()

    def clear(self) -> None:
        self._documents = []
        self._save()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(self, query: str, n: int = 3) -> list[str]:
        """Return text of top-n documents by BM25 score (score > 0 only)."""
        if not self._documents:
            return []
        q_tokens = self._tokenize(query)
        scored = [(self._bm25(q_tokens, doc), doc["text"]) for doc in self._documents]
        scored.sort(reverse=True)
        return [text for score, text in scored[:n] if score > 0]
