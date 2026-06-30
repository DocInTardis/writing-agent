#!/usr/bin/env python3
"""Run a compliant export -> quality-check -> revise -> recheck loop.

This script focuses on reducing internal overlap risk and model-like writing risk
for the exported document. It does not target external detector evasion.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DEFAULT_INSTRUCTION = (
    "请生成一篇中文学术文稿初稿，要求结构完整、论证具体、语言自然，"
    "避免模板化套话，避免连续复用相同句式，并保留清晰的小节结构。"
)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def _set_env_default(key: str, value: str) -> None:
    if str(os.environ.get(key) or "").strip():
        return
    os.environ[key] = value


def configure_generation_env() -> None:
    _set_env_default("WRITING_AGENT_LLM_PROVIDER", "openai")
    _set_env_default("WRITING_AGENT_OPENAI_INCLUDE_CODEX_AUTH", "1")
    _set_env_default("WRITING_AGENT_OPENAI_MODEL", "gpt-5.4")
    _set_env_default("WRITING_AGENT_MODEL", os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-5.4"))
    _set_env_default("WRITING_AGENT_AGG_MODEL", os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-5.4"))
    _set_env_default("WRITING_AGENT_WORKER_MODELS", os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-5.4"))
    _set_env_default("WRITING_AGENT_OPENAI_TIMEOUT_S", "300")
    _set_env_default("WRITING_AGENT_STREAM_EVENT_TIMEOUT_S", "300")
    _set_env_default("WRITING_AGENT_STREAM_MAX_S", "1500")
    _set_env_default("WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S", "300")
    _set_env_default("WRITING_AGENT_NONSTREAM_MAX_S", "1500")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_doc_id_from_redirect(resp: Any) -> str:
    location = str(resp.headers.get("location") or "")
    if "/workbench/" not in location:
        raise RuntimeError(f"cannot parse doc_id from redirect: {location}")
    return location.split("/workbench/")[-1].strip()


def create_doc(client: TestClient) -> str:
    resp = client.get("/new", follow_redirects=False)
    if int(resp.status_code) != 303:
        raise RuntimeError(f"create doc failed: {resp.status_code} {resp.text[:200]}")
    return parse_doc_id_from_redirect(resp)


def set_doc_settings(client: TestClient, doc_id: str, *, target_chars: int) -> dict[str, Any]:
    payload = {
        "generation_prefs": {
            "purpose": "学术论文",
            "target_char_count": max(1200, int(target_chars)),
            "target_length_confirmed": True,
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
    resp = client.post(f"/api/doc/{doc_id}/settings", json=payload)
    if int(resp.status_code) != 200:
        raise RuntimeError(f"save settings failed: {resp.status_code} {resp.text[:300]}")
    return payload


def fetch_doc_text(client: TestClient, doc_id: str) -> str:
    resp = client.get(f"/api/doc/{doc_id}")
    if int(resp.status_code) != 200:
        raise RuntimeError(f"fetch doc failed: {resp.status_code} {resp.text[:300]}")
    data = resp.json() if resp.content else {}
    return str(data.get("text") or "")


def generate_stream(
    client: TestClient,
    doc_id: str,
    instruction: str,
    *,
    text: str = "",
    compose_mode: str = "overwrite",
    timeout_s: int = 900,
) -> dict[str, Any]:
    payload = {
        "instruction": instruction,
        "text": text,
        "compose_mode": compose_mode,
    }
    started = time.time()
    final_payload: dict[str, Any] = {}
    final_text = ""
    event_name = ""
    event_count = 0
    trace: list[str] = []
    error = ""
    with client.stream(
        "POST",
        f"/api/doc/{doc_id}/generate/stream",
        json=payload,
        timeout=max(30, int(timeout_s)),
    ) as resp:
        if int(resp.status_code) != 200:
            detail = ""
            try:
                detail = resp.text
            except Exception:
                detail = ""
            return {
                "ok": False,
                "status_code": int(resp.status_code),
                "error": detail[:600] or f"HTTP {resp.status_code}",
                "duration_s": round(time.time() - started, 2),
                "event_count": 0,
                "trace": [],
                "text": "",
                "payload": {},
            }
        for raw in resp.iter_lines():
            if raw is None:
                continue
            line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            line = line.strip()
            if not line:
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
                continue
            if not line.startswith("data:"):
                continue
            event_count += 1
            body = line[5:].strip()
            try:
                data_obj = json.loads(body) if body else {}
            except Exception:
                data_obj = {}
            if event_name == "delta":
                delta = str(data_obj.get("delta") or "").strip()
                if delta:
                    trace.append(delta[:180])
            elif event_name == "error":
                error = str(data_obj.get("message") or data_obj.get("detail") or "stream error").strip()
            elif event_name == "final":
                final_payload = data_obj if isinstance(data_obj, dict) else {}
                final_text = str(final_payload.get("text") or "")
    if not final_text:
        final_text = fetch_doc_text(client, doc_id)
    if not final_text and not error:
        error = "stream ended without final text"
    return {
        "ok": bool(final_text),
        "status_code": 200,
        "error": error,
        "duration_s": round(time.time() - started, 2),
        "event_count": event_count,
        "trace": trace[-12:],
        "text": final_text,
        "payload": final_payload,
    }


def run_generation_with_retry(
    client: TestClient,
    doc_id: str,
    instruction: str,
    *,
    compose_mode: str,
    timeout_s: int,
    retries: int,
    min_acceptable_chars: int = 300,
) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for attempt in range(0, max(1, int(retries))):
        last = generate_stream(
            client,
            doc_id,
            instruction,
            compose_mode=compose_mode,
            timeout_s=timeout_s,
        )
        text = str(last.get("text") or "").strip()
        if bool(last.get("ok")) or compact_len(text) >= int(min_acceptable_chars):
            last["ok"] = True
            last["accepted_on_attempt"] = attempt + 1
            return last
        if attempt + 1 < max(1, int(retries)):
            time.sleep(min(6.0, 1.5 * (attempt + 1)))
    return last


def export_precheck(client: TestClient, doc_id: str) -> dict[str, Any]:
    resp = client.get(f"/api/doc/{doc_id}/export/check?format=docx&auto_fix=1")
    if int(resp.status_code) != 200:
        return {
            "ok": False,
            "status_code": int(resp.status_code),
            "can_export": False,
            "issues": [],
            "warnings": [],
            "policy": "",
            "error": resp.text[:300],
        }
    data = resp.json() if resp.content else {}
    return {
        "ok": bool(data.get("ok") == 1 or data.get("ok") is True),
        "status_code": int(resp.status_code),
        "can_export": bool(data.get("can_export")),
        "issues": data.get("issues") if isinstance(data.get("issues"), list) else [],
        "warnings": data.get("warnings") if isinstance(data.get("warnings"), list) else [],
        "policy": str(data.get("policy") or ""),
    }


def download_docx(client: TestClient, doc_id: str, out_path: Path) -> tuple[bool, str]:
    resp = client.get(f"/download/{doc_id}.docx")
    if int(resp.status_code) != 200 or not resp.content:
        body = ""
        try:
            body = resp.text
        except Exception:
            body = ""
        return False, f"HTTP {resp.status_code}: {body[:300]}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)
    return out_path.exists() and out_path.stat().st_size > 0, ""


def extract_docx_text_from_bytes(payload: bytes) -> str:
    try:
        with zipfile.ZipFile(io_from_bytes(payload), "r") as zf:
            xml_bytes = zf.read("word/document.xml")
    except Exception:
        return ""
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return ""
    paragraphs: list[str] = []
    for para in root.findall(".//w:body/w:p", WORD_NS):
        parts: list[str] = []
        for node in para.iter():
            tag = str(node.tag or "")
            if tag.endswith("}t"):
                parts.append(str(node.text or ""))
            elif tag.endswith("}tab"):
                parts.append("\t")
            elif tag.endswith("}br") or tag.endswith("}cr"):
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs).strip()


def io_from_bytes(payload: bytes):
    import io

    return io.BytesIO(payload)


def extract_docx_text(path: Path) -> str:
    return extract_docx_text_from_bytes(path.read_bytes())


def run_ai_check(client: TestClient, doc_id: str, *, text: str, threshold: float) -> dict[str, Any]:
    resp = client.post(
        f"/api/doc/{doc_id}/ai_rate/check",
        json={"text": text, "threshold": float(threshold)},
    )
    if int(resp.status_code) != 200:
        raise RuntimeError(f"ai check failed: {resp.status_code} {resp.text[:300]}")
    return resp.json() if resp.content else {}


def run_plagiarism_scan(
    client: TestClient,
    doc_id: str,
    *,
    text: str,
    threshold: float,
    top_k: int,
    max_docs: int,
    include_all_docs: bool,
    reference_doc_ids: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "text": text,
        "threshold": float(threshold),
        "top_k": int(top_k),
        "max_docs": int(max_docs),
        "include_all_docs": bool(include_all_docs),
    }
    refs = [str(x).strip() for x in (reference_doc_ids or []) if str(x).strip()]
    if refs:
        payload["reference_doc_ids"] = refs
        payload["include_all_docs"] = False
    resp = client.post(f"/api/doc/{doc_id}/plagiarism/library_scan", json=payload)
    if int(resp.status_code) != 200:
        raise RuntimeError(f"plagiarism scan failed: {resp.status_code} {resp.text[:300]}")
    return resp.json() if resp.content else {}


def download_plagiarism_report(client: TestClient, doc_id: str, report_id: str, fmt: str, out_path: Path) -> None:
    resp = client.get(f"/api/doc/{doc_id}/plagiarism/library_scan/download?report_id={report_id}&format={fmt}")
    if int(resp.status_code) != 200 or not resp.content:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        item = str(raw or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def build_revision_instruction(
    *,
    title: str,
    round_index: int,
    plagiarism_result: dict[str, Any],
    ai_result: dict[str, Any],
) -> str:
    progress = plagiarism_result.get("progress_summary") if isinstance(plagiarism_result.get("progress_summary"), dict) else {}
    current_overlap = float(progress.get("current_overlap_risk") or plagiarism_result.get("max_score") or 0.0)
    reduced_by = progress.get("reduced_by")
    ai_rate = float(ai_result.get("ai_rate") or 0.0)
    ai_percent = int(ai_result.get("ai_rate_percent") or round(ai_rate * 100))
    overlap_advice = [str(x).strip() for x in (plagiarism_result.get("revision_advice") or []) if str(x).strip()]
    ai_actions = [str(x).strip() for x in (ai_result.get("improvement_actions") or []) if str(x).strip()]
    directives = dedupe_preserve_order(overlap_advice + ai_actions)
    if not directives:
        directives = [
            "优先重写高重合的分析句群，改用自己的论证顺序和证据组织方式。",
            "补充更具体的对象、变量、时间范围、条件和限制，避免模板化表达。",
        ]

    lines = [
        f"请对题为《{title or '当前文档'}》的全文进行深度原创性修订。",
        f"当前导出稿内部重合风险约为 {current_overlap:.4f}，估计 AI 风险约为 {ai_percent}%。",
        "目标是继续降低内部重合风险和模板化写作信号，同时保持信息密度和论证完整性。",
        "硬性要求：",
        "1. 不要通过简单删段、压缩篇幅或删除关键事实来换取更低风险，正文应保持完整甚至更充实。",
        "2. 保留文档主标题、章节层级、引用编号和必要的图表/表格标记。",
        "3. 优先改写分析句群、解释句群和连续相似表达，不要只做同义词替换。",
        "4. 打散重复开头和机械连接词堆叠，增加具体背景、条件、比较、限制与判断。",
        "5. 只输出修订后的完整 Markdown 正文，不要解释修改过程。",
    ]
    if reduced_by is not None:
        lines.append(f"上一轮相对前一版的风险变化为 {float(reduced_by):.4f}。")
    lines.append("本轮重点：")
    for idx, item in enumerate(directives[:6], start=1):
        lines.append(f"- {idx}. {item}")
    return "\n".join(lines)


@dataclass
class LoopDecision:
    should_continue: bool
    reason: str
    current_overlap_risk: float
    reduced_by: float | None
    still_has_reduction_space: bool
    ai_rate: float
    ai_above_target: bool


def should_force_revision(*, force_revise_remaining: int, round_index: int, max_rounds: int) -> bool:
    return int(force_revise_remaining) > 0 and (int(round_index) + 1) < int(max_rounds)


def decide_whether_to_continue(
    *,
    plagiarism_result: dict[str, Any],
    ai_result: dict[str, Any],
    ai_threshold: float,
    previous_ai_rate: float | None = None,
) -> LoopDecision:
    progress = plagiarism_result.get("progress_summary") if isinstance(plagiarism_result.get("progress_summary"), dict) else {}
    current_overlap = float(progress.get("current_overlap_risk") or plagiarism_result.get("max_score") or 0.0)
    reduced_by_raw = progress.get("reduced_by")
    reduced_by = None if reduced_by_raw is None else float(reduced_by_raw)
    still_space = bool(progress.get("still_has_reduction_space"))
    ai_rate = float(ai_result.get("ai_rate") or 0.0)
    ai_above = ai_rate > float(ai_threshold)
    overlap_stagnant = reduced_by is not None and reduced_by <= 0.0 and still_space
    ai_stagnant = previous_ai_rate is not None and ai_rate >= float(previous_ai_rate) and ai_above

    if not still_space and not ai_above:
        return LoopDecision(
            should_continue=False,
            reason="targets_reached",
            current_overlap_risk=current_overlap,
            reduced_by=reduced_by,
            still_has_reduction_space=still_space,
            ai_rate=ai_rate,
            ai_above_target=ai_above,
        )
    if overlap_stagnant and ai_stagnant:
        return LoopDecision(
            should_continue=False,
            reason="stagnated",
            current_overlap_risk=current_overlap,
            reduced_by=reduced_by,
            still_has_reduction_space=still_space,
            ai_rate=ai_rate,
            ai_above_target=ai_above,
        )
    return LoopDecision(
        should_continue=True,
        reason="needs_more_revision",
        current_overlap_risk=current_overlap,
        reduced_by=reduced_by,
        still_has_reduction_space=still_space,
        ai_rate=ai_rate,
        ai_above_target=ai_above,
    )


def run_revision(client: TestClient, doc_id: str, *, instruction: str, text: str) -> dict[str, Any]:
    resp = client.post(
        f"/api/doc/{doc_id}/revise",
        json={
            "instruction": instruction,
            "text": text,
            "allow_unscoped_fallback": True,
        },
    )
    if int(resp.status_code) != 200:
        raise RuntimeError(f"revise failed: {resp.status_code} {resp.text[:300]}")
    return resp.json() if resp.content else {}


def persist_round_bundle(
    *,
    round_dir: Path,
    generate_result: dict[str, Any] | None,
    precheck: dict[str, Any],
    plagiarism_result: dict[str, Any],
    ai_result: dict[str, Any],
    decision: LoopDecision,
    exported_text: str,
    revise_instruction: str | None,
    revise_result: dict[str, Any] | None,
) -> None:
    round_dir.mkdir(parents=True, exist_ok=True)
    if generate_result is not None:
        write_json(round_dir / "generate_result.json", generate_result)
    write_json(round_dir / "export_precheck.json", precheck)
    write_json(round_dir / "plagiarism_scan.json", plagiarism_result)
    write_json(round_dir / "ai_rate_check.json", ai_result)
    write_json(
        round_dir / "decision.json",
        {
            "should_continue": decision.should_continue,
            "reason": decision.reason,
            "current_overlap_risk": decision.current_overlap_risk,
            "reduced_by": decision.reduced_by,
            "still_has_reduction_space": decision.still_has_reduction_space,
            "ai_rate": decision.ai_rate,
            "ai_above_target": decision.ai_above_target,
        },
    )
    (round_dir / "exported_text.md").write_text(exported_text, encoding="utf-8")
    if revise_instruction:
        (round_dir / "revise_instruction.txt").write_text(revise_instruction, encoding="utf-8")
    if revise_result is not None:
        write_json(round_dir / "revise_result.json", revise_result)


def build_summary_markdown(summary: dict[str, Any]) -> str:
    rounds = summary.get("rounds") if isinstance(summary.get("rounds"), list) else []
    lines = [
        "# Export Quality Optimization Loop",
        "",
        f"- Run ID: `{summary.get('run_id')}`",
        f"- Doc ID: `{summary.get('doc_id')}`",
        f"- Title: `{summary.get('title')}`",
        f"- Max Rounds: `{summary.get('max_rounds')}`",
        f"- Completed Rounds: `{len(rounds)}`",
        "",
    ]
    for row in rounds:
        if not isinstance(row, dict):
            continue
        lines.append(f"## Round {row.get('round')}")
        lines.append(f"- Overlap Risk: `{row.get('current_overlap_risk')}`")
        lines.append(f"- Reduced By: `{row.get('reduced_by')}`")
        lines.append(f"- Still Has Reduction Space: `{row.get('still_has_reduction_space')}`")
        lines.append(f"- AI Rate: `{row.get('ai_rate')}`")
        lines.append(f"- Decision: `{row.get('decision_reason')}`")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def derive_title(text: str) -> str:
    match = re.search(r"(?m)^#\s+(.+)$", str(text or ""))
    return str(match.group(1) or "").strip() if match else ""


def derive_title_from_instruction(instruction: str) -> str:
    src = str(instruction or "")
    for pattern in (r"[《“\"']([^》”\"']{4,80})[》”\"']", r"围绕[‘“\"']([^’”\"']{4,80})[’”\"']"):
        match = re.search(pattern, src)
        if match:
            return str(match.group(1) or "").strip()
    return ""


def title_looks_invalid(title: str) -> bool:
    token = str(title or "").strip()
    if not token:
        return True
    low = token.lower()
    if "pt" in low:
        return True
    if any(word in token for word in ("黑体", "宋体", "楷体", "Arial", "Times New Roman")):
        return True
    if len(token) <= 3:
        return True
    return False


def run_loop(args: argparse.Namespace) -> dict[str, Any]:
    configure_generation_env()
    out_root = Path(args.output_dir or (Path("deliverables") / f"export_quality_loop_{now_stamp()}")).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    client = TestClient(app_v2.app)
    generate_result: dict[str, Any] | None = None
    if bool(args.resume_existing) and str(args.doc_id or "").strip():
        doc_id = str(args.doc_id or "").strip()
        current_text = fetch_doc_text(client, doc_id)
        if not current_text.strip():
            raise RuntimeError(f"resume failed: empty document for doc_id={doc_id}")
    else:
        doc_id = create_doc(client)
        set_doc_settings(client, doc_id, target_chars=int(args.target_chars))
        generate_result = run_generation_with_retry(
            client,
            doc_id,
            args.instruction,
            compose_mode="overwrite",
            timeout_s=int(args.timeout_s),
            retries=int(args.generate_retries),
            min_acceptable_chars=int(args.min_generation_chars),
        )
        if not bool(generate_result.get("ok")):
            raise RuntimeError(f"generate failed: {generate_result.get('error') or 'unknown error'}")
        current_text = str(generate_result.get("text") or fetch_doc_text(client, doc_id))
    title = derive_title(current_text)
    if title_looks_invalid(title):
        title = str(args.title or "").strip() or derive_title_from_instruction(args.instruction) or title
    title = title or "未命名文档"
    summary_rounds: list[dict[str, Any]] = []
    previous_ai_rate: float | None = None
    force_revise_remaining = max(0, int(args.force_revise_rounds))

    for round_index in range(0, int(args.max_rounds)):
        round_dir = out_root / f"round_{round_index:02d}"
        precheck = export_precheck(client, doc_id)
        docx_path = round_dir / "export.docx"
        ok_docx, docx_err = download_docx(client, doc_id, docx_path)
        if not ok_docx:
            raise RuntimeError(f"docx export failed: {docx_err}")
        exported_text = extract_docx_text(docx_path)
        if not exported_text:
            exported_text = current_text

        plagiarism_result = run_plagiarism_scan(
            client,
            doc_id,
            text=exported_text,
            threshold=float(args.plagiarism_threshold),
            top_k=int(args.top_k),
            max_docs=int(args.max_docs),
            include_all_docs=bool(args.include_all_docs),
            reference_doc_ids=list(args.reference_doc_ids or []),
        )
        ai_result = run_ai_check(
            client,
            doc_id,
            text=exported_text,
            threshold=float(args.ai_threshold),
        )
        report_id = str(plagiarism_result.get("report_id") or "").strip()
        if report_id:
            download_plagiarism_report(client, doc_id, report_id, "json", round_dir / "plagiarism_report.json")
            download_plagiarism_report(client, doc_id, report_id, "md", round_dir / "plagiarism_report.md")
            download_plagiarism_report(client, doc_id, report_id, "csv", round_dir / "plagiarism_report.csv")

        decision = decide_whether_to_continue(
            plagiarism_result=plagiarism_result,
            ai_result=ai_result,
            ai_threshold=float(args.ai_threshold),
            previous_ai_rate=previous_ai_rate,
        )
        previous_ai_rate = float(ai_result.get("ai_rate") or 0.0)

        revise_instruction = None
        revise_result = None
        forced_revision = False
        if not decision.should_continue and should_force_revision(
            force_revise_remaining=force_revise_remaining,
            round_index=round_index,
            max_rounds=int(args.max_rounds),
        ):
            forced_revision = True
        if (decision.should_continue or forced_revision) and round_index + 1 < int(args.max_rounds):
            revise_instruction = build_revision_instruction(
                title=title,
                round_index=round_index,
                plagiarism_result=plagiarism_result,
                ai_result=ai_result,
            )
            if forced_revision:
                revise_instruction += (
                    "\n本轮为强制优化轮次：即使当前风险已进入目标带，"
                    "仍需继续重写局部高重合表达与模板化句群，争取进一步降低内部重合风险。"
                )
            revise_result = run_revision(client, doc_id, instruction=revise_instruction, text=current_text)
            current_text = str(revise_result.get("text") or current_text)
            if forced_revision and force_revise_remaining > 0:
                force_revise_remaining -= 1

        persist_round_bundle(
            round_dir=round_dir,
            generate_result=generate_result if round_index == 0 else None,
            precheck=precheck,
            plagiarism_result=plagiarism_result,
            ai_result=ai_result,
            decision=decision,
            exported_text=exported_text,
            revise_instruction=revise_instruction,
            revise_result=revise_result,
        )
        summary_rounds.append(
            {
                "round": round_index,
                "current_overlap_risk": decision.current_overlap_risk,
                "reduced_by": decision.reduced_by,
                "still_has_reduction_space": decision.still_has_reduction_space,
                "ai_rate": decision.ai_rate,
                "decision_reason": "forced_revision" if forced_revision else decision.reason,
                "export_chars": compact_len(exported_text),
                "report_id": report_id,
                "docx_path": str(docx_path),
            }
        )
        if not decision.should_continue and not forced_revision:
            break

    summary = {
        "run_id": now_stamp(),
        "doc_id": doc_id,
        "title": title,
        "instruction": args.instruction,
        "max_rounds": int(args.max_rounds),
        "plagiarism_threshold": float(args.plagiarism_threshold),
        "ai_threshold": float(args.ai_threshold),
        "rounds": summary_rounds,
        "output_dir": str(out_root),
    }
    write_json(out_root / "summary.json", summary)
    (out_root / "summary.md").write_text(build_summary_markdown(summary), encoding="utf-8")
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run export-quality optimization loop against the local app.")
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION, help="Initial generation instruction.")
    parser.add_argument("--title", default="", help="Optional expected title.")
    parser.add_argument("--doc-id", default="", help="Existing doc id to continue optimizing.")
    parser.add_argument("--resume-existing", action=argparse.BooleanOptionalAction, default=False, help="Resume from existing doc instead of creating and generating a new one.")
    parser.add_argument("--target-chars", type=int, default=7000, help="Target character count for generation.")
    parser.add_argument("--max-rounds", type=int, default=3, help="Maximum generate/export/check/revise rounds.")
    parser.add_argument("--force-revise-rounds", type=int, default=0, help="Force extra revise rounds even after the stop condition is met.")
    parser.add_argument("--plagiarism-threshold", type=float, default=0.35, help="Internal overlap threshold.")
    parser.add_argument("--ai-threshold", type=float, default=0.55, help="Internal AI-risk threshold.")
    parser.add_argument("--top-k", type=int, default=30, help="Top plagiarism matches to keep.")
    parser.add_argument("--max-docs", type=int, default=120, help="Maximum reference docs to scan.")
    parser.add_argument("--timeout-s", type=int, default=1200, help="Generation stream timeout in seconds.")
    parser.add_argument("--generate-retries", type=int, default=2, help="Initial generation retry count.")
    parser.add_argument("--min-generation-chars", type=int, default=300, help="Accept partial generation once this compact length is reached.")
    parser.add_argument("--include-all-docs", action=argparse.BooleanOptionalAction, default=True, help="Use all stored docs as plagiarism references.")
    parser.add_argument("--reference-doc-ids", nargs="*", default=[], help="Optional explicit reference doc ids.")
    parser.add_argument("--output-dir", default="", help="Optional output directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    summary = run_loop(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(str(Path(summary["output_dir"]).resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
