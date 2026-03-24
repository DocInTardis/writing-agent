#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Targeted codex smoke run that forces reference_repair to emit a real runtime event."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
import writing_agent.v2.graph_runner_runtime as runtime_module
from scripts.run_codex_smoke_test import configure_env, now_stamp, parse_doc_id_from_redirect, settings_payload
from writing_agent.v2.figure_render import export_rendered_figure_assets
from scripts.run_summary_utils import extract_section_originality_summary

TITLE = "区块链+农村社会化服务参考文献修复冒烟验证"
REQUIRED_H2 = ["摘要", "引言", "参考文献"]


def _repair_fallback_sources() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx in range(1, 13):
        rows.append(
            {
                "id": f"repair-src-{idx}",
                "title": f"Blockchain Rural Service Study {idx}",
                "url": f"https://example.test/repair/{idx}",
                "authors": [f"Author {idx}"],
                "published": f"202{idx % 5}-01-01",
                "updated": f"202{idx % 5}-01-01",
                "source": "forced-repair",
            }
        )
    return rows


def build_instruction() -> str:
    joined = "\u3001".join(REQUIRED_H2)
    return (
        f"\u8bf7\u56f4\u7ed5\u300a{TITLE}\u300b\u751f\u6210\u4e00\u4efd\u4e2d\u6587\u5b66\u672f\u77ed\u7a3f\uff0c\u7528\u4e8e\u9a8c\u8bc1\u53c2\u8003\u6587\u732e\u4fee\u590d\u94fe\u8def\u3002\n"
        f"\u5fc5\u987b\u5305\u542b\u4ee5\u4e0b\u4e8c\u7ea7\u7ae0\u8282\u4e14\u987a\u5e8f\u56fa\u5b9a\uff1a{joined}\u3002\n"
        "\u4ec5\u8f93\u51fa\u6700\u7ec8\u6b63\u6587\uff0c\u4e0d\u5f97\u8f93\u51fa\u63d0\u793a\u8bcd\u3001\u8bf4\u660e\u8bed\u6216\u8fc7\u7a0b\u63cf\u8ff0\u3002\n"
        "\u82e5\u521d\u59cb\u53c2\u8003\u6587\u732e\u4e0d\u8db3\uff0c\u7cfb\u7edf\u5e94\u7ee7\u7eed\u4fee\u590d\u5e76\u7ed9\u51fa\u7ed3\u6784\u5316\u53c2\u8003\u6587\u732e\u3002"
    )

def main() -> int:
    configure_env()
    os.environ["WRITING_AGENT_MIN_REFERENCE_ITEMS"] = "8"
    os.environ["WRITING_AGENT_ENFORCE_REFERENCE_MIN"] = "1"
    os.environ["WRITING_AGENT_RAG_THEME_GATE_ENABLED"] = "0"

    original_collect = runtime_module._collect_reference_sources
    original_fallback = runtime_module._fallback_reference_sources

    def forced_collect(evidence_map, query: str = ""):
        rows = list(original_collect(evidence_map, query=query) or [])
        if rows:
            return rows[:2]
        return _repair_fallback_sources()[:2]

    def forced_fallback(*, instruction: str = ""):
        return _repair_fallback_sources()

    runtime_module._collect_reference_sources = forced_collect
    runtime_module._fallback_reference_sources = forced_fallback
    try:
        run_root = Path("deliverables").resolve() / f"codex_reference_repair_smoke_{now_stamp()}"
        run_root.mkdir(parents=True, exist_ok=True)
        out_dir = run_root / "codex_openai_compat"
        out_dir.mkdir(parents=True, exist_ok=True)

        client = TestClient(app_v2.app)
        root_resp = client.get("/", follow_redirects=False)
        if root_resp.status_code != 303:
            raise RuntimeError(f"create doc failed: {root_resp.status_code} {root_resp.text[:200]}")
        doc_id = parse_doc_id_from_redirect(root_resp)
        set_resp = client.post(f"/api/doc/{doc_id}/settings", json=settings_payload())
        if set_resp.status_code != 200:
            raise RuntimeError(f"save settings failed: {set_resp.status_code} {set_resp.text[:200]}")

        cfg = app_v2.GenerateConfig(workers=4, min_total_chars=1800, max_total_chars=0)
        events: list[dict[str, Any]] = []
        final_payload: dict[str, Any] = {}
        started = time.time()
        generator = app_v2.run_generate_graph(
            instruction=build_instruction(),
            current_text="",
            required_h2=list(REQUIRED_H2),
            required_outline=[(2, sec) for sec in REQUIRED_H2],
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

        raw_events = out_dir / "raw_events.jsonl"
        raw_events.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in events) + "\n", encoding="utf-8")
        final_text = str(final_payload.get("text") or "")
        (out_dir / "final_output.md").write_text(final_text, encoding="utf-8")
        figure_manifest = export_rendered_figure_assets(final_text, out_dir / "figure_assets")
        dl = client.get(f"/download/{doc_id}.docx")
        if dl.status_code == 200 and dl.content:
            (out_dir / "final_output.docx").write_bytes(dl.content)

        repair_events = [row for row in events if row.get("event") == "reference_repair"]
        quality_snapshot = final_payload.get("quality_snapshot") if isinstance(final_payload.get("quality_snapshot"), dict) else {}
        section_originality_hot_sample = extract_section_originality_summary(quality_snapshot)
        summary = {
            "doc_id": doc_id,
            "reference_repair_count": len(repair_events),
            "reference_repair_last": repair_events[-1]["payload"] if repair_events else {},
            "final_status": str(final_payload.get("status") or ""),
            "runtime_status": str(final_payload.get("runtime_status") or ""),
            "quality_passed": bool(final_payload.get("quality_passed", False)),
            "quality_failure_reason": str(final_payload.get("quality_failure_reason") or ""),
            "quality_snapshot": quality_snapshot,
            "section_originality_hot_sample": section_originality_hot_sample,
            "events_file": str(raw_events.resolve()),
            "final_markdown_file": str((out_dir / "final_output.md").resolve()),
            "final_docx_file": str((out_dir / "final_output.docx").resolve()) if (out_dir / "final_output.docx").exists() else "",
            "figure_assets_dir": str((out_dir / "figure_assets").resolve()),
            "figure_manifest_file": str((out_dir / "figure_assets" / "manifest.json").resolve()),
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
        }
        (run_root / "REFERENCE_REPAIR_SMOKE_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if repair_events else 1
    finally:
        runtime_module._collect_reference_sources = original_collect
        runtime_module._fallback_reference_sources = original_fallback


if __name__ == "__main__":
    raise SystemExit(main())
