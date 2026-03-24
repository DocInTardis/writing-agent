"""Service-facing editing workflow facade."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi.responses import StreamingResponse

from writing_agent.capabilities.editing import (
    build_block_edit_variants,
    clone_doc_ir,
    extract_block_text_from_ir,
    prepare_inline_request,
)

ContextPolicyNormalizer = Callable[[object], dict[str, object]]
InlineContextTrimmer = Callable[..., tuple[str, str, dict[str, object]]]


@dataclass(frozen=True)
class InlineAIRequest:
    app_v2: Any
    session: Any
    data: dict[str, Any]
    normalize_inline_context_policy_fn: ContextPolicyNormalizer
    trim_inline_context_fn: InlineContextTrimmer
    inline_ai_module: Any


@dataclass(frozen=True)
class BlockEditRequest:
    app_v2: Any
    session: Any
    data: dict[str, Any]


@dataclass(frozen=True)
class DocIRRequest:
    app_v2: Any
    session: Any
    data: dict[str, Any]


@dataclass(frozen=True)
class RenderFigureRequest:
    app_v2: Any
    data: dict[str, Any]


@dataclass(frozen=True)
class DiagramGenerateRequest:
    app_v2: Any
    session: Any
    data: dict[str, Any]
    diagram_spec_from_prompt_fn: Callable[[str, str], dict[str, Any]]


def _prepare_inline_request(request: InlineAIRequest):
    try:
        return prepare_inline_request(
            data=request.data,
            normalize_inline_context_policy_fn=request.normalize_inline_context_policy_fn,
            trim_inline_context_fn=request.trim_inline_context_fn,
            inline_operation_cls=request.inline_ai_module.InlineOperation,
            inline_context_cls=request.inline_ai_module.InlineContext,
            tone_style_cls=request.inline_ai_module.ToneStyle,
        )
    except ValueError as exc:
        raise request.app_v2.HTTPException(status_code=400, detail=str(exc)) from exc


async def run_inline_ai_workflow(*, request: InlineAIRequest) -> dict[str, Any]:
    prepared = _prepare_inline_request(request)
    engine = request.inline_ai_module.InlineAIEngine()
    result = await engine.execute_operation(prepared.operation, prepared.context, **prepared.kwargs)
    if not result.success:
        raise request.app_v2.HTTPException(status_code=500, detail=result.error or "operation failed")
    return {
        "ok": 1,
        "generated_text": result.generated_text,
        "operation": result.operation.value,
        "context_meta": prepared.context_meta,
    }


async def run_inline_ai_stream_workflow(*, request: InlineAIRequest) -> StreamingResponse:
    prepared = _prepare_inline_request(request)
    engine = request.inline_ai_module.InlineAIEngine()

    def emit(event: str, payload: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {request.app_v2.json.dumps(payload, ensure_ascii=False)}\n\n"

    async def event_generator():
        yield emit("context_meta", prepared.context_meta)
        try:
            async for event in engine.execute_operation_stream(prepared.operation, prepared.context, **prepared.kwargs):
                yield emit(str(event.get("type", "message")), event)
        except Exception as exc:
            request.app_v2.logger.error(f"Streaming inline AI failed: {exc}", exc_info=True)
            yield emit("error", {"error": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _require_block_edit_input(request: BlockEditRequest) -> tuple[str, str]:
    data = request.data
    if not isinstance(data, dict):
        raise request.app_v2.HTTPException(status_code=400, detail="body must be object")
    block_id = str(data.get("block_id") or "").strip()
    instruction = str(data.get("instruction") or "").strip()
    if not block_id or not instruction:
        raise request.app_v2.HTTPException(status_code=400, detail="block_id and instruction required")
    return block_id, instruction


def _resolve_base_ir(*, app_v2: Any, session: Any, data: dict[str, Any]):
    incoming_ir = data.get("doc_ir")
    if isinstance(incoming_ir, dict) and incoming_ir.get("sections") is not None:
        return app_v2.doc_ir_from_dict(incoming_ir)
    return app_v2.doc_ir_from_dict(session.doc_ir or {})


def _extract_block_text(*, app_v2: Any, doc_ir_obj: Any, block_id: str) -> str:
    return extract_block_text_from_ir(
        doc_ir_obj=doc_ir_obj,
        block_id=block_id,
        doc_ir_build_index_fn=app_v2.doc_ir_build_index,
        doc_ir_render_block_text_fn=app_v2.doc_ir_render_block_text,
    )


async def run_block_edit_workflow(*, request: BlockEditRequest) -> dict[str, Any]:
    app_v2 = request.app_v2
    session = request.session
    block_id, instruction = _require_block_edit_input(request)
    doc_ir = _resolve_base_ir(app_v2=app_v2, session=session, data=request.data)

    try:
        base_text = app_v2.doc_ir_to_text(doc_ir)
    except Exception:
        base_text = ""
    if base_text.strip():
        session.doc_text = base_text
        session.doc_ir = app_v2.doc_ir_to_dict(doc_ir)
        app_v2._auto_commit_version(session, "auto: before update")

    try:
        updated_ir, meta = await app_v2.apply_block_edit(doc_ir, block_id, instruction)
    except Exception as exc:
        raise app_v2.HTTPException(status_code=500, detail=str(exc)) from exc

    session.doc_ir = app_v2.doc_ir_to_dict(updated_ir)
    session.doc_text = app_v2.doc_ir_to_text(updated_ir)
    app_v2._auto_commit_version(session, "auto: after update")
    app_v2.store.put(session)
    return {"ok": 1, "doc_ir": session.doc_ir, "text": session.doc_text, "meta": meta}


async def run_block_edit_preview_workflow(*, request: BlockEditRequest) -> dict[str, Any]:
    app_v2 = request.app_v2
    block_id, instruction = _require_block_edit_input(request)
    base_ir = _resolve_base_ir(app_v2=app_v2, session=request.session, data=request.data)

    before_text = _extract_block_text(app_v2=app_v2, doc_ir_obj=base_ir, block_id=block_id)
    if not before_text:
        raise app_v2.HTTPException(status_code=404, detail="block not found")

    variants = build_block_edit_variants(instruction=instruction, variants_raw=request.data.get("variants"))

    candidates: list[dict[str, Any]] = []
    for item in variants:
        candidate_label = str(item.get("label") or "Variant").strip() or "Variant"
        candidate_instruction = str(item.get("instruction") or "").strip()
        if not candidate_instruction:
            continue
        try:
            working_ir = clone_doc_ir(
                doc_ir_obj=base_ir,
                doc_ir_to_dict_fn=app_v2.doc_ir_to_dict,
                doc_ir_from_dict_fn=app_v2.doc_ir_from_dict,
            )
            updated_ir, meta = await app_v2.apply_block_edit(working_ir, block_id, candidate_instruction)
            candidate_after = _extract_block_text(app_v2=app_v2, doc_ir_obj=updated_ir, block_id=block_id)
            candidates.append(
                {
                    "label": candidate_label,
                    "instruction": candidate_instruction,
                    "doc_ir": app_v2.doc_ir_to_dict(updated_ir),
                    "text": app_v2.doc_ir_to_text(updated_ir),
                    "selected_before": before_text,
                    "selected_after": candidate_after,
                    "diff": app_v2.doc_ir_diff(base_ir, updated_ir),
                    "meta": meta,
                }
            )
        except Exception as exc:
            candidates.append(
                {
                    "label": candidate_label,
                    "instruction": candidate_instruction,
                    "error": str(exc),
                    "selected_before": before_text,
                }
            )

    return {"ok": 1, "before": before_text, "candidates": candidates}


def run_doc_ir_ops_workflow(*, request: DocIRRequest) -> dict[str, Any]:
    app_v2 = request.app_v2
    session = request.session
    ops_raw = request.data.get("ops") or []
    ops: list[Any] = []
    for item in ops_raw:
        if not isinstance(item, dict):
            continue
        try:
            ops.append(app_v2.DocIROperation.parse_obj(item))
        except Exception:
            continue

    if not ops:
        raise app_v2.HTTPException(status_code=400, detail="ops required")

    doc_ir = app_v2.doc_ir_from_dict(session.doc_ir or {})
    doc_ir = app_v2.doc_ir_apply_ops(doc_ir, ops)
    session.doc_ir = app_v2.doc_ir_to_dict(doc_ir)
    session.doc_text = app_v2.doc_ir_to_text(doc_ir)
    app_v2.store.put(session)
    return {"ok": 1, "doc_ir": session.doc_ir, "text": session.doc_text}


def run_doc_ir_diff_workflow(*, request: DocIRRequest) -> dict[str, Any]:
    app_v2 = request.app_v2
    other = request.data.get("doc_ir")
    if not isinstance(other, dict):
        raise app_v2.HTTPException(status_code=400, detail="doc_ir must be object")

    cur = app_v2.doc_ir_from_dict(request.session.doc_ir or {})
    nxt = app_v2.doc_ir_from_dict(other)
    diff = app_v2.doc_ir_diff(cur, nxt)
    return {"ok": 1, "diff": diff}


def run_render_figure_workflow(*, request: RenderFigureRequest) -> dict[str, Any]:
    spec = request.data.get("spec") if isinstance(request.data, dict) else {}
    if not isinstance(spec, dict):
        raise request.app_v2.HTTPException(status_code=400, detail="spec must be object")

    svg, caption = request.app_v2.render_figure_svg(spec)
    safe_svg = request.app_v2.sanitize_html(svg)
    return {"svg": safe_svg, "caption": caption}


def run_diagram_generate_workflow(*, request: DiagramGenerateRequest) -> dict[str, Any]:
    prompt = str(request.data.get("prompt") or "").strip()
    kind = str(request.data.get("kind") or "flow").strip().lower()
    if not prompt:
        raise request.app_v2.HTTPException(status_code=400, detail="prompt required")

    spec = request.diagram_spec_from_prompt_fn(prompt, kind)
    return {"ok": 1, "spec": spec}


__all__ = [name for name in globals() if not name.startswith("__")]
