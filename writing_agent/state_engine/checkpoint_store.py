"""Checkpoint Store module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class CheckpointStore:
    """Chapter-level checkpoint persistence for resume/retry/replay."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else Path(os.environ.get("WRITING_AGENT_DATA_DIR", ".data")) / "graph_checkpoints"

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
        path = self._path(run_id)
        existing = self.load(run_id)
        if isinstance(existing, dict) and existing.get("state") == state and existing.get("events") == events:
            return path
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": str(run_id),
            "saved_at": time.time(),
            "state": state,
            "events": events,
            "schema_version": str((state or {}).get("schema_version") or "1.0"),
        }
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        fd, temporary = tempfile.mkstemp(prefix=".checkpoint-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(serialized)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
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
