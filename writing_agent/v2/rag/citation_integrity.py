"""Citation Integrity module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class CitationCheck:
    ok: bool
    reachable: bool
    status: int
    consistent: bool
    reason: str


def check_reachability(url: str, timeout_s: float = 3.0) -> tuple[bool, int]:
    raw = str(url or "").strip()
    if not raw:
        return False, 0
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return False, 0
    req = Request(raw, method="HEAD")
    try:
        with urlopen(req, timeout=timeout_s) as resp:  # nosec B310
            code = int(getattr(resp, "status", 0) or 0)
            return 200 <= code < 400, code
    except Exception:
        return False, 0


def check_metadata_consistency(*, title: str, source_title: str, author: str, source_author: str) -> bool:
    t1 = str(title or "").strip().lower()
    t2 = str(source_title or "").strip().lower()
    a1 = str(author or "").strip().lower()
    a2 = str(source_author or "").strip().lower()
    title_ok = bool(t1 and t2 and (t1 in t2 or t2 in t1))
    author_ok = not a1 or not a2 or (a1 in a2 or a2 in a1)
    return title_ok and author_ok


def citation_span_grounding(text: str, citations: list[dict]) -> list[dict]:
    body = str(text or "")
    out: list[dict] = []
    for row in citations or []:
        cid = str((row or {}).get("id") or "")
        marker = str((row or {}).get("marker") or "")
        if not marker:
            continue
        idx = body.find(marker)
        out.append({"id": cid, "marker": marker, "start": idx, "end": (idx + len(marker)) if idx >= 0 else -1})
    return out
