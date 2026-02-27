"""Checkpoint Store module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class CheckpointStore:
    """Chapter-level checkpoint persistence for resume/retry/replay."""

    def __init__(self, root: Path | str = ".data/graph_checkpoints") -> None:
        self.root = Path(root)

    def _path(self, run_id: str) -> Path:
        safe = "".join(ch for ch in str(run_id) if ch.isalnum() or ch in {"-", "_"}) or "run"
        return self.root / f"{safe}.json"

    def load(self, run_id: str) -> dict[str, Any] | None:
        path = self._path(run_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save(self, run_id: str, state: dict[str, Any], events: list[dict[str, Any]]) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": str(run_id),
            "saved_at": time.time(),
            "state": state,
            "events": events,
            "schema_version": str((state or {}).get("schema_version") or "1.0"),
        }
        path = self._path(run_id)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def append_event(self, run_id: str, event: dict[str, Any]) -> Path:
        raw = self.load(run_id) or {
            "run_id": str(run_id),
            "saved_at": time.time(),
            "state": {},
            "events": [],
            "schema_version": "1.0",
        }
        events = raw.get("events") if isinstance(raw.get("events"), list) else []
        events.append(dict(event or {}))
        return self.save(run_id, dict(raw.get("state") or {}), events)
