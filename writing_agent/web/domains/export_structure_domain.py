"""Export Structure Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import os
import re
import time
from datetime import date
from typing import Any, Callable

_TOC_HEADING_RE = re.compile(
    r"^#{1,3}\s*(?:\u76ee\u5f55|\u76ee\u6b21|table\s+of\s+contents|contents?)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_REFERENCE_HEADING_RE = re.compile(
    r"^#{1,3}\s*(?:\u53c2\u8003\u6587\u732e|\u53c2\u8003\u8d44\u6599|references?|bibliography)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_ABSTRACT_HEADING_RE = re.compile(
    r"^#{1,3}\s*(?:\u6458\u8981|abstract)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_KEYWORDS_HEADING_RE = re.compile(
    r"^#{1,3}\s*(?:\u5173\u952e\u8bcd|keywords?)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_CITATION_KEY_RE = re.compile(r"\[@([a-zA-Z0-9_-]+)\]")
_REF_LINE_RE = re.compile(r"^\[(\d+)\]\s*(.+)$")
_REF_LINE_RELAXED_RE = re.compile(r"^\s*\\?\[(\d+)\\?\]\s*(.+)$")
_FIGURE_MENTION_RE = re.compile(r"(\u89c1\u56fe\s*\d+|\u5982\u56fe\s*\d+|figure\s*\d+)", flags=re.IGNORECASE)
_TABLE_MENTION_RE = re.compile(r"(\u89c1\u8868\s*\d+|\u5982\u8868\s*\d+|table\s*\d+)", flags=re.IGNORECASE)
_FIGURE_PRESENT_RE = re.compile(r"(\[\[FIGURE:|^\s*\u56fe\s*\d+|^\s*figure\s*\d+)", flags=re.IGNORECASE | re.MULTILINE)
_TABLE_PRESENT_RE = re.compile(r"(\[\[TABLE:|^\s*\u8868\s*\d+|^\s*table\s*\d+)", flags=re.IGNORECASE | re.MULTILINE)
_HEADING_LINE_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
_URL_RE = re.compile(r"https?://[^\s]+", flags=re.IGNORECASE)
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_ACCESS_DATE_RE = re.compile(r"\[(?:19|20)\d{2}-\d{2}-\d{2}\]")
_GBT_TYPE_MARK_RE = re.compile(r"\[(?:M|J|C|N|D|R|S|P|Z|EB/OL|DB/OL|CP/OL|DS/OL)\]", flags=re.IGNORECASE)
_GBT_ONLINE_TYPE_MARK_RE = re.compile(r"\[(?:EB/OL|DB/OL|CP/OL|DS/OL)\]", flags=re.IGNORECASE)

_MSG_MISSING_TOC = "\u7f3a\u5c11\u76ee\u5f55\u7ae0\u8282\u3002"
_MSG_MISSING_REFERENCES = "\u7f3a\u5c11\u53c2\u8003\u6587\u732e\u7ae0\u8282\u3002"
_MSG_REFERENCES_NOT_LAST = "\u53c2\u8003\u6587\u732e\u7ae0\u8282\u5fc5\u987b\u4f4d\u4e8e\u6587\u672b\u3002"
_MSG_HEADING_GLUE = "\u68c0\u6d4b\u5230\u6807\u9898\u7c98\u8fde\u6216\u4e2d\u82f1\u6587\u91cd\u590d\u6807\u9898\u3002"
_MSG_AUTOFIX_APPLIED = (
    "\u5bfc\u51fa\u524d\u5df2\u81ea\u52a8\u4fee\u590d\u76ee\u5f55/\u53c2\u8003\u6587\u732e/\u6807\u9898\u7ed3\u6784\u95ee\u9898\u3002"
)
_MSG_MISSING_ABSTRACT = "\u7f3a\u5c11\u6458\u8981/Abstract \u7ae0\u8282\u3002"
_MSG_MISSING_KEYWORDS = "\u7f3a\u5c11\u5173\u952e\u8bcd/Keywords \u7ae0\u8282\u3002"
_MSG_REFERENCE_EMPTY = "\u53c2\u8003\u6587\u732e\u7ae0\u8282\u4e3a\u7a7a\u6216\u6761\u76ee\u683c\u5f0f\u65e0\u6548\u3002"
_MSG_REFERENCE_TOO_FEW = "\u53c2\u8003\u6587\u732e\u6709\u6548\u6761\u76ee\u8fc7\u5c11\u3002"
_MSG_REFERENCE_DUPLICATED = "\u53c2\u8003\u6587\u732e\u5b58\u5728\u91cd\u590d\u6761\u76ee\u3002"
_MSG_TOC_ENTRIES_MISMATCH = "\u76ee\u5f55\u9879\u4e0e\u6b63\u6587\u7ae0\u8282\u6570\u91cf\u4e0d\u4e00\u81f4\u3002"
_MSG_FIGURE_MENTION_WITHOUT_OBJECT = "\u6587\u4e2d\u63d0\u53ca\u56fe\u4f46\u672a\u68c0\u6d4b\u5230\u56fe\u5bf9\u8c61\u3002"
_MSG_TABLE_MENTION_WITHOUT_OBJECT = "\u6587\u4e2d\u63d0\u53ca\u8868\u4f46\u672a\u68c0\u6d4b\u5230\u8868\u5bf9\u8c61\u3002"
_MSG_CITATION_MISSING_METADATA = (
    "\u6587\u6863\u4e2d\u5b58\u5728\u672a\u767b\u8bb0\u7684\u5f15\u7528\u952e\uff0c\u5bfc\u51fa\u5df2\u963b\u6b62\u3002"
)
_MSG_CITATION_UNVERIFIED = (
    "\u6587\u6863\u4e2d\u5b58\u5728\u672a\u6821\u9a8c\u901a\u8fc7\u7684\u5f15\u7528\uff0c\u5bfc\u51fa\u5df2\u963b\u6b62\u3002"
)
_MSG_CITATION_VERIFY_STALE = (
    "\u5f15\u7528\u6821\u9a8c\u7ed3\u679c\u5df2\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u6821\u9a8c\u540e\u5bfc\u51fa\u3002"
)
_MSG_HEADING_DEPTH_H2_INSUFFICIENT = "\u8bba\u6587\u6b63\u6587\u4e8c\u7ea7\u6807\u9898\uff08H2\uff09\u6570\u91cf\u4e0d\u8db3\u3002"
_MSG_HEADING_DEPTH_H3_INSUFFICIENT = "\u8bba\u6587\u6b63\u6587\u4e09\u7ea7\u6807\u9898\uff08H3\uff09\u6570\u91cf\u4e0d\u8db3\u3002"
_MSG_REFERENCE_NUMBERING_INVALID = "\u53c2\u8003\u6587\u732e\u7f16\u53f7\u4e0d\u8fde\u7eed\u6216\u683c\u5f0f\u5f02\u5e38\u3002"
_MSG_REFERENCE_GBT7714_NONCOMPLIANT = "\u53c2\u8003\u6587\u732e\u4e0d\u7b26\u5408 GB/T 7714 \u5b57\u6bb5\u7ea7\u89c4\u8303\u3002"
_MSG_FIGURE_NUMBERING_INVALID = "\u56fe\u7f16\u53f7\u4e0d\u8fde\u7eed\u6216\u683c\u5f0f\u5f02\u5e38\u3002"
_MSG_TABLE_NUMBERING_INVALID = "\u8868\u7f16\u53f7\u4e0d\u8fde\u7eed\u6216\u683c\u5f0f\u5f02\u5e38\u3002"


def _coerce_optional_bool(value: object) -> bool | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def has_toc_heading(text: str) -> bool:
    src = str(text or "")
    if not src:
        return False
    return bool(_TOC_HEADING_RE.search(src))


def has_reference_heading(text: str) -> bool:
    src = str(text or "")
    if not src:
        return False
    return bool(_REFERENCE_HEADING_RE.search(src))


def has_abstract_heading(text: str) -> bool:
    src = str(text or "")
    if not src:
        return False
    return bool(_ABSTRACT_HEADING_RE.search(src))


def has_keywords_heading(text: str) -> bool:
    src = str(text or "")
    if not src:
        return False
    return bool(_KEYWORDS_HEADING_RE.search(src))


def _collect_markdown_titles(text: str) -> list[str]:
    src = str(text or "")
    if not src:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for line in src.splitlines():
        m = re.match(r"^\s*##\s+(.+?)\s*$", line)
        if not m:
            continue
        title = str(m.group(1) or "").strip()
        if not title:
            continue
        if _TOC_HEADING_RE.match(f"## {title}") or _REFERENCE_HEADING_RE.match(f"## {title}"):
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(title)
    return out


def _extract_toc_entries(text: str) -> list[str]:
    src = str(text or "")
    if not src:
        return []
    lines = src.splitlines()
    toc_start = -1
    for i, line in enumerate(lines):
        if _TOC_HEADING_RE.match(str(line or "").strip()):
            toc_start = i + 1
            break
    if toc_start < 0:
        return []
    out: list[str] = []
    for line in lines[toc_start:]:
        row = str(line or "").strip()
        if not row:
            continue
        if row.startswith("#"):
            break
        m = re.match(r"^\d+[.\u3001\)]\s*(.+)$", row)
        if m:
            title = str(m.group(1) or "").strip()
            if title:
                out.append(title)
    return out


def extract_reference_items(text: str) -> list[str]:
    src = str(text or "")
    if not src:
        return []
    lines = src.splitlines()
    start = -1
    for i, line in enumerate(lines):
        if _REFERENCE_HEADING_RE.match(str(line or "").strip()):
            start = i + 1
            break
    if start < 0:
        return []
    end = len(lines)
    for i in range(start, len(lines)):
        if re.match(r"^\s*#{1,3}\s+.+$", str(lines[i] or "").strip()):
            end = i
            break
    items: list[str] = []
    cur = ""
    for raw in lines[start:end]:
        row = str(raw or "").strip()
        if not row:
            continue
        m = _REF_LINE_RE.match(row)
        if m:
            if cur.strip():
                items.append(cur.strip())
            cur = str(m.group(2) or "").strip()
            continue
        if cur:
            cur = (cur + " " + row).strip()
        elif items:
            items[-1] = (items[-1] + " " + row).strip()
        else:
            cur = row
    if cur.strip():
        items.append(cur.strip())
    return items


def _reference_unique_count(items: list[str]) -> tuple[int, int]:
    seen: set[str] = set()
    unique = 0
    dup = 0
    for item in items:
        key = re.sub(r"\s+", " ", str(item or "").strip().lower())
        if not key:
            continue
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        unique += 1
    return unique, dup


def _looks_academic_document(session: Any, text: str) -> bool:
    src = str(text or "")
    compact_len = len(re.sub(r"\s+", "", src))
    if compact_len >= 1600:
        return True
    prefs = getattr(session, "generation_prefs", None)
    purpose = ""
    if isinstance(prefs, dict):
        purpose = str(prefs.get("purpose") or "")
    purpose_low = purpose.lower()
    academic_markers = (
        "\u8bba\u6587",
        "\u6bd5\u4e1a",
        "\u5b66\u672f",
        "thesis",
        "paper",
        "dissertation",
        "report",
    )
    return any(marker in purpose_low for marker in academic_markers)


def _resolve_min_reference_count(session: Any) -> int:
    prefs = getattr(session, "generation_prefs", None)
    if isinstance(prefs, dict):
        raw = prefs.get("min_reference_count")
        try:
            value = int(raw)
            if value > 0:
                return min(100, value)
        except Exception:
            pass
    raw_env = str(os.environ.get("WRITING_AGENT_MIN_REFERENCE_COUNT", "8")).strip()
    try:
        return max(1, min(100, int(raw_env)))
    except Exception:
        return 8


def _strict_toc_consistency_enabled(session: Any) -> bool:
    prefs = getattr(session, "generation_prefs", None)
    if isinstance(prefs, dict):
        pref = _coerce_optional_bool(prefs.get("strict_toc_consistency"))
        if pref is not None:
            return pref
    raw = str(os.environ.get("WRITING_AGENT_STRICT_TOC_CONSISTENCY", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _require_text_toc_heading(session: Any) -> bool:
    prefs = getattr(session, "generation_prefs", None)
    if isinstance(prefs, dict):
        pref = _coerce_optional_bool(prefs.get("require_text_toc_heading"))
        if pref is not None:
            return pref
    raw = str(os.environ.get("WRITING_AGENT_REQUIRE_TEXT_TOC_HEADING", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_positive_int_pref(
    session: Any,
    *,
    pref_key: str,
    env_key: str,
    default: int,
    min_value: int = 0,
    max_value: int = 200,
) -> int:
    prefs = getattr(session, "generation_prefs", None)
    if isinstance(prefs, dict):
        raw = prefs.get(pref_key)
        try:
            value = int(raw)
            return max(min_value, min(max_value, value))
        except Exception:
            pass
    raw_env = str(os.environ.get(env_key, str(default))).strip()
    try:
        value = int(raw_env)
        return max(min_value, min(max_value, value))
    except Exception:
        return max(min_value, min(max_value, int(default)))


def _enforce_heading_depth_for_academic(session: Any) -> bool:
    prefs = getattr(session, "generation_prefs", None)
    if isinstance(prefs, dict):
        pref = _coerce_optional_bool(prefs.get("enforce_heading_depth"))
        if pref is not None:
            return pref
    raw = str(os.environ.get("WRITING_AGENT_ENFORCE_HEADING_DEPTH", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _enforce_gbt7714_for_academic(session: Any) -> bool:
    prefs = getattr(session, "generation_prefs", None)
    if isinstance(prefs, dict):
        pref = _coerce_optional_bool(prefs.get("enforce_gbt7714_reference"))
        if pref is not None:
            return pref
    raw = str(os.environ.get("WRITING_AGENT_ENFORCE_GBT7714_REFERENCE", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_min_h2_count(session: Any) -> int:
    return _resolve_positive_int_pref(
        session,
        pref_key="min_h2_count",
        env_key="WRITING_AGENT_MIN_H2_COUNT",
        default=3,
        min_value=0,
        max_value=60,
    )


def _resolve_min_h3_count(session: Any) -> int:
    return _resolve_positive_int_pref(
        session,
        pref_key="min_h3_count",
        env_key="WRITING_AGENT_MIN_H3_COUNT",
        default=1,
        min_value=0,
        max_value=60,
    )


def _reference_section_bounds(lines: list[str]) -> tuple[int, int]:
    start = -1
    for i, line in enumerate(lines):
        if _REFERENCE_HEADING_RE.match(str(line or "").strip()):
            start = i + 1
            break
    if start < 0:
        return -1, -1
    end = len(lines)
    for i in range(start, len(lines)):
        if re.match(r"^\s*#{1,3}\s+.+$", str(lines[i] or "").strip()):
            end = i
            break
    return start, end


def _reference_section_lines(text: str) -> list[str]:
    lines = str(text or "").splitlines()
    start, end = _reference_section_bounds(lines)
    if start < 0:
        return []
    return lines[start:end]


def _collect_non_special_heading_depth_counts(text: str) -> dict[int, int]:
    counts: dict[int, int] = {2: 0, 3: 0}
    for raw in str(text or "").splitlines():
        m = _HEADING_LINE_RE.match(str(raw or "").rstrip())
        if not m:
            continue
        level = len(str(m.group(1) or ""))
        title = str(m.group(2) or "").strip()
        if not title:
            continue
        if level not in {2, 3}:
            continue
        # Exclude structural wrappers from depth statistics.
        probe = f"## {title}"
        if _TOC_HEADING_RE.match(probe) or _REFERENCE_HEADING_RE.match(probe):
            continue
        if _ABSTRACT_HEADING_RE.match(probe) or _KEYWORDS_HEADING_RE.match(probe):
            continue
        counts[level] = counts.get(level, 0) + 1
    return counts


def _reference_numbering_is_sequential(text: str) -> tuple[bool, dict]:
    rows = _reference_section_lines(text)
    numbers: list[int] = []
    nonempty = 0
    for raw in rows:
        row = str(raw or "").strip()
        if not row:
            continue
        nonempty += 1
        m = _REF_LINE_RELAXED_RE.match(row)
        if m:
            try:
                numbers.append(int(m.group(1)))
            except Exception:
                pass
    if nonempty <= 0:
        return True, {"numbers": [], "expected": []}
    if not numbers:
        return False, {"numbers": [], "expected": []}
    expected = list(range(1, len(numbers) + 1))
    return numbers == expected, {"numbers": numbers, "expected": expected}


def _series_numbering_is_sequential(values: list[int]) -> tuple[bool, dict]:
    if not values:
        return True, {"numbers": [], "expected": []}
    uniq = sorted(set(int(x) for x in values if int(x) > 0))
    if not uniq:
        return True, {"numbers": [], "expected": []}
    expected = list(range(uniq[0], uniq[0] + len(uniq)))
    return uniq == expected, {"numbers": uniq, "expected": expected}


def _figure_numbering_is_sequential(text: str) -> tuple[bool, dict]:
    src = str(text or "")
    nums = [int(x) for x in re.findall(r"(?mi)^\s*(?:\u56fe|figure)\s*(\d+)", src)]
    return _series_numbering_is_sequential(nums)


def _table_numbering_is_sequential(text: str) -> tuple[bool, dict]:
    src = str(text or "")
    nums = [int(x) for x in re.findall(r"(?mi)^\s*(?:\u8868|table)\s*(\d+)", src)]
    return _series_numbering_is_sequential(nums)


def _normalize_reference_body_for_gbt7714(body: str, *, today: str) -> str:
    value = re.sub(r"\s+", " ", str(body or "").strip())
    if not value:
        return value
    has_url = bool(_URL_RE.search(value))
    has_type = bool(_GBT_TYPE_MARK_RE.search(value))
    if has_url:
        if _GBT_ONLINE_TYPE_MARK_RE.search(value):
            pass
        elif has_type:
            value = _GBT_TYPE_MARK_RE.sub("[EB/OL]", value, count=1)
        else:
            value = value.rstrip(" .;；。")
            value = f"{value}[EB/OL]."
    elif (not has_url) and (not has_type):
        value = value.rstrip(" .;；。")
        value = f"{value}[J]."
    if has_url and not _ACCESS_DATE_RE.search(value):
        value = _URL_RE.sub(lambda m: f"[{today}] {m.group(0)}", value, count=1)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_reference_section_for_gbt7714(text: str) -> str:
    src = str(text or "").strip()
    if not src:
        return src
    lines = src.splitlines()
    start, end = _reference_section_bounds(lines)
    if start < 0:
        return src
    today = date.today().strftime("%Y-%m-%d")
    normalized_rows: list[str] = []
    index = 1
    for raw in lines[start:end]:
        row = str(raw or "").strip()
        if not row:
            continue
        row = row.replace("\\[", "[").replace("\\]", "]")
        m = _REF_LINE_RELAXED_RE.match(row)
        body = str(m.group(2) if m else row).strip()
        if not body:
            continue
        body = _normalize_reference_body_for_gbt7714(body, today=today)
        if not body:
            continue
        normalized_rows.append(f"[{index}] {body}")
        index += 1
    if not normalized_rows:
        return src
    rebuilt = list(lines[:start]) + [""] + normalized_rows + [""] + list(lines[end:])
    return "\n".join(rebuilt).strip()


def _gbt7714_reference_violations(items: list[str]) -> list[dict]:
    problems: list[dict] = []
    for idx, raw in enumerate(items, start=1):
        row = re.sub(r"\s+", " ", str(raw or "").strip())
        if not row:
            problems.append({"index": idx, "reasons": ["empty_item"]})
            continue
        reasons: list[str] = []
        has_url = bool(_URL_RE.search(row))
        if not _GBT_TYPE_MARK_RE.search(row):
            reasons.append("missing_type_marker")
        if not _YEAR_RE.search(row):
            reasons.append("missing_year")
        if has_url and not _ACCESS_DATE_RE.search(row):
            reasons.append("missing_access_date")
        if has_url and not _GBT_ONLINE_TYPE_MARK_RE.search(row):
            reasons.append("online_type_marker_missing")
        if reasons:
            problems.append({"index": idx, "reasons": reasons})
    return problems


def collect_toc_titles(
    text: str,
    *,
    extract_sections: Callable[..., list[Any]],
    is_reference_section: Callable[[str], bool],
) -> list[str]:
    sections = extract_sections(text, prefer_levels=(2, 3))
    out: list[str] = []
    seen: set[str] = set()
    for sec in sections:
        title = str(getattr(sec, "title", "") or "").strip()
        if not title:
            continue
        if is_reference_section(title):
            continue
        if has_toc_heading(f"## {title}"):
            continue
        norm = title.lower()
        if norm in seen:
            continue
        seen.add(norm)
        out.append(title)
    # Fallback to direct markdown heading scan when parser output is sparse.
    if len(out) < 2:
        for title in _collect_markdown_titles(text):
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(title)
    return out


def ensure_toc_section(
    text: str,
    *,
    extract_sections: Callable[..., list[Any]],
    is_reference_section: Callable[[str], bool],
    split_lines: Callable[[str], list[str]],
) -> str:
    src = str(text or "").strip()
    if not src or has_toc_heading(src):
        return src
    titles = collect_toc_titles(
        src,
        extract_sections=extract_sections,
        is_reference_section=is_reference_section,
    )
    if len(titles) < 1:
        return src
    lines = split_lines(src)
    insert_idx = 0
    if lines and re.match(r"^#\s+.+", lines[0].strip()):
        insert_idx = 1
        while insert_idx < len(lines) and not lines[insert_idx].strip():
            insert_idx += 1
    toc_lines = ["## \u76ee\u5f55", ""] + [f"{idx}. {title}" for idx, title in enumerate(titles, start=1)] + [""]
    lines[insert_idx:insert_idx] = toc_lines
    return "\n".join(lines).strip()


def reference_lines_from_session(
    session: Any,
    *,
    citation_style_from_session: Callable[[Any], Any],
    format_reference: Callable[[Any, Any], str],
) -> list[str]:
    if session is None:
        return []
    citations = session.citations if isinstance(getattr(session, "citations", None), dict) else {}
    if not citations:
        return []
    style = citation_style_from_session(session)
    out: list[str] = []
    for idx, key in enumerate(citations.keys(), start=1):
        cite = citations.get(key)
        try:
            body = format_reference(cite, style) if cite else f"{key} (citation metadata missing)"
        except Exception:
            body = str(getattr(cite, "title", "") or key)
        out.append(f"[{idx}] {body}")
    return out


def ensure_reference_section(
    text: str,
    session: Any,
    *,
    has_reference_heading_fn: Callable[[str], bool],
    reference_lines_from_session_fn: Callable[[Any], list[str]],
    insert_reference_section: Callable[[str, list[str]], str],
) -> str:
    src = str(text or "").strip()
    if not src or has_reference_heading_fn(src):
        return src
    ref_lines = reference_lines_from_session_fn(session)
    if not ref_lines:
        return src
    return insert_reference_section(src, ref_lines)


def reference_section_last(
    text: str,
    *,
    extract_sections: Callable[..., list[Any]],
    is_reference_section: Callable[[str], bool],
) -> bool:
    sections = extract_sections(text, prefer_levels=(1, 2, 3))
    if not sections:
        return True
    ref_idx = -1
    for i, sec in enumerate(sections):
        if is_reference_section(str(getattr(sec, "title", "") or "")):
            ref_idx = i
            break
    if ref_idx < 0:
        return False
    return ref_idx == (len(sections) - 1)


def move_reference_section_to_end(
    text: str,
    *,
    extract_sections: Callable[..., list[Any]],
    is_reference_section: Callable[[str], bool],
    apply_move_section_op: Callable[..., str],
) -> str:
    sections = extract_sections(text, prefer_levels=(1, 2, 3))
    if len(sections) <= 1:
        return text
    ref = None
    for sec in sections:
        if is_reference_section(str(getattr(sec, "title", "") or "")):
            ref = sec
            break
    if ref is None:
        return text
    if getattr(sections[-1], "start", -1) == getattr(ref, "start", -2) and getattr(sections[-1], "end", -1) == getattr(ref, "end", -2):
        return text
    anchor = sections[-1]
    try:
        return apply_move_section_op(
            text,
            str(getattr(ref, "title", "") or ""),
            str(getattr(anchor, "title", "") or ""),
            position="after",
        )
    except Exception:
        return text


def extract_citation_keys_from_text(text: str) -> list[str]:
    src = str(text or "")
    if not src:
        return []
    return sorted(set(_CITATION_KEY_RE.findall(src)))


def has_reference_requirement(
    session: Any,
    text: str,
    *,
    has_reference_heading_fn: Callable[[str], bool],
    reference_lines_from_session_fn: Callable[[Any], list[str]],
) -> bool:
    src = str(text or "")
    if not src:
        return False
    if has_reference_heading_fn(src):
        return True
    if extract_citation_keys_from_text(src):
        return True
    return bool(reference_lines_from_session_fn(session))


def citation_export_issues(
    session: Any,
    text: str,
    *,
    strict_citation_verify_enabled: Callable[[Any], bool],
    get_internal_pref: Callable[[Any, str, Any], Any],
    citation_verify_key: str,
    allow_possible_citation_status: Callable[[Any], bool],
) -> list[dict]:
    if not strict_citation_verify_enabled(session):
        return []

    cite_keys = extract_citation_keys_from_text(text)
    if not cite_keys:
        return []

    citations = session.citations if isinstance(getattr(session, "citations", None), dict) else {}
    verify_raw = get_internal_pref(session, citation_verify_key, {}) or {}
    verify_obj = verify_raw if isinstance(verify_raw, dict) else {}
    verify_items = verify_obj.get("items") if isinstance(verify_obj.get("items"), dict) else {}
    updated_at = float(verify_obj.get("updated_at") or 0.0)

    max_age_h_raw = os.environ.get("WRITING_AGENT_CITATION_VERIFY_MAX_AGE_H", "168").strip()
    try:
        max_age_h = max(1.0, float(max_age_h_raw))
    except Exception:
        max_age_h = 168.0

    is_stale = updated_at <= 0 or (time.time() - updated_at) > max_age_h * 3600.0
    allow_possible = allow_possible_citation_status(session)

    missing_meta: list[str] = []
    unverified: list[str] = []
    for key in cite_keys:
        if key not in citations:
            missing_meta.append(key)
            continue
        row = verify_items.get(key) if isinstance(verify_items, dict) else None
        status = str(row.get("status") or "") if isinstance(row, dict) else ""
        if status == "verified":
            continue
        if allow_possible and status == "possible":
            continue
        unverified.append(key)

    issues: list[dict] = []
    if missing_meta:
        issues.append(
            {
                "code": "citation_missing_metadata",
                "message": _MSG_CITATION_MISSING_METADATA,
                "blocking": True,
                "keys": missing_meta,
            }
        )
    if unverified:
        issues.append(
            {
                "code": "citation_unverified",
                "message": _MSG_CITATION_UNVERIFIED,
                "blocking": True,
                "keys": unverified,
            }
        )
    if not issues and is_stale:
        issues.append(
            {
                "code": "citation_verify_stale",
                "message": _MSG_CITATION_VERIFY_STALE,
                "blocking": True,
                "keys": cite_keys,
            }
        )
    return issues


def export_quality_report(
    session: Any,
    text: str,
    *,
    auto_fix: bool,
    export_gate_policy: Callable[[Any], str],
    strict_doc_format_enabled: Callable[[Any], bool],
    has_reference_requirement_fn: Callable[[Any, str], bool],
    normalize_export_text: Callable[..., str],
    ensure_toc_section_fn: Callable[[str], str],
    ensure_reference_section_fn: Callable[[str, Any], str],
    move_reference_section_to_end_fn: Callable[[str], str],
    has_toc_heading_fn: Callable[[str], bool],
    has_reference_heading_fn: Callable[[str], bool],
    reference_section_last_fn: Callable[[str], bool],
    citation_export_issues_fn: Callable[[Any, str], list[dict]],
) -> dict:
    policy = export_gate_policy(session)
    src = str(text or "").strip()
    fixed = src
    issues: list[dict] = []
    warnings: list[dict] = []

    strict_doc_format = strict_doc_format_enabled(session)
    if strict_doc_format and fixed:
        before = fixed
        require_references = has_reference_requirement_fn(session, fixed)
        require_text_toc = _require_text_toc_heading(session)
        academic_like = _looks_academic_document(session, fixed)
        if auto_fix:
            fixed = normalize_export_text(fixed, session=session)
            if require_text_toc:
                fixed = ensure_toc_section_fn(fixed)
            if require_references:
                fixed = ensure_reference_section_fn(fixed, session)
                fixed = move_reference_section_to_end_fn(fixed)
            if academic_like and _enforce_gbt7714_for_academic(session):
                fixed = _normalize_reference_section_for_gbt7714(fixed)
            fixed = normalize_export_text(fixed, session=session)
            require_references = has_reference_requirement_fn(session, fixed)
        if require_text_toc and not has_toc_heading_fn(fixed):
            issues.append({"code": "missing_toc", "message": _MSG_MISSING_TOC, "blocking": True})
        if require_text_toc and has_toc_heading_fn(fixed) and _strict_toc_consistency_enabled(session):
            toc_entries = _extract_toc_entries(fixed)
            body_titles = _collect_markdown_titles(fixed)
            if len(body_titles) >= 3 and len(toc_entries) < max(2, len(body_titles) - 1):
                issues.append({"code": "toc_entries_mismatch", "message": _MSG_TOC_ENTRIES_MISMATCH, "blocking": True})
        if require_references and not has_reference_heading_fn(fixed):
            issues.append({"code": "missing_references", "message": _MSG_MISSING_REFERENCES, "blocking": True})
        if require_references and has_reference_heading_fn(fixed) and not reference_section_last_fn(fixed):
            issues.append({"code": "references_not_last", "message": _MSG_REFERENCES_NOT_LAST, "blocking": True})
        if academic_like:
            if _enforce_heading_depth_for_academic(session):
                depth_counts = _collect_non_special_heading_depth_counts(fixed)
                min_h2 = _resolve_min_h2_count(session)
                min_h3 = _resolve_min_h3_count(session)
                h2_count = int(depth_counts.get(2, 0))
                h3_count = int(depth_counts.get(3, 0))
                if h2_count < min_h2:
                    issues.append(
                        {
                            "code": "heading_depth_h2_insufficient",
                            "message": _MSG_HEADING_DEPTH_H2_INSUFFICIENT,
                            "blocking": True,
                            "meta": {"count": h2_count, "min_required": min_h2},
                        }
                    )
                if h3_count < min_h3:
                    issues.append(
                        {
                            "code": "heading_depth_h3_insufficient",
                            "message": _MSG_HEADING_DEPTH_H3_INSUFFICIENT,
                            "blocking": True,
                            "meta": {"count": h3_count, "min_required": min_h3},
                        }
                    )
            if not has_abstract_heading(fixed):
                issues.append({"code": "missing_abstract", "message": _MSG_MISSING_ABSTRACT, "blocking": True})
            if not has_keywords_heading(fixed):
                issues.append({"code": "missing_keywords", "message": _MSG_MISSING_KEYWORDS, "blocking": True})
            # If references are present in academic content, enforce minimum and uniqueness.
            if has_reference_heading_fn(fixed):
                numbering_ok, numbering_meta = _reference_numbering_is_sequential(fixed)
                if not numbering_ok:
                    issues.append(
                        {
                            "code": "reference_numbering_invalid",
                            "message": _MSG_REFERENCE_NUMBERING_INVALID,
                            "blocking": True,
                            "meta": numbering_meta,
                        }
                    )
                ref_items = extract_reference_items(fixed)
                if not ref_items:
                    issues.append({"code": "reference_empty", "message": _MSG_REFERENCE_EMPTY, "blocking": True})
                else:
                    unique_count, dup_count = _reference_unique_count(ref_items)
                    min_refs = _resolve_min_reference_count(session)
                    if unique_count < min_refs:
                        issues.append(
                            {
                                "code": "reference_too_few",
                                "message": _MSG_REFERENCE_TOO_FEW,
                                "blocking": True,
                                "meta": {"unique_count": unique_count, "min_required": min_refs},
                            }
                        )
                    if dup_count > 0:
                        issues.append(
                            {
                                "code": "reference_duplicated",
                                "message": _MSG_REFERENCE_DUPLICATED,
                                "blocking": True,
                                "meta": {"duplicate_count": dup_count},
                            }
                        )
                    if _enforce_gbt7714_for_academic(session):
                        gbt_violations = _gbt7714_reference_violations(ref_items)
                        if gbt_violations:
                            issues.append(
                                {
                                    "code": "reference_gbt7714_noncompliant",
                                    "message": _MSG_REFERENCE_GBT7714_NONCOMPLIANT,
                                    "blocking": True,
                                    "meta": {
                                        "violation_count": len(gbt_violations),
                                        "sample": gbt_violations[:5],
                                    },
                                }
                            )
            if _FIGURE_MENTION_RE.search(fixed) and not _FIGURE_PRESENT_RE.search(fixed):
                issues.append(
                    {
                        "code": "figure_mention_without_object",
                        "message": _MSG_FIGURE_MENTION_WITHOUT_OBJECT,
                        "blocking": True,
                    }
                )
            if _TABLE_MENTION_RE.search(fixed) and not _TABLE_PRESENT_RE.search(fixed):
                issues.append(
                    {
                        "code": "table_mention_without_object",
                        "message": _MSG_TABLE_MENTION_WITHOUT_OBJECT,
                        "blocking": True,
                    }
                )
            fig_ok, fig_meta = _figure_numbering_is_sequential(fixed)
            if not fig_ok:
                issues.append(
                    {
                        "code": "figure_numbering_invalid",
                        "message": _MSG_FIGURE_NUMBERING_INVALID,
                        "blocking": True,
                        "meta": fig_meta,
                    }
                )
            table_ok, table_meta = _table_numbering_is_sequential(fixed)
            if not table_ok:
                issues.append(
                    {
                        "code": "table_numbering_invalid",
                        "message": _MSG_TABLE_NUMBERING_INVALID,
                        "blocking": True,
                        "meta": table_meta,
                    }
                )
        probe = normalize_export_text(fixed, session=session)
        if probe != fixed:
            issues.append({"code": "heading_glue", "message": _MSG_HEADING_GLUE, "blocking": True})
        if auto_fix and before != fixed:
            warnings.append({"code": "autofix_applied", "message": _MSG_AUTOFIX_APPLIED})

    issues.extend(citation_export_issues_fn(session, fixed or src))

    normalized_issues: list[dict] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        is_blocking = bool(row.get("blocking", True))
        if policy != "strict":
            if policy == "warn" and is_blocking:
                warnings.append(
                    {
                        "code": "policy_warn",
                        "from": str(row.get("code") or ""),
                        "message": str(row.get("message") or row.get("code") or "export issue"),
                    }
                )
            row["blocking"] = False
        else:
            row["blocking"] = is_blocking
        normalized_issues.append(row)

    can_export = True if policy in {"warn", "off"} else not any(bool(x.get("blocking", True)) for x in normalized_issues)
    return {
        "policy": policy,
        "can_export": can_export,
        "issues": normalized_issues,
        "warnings": warnings,
        "fixed_text": fixed if auto_fix else "",
    }
