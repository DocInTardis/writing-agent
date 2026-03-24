#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run one high-quality Chinese paper generation for local+OpenAI-compatible providers."""

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
from scripts.run_summary_utils import extract_section_originality_summary
from scripts.targeted_revision_utils import run_targeted_section_revisions


TITLE = "“区块链+农村社会化服务”研究现状与研究热点分析——基于CiteSpace的可视化分析"
REQUIRED_H2 = [
    "摘要",
    "关键词",
    "引言",
    "相关研究",
    "数据来源与检索策略",
    "发文量时空分布",
    "作者与机构合作网络",
    "关键词共现与聚类分析",
    "研究热点演化与突现分析",
    "讨论",
    "结论",
    "参考文献",
]


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def parse_doc_id_from_redirect(resp) -> str:
    location = str(resp.headers.get("location") or "")
    if "/workbench/" not in location:
        raise RuntimeError(f"cannot parse doc_id from redirect: {location}")
    return location.split("/workbench/")[-1].strip()


def _structured_residue(text: str) -> bool:
    src = str(text or "")
    pattern = re.compile(
        r'(?i)(?:^|[,{]\s*)"?(?:section_id|block_id|type|items|caption|columns|rows)"?\s*:'
    )
    for line in src.splitlines():
        token = str(line or "").strip()
        if not token:
            continue
        if token.startswith("[[TABLE:") or token.startswith("[[FIGURE:"):
            continue
        if pattern.search(token):
            return True
    return False


@dataclass
class QualitySnapshot:
    passed: bool
    chars: int
    target_chars: int
    requested_target_chars: int
    refs_count: int
    h2_count: int
    missing_sections: list[str]
    structured_residue: bool
    meta_hits: list[str]
    repeat_sentence_ratio: float
    instruction_mirroring_ratio: float
    template_padding_ratio: float
    validator: dict[str, Any]
    deficits: list[str]


def evaluate_quality(
    text: str,
    *,
    target_chars: int = 9000,
    requested_target_chars: int | None = None,
) -> QualitySnapshot:
    src = str(text or "")
    chars = compact_len(src)
    resolved_target_chars = max(0, int(target_chars or 0)) or 9000
    resolved_requested_target_chars = max(resolved_target_chars, int(requested_target_chars or 0)) if requested_target_chars else resolved_target_chars
    headings = re.findall(r"(?m)^##\s+(.+?)\s*$", src)
    refs_count = len(re.findall(r"(?m)^\s*\[\d+\]\s+", src))
    missing = [sec for sec in REQUIRED_H2 if sec not in headings]
    residue = _structured_residue(src)
    meta_scan = MetaFirewall().scan(src)
    validator = validate_final_document(
        title=TITLE,
        text=src,
        sections=REQUIRED_H2,
        problems=[],
        rag_gate_dropped=[],
    )
    deficits: list[str] = []
    if chars < resolved_target_chars:
        deficits.append(f"正文长度不足：{chars} < {resolved_target_chars}")
    if refs_count < 18:
        deficits.append(f"参考文献不足：{refs_count} < 18")
    if missing:
        deficits.append("缺失章节：" + "、".join(missing))
    if residue:
        deficits.append("存在结构化残留(section_id/block_id/type等)")
    if meta_scan.has_meta:
        deficits.append("存在元指令残留")
    template_ratio = float(validator.get("template_padding_ratio") or 0.0)
    template_max = float(validator.get("max_template_padding_ratio") or 0.0)
    if template_ratio > template_max:
        deficits.append(f"模板化占位句比例过高：{template_ratio:.4f} > {template_max:.4f}")
    if not bool(validator.get("passed")):
        deficits.append("最终双门禁未通过")
    passed = len(deficits) == 0
    return QualitySnapshot(
        passed=passed,
        chars=chars,
        target_chars=resolved_target_chars,
        requested_target_chars=resolved_requested_target_chars,
        refs_count=refs_count,
        h2_count=len(headings),
        missing_sections=missing,
        structured_residue=residue,
        meta_hits=list(meta_scan.fragments[:8]),
        repeat_sentence_ratio=float(validator.get("repeat_sentence_ratio") or 0.0),
        instruction_mirroring_ratio=float(validator.get("instruction_mirroring_ratio") or 0.0),
        template_padding_ratio=float(validator.get("template_padding_ratio") or 0.0),
        validator=validator,
        deficits=deficits,
    )


