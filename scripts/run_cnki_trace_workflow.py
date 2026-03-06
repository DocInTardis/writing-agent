#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run a full CNKI-title benchmark workflow with complete stage tracing.

Outputs:
1) Full SSE event stream JSON (all stages)
2) Planner/section/final DocIR snapshots
3) Quality comparison + revise rounds
4) Final Markdown report document
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
import zipfile

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.v2.doc_ir import from_text as doc_ir_from_text
from writing_agent.v2.doc_ir import to_dict as doc_ir_to_dict


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_doc_id_from_redirect(resp) -> str:
    location = str(resp.headers.get("location") or "")
    if "/workbench/" not in location:
        raise RuntimeError(f"cannot parse doc_id from redirect: {location}")
    return location.split("/workbench/")[-1].strip()


def safe_json_load(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except Exception:
        return {"_raw": raw}
    return data if isinstance(data, dict) else {"_raw": raw}


@dataclass
class QualityResult:
    score: float
    passed: bool
    chars: int
    h2_count: int
    refs_count: int
    table_markers: int
    figure_markers: int
    avg_section_chars: float
    missing_required: list[str]
    deficits: list[str]


def split_h2_sections(text: str) -> list[tuple[str, str]]:
    src = str(text or "")
    lines = src.splitlines()
    idxs: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^\s*##\s+(.+?)\s*$", line)
        if m:
            idxs.append((i, m.group(1).strip()))
    if not idxs:
        return []
    out: list[tuple[str, str]] = []
    for n, (start_i, title) in enumerate(idxs):
        end_i = idxs[n + 1][0] if n + 1 < len(idxs) else len(lines)
        body = "\n".join(lines[start_i + 1 : end_i]).strip()
        out.append((title, body))
    return out


def evaluate_quality(text: str) -> QualityResult:
    src = str(text or "")
    chars = compact_len(src)
    h2_sections = split_h2_sections(src)
    h2_count = len(h2_sections)
    refs_count = len(re.findall(r"(?m)^\s*\[\d+\]\s+", src))
    table_markers = len(re.findall(r"\[\[TABLE:", src))
    figure_markers = len(re.findall(r"\[\[FIGURE:", src))
    non_ref_bodies = [body for title, body in h2_sections if "参考文献" not in title]
    avg_section_chars = (
        sum(compact_len(x) for x in non_ref_bodies) / float(len(non_ref_bodies))
        if non_ref_bodies
        else 0.0
    )
    required_tokens = [
        "摘要",
        "关键词",
        "引言",
        "相关研究",
        "研究方法",
        "系统设计",
        "实验",
        "讨论",
        "结论",
        "参考文献",
    ]
    missing_required = [tok for tok in required_tokens if tok not in src]

    # Weighted score (100).
    score = 0.0
    score += min(30.0, (chars / 12000.0) * 30.0)
    score += min(15.0, (h2_count / 8.0) * 15.0)
    score += min(15.0, (refs_count / 18.0) * 15.0)
    score += min(10.0, (table_markers / 2.0) * 10.0)
    score += min(10.0, (figure_markers / 2.0) * 10.0)
    score += min(10.0, (avg_section_chars / 700.0) * 10.0)
    score += max(0.0, 10.0 - float(len(missing_required)) * 1.5)

    deficits: list[str] = []
    if chars < 12000:
        deficits.append(f"正文字数不足: {chars} < 12000")
    if h2_count < 8:
        deficits.append(f"二级章节不足: {h2_count} < 8")
    if refs_count < 18:
        deficits.append(f"参考文献不足: {refs_count} < 18")
    if table_markers < 2:
        deficits.append(f"表格标记不足: {table_markers} < 2")
    if figure_markers < 2:
        deficits.append(f"图示标记不足: {figure_markers} < 2")
    if avg_section_chars < 700:
        deficits.append(f"章节平均长度不足: {avg_section_chars:.1f} < 700")
    if missing_required:
        deficits.append("缺少必要章节关键词: " + "、".join(missing_required))

    passed = (score >= 80.0) and (not deficits)
    return QualityResult(
        score=round(score, 2),
        passed=passed,
        chars=chars,
        h2_count=h2_count,
        refs_count=refs_count,
        table_markers=table_markers,
        figure_markers=figure_markers,
        avg_section_chars=round(avg_section_chars, 2),
        missing_required=missing_required,
        deficits=deficits,
    )


def build_full_markdown(title: str, sections_order: list[str], section_text: dict[str, str]) -> str:
    lines = [f"# {title}".strip(), ""]
    for sec in sections_order:
        lines.append(f"## {sec}".strip())
        lines.append("")
        lines.append(str(section_text.get(sec) or "").strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def docir_of_text(text: str) -> dict[str, Any]:
    try:
        return doc_ir_to_dict(doc_ir_from_text(text))
    except Exception as exc:
        return {"_error": f"doc_ir_convert_failed: {exc}", "_text_preview": str(text or "")[:2000]}


def extract_text_nodes_from_docx_bytes(payload: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    return re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml)


def run(args: argparse.Namespace) -> int:
    # Force detailed legacy graph stream so planner/section events are available.
    os.environ["WRITING_AGENT_USE_ROUTE_GRAPH"] = "0"
    os.environ["WRITING_AGENT_FAST_GENERATE"] = "0"
    os.environ["WRITING_AGENT_FAST_PLAN"] = "0"
    os.environ["WRITING_AGENT_FAST_CPU"] = "100"
    os.environ["WRITING_AGENT_FAST_MEM"] = "100"
    os.environ["WRITING_AGENT_ENFORCE_INSTRUCTION_REQUIREMENTS"] = "1"
    os.environ["WRITING_AGENT_STREAM_EVENT_TIMEOUT_S"] = str(max(120, int(args.stream_timeout_s)))
    os.environ["WRITING_AGENT_STREAM_MAX_S"] = str(max(360, int(args.stream_timeout_s) * 2))
    os.environ["WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S"] = str(max(120, int(args.stream_timeout_s)))
    os.environ["WRITING_AGENT_NONSTREAM_MAX_S"] = str(max(360, int(args.stream_timeout_s) * 2))

    run_dir = Path(args.out_dir).resolve() / f"cnki_trace_workflow_{now_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)

    benchmark = {
        "source": "CNKI(知网)",
        "title": "“区块链+农村社会化服务”研究现状与研究热点分析——基于Cite Space的可视化分析",
        "cnki_url": "https://kns.cnki.net/kcms2/article/abstract?v=VfBi72W4rs4fS5Qq7ei1BbMcfH4I2f7ix4R47X0Q4cnksizNc6jxt2RZ4wHVeTjj_D7SObhlN4MzVC8zhPgIhC9h7weRzlyQYwJpxQv_rwtIkdX5UXXGww==&uniplatform=NZKPT&language=CHS",
        "source_note": "标题来自知网条目（通过公开检索页抓取到的CNKI详情链接）。",
    }

    complex_prompt = f"""
请以《{benchmark["title"]}》为题，产出一篇中文学术论文初稿，对标知网期刊论文写作质量。
硬性要求：
1. 标题必须完全一致，不得改写；
2. 全文中文字符数 12000-15000（不含空格）；
3. 结构必须包含并按顺序出现：摘要、关键词、1 引言、2 相关研究、3 研究方法、4 系统设计与实现、5 实验设计与结果、6 讨论、7 结论、参考文献；
4. 每个二级章节至少 3 个自然段，每段不少于 120 字；
5. 文中必须包含至少 2 个表格标记与 2 个图示标记，格式分别为 [[TABLE:{{...}}]] 与 [[FIGURE:{{...}}]]；
6. 参考文献不少于 18 条，按 [n] 编号，条目须为可核验学术来源写法；
7. 用语必须学术化、可复现、避免空泛套话和口语；
8. 不得输出提示词，不得出现“作为AI”或类似措辞；
9. 如果不满足以上约束，优先补齐完整内容再结束输出。
""".strip()

    client = TestClient(app_v2.app)
    root_resp = client.get("/", follow_redirects=False)
    if root_resp.status_code != 303:
        raise RuntimeError(f"create doc failed: {root_resp.status_code} {root_resp.text[:300]}")
    doc_id = parse_doc_id_from_redirect(root_resp)

    # Set doc preferences first.
    settings_payload = {
        "generation_prefs": {
            "purpose": "学术论文",
            "target_char_count": 13000,
            "target_length_confirmed": True,
            "include_cover": True,
            "include_toc": True,
            "toc_levels": 3,
            "page_numbers": True,
            "include_header": True,
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
    settings_resp = client.post(f"/api/doc/{doc_id}/settings", json=settings_payload)
    if settings_resp.status_code != 200:
        raise RuntimeError(f"save settings failed: {settings_resp.status_code} {settings_resp.text[:500]}")

    # Stage 1: direct graph generation and capture all events.
    events: list[dict[str, Any]] = []
    final_payload: dict[str, Any] = {}
    started = time.time()
    graph_cfg = app_v2.GenerateConfig(
        workers=int(os.environ.get("WRITING_AGENT_WORKERS", "12")),
        min_total_chars=12000,
        max_total_chars=0,
    )
    generator = app_v2.run_generate_graph(
        instruction=complex_prompt,
        current_text="",
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        config=graph_cfg,
    )
    per_event_s = max(60.0, float(args.stream_timeout_s))
    overall_s = max(300.0, float(args.stream_timeout_s) * 3.0)
    for ev in app_v2._iter_with_timeout(generator, per_event=per_event_s, overall=overall_s):
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

    raw_events_path = run_dir / "raw_events.jsonl"
    with raw_events_path.open("w", encoding="utf-8") as f:
        for row in events:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if not final_payload:
        raise RuntimeError("graph generation finished without final payload")

    current_text = str(final_payload.get("text") or "")
    if not current_text.strip():
        raise RuntimeError("final payload text is empty")

    # Extract stage-level artifacts.
    analysis_payload = {}
    struct_plan_payload = {}
    plan_payload = {}
    targets_payload = {}
    for row in events:
        ev = str(row.get("event") or "")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if ev == "analysis" and not analysis_payload:
            analysis_payload = payload
        elif ev == "struct_plan" and not struct_plan_payload:
            struct_plan_payload = payload
        elif ev == "plan" and not plan_payload:
            plan_payload = payload
        elif ev == "targets" and not targets_payload:
            targets_payload = payload

    plan_title = (
        str((struct_plan_payload.get("plan") or {}).get("title") or "")
        if isinstance(struct_plan_payload.get("plan"), dict)
        else ""
    )
    if not plan_title:
        plan_title = str(plan_payload.get("title") or benchmark["title"])
    plan_sections = [str(x) for x in (plan_payload.get("sections") or []) if str(x).strip()]

    # Build agent snapshots (planner + per-section + final aggregate) with DocIR.
    agent_docir_snapshots: list[dict[str, Any]] = []
    planner_md = "# {title}\n\n## 规划\n\n{items}\n".format(
        title=plan_title,
        items="\n".join([f"- {x}" for x in plan_sections]) if plan_sections else "- 无显式规划",
    )
    agent_docir_snapshots.append(
        {
            "agent": "planner",
            "event_seq": 0,
            "markdown_chars": compact_len(planner_md),
            "doc_ir": docir_of_text(planner_md),
            "planner_json": {
                "analysis": analysis_payload,
                "struct_plan": struct_plan_payload,
                "plan": plan_payload,
                "targets": targets_payload,
            },
        }
    )

    section_buffers: dict[str, str] = {}
    completed_sections: list[str] = []
    for row in events:
        ev = str(row.get("event") or "")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if ev != "section":
            continue
        sec = str(payload.get("section") or "").strip()
        phase = str(payload.get("phase") or "").strip().lower()
        if not sec:
            continue
        if phase == "delta":
            section_buffers[sec] = (section_buffers.get(sec, "") + str(payload.get("delta") or "")).strip()
        elif phase == "end":
            if sec not in completed_sections:
                completed_sections.append(sec)
            use_order = [s for s in plan_sections if s in completed_sections] + [
                s for s in completed_sections if s not in plan_sections
            ]
            snap_md = build_full_markdown(plan_title or benchmark["title"], use_order, section_buffers)
            agent_docir_snapshots.append(
                {
                    "agent": f"section_drafter::{sec}",
                    "event_seq": int(row.get("seq") or 0),
                    "section": sec,
                    "completed_sections": list(use_order),
                    "section_chars": compact_len(section_buffers.get(sec, "")),
                    "markdown_chars": compact_len(snap_md),
                    "doc_ir": docir_of_text(snap_md),
                }
            )

    final_doc_ir = final_payload.get("doc_ir") if isinstance(final_payload.get("doc_ir"), dict) else {}
    if not final_doc_ir:
        final_doc_ir = docir_of_text(current_text)
    agent_docir_snapshots.append(
        {
            "agent": "aggregate_final",
            "event_seq": len(events),
            "markdown_chars": compact_len(current_text),
            "doc_ir": final_doc_ir,
            "problems": list(final_payload.get("problems") or []),
        }
    )

    stage_summary = {
        "doc_id": doc_id,
        "event_count": len(events),
        "analysis": analysis_payload,
        "struct_plan": struct_plan_payload,
        "plan": plan_payload,
        "targets": targets_payload,
        "prompt_routes": [
            {
                "seq": row.get("seq"),
                "stage": str((row.get("payload") or {}).get("stage") or ""),
                "metadata": dict((row.get("payload") or {}).get("metadata") or {}),
            }
            for row in events
            if str(row.get("event") or "") == "prompt_route"
        ],
        "quality_gate": {
            "problems": list(final_payload.get("problems") or []),
            "quality_snapshot": dict(final_payload.get("quality_snapshot") or {}),
        },
        "terminal": {
            "status": str(final_payload.get("status") or ""),
            "failure_reason": str(final_payload.get("failure_reason") or ""),
            "quality_snapshot": dict(final_payload.get("quality_snapshot") or {}),
        },
        "fallback_path": {
            "route_path": str(
                (final_payload.get("trace_context") or {}).get("route_path")
                or (final_payload.get("graph_meta") or {}).get("path")
                or "legacy_graph"
            ),
            "fallback_trigger": str((final_payload.get("trace_context") or {}).get("fallback_trigger") or ""),
            "fallback_recovered": bool((final_payload.get("trace_context") or {}).get("fallback_recovered") is True),
        },
    }

    (run_dir / "stage_summary.json").write_text(
        json.dumps(stage_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "agent_docir_snapshots.json").write_text(
        json.dumps(agent_docir_snapshots, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Quality compare and revise rounds.
    rounds: list[dict[str, Any]] = []
    quality = evaluate_quality(current_text)
    rounds.append(
        {
            "round": 0,
            "type": "generate",
            "quality": asdict(quality),
            "text_chars": compact_len(current_text),
        }
    )

    failed = False
    failure_reason = ""
    for ridx in range(1, int(args.max_revise_rounds) + 1):
        if quality.passed:
            break
        revise_instruction = (
            f"请对整篇论文做深度学术化修订，标题必须保持《{benchmark['title']}》完全一致。\n"
            f"当前质量缺陷：{'; '.join(quality.deficits)}。\n"
            "修订要求：\n"
            "1) 在不删减已有有效内容的前提下，补齐缺失章节与细节；\n"
            "2) 明显扩展方法、实验、结果分析与讨论；\n"
            "3) 参考文献补足到至少18条，格式规范；\n"
            "4) 保留并补足[[TABLE:...]]和[[FIGURE:...]]标记不少于2个；\n"
            "5) 输出完整修订后的全文，不要解释。"
        )
        revise_payload = {
            "instruction": revise_instruction,
            "text": current_text,
            "allow_unscoped_fallback": False,
        }
        revise_resp = client.post(f"/api/doc/{doc_id}/revise", json=revise_payload)
        if revise_resp.status_code != 200:
            failed = True
            failure_reason = f"revise_api_failed_round_{ridx}: {revise_resp.status_code} {revise_resp.text[:400]}"
            rounds.append(
                {
                    "round": ridx,
                    "type": "revise",
                    "request": revise_payload,
                    "response_status": revise_resp.status_code,
                    "response_body": revise_resp.text[:1200],
                    "result": "failed",
                }
            )
            break
        revise_data = revise_resp.json() if revise_resp.content else {}
        revised_text = str(revise_data.get("text") or "")
        changed_chars = abs(compact_len(revised_text) - compact_len(current_text))
        if not revised_text.strip():
            failed = True
            failure_reason = f"revise_empty_output_round_{ridx}"
            rounds.append(
                {
                    "round": ridx,
                    "type": "revise",
                    "request": revise_payload,
                    "response": revise_data,
                    "result": "failed",
                    "reason": failure_reason,
                }
            )
            break
        current_text = revised_text
        quality = evaluate_quality(current_text)
        rounds.append(
            {
                "round": ridx,
                "type": "revise",
                "request": revise_payload,
                "response_meta": {
                    "keys": list(revise_data.keys()),
                    "changed_chars": changed_chars,
                    "doc_ir_present": isinstance(revise_data.get("doc_ir"), dict),
                    "revision_meta": revise_data.get("revision_meta"),
                },
                "quality": asdict(quality),
                "result": "passed" if quality.passed else "not_passed",
            }
        )
        if not quality.passed and ridx >= int(args.max_revise_rounds):
            failed = True
            failure_reason = "quality_still_below_cnki_threshold_after_revise_rounds"

    if (not failed) and (not quality.passed):
        failed = True
        failure_reason = "quality_not_passed"

    (run_dir / "quality_rounds.json").write_text(
        json.dumps(rounds, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Persist final text into doc session via save endpoint (explicit).
    save_payload = {
        "text": current_text,
        "generation_prefs": settings_payload["generation_prefs"],
        "formatting": settings_payload["formatting"],
    }
    save_resp = client.post(f"/api/doc/{doc_id}/save", json=save_payload)
    save_ok = save_resp.status_code == 200

    final_docx_path = run_dir / "final_output.docx"
    docx_meta: dict[str, Any] = {"download_status": 0, "path": ""}
    dl = client.get(f"/download/{doc_id}.docx")
    if dl.status_code == 200 and dl.content:
        final_docx_path.write_bytes(dl.content)
        text_nodes = extract_text_nodes_from_docx_bytes(dl.content)
        docx_meta = {
            "download_status": 200,
            "path": str(final_docx_path),
            "text_nodes": len(text_nodes),
            "question_mark_count_in_text_nodes": sum(x.count("?") for x in text_nodes),
        }
    else:
        docx_meta = {"download_status": dl.status_code, "body_preview": (dl.text or "")[:500]}

    final_md_path = run_dir / "final_output.md"
    final_md_path.write_text(current_text, encoding="utf-8")

    outcome = {
        "status": "failed" if failed else "passed",
        "failure_reason": failure_reason,
        "benchmark": benchmark,
        "doc_id": doc_id,
        "save_ok": save_ok,
        "save_status": save_resp.status_code,
        "final_quality": asdict(quality),
        "docx_meta": docx_meta,
        "events_file": str(raw_events_path),
        "stage_summary_file": str(run_dir / "stage_summary.json"),
        "agent_docir_file": str(run_dir / "agent_docir_snapshots.json"),
        "quality_rounds_file": str(run_dir / "quality_rounds.json"),
        "final_markdown_file": str(final_md_path),
        "final_docx_file": str(final_docx_path) if final_docx_path.exists() else "",
        "fallback_path": dict(stage_summary.get("fallback_path") or {}),
    }
    (run_dir / "outcome.json").write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")

    # Build one consolidated report document (requested).
    report_path = run_dir / "CNKI_BENCHMARK_FULL_TRACE_REPORT.md"
    report_lines: list[str] = []
    report_lines.append(f"# CNKI 对标全流程报告（{now_stamp()}）")
    report_lines.append("")
    report_lines.append("## 0. 执行结论")
    report_lines.append("")
    report_lines.append(f"- 状态: `{outcome['status']}`")
    report_lines.append(f"- 失败原因: `{failure_reason or 'N/A'}`")
    report_lines.append(f"- 文档ID: `{doc_id}`")
    report_lines.append(f"- 最终质量分: `{quality.score}`")
    report_lines.append(f"- 路由路径: `{(stage_summary.get('fallback_path') or {}).get('route_path') or ''}`")
    report_lines.append(f"- 降级触发: `{(stage_summary.get('fallback_path') or {}).get('fallback_trigger') or 'N/A'}`")
    report_lines.append(f"- 是否恢复: `{bool((stage_summary.get('fallback_path') or {}).get('fallback_recovered') is True)}`")
    report_lines.append("")
    report_lines.append("## 1. 对标来源（知网标题）")
    report_lines.append("")
    report_lines.append(f"- 标题: `{benchmark['title']}`")
    report_lines.append(f"- CNKI链接: {benchmark['cnki_url']}")
    report_lines.append(f"- 说明: {benchmark['source_note']}")
    report_lines.append("")
    report_lines.append("## 2. 复杂 Prompt（原文）")
    report_lines.append("")
    report_lines.append("```text")
    report_lines.append(complex_prompt)
    report_lines.append("```")
    report_lines.append("")
    report_lines.append("## 3. Planner 与阶段 JSON")
    report_lines.append("")
    report_lines.append("### 3.1 analysis")
    report_lines.append("```json")
    report_lines.append(json.dumps(analysis_payload, ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    report_lines.append("### 3.2 struct_plan")
    report_lines.append("```json")
    report_lines.append(json.dumps(struct_plan_payload, ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    report_lines.append("### 3.3 plan")
    report_lines.append("```json")
    report_lines.append(json.dumps(plan_payload, ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    report_lines.append("### 3.4 targets")
    report_lines.append("```json")
    report_lines.append(json.dumps(targets_payload, ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    report_lines.append("## 4. 每个 Agent 阶段 DocIR（完整）")
    report_lines.append("")
    report_lines.append("```json")
    report_lines.append(json.dumps(agent_docir_snapshots, ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    report_lines.append("## 5. 修订轮次与质量评估 JSON")
    report_lines.append("")
    report_lines.append("```json")
    report_lines.append(json.dumps(rounds, ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    report_lines.append("## 6. 生成事件流（完整 SSE 事件 JSON）")
    report_lines.append("")
    report_lines.append("```json")
    report_lines.append(json.dumps(events, ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    report_lines.append("## 7. 文件清单")
    report_lines.append("")
    report_lines.append(f"- `raw_events.jsonl`: `{raw_events_path}`")
    report_lines.append(f"- `stage_summary.json`: `{run_dir / 'stage_summary.json'}`")
    report_lines.append(f"- `agent_docir_snapshots.json`: `{run_dir / 'agent_docir_snapshots.json'}`")
    report_lines.append(f"- `quality_rounds.json`: `{run_dir / 'quality_rounds.json'}`")
    report_lines.append(f"- `outcome.json`: `{run_dir / 'outcome.json'}`")
    report_lines.append(f"- `final_output.md`: `{final_md_path}`")
    report_lines.append(f"- `final_output.docx`: `{final_docx_path if final_docx_path.exists() else 'N/A'}`")
    report_lines.append("")
    report_lines.append("## 8. 失败判定原因分析（如失败）")
    report_lines.append("")
    if failed:
        report_lines.append(f"- 判定: `FAIL`")
        report_lines.append(f"- 原因: `{failure_reason}`")
        report_lines.append("- 解释: 系统已执行“生成→评估→修订”链路，仍未满足对标阈值，按要求停止并标记失败。")
    else:
        report_lines.append("- 判定: `PASS`")
        report_lines.append("- 说明: 达到本次对标阈值。")
    report_lines.append("")

    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    # Console summary for operator.
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    print(str(report_path))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CNKI benchmark workflow with full trace.")
    parser.add_argument("--out-dir", default="deliverables", help="Output directory root")
    parser.add_argument("--stream-timeout-s", type=int, default=300, help="Stream timeout baseline seconds")
    parser.add_argument("--max-revise-rounds", type=int, default=2, help="Max revise rounds after initial generation")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
