#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fast smoke test for codex_openai_compat generation."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.v2.final_validator import validate_final_document
from writing_agent.v2.meta_firewall import MetaFirewall
from writing_agent.v2.figure_render import export_rendered_figure_assets

TITLE = "“区块链+农村社会化服务”研究现状与研究热点分析——基于CiteSpace的可视化分析"
REQUIRED_H2 = [
    "摘要",
    "关键词",
    "引言",
    "数据来源与检索策略",
    "结论",
    "参考文献",
]


@dataclass
class SmokeQuality:
    passed: bool
    chars: int
    refs_count: int
    h2_count: int
    missing_sections: list[str]
    meta_hits: list[str]
    validator: dict[str, Any]
    deficits: list[str]


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def parse_doc_id_from_redirect(resp) -> str:
    location = str(resp.headers.get("location") or "")
    if "/workbench/" not in location:
        raise RuntimeError(f"cannot parse doc_id from redirect: {location}")
    return location.split("/workbench/")[-1].strip()


def _load_openai_key_if_missing() -> None:
    if str(os.environ.get("WRITING_AGENT_OPENAI_API_KEY") or "").strip():
        return
    auth_file = Path.home() / ".codex" / "auth.json"
    if not auth_file.exists():
        return
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
    except Exception:
        return
    key = str(data.get("OPENAI_API_KEY") or "").strip()
    if key:
        os.environ["WRITING_AGENT_OPENAI_API_KEY"] = key


def _set_env_default(key: str, value: str) -> None:
    if str(os.environ.get(key) or "").strip():
        return
    os.environ[key] = value


