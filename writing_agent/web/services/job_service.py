"""Job Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class JobRecord:
    job_id: str
    type: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    callback_url: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobService:
    def __init__(self, *, persist_path: str | Path = ".data/jobs/jobs.json") -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._path = Path(persist_path)
        self._load()

    def submit(self, *, job_type: str, payload: dict[str, Any], callback_url: str = "") -> JobRecord:
        job_id = uuid.uuid4().hex
        row = JobRecord(job_id=job_id, type=str(job_type or "job"), status="queued", payload=dict(payload or {}), callback_url=str(callback_url or ""))
        with self._lock:
            self._jobs[job_id] = row
            self._save()
        return row

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._jobs.get(str(job_id or "").strip())
            return row

    def list(self, *, limit: int = 50) -> list[JobRecord]:
        with self._lock:
            rows = sorted(self._jobs.values(), key=lambda x: x.created_at, reverse=True)
            return rows[: max(1, min(200, int(limit)))]

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            row = self._jobs.get(job_id)
            if row is None:
                return
            row.status = "running"
            row.updated_at = time.time()
            self._save()

    def mark_done(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            row = self._jobs.get(job_id)
            if row is None:
                return
            row.status = "done"
            row.result = dict(result or {})
            row.updated_at = time.time()
            self._save()

    def mark_failed(self, job_id: str, message: str) -> None:
        with self._lock:
            row = self._jobs.get(job_id)
            if row is None:
                return
            row.status = "failed"
            row.result = {"ok": 0, "error": str(message or "failed")}
            row.updated_at = time.time()
            self._save()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        rows = raw.get("jobs") if isinstance(raw, dict) else []
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            job_id = str(row.get("job_id") or "").strip()
            if not job_id:
                continue
            self._jobs[job_id] = JobRecord(
                job_id=job_id,
                type=str(row.get("type") or "job"),
                status=str(row.get("status") or "queued"),
                payload=dict(row.get("payload") or {}),
                result=dict(row.get("result") or {}) if isinstance(row.get("result"), dict) else None,
                callback_url=str(row.get("callback_url") or ""),
                created_at=float(row.get("created_at") or time.time()),
                updated_at=float(row.get("updated_at") or time.time()),
            )

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for row in self._jobs.values():
            rows.append(
                {
                    "job_id": row.job_id,
                    "type": row.type,
                    "status": row.status,
                    "payload": row.payload,
                    "result": row.result,
                    "callback_url": row.callback_url,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
            )
        payload = {"jobs": rows}
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
