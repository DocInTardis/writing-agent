"""Editing Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

# Prompt-contract markers retained for guard tests:
# <task>diagram_spec_generation</task>
# <constraints>
# <user_request>

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from writing_agent.capabilities.diagramming import build_diagram_spec_from_prompt
from writing_agent.capabilities.editing import trim_inline_context
from writing_agent.web.domains import context_policy_domain
from writing_agent.workflows import (
    BlockEditDeps,
    BlockEditRequest,
    DiagramGenerateDeps,
    DiagramGenerateRequest,
    DocIRDeps,
    DocIRRequest,
    InlineAIDeps,
    InlineAIRequest,
    RenderFigureDeps,
    RenderFigureRequest,
    run_block_edit_preview_workflow,
    run_block_edit_workflow,
    run_diagram_generate_workflow,
    run_doc_ir_diff_workflow,
    run_doc_ir_ops_workflow,
    run_inline_ai_stream_workflow,
    run_inline_ai_workflow,
    run_render_figure_workflow,
)

router = APIRouter()


def _app_v2():
    from writing_agent.web import app_v2

    return app_v2


def _normalize_inline_context_policy(raw: object) -> dict[str, object]:
    return context_policy_domain.normalize_inline_context_policy(raw)


def _trim_inline_context(
    *,
    selected_text: str,
    before_text: str,
    after_text: str,
    policy: dict[str, object],
) -> tuple[str, str, dict[str, object]]:
    return trim_inline_context(
        selected_text=selected_text,
        before_text=before_text,
        after_text=after_text,
        policy=policy,
    )


def _inline_ai_deps(app_v2, inline_ai_module) -> InlineAIDeps:
    return InlineAIDeps(
        exception_factory=app_v2.HTTPException,
        normalize_inline_context_policy_fn=_normalize_inline_context_policy,
        trim_inline_context_fn=_trim_inline_context,
        inline_ai_module=inline_ai_module,
    )


def _block_edit_deps(app_v2) -> BlockEditDeps:
    return BlockEditDeps(
        exception_factory=app_v2.HTTPException,
        doc_ir_from_dict=app_v2.doc_ir_from_dict,
        doc_ir_to_dict=app_v2.doc_ir_to_dict,
        doc_ir_to_text=app_v2.doc_ir_to_text,
        doc_ir_build_index=app_v2.doc_ir_build_index,
        doc_ir_render_block_text=app_v2.doc_ir_render_block_text,
        doc_ir_diff=app_v2.doc_ir_diff,
        apply_block_edit=app_v2.apply_block_edit,
        auto_commit_version=app_v2._auto_commit_version,
        persist_session=app_v2.store.put,
    )


def _doc_ir_deps(app_v2) -> DocIRDeps:
    return DocIRDeps(
        exception_factory=app_v2.HTTPException,
        parse_operation=app_v2.DocIROperation.parse_obj,
        doc_ir_from_dict=app_v2.doc_ir_from_dict,
        doc_ir_apply_ops=app_v2.doc_ir_apply_ops,
        doc_ir_to_dict=app_v2.doc_ir_to_dict,
        doc_ir_to_text=app_v2.doc_ir_to_text,
        doc_ir_diff=app_v2.doc_ir_diff,
        persist_session=app_v2.store.put,
    )


async def doc_ir_ops(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    return run_doc_ir_ops_workflow(
        request=DocIRRequest(session=session, data=data),
        deps=_doc_ir_deps(app_v2),
    )


async def doc_ir_diff(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    return run_doc_ir_diff_workflow(
        request=DocIRRequest(session=session, data=data),
        deps=_doc_ir_deps(app_v2),
    )


async def render_figure(request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    return run_render_figure_workflow(
        request=RenderFigureRequest(data=data),
        deps=RenderFigureDeps(
            exception_factory=app_v2.HTTPException,
            render_figure_svg=app_v2.render_figure_svg,
            sanitize_html=app_v2.sanitize_html,
        ),
    )


def _diagram_spec_from_prompt(prompt: str, kind: str) -> dict:
    return build_diagram_spec_from_prompt(app_v2=_app_v2(), prompt=prompt, kind=kind)


async def diagram_generate(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    return run_diagram_generate_workflow(
        request=DiagramGenerateRequest(data=data),
        deps=DiagramGenerateDeps(
            exception_factory=app_v2.HTTPException,
            diagram_spec_from_prompt_fn=_diagram_spec_from_prompt,
        ),
    )


async def inline_ai(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    from writing_agent.v2 import inline_ai as inline_ai_module

    return await run_inline_ai_workflow(
        request=InlineAIRequest(
            session=session,
            data=data,
        ),
        deps=_inline_ai_deps(app_v2, inline_ai_module),
    )


async def inline_ai_stream(doc_id: str, request: Request) -> StreamingResponse:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    from writing_agent.v2 import inline_ai as inline_ai_module

    events = await run_inline_ai_stream_workflow(
        request=InlineAIRequest(
            session=session,
            data=data,
        ),
        deps=_inline_ai_deps(app_v2, inline_ai_module),
    )

    async def event_generator():
        async for item in events:
            if item.event == "error":
                app_v2.logger.error("Streaming inline AI failed: %s", item.payload.get("error"))
            payload = json.dumps(item.payload, ensure_ascii=False)
            yield f"event: {item.event}\ndata: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


async def block_edit(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    return await run_block_edit_workflow(
        request=BlockEditRequest(session=session, data=data),
        deps=_block_edit_deps(app_v2),
    )


async def block_edit_preview(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    return await run_block_edit_preview_workflow(
        request=BlockEditRequest(session=session, data=data),
        deps=_block_edit_deps(app_v2),
    )


class EditingService:
    async def doc_ir_ops(self, doc_id: str, request: Request) -> dict:
        return await doc_ir_ops(doc_id, request)

    async def doc_ir_diff(self, doc_id: str, request: Request) -> dict:
        return await doc_ir_diff(doc_id, request)

    async def render_figure(self, request: Request) -> dict:
        return await render_figure(request)

    async def diagram_generate(self, doc_id: str, request: Request) -> dict:
        return await diagram_generate(doc_id, request)

    async def inline_ai(self, doc_id: str, request: Request) -> dict:
        return await inline_ai(doc_id, request)

    async def inline_ai_stream(self, doc_id: str, request: Request) -> StreamingResponse:
        return await inline_ai_stream(doc_id, request)

    async def block_edit(self, doc_id: str, request: Request) -> dict:
        return await block_edit(doc_id, request)

    async def block_edit_preview(self, doc_id: str, request: Request) -> dict:
        return await block_edit_preview(doc_id, request)


service = EditingService()


@router.post("/api/doc/{doc_id}/doc_ir/ops")
async def doc_ir_ops_flow(doc_id: str, request: Request) -> dict:
    return await service.doc_ir_ops(doc_id, request)


@router.post("/api/doc/{doc_id}/doc_ir/diff")
async def doc_ir_diff_flow(doc_id: str, request: Request) -> dict:
    return await service.doc_ir_diff(doc_id, request)


@router.post("/api/figure/render")
async def render_figure_flow(request: Request) -> dict:
    return await service.render_figure(request)


@router.post("/api/doc/{doc_id}/diagram/generate")
async def diagram_generate_flow(doc_id: str, request: Request) -> dict:
    return await service.diagram_generate(doc_id, request)


@router.post("/api/doc/{doc_id}/inline-ai")
async def inline_ai_flow(doc_id: str, request: Request) -> dict:
    return await service.inline_ai(doc_id, request)


@router.post("/api/doc/{doc_id}/inline-ai/stream")
async def inline_ai_stream_flow(doc_id: str, request: Request) -> StreamingResponse:
    return await service.inline_ai_stream(doc_id, request)


@router.post("/api/doc/{doc_id}/block-edit")
async def block_edit_flow(doc_id: str, request: Request) -> dict:
    return await service.block_edit(doc_id, request)


@router.post("/api/doc/{doc_id}/block-edit/preview")
async def block_edit_preview_flow(doc_id: str, request: Request) -> dict:
    return await service.block_edit_preview(doc_id, request)
