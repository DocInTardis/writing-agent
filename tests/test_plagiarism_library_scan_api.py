from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _new_doc(text: str):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, text)
    app_v2.store.put(session)
    return session


def test_plagiarism_library_scan_and_download(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_v2, "PLAGIARISM_REPORT_DIR", tmp_path / "plagiarism_reports")
    source = _new_doc(
        "# 方案\n\n"
        "AI治理实施中，需要定义里程碑、责任人、验收指标和风险闭环。"
        "每个阶段应保留复盘记录，避免流程漂移。"
    )
    reference_1 = _new_doc(
        "# 样本1\n\n"
        "AI治理实施中，需要定义里程碑、责任人、验收指标和风险闭环。"
        "每个阶段应保留复盘记录。"
    )
    reference_2 = _new_doc(
        "# 样本2\n\n"
        "本文讨论读书计划与时间管理方法，强调每日复盘与目标拆解。"
    )
    client = TestClient(app_v2.app)

    resp = client.post(
        f"/api/doc/{source.id}/plagiarism/library_scan",
        json={
            "include_all_docs": False,
            "reference_doc_ids": [reference_1.id, reference_2.id],
            "threshold": 0.35,
            "top_k": 10,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") == 1
    assert str(body.get("doc_id") or "") == source.id
    assert int(body.get("total_references") or 0) >= 2
    assert str(body.get("report_id") or "")
    paths = body.get("paths") or {}
    json_path = Path(str(paths.get("json") or ""))
    md_path = Path(str(paths.get("markdown") or ""))
    csv_path = Path(str(paths.get("csv") or ""))
    assert json_path.exists()
    assert md_path.exists()
    assert csv_path.exists()

    raw = json.loads(json_path.read_text(encoding="utf-8"))
    assert str(raw.get("doc_id") or "") == source.id

    latest = client.get(f"/api/doc/{source.id}/plagiarism/library_scan/latest")
    assert latest.status_code == 200
    latest_body = latest.json()
    assert latest_body.get("has_report") is True
    latest_report = latest_body.get("latest") or {}
    report_id = str(latest_report.get("report_id") or "")
    assert report_id

    dl_json = client.get(f"/api/doc/{source.id}/plagiarism/library_scan/download?report_id={report_id}&format=json")
    assert dl_json.status_code == 200
    assert dl_json.headers.get("content-type", "").startswith("application/json")

    dl_md = client.get(f"/api/doc/{source.id}/plagiarism/library_scan/download?report_id={report_id}&format=md")
    assert dl_md.status_code == 200
    assert "text/markdown" in dl_md.headers.get("content-type", "")

    dl_csv = client.get(f"/api/doc/{source.id}/plagiarism/library_scan/download?report_id={report_id}&format=csv")
    assert dl_csv.status_code == 200
    assert "text/csv" in dl_csv.headers.get("content-type", "")