def configure_env() -> None:
    _load_openai_key_if_missing()
    if not str(os.environ.get("WRITING_AGENT_OPENAI_API_KEY") or "").strip():
        raise RuntimeError("missing WRITING_AGENT_OPENAI_API_KEY")
    _set_env_default("WRITING_AGENT_LLM_PROVIDER", "openai")
    os.environ["WRITING_AGENT_OPENAI_BASE_URL"] = str(
        os.environ.get("WRITING_AGENT_OPENAI_BASE_URL", "https://vpsairobot.com/v1")
    ).strip()
    _set_env_default("WRITING_AGENT_OPENAI_MODEL", "gpt-5.4")
    _set_env_default("WRITING_AGENT_MODEL", os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-5.4"))
    _set_env_default("WRITING_AGENT_AGG_MODEL", os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-5.4"))
    _set_env_default("WRITING_AGENT_WORKER_MODELS", os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-5.4"))
    _set_env_default("WRITING_AGENT_OPENAI_TIMEOUT_S", "180")

    _set_env_default("WRITING_AGENT_USE_ROUTE_GRAPH", "0")
    _set_env_default("WRITING_AGENT_FAST_GENERATE", "0")
    _set_env_default("WRITING_AGENT_FAST_PLAN", "1")
    _set_env_default("WRITING_AGENT_ANALYSIS_FAST", "force")
    _set_env_default("WRITING_AGENT_FAST_DRAFT", "0")
    _set_env_default("WRITING_AGENT_STRICT_JSON", "1")
    _set_env_default("WRITING_AGENT_ENFORCE_FINAL_VALIDATION", "1")
    _set_env_default("WRITING_AGENT_ENFORCE_META_FIREWALL", "1")
    _set_env_default("WRITING_AGENT_ENFORCE_CONTRACT_SLOTS", "1")
    _set_env_default("WRITING_AGENT_EVIDENCE_ENABLED", "0")
    _set_env_default("WRITING_AGENT_RAG_THEME_GATE_ENABLED", "0")
    _set_env_default("WRITING_AGENT_RAG_TOP_K", "3")
    _set_env_default("WRITING_AGENT_RAG_PER_PAPER", "1")
    _set_env_default("WRITING_AGENT_RAG_MAX_CHARS", "1600")
    _set_env_default("WRITING_AGENT_FORCE_REQUIRED_OUTLINE_ONLY", "1")
    _set_env_default("WRITING_AGENT_REQUIRED_OUTLINE_ONLY", "1")
    _set_env_default("WRITING_AGENT_OPENALEX_MAX_RESULTS", "12")
    _set_env_default("WRITING_AGENT_MIN_REFERENCE_ITEMS", "6")
    _set_env_default("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "0")
    _set_env_default("WRITING_AGENT_PARADIGM_OVERRIDE", "bibliometric")
    _set_env_default("WRITING_AGENT_PROVIDER_PREFLIGHT_CHAT", "0")
    _set_env_default("WRITING_AGENT_PER_MODEL_CONCURRENCY", "6")
    _set_env_default("WRITING_AGENT_EVIDENCE_WORKERS", "8")
    _set_env_default("WRITING_AGENT_EVIDENCE_TIMEOUT_S", "25")
    _set_env_default("WRITING_AGENT_RAG_AUTO_FETCH_ENABLED", "0")
    _set_env_default("WRITING_AGENT_RAG_EXPAND_ENABLED", "0")
    _set_env_default("WRITING_AGENT_RAG_ONLINE_FILL_ENABLED", "0")
    _set_env_default("WRITING_AGENT_SECTION_CONTINUE_ROUNDS", "0")
    _set_env_default("WRITING_AGENT_SKIP_PLAN_DETAIL", "1")
    _set_env_default("WRITING_AGENT_ALLOW_SKIP_PLAN_DETAIL", "1")
    _set_env_default("WRITING_AGENT_RUNTIME_PROFILE", "smoke")
    _set_env_default("WRITING_AGENT_SECTION_CONTRACT_SCALE", "0.55")
    _set_env_default("WRITING_AGENT_REFERENCE_ONLINE_PROVIDERS", "crossref")
    _set_env_default("WRITING_AGENT_REFERENCE_QUERY_SEED_CAP", "3")
    _set_env_default("WRITING_AGENT_REFERENCE_ONLINE_PER_SEED", "6")

    _set_env_default("WRITING_AGENT_PLAN_TIMEOUT_S", "180")
    _set_env_default("WRITING_AGENT_ANALYSIS_TIMEOUT_S", "180")
    _set_env_default("WRITING_AGENT_SECTION_TIMEOUT_S", "300")
    _set_env_default("WRITING_AGENT_STREAM_EVENT_TIMEOUT_S", "300")
    _set_env_default("WRITING_AGENT_STREAM_MAX_S", "600")
    _set_env_default("WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S", "300")
    _set_env_default("WRITING_AGENT_NONSTREAM_MAX_S", "600")


def build_instruction() -> str:
    joined = "、".join(REQUIRED_H2)
    return (
        f"请围绕《{TITLE}》生成一份中文学术论文冒烟稿，用于快速验证系统结构、语言质量、元指令清洁度与导出链路。\n"
        "要求：\n"
        f"1. 仅输出正文，必须包含以下二级章节且顺序固定：{joined}。\n"
        "2. 正文目标约2400字，允许略有浮动，但不得输出模板说明、写作提示或过程性话语。\n"
        "3. 摘要简洁完整；关键词3至5个；引言交代背景与问题；数据来源与检索策略说明数据范围、检索式、工具与参数；结论给出总结与不足。\n"
        "4. 参考文献至少8条，使用 [1] [2] 形式逐条列出，不得重复，不得留空。\n"
        "5. 不得出现 section_id、block_id、type、items、caption、columns、rows 等结构化残留。\n"
        "6. 不得出现“本节应”“需要补充”“围绕……展开”等元指令句式。"
    )


def settings_payload() -> dict[str, Any]:
    return {
        "generation_prefs": {
            "purpose": "学术论文",
            "target_char_count": 2000,
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


def evaluate_quality(text: str) -> SmokeQuality:
    headings = re.findall(r"(?m)^##\s+(.+?)\s*$", str(text or ""))
    refs_count = len(re.findall(r"(?m)^\s*\[\d+\]\s+", str(text or "")))
    missing = [sec for sec in REQUIRED_H2 if sec not in headings]
    meta_scan = MetaFirewall().scan(str(text or ""))
    validator = validate_final_document(
        title=TITLE,
        text=str(text or ""),
        sections=REQUIRED_H2,
        problems=[],
        rag_gate_dropped=[],
    )
    deficits: list[str] = []
    chars = compact_len(text)
    if chars < 1800:
        deficits.append(f"正文长度不足: {chars} < 2200")
    if refs_count < 6:
        deficits.append(f"??????: {refs_count} < 6")
    if missing:
        deficits.append("缺失章节: " + "、".join(missing))
    if meta_scan.has_meta:
        deficits.append("存在元指令残留")
    if not bool(validator.get("passed")):
        deficits.append("最终验证未通过")
    return SmokeQuality(
        passed=len(deficits) == 0,
        chars=chars,
        refs_count=refs_count,
        h2_count=len(headings),
        missing_sections=missing,
        meta_hits=list(meta_scan.fragments[:8]),
        validator=validator,
        deficits=deficits,
    )


def main() -> int:
    configure_env()
    run_root = Path("deliverables").resolve() / f"codex_smoke_test_{now_stamp()}"
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

    cfg = app_v2.GenerateConfig(workers=8, min_total_chars=2000, max_total_chars=0)
    started = time.time()
    events: list[dict[str, Any]] = []
    final_payload: dict[str, Any] = {}
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

    if not final_payload:
        final_payload = {
            "event": "final",
            "text": "",
            "status": "failed",
            "failure_reason": "missing_final_payload",
            "problems": ["missing_final_payload"],
        }
        events.append({"seq": len(events) + 1, "t_rel_s": round(time.time() - started, 3), "event": "final", "payload": final_payload})

    raw_events = out_dir / "raw_events.jsonl"
    with raw_events.open("w", encoding="utf-8") as f:
        for row in events:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    text = str(final_payload.get("text") or "")
    final_md = out_dir / "final_output.md"
    final_md.write_text(text, encoding="utf-8")
    figure_manifest = export_rendered_figure_assets(text, out_dir / "figure_assets")

    save_resp = client.post(
        f"/api/doc/{doc_id}/save",
        json={
            "text": text,
            "generation_prefs": settings_payload()["generation_prefs"],
            "formatting": settings_payload()["formatting"],
        },
    )
    final_docx = out_dir / "final_output.docx"
    dl = client.get(f"/download/{doc_id}.docx")
    if dl.status_code == 200 and dl.content:
        final_docx.write_bytes(dl.content)

    quality = evaluate_quality(text)
    outcome = {
        "run_root": str(run_root),
        "profile": "codex_openai_compat",
        "doc_id": doc_id,
        "status": str(final_payload.get("status") or "failed"),
        "failure_reason": str(final_payload.get("failure_reason") or ""),
        "runtime_status": str(final_payload.get("runtime_status") or final_payload.get("status") or "failed"),
        "runtime_failure_reason": str(final_payload.get("runtime_failure_reason") or ""),
        "quality_passed": bool(final_payload.get("quality_passed", False)),
        "quality_failure_reason": str(final_payload.get("quality_failure_reason") or ""),
        "duration_s": round(time.time() - started, 3),
        "quality": asdict(quality),
        "save_status": save_resp.status_code,
        "final_markdown_file": str(final_md.resolve()),
        "final_docx_file": str(final_docx.resolve()) if final_docx.exists() else "",
        "events_file": str(raw_events.resolve()),
        "figure_assets_dir": str((out_dir / "figure_assets").resolve()),
        "figure_manifest_file": str((out_dir / "figure_assets" / "manifest.json").resolve()),
        "figure_count": int(figure_manifest.get("count", 0)),
        "figure_gate_passed": bool((quality.validator or {}).get("figure_gate_passed", True)),
        "validator_figure_score_avg": float((quality.validator or {}).get("figure_score_avg", 0.0) or 0.0),
        "validator_figure_pass_ratio": float((quality.validator or {}).get("figure_pass_ratio", 0.0) or 0.0),
        "validator_figure_review_count": int((quality.validator or {}).get("figure_review_count", 0) or 0),
        "validator_figure_drop_count": int((quality.validator or {}).get("figure_drop_count", 0) or 0),
        "validator_weak_figure_items": list((quality.validator or {}).get("weak_figure_items") or []),
        "figure_score_avg": float(figure_manifest.get("avg_score", 0.0) or 0.0),
        "figure_score_min": int(figure_manifest.get("min_score", 0) or 0),
        "figure_score_max": int(figure_manifest.get("max_score", 0) or 0),
        "figure_passed_count": int(figure_manifest.get("passed_count", 0) or 0),
    }
    (run_root / "SMOKE_SUMMARY.json").write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
