"""Idempotency module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


class IdempotencyStore:
    """Local idempotency cache backed by JSON files.

    Cleanup strategy (Redis-like, but file-based):
    1) Lazy expiration on `get`: expired item is removed when accessed.
    2) Active sweep on `put`: periodically remove expired/corrupt files.
    3) Size cap eviction: keep newest N items, delete older ones.
    """

    def __init__(
        self,
        root: str | Path = ".data/idempotency",
        *,
        ttl_s: float | None = None,
        max_entries: int | None = None,
        sweep_interval_s: float | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        # <=0 means disabled.
        self.ttl_s = max(0.0, float(ttl_s if ttl_s is not None else self._float_env("WRITING_AGENT_IDEMPOTENCY_TTL_S", 6 * 3600)))
        self.max_entries = max(0, int(max_entries if max_entries is not None else self._int_env("WRITING_AGENT_IDEMPOTENCY_MAX_ENTRIES", 2000)))
        self.sweep_interval_s = max(
            0.0,
            float(
                sweep_interval_s
                if sweep_interval_s is not None
                else self._float_env("WRITING_AGENT_IDEMPOTENCY_SWEEP_INTERVAL_S", 60.0)
            ),
        )
        self._next_cleanup_at = 0.0

    @staticmethod
    def _float_env(name: str, default: float) -> float:
        raw = str(os.environ.get(name, "")).strip()
        if not raw:
            return float(default)
        try:
            return float(raw)
        except Exception:
            return float(default)

    @staticmethod
    def _int_env(name: str, default: int) -> int:
        raw = str(os.environ.get(name, "")).strip()
        if not raw:
            return int(default)
        try:
            return int(raw)
        except Exception:
            return int(default)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()
        return self.root / f"{digest}.json"

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    def _record_saved_at(value: dict[str, Any], path: Path) -> float:
        raw = value.get("saved_at")
        try:
            return float(raw)
        except Exception:
            try:
                return float(path.stat().st_mtime)
            except Exception:
                return 0.0

    def _read_record(self, path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def _is_expired(self, value: dict[str, Any], path: Path, *, now: float) -> bool:
        if self.ttl_s <= 0:
            return False
        saved_at = self._record_saved_at(value, path)
        return (now - saved_at) > self.ttl_s

    def _maybe_cleanup(self, *, now: float | None = None, force: bool = False) -> None:
        ts = float(now if now is not None else time.time())
        if not force and ts < self._next_cleanup_at:
            return
        self.cleanup(now=ts)
        self._next_cleanup_at = ts + self.sweep_interval_s

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        value = self._read_record(path)
        if not isinstance(value, dict):
            self._safe_unlink(path)
            return None
        if self._is_expired(value, path, now=time.time()):
            self._safe_unlink(path)
            return None
        return value

    def put(self, key: str, payload: dict[str, Any]) -> None:
        path = self._path(key)
        now = time.time()
        body = {
            "key": key,
            "saved_at": now,
            "payload": payload,
        }
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        self._maybe_cleanup(now=now)

    def cleanup(self, *, now: float | None = None) -> int:
        """Delete expired/corrupt files and evict old records if over capacity."""
        ts = float(now if now is not None else time.time())
        removed = 0
        live: list[tuple[float, Path]] = []
        for path in self.root.glob("*.json"):
            value = self._read_record(path)
            if not isinstance(value, dict):
                self._safe_unlink(path)
                removed += 1
                continue
            if self._is_expired(value, path, now=ts):
                self._safe_unlink(path)
                removed += 1
                continue
            live.append((self._record_saved_at(value, path), path))

        if self.max_entries > 0 and len(live) > self.max_entries:
            # Keep newest entries; evict older ones.
            live.sort(key=lambda item: item[0], reverse=True)
            for _, path in live[self.max_entries :]:
                self._safe_unlink(path)
                removed += 1
        return removed


def make_idempotency_key(*, doc_id: str, route: str, body: dict[str, Any]) -> str:
    raw = json.dumps({"doc_id": doc_id, "route": route, "body": body}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()
