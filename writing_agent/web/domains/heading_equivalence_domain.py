"""Heading Equivalence Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import os
import re
from typing import Callable


HEADING_EQUIV_ALIASES: dict[str, set[str]] = {
    "toc": {"toc", "tableofcontents", "contents", "目录", "目次"},
    "background": {"background", "context", "intro", "introduction", "背景", "研究背景", "项目背景"},
    "current_state": {"currentstate", "currentphase", "statusquo", "当前状态", "当前阶段", "当前状态当前阶段", "现状"},
    "method": {"method", "methods", "methodology", "方法", "研究方法", "技术路线"},
    "results": {"results", "result", "findings", "结果", "研究结果", "实验结果"},
    "recommendations": {"recommendations", "recommendation", "actions", "建议", "推荐", "推荐措施", "改进建议"},
    "conclusion": {"conclusion", "conclusions", "summary", "结论", "总结", "小结"},
    "references": {"references", "reference", "bibliography", "参考文献", "参考资料", "文献"},
}


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def contains_latin(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", str(text or "")))


def preferred_heading_language_is_chinese(text: str) -> bool:
    src = str(text or "")
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", src))
    latin_count = len(re.findall(r"[A-Za-z]", src))
    if cjk_count <= 0:
        return False
    prefer_zh_raw = str(os.environ.get("WRITING_AGENT_EXPORT_PREFER_ZH_HEADINGS", "1")).strip().lower()
    if prefer_zh_raw in {"1", "true", "yes", "on"}:
        return True
    return cjk_count >= latin_count


def strip_cross_language_parenthetical(title: str, *, prefer_chinese: bool) -> str:
    t = str(title or "").strip()
    if not t:
        return t
    m = re.match(r"^(.*?)[\(\uFF08]\s*([^()\uFF08\uFF09]{1,64})\s*[\)\uFF09]\s*$", t)
    if not m:
        return t
    base = str(m.group(1) or "").strip()
    ext = str(m.group(2) or "").strip()
    if not base or not ext:
        return t
    base_has_cjk = contains_cjk(base)
    base_has_latin = contains_latin(base)
    ext_has_cjk = contains_cjk(ext)
    ext_has_latin = contains_latin(ext)
    if prefer_chinese and base_has_cjk and ext_has_latin and not ext_has_cjk:
        return base
    if (not prefer_chinese) and base_has_latin and ext_has_cjk and not ext_has_latin:
        return base
    return t


def heading_alias_token(text: str, *, normalize_heading_text: Callable[[str], str]) -> str:
    norm = normalize_heading_text(text)
    if not norm:
        return ""
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", norm).lower()


def equivalent_heading_key(
    title: str,
    *,
    normalize_heading_text: Callable[[str], str],
    aliases: dict[str, set[str]] | None = None,
) -> str:
    token = heading_alias_token(title, normalize_heading_text=normalize_heading_text)
    if not token:
        return ""
    alias_map = aliases or HEADING_EQUIV_ALIASES
    for key, alias_tokens in alias_map.items():
        if token in alias_tokens:
            return f"eq:{key}"
    return f"raw:{token}"


def parse_toc_entry_line(line: str) -> dict | None:
    raw = str(line or "")
    if not raw.strip():
        return None
    m_num = re.match(r"^(\s*)(\d+)[\.\)\u3001]\s+(.+?)\s*$", raw)
    if m_num:
        return {
            "kind": "numbered",
            "indent": str(m_num.group(1) or ""),
            "num": int(m_num.group(2)),
            "title": str(m_num.group(3) or "").strip(),
        }
    m_bullet = re.match(r"^(\s*)([-*\u2022])\s+(.+?)\s*$", raw)
    if m_bullet:
        return {
            "kind": "bullet",
            "indent": str(m_bullet.group(1) or ""),
            "bullet": str(m_bullet.group(2) or "-"),
            "title": str(m_bullet.group(3) or "").strip(),
        }
    return None


def choose_preferred_heading_title(candidates: list[str], *, prefer_chinese: bool) -> str:
    picked = ""
    for title in candidates:
        if prefer_chinese and contains_cjk(title):
            picked = title
            break
        if (not prefer_chinese) and contains_latin(title):
            picked = title
            break
    if not picked and candidates:
        picked = str(candidates[0] or "").strip()
    return strip_cross_language_parenthetical(picked, prefer_chinese=prefer_chinese)


def dedupe_toc_entries(
    text: str,
    *,
    prefer_chinese: bool,
    split_lines: Callable[[str], list[str]],
    extract_sections: Callable[[str], list[object]],
    equivalent_heading_key: Callable[[str], str],
) -> str:
    lines = split_lines(text)
    sections = extract_sections(text)
    if not sections:
        return text
    changed = False
    for sec in sections:
        if equivalent_heading_key(getattr(sec, "title", "")) != "eq:toc":
            continue
        start = int(getattr(sec, "start", -1)) + 1
        end = int(getattr(sec, "end", -1))
        if start < 0 or end <= start:
            continue
        parsed_rows: list[tuple[int, dict]] = []
        candidates_by_key: dict[str, list[str]] = {}
        for idx in range(start, end):
            parsed = parse_toc_entry_line(lines[idx])
            if not parsed:
                continue
            key = equivalent_heading_key(str(parsed.get("title") or ""))
            if not key:
                continue
            parsed_rows.append((idx, parsed))
            candidates_by_key.setdefault(key, []).append(str(parsed.get("title") or "").strip())
        if not parsed_rows:
            continue
        preferred_by_key: dict[str, str] = {}
        for key, items in candidates_by_key.items():
            preferred_by_key[key] = choose_preferred_heading_title(items, prefer_chinese=prefer_chinese)
        seen: set[str] = set()
        next_num = 1
        drop_idxs: set[int] = set()
        replace_map: dict[int, str] = {}
        for idx, parsed in parsed_rows:
            key = equivalent_heading_key(str(parsed.get("title") or ""))
            if not key:
                continue
            if key in seen:
                drop_idxs.add(idx)
                changed = True
                continue
            seen.add(key)
            title = preferred_by_key.get(key) or str(parsed.get("title") or "").strip()
            kind = str(parsed.get("kind") or "")
            if kind == "numbered":
                line = f"{parsed.get('indent', '')}{next_num}. {title}"
                next_num += 1
            elif kind == "bullet":
                line = f"{parsed.get('indent', '')}{parsed.get('bullet', '-')} {title}"
            else:
                continue
            if line != lines[idx]:
                replace_map[idx] = line
                changed = True
        if not drop_idxs and not replace_map:
            continue
        new_block: list[str] = []
        for idx in range(start, end):
            if idx in drop_idxs:
                continue
            new_block.append(replace_map.get(idx, lines[idx]))
        lines[start:end] = new_block
        break
    if not changed:
        return text
    return "\n".join(lines).strip()


def dedupe_equivalent_headings(
    text: str,
    *,
    split_lines: Callable[[str], list[str]],
    heading_num_prefix: Callable[[str], tuple[str, str]],
    equivalent_heading_key: Callable[[str], str],
    prefer_heading_language_is_chinese: Callable[[str], bool],
    choose_preferred_heading_title: Callable[[list[str], bool], str],
    dedupe_toc_entries: Callable[[str, bool], str],
) -> str:
    src = str(text or "").strip()
    if not src:
        return src
    lines = split_lines(src)
    entries: list[dict] = []
    for idx, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not m:
            continue
        title = str(m.group(2) or "").strip()
        if not title:
            continue
        key = equivalent_heading_key(title)
        if not key:
            continue
        entries.append(
            {
                "idx": idx,
                "prefix": str(m.group(1) or "##"),
                "title": title,
                "key": key,
            }
        )
    if not entries:
        return src
    prefer_chinese = bool(prefer_heading_language_is_chinese(src))
    first_idx_by_key: dict[str, int] = {}
    titles_by_key: dict[str, list[str]] = {}
    for row in entries:
        key = str(row.get("key") or "")
        if key not in first_idx_by_key:
            first_idx_by_key[key] = int(row.get("idx") or 0)
        titles_by_key.setdefault(key, []).append(str(row.get("title") or "").strip())
    preferred_title_by_key: dict[str, str] = {}
    for key, candidates in titles_by_key.items():
        preferred_title_by_key[key] = choose_preferred_heading_title(candidates, prefer_chinese)
    changed = False
    seen: set[str] = set()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not m:
            out.append(line)
            i += 1
            continue
        title = str(m.group(2) or "").strip()
        key = equivalent_heading_key(title)
        if not key:
            out.append(line)
            i += 1
            continue
        first_idx = first_idx_by_key.get(key, i)
        if key in seen and i != first_idx:
            changed = True
            i += 1
            if i < len(lines) and not lines[i].strip():
                i += 1
            continue
        seen.add(key)
        preferred_title = preferred_title_by_key.get(key) or title
        base_prefix, _ = heading_num_prefix(title)
        pick_prefix, pick_body = heading_num_prefix(preferred_title)
        final_title = preferred_title
        if base_prefix and not pick_prefix:
            final_title = f"{base_prefix} {pick_body or preferred_title}".strip()
        elif pick_prefix and not base_prefix:
            final_title = pick_body or preferred_title
        if final_title != title:
            changed = True
        out.append(f"{m.group(1)} {final_title}")
        i += 1
    merged = "\n".join(out).strip()
    merged = dedupe_toc_entries(merged, prefer_chinese)
    if not changed and merged == src:
        return src
    return merged
