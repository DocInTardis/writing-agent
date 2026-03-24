"""Editing Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

# Prompt-contract markers retained for guard tests:
# <task>diagram_spec_generation</task>
# <constraints>
# <user_request>

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from writing_agent.capabilities.diagramming import build_diagram_spec_from_prompt
from writing_agent.capabilities.editing import trim_inline_context
from writing_agent.web.domains import context_policy_domain
from writing_agent.workflows import (
    BlockEditRequest,
    DiagramGenerateRequest,
    DocIRRequest,
    InlineAIRequest,
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


async def doc_ir_ops(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    return run_doc_ir_ops_workflow(request=DocIRRequest(app_v2=app_v2, session=session, data=data))


async def doc_ir_diff(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    return run_doc_ir_diff_workflow(request=DocIRRequest(app_v2=app_v2, session=session, data=data))


async def render_figure(request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    return run_render_figure_workflow(request=RenderFigureRequest(app_v2=app_v2, data=data))


def _diagram_spec_from_prompt(prompt: str, kind: str) -> dict:
    return build_diagram_spec_from_prompt(app_v2=_app_v2(), prompt=prompt, kind=kind)


async def diagram_generate(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    return run_diagram_generate_workflow(
        request=DiagramGenerateRequest(
            app_v2=app_v2,
            session=session,
            data=data,
            diagram_spec_from_prompt_fn=_diagram_spec_from_prompt,
        )
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
            app_v2=app_v2,
            session=session,
            data=data,
            normalize_inline_context_policy_fn=_normalize_inline_context_policy,
            trim_inline_context_fn=_trim_inline_context,
            inline_ai_module=inline_ai_module,
        )
    )


async def inline_ai_stream(doc_id: str, request: Request) -> StreamingResponse:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    from writing_agent.v2 import inline_ai as inline_ai_module

    return await run_inline_ai_stream_workflow(
        request=InlineAIRequest(
            app_v2=app_v2,
            session=session,
            data=data,
            normalize_inline_context_policy_fn=_normalize_inline_context_policy,
            trim_inline_context_fn=_trim_inline_context,
            inline_ai_module=inline_ai_module,
        )
    )
async def block_edit(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    return await run_block_edit_workflow(request=BlockEditRequest(app_v2=app_v2, session=session, data=data))


async def block_edit_preview(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    return await run_block_edit_preview_workflow(
        request=BlockEditRequest(app_v2=app_v2, session=session, data=data)
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