def build_instruction() -> str:
    return (
        f"请撰写题为《{TITLE}》的中文学术论文初稿，严格对标知网高质量文献计量论文写作规范。\n"
        "硬性要求：\n"
        "1. 必须使用中文学术表达，不得输出提示词、过程说明、模板语句。\n"
        "2. 正文字数不少于9000（不含空白），每节不少于3段。\n"
        "3. 必须包含以下二级章节并按顺序输出："
        + "、".join(REQUIRED_H2)
        + "。\n"
        "4. 在“关键词共现与聚类分析”“研究热点演化与突现分析”中必须给出可解释分析，不得泛化空话。\n"
        "5. 参考文献至少18条，按 [n] 格式逐条列出；不得重复，不得空条目。\n"
        "6. 不得出现 section_id、block_id、type、items、caption、columns、rows 等结构化键值残留。\n"
        "7. 不得出现“本节应/需/建议”等元指令句式。\n"
        "8. 若内容未达标，继续补全后再结束输出。"
    )


def revision_instruction(deficits: list[str]) -> str:
    joined = "；".join(deficits) if deficits else "请整体提升论文质量并补全不足"
    return (
        f"请对当前论文进行深度学术化修订，题目保持《{TITLE}》不变。\n"
        f"当前问题：{joined}\n"
        "修订要求：\n"
        "1. 仅输出最终正文，不要解释修订过程。\n"
        "2. 缺失章节必须补齐并保持章节顺序。\n"
        "3. 删除所有元指令句、模板句和结构化键值残留。\n"
        "4. 强化方法与结果论证，避免重复和空泛表述。\n"
        "5. 参考文献补足到至少18条，采用 [n] 编号。"
    )


def _set_base_env() -> None:
    os.environ["WRITING_AGENT_USE_ROUTE_GRAPH"] = "0"
    os.environ["WRITING_AGENT_FAST_GENERATE"] = "0"
    os.environ["WRITING_AGENT_FAST_PLAN"] = "0"
    os.environ["WRITING_AGENT_FAST_DRAFT"] = "0"
    os.environ["WRITING_AGENT_STRICT_JSON"] = "1"
    os.environ["WRITING_AGENT_ENFORCE_FINAL_VALIDATION"] = "1"
    os.environ["WRITING_AGENT_ENFORCE_META_FIREWALL"] = "1"
    os.environ["WRITING_AGENT_ENFORCE_CONTRACT_SLOTS"] = "1"
    os.environ["WRITING_AGENT_EVIDENCE_ENABLED"] = "1"
    # Disable theme gate hard-blocking for this benchmark run; quality is still enforced by dual gate + custom checks.
    os.environ["WRITING_AGENT_RAG_THEME_GATE_ENABLED"] = "0"
    os.environ["WRITING_AGENT_RAG_TOP_K"] = "12"
    os.environ["WRITING_AGENT_RAG_PER_PAPER"] = "3"
    os.environ["WRITING_AGENT_RAG_MAX_CHARS"] = "4200"
    os.environ["WRITING_AGENT_OPENALEX_MAX_RESULTS"] = "60"
    os.environ["WRITING_AGENT_MIN_REFERENCE_ITEMS"] = "18"
    os.environ["WRITING_AGENT_ENFORCE_REFERENCE_MIN"] = "1"
    os.environ["WRITING_AGENT_PARADIGM_OVERRIDE"] = "bibliometric"
    os.environ["WRITING_AGENT_PROVIDER_PREFLIGHT_CHAT"] = "0"

    # Long-running settings: do not prematurely stop while model is still generating.
    os.environ["WRITING_AGENT_PLAN_TIMEOUT_S"] = "1800"
    os.environ["WRITING_AGENT_ANALYSIS_TIMEOUT_S"] = "1800"
    os.environ["WRITING_AGENT_SECTION_TIMEOUT_S"] = "3600"
    os.environ["WRITING_AGENT_STREAM_EVENT_TIMEOUT_S"] = "3600"
    os.environ["WRITING_AGENT_STREAM_MAX_S"] = "21600"
    os.environ["WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S"] = "3600"
    os.environ["WRITING_AGENT_NONSTREAM_MAX_S"] = "21600"


