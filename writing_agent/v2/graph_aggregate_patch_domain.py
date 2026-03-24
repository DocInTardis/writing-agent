"""Patch application helpers extracted from graph_aggregate_domain."""

from __future__ import annotations

import json
import re
from typing import Callable

from writing_agent.v2.doc_format import DocBlock, ParsedDoc, parse_report_text

def extract_section_from_parsed(parsed: ParsedDoc, name: str) -> str:
    cur = None
    buf: list[DocBlock] = []
    for block in parsed.blocks:
        if block.type == "heading" and int(block.level or 0) == 2:
            cur = (block.text or "").strip()
            continue
        if cur == name:
            buf.append(block)
    if not buf:
        return ""
    return blocks_to_text(buf)


def blocks_to_text(blocks: list[DocBlock]) -> str:
    out: list[str] = []
    for block in blocks:
        if block.type == "paragraph":
            text = (block.text or "").strip()
            if text:
                out.append(text)
        elif block.type == "table":
            out.append("[[TABLE:{}]]".format(json.dumps(block.table or {}, ensure_ascii=False)))
        elif block.type == "figure":
            out.append("[[FIGURE:{}]]".format(json.dumps(block.figure or {}, ensure_ascii=False)))
    return "\n\n".join(out).strip()


def extract_transitions(
    patch_text: str,
    sections: list[str],
    *,
    section_title: Callable[[str], str],
) -> dict[str, str]:
    transitions: dict[str, str] = {}
    if not patch_text:
        return transitions
    allowed = {section_title(section) or section for section in sections if section}
    for line in patch_text.splitlines():
        m = re.match(r"^\s*[-*]?\s*([^>]+?)\s*->\s*([^:：]+?)[:：]\s*(.+)$", line)
        if not m:
            continue
        frm = m.group(1).strip()
        to = m.group(2).strip()
        text = m.group(3).strip()
        if not text or frm not in allowed or to not in allowed:
            continue
        transitions[frm] = text
    return transitions


def apply_section_updates(base_text: str, updates: dict[str, str], transitions: dict[str, str]) -> str:
    src = (base_text or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", src))
    if not matches:
        return base_text
    out: list[str] = []
    cursor = 0
    for i, match in enumerate(matches):
        name = (match.group(1) or "").strip()
        content_start = match.end()
        if content_start < len(src) and src[content_start] == "\n":
            content_start += 1
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(src)
        out.append(src[cursor:content_start])
        body = src[content_start:content_end]
        body_text = body.strip()
        if name in updates:
            body_text = updates[name].strip()
        if name in transitions:
            trans = transitions[name].strip()
            if trans:
                body_text = (body_text + "\n\n" + trans).strip() if body_text else trans
        out.append(body_text + ("\n\n" if body_text else ""))
        cursor = content_end
    out.append(src[cursor:])
    return "".join(out).strip() + "\n"


def apply_aggregate_patch(
    base_text: str,
    patch_text: str,
    sections: list[str],
    *,
    section_title: Callable[[str], str],
) -> str:
    if not patch_text.strip():
        return base_text
    parsed = parse_report_text(patch_text)
    conclusion_text = extract_section_from_parsed(parsed, "结论")
    transitions = extract_transitions(patch_text, sections, section_title=section_title)
    updates: dict[str, str] = {}
    if conclusion_text:
        updates["结论"] = conclusion_text
    if not updates and not transitions:
        return base_text
    return apply_section_updates(base_text, updates, transitions)


