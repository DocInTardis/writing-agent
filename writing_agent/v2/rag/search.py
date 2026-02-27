"""Search module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from writing_agent.v2.rag.store import RagPaperRecord


@dataclass(frozen=True)
class RagSearchHit:
    paper_id: str
    title: str
    summary: str
    score: float
    published: str
    abs_url: str
    pdf_path: str
    snippet: str


def search_papers(*, papers: list[RagPaperRecord], query: str, top_k: int = 5) -> list[RagSearchHit]:
    q = (query or "").strip()
    if not q:
        return []
    top_k = int(max(1, min(20, top_k)))

    q_tokens = _tokens(q)
    hits: list[RagSearchHit] = []
    for p in papers:
        title = p.title or ""
        summary = p.summary or ""
        title_l = title.lower()
        summary_l = summary.lower()

        score = 0.0
        for tok in q_tokens:
            if not tok:
                continue
            tok_l = tok.lower()
            if len(tok_l) == 1 and tok_l.isspace():
                continue
            score += 3.0 * _count_occurrences(title_l, tok_l)
            score += 1.0 * _count_occurrences(summary_l, tok_l)

        if score <= 0:
            continue
        # small normalization to avoid long-summary bias
        score = score / (1.0 + 0.05 * math.log(2.0 + len(summary_l)))

        hits.append(
            RagSearchHit(
                paper_id=p.paper_id,
                title=title,
                summary=summary,
                score=float(score),
                published=p.published,
                abs_url=p.abs_url,
                pdf_path=p.pdf_path,
                snippet=_make_snippet(title=title, summary=summary, query=q),
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]


def build_rag_context(*, hits: list[RagSearchHit], max_chars: int = 2500) -> str:
    max_chars = int(max(400, min(20000, max_chars)))
    out: list[str] = []
    used = 0
    for h in hits:
        block = f"[{h.paper_id}] {h.title}\n{h.summary}".strip()
        if not block:
            continue
        if used + len(block) + 2 > max_chars:
            break
        out.append(block)
        used += len(block) + 2
    return "\n\n".join(out).strip()


def _tokens(text: str) -> list[str]:
    s = (text or "").strip()
    toks = re.findall(r"[A-Za-z0-9_]+", s)
    if toks:
        return [t for t in toks if t]
    # CJK / mixed-language fallback: per-character tokens (ignoring whitespace)
    return [ch for ch in s if ch.strip()]


def _count_occurrences(haystack: str, needle: str) -> int:
    if not needle:
        return 0
    if len(needle) <= 2:
        return haystack.count(needle)
    # for longer tokens, avoid O(n^2) counting on huge strings (still fine here)
    return haystack.count(needle)


def _make_snippet(*, title: str, summary: str, query: str, max_len: int = 240) -> str:
    q = (query or "").strip()
    text = (title + " " + summary).strip()
    if not text:
        return ""
    if not q:
        return text[:max_len]
    idx = text.lower().find(q.lower())
    if idx < 0:
        return text[:max_len]
    start = max(0, idx - 60)
    end = min(len(text), idx + 60)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet[:max_len]
