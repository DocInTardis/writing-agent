from __future__ import annotations

import os
import tempfile
from pathlib import Path

from writing_agent.v2.rag.audit_trail import AuditTrailStore, RetrievalTrail
from writing_agent.v2.rag.retrieve import _record_retrieval_trail


def test_read_only_audit_store_does_not_create_directory() -> None:
    with tempfile.TemporaryDirectory() as root:
        audit_dir = Path(root) / "missing" / "audit"
        store = AuditTrailStore(audit_dir)

        assert store.load() == []
        assert store.stats() == {"total_trails": 0, "with_kg": 0, "with_online": 0}
        assert not audit_dir.exists()


def test_retrieval_audit_is_disabled_by_default() -> None:
    previous = os.environ.pop("WRITING_AGENT_RAG_AUDIT_ENABLED", None)
    try:
        with tempfile.TemporaryDirectory() as root:
            rag_dir = Path(root)
            trail_id = _record_retrieval_trail(
                rag_dir=rag_dir,
                query="query",
                queries=["query"],
                context="context",
            )
            assert trail_id == ""
            assert not (rag_dir / "audit").exists()
    finally:
        if previous is not None:
            os.environ["WRITING_AGENT_RAG_AUDIT_ENABLED"] = previous


def test_enabled_audit_file_stays_within_limit_and_keeps_newest_rows() -> None:
    with tempfile.TemporaryDirectory() as root:
        store = AuditTrailStore(Path(root) / "audit", max_bytes=1400)
        for index in range(30):
            assert store.record(RetrievalTrail(query=f"query-{index}-" + ("x" * 80)))

        assert store.trail_path.stat().st_size <= 1400
        loaded = store.load()
        assert loaded
        assert loaded[-1].query.startswith("query-29-")
        assert all(not item.query.startswith("query-0-") for item in loaded)


def test_oversized_audit_row_is_rejected_without_creating_files() -> None:
    with tempfile.TemporaryDirectory() as root:
        audit_dir = Path(root) / "audit"
        store = AuditTrailStore(audit_dir, max_bytes=256)

        assert not store.record(RetrievalTrail(query="x" * 1000))
        assert not audit_dir.exists()
