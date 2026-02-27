"""Knowledge Snapshot module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def save_snapshot(*, rag_dir: Path, name: str, payload: dict) -> Path:
    rag_dir = Path(rag_dir)
    snap_dir = rag_dir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    safe = "".join(ch for ch in str(name or "snapshot") if ch.isalnum() or ch in {"-", "_"})
    path = snap_dir / f"{safe}_{ts}.json"
    body = {
        "schema_version": "1.0",
        "created_at": ts,
        "name": safe,
        "payload": dict(payload or {}),
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def latest_snapshot(*, rag_dir: Path, name: str) -> Path | None:
    rag_dir = Path(rag_dir)
    snap_dir = rag_dir / "snapshots"
    if not snap_dir.exists():
        return None
    safe = "".join(ch for ch in str(name or "snapshot") if ch.isalnum() or ch in {"-", "_"})
    rows = sorted(snap_dir.glob(f"{safe}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return rows[0] if rows else None
