"""Idempotency module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class IdempotencyStore:
    def __init__(self, root: str | Path = ".data/idempotency") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()
        return self.root / f"{digest}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def put(self, key: str, payload: dict[str, Any]) -> None:
        path = self._path(key)
        body = {
            "key": key,
            "saved_at": time.time(),
            "payload": payload,
        }
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")


def make_idempotency_key(*, doc_id: str, route: str, body: dict[str, Any]) -> str:
    raw = json.dumps({"doc_id": doc_id, "route": route, "body": body}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()
