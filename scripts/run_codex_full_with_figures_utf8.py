#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import os
import json
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

TITLE = "\u9762\u5411\u9ad8\u6821\u79d1\u7814\u573a\u666f\u7684\u667a\u80fd\u5199\u4f5c\u4ee3\u7406\u7cfb\u7edf\u8bbe\u8ba1\u4e0e\u5b9e\u73b0"
SECTIONS = [
    "\u6458\u8981",
    "\u5173\u952e\u8bcd",
    "\u5f15\u8a00",
    "\u9700\u6c42\u5206\u6790",
    "\u7cfb\u7edf\u603b\u4f53\u67b6\u6784",
    "\u6838\u5fc3\u4e1a\u52a1\u6d41\u7a0b",
    "\u5173\u952e\u6280\u672f\u5b9e\u73b0",
    "\u5b9e\u9a8c\u7ed3\u679c\u4e0e\u5206\u6790",
    "\u7ed3\u8bba",
    "\u53c2\u8003\u6587\u732e",
]
TARGET_CHARS = 7800


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def build_instruction() -> str:
    joined = "\u3001".join(SECTIONS)
    return (
        f"\u8bf7\u56f4\u7ed5\u300a{TITLE}\u300b\u751f\u6210\u4e00\u7bc7\u5b8c\u6574\u7684\u4e2d\u6587\u5b66\u672f\u8bba\u6587\u3002\n"
        "\u8981\u6c42\uff1a\n"
        f"1. \u4ec5\u8f93\u51fa\u6b63\u6587\uff0c\u5fc5\u987b\u5305\u542b\u4ee5\u4e0b\u4e8c\u7ea7\u7ae0\u8282\u4e14\u987a\u5e8f\u56fa\u5b9a\uff1a{joined}\u3002\n"
        f"2. \u6b63\u6587\u76ee\u6807\u7ea6{TARGET_CHARS}\u5b57\uff0c\u5141\u8bb8\u5408\u7406\u6d6e\u52a8\uff0c\u4f46\u6bcf\u4e2a\u7ae0\u8282\u90fd\u5fc5\u987b\u662f\u5b8c\u6574\u5185\u5bb9\uff0c\u4e0d\u5f97\u7528\u6a21\u677f\u53e5\u3001\u63d0\u793a\u8bed\u6216\u5360\u4f4d\u6587\u5b57\u51d1\u6570\u3002\n"
        "3. \u5bf9\u4e8e\u9002\u5408\u56fe\u793a\u7684\u7ae0\u8282\uff0c\u5982\u603b\u4f53\u67b6\u6784\u3001\u6838\u5fc3\u6d41\u7a0b\u3001\u6a21\u5757\u5173\u7cfb\u7b49\uff0c\u53ef\u5728\u786e\u6709\u5fc5\u8981\u65f6\u63d2\u5165\u56fe\u793a\uff0c\u4e14\u53ea\u80fd\u4f7f\u7528\u5408\u6cd5\u7684 [[FIGURE:{...}]] \u6807\u8bb0\uff1b\u56fe\u793a\u5fc5\u987b\u4e0e\u672c\u8282\u5185\u5bb9\u4e00\u81f4\u3002\n"
        "4. \u5bf9\u4e8e\u5b9e\u9a8c\u7ed3\u679c\u4e0e\u5206\u6790\u7b49\u7ae0\u8282\uff0c\u53ef\u5728\u786e\u6709\u5fc5\u8981\u65f6\u63d2\u5165\u5408\u6cd5\u7684 [[TABLE:{...}]] \u6807\u8bb0\uff1b\u8868\u683c\u5fc5\u987b\u670d\u52a1\u4e8e\u8bba\u8bc1\uff0c\u4e0d\u5f97\u7a7a\u8868\u3002\n"
        "5. \u4e0d\u5f97\u8f93\u51fa\u5199\u4f5c\u63d0\u793a\u3001\u5143\u6307\u4ee4\u3001\u7ed3\u6784\u5316\u5b57\u6bb5\u6b8b\u7559\uff0c\u4e0d\u5f97\u51fa\u73b0 section_id\u3001block_id\u3001type\u3001items\u3001caption\u3001columns\u3001rows \u7b49\u8bf4\u660e\u6027\u6587\u5b57\u3002\n"
        "6. \u4e0d\u5f97\u7f16\u9020\u5b9e\u9a8c benchmark\u3001\u5e76\u53d1\u6027\u80fd\u3001\u6210\u529f\u7387\u3001\u95ee\u5377\u767e\u5206\u6bd4\u3001\u54cd\u5e94\u65f6\u5ef6\u3001\u6837\u672c\u91cf\u7b49\u65e0\u4f9d\u636e\u6570\u503c\uff1b\u5982\u65e0\u660e\u786e\u8bc1\u636e\uff0c\u4ec5\u5141\u8bb8\u5b9a\u6027\u63cf\u8ff0\uff0c\u4e0d\u5f97\u5199\u5177\u4f53\u6570\u5b57\u3002\n"
        "7. \u53c2\u8003\u6587\u732e\u81f3\u5c118\u6761\uff0c\u4f7f\u7528 [1] [2] \u5f62\u5f0f\u9010\u6761\u5217\u51fa\uff0c\u4e0d\u5f97\u91cd\u590d\uff0c\u4e0d\u5f97\u7559\u7a7a\u3002\n"
        "8. \u8bed\u8a00\u4fdd\u6301\u6b63\u5f0f\u3001\u4e2d\u6587\u3001\u5b66\u672f\u5316\uff0c\u907f\u514d\u53e3\u8bed\u3001\u907f\u514d\u91cd\u590d\u3002"
    )


