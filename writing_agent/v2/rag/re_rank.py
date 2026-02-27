"""Re Rank module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RerankItem:
    text: str
    score: float


def rerank_texts(*, query: str, items: list[RerankItem], top_k: int = 8) -> list[RerankItem]:
    q = str(query or "").lower()
    ranked: list[RerankItem] = []
    for row in items:
        text = str(row.text or "")
        bonus = 0.0
        if q and q in text.lower():
            bonus += 0.3
        if len(text) > 400:
            bonus += 0.05
        ranked.append(RerankItem(text=text, score=float(row.score) + bonus))
    ranked.sort(key=lambda x: x.score, reverse=True)
    return ranked[: max(1, int(top_k))]
