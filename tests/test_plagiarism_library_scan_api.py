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
    assert isinstance(body.get("revision_advice"), list)
    assert body.get("revision_advice")
    progress_summary = body.get("progress_summary") or {}
    assert isinstance(progress_summary, dict)
    assert float(progress_summary.get("current_overlap_risk") or 0.0) == float(body.get("max_score") or 0.0)
    assert progress_summary.get("reduced_by") is None
    paths = body.get("paths") or {}
    json_path = Path(str(paths.get("json") or ""))
    md_path = Path(str(paths.get("markdown") or ""))
    csv_path = Path(str(paths.get("csv") or ""))
    assert json_path.exists()
    assert md_path.exists()
    assert csv_path.exists()

    raw = json.loads(json_path.read_text(encoding="utf-8"))
    assert str(raw.get("doc_id") or "") == source.id
    assert raw.get("revision_advice") == body.get("revision_advice")
    assert raw.get("progress_summary") == body.get("progress_summary")

    latest = client.get(f"/api/doc/{source.id}/plagiarism/library_scan/latest")
    assert latest.status_code == 200
    latest_body = latest.json()
    assert latest_body.get("has_report") is True
    latest_report = latest_body.get("latest") or {}
    report_id = str(latest_report.get("report_id") or "")
    assert report_id
    assert latest_report.get("revision_advice") == body.get("revision_advice")
    assert latest_report.get("progress_summary") == body.get("progress_summary")

    dl_json = client.get(f"/api/doc/{source.id}/plagiarism/library_scan/download?report_id={report_id}&format=json")
    assert dl_json.status_code == 200
    assert dl_json.headers.get("content-type", "").startswith("application/json")

    dl_md = client.get(f"/api/doc/{source.id}/plagiarism/library_scan/download?report_id={report_id}&format=md")
    assert dl_md.status_code == 200
    assert "text/markdown" in dl_md.headers.get("content-type", "")

    dl_csv = client.get(f"/api/doc/{source.id}/plagiarism/library_scan/download?report_id={report_id}&format=csv")
    assert dl_csv.status_code == 200
    assert "text/csv" in dl_csv.headers.get("content-type", "")


def test_plagiarism_library_scan_reports_progress_against_previous_run(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_v2, "PLAGIARISM_REPORT_DIR", tmp_path / "plagiarism_reports")
    source = _new_doc(
        "# 方案\n\n"
        "AI治理实施中，需要定义里程碑、责任人、验收指标和风险闭环。"
        "每个阶段应保留复盘记录，避免流程漂移。"
    )
    reference = _new_doc(
        "# 样本1\n\n"
        "AI治理实施中，需要定义里程碑、责任人、验收指标和风险闭环。"
        "每个阶段应保留复盘记录。"
    )
    client = TestClient(app_v2.app)

    first = client.post(
        f"/api/doc/{source.id}/plagiarism/library_scan",
        json={
            "include_all_docs": False,
            "reference_doc_ids": [reference.id],
            "threshold": 0.35,
            "top_k": 10,
        },
    )
    assert first.status_code == 200
    first_body = first.json()
    first_score = float(first_body.get("max_score") or 0.0)

    app_v2._set_doc_text(
        source,
        "# 方案\n\n"
        "本节讨论治理实施中的阶段安排、责任边界与复盘机制。"
        "重点是把执行反馈转化为后续调整依据，而不是复述原始资料表述。",
    )
    app_v2.store.put(source)

    second = client.post(
        f"/api/doc/{source.id}/plagiarism/library_scan",
        json={
            "include_all_docs": False,
            "reference_doc_ids": [reference.id],
            "threshold": 0.35,
            "top_k": 10,
        },
    )
    assert second.status_code == 200
    second_body = second.json()
    second_score = float(second_body.get("max_score") or 0.0)
    progress = second_body.get("progress_summary") or {}
    assert float(progress.get("current_overlap_risk") or 0.0) == second_score
    assert float(progress.get("previous_overlap_risk") or 0.0) == first_score
    assert float(progress.get("reduced_by") or 0.0) == round(first_score - second_score, 4)


def test_plagiarism_library_scan_supports_text_override(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_v2, "PLAGIARISM_REPORT_DIR", tmp_path / "plagiarism_reports")
    source = _new_doc(
        "# 方案\n\n"
        "这里是会话内原始正文，故意保持与参考文献差异较大，避免默认正文触发高重合。\n"
    )
    reference = _new_doc(
        "# 样本\n\n"
        "研究执行阶段需要定义里程碑、责任边界、验收指标与复盘机制，"
        "并把阶段反馈转化为后续调整依据。\n"
    )
    exported_text = (
        "# 方案\n\n"
        "研究执行阶段需要定义里程碑、责任边界、验收指标与复盘机制，"
        "并把阶段反馈转化为后续调整依据。\n"
    )
    client = TestClient(app_v2.app)

    resp = client.post(
        f"/api/doc/{source.id}/plagiarism/library_scan",
        json={
            "include_all_docs": False,
            "reference_doc_ids": [reference.id],
            "threshold": 0.35,
            "top_k": 10,
            "text": exported_text,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert float(body.get("source_chars") or 0.0) > float(len("这里是会话内原始正文，故意保持与参考文献差异较大，避免默认正文触发高重合。"))
    assert float(body.get("max_score") or 0.0) >= 0.35
    assert body.get("suspected") is True
