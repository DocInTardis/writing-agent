"""Heading Glue Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from typing import Callable


def fix_section_heading_glue(
    text: str,
    titles: list[str],
    *,
    split_heading_glue: Callable[[str], tuple[str, str] | None],
) -> str:
    if not text:
        return text
    num_prefix_re = re.compile(
        r"^(?P<prefix>(?:\d+(?:\.\d+){0,3}|[一二三四五六七八九十百千万零〇两]+)[\.\uFF0E\u3001\)]?)\s*(?P<body>.+)$"
    )

    def _level_from_prefix(prefix: str) -> str:
        p = str(prefix or "").strip()
        if p and re.match(r"^\d", p):
            return "#" * min(4, 2 + p.count("."))
        return "##"

    def _strip_num_punct(prefix: str) -> str:
        return re.sub(r"[\.\uFF0E\u3001\)]$", "", str(prefix or "").strip())

    def _looks_like_plain_numbered_heading(body: str) -> bool:
        plain = re.sub(r"[\*_`]+", "", str(body or "")).strip()
        if not plain:
            return False
        if re.search(r"[，。！？；：!?]", plain):
            return False
        if len(plain) > 24:
            return False
        if plain.startswith(("负责人", "输入", "输出", "验收标准")):
            return False
        return True

    lines = (text or "").splitlines()
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            out.append(raw)
            continue
        heading_prefix = ""
        content = line
        if line.startswith("#"):
            m = re.match(r"^(#{1,6})\s*(.+)$", line)
            if not m:
                out.append(raw)
                continue
            heading_prefix = m.group(1)
            content = m.group(2).strip()
            split = split_heading_glue(content)
            if split:
                out.append(f"{heading_prefix} {split[0]}")
                if split[1]:
                    out.append(split[1])
                continue

        num_prefix = ""
        title_body = content
        m_num = num_prefix_re.match(content)
        if m_num:
            num_prefix = str(m_num.group("prefix") or "").strip()
            title_body = str(m_num.group("body") or "").strip()
            allow_plain_numbered_heading = bool(heading_prefix)
            if not allow_plain_numbered_heading:
                num_core = _strip_num_punct(num_prefix)
                if num_core and re.search(r"\.", num_core):
                    allow_plain_numbered_heading = True
                elif _looks_like_plain_numbered_heading(title_body):
                    allow_plain_numbered_heading = True
            if allow_plain_numbered_heading:
                split_num = split_heading_glue(title_body)
                if split_num:
                    level = heading_prefix or _level_from_prefix(num_prefix)
                    heading_text = f"{num_prefix} {split_num[0]}".strip()
                    out.append(f"{level} {heading_text}")
                    if split_num[1]:
                        out.append(split_num[1])
                    continue

        if titles:
            matched = ""
            used_title_body = False
            for t in titles:
                if content.startswith(t):
                    matched = t
                    break
                if title_body.startswith(t):
                    matched = t
                    used_title_body = True
                    break
            if matched:
                if not heading_prefix and not num_prefix:
                    out.append(raw)
                    continue
                if num_prefix and not heading_prefix and not _looks_like_plain_numbered_heading(title_body):
                    out.append(raw)
                    continue
                source = title_body if used_title_body else content
                rest = source[len(matched) :].lstrip("：:，,。.;；、-— \t")
                level = heading_prefix or (_level_from_prefix(num_prefix) if num_prefix else "##")
                heading_text = f"{num_prefix} {matched}".strip() if used_title_body and num_prefix else matched
                out.append(f"{level} {heading_text}")
                if rest:
                    out.append(rest)
                continue

        out.append(raw)
    return "\n".join(out).strip()


def maybe_fix_heading_glue(
    text: str,
    titles: list[str],
    *,
    split_heading_glue: Callable[[str], tuple[str, str] | None],
) -> str:
    src = str(text or "").strip()
    if not src:
        return src
    clean_titles = [str(t or "").strip() for t in (titles or []) if str(t or "").strip()]
    if not clean_titles:
        return src
    likely_glued = False
    for line in src.splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        for title in clean_titles:
            if not t.startswith(title):
                continue
            if len(t) <= len(title):
                continue
            nxt = t[len(title)]
            if nxt in {" ", "\t", ":", "-", ";", ",", ".", "?", "!", "。", "，", "；", "："}:
                continue
            likely_glued = True
            break
        if likely_glued:
            break
    if not likely_glued:
        return src
    return fix_section_heading_glue(src, clean_titles, split_heading_glue=split_heading_glue).strip()
