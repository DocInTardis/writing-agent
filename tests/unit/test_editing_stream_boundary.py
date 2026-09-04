from __future__ import annotations

import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from writing_agent.web.api import editing_flow
from writing_agent.workflows.editing_request_workflow import (
    BlockEditDeps,
    BlockEditRequest,
    DiagramGenerateRequest,
    DocIRRequest,
    InlineAIDeps,
    InlineAIRequest,
    InlineAIStreamEvent,
    RenderFigureRequest,
    run_inline_ai_stream_workflow,
)


class _HTTPException(Exception):
    def __init__(self, *, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _request(engine_type: type) -> tuple[InlineAIRequest, InlineAIDeps]:
    operation = SimpleNamespace(value="improve")
    module = SimpleNamespace(
        InlineAIEngine=engine_type,
        InlineOperation=lambda _value: operation,
        InlineContext=lambda **kwargs: SimpleNamespace(**kwargs),
        ToneStyle=lambda value: value,
    )
    return (
        InlineAIRequest(
            session=SimpleNamespace(doc_text=""),
            data={"operation": "improve", "selected_text": "text"},
        ),
        InlineAIDeps(
            exception_factory=_HTTPException,
            normalize_inline_context_policy_fn=lambda _raw: {},
            trim_inline_context_fn=lambda **_kwargs: ("", "", {}),
            inline_ai_module=module,
        ),
    )


def test_workflow_module_has_no_http_response_imports() -> None:
    path = Path(__file__).parents[2] / "writing_agent" / "workflows" / "editing_request_workflow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(name == "fastapi" or name.startswith("fastapi.") for name in imports)
    assert not any(name == "starlette" or name.startswith("starlette.") for name in imports)


def test_inline_request_contains_input_not_web_services() -> None:
    assert set(InlineAIRequest.__dataclass_fields__) == {"session", "data"}
    assert set(InlineAIDeps.__dataclass_fields__) == {
        "exception_factory",
        "normalize_inline_context_policy_fn",
        "trim_inline_context_fn",
        "inline_ai_module",
    }


def test_block_edit_request_contains_input_not_web_services() -> None:
    assert set(BlockEditRequest.__dataclass_fields__) == {"session", "data"}
    assert "exception_factory" in BlockEditDeps.__dataclass_fields__
    assert "persist_session" in BlockEditDeps.__dataclass_fields__


def test_remaining_editing_requests_contain_no_web_service_locator() -> None:
    assert set(DocIRRequest.__dataclass_fields__) == {"session", "data"}
    assert set(RenderFigureRequest.__dataclass_fields__) == {"data"}
    assert set(DiagramGenerateRequest.__dataclass_fields__) == {"data"}

    path = Path(__file__).parents[2] / "writing_agent" / "workflows" / "editing_request_workflow.py"
    assert "app_v2" not in path.read_text(encoding="utf-8")


def test_stream_is_closed_when_consumer_stops_early() -> None:
    closed = False

    class _Engine:
        async def execute_operation_stream(self, *_args, **_kwargs):
            nonlocal closed
            try:
                yield {"type": "delta", "content": "one"}
                yield {"type": "delta", "content": "two"}
            finally:
                closed = True

    async def exercise() -> None:
        request, deps = _request(_Engine)
        events = await run_inline_ai_stream_workflow(request=request, deps=deps)
        assert (await anext(events)).event == "context_meta"
        assert (await anext(events)).payload["content"] == "one"
        await events.aclose()

    asyncio.run(exercise())
    assert closed is True


def test_stream_failure_becomes_structured_error_and_closes_source() -> None:
    closed = False

    class _Engine:
        async def execute_operation_stream(self, *_args, **_kwargs):
            nonlocal closed
            try:
                yield {"type": "start"}
                raise RuntimeError("provider failed")
            finally:
                closed = True

    async def exercise() -> list[tuple[str, dict]]:
        request, deps = _request(_Engine)
        events = await run_inline_ai_stream_workflow(request=request, deps=deps)
        return [(item.event, item.payload) async for item in events]

    events = asyncio.run(exercise())
    assert events[-1] == ("error", {"error": "provider failed"})
    assert closed is True


def test_web_adapter_serializes_structured_events_as_sse() -> None:
    async def fake_workflow(*, request, deps):
        _ = request, deps

        async def events():
            yield InlineAIStreamEvent("context_meta", {"language": "中文"})
            yield InlineAIStreamEvent("delta", {"content": "片段"})

        return events()

    app = SimpleNamespace(
        HTTPException=_HTTPException,
        logger=SimpleNamespace(error=lambda *_args, **_kwargs: None),
        store=SimpleNamespace(get=lambda _doc_id: SimpleNamespace(doc_text="")),
    )
    request = SimpleNamespace(json=lambda: None)

    async def request_json():
        return {"operation": "improve", "selected_text": "text"}

    request.json = request_json

    async def exercise() -> tuple[str, str, dict[str, str]]:
        with (
            patch.object(editing_flow, "_app_v2", return_value=app),
            patch.object(editing_flow, "run_inline_ai_stream_workflow", fake_workflow),
        ):
            response = await editing_flow.inline_ai_stream("doc", request)
            body = "".join([str(chunk) async for chunk in response.body_iterator])
            return body, response.media_type or "", dict(response.headers)

    body, media_type, headers = asyncio.run(exercise())
    assert "event: context_meta" in body
    assert '"language": "中文"' in body
    assert "event: delta" in body
    assert media_type == "text/event-stream"
    assert headers["cache-control"] == "no-cache"