def settings_payload() -> dict[str, Any]:
    return {
        "generation_prefs": {
            "purpose": "\u5b66\u672f\u8bba\u6587",
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
            "font_name": "\u5b8b\u4f53",
            "font_name_east_asia": "\u5b8b\u4f53",
            "font_size_name": "\u5c0f\u56db",
            "font_size_pt": 12,
            "line_spacing": 28,
            "heading1_font_name": "\u9ed1\u4f53",
            "heading1_font_name_east_asia": "\u9ed1\u4f53",
            "heading1_size_pt": 22,
            "heading2_font_name": "\u9ed1\u4f53",
            "heading2_font_name_east_asia": "\u9ed1\u4f53",
            "heading2_size_pt": 16,
            "heading3_font_name": "\u9ed1\u4f53",
            "heading3_font_name_east_asia": "\u9ed1\u4f53",
            "heading3_size_pt": 16,
        },
    }


def main() -> int:
    configure_env()
    os.environ["WRITING_AGENT_RUNTIME_JSON_CACHE"] = "0"
    os.environ["WRITING_AGENT_PARADIGM_OVERRIDE"] = "engineering"
    run_root = Path("deliverables").resolve() / f"codex_full_with_figures_utf8_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_root.mkdir(parents=True, exist_ok=True)

    client = TestClient(app_v2.app)
    root_resp = client.get("/", follow_redirects=False)
    if root_resp.status_code != 303:
        raise RuntimeError(f"create doc failed: {root_resp.status_code} {root_resp.text[:200]}")
    doc_id = parse_doc_id_from_redirect(root_resp)
    set_resp = client.post(f"/api/doc/{doc_id}/settings", json=settings_payload())
    if set_resp.status_code != 200:
        raise RuntimeError(f"save settings failed: {set_resp.status_code} {set_resp.text[:200]}")

    started = time.time()
    events: list[dict[str, Any]] = []
    final_payload: dict[str, Any] = {}
    generator = app_v2.run_generate_graph(
        instruction=build_instruction(),
        current_text="",
        required_h2=list(SECTIONS),
        required_outline=[(2, sec) for sec in SECTIONS],
        expand_outline=False,
        config=app_v2.GenerateConfig(workers=8, min_total_chars=TARGET_CHARS, max_total_chars=0),
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
        "title": TITLE,
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
        "figure_gate_passed": bool(validator.get("figure_gate_passed", True)),
        "validator_figure_score_avg": float(validator.get("figure_score_avg", 0.0) or 0.0),
        "validator_figure_pass_ratio": float(validator.get("figure_pass_ratio", 0.0) or 0.0),
        "validator_figure_review_count": int(validator.get("figure_review_count", 0) or 0),
        "validator_figure_drop_count": int(validator.get("figure_drop_count", 0) or 0),
        "validator_weak_figure_items": list(validator.get("weak_figure_items") or []),
        "figure_score_avg": float(figure_manifest.get("avg_score", 0.0) or 0.0),
        "figure_score_min": int(figure_manifest.get("min_score", 0) or 0),
        "figure_score_max": int(figure_manifest.get("max_score", 0) or 0),
        "figure_passed_count": int(figure_manifest.get("passed_count", 0) or 0),
        "inline_shapes": inline_shapes,
        "final_markdown_file": str(final_md.resolve()),
        "final_docx_file": str(final_docx.resolve()) if final_docx.exists() else "",
        "figure_assets_dir": str((run_root / "figure_assets").resolve()),
        "figure_manifest_file": str((run_root / "figure_assets" / "manifest.json").resolve()),
        "events_file": str(raw_events.resolve()),
        "save_status": save_resp.status_code,
    }
    (run_root / "targeted_revision_report.json").write_text(json.dumps(targeted_revision_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_root / "RUN_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] == "success" and bool(validator.get("passed")) and (summary["figure_count"] == 0 or summary["inline_shapes"] >= 1):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
