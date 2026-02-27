"""Tool Registry module.

This module belongs to `writing_agent.llm` in the writing-agent codebase.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[[dict[str, Any]], Any]] = {}

    def register(self, name: str, fn: Callable[[dict[str, Any]], Any]) -> None:
        key = str(name or "").strip()
        if not key:
            raise ValueError("tool name required")
        self._tools[key] = fn

    def get(self, name: str) -> Callable[[dict[str, Any]], Any] | None:
        return self._tools.get(str(name or "").strip())

    def as_dict(self) -> dict[str, Callable[[dict[str, Any]], Any]]:
        return dict(self._tools)


def load_tool_manifest(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("tool manifest must be json object")
    tools = raw.get("tools")
    if not isinstance(tools, list):
        raise ValueError("tool manifest missing tools list")
    return raw
