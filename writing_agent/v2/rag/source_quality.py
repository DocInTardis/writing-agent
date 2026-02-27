"""Source Quality module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceQuality:
    score: float
    level: str
    reason: str


DEFAULT_ALLOW = {"arxiv.org", "doi.org", "openalex.org", "crossref.org"}
DEFAULT_DENY = {"example.com", "localhost"}


def score_source(*, url: str, author: str = "", recency_days: int | None = None) -> SourceQuality:
    host = (urlparse(str(url or "")).hostname or "").lower()
    score = 0.4
    reason = []
    if host in DEFAULT_ALLOW:
        score += 0.4
        reason.append("allowlist_host")
    if host in DEFAULT_DENY:
        score -= 0.6
        reason.append("denylist_host")
    if author:
        score += 0.1
        reason.append("has_author")
    if recency_days is not None:
        if recency_days <= 365 * 2:
            score += 0.1
            reason.append("fresh")
        elif recency_days > 365 * 8:
            score -= 0.1
            reason.append("stale")
    score = max(0.0, min(1.0, score))
    if score >= 0.75:
        level = "high"
    elif score >= 0.45:
        level = "medium"
    else:
        level = "low"
    return SourceQuality(score=score, level=level, reason=",".join(reason) or "default")
