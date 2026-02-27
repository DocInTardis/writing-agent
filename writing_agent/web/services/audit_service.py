"""Audit Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any


class AuditService:
    """Append-only audit trail with hash-chain signatures."""

    def __init__(self, *, path: str | Path = ".data/audit/app_audit_chain.ndjson", secret: str = "") -> None:
        self.path = Path(path)
        self.secret = str(secret or "")

    def append(self, *, actor: str, action: str, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        prev_hash = self._last_hash()
        event = {
            "ts": time.time(),
            "actor": str(actor or "system"),
            "action": str(action or "unknown"),
            "tenant_id": str(tenant_id or "default"),
            "payload": dict(payload or {}),
            "prev_hash": prev_hash,
        }
        body = json.dumps(event, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()
        event["hash"] = digest
        if self.secret:
            event["signature"] = hmac.new(self.secret.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def _last_hash(self) -> str:
        if not self.path.exists():
            return ""
        lines = self.path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for raw in reversed(lines):
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict) and row.get("hash"):
                return str(row.get("hash"))
        return ""
