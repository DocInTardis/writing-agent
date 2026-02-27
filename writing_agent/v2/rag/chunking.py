"""Chunking module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import re


def chunk_text(*, text: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
    """
    Simple, dependency-free chunking.
    - Prefers paragraph boundaries; falls back to sentence-ish splitting.
    - Returns non-empty chunks <= ~max_chars (soft limit).
    """
    src = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not src:
        return []
    max_chars = int(max(200, min(5000, max_chars)))
    overlap = int(max(0, min(max_chars // 2, overlap)))

    paras = [p.strip() for p in re.split(r"\n\s*\n+", src) if p.strip()]
    if len(paras) <= 1:
        # sentence-ish fallback (keeps punctuation)
        parts = [p.strip() for p in re.split(r"(?<=[。！？!?.])\s*", src) if p.strip()]
        paras = parts if parts else [src]

    chunks: list[str] = []
    buf = ""
    for para in paras:
        if not para:
            continue
        if not buf:
            buf = para
            continue
        if len(buf) + 2 + len(para) <= max_chars:
            buf = buf + "\n\n" + para
            continue
        chunks.append(buf.strip())
        if overlap > 0:
            tail = buf[-overlap:]
            buf = (tail + "\n\n" + para).strip()
        else:
            buf = para
    if buf.strip():
        chunks.append(buf.strip())

    # hard cap (rare huge para)
    out: list[str] = []
    for c in chunks:
        if len(c) <= max_chars * 2:
            out.append(c)
            continue
        # split long chunk by fixed window
        step = max(100, max_chars - overlap)
        i = 0
        while i < len(c):
            out.append(c[i : i + max_chars].strip())
            i += step
    return [c for c in out if c]

