"""Section Edit Ops Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class SectionSpan:
    level: int
    title: str
    start: int
    end: int


def split_lines(text: str) -> list[str]:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def extract_sections(text: str, *, prefer_levels: tuple[int, ...] = (2, 3)) -> list[SectionSpan]:
    lines = split_lines(text)
    raw: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        if not title:
            continue
        raw.append((i, level, title))
    use = [h for h in raw if h[1] in prefer_levels]
    if not use:
        use = raw
    out: list[SectionSpan] = []
    for idx, (start, level, title) in enumerate(use):
        end = use[idx + 1][0] if idx + 1 < len(use) else len(lines)
        out.append(SectionSpan(level=level, title=title, start=start, end=end))
    return out


def find_section(
    sections: list[SectionSpan],
    title: str,
    *,
    normalize_heading_text: Callable[[str], str],
) -> SectionSpan | None:
    target = normalize_heading_text(title)
    if not target:
        return None
    for sec in sections:
        if normalize_heading_text(sec.title) == target:
            return sec
    for sec in sections:
        norm = normalize_heading_text(sec.title)
        if target in norm or norm in target:
            return sec
    return None


def find_section_by_index(text: str, index: int) -> SectionSpan | None:
    if index <= 0:
        return None
    sections = extract_sections(text, prefer_levels=(2,))
    if not sections:
        sections = extract_sections(text, prefer_levels=(1, 2, 3))
    if 0 < index <= len(sections):
        return sections[index - 1]
    return None


def insert_block(lines: list[str], idx: int, block: list[str]) -> None:
    if idx < 0:
        idx = 0
    if idx > len(lines):
        idx = len(lines)
    insert_data = list(block)
    if idx > 0 and lines[idx - 1].strip() and insert_data and insert_data[0].strip():
        insert_data = [""] + insert_data
    lines[idx:idx] = insert_data


def apply_set_title(
    text: str,
    title: str,
    *,
    apply_title_change: Callable[[str, str], str],
) -> str:
    return apply_title_change(text, title)


def apply_replace_text(text: str, old: str, new: str, *, replace_all: bool = False) -> str:
    if not old:
        return text
    return (text or "").replace(old, new) if replace_all else (text or "").replace(old, new, 1)


def apply_rename_section(
    text: str,
    old_title: str,
    new_title: str,
    *,
    normalize_heading_text: Callable[[str], str],
) -> str:
    lines = split_lines(text)
    sections = extract_sections(text)
    sec = find_section(sections, old_title, normalize_heading_text=normalize_heading_text)
    if not sec:
        return text
    line = lines[sec.start]
    m = re.match(r"^(#+)\s+", line)
    prefix = m.group(1) if m else "##"
    lines[sec.start] = f"{prefix} {new_title}"
    return "\n".join(lines).strip()


def apply_add_section_op(
    text: str,
    title: str,
    *,
    anchor: str | None = None,
    position: str = "after",
    level: int | None = None,
    normalize_heading_text: Callable[[str], str],
) -> str:
    lines = split_lines(text)
    sections = extract_sections(text)
    anchor_sec = find_section(sections, anchor, normalize_heading_text=normalize_heading_text) if anchor else None
    if anchor_sec:
        insert_idx = anchor_sec.end if position == "after" else anchor_sec.start
        level = level or max(2, anchor_sec.level)
    else:
        ref_sec = find_section(sections, "references", normalize_heading_text=normalize_heading_text) or find_section(
            sections,
            "bibliography",
            normalize_heading_text=normalize_heading_text,
        )
        insert_idx = ref_sec.start if ref_sec else len(lines)
        level = level or 2
    heading = f"{'#' * level} {title}"
    block = [heading, ""]
    insert_block(lines, insert_idx, block)
    return "\n".join(lines).strip()


def apply_delete_section_op(
    text: str,
    *,
    title: str | None = None,
    index: int | None = None,
    normalize_heading_text: Callable[[str], str],
) -> str:
    lines = split_lines(text)
    sec = None
    if index:
        sec = find_section_by_index(text, index)
    if sec is None and title:
        sections = extract_sections(text)
        sec = find_section(sections, title, normalize_heading_text=normalize_heading_text)
    if not sec:
        return text
    del lines[sec.start : sec.end]
    if sec.start > 0 and sec.start < len(lines):
        if not lines[sec.start - 1].strip() and not lines[sec.start].strip():
            del lines[sec.start]
    return "\n".join(lines).strip()


def apply_move_section_op(
    text: str,
    title: str,
    anchor: str,
    *,
    position: str = "after",
    normalize_heading_text: Callable[[str], str],
) -> str:
    lines = split_lines(text)
    sections = extract_sections(text)
    src = find_section(sections, title, normalize_heading_text=normalize_heading_text)
    if not src:
        return text
    block = lines[src.start : src.end]
    del lines[src.start : src.end]
    rebuilt = "\n".join(lines)
    sections = extract_sections(rebuilt)
    anchor_sec = find_section(sections, anchor, normalize_heading_text=normalize_heading_text)
    insert_idx = len(lines)
    if anchor_sec:
        insert_idx = anchor_sec.end if position == "after" else anchor_sec.start
    insert_block(lines, insert_idx, block)
    return "\n".join(lines).strip()


def apply_replace_section_content_op(
    text: str,
    title: str,
    content: str,
    *,
    normalize_heading_text: Callable[[str], str],
) -> str:
    lines = split_lines(text)
    sections = extract_sections(text)
    sec = find_section(sections, title, normalize_heading_text=normalize_heading_text)
    if not sec:
        return text
    content_lines = split_lines(str(content or ""))
    while content_lines and not content_lines[0].strip():
        content_lines.pop(0)
    while content_lines and not content_lines[-1].strip():
        content_lines.pop()
    block: list[str] = []
    if content_lines:
        if content_lines[0].strip():
            block.append("")
        block.extend(content_lines)
        block.append("")
    rebuilt = lines[: sec.start + 1] + block + lines[sec.end :]
    return "\n".join(rebuilt).strip()


def apply_append_section_content_op(
    text: str,
    title: str,
    content: str,
    *,
    normalize_heading_text: Callable[[str], str],
) -> str:
    content_lines = split_lines(str(content or ""))
    while content_lines and not content_lines[0].strip():
        content_lines.pop(0)
    while content_lines and not content_lines[-1].strip():
        content_lines.pop()
    if not content_lines:
        return text
    lines = split_lines(text)
    sections = extract_sections(text)
    sec = find_section(sections, title, normalize_heading_text=normalize_heading_text)
    if not sec:
        return text
    insert_idx = sec.end
    insert_block(lines, insert_idx, content_lines)
    return "\n".join(lines).strip()


def apply_merge_sections_op(
    text: str,
    first: str,
    second: str,
    *,
    normalize_heading_text: Callable[[str], str],
) -> str:
    lines = split_lines(text)
    sections = extract_sections(text)
    sec_second = find_section(sections, second, normalize_heading_text=normalize_heading_text)
    sec_first = find_section(sections, first, normalize_heading_text=normalize_heading_text)
    if not sec_first or not sec_second or sec_first.start == sec_second.start:
        return text
    content_second = lines[sec_second.start + 1 : sec_second.end]
    del lines[sec_second.start : sec_second.end]
    rebuilt = "\n".join(lines)
    sections = extract_sections(rebuilt)
    sec_first = find_section(sections, first, normalize_heading_text=normalize_heading_text)
    if not sec_first:
        return text
    insert_at = sec_first.end
    block: list[str] = []
    if insert_at > 0 and lines[insert_at - 1].strip():
        block.append("")
    block.extend(content_second)
    lines[insert_at:insert_at] = block
    return "\n".join(lines).strip()


def apply_swap_sections_op(
    text: str,
    first: str,
    second: str,
    *,
    normalize_heading_text: Callable[[str], str],
) -> str:
    lines = split_lines(text)
    sections = extract_sections(text)
    sec_a = find_section(sections, first, normalize_heading_text=normalize_heading_text)
    sec_b = find_section(sections, second, normalize_heading_text=normalize_heading_text)
    if not sec_a or not sec_b or sec_a.start == sec_b.start:
        return text
    if sec_a.start > sec_b.start:
        sec_a, sec_b = sec_b, sec_a
    block_a = lines[sec_a.start : sec_a.end]
    block_b = lines[sec_b.start : sec_b.end]
    middle = lines[sec_a.end : sec_b.start]
    rebuilt = lines[: sec_a.start] + block_b + middle + block_a + lines[sec_b.end :]
    return "\n".join(rebuilt).strip()


def split_paragraphs(lines: list[str]) -> list[list[str]]:
    paras: list[list[str]] = []
    buf: list[str] = []
    for line in lines:
        if line.strip():
            buf.append(line)
        else:
            if buf:
                paras.append(buf)
                buf = []
    if buf:
        paras.append(buf)
    return paras


def apply_split_section_op(
    text: str,
    title: str,
    new_titles: list[str],
    *,
    normalize_heading_text: Callable[[str], str],
) -> str:
    if not new_titles:
        return text
    lines = split_lines(text)
    sections = extract_sections(text)
    sec = find_section(sections, title, normalize_heading_text=normalize_heading_text)
    if not sec:
        return text
    level = sec.level
    content_lines = lines[sec.start + 1 : sec.end]
    paragraphs = split_paragraphs(content_lines)
    n = len(new_titles)
    groups: list[list[str]] = [[] for _ in range(n)]
    if paragraphs:
        chunk = max(1, int(math.ceil(len(paragraphs) / n)))
        for i in range(n):
            chunk_paras = paragraphs[i * chunk : (i + 1) * chunk]
            block: list[str] = []
            for para in chunk_paras:
                if block:
                    block.append("")
                block.extend(para)
            groups[i] = block
    new_blocks: list[str] = []
    for i, sub_title in enumerate(new_titles):
        heading = f"{'#' * level} {sub_title}"
        new_blocks.append(heading)
        if groups[i]:
            new_blocks.extend(groups[i])
        new_blocks.append("")
    while new_blocks and not new_blocks[-1].strip():
        new_blocks.pop()
    rebuilt = lines[: sec.start] + new_blocks + lines[sec.end :]
    return "\n".join(rebuilt).strip()


def match_section_index(
    sections: list[SectionSpan],
    title: str,
    used: set[int],
    *,
    normalize_heading_text: Callable[[str], str],
) -> int | None:
    target = normalize_heading_text(title)
    for idx, sec in enumerate(sections):
        if idx in used:
            continue
        if normalize_heading_text(sec.title) == target:
            return idx
    for idx, sec in enumerate(sections):
        if idx in used:
            continue
        norm = normalize_heading_text(sec.title)
        if target in norm or norm in target:
            return idx
    return None


def apply_reorder_sections_op(
    text: str,
    order: list[str],
    *,
    normalize_heading_text: Callable[[str], str],
) -> str:
    if not order:
        return text
    lines = split_lines(text)
    sections = extract_sections(text, prefer_levels=(2,))
    if not sections:
        sections = extract_sections(text, prefer_levels=(1, 2, 3))
    if not sections:
        return text
    blocks = [lines[s.start : s.end] for s in sections]
    used: set[int] = set()
    order_idx: list[int] = []
    for title in order:
        idx = match_section_index(sections, title, used, normalize_heading_text=normalize_heading_text)
        if idx is not None:
            used.add(idx)
            order_idx.append(idx)
    remaining = [i for i in range(len(sections)) if i not in used]
    new_blocks = [blocks[i] for i in order_idx] + [blocks[i] for i in remaining]
    prefix = lines[: sections[0].start]
    suffix = lines[sections[-1].end :]
    merged: list[str] = []
    for block in new_blocks:
        if merged and merged[-1].strip() and block and block[0].strip():
            merged.append("")
        merged.extend(block)
    rebuilt = prefix + merged + suffix
    return "\n".join(rebuilt).strip()
