"""Prompt and brief helpers extracted from graph_aggregate_domain."""

from __future__ import annotations

import re
from typing import Callable

def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[。！？!?])\s*", text)
    return [p for p in parts if p and p.strip()]


def extract_key_points(text: str, *, max_points: int = 3, max_chars: int = 320) -> list[str]:
    src = (text or "").replace("\r", "")
    src = re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", src, flags=re.IGNORECASE)
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", src) if p.strip()]
    points: list[str] = []
    total = 0
    for para in paragraphs:
        for sent in split_sentences(para):
            sentence = sent.strip()
            if not sentence:
                continue
            if len(sentence) > 120:
                sentence = sentence[:120] + "..."
            if total + len(sentence) > max_chars:
                return points
            points.append(sentence)
            total += len(sentence)
            if len(points) >= max_points:
                return points
    return points


def extract_sections_from_text(text: str) -> dict[str, str]:
    src = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", src))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        name = (match.group(1) or "").strip()
        start = match.end()
        if start < len(src) and src[start] == "\n":
            start += 1
        end = matches[i + 1].start() if i + 1 < len(matches) else len(src)
        sections[name] = src[start:end].strip()
    return sections


def _escape_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")



def build_aggregate_brief(
    title: str,
    instruction: str,
    sections: list[str],
    section_text: dict[str, str],
    merged_draft: str,
    *,
    section_level: Callable[[str], int],
    section_title: Callable[[str], str],
) -> str:
    focus_map = extract_sections_from_text(merged_draft)
    brief_lines = [
        f"标题：{title}",
        f"用户要求：{instruction}",
        "",
        "【结论原文】",
        (focus_map.get("结论") or section_text.get("结论") or "").strip(),
        "",
        "【各章节关键要点】",
    ]
    for sec in sections:
        if section_level(sec) > 2:
            continue
        content = (section_text.get(sec) or "").strip()
        points = extract_key_points(content)
        if not points:
            continue
        brief_lines.append(f"- {section_title(sec) or sec}：")
        for point in points:
            brief_lines.append(f"  - {point}")
    return "\n".join([line for line in brief_lines if line is not None]).strip()


