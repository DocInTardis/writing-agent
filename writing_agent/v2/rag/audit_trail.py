"""Audit trail for retrieval operations.

Records query paths, linked entities, selected KUs, and vector hits
for post-hoc verification and citation review.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from writing_agent.bounded_jsonl import append_bounded_jsonl, read_recent_jsonl

logger = logging.getLogger(__name__)
_DEFAULT_MAX_BYTES = 8 * 1024 * 1024


def _audit_max_bytes() -> int:
    raw = os.environ.get("WRITING_AGENT_RAG_AUDIT_MAX_BYTES", str(_DEFAULT_MAX_BYTES))
    try:
        return max(64 * 1024, min(64 * 1024 * 1024, int(raw)))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_BYTES


@dataclass
class RetrievalTrail:
    """Immutable(ish) record of a single retrieval operation."""

    trail_id: str = field(default_factory=lambda: f"RT-{uuid.uuid4().hex[:12]}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    query: str = ""
    expanded_queries: list[str] = field(default_factory=list)
    # Vector RAG branch
    chunk_hits: list[dict[str, Any]] = field(default_factory=list)
    # Structured RAG branch
    section_hits: list[dict[str, Any]] = field(default_factory=list)
    evidence_hits: list[dict[str, Any]] = field(default_factory=list)
    # KG-RAG branch
    linked_entities: list[str] = field(default_factory=list)
    kg_hits: list[dict[str, Any]] = field(default_factory=list)
    # Final fused context
    context_preview: str = ""
    # Source counts
    local_chunks: int = 0
    online_chunks: int = 0
    kg_units: int = 0
    papers: int = 0
    # Optional user feedback
    feedback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class AuditTrailStore:
    """Bounded JSONL store for opt-in retrieval trails."""

    def __init__(self, base_dir: Path, *, max_bytes: int | None = None) -> None:
        self.base_dir = Path(base_dir)
        self.trail_path = self.base_dir / "retrieval_trails.jsonl"
        self.max_bytes = max(1, int(max_bytes)) if max_bytes is not None else _audit_max_bytes()

    def record(self, trail: RetrievalTrail) -> bool:
        ok = append_bounded_jsonl(self.trail_path, trail.to_dict(), max_bytes=self.max_bytes)
        if not ok:
            logger.debug("Retrieval audit write skipped")
        return ok

    def load(self, limit: int = 0) -> list[RetrievalTrail]:
        out: list[RetrievalTrail] = []
        rows = read_recent_jsonl(self.trail_path, max_bytes=self.max_bytes)
        if limit:
            rows = rows[-limit:]
        for row in rows:
            try:
                out.append(RetrievalTrail(**row))
            except Exception:
                continue
        return out

    def get_by_query(self, query: str) -> list[RetrievalTrail]:
        q = str(query or "").strip().lower()
        return [t for t in self.load() if q in t.query.lower()]

    def stats(self) -> dict[str, int]:
        trails = self.load()
        return {
            "total_trails": len(trails),
            "with_kg": sum(1 for t in trails if t.kg_units > 0),
            "with_online": sum(1 for t in trails if t.online_chunks > 0),
        }