def _clear_provider_env() -> None:
    for key in [
        "WRITING_AGENT_USE_OLLAMA",
        "WRITING_AGENT_LLM_PROVIDER",
        "WRITING_AGENT_LLM_BACKEND",
        "WRITING_AGENT_MODEL",
        "WRITING_AGENT_AGG_MODEL",
        "WRITING_AGENT_WORKER_MODELS",
        "OLLAMA_MODEL",
        "OLLAMA_HOST",
        "OLLAMA_TIMEOUT_S",
        "WRITING_AGENT_OPENAI_MODEL",
        "WRITING_AGENT_OPENAI_BASE_URL",
        "WRITING_AGENT_OPENAI_TIMEOUT_S",
        "WRITING_AGENT_PER_MODEL_CONCURRENCY",
        "WRITING_AGENT_EVIDENCE_WORKERS",
    ]:
        os.environ.pop(key, None)


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


def _configure_provider(profile: str) -> None:
    _clear_provider_env()
    _set_base_env()
    if profile == "local_ollama":
        os.environ["WRITING_AGENT_LLM_PROVIDER"] = "ollama"
        os.environ["WRITING_AGENT_USE_OLLAMA"] = "1"
        os.environ["OLLAMA_MODEL"] = "qwen2.5:7b"
        os.environ["WRITING_AGENT_MODEL"] = "qwen2.5:7b"
        os.environ["WRITING_AGENT_AGG_MODEL"] = "qwen2.5:7b"
        os.environ["WRITING_AGENT_WORKER_MODELS"] = "qwen2.5:7b,qwen2.5:3b"
        os.environ["WRITING_AGENT_OLLAMA_TIMEOUT_S"] = "600"
        os.environ["OLLAMA_TIMEOUT_S"] = "600"
        os.environ["WRITING_AGENT_PER_MODEL_CONCURRENCY"] = "1"
        os.environ["WRITING_AGENT_EVIDENCE_WORKERS"] = "3"
        return

    if profile == "codex_openai_compat":
        _load_openai_key_if_missing()
        if not str(os.environ.get("WRITING_AGENT_OPENAI_API_KEY") or "").strip():
            raise RuntimeError("missing WRITING_AGENT_OPENAI_API_KEY")
        os.environ["WRITING_AGENT_LLM_PROVIDER"] = "openai"
        os.environ["WRITING_AGENT_OPENAI_BASE_URL"] = str(
            os.environ.get("WRITING_AGENT_OPENAI_BASE_URL", "https://vpsairobot.com/v1")
        ).strip()
        os.environ["WRITING_AGENT_OPENAI_MODEL"] = "gpt-5.4"
        os.environ["WRITING_AGENT_MODEL"] = "gpt-5.4"
        os.environ["WRITING_AGENT_AGG_MODEL"] = "gpt-5.4"
        os.environ["WRITING_AGENT_WORKER_MODELS"] = "gpt-5.4"
        os.environ["WRITING_AGENT_OPENAI_TIMEOUT_S"] = "600"
        os.environ["WRITING_AGENT_PER_MODEL_CONCURRENCY"] = "4"
        os.environ["WRITING_AGENT_EVIDENCE_WORKERS"] = "6"
        return

    raise RuntimeError(f"unsupported profile: {profile}")


