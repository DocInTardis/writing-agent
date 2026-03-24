"""Service-facing revision workflow facade."""

# Prompt-contract markers retained for revision fallback chat flows:
# <task>revise_full_document</task>
# <constraints>

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

SectionResolver = Callable[..., dict[str, object] | None]
HeadingNormalizer = Callable[[object], str]
RevisionPromptBuilder = Callable[..., tuple[str, str]]
RevisionTextExtractor = Callable[[object], str]
RevisionValidator = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class RevisionRequest:
    app_v2: Any
    session: Any
    data: dict[str, Any]
    fallback_normalize_heading_text_fn: HeadingNormalizer
    resolve_target_section_selection_fn: SectionResolver
    build_revision_fallback_prompt_fn: RevisionPromptBuilder
    extract_revision_fallback_text_fn: RevisionTextExtractor
    validate_revision_candidate_fn: RevisionValidator


def run_revision_workflow(*, request: RevisionRequest) -> dict[str, Any]:
    app_v2 = request.app_v2
    session = request.session
    data = request.data
    fallback_normalize_heading_text_fn = request.fallback_normalize_heading_text_fn
    resolve_target_section_selection_fn = request.resolve_target_section_selection_fn
    build_revision_fallback_prompt_fn = request.build_revision_fallback_prompt_fn
    extract_revision_fallback_text_fn = request.extract_revision_fallback_text_fn
    validate_revision_candidate_fn = request.validate_revision_candidate_fn

    instruction = str(data.get("instruction") or "").strip()
    raw_selection = data.get("selection")
    selection_text = (
        str(raw_selection.get("text") or "") if isinstance(raw_selection, dict) else str(raw_selection or "")
    ).strip()
    selection_payload: object = raw_selection
    if not selection_text:
        fallback_selection_text = str(data.get("selection_text") or "").strip()
        if fallback_selection_text:
            selection_text = fallback_selection_text
            if not isinstance(selection_payload, dict):
                selection_payload = fallback_selection_text
    context_policy = data.get("context_policy")
    allow_unscoped_fallback = bool(data.get("allow_unscoped_fallback") is True)
    incoming_ir = data.get("doc_ir")
    if isinstance(incoming_ir, dict) and incoming_ir.get("sections") is not None:
        try:
            session.doc_ir = incoming_ir
            text = app_v2.doc_ir_to_text(app_v2.doc_ir_from_dict(session.doc_ir))
        except Exception:
            text = str(data.get("text") or session.doc_text or "")
    else:
        text = str(data.get("text") or session.doc_text or "")

    target_section = str(data.get("target_section") or "").strip()
    if target_section and not selection_text:
        normalize_heading_text = getattr(app_v2, "_normalize_heading_text", None)
        if not callable(normalize_heading_text):
            normalize_heading_text = fallback_normalize_heading_text_fn
        selection_resolved = resolve_target_section_selection_fn(
            text=text,
            section_title=target_section,
            normalize_heading_text=normalize_heading_text,
        )
        if selection_resolved:
            selection_payload = selection_resolved
            selection_text = str(selection_resolved.get("text") or "").strip()
        else:
            raise app_v2.HTTPException(status_code=400, detail=f"target section not found: {target_section}")

    base_text = text
    if not instruction:
        raise app_v2.HTTPException(status_code=400, detail="instruction required")
    if not text.strip():
        raise app_v2.HTTPException(status_code=400, detail="empty document")

    settings = app_v2.get_ollama_settings()
    if not settings.enabled:
        raise app_v2.HTTPException(status_code=400, detail="Ollama is not enabled")
    client_probe = app_v2.OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client_probe.is_running():
        raise app_v2.HTTPException(status_code=400, detail="Ollama is not running")

    analysis = app_v2._run_message_analysis(session, instruction)
    analysis_instruction = str(analysis.get("rewritten_query") or instruction).strip() or instruction
    model = app_v2.os.environ.get("WRITING_AGENT_REVISE_MODEL", "").strip() or settings.model
    hard_constraints = dict(app_v2._revision_hard_constraints(session, analysis_instruction, base_text) or {})

    decision = app_v2._revision_decision_with_model(
        base_url=settings.base_url,
        model=model,
        instruction=analysis_instruction,
        selection=selection_text,
        text=text,
    )
    if isinstance(decision, dict) and decision.get("should_apply") is False:
        return {"ok": 1, "text": text}

    plan_steps: list[str] = []
    if isinstance(decision, dict):
        plan_steps = [str(x).strip() for x in (decision.get("plan") or []) if str(x).strip()]

    revision_status: dict[str, object] = {}
    if selection_text:
        def _capture_revision_status(payload: dict[str, object]) -> None:
            if isinstance(payload, dict):
                revision_status.update(payload)

        revised = app_v2._try_revision_edit(
            session=session,
            instruction=analysis_instruction,
            text=text,
            selection=selection_payload if selection_payload is not None else selection_text,
            analysis=analysis,
            context_policy=context_policy,
            report_status=_capture_revision_status,
        )
        if revised:
            text, note = revised
            text = app_v2._replace_question_headings(text)
            if not text.strip():
                raise app_v2.HTTPException(status_code=500, detail="revision produced empty text")
            text = app_v2._postprocess_output_text(
                session,
                text,
                instruction,
                current_text=base_text,
                base_text=base_text,
            )
            app_v2._set_doc_text(session, text)
            app_v2.store.put(session)
            out = {"ok": 1, "text": text, "doc_ir": session.doc_ir or {}, "note": note}
            if revision_status:
                out["revision_meta"] = revision_status
            return out
        if not allow_unscoped_fallback:
            out = {"ok": 1, "text": text, "doc_ir": session.doc_ir or {}, "applied": False}
            if revision_status:
                out["revision_meta"] = revision_status
            return out

    client = app_v2.OllamaClient(base_url=settings.base_url, model=model, timeout_s=settings.timeout_s)
    system, user = build_revision_fallback_prompt_fn(
        instruction=analysis_instruction,
        plan_steps=plan_steps,
        text=text,
        hard_constraints=hard_constraints,
    )
    buf: list[str] = []
    for delta in client.chat_stream(system=system, user=user, temperature=0.25):
        buf.append(delta)
    raw_fallback = "".join(buf).strip()
    parsed_fallback = extract_revision_fallback_text_fn(raw_fallback)
    text = app_v2._sanitize_output_text(parsed_fallback or text)
    if app_v2._looks_like_prompt_echo(text, analysis_instruction):
        text = base_text
    normalized_text = str(text or "").strip().lower()
    if normalized_text and normalized_text in {
        str(analysis_instruction or "").strip().lower(),
        str(instruction or "").strip().lower(),
    }:
        text = base_text
    text = app_v2._replace_question_headings(text)

    if not text.strip():
        raise app_v2.HTTPException(status_code=500, detail="revision produced empty text")

    text = app_v2._postprocess_output_text(
        session,
        text,
        instruction,
        current_text=base_text,
        base_text=base_text,
    )
    validation = validate_revision_candidate_fn(
        app_v2,
        candidate_text=text,
        base_text=base_text,
        hard_constraints=hard_constraints,
    )
    if not bool(validation.get("passed")):
        out = {
            "ok": 1,
            "text": base_text,
            "doc_ir": app_v2._safe_doc_ir_payload(base_text),
            "applied": False,
            "revision_meta": {
                "ok": False,
                "error_code": "E_REVISION_HARD_GATE_REJECTED",
                "selection_source": "full_document_fallback",
                "reasons": list(validation.get("reasons") or []),
                "score_delta": float(validation.get("score_delta") or 0.0),
                "validation": validation,
            },
        }
        if revision_status:
            out["revision_meta"]["selection_status"] = dict(revision_status)
        return out

    app_v2._set_doc_text(session, text)
    app_v2.store.put(session)
    out = {"ok": 1, "text": text, "doc_ir": session.doc_ir or {}}
    fallback_meta = {
        "ok": True,
        "error_code": "",
        "selection_source": "full_document_fallback",
        "reasons": list(validation.get("reasons") or []),
        "score_delta": float(validation.get("score_delta") or 0.0),
        "validation": validation,
    }
    if revision_status:
        fallback_meta["selection_status"] = dict(revision_status)
    out["revision_meta"] = fallback_meta
    return out


__all__ = [name for name in globals() if not name.startswith("__")]
