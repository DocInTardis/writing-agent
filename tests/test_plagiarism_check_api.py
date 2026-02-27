from __future__ import annotations

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _new_doc(text: str):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, text)
    app_v2.store.put(session)
    return session


def test_plagiarism_check_requires_references():
    source = _new_doc("这是一段用于查重测试的文本，包含结构化内容和结论。")
    client = TestClient(app_v2.app)
    resp = client.post(f"/api/doc/{source.id}/plagiarism/check", json={})
    assert resp.status_code == 400


def test_plagiarism_check_detects_overlap_with_doc_reference():
    source = _new_doc(
        "# 标题\n\n"
        "企业AI治理需要明确治理目标、风险闭环、责任人和验收指标。"
        "在90天推进过程中，应按里程碑进行阶段复盘，并输出执行保障计划。"
    )
    reference = _new_doc(
        "# 参考\n\n"
        "企业AI治理需要明确治理目标、风险闭环、责任人和验收指标。"
        "在90天推进过程中，应按里程碑进行阶段复盘，并输出执行保障计划。"
        "此外，还应补充组织协同机制。"
    )
    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{source.id}/plagiarism/check",
        json={"reference_doc_ids": [reference.id], "threshold": 0.35},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") == 1
    assert data.get("total_references") == 1
    rows = data.get("results") or []
    assert len(rows) == 1
    row = rows[0]
    assert str(row.get("reference_id") or "") == reference.id
    assert float(row.get("score") or 0.0) >= 0.5
    assert bool(row.get("suspected")) is True
    metrics = row.get("metrics") or {}
    assert int(metrics.get("longest_match_chars") or 0) >= 30


def test_plagiarism_check_with_manual_text_can_be_low_risk():
    source = _new_doc(
        "本文主要介绍供应链协同平台的建设路径，包括流程梳理、接口治理和指标仪表盘设计。"
    )
    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{source.id}/plagiarism/check",
        json={
            "threshold": 0.4,
            "reference_texts": [
                {"id": "r1", "title": "manual", "text": "这是一段关于亲子阅读方法的说明，讨论阅读习惯培养。"}
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    rows = data.get("results") or []
    assert len(rows) == 1
    row = rows[0]
    assert float(row.get("score") or 0.0) < 0.4
    assert bool(row.get("suspected")) is False

