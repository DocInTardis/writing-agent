#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from scripts.run_codex_smoke_test import configure_env, parse_doc_id_from_redirect
from writing_agent.v2.figure_render import export_rendered_figure_assets
from writing_agent.v2.final_validator import validate_final_document
from writing_agent.v2.meta_firewall import MetaFirewall
from scripts.run_summary_utils import extract_section_originality_summary
from scripts.targeted_revision_utils import run_targeted_section_revisions

TITLE = "面向高校科研场景的智能写作代理系统设计与实现"
SECTIONS = [
    "摘要",
    "关键词",
    "引言",
    "需求分析",
    "系统总体架构",
    "核心业务流程",
    "关键技术实现",
    "实验结果与分析",
    "结论",
    "参考文献",
]
TARGET_CHARS = 5200


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def build_instruction() -> str:
    joined = "、".join(SECTIONS)
    return (
        f"请围绕《{TITLE}》生成一篇完整的中文学术论文。\n"
        f"必须包含以下二级章节且顺序固定：{joined}。\n"
        f"正文目标约 {TARGET_CHARS} 字，只输出最终正文。\n"
        "系统总体架构、核心业务流程、关键技术实现三个章节中，至少产出 2 个可渲染的真实图示，"
        "图示只能使用合法的 [[FIGURE:{...}]] 标记，且必须包含 type=figure、kind、caption、data，禁止只写 caption。\n"
        "参考文献章节必须至少列出 8 条真实且不重复的参考文献，使用 [1] [2] 形式逐条列出。\n"
        "不得输出提示词、元指令、schema 解释、字段说明、section_id、block_id、caption kind data json 等说明性文字。"
    )


def settings_payload() -> dict[str, Any]:
    return {
        "generation_prefs": {
            "purpose": "学术论文",
            "target_char_count": TARGET_CHARS,
            "target_length_confirmed": True,
            "include_cover": False,
            "include_toc": False,
            "toc_levels": 2,
            "page_numbers": False,
            "include_header": False,
            "expand_outline": False,
            "export_gate_policy": "off",
            "strict_doc_format": False,
            "strict_citation_verify": False,
        },
        "formatting": {
            "font_name": "宋体",
            "font_name_east_asia": "宋体",
            "font_size_name": "小四",
            "font_size_pt": 12,
            "line_spacing": 28,
            "heading1_font_name": "黑体",
            "heading1_font_name_east_asia": "黑体",
            "heading1_size_pt": 22,
            "heading2_font_name": "黑体",
            "heading2_font_name_east_asia": "黑体",
            "heading2_size_pt": 16,
            "heading3_font_name": "黑体",
            "heading3_font_name_east_asia": "黑体",
            "heading3_size_pt": 16,
        },
    }


