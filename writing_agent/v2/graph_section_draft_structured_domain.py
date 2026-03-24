"""Structured payload parsing helpers extracted from graph_section_draft_domain."""

from __future__ import annotations

import json
import re


def parse_structured_payload(payload) -> list[dict]:
    if isinstance(payload, dict):
        if isinstance(payload.get("blocks"), list):
            return [b for b in payload.get("blocks") if isinstance(b, dict)]
        if any(k in payload for k in ("text", "items", "type", "block_id", "id")):
            return [payload]
    if isinstance(payload, list):
        return [b for b in payload if isinstance(b, dict)]
    return []


def parse_structured_line(line: str) -> list[dict]:
    value = (line or "").strip()
    if not value or value.startswith("```"):
        return []
    try:
        payload = json.loads(value)
    except Exception:
        return []
    return parse_structured_payload(payload)


def _strip_code_fence(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if value.startswith("```"):
        value = re.sub(r"^\s*```[a-zA-Z0-9_-]*\s*", "", value)
        value = re.sub(r"\s*```\s*$", "", value)
    return value.strip()


def _try_parse_structured_blob(blob: str) -> list[dict]:
    raw = _strip_code_fence(blob)
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception:
        payload = None
    if payload is not None:
        rows = parse_structured_payload(payload)
        if rows:
            return rows
    for left, right in [("{", "}"), ("[", "]")]:
        s = raw.find(left)
        e = raw.rfind(right)
        if s >= 0 and e > s:
            snippet = raw[s : e + 1].strip()
            try:
                payload = json.loads(snippet)
            except Exception:
                continue
            rows = parse_structured_payload(payload)
            if rows:
                return rows
    return []


def _decode_fragment(token_raw: str) -> str:
    if re.search(r"\\(?:u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|[nrt])", token_raw):
        return token_raw.encode("utf-8", "ignore").decode("unicode_escape", errors="ignore").strip()
    return token_raw.strip()


def _extract_text_like_payload(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    key_value_re = r'(?i)(?:^|[,{]\s*)"?(?:section_id|block_id|type|items|caption|columns|rows)"?\s*:'
    text_field_re = r'"(?:text|content|paragraph)"\s*:\s*"((?:[^"\\]|\\.)*)"'
    if re.search(key_value_re, value):
        text_fragments = re.findall(text_field_re, value, flags=re.IGNORECASE)
        if text_fragments:
            recovered = [_decode_fragment(str(frag)) for frag in text_fragments]
            recovered = [token for token in recovered if token]
            if recovered:
                return "\n".join(recovered).strip()
        return ""
    fields = re.findall(text_field_re, value, flags=re.IGNORECASE)
    if fields:
        recovered = [_decode_fragment(str(field)) for field in fields]
        recovered = [token for token in recovered if token]
        if recovered:
            return "\n".join(recovered).strip()
    if re.search(r"(?i)(?:section_id|block_id|caption|columns|rows)\s*[:=]", value):
        return ""
    return value


__all__ = [name for name in globals() if not name.startswith("__")]
