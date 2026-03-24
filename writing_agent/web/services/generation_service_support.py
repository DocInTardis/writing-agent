"""Support utilities for GenerationService.

This module isolates pure helper logic from the transport/orchestration layer so the
service class stays focused on request flow, persistence, and runtime delegation.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from fastapi import Request

from writing_agent.web.domains import section_edit_ops_domain
from writing_agent.web.idempotency import IdempotencyStore, make_idempotency_key


def xml_escape(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def strip_fences(raw: object) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    return text


def fallback_normalize_heading_text(text: object) -> str:
    token = str(text or "").strip().lower()
    token = re.sub(r"^#+\s*", "", token)
    token = re.sub(r"[\s\-_:,.;()\[\]{}]+", "", token)
    return token


def resolve_target_section_selection(
    *,
    text: str,
    section_title: str,
    normalize_heading_text: Callable[[object], str],
) -> dict[str, object] | None:
    source = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    target = str(section_title or "").strip()
    if not source.strip() or not target:
        return None
    sections = section_edit_ops_domain.extract_sections(source, prefer_levels=(2, 3))
    if not sections:
        sections = section_edit_ops_domain.extract_sections(source, prefer_levels=(1, 2, 3))
    if not sections:
        return None
    try:
        sec = section_edit_ops_domain.find_section(
            sections,
            target,
            normalize_heading_text=normalize_heading_text,
        )
    except Exception:
        sec = None
    if sec is None:
        return None
    lines = section_edit_ops_domain.split_lines(source)
    line_starts: list[int] = []
    cursor = 0
    for line in lines:
        line_starts.append(cursor)
        cursor += len(line) + 1
    body_start_line = min(len(lines), int(sec.start) + 1)
    while body_start_line < int(sec.end) and not str(lines[body_start_line] or "").strip():
        body_start_line += 1
    start = line_starts[body_start_line] if body_start_line < len(line_starts) else len(source)
    end_line = min(int(sec.end), len(lines))
    end = line_starts[end_line] if end_line < len(line_starts) else len(source)
    body = source[start:end].strip("\n")
    if not body:
        heading_start = line_starts[int(sec.start)] if int(sec.start) < len(line_starts) else 0
        start = heading_start
        end = line_starts[end_line] if end_line < len(line_starts) else len(source)
        body = source[start:end].strip("\n")
    if not body:
        return None
    heading = str(sec.title or target).strip() or target
    return {
        "start": int(start),
        "end": int(end),
        "text": body,
        "title": heading,
    }


def build_revision_fallback_prompt(
    *,
    instruction: str,
    plan_steps: list[str],
    text: str,
    hard_constraints: dict[str, Any] | None = None,
) -> tuple[str, str]:
    system = (
        "You are a constrained document revision assistant.\n"
        "Return complete Markdown only inside <revised_markdown>...</revised_markdown>.\n"
        "Do not output any text outside that tag."
    )
    plan_rows = []
    for step in plan_steps:
        clean_step = xml_escape(step)
        if clean_step:
            plan_rows.append(f"<step>{clean_step}</step>")
        if len(plan_rows) >= 12:
            break
    plan_block = "\n".join(plan_rows) if plan_rows else "<step>no-explicit-plan</step>"
    hard = dict(hard_constraints or {})
    req_h2_rows = []
    for title in hard.get("required_h2") or []:
        clean_title = xml_escape(title)
        if clean_title:
            req_h2_rows.append(f"<required_h2>{clean_title}</required_h2>")
    req_h2_block = "\n".join(req_h2_rows) if req_h2_rows else "<required_h2>none</required_h2>"
    hard_block = (
        "<hard_requirements>\n"
        f"<min_chars>{int(hard.get('min_chars') or 0)}</min_chars>\n"
        f"<min_refs>{int(hard.get('min_refs') or 0)}</min_refs>\n"
        f"<min_tables>{int(hard.get('min_tables') or 0)}</min_tables>\n"
        f"<min_figures>{int(hard.get('min_figures') or 0)}</min_figures>\n"
        f"{req_h2_block}\n"
        "</hard_requirements>"
    )
    user = (
        "<task>revise_full_document</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Rewrite the full document, not a summary.\n"
        "- Preserve heading structure unless instruction explicitly asks to change it.\n"
        "- Preserve markers like [[TABLE:...]] and [[FIGURE:...]] when present.\n"
        "- Do not include analysis, explanation, or JSON.\n"
        "- Hard requirements must be satisfied before finishing output.\n"
        "</constraints>\n"
        f"<revision_request>\n{xml_escape(instruction)}\n</revision_request>\n"
        f"<execution_plan>\n{plan_block}\n</execution_plan>\n"
        f"{hard_block}\n"
        f"<original_document>\n{xml_escape(text)}\n</original_document>\n"
        "Return only one block:\n"
        "<revised_markdown>\n"
        "...complete revised markdown...\n"
        "</revised_markdown>"
    )
    return system, user


def extract_revision_fallback_text(raw: object) -> str:
    text = strip_fences(raw)
    match = re.search(r"<revised_markdown>\s*([\s\S]*?)\s*</revised_markdown>", text, flags=re.IGNORECASE)
    if match:
        return str(match.group(1) or "").strip()
    alt = re.search(r"<revised_text>\s*([\s\S]*?)\s*</revised_text>", text, flags=re.IGNORECASE)
    if alt:
        return str(alt.group(1) or "").strip()
    return text.strip()


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def revision_candidate_metrics(
    app_v2: Any,
    *,
    text: str,
    required_h2: list[str],
    min_chars: int,
    min_refs: int,
    min_tables: int,
    min_figures: int,
) -> dict[str, Any]:
    src = str(text or "")
    chars = compact_len(src)
    sections = []
    try:
        sections = list(app_v2._extract_sections(src, prefer_levels=(2, 3)) or [])
    except Exception:
        sections = []

    def _norm(value: str) -> str:
        try:
            return str(app_v2._normalize_heading_text(value or "")).strip()
        except Exception:
            return re.sub(r"\s+", "", str(value or "")).strip().lower()

    section_tokens = {_norm(getattr(sec, "title", "")) for sec in sections if str(getattr(sec, "title", "")).strip()}
    required_tokens = [_norm(x) for x in (required_h2 or []) if _norm(x)]
    covered = sum(1 for tok in required_tokens if tok in section_tokens)
    coverage = 1.0 if not required_tokens else (covered / float(len(required_tokens)))
    missing_required_h2 = []
    if required_tokens:
        missing_required_h2 = [str(x) for x in (required_h2 or []) if _norm(x) and _norm(x) not in section_tokens]

    refs_count = len(re.findall(r"(?m)^\s*\[\d+\]\s+", src))
    table_markers = len(re.findall(r"\[\[TABLE:", src))
    figure_markers = len(re.findall(r"\[\[FIGURE:", src))

    def _ratio(value: int, target: int) -> float:
        if target <= 0:
            return 1.0
        return min(1.0, float(value) / float(target))

    score = (
        0.35 * _ratio(chars, max(1, min_chars))
        + 0.25 * coverage
        + 0.2 * _ratio(refs_count, min_refs)
        + 0.1 * _ratio(table_markers, min_tables)
        + 0.1 * _ratio(figure_markers, min_figures)
    ) * 100.0

    return {
        "chars": int(chars),
        "required_h2_total": int(len(required_tokens)),
        "required_h2_covered": int(covered),
        "required_h2_coverage": round(coverage, 4),
        "missing_required_h2": missing_required_h2,
        "refs_count": int(refs_count),
        "table_markers": int(table_markers),
        "figure_markers": int(figure_markers),
        "quality_score": round(score, 2),
    }


def validate_revision_candidate(
    app_v2: Any,
    *,
    candidate_text: str,
    base_text: str,
    hard_constraints: dict[str, Any],
) -> dict[str, Any]:
    min_chars = max(120, int(hard_constraints.get("min_chars") or 0))
    required_h2 = [str(x).strip() for x in (hard_constraints.get("required_h2") or []) if str(x).strip()]
    min_refs = max(0, int(hard_constraints.get("min_refs") or 0))
    min_tables = max(0, int(hard_constraints.get("min_tables") or 0))
    min_figures = max(0, int(hard_constraints.get("min_figures") or 0))
    epsilon = max(0.0, float(hard_constraints.get("epsilon") or 0.0))

    before = revision_candidate_metrics(
        app_v2,
        text=base_text,
        required_h2=required_h2,
        min_chars=min_chars,
        min_refs=min_refs,
        min_tables=min_tables,
        min_figures=min_figures,
    )
    after = revision_candidate_metrics(
        app_v2,
        text=candidate_text,
        required_h2=required_h2,
        min_chars=min_chars,
        min_refs=min_refs,
        min_tables=min_tables,
        min_figures=min_figures,
    )

    reasons: list[str] = []
    if after["chars"] < min_chars:
        reasons.append(f"chars_below_min:{after['chars']}<{min_chars}")
    if required_h2 and float(after["required_h2_coverage"]) < 1.0:
        reasons.append(
            "required_h2_coverage_insufficient:"
            + ",".join(str(x) for x in (after.get("missing_required_h2") or [])[:8])
        )
    if after["refs_count"] < min_refs:
        reasons.append(f"refs_below_min:{after['refs_count']}<{min_refs}")
    if after["table_markers"] < min_tables:
        reasons.append(f"tables_below_min:{after['table_markers']}<{min_tables}")
    if after["figure_markers"] < min_figures:
        reasons.append(f"figures_below_min:{after['figure_markers']}<{min_figures}")

    delta = float(after["quality_score"]) - float(before["quality_score"])
    if delta < (-epsilon):
        reasons.append(f"quality_score_regressed:{delta:.2f}<-{epsilon:.2f}")

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "score_delta": round(delta, 2),
        "before": before,
        "after": after,
        "hard_constraints": {
            "min_chars": min_chars,
            "required_h2": required_h2,
            "min_refs": min_refs,
            "min_tables": min_tables,
            "min_figures": min_figures,
            "epsilon": epsilon,
        },
    }


def parse_generate_payload(
    app_v2: Any,
    data: dict[str, Any],
    *,
    session: Any = None,
    load_plan_confirm_state_fn: Callable[..., dict[str, Any] | None],
    normalize_plan_confirm_payload_fn: Callable[[object], dict[str, Any]],
) -> dict[str, Any]:
    selection_payload = data.get("selection")
    selection_text = (
        str(selection_payload.get("text") or "")
        if isinstance(selection_payload, dict)
        else str(selection_payload or "")
    )
    incoming_plan_confirm = data.get("plan_confirm")
    if incoming_plan_confirm is None:
        incoming_plan_confirm = load_plan_confirm_state_fn(app_v2, session=session)
    return {
        "raw_instruction": str(data.get("instruction") or "").strip(),
        "current_text": str(data.get("text") or ""),
        "selection_payload": selection_payload,
        "selection_text": selection_text,
        "context_policy": data.get("context_policy"),
        "compose_mode": app_v2._normalize_compose_mode(data.get("compose_mode")),
        "resume_sections": app_v2._normalize_resume_sections(data.get("resume_sections")),
        "cursor_anchor": str(data.get("cursor_anchor") or ""),
        "confirm_apply": bool(data.get("confirm_apply") is True),
        "plan_confirm": normalize_plan_confirm_payload_fn(incoming_plan_confirm),
    }


def normalize_plan_confirm_payload(raw: object) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    decision_raw = str(data.get("decision") or "").strip().lower()
    if decision_raw in {"stop", "terminate", "cancel", "reject"}:
        decision = "interrupted"
    elif decision_raw in {"interrupted", "approved"}:
        decision = decision_raw
    else:
        decision = "approved"
    try:
        score = int(data.get("score") or 0)
    except Exception:
        score = 0
    score = max(0, min(5, score))
    note = str(data.get("note") or "").strip()[:300]
    return {
        "decision": decision,
        "score": score,
        "note": note,
    }


def load_plan_confirm_state(app_v2: Any, *, session: Any) -> dict[str, Any] | None:
    if session is None:
        return None
    try:
        data = app_v2._get_internal_pref(session, "_wa_plan_confirm", {})
        return data if isinstance(data, dict) else None
    except Exception:
        prefs = session.generation_prefs if isinstance(getattr(session, "generation_prefs", None), dict) else {}
        value = prefs.get("_wa_plan_confirm") if isinstance(prefs, dict) else None
        return value if isinstance(value, dict) else None


def save_plan_confirm_state(app_v2: Any, *, session: Any, payload: dict[str, Any]) -> None:
    if session is None:
        return
    value = dict(payload or {})
    value["updated_at"] = time.time()
    try:
        app_v2._set_internal_pref(session, "_wa_plan_confirm", value)
    except Exception:
        prefs = dict(session.generation_prefs or {})
        prefs["_wa_plan_confirm"] = value
        session.generation_prefs = prefs
    app_v2.store.put(session)


def resolve_idempotency_key(*, doc_id: str, request: Request, payload: dict[str, Any]) -> str:
    header_key = str(request.headers.get("x-idempotency-key") or "").strip()
    if header_key:
        return header_key
    return make_idempotency_key(doc_id=doc_id, route="generate", body=payload)


def load_idempotent_result(store: IdempotencyStore, key: str) -> dict[str, Any] | None:
    cached = store.get(key)
    if not isinstance(cached, dict):
        return None
    payload = cached.get("payload")
    return payload if isinstance(payload, dict) and payload.get("ok") else None


def save_idempotent_result(store: IdempotencyStore, key: str, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or not payload.get("ok"):
        return
    store.put(key, payload)


def build_generation_instruction(
    *,
    app_v2: Any,
    session: Any,
    raw_instruction: str,
    compose_mode: str,
    resume_sections: list[str],
    cursor_anchor: str,
) -> str:
    has_existing = bool(str(session.doc_text or "").strip())
    instruction = app_v2._apply_compose_mode_instruction(raw_instruction, compose_mode, has_existing=has_existing)
    if resume_sections:
        instruction = app_v2._apply_resume_sections_instruction(
            instruction,
            resume_sections,
            cursor_anchor=cursor_anchor,
        )
    return instruction


def build_shortcut_result(*, app_v2: Any, session: Any, text: str, instruction: str, base_text: str) -> dict[str, Any]:
    if base_text.strip():
        if base_text != session.doc_text:
            app_v2._set_doc_text(session, base_text)
        app_v2._auto_commit_version(session, "auto: before update")
    updated_text = app_v2._postprocess_output_text(
        session,
        text,
        instruction,
        current_text=base_text,
        base_text=base_text,
    )
    app_v2._set_doc_text(session, updated_text)
    app_v2._auto_commit_version(session, "auto: after update")
    app_v2.store.put(session)
    return {"ok": 1, "text": updated_text, "problems": [], "doc_ir": app_v2._safe_doc_ir_payload(updated_text)}


def build_confirmation_shortcut_result(
    *,
    app_v2: Any,
    base_text: str,
    note: str,
    confirmation_reason: str,
    risk_level: str,
    source: str,
    operations_count: int,
) -> dict[str, Any]:
    return {
        "ok": 1,
        "text": base_text,
        "problems": [],
        "doc_ir": app_v2._safe_doc_ir_payload(base_text),
        "note": note,
        "requires_confirmation": True,
        "confirmation_reason": confirmation_reason or "high_risk_edit",
        "risk_level": risk_level or "high",
        "plan_source": source or "rules",
        "operations_count": int(operations_count or 0),
        "confirmation_action": "confirm_apply",
    }


def prepare_generation_config(
    *,
    app_v2: Any,
    session: Any,
    raw_instruction: str,
    compose_instruction: str,
    resume_sections: list[str],
    base_text: str,
) -> tuple[str, Any, int]:
    analysis_timeout = float(app_v2.os.environ.get("WRITING_AGENT_ANALYSIS_MAX_S", "20"))
    analysis = app_v2._run_with_timeout(
        lambda: app_v2._run_message_analysis(session, compose_instruction),
        analysis_timeout,
        app_v2._normalize_analysis({}, compose_instruction),
    )
    analysis_instruction = app_v2._compose_analysis_input(compose_instruction, analysis)
    instruction = app_v2._augment_instruction(
        analysis_instruction,
        formatting=session.formatting or {},
        generation_prefs=session.generation_prefs or {},
    )

    if (not resume_sections) and (not session.template_required_h2) and (not session.template_outline):
        auto_outline = app_v2._default_outline_from_instruction(raw_instruction)
        if auto_outline:
            session.template_required_h2 = auto_outline
            app_v2.store.put(session)

    target_chars = app_v2._resolve_target_chars(session.formatting or {}, session.generation_prefs or {})
    if target_chars <= 0:
        target_chars = app_v2._extract_target_chars_from_instruction(raw_instruction)
    if target_chars > 0:
        raw_margin = app_v2.os.environ.get("WRITING_AGENT_TARGET_MARGIN", "").strip()
        try:
            margin = float(raw_margin) if raw_margin else 0.15
        except Exception:
            margin = 0.15
        margin = max(0.0, min(0.3, margin))
        internal_target = int(round(target_chars * (1.0 + margin)))
        cfg = app_v2.GenerateConfig(
            workers=int(app_v2.os.environ.get("WRITING_AGENT_WORKERS", "12")),
            min_total_chars=internal_target,
            max_total_chars=0,
        )
    else:
        cfg = app_v2.GenerateConfig(workers=int(app_v2.os.environ.get("WRITING_AGENT_WORKERS", "12")))
    return instruction, cfg, target_chars
