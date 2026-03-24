"""Section postprocess application helper."""

from __future__ import annotations

import os
import re
from collections.abc import Callable

from writing_agent.v2 import graph_section_postprocess_format_domain as format_domain
from writing_agent.v2 import graph_section_postprocess_residue_domain as residue_domain

_looks_like_prompt_residue = residue_domain._looks_like_prompt_residue
_normalize_paragraph_signature = residue_domain._normalize_paragraph_signature
_near_duplicate_signature = residue_domain._near_duplicate_signature
_normalize_media_markers = format_domain._normalize_media_markers

def postprocess_section(
    section: str,
    txt: str,
    *,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    section_title: Callable[[str], str],
    is_reference_section: Callable[[str], bool],
    format_references: Callable[[str], str],
    strip_reference_like_lines: Callable[[str], str],
    strip_inline_headings: Callable[[str, str], str],
    generic_fill_paragraph: Callable[[str, int], str],
    sanitize_output_text: Callable[[str], str],
    ensure_media_markers: Callable[[str, str, int, int], str],
) -> str:
    value = (txt or "").replace("\r", "").strip()
    sec_title = (section_title(section) or "").strip()
    if is_reference_section(sec_title):
        value = format_references(value)
    else:
        value = strip_reference_like_lines(value)
        value = strip_inline_headings(value, sec_title)
    bullet_re = re.compile(r"^\s*[\u2022\u00B7]\s+")
    lines = [ln.strip() for ln in value.splitlines()]
    has_bullets = any(bullet_re.match(ln) for ln in lines if ln)
    if has_bullets:
        paras: list[str] = []
        buf: list[str] = []
        for line in lines:
            if not line:
                if buf:
                    paras.append(" ".join(buf).strip())
                    buf = []
                continue
            if bullet_re.match(line):
                if buf:
                    paras.append(" ".join(buf).strip())
                    buf = []
                paras.append(line.strip())
                continue
            buf.append(line)
        if buf:
            paras.append(" ".join(buf).strip())
    else:
        paras = [p.strip() for p in re.split(r"\n\s*\n+", value) if p.strip()]
        paras = [re.sub(r"\s*\n+\s*", " ", p).strip() for p in paras if p.strip()]
    if len(paras) <= 1 and len(value) >= 420:
        parts = [p.strip() for p in re.split(r"(?<=[。！？!?；;:.])\s*", " ".join(paras) or value) if p.strip()]
        if len(parts) >= 6:
            chunked: list[str] = []
            buf: list[str] = []
            for part in parts:
                buf.append(part)
                if len("".join(buf)) >= 180:
                    chunked.append("".join(buf).strip())
                    buf = []
            if buf:
                chunked.append("".join(buf).strip())
            paras = [p for p in chunked if p]

    deduped_paras: list[str] = []
    seen_norm: set[str] = set()
    signatures: list[str] = []
    for para in paras:
        norm = re.sub(r"\s+", " ", str(para or "")).strip()
        if not norm:
            continue
        if _looks_like_prompt_residue(norm):
            continue
        if norm in seen_norm:
            continue
        sig = _normalize_paragraph_signature(norm)
        if any(_near_duplicate_signature(sig, prev) for prev in signatures):
            continue
        # Guard against fabricated metric claims without citation support.
        if re.search(r"(提高|提升|降低|减少|增长|下降)\s*\d{1,3}(?:\.\d+)?\s*%", norm):
            has_citation = bool(re.search(r"\[\d+\]", norm))
            has_table_fig_ref = ("表" in norm) or ("图" in norm) or ("TABLE" in norm) or ("FIGURE" in norm)
            if (not has_citation) and (not has_table_fig_ref):
                continue
        seen_norm.add(norm)
        if sig:
            signatures.append(sig)
        deduped_paras.append(str(para or "").strip())
    paras = deduped_paras

    joined = "\n\n".join(paras)
    if min_chars > 0:
        body_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", joined).strip())

    if max_chars > 0:
        hard_max_mode = os.environ.get("WRITING_AGENT_HARD_MAX", "0").strip() in {"1", "true", "yes"}
        if hard_max_mode:
            body_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", joined).strip())
            if body_len > max_chars:
                trimmed: list[str] = []
                cur = 0
                for para in paras:
                    next_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", para).strip())
                    if cur + next_len <= max_chars or not trimmed:
                        trimmed.append(para)
                        cur += next_len
                    else:
                        break
                joined = "\n\n".join(trimmed)
                body_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", joined).strip())
                if body_len > max_chars:
                    joined = joined[:max_chars].rsplit("\n", 1)[0].strip()
    joined = sanitize_output_text(joined).strip()
    joined = ensure_media_markers(joined, sec_title, min_tables, min_figures)
    joined = _normalize_media_markers(joined, section_title=sec_title)
    return joined.strip()

__all__ = [name for name in globals() if not name.startswith('__')]
