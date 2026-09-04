"""Service-facing revision workflow facade."""

# Prompt-contract markers retained for revision fallback chat flows:
# <task>revise_full_document</task>
# <constraints>

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

SectionResolver = Callable[..., dict[str, object] | None]
HeadingNormalizer = Callable[[object], str]
RevisionPromptBuilder = Callable[..., tuple[str, str]]
RevisionTextExtractor = Callable[[object], str]
RevisionValidator = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class RevisionRequest:
    session: Any
    data: dict[str, Any]


@dataclass(frozen=True)
class RevisionDeps:
    environ: dict[str, str]
    exception_factory: Callable[..., Exception]
    doc_ir_from_dict: Callable[..., Any]
    doc_ir_to_text: Callable[..., str]
    get_model_settings: Callable[..., Any]
    create_model_client: Callable[..., Any]
    analyze_message: Callable[..., Any]
    hard_constraints: Callable[..., Any]
    decide_revision: Callable[..., Any]
    try_selected_edit: Callable[..., Any]
    replace_question_headings: Callable[..., str]
    postprocess_output: Callable[..., str]
    set_doc_text: Callable[..., None]
    persist_session: Callable[..., None]
    sanitize_output: Callable[..., str]
    looks_like_prompt_echo: Callable[..., bool]
    safe_doc_ir_payload: Callable[..., Any]
    normalize_heading_text_fn: HeadingNormalizer
    resolve_target_section_selection_fn: SectionResolver
    build_revision_fallback_prompt_fn: RevisionPromptBuilder
    extract_revision_fallback_text_fn: RevisionTextExtractor
    validate_revision_candidate_fn: RevisionValidator


def run_revision_workflow(*, request: RevisionRequest, deps: RevisionDeps) -> dict[str, Any]:
    session = request.session
    data = request.data
    resolve_target_section_selection_fn = deps.resolve_target_section_selection_fn
    build_revision_fallback_prompt_fn = deps.build_revision_fallback_prompt_fn
    extract_revision_fallback_text_fn = deps.extract_revision_fallback_text_fn
    validate_revision_candidate_fn = deps.validate_revision_candidate_fn

    instruction = str(data.get("instruction") or "").strip()
    if not instruction:
        raise deps.exception_factory(status_code=400, detail="instruction required")
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
    input_doc_ir = None
    if incoming_ir is not None:
        if not isinstance(incoming_ir, dict) or not isinstance(incoming_ir.get("sections"), list):
            raise deps.exception_factory(status_code=400, detail="invalid document structure")
        try:
            input_doc_ir = deepcopy(incoming_ir)
            text = deps.doc_ir_to_text(deps.doc_ir_from_dict(deepcopy(input_doc_ir)))
        except Exception as exc:
            raise deps.exception_factory(status_code=400, detail="invalid document structure") from exc
    else:
        text = str(data.get("text") or session.doc_text or "")

    target_section = str(data.get("target_section") or "").strip()
    if target_section and not selection_text:
        selection_resolved = resolve_target_section_selection_fn(
            text=text,
            section_title=target_section,
            normalize_heading_text=deps.normalize_heading_text_fn,
        )
        if selection_resolved:
            selection_payload = selection_resolved
            selection_text = str(selection_resolved.get("text") or "").strip()
        else:
            raise deps.exception_factory(status_code=400, detail=f"target section not found: {target_section}")

    base_text = text
    if not text.strip():
        raise deps.exception_factory(status_code=400, detail="empty document")

    settings = deps.get_model_settings()
    if not settings.enabled:
        raise deps.exception_factory(status_code=400, detail="Ollama is not enabled")
    client_probe = deps.create_model_client(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client_probe.is_running():
        raise deps.exception_factory(status_code=400, detail="Ollama is not running")

    analysis = deps.analyze_message(session, instruction)
    analysis_instruction = str(analysis.get("rewritten_query") or instruction).strip() or instruction
    model = deps.environ.get("WRITING_AGENT_REVISE_MODEL", "").strip() or settings.model
    hard_constraints = dict(deps.hard_constraints(session, analysis_instruction, base_text) or {})

    decision = deps.decide_revision(
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

        revised = deps.try_selected_edit(
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
            text = deps.replace_question_headings(text)
            if not text.strip():
                raise deps.exception_factory(status_code=500, detail="revision produced empty text")
            text = deps.postprocess_output(
                session,
                text,
                instruction,
                current_text=base_text,
                base_text=base_text,
            )
            if not text.strip():
                raise deps.exception_factory(status_code=500, detail="revision produced empty text")
            deps.set_doc_text(session, text)
            deps.persist_session(session)
            out = {"ok": 1, "text": text, "doc_ir": session.doc_ir or {}, "note": note}
            if revision_status:
                out["revision_meta"] = revision_status
            return out
        if not allow_unscoped_fallback:
            out = {
                "ok": 1, "text": text,
                "doc_ir": input_doc_ir if input_doc_ir is not None else deps.safe_doc_ir_payload(text),
                "applied": False,
            }
            if revision_status:
                out["revision_meta"] = revision_status
            return out

    client = deps.create_model_client(base_url=settings.base_url, model=model, timeout_s=settings.timeout_s)
    system, user = build_revision_fallback_prompt_fn(
        instruction=analysis_instruction,
        plan_steps=plan_steps,
        text=text,
        hard_constraints=hard_constraints,
    )
    buf: list[str] = []
    stream = client.chat_stream(system=system, user=user, temperature=0.25)
    try:
        for delta in stream:
            buf.append(delta)
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    raw_fallback = "".join(buf).strip()
    parsed_fallback = extract_revision_fallback_text_fn(raw_fallback)
    text = deps.sanitize_output(parsed_fallback or text)
    if deps.looks_like_prompt_echo(text, analysis_instruction):
        text = base_text
    normalized_text = str(text or "").strip().lower()
    if normalized_text and normalized_text in {
        str(analysis_instruction or "").strip().lower(),
        str(instruction or "").strip().lower(),
    }:
        text = base_text
    text = deps.replace_question_headings(text)

    if not text.strip():
        raise deps.exception_factory(status_code=500, detail="revision produced empty text")

    text = deps.postprocess_output(
        session,
        text,
        instruction,
        current_text=base_text,
        base_text=base_text,
    )
    if not text.strip():
        raise deps.exception_factory(status_code=500, detail="revision produced empty text")
    validation = validate_revision_candidate_fn(
        candidate_text=text,
        base_text=base_text,
        hard_constraints=hard_constraints,
    )
    if not bool(validation.get("passed")):
        out = {
            "ok": 1,
            "text": base_text,
            "doc_ir": deps.safe_doc_ir_payload(base_text),
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

    deps.set_doc_text(session, text)
    deps.persist_session(session)
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


__all__ = ["RevisionRequest", "RevisionDeps", "run_revision_workflow"]
