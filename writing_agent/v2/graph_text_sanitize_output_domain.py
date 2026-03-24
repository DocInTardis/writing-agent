"""High-level sanitize output helper."""

from __future__ import annotations

import os
import re
from typing import Callable

from writing_agent.v2 import graph_text_sanitize_core_domain as core_domain
from writing_agent.v2 import graph_text_sanitize_process_domain as process_domain

strip_markdown_noise = core_domain.strip_markdown_noise
strip_chatty_closings = core_domain.strip_chatty_closings
compact_list_spacing = core_domain.compact_list_spacing
normalize_punctuation = core_domain.normalize_punctuation
_dedupe_repeated_sentences = process_domain._dedupe_repeated_sentences
_looks_like_process_line = process_domain._looks_like_process_line
_is_dedup_candidate_line = process_domain._is_dedup_candidate_line
_normalize_global_media_markers = process_domain._normalize_global_media_markers

def sanitize_output_text(
    text: str,
    *,
    meta_phrases: list[str],
    has_cjk: Callable[[str], bool],
    is_mostly_ascii_line: Callable[[str], bool],
    banned_phrases: list[str],
) -> str:
    value = (text or "").replace("\r", "")
    drop_ascii_lines = str(os.environ.get("WRITING_AGENT_DROP_ASCII_LINES", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    value = re.sub(r"\[\s*(?:待补充|todo|tbd)[^\]]*\]", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[（(]\s*(?:待补充|todo|tbd)[^）)]*[）)]", "", value, flags=re.IGNORECASE)
    value = strip_markdown_noise(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("&nbsp;", " ")
    # Collapse in-line CJK spacing without destroying heading/body line breaks.
    value = re.sub(r"(?<=[\u4e00-\u9fff])[ \t\u3000]+(?=[\u4e00-\u9fff])", "", value)
    value = strip_chatty_closings(value, banned_phrases=banned_phrases)

    filtered_lines: list[str] = []
    for line in value.split("\n"):
        if drop_ascii_lines and is_mostly_ascii_line(line) and not has_cjk(line):
            continue
        if re.match(r"^#{1,3}\s*[?？]{2,}\s*$", line):
            line = "## 参考文献"
        elif re.match(r"^[?？]{2,}\s*$", line):
            line = "参考文献"
        filtered_lines.append(line)
    value = "\n".join(filtered_lines)

    for phrase in meta_phrases:
        if phrase:
            value = value.replace(phrase, "")

    value = _normalize_global_media_markers(value)
    value = normalize_punctuation(value)
    value = re.sub(r"[ \t]+", " ", value)
    value = compact_list_spacing(value)

    cleaned_lines: list[str] = []
    seen_line_counts: dict[str, int] = {}
    try:
        max_dup_repeat = max(1, min(3, int(os.environ.get("WRITING_AGENT_MAX_DUP_LINE_REPEAT", "1"))))
    except Exception:
        max_dup_repeat = 1
    for line in value.split("\n"):
        if _looks_like_process_line(line):
            continue
        token = str(line or "").strip()
        if _is_dedup_candidate_line(token):
            count = int(seen_line_counts.get(token, 0))
            if count >= max_dup_repeat:
                continue
            seen_line_counts[token] = count + 1
        cleaned_lines.append(line)
    value = "\n".join(cleaned_lines)
    enable_sentence_dedup = str(os.environ.get("WRITING_AGENT_ENABLE_SENTENCE_DEDUP", "1")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if enable_sentence_dedup:
        value = _dedupe_repeated_sentences(value)

    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()

__all__ = [name for name in globals() if not name.startswith("__")]
