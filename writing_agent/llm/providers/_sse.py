"""Shared helpers for UTF-8 safe SSE decoding."""

from __future__ import annotations

from typing import Iterable

import requests


def _decode_sse_line(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = str(raw)
    return text.lstrip("\ufeff").strip()


def _count_cjk(text: str) -> int:
    return sum(1 for ch in str(text or "") if "\u4e00" <= ch <= "\u9fff")


def _count_latin1_noise(text: str) -> int:
    return sum(1 for ch in str(text or "") if 0x80 <= ord(ch) <= 0xFF)


def repair_utf8_mojibake(text: str) -> str:
    src = str(text or "")
    if not src:
        return ""
    if _count_latin1_noise(src) < 2:
        return src
    try:
        repaired = src.encode("latin-1", errors="strict").decode("utf-8")
    except Exception:
        return src
    if _count_cjk(repaired) > _count_cjk(src) and _count_latin1_noise(repaired) < _count_latin1_noise(src):
        return repaired
    return src


def iter_sse_data_lines(resp: requests.Response) -> Iterable[str]:
    resp.encoding = "utf-8"
    for raw in resp.iter_lines(decode_unicode=False):
        line = _decode_sse_line(raw)
        if not line or not line.startswith("data:"):
            continue
        yield line[5:].strip()
