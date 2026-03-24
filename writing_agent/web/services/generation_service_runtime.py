"""Runtime helpers for section generation and revision request flows."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from writing_agent.workflows import (
    GenerateSectionRequest,
    RevisionRequest,
    run_generate_section_graph,
    run_revision_workflow,
)

SectionResolver = Callable[..., dict[str, object] | None]
HeadingNormalizer = Callable[[object], str]
RevisionPromptBuilder = Callable[..., tuple[str, str]]
RevisionTextExtractor = Callable[[object], str]
RevisionValidator = Callable[..., dict[str, Any]]


def run_section_generation_request(*, app_v2: Any, session: Any, data: dict[str, Any]) -> dict[str, Any]:
    section = str(data.get("section") or "").strip()
    if not section:
        raise app_v2.HTTPException(status_code=400, detail="section required")

    instruction = str(data.get("instruction") or "").strip() or str(getattr(session, "last_instruction", "") or "")
    current_text = str(getattr(session, "doc_text", "") or "")
    cfg = app_v2.GenerateConfig(workers=1, min_total_chars=0, max_total_chars=0)

    try:
        final_text, graph_meta = run_generate_section_graph(
            request=GenerateSectionRequest(
                app_v2=app_v2,
                session=session,
                section=section,
                instruction=instruction,
                current_text=current_text,
                cfg=cfg,
            )
        )
    except Exception as exc:
        raise app_v2.HTTPException(status_code=500, detail=f"section generation failed: {exc}") from exc

    if not final_text:
        raise app_v2.HTTPException(status_code=500, detail="section generation produced no text")

    try:
        from writing_agent.v2.graph_runner import _apply_section_updates  # type: ignore

        updated = _apply_section_updates(current_text, final_text, [section])
    except Exception:
        updated = final_text

    app_v2._set_doc_text(session, updated)
    app_v2.store.put(session)
    final_doc_ir = (
        session.doc_ir
        if isinstance(getattr(session, "doc_ir", None), dict)
        else app_v2._safe_doc_ir_payload(updated)
    )
    out = {"ok": 1, "text": updated, "doc_ir": final_doc_ir}
    if graph_meta:
        out["graph_meta"] = graph_meta
    return out


def run_revision_request(
    *,
    app_v2: Any,
    session: Any,
    data: dict[str, Any],
    fallback_normalize_heading_text_fn: HeadingNormalizer,
    resolve_target_section_selection_fn: SectionResolver,
    build_revision_fallback_prompt_fn: RevisionPromptBuilder,
    extract_revision_fallback_text_fn: RevisionTextExtractor,
    validate_revision_candidate_fn: RevisionValidator,
) -> dict[str, Any]:
    return run_revision_workflow(
        request=RevisionRequest(
            app_v2=app_v2,
            session=session,
            data=data,
            fallback_normalize_heading_text_fn=fallback_normalize_heading_text_fn,
            resolve_target_section_selection_fn=resolve_target_section_selection_fn,
            build_revision_fallback_prompt_fn=build_revision_fallback_prompt_fn,
            extract_revision_fallback_text_fn=extract_revision_fallback_text_fn,
            validate_revision_candidate_fn=validate_revision_candidate_fn,
        )
    )
