"""RAG context retrieval and sanitization helpers for graph runner post-processing."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote


def _maybe_rag_context(*, instruction: str, section: str) -> str:
    enabled_raw = os.environ.get("WRITING_AGENT_RAG_ENABLED", "1").strip().lower()
    if enabled_raw not in {"1", "true", "yes", "on"}:
        return ""

    q = (instruction or "").strip()
    if section:
        q = (q + " " + section).strip()
    top_k = int(os.environ.get("WRITING_AGENT_RAG_TOP_K", "4"))
    max_chars = int(os.environ.get("WRITING_AGENT_RAG_MAX_CHARS", "2500"))
    per_paper = int(os.environ.get("WRITING_AGENT_RAG_PER_PAPER", "2"))

    ctx, _ = _mcp_rag_retrieve(query=q, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    if ctx.strip():
        return _sanitize_rag_context(ctx, max_chars=max_chars)

    try:
        from writing_agent.v2.rag.retrieve import retrieve_context
    except Exception:
        return ""

    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    rag_dir = data_dir / "rag"

    res = retrieve_context(rag_dir=rag_dir, query=q, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    return _sanitize_rag_context(res.context, max_chars=max_chars)

def _mcp_rag_enabled() -> bool:
    raw = os.environ.get("WRITING_AGENT_RAG_MCP", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}

def _mcp_rag_retrieve(*, query: str, top_k: int, per_paper: int, max_chars: int) -> tuple[str, list[dict]]:
    if not _mcp_rag_enabled():
        return "", []
    q = (query or "").strip()
    if not q:
        return "", []
    try:
        from writing_agent.mcp_client import fetch_mcp_json
    except Exception:
        return "", []
    uri = (
        "mcp://rag/retrieve?query="
        + quote(q)
        + f"&top_k={int(top_k)}&per_paper={int(per_paper)}&max_chars={int(max_chars)}"
    )
    data = fetch_mcp_json(uri)
    if not isinstance(data, dict):
        return "", []
    context = str(data.get("context") or "")
    sources = data.get("sources")
    if not isinstance(sources, list):
        sources = []
    return context, sources

def _looks_like_rag_meta_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return True
    low = s.lower()
    if "http://" in low or "https://" in low:
        return True
    if "openalex" in low or "arxiv" in low or "doi" in low:
        return True
    if re.match(r"^\[[^\]]+\]", s):
        return True
    # Common portal/navigation/contact noise from crawled pages.
    if any(
        k in low
        for k in [
            "\u670d\u52a1\u70ed\u7ebf",
            "\u8ba2\u5361\u70ed\u7ebf",
            "\u5728\u7ebf\u54a8\u8be2",
            "\u90ae\u4ef6\u54a8\u8be2",
            "\u5e2e\u52a9\u4e2d\u5fc3",
            "\u4e0b\u8f7d\u4e2d\u5fc3",
            "\u8bfb\u8005\u670d\u52a1",
            "\u5e7f\u544a\u670d\u52a1",
            "\u5ba2\u670d",
            "service.cnki.net",
            "help@",
            "400-",
            "cnki",
            "\u8d2d\u4e70\u77e5\u7f51\u5361",
            "\u77e5\u7f51\u7814\u5b66",
            "cajviewer",
            "\u624b\u673a\u77e5\u7f51",
            "\u6742\u5fd7\u8ba2\u9605",
            "\u6570\u5b57\u51fa\u7248\u7269\u8ba2\u9605",
            "\u603b\u4e0b\u8f7d\u91cf",
            "\u603b\u53d1\u6587\u91cf",
            "\u8ba4\u9886\u6210\u679c",
        ]
    ):
        return True
    if re.search(r"(\u6700\u9ad8\u4e0b\u8f7d|\u603b\u4e0b\u8f7d\u91cf|\u603b\u88ab\u5f15|\u5f15\u7528\u91cf)\s*\d", s):
        return True
    if re.search(r"\d{3,}", s) and len(re.findall(r"\d", s)) >= 8:
        return True
    return False

def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))

def _is_mostly_ascii_line(text: str) -> bool:
    s = text or ""
    letters = sum(1 for ch in s if ch.isascii() and ch.isalpha())
    if letters < 12:
        return False
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    if cjk == 0:
        return True
    return letters > cjk * 2

def _strip_rag_meta_lines(text: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _looks_like_rag_meta_line(line):
            continue
        if _is_mostly_ascii_line(line) and not _has_cjk(line):
            continue
        # Skip mojibake-like tokens (e.g., "娑撴艾濮熷ù浣衡柤") to avoid propagating garbage.
        if re.search(r"[閿燂拷]{2,}|[^\u4e00-\u9fffA-Za-z0-9锛屻€傦紱锛氾紒锛熴€佲€溾€濃€樷€欙紙锛?)\[\]銆愩€慭s\-\+:/.%]", line):
            continue
        norm = re.sub(r"\s+", " ", line).strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        lines.append(norm)
    return " ".join(lines).strip()


def _sanitize_rag_context(text: str, *, max_chars: int = 2500) -> str:
    blocks = [b for b in re.split(r"\n\s*\n+", str(text or "")) if str(b).strip()]
    out_blocks: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        cleaned = _strip_rag_meta_lines(block)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) < 30:
            continue
        if len(set(cleaned)) <= 12:
            continue
        if re.search(r"(鏈€楂樹笅杞絴鏈€楂樿寮晐鎬讳笅杞介噺|鎬诲彂鏂囬噺|鏈嶅姟鐑嚎|璐拱鐭ョ綉鍗鐭ョ綉鐮斿|CAJViewer)", cleaned, flags=re.IGNORECASE):
            continue
        key = cleaned[:120]
        if key in seen:
            continue
        seen.add(key)
        out_blocks.append(cleaned)
        if len("\n\n".join(out_blocks)) >= max(600, int(max_chars * 0.9)):
            break
    merged = "\n\n".join(out_blocks).strip()
    if not merged:
        return ""
    if len(merged) > max_chars:
        clipped = merged[:max_chars]
        cut = max(
            clipped.rfind("\u3002"),
            clipped.rfind("."),
            clipped.rfind("\uff1f"),
            clipped.rfind("!"),
            clipped.rfind(";"),
            clipped.rfind("\uff1b"),
        )
        if cut >= int(max_chars * 0.6):
            merged = clipped[: cut + 1]
        else:
            merged = clipped
    return merged.strip()