def _settings_payload() -> dict[str, Any]:
    return {
        "generation_prefs": {
            "purpose": "学术论文",
            "target_char_count": 11000,
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


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_one_profile(*, profile: str, out_root: Path, max_revise_rounds: int) -> dict[str, Any]:
    _configure_provider(profile)
    profile_dir = out_root / profile
    profile_dir.mkdir(parents=True, exist_ok=True)

    instruction = build_instruction()
    client = TestClient(app_v2.app)
    root_resp = client.get("/", follow_redirects=False)
    if root_resp.status_code != 303:
        raise RuntimeError(f"create doc failed: {root_resp.status_code} {root_resp.text[:200]}")
    doc_id = parse_doc_id_from_redirect(root_resp)
    settings_payload = _settings_payload()
    set_resp = client.post(f"/api/doc/{doc_id}/settings", json=settings_payload)
    if set_resp.status_code != 200:
        raise RuntimeError(f"save settings failed: {set_resp.status_code} {set_resp.text[:200]}")

    events: list[dict[str, Any]] = []
    final_payload: dict[str, Any] = {}
    started = time.time()
    cfg = app_v2.GenerateConfig(workers=6, min_total_chars=9000, max_total_chars=0)
    generator = app_v2.run_generate_graph(
        instruction=instruction,
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

    raw_events = profile_dir / "raw_events.jsonl"
    with raw_events.open("w", encoding="utf-8") as f:
        for row in events:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    text = str(final_payload.get("text") or "")
    status = str(final_payload.get("status") or "failed").strip().lower()
    failure_reason = str(final_payload.get("failure_reason") or "").strip()
    runtime_status = str(final_payload.get("runtime_status") or final_payload.get("status") or "failed").strip().lower()
    runtime_failure_reason = str(final_payload.get("runtime_failure_reason") or "").strip()
    quality_passed = bool(final_payload.get("quality_passed", False))
    quality_failure_reason = str(final_payload.get("quality_failure_reason") or "").strip()
    rounds: list[dict[str, Any]] = []

    quality_snapshot = final_payload.get("quality_snapshot") if isinstance(final_payload.get("quality_snapshot"), dict) else {}
    section_originality_hot_sample = extract_section_originality_summary(quality_snapshot)
    text, targeted_revision_report = run_targeted_section_revisions(
        client=client,
        doc_id=doc_id,
        text=text,
        quality_snapshot=quality_snapshot,
        max_sections=2,
    )
    try:
        requested_target_chars = max(0, int(quality_snapshot.get("requested_min_total_chars") or 9000)) or 9000
    except Exception:
        requested_target_chars = 9000
    try:
        effective_target_chars = max(0, int(quality_snapshot.get("effective_min_total_chars") or requested_target_chars)) or requested_target_chars
    except Exception:
        effective_target_chars = requested_target_chars

    quality = evaluate_quality(
        text,
        target_chars=effective_target_chars,
        requested_target_chars=requested_target_chars,
    )
    rounds.append({
        "round": 0,
        "type": "generate",
        "quality": asdict(quality),
        "targeted_revision_report": targeted_revision_report,
        "quality_snapshot_runtime": dict(quality_snapshot),
        "section_originality_hot_sample": section_originality_hot_sample,
        "status": status,
        "failure_reason": failure_reason,
        "status": status,
        "failure_reason": failure_reason,
        "runtime_status": runtime_status,
        "runtime_failure_reason": runtime_failure_reason,
        "quality_passed": quality_passed,
        "quality_failure_reason": quality_failure_reason,
        "quality_passed": quality_passed,
        "quality_failure_reason": quality_failure_reason,
    })

    for ridx in range(1, int(max_revise_rounds) + 1):
        if quality.passed:
            break
        revise_payload = {
            "instruction": revision_instruction(quality.deficits),
            "text": text,
            "allow_unscoped_fallback": False,
        }
        revise_resp = client.post(f"/api/doc/{doc_id}/revise", json=revise_payload)
        if revise_resp.status_code != 200:
            rounds.append(
                {
                    "round": ridx,
                    "type": "revise",
                    "result": "failed",
                    "status_code": revise_resp.status_code,
                    "body": revise_resp.text[:500],
                }
            )
            break
        revise_data = revise_resp.json() if revise_resp.content else {}
        text = str(revise_data.get("text") or text)
        quality = evaluate_quality(text, target_chars=effective_target_chars, requested_target_chars=requested_target_chars)
        rounds.append(
            {
                "round": ridx,
                "type": "revise",
                "result": "passed" if quality.passed else "not_passed",
                "quality": asdict(quality),
            }
        )

    save_payload = {
        "text": text,
        "generation_prefs": settings_payload["generation_prefs"],
        "formatting": settings_payload["formatting"],
    }
    save_resp = client.post(f"/api/doc/{doc_id}/save", json=save_payload)

    final_md = profile_dir / "final_output.md"
    _write_json(profile_dir / "targeted_revision_report.json", targeted_revision_report)
    final_md.write_text(text, encoding="utf-8")
    figure_manifest = export_rendered_figure_assets(text, profile_dir / "figure_assets")
    final_docx = profile_dir / "final_output.docx"
    dl = client.get(f"/download/{doc_id}.docx")
    if dl.status_code == 200 and dl.content:
        final_docx.write_bytes(dl.content)

    _write_json(profile_dir / "quality_rounds.json", rounds)
    outcome = {
        "profile": profile,
        "doc_id": doc_id,
        "status": status,
        "failure_reason": failure_reason,
        "runtime_status": runtime_status,
        "runtime_failure_reason": runtime_failure_reason,
        "quality_passed": quality_passed,
        "quality_failure_reason": quality_failure_reason,
        "quality": asdict(quality),
        "quality_snapshot_runtime": dict(quality_snapshot),
        "section_originality_hot_sample": section_originality_hot_sample,
        "save_status": save_resp.status_code,
        "final_markdown_file": str(final_md.resolve()),
        "final_docx_file": str(final_docx.resolve()) if final_docx.exists() else "",
        "events_file": str(raw_events.resolve()),
        "quality_rounds_file": str((profile_dir / "quality_rounds.json").resolve()),
        "figure_assets_dir": str((profile_dir / "figure_assets").resolve()),
        "figure_manifest_file": str((profile_dir / "figure_assets" / "manifest.json").resolve()),
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
    _write_json(profile_dir / "outcome.json", outcome)
    return outcome


def main() -> int:
    out_root = Path("deliverables").resolve() / f"dual_provider_high_quality_cn_{now_stamp()}"
    out_root.mkdir(parents=True, exist_ok=True)
    profiles = ["local_ollama", "codex_openai_compat"]
    outcomes: dict[str, Any] = {}
    for profile in profiles:
        try:
            outcomes[profile] = run_one_profile(profile=profile, out_root=out_root, max_revise_rounds=2)
        except Exception as exc:
            outcomes[profile] = {
                "profile": profile,
                "runtime_status": "failed",
                "runtime_failure_reason": f"{exc.__class__.__name__}: {str(exc)[:400]}",
                "quality": {"passed": False},
            }
    summary = {"run_root": str(out_root), **outcomes}
    _write_json(out_root / "DUAL_PROVIDER_SUMMARY.json", summary)
    report_lines = [
        f"# Dual Provider High-Quality CN Run ({now_stamp()})",
        "",
    ]
    for p in profiles:
        row = outcomes.get(p) or {}
        quality = (row.get("quality") or {}) if isinstance(row.get("quality"), dict) else {}
        report_lines.append(f"## {p}")
        report_lines.append(f"- status: `{row.get('status', '')}`")
        report_lines.append(f"- failure_reason: `{row.get('failure_reason', '')}`")
        report_lines.append(f"- runtime_status: `{row.get('runtime_status', '')}`")
        report_lines.append(f"- runtime_failure_reason: `{row.get('runtime_failure_reason', '')}`")
        report_lines.append(f"- quality_passed(runtime): `{row.get('quality_passed', False)}`")
        report_lines.append(f"- quality_failure_reason(runtime): `{row.get('quality_failure_reason', '')}`")
        report_lines.append(f"- quality_passed(validator): `{quality.get('passed', False)}`")
        report_lines.append(f"- chars: `{quality.get('chars', 0)}`")
        report_lines.append(f"- refs_count: `{quality.get('refs_count', 0)}`")
        originality = (row.get("section_originality_hot_sample") or {}) if isinstance(row.get("section_originality_hot_sample"), dict) else {}
        report_lines.append(f"- originality_failed_sections: `{originality.get('failed_section_count', 0)}`")
        report_lines.append(f"- originality_rewrites: `{originality.get('rewrite_count', 0)}`")
        report_lines.append(f"- originality_fast_draft_rejected: `{originality.get('fast_draft_rejected_count', 0)}`")
        targeted = (row.get("targeted_revision_report") or {}) if isinstance(row.get("targeted_revision_report"), dict) else {}
        report_lines.append(f"- targeted_revision_attempted: `{targeted.get('attempted', 0)}`")
        report_lines.append(f"- targeted_revision_applied: `{targeted.get('applied', 0)}`")
        report_lines.append(f"- markdown: `{row.get('final_markdown_file', '')}`")
        report_lines.append(f"- docx: `{row.get('final_docx_file', '')}`")
        report_lines.append("")
    (out_root / "DUAL_PROVIDER_REPORT.md").write_text("\n".join(report_lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(str((out_root / "DUAL_PROVIDER_REPORT.md").resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
