from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from writing_agent.web import meta_db
from writing_agent.web.services import feedback_service


def _with_data_dir(root: str):
    previous_dir = os.environ.get("WRITING_AGENT_DATA_DIR")
    previous_limit = os.environ.get("WRITING_AGENT_FEEDBACK_LOG_MAX_BYTES")
    os.environ["WRITING_AGENT_DATA_DIR"] = root
    os.environ["WRITING_AGENT_FEEDBACK_LOG_MAX_BYTES"] = str(64 * 1024)
    return previous_dir, previous_limit


def _restore_env(previous_dir: str | None, previous_limit: str | None) -> None:
    for key, value in (
        ("WRITING_AGENT_DATA_DIR", previous_dir),
        ("WRITING_AGENT_FEEDBACK_LOG_MAX_BYTES", previous_limit),
    ):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_feedback_listing_does_not_create_learning_directory() -> None:
    with tempfile.TemporaryDirectory() as root:
        previous = _with_data_dir(root)
        try:
            assert meta_db.load_low_satisfaction_events() == []
            assert not (Path(root) / "learning").exists()
        finally:
            _restore_env(*previous)


def test_feedback_learning_copy_stays_bounded_and_keeps_newest_rows() -> None:
    with tempfile.TemporaryDirectory() as root:
        previous = _with_data_dir(root)
        try:
            for index in range(100):
                assert meta_db.append_low_satisfaction_event(
                    f"doc-{index}",
                    {"rating": 1, "stage": "draft", "note": "n" * 100},
                    context={"index": index},
                    doc_text="文" * 1200,
                )

            path = Path(root) / "learning" / "low_satisfaction_feedback.jsonl"
            assert path.stat().st_size <= 64 * 1024
            rows = meta_db.load_low_satisfaction_events(limit=5000)
            assert rows
            assert rows[-1]["doc_id"] == "doc-99"
            assert all(row["doc_id"] != "doc-0" for row in rows)
        finally:
            _restore_env(*previous)


def test_feedback_service_still_records_low_ratings() -> None:
    with tempfile.TemporaryDirectory() as root:
        previous = _with_data_dir(root)
        try:
            session = SimpleNamespace(doc_text="draft")
            app = SimpleNamespace(
                HTTPException=RuntimeError,
                store=SimpleNamespace(get=lambda _doc_id: session),
                _normalize_feedback_item=lambda item: dict(item, created_at=1.0),
                _low_satisfaction_threshold=lambda: 2,
            )

            class _Request:
                async def json(self):
                    return {"item": {"rating": 1, "stage": "draft", "note": "missing section"}}

            with patch.object(feedback_service, "app_v2_module", return_value=app):
                result = asyncio.run(feedback_service.FeedbackService().save_feedback("doc-1", _Request()))

            assert result["low_recorded"] == 1
            assert meta_db.load_low_satisfaction_events(limit=10)[-1]["doc_id"] == "doc-1"
        finally:
            _restore_env(*previous)