def main() -> int:
    configure_env()
    os.environ["WRITING_AGENT_EVIDENCE_ENABLED"] = "1"
    os.environ["WRITING_AGENT_MIN_REFERENCE_ITEMS"] = "8"
    os.environ["WRITING_AGENT_ENFORCE_REFERENCE_MIN"] = "1"
    os.environ["WRITING_AGENT_RAG_THEME_GATE_ENABLED"] = "1"
    os.environ["WRITING_AGENT_FIGURE_GATE_ENABLED"] = "1"
    os.environ["WRITING_AGENT_PARADIGM_OVERRIDE"] = "engineering"

    run_root = Path("deliverables").resolve() / f"codex_forced_figure_and_refs_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_root.mkdir(parents=True, exist_ok=True)

    client = TestClient(app_v2.app)
    root_resp = client.get("/", follow_redirects=False)
    if root_resp.status_code != 303:
        raise RuntimeError(f"create doc failed: {root_resp.status_code} {root_resp.text[:200]}")
    doc_id = parse_doc_id_from_redirect(root_resp)
    set_resp = client.post(f"/api/doc/{doc_id}/settings", json=settings_payload())
    if set_resp.status_code != 200:
        raise RuntimeError(f"save settings failed: {set_resp.status_code} {set_resp.text[:200]}")

    cfg = app_v2.GenerateConfig(workers=8, min_total_chars=TARGET_CHARS, max_total_chars=0)
    events: list[dict[str, Any]] = []
    final_payload: dict[str, Any] = {}
    started = time.time()
    generator = app_v2.run_generate_graph(
        instruction=build_instruction(),
        current_text="",
        required_h2=list(SECTIONS),
        required_outline=[(2, sec) for sec in SECTIONS],
        expand_outline=False,
        config=cfg,
    )
    for ev in generator:
        payload = ev if isinstance(ev, dict) else {"_raw": str(ev)}
        row = {
            "seq": len(events) + 1,
            "t_rel_s": round(time.time() - started, 3),
            "event": str(payload.get("event") or "message"),
            "payload": payload,
        }
        events.append(row)
        if row["event"] == "final":
            final_payload = payload

    if not final_payload:
        final_payload = {
            "event": "final",
            "text": "",
            "status": "failed",
            "failure_reason": "missing_final_payload",
            "problems": ["missing_final_payload"],
        }
        events.append({"seq": len(events) + 1, "t_rel_s": round(time.time() - started, 3), "event": "final", "payload": final_payload})

    raw_events = run_root / "raw_events.jsonl"
    raw_events.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in events) + "\n", encoding="utf-8")

    text = str(final_payload.get("text") or "")
    quality_snapshot_runtime = final_payload.get("quality_snapshot") if isinstance(final_payload.get("quality_snapshot"), dict) else {}
    section_originality_hot_sample = extract_section_originality_summary(quality_snapshot_runtime)
    text, targeted_revision_report = run_targeted_section_revisions(
        client=client,
        doc_id=doc_id,
        text=text,
        quality_snapshot=quality_snapshot_runtime,
        max_sections=2,
    )
    final_md = run_root / "final_output.md"
    final_md.write_text(text, encoding="utf-8")
    figure_manifest = export_rendered_figure_assets(text, run_root / "figure_assets")

    save_resp = client.post(f"/api/doc/{doc_id}/save", json={"text": text, **settings_payload()})
    final_docx = run_root / "final_output.docx"
    dl = client.get(f"/download/{doc_id}.docx")
    if dl.status_code == 200 and dl.content:
        final_docx.write_bytes(dl.content)

    inline_shapes = 0
    if final_docx.exists():
        try:
            inline_shapes = len(Document(io.BytesIO(final_docx.read_bytes())).inline_shapes)
        except Exception:
            inline_shapes = 0

    refs_count = len(re.findall(r"(?m)^\s*\[\d+\]\s+", text))
    meta_scan = MetaFirewall().scan(text)
    validator = validate_final_document(
        title=TITLE,
        text=text,
        sections=SECTIONS,
        problems=[],
        rag_gate_dropped=[],
    )
    summary = {
        "run_root": str(run_root),
        "doc_id": doc_id,
        "status": str(final_payload.get("status") or "failed"),
        "failure_reason": str(final_payload.get("failure_reason") or ""),
        "runtime_status": str(final_payload.get("runtime_status") or final_payload.get("status") or "failed"),
        "runtime_failure_reason": str(final_payload.get("runtime_failure_reason") or ""),
        "quality_passed_runtime": bool(final_payload.get("quality_passed", False)),
        "quality_failure_reason_runtime": str(final_payload.get("quality_failure_reason") or ""),
        "duration_s": round(time.time() - started, 3),
        "chars": compact_len(text),
        "refs_count": refs_count,
        "meta_hits": list(meta_scan.fragments[:8]),
        "quality_snapshot_runtime": quality_snapshot_runtime,
        "section_originality_hot_sample": section_originality_hot_sample,
        "targeted_revision_report": targeted_revision_report,
        "validator": validator,
        "figure_count": int(figure_manifest.get("count", 0)),
        "figure_score_avg": float(figure_manifest.get("avg_score", 0.0) or 0.0),
        "figure_passed_count": int(figure_manifest.get("passed_count", 0) or 0),
        "inline_shapes": inline_shapes,
        "final_markdown_file": str(final_md.resolve()),
        "final_docx_file": str(final_docx.resolve()) if final_docx.exists() else "",
        "figure_manifest_file": str((run_root / "figure_assets" / "manifest.json").resolve()),
        "events_file": str(raw_events.resolve()),
        "save_status": save_resp.status_code,
    }
    (run_root / "targeted_revision_report.json").write_text(json.dumps(targeted_revision_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_root / "RUN_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "success" and bool(validator.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
