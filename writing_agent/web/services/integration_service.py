"""Integration Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from writing_agent.bounded_jsonl import append_bounded_jsonl, read_recent_jsonl
from writing_agent.web.contracts import WebhookEvent


class IntegrationService:
    def __init__(self, *, event_log: str | Path | None = None, max_bytes: int = 2 * 1024 * 1024) -> None:
        data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", "").strip() or ".data")
        self._event_log = Path(event_log) if event_log is not None else data_dir / "integration" / "event_bus.jsonl"
        self._max_bytes = max(1, int(max_bytes))

    def publish_event(self, event: WebhookEvent) -> dict[str, Any]:
        payload = event.model_dump()
        payload["published_at"] = time.time()
        if not append_bounded_jsonl(self._event_log, payload, max_bytes=self._max_bytes):
            raise OSError("integration event could not be persisted")
        return {"ok": 1, "event": payload}

    def list_events(self, *, limit: int = 50, tenant_id: str = "") -> dict[str, Any]:
        lim = max(1, min(500, int(limit)))
        rows: list[dict[str, Any]] = []
        for item in read_recent_jsonl(self._event_log, max_bytes=self._max_bytes, limit=lim * 4):
            if tenant_id and str(item.get("tenant_id") or "") != tenant_id:
                continue
            rows.append(item)
        rows = rows[-lim:]
        return {"ok": 1, "items": rows, "total": len(rows)}
