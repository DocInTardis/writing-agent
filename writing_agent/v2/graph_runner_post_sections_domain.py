"""Section token and outline helpers for graph runner post domain."""

from __future__ import annotations

import re

from writing_agent.v2 import graph_plan_domain


_DISALLOWED_SECTIONS = {"鐩綍", "Table of Contents", "Contents"}
_ACK_SECTIONS = {"鑷磋阿", "楦ｈ阿"}
_META_PHRASES = [
    "\u4e0b\u9762\u662f",
    "\u4ee5\u4e0b\u662f",
    "\u6839\u636e\u4f60\u7684\u8981\u6c42",
    "\u6839\u636e\u60a8\u7684\u8981\u6c42",
    "\u751f\u6210\u7ed3\u679c\u5982\u4e0b",
    "\u8f93\u51fa\u5982\u4e0b",
]
_SECTION_TOKEN_RE = re.compile(r"^H([23])::(.*)$")


def _strip_chapter_prefix_local(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^\u7b2c\s*\d+\s*\u7ae0\s*", "", s)
    s = re.sub(r"^\d+(?:\.\d+)*\s*", "", s)
    return s.strip()

def _clean_section_title(title: str) -> str:
    return graph_plan_domain.clean_section_title(
        title,
        strip_chapter_prefix_local=_strip_chapter_prefix_local,
    )

def _sanitize_planned_sections(sections: list[str]) -> list[str]:
    banned = {"\u76ee\u5f55", "Table of Contents", "Contents", "\u5efa\u8bae", "\u9644\u5f55"}
    out: list[str] = []
    seen: set[str] = set()
    for s in sections or []:
        title = _clean_section_title(str(s or ""))
        if not title:
            continue
        if title in banned:
            continue
        if title in _ACK_SECTIONS:
            continue
        if title in _DISALLOWED_SECTIONS:
            continue
        if title in seen:
            continue
        seen.add(title)
        out.append(title)
    # ensure references last
    refs = [t for t in out if _is_reference_section(t)]
    out = [t for t in out if not _is_reference_section(t)]
    if refs:
        out.append("\u53c2\u8003\u6587\u732e")
    else:
        out.append("\u53c2\u8003\u6587\u732e")
    return out


def _strip_chapter_prefix_local(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^\u7b2c\s*\d+\s*\u7ae0\s*", "", s)
    s = re.sub(r"^\d+(?:\.\d+)*\s*", "", s)
    return s.strip()


def _clean_section_title(title: str) -> str:
    return graph_plan_domain.clean_section_title(
        title,
        strip_chapter_prefix_local=_strip_chapter_prefix_local,
    )


def _sanitize_planned_sections(sections: list[str]) -> list[str]:
    banned = {"\u76ee\u5f55", "Table of Contents", "Contents", "\u5efa\u8bae", "\u9644\u5f55"}
    out: list[str] = []
    seen: set[str] = set()
    for s in sections or []:
        title = _clean_section_title(str(s or ""))
        if not title:
            continue
        if title in banned:
            continue
        if title in _ACK_SECTIONS:
            continue
        if title in _DISALLOWED_SECTIONS:
            continue
        if title in seen:
            continue
        seen.add(title)
        out.append(title)
    # ensure references last
    refs = [t for t in out if _is_reference_section(t)]
    out = [t for t in out if not _is_reference_section(t)]
    if refs:
        out.append("\u53c2\u8003\u6587\u732e")
    else:
        out.append("\u53c2\u8003\u6587\u732e")
    return out


def _is_reference_section(title: str) -> bool:
    t = (title or "").strip().lower()
    if not t:
        return False
    return ("\u53c2\u8003\u6587\u732e" in t) or ("\u53c2\u8003\u8d44\u6599" in t) or (t == "\u6587\u732e") or ("references" in t)


def _encode_section(level: int, title: str) -> str:
    lvl = 2 if int(level or 2) <= 2 else 3
    return f"H{lvl}::{(title or '').strip()}"


def _split_section_token(section: str) -> tuple[int, str]:
    m = _SECTION_TOKEN_RE.match((section or "").strip())
    if m:
        return int(m.group(1)), (m.group(2) or "").strip()
    return 2, (section or "").strip()


def _section_title(section: str) -> str:
    return _split_section_token(section)[1]


def _sections_from_outline(outline: list[tuple[int, str]], *, expand: bool) -> tuple[list[str], list[str]]:
    items = [(int(lvl), str(txt).strip()) for lvl, txt in (outline or []) if str(txt).strip()]
    if not items:
        return [], []
    has_non_reference_h1 = any(lvl == 1 and not _is_reference_section(str(txt or "")) for lvl, txt in items)
    sections: list[str] = []
    chapters: list[str] = []
    seen: set[tuple[int, str]] = set()
    for lvl, txt in items:
        if lvl == 1:
            chapters.append(txt)
            key = (2, txt)
            if key not in seen:
                sections.append(_encode_section(2, txt))
                seen.add(key)
        elif lvl == 2:
            if has_non_reference_h1:
                if expand:
                    key = (3, txt)
                    if key not in seen:
                        sections.append(_encode_section(3, txt))
                        seen.add(key)
                else:
                    continue
            else:
                chapters.append(txt)
                key = (2, txt)
                if key not in seen:
                    sections.append(_encode_section(2, txt))
                    seen.add(key)
    return sections, chapters


def _map_section_parents(sections: list[str]) -> dict[str, str]:
    parent_map: dict[str, str] = {}
    current_parent = ""
    for sec in sections:
        level, title = _split_section_token(sec)
        if not title:
            continue
        if level <= 2:
            current_parent = title
            continue
        if level >= 3 and current_parent:
            parent_map[sec] = current_parent
    return parent_map


def _merge_sections_text(title: str, sections: list[str], section_text: dict[str, str]) -> str:
    if not sections:
        sections = [
            "\u5f15\u8a00",
            "\u76f8\u5173\u7814\u7a76",
            "\u65b9\u6cd5\u8bbe\u8ba1",
            "\u5b9e\u9a8c\u4e0e\u5206\u6790",
            "\u7ed3\u8bba",
            "\u53c2\u8003\u6587\u732e",
        ]
    out = [f"# {title}"]
    for sec in sections:
        level, heading = _split_section_token(sec)
        prefix = "##" if level <= 2 else "###"
        out.append(f"{prefix} {heading}")
        content = (section_text.get(sec) or "").strip()
        out.append(content)
    return "\n\n".join(out).strip() + "\n"



__all__ = [name for name in globals() if not name.startswith("__")]
