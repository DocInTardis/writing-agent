"""Audit Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from writing_agent.bounded_jsonl import read_recent_jsonl

_AUDIT_LOCK = threading.Lock()
_DEFAULT_AUDIT_MAX_BYTES = 8 * 1024 * 1024
_DEFAULT_AUDIT_RETENTION_S = 90 * 24 * 60 * 60


def _audit_max_bytes() -> int:
    raw = os.environ.get("WRITING_AGENT_AUDIT_MAX_BYTES", str(_DEFAULT_AUDIT_MAX_BYTES))
    try:
        return max(64 * 1024, min(64 * 1024 * 1024, int(raw)))
    except (TypeError, ValueError):
        return _DEFAULT_AUDIT_MAX_BYTES


def _audit_retention_seconds() -> int:
    raw = os.environ.get("WRITING_AGENT_AUDIT_TTL_S", str(_DEFAULT_AUDIT_RETENTION_S))
    try:
        return max(24 * 60 * 60, min(2 * 365 * 24 * 60 * 60, int(raw)))
    except (TypeError, ValueError):
        return _DEFAULT_AUDIT_RETENTION_S


class AuditService:
    """Bounded audit window with an explicit hash anchor on rotation."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        secret: str = "",
        max_bytes: int | None = None,
        max_age_s: int | None = None,
    ) -> None:
        data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", "").strip() or ".data")
        self.path = Path(path) if path is not None else data_dir / "audit" / "app_audit_chain.ndjson"
        self.secret = str(secret or "")
        self.max_bytes = max(1, int(max_bytes)) if max_bytes is not None else _audit_max_bytes()
        self.max_age_s = _audit_retention_seconds() if max_age_s is None else max(1, int(max_age_s))

    def append(self, *, actor: str, action: str, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with _AUDIT_LOCK:
            prev_hash = self._last_hash()
            event = self._build_event(
                actor=actor,
                action=action,
                tenant_id=tenant_id,
                payload=payload,
                prev_hash=prev_hash,
            )
            line = self._encode(event)
            size = self.path.stat().st_size if self.path.exists() else 0
            complete = self._ends_with_newline(size)
            expired = self._window_expired()
            if not expired and complete and size + len(line) <= self.max_bytes:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("ab") as stream:
                    stream.write(line)
                return event

            root = self._build_event(
                actor="system",
                action="audit_window_rotated",
                tenant_id="system",
                payload={"prior_terminal_hash": prev_hash},
                prev_hash="",
            )
            event = self._build_event(
                actor=actor,
                action=action,
                tenant_id=tenant_id,
                payload=payload,
                prev_hash=str(root["hash"]),
            )
            replacement = self._encode(root) + self._encode(event)
            if len(replacement) > self.max_bytes:
                raise ValueError("audit event exceeds configured storage limit")
            self._replace(replacement)
            return event

    def _window_expired(self) -> bool:
        cutoff = time.time() - self.max_age_s
        for row in read_recent_jsonl(self.path, max_bytes=self.max_bytes):
            timestamp = row.get("ts")
            if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
                return float(timestamp) < cutoff
        return False

    def _build_event(
        self,
        *,
        actor: str,
        action: str,
        tenant_id: str,
        payload: dict[str, Any],
        prev_hash: str,
    ) -> dict[str, Any]:
        event = {
            "ts": time.time(),
            "actor": str(actor or "system"),
            "action": str(action or "unknown"),
            "tenant_id": str(tenant_id or "default"),
            "payload": dict(payload or {}),
            "prev_hash": prev_hash,
        }
        body = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()
        event["hash"] = digest
        if self.secret:
            event["signature"] = hmac.new(self.secret.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()
        return event

    def _last_hash(self) -> str:
        for row in reversed(read_recent_jsonl(self.path, max_bytes=self.max_bytes)):
            if row.get("hash"):
                return str(row.get("hash"))
        return ""

    @staticmethod
    def _encode(event: dict[str, Any]) -> bytes:
        return (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

    def _ends_with_newline(self, size: int) -> bool:
        if not size:
            return True
        with self.path.open("rb") as stream:
            stream.seek(-1, os.SEEK_END)
            return stream.read(1) == b"\n"

    def _replace(self, payload: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent,
                prefix=self.path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
