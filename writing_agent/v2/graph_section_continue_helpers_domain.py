"""Section continuation helper primitives."""

from __future__ import annotations

import re
from collections.abc import Callable

_PARA_SENT_END_RE = re.compile(r"[。！？!?；;.:]\s*$")
_PARA_CLOSING_RE = re.compile(r"[”’」』》》】\)\]]+\s*$")
_LIST_LINE_RE = re.compile(
    r"^\s*(?:[-*•·]|\d+[.．、\)]|[一二三四五六七八九十]+[.、\)])\s+"
)
REF_LINE_RE = re.compile(r"^\s*\[\d+\]\s+")

def _escape_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def normalize_section_id(
    section: str,
    *,
    section_token_re: re.Pattern[str],
    encode_section: Callable[[int, str], str],
) -> str:
    value = (section or "").strip()
    if value and section_token_re.match(value):
        return value
    return encode_section(2, value or "section")

def _section_body_len(text: str) -> int:
    return len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", str(text or "")).strip())

def _section_paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n+", str(text or "")) if p.strip()]

def _is_reference_or_list_paragraph(text: str) -> bool:
    token = str(text or "").strip()
    if not token:
        return True
    if token.startswith("[[TABLE:") or token.startswith("[[FIGURE:"):
        return True
    if REF_LINE_RE.match(token):
        return True
    if _LIST_LINE_RE.match(token):
        return True
    return False

def _paragraph_looks_complete(text: str) -> bool:
    token = str(text or "").strip()
    if not token:
        return True
    if _is_reference_or_list_paragraph(token):
        return True
    if _PARA_SENT_END_RE.search(token):
        return True
    m = _PARA_CLOSING_RE.search(token)
    if m:
        core = token[: m.start()].rstrip()
        if _PARA_SENT_END_RE.search(core):
            return True
    return False

def _has_incomplete_paragraph(text: str) -> bool:
    for para in _section_paragraphs(text):
        if not _paragraph_looks_complete(para):
            return True
    return False

def _ensure_paragraph_integrity(text: str) -> str:
    paras = _section_paragraphs(text)
    if not paras:
        return str(text or "").strip()
    out: list[str] = []
    for para in paras:
        token = str(para or "").strip()
        if not token:
            continue
        if _paragraph_looks_complete(token):
            out.append(token)
            continue
        if len(token) <= 24 and out:
            out[-1] = (out[-1].rstrip() + " " + token).strip()
            continue
        suffix = "."
        if re.search(r"[\u4e00-\u9fff]", token):
            suffix = "。"
        out.append(token.rstrip() + suffix)
    return "\n\n".join(out).strip()

def _section_minimum_satisfied(*, text: str, min_paras: int, min_chars: int) -> bool:
    paras = _section_paragraphs(text)
    body_len = _section_body_len(text)
    return (len(paras) >= min_paras) and (min_chars <= 0 or body_len >= min_chars)

__all__ = [name for name in globals() if not name.startswith("__")]
