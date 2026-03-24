#!/usr/bin/env python3
"""Shared helpers for operational report scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return None


def load_json_dict(path: Path) -> dict[str, Any]:
    raw = load_json(path)
    return raw if isinstance(raw, dict) else {}


def load_json_dict_or_none(path: Path) -> dict[str, Any] | None:
    raw = load_json(path)
    return raw if isinstance(raw, dict) else None


def latest_report(pattern: str, *, root: Path | None = None) -> Path | None:
    base = root if root is not None else Path(".")
    rows = sorted(base.glob(pattern), key=lambda path: path.stat().st_mtime if path.exists() else 0.0)
    if not rows:
        return None
    return rows[-1]


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def normalize_events(raw: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if isinstance(raw, dict):
        events = raw.get("events")
        if isinstance(events, list):
            return [row for row in events if isinstance(row, dict)]
    return []


def latest_text_field(events: list[dict[str, Any]], key: str) -> str:
    target = str(key or "").strip()
    if not target:
        return ""
    for row in reversed(events):
        text = str((row if isinstance(row, dict) else {}).get(target) or "").strip()
        if text:
            return text
    return ""
