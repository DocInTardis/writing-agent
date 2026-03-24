"""Reference and numbering helpers for export structure checks."""

from __future__ import annotations

import re
from datetime import date


_REFERENCE_HEADING_RE = re.compile(
    r"^#{1,3}\s*(?:\u53c2\u8003\u6587\u732e|\u53c2\u8003\u8d44\u6599|references?|bibliography)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_REF_LINE_RE = re.compile(r"^\[(\d+)\]\s*(.+)$")
_REF_LINE_RELAXED_RE = re.compile(r"^\s*\\?\[(\d+)\\?\]\s*(.+)$")
_URL_RE = re.compile(r"https?://[^\s]+", flags=re.IGNORECASE)
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_ACCESS_DATE_RE = re.compile(r"\[(?:19|20)\d{2}-\d{2}-\d{2}\]")
_GBT_TYPE_MARK_RE = re.compile(r"\[(?:M|J|C|N|D|R|S|P|Z|EB/OL|DB/OL|CP/OL|DS/OL)\]", flags=re.IGNORECASE)
_GBT_ONLINE_TYPE_MARK_RE = re.compile(r"\[(?:EB/OL|DB/OL|CP/OL|DS/OL)\]", flags=re.IGNORECASE)


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
            value = value.rstrip(" .;)")
            value = f"{value}[EB/OL]."
    elif (not has_url) and (not has_type):
        value = value.rstrip(" .;)")
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
