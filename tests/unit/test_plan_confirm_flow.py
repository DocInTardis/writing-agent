from __future__ import annotations

import writing_agent.v2.graph_runner as graph_runner
import writing_agent.web.app_v2 as app_v2
from fastapi.testclient import TestClient


def _parse_doc_id(resp) -> str:
    location = str(resp.headers.get("location") or "")
    return location.split("/workbench/")[-1].strip()


def test_dual_engine_interrupts_before_writer(monkeypatch) -> None:
    called = {"writer": 0}

    def _boom_run_generate_graph(**kwargs):
        _ = kwargs
        called["writer"] += 1
        raise AssertionError("writer path should not run when plan is interrupted")

    monkeypatch.setattr(graph_runner, "run_generate_graph", _boom_run_generate_graph)
    out = graph_runner.run_generate_graph_dual_engine(
        instruction="请生成技术报告",
        current_text="# 现有文本\n\n## 引言\n已有内容。",
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        config=graph_runner.GenerateConfig(workers=1, min_total_chars=0, max_total_chars=0),
        compose_mode="continue",
        resume_sections=[],
        format_only=False,
        plan_confirm={"decision": "interrupted", "score": 3, "note": "先暂停"},
    )
    assert called["writer"] == 0
    assert str(out.get("terminal_status") or "") == "interrupted"
    assert str(out.get("failure_reason") or "") == "plan_not_confirmed_by_user"
    assert isinstance(out.get("quality_snapshot"), dict)


def test_plan_confirm_api_persists_and_interrupts_generate() -> None:
    client = TestClient(app_v2.app)
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 303
    doc_id = _parse_doc_id(root)
    assert doc_id

    save_resp = client.post(
        f"/api/doc/{doc_id}/plan/confirm",
        json={"decision": "interrupted", "score": 4, "note": "先不要下发writer"},
    )
    assert save_resp.status_code == 200
    body = save_resp.json()
    assert body.get("ok") == 1
    assert body.get("plan_confirm", {}).get("decision") == "interrupted"

    gen_resp = client.post(
        f"/api/doc/{doc_id}/generate",
        json={"instruction": "请生成一份系统设计文档", "text": ""},
    )
    assert gen_resp.status_code == 200
    payload = gen_resp.json()
    assert payload.get("status") == "interrupted"
    assert payload.get("failure_reason") == "plan_not_confirmed_by_user"
