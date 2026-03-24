"""Utility helpers for graph runner post text processing."""

from __future__ import annotations

import json
import re

from writing_agent.v2.doc_format import DocBlock, parse_report_text


def _section_body_len(text: str) -> int:
    if not text:
        return 0
    body = re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", text, flags=re.IGNORECASE)
    return len(body.strip())


def _doc_body_len(text: str) -> int:
    if not text:
        return 0
    body = re.sub(r"(?m)^#{1,6}\s+.+$", "", text or "")
    return _section_body_len(body)


def _count_text_chars(text: str) -> int:
    if not text:
        return 0
    return len(str(text).strip())


def _truncate_to_chars(text: str, max_chars: int) -> str:
    if not text or max_chars <= 0:
        return ""
    value = str(text).strip()
    if len(value) <= max_chars:
        return value
    clipped = value[:max_chars]
    sentence_separators = [chr(0x3002), chr(0xFF01), chr(0xFF1F), ".", "!", "?", ";", chr(0xFF1B)]
    for sep in sentence_separators:
        idx = clipped.rfind(sep)
        if idx >= max(0, int(max_chars * 0.5)):
            return clipped[: idx + 1].strip()
    return clipped.strip()


def _blocks_to_doc_text(blocks: list[DocBlock]) -> str:
    if not blocks:
        return ""
    out: list[str] = []
    for block in blocks:
        if block.type == "heading":
            level = block.level or 1
            out.append(("#" * level) + " " + (block.text or "").strip())
        elif block.type == "paragraph":
            out.append((block.text or "").strip())
        elif block.type == "table":
            out.append(f"[[TABLE:{json.dumps(block.table or {}, ensure_ascii=False)}]]")
        elif block.type == "figure":
            out.append(f"[[FIGURE:{json.dumps(block.figure or {}, ensure_ascii=False)}]]")
    return "\n\n".join([item for item in out if item])


def _trim_total_chars(text: str, max_chars: int) -> str:
    if max_chars <= 0 or not text:
        return text
    if _count_text_chars(text) <= max_chars:
        return text
    parsed = parse_report_text(text)
    used = 0
    out_blocks: list[DocBlock] = []
    for block in parsed.blocks:
        if block.type == "heading":
            out_blocks.append(block)
            continue
        if block.type == "paragraph":
            body = block.text or ""
            para_len = _count_text_chars(body)
            if used + para_len <= max_chars:
                out_blocks.append(block)
                used += para_len
                continue
            remaining = max_chars - used
            if remaining <= 0:
                break
            trimmed = _truncate_to_chars(body, remaining)
            if trimmed:
                out_blocks.append(DocBlock(type="paragraph", text=trimmed))
                used += _count_text_chars(trimmed)
            break
        out_blocks.append(block)
    while out_blocks and out_blocks[-1].type == "heading":
        out_blocks.pop()
    if not out_blocks:
        return text
    return _blocks_to_doc_text(out_blocks)


__all__ = [name for name in globals() if not name.startswith("__")]
