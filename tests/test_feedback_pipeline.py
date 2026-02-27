from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _prepare_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_v2, "META_DB_PATH", tmp_path / "session_meta.db")
    monkeypatch.setattr(app_v2, "LOW_SATISFACTION_PATH", tmp_path / "learning" / "low_satisfaction_feedback.jsonl")


def test_feedback_roundtrip_and_doc_payload(tmp_path: Path, monkeypatch):
    _prepare_paths(tmp_path, monkeypatch)
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# T\n\n正文")
    app_v2.store.put(session)
    client = TestClient(app_v2.app)

    resp = client.post(
        f"/api/doc/{session.id}/feedback",
        json={
            "item": {
                "rating": 5,
                "stage": "final",
                "note": "整体可用，结构完整。",
            },
            "context": {"source": "unit_test"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("saved") == 1
    assert body.get("low_recorded") == 0

    resp_get = client.get(f"/api/doc/{session.id}/feedback")
    assert resp_get.status_code == 200
    items = resp_get.json().get("items") or []
    assert len(items) == 1
    assert int(items[0].get("rating") or 0) == 5
    assert str(items[0].get("stage") or "") == "final"

    resp_doc = client.get(f"/api/doc/{session.id}")
    assert resp_doc.status_code == 200
    payload = resp_doc.json()
    assert isinstance(payload.get("feedback_log"), list)
    assert len(payload.get("feedback_log") or []) == 1


def test_low_feedback_written_for_learning(tmp_path: Path, monkeypatch):
    _prepare_paths(tmp_path, monkeypatch)
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# T\n\n低分反馈样本文本")
    app_v2.store.put(session)
    client = TestClient(app_v2.app)

    resp = client.post(
        f"/api/doc/{session.id}/feedback",
        json={
            "item": {
                "rating": 1,
                "stage": "stage1",
                "note": "输出缺关键章节，质量不达标",
            },
            "context": {"scenario": "complex_prompt"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("saved") == 1
    assert body.get("low_recorded") == 1

    path = Path(app_v2.LOW_SATISFACTION_PATH)
    assert path.exists()
    lines = [x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) >= 1
    row = json.loads(lines[-1])
    assert str(row.get("doc_id") or "") == session.id
    assert int(row.get("rating") or 0) == 1
    assert "text_preview" in row

    resp_low = client.get("/api/feedback/low?limit=10")
    assert resp_low.status_code == 200
    low_items = resp_low.json().get("items") or []
    assert any(str(x.get("doc_id") or "") == session.id for x in low_items if isinstance(x, dict))


def test_feedback_rejects_invalid_rating(tmp_path: Path, monkeypatch):
    _prepare_paths(tmp_path, monkeypatch)
    session = app_v2.store.create()
    app_v2.store.put(session)
    client = TestClient(app_v2.app)

    resp = client.post(
        f"/api/doc/{session.id}/feedback",
        json={"item": {"rating": 8, "note": "invalid"}},
    )
    assert resp.status_code == 400
