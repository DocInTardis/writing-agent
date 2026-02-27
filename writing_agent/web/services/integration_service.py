"""Integration Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from writing_agent.web.contracts import WebhookEvent


class IntegrationService:
    def __init__(self, *, event_log: str | Path = ".data/integration/event_bus.jsonl") -> None:
        self._event_log = Path(event_log)

    def publish_event(self, event: WebhookEvent) -> dict[str, Any]:
        payload = event.model_dump()
        payload["published_at"] = time.time()
        self._event_log.parent.mkdir(parents=True, exist_ok=True)
        with self._event_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return {"ok": 1, "event": payload}

    def list_events(self, *, limit: int = 50, tenant_id: str = "") -> dict[str, Any]:
        lim = max(1, min(500, int(limit)))
        rows: list[dict[str, Any]] = []
        if self._event_log.exists():
            for raw in self._event_log.read_text(encoding="utf-8", errors="ignore").splitlines()[-lim * 4 :]:
                try:
                    item = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(item, dict):
                    continue
                if tenant_id and str(item.get("tenant_id") or "") != tenant_id:
                    continue
                rows.append(item)
        rows = rows[-lim:]
        return {"ok": 1, "items": rows, "total": len(rows)}
