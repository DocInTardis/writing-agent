"""Doc format parsing marker and text helpers."""

from __future__ import annotations

import json
import re
import time

from writing_agent.v2 import doc_format_parse_heading_domain as heading_domain

_MARKER_RE = heading_domain._MARKER_RE
_INLINE_MARKER_RE = heading_domain._INLINE_MARKER_RE
_STRUCTURED_MARKER_START_RE = heading_domain._STRUCTURED_MARKER_START_RE

def _scan_json_object_end(src: str, brace_start: int) -> int:
    depth = 0
    in_string = False
    escape = False
    for idx in range(brace_start, len(src)):
        ch = src[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _repair_fragmented_structured_markers(text: str) -> str:
    src = str(text or "")
    if "[[" not in src:
        return src
    out: list[str] = []
    pos = 0
    while True:
        match = _STRUCTURED_MARKER_START_RE.search(src, pos)
        if not match:
            out.append(src[pos:])
            break
        out.append(src[pos:match.start()])
        brace_start = src.find("{", match.end())
        if brace_start < 0:
            out.append(src[match.start():])
            break
        brace_end = _scan_json_object_end(src, brace_start)
        if brace_end < 0:
            out.append(src[match.start():])
            break
        close = src.find("]]", brace_end)
        if close < 0:
            out.append(src[match.start():])
            break
        kind = str(match.group(1) or "FIGURE").upper()
        payload = src[brace_start : brace_end + 1].strip()
        try:
            payload = json.dumps(json.loads(payload), ensure_ascii=False)
        except Exception:
            payload = re.sub(r"\s*[\r\n]+\s*", "", payload)
        out.append(f"[[{kind}:{payload}]]")
        pos = close + 2
    return "".join(out)


def _normalize_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        if len(run) >= 4:
            out.append("".join(run))
        else:
            out.extend(run)
        run.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            out.append("")
            continue
        single = len(line) <= 1
        looks_like_char = re.search(r"[\u4e00-\u9fa5A-Za-z0-9\.\-\u3000-\u303F]", line)
        if single and looks_like_char:
            run.append(line)
            continue
        flush()
        out.append(raw)
    flush()
    return out


def _default_title() -> str:
    stamp = time.strftime("%Y%m%d-%H%M")
    return f"\u81ea\u52a8\u751f\u6210\u6587\u6863-{stamp}"


def _strip_inline_markers(text: str) -> str:
    return _INLINE_MARKER_RE.sub("", text or "").strip()


def _derive_title_from_blocks(blocks: list[object]) -> str:
    for b in blocks:
        if b.type == "heading" and (b.level or 0) >= 1 and (b.text or "").strip():
            return _strip_inline_markers(b.text or "")
        if b.type == "paragraph" and (b.text or "").strip():
            raw = _strip_inline_markers(b.text or "")
            if raw:
                return raw[:24].rstrip()
    return ""


def _safe_json_loads(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        return None



def _join_text(blocks: list[DocBlock]) -> str:
    out: list[str] = []
    for b in blocks:
        if b.type == "heading":
            level = b.level or 1
            out.append(f"{'#' * level} {(b.text or '').strip()}")
        elif b.type == "paragraph":
            out.append((b.text or "").strip())
        elif b.type == "table":
            out.append("[[TABLE:{}]]".format(json.dumps(b.table or {}, ensure_ascii=False)))
        elif b.type == "figure":
            out.append("[[FIGURE:{}]]".format(json.dumps(b.figure or {}, ensure_ascii=False)))
    return "\n\n".join([s for s in out if s])


def _strip_headings(s: str) -> str:
    return re.sub(r"(?m)^#{1,3}\s+.*?$", "", s or "")


def _strip_markers(s: str) -> str:
    stripped = re.sub(_MARKER_RE, "", s or "")
    return re.sub(_INLINE_MARKER_RE, "", stripped)

__all__ = [name for name in globals() if not name.startswith("__")]
