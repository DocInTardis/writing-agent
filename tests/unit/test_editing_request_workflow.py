from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace

from writing_agent.workflows.editing_request_workflow import (
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


@dataclass
class _Session:
    doc_text: str
    doc_ir: dict | None = None


class _HTTPException(Exception):
    def __init__(self, *, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _InlineOperation(str, Enum):
    CONTINUE = "continue"
    IMPROVE = "improve"
    CHANGE_TONE = "change_tone"


class _ToneStyle(str, Enum):
    PROFESSIONAL = "professional"
    CASUAL = "casual"


@dataclass
class _InlineContext:
    selected_text: str
    before_text: str
    after_text: str
    document_title: str
    section_title: str | None = None
    document_type: str | None = None
    pretrimmed: bool = False


@dataclass
class _InlineResult:
    success: bool
    generated_text: str
    operation: _InlineOperation
    error: str | None = None


def test_inline_ai_workflow_builds_pretrimmed_context() -> None:
    captured: dict[str, object] = {}

    class _FakeEngine:
        async def execute_operation(self, operation, context, **kwargs):
            captured["operation"] = operation
            captured["context"] = context
            captured["kwargs"] = kwargs
            return _InlineResult(success=True, generated_text="better text", operation=operation)

    inline_ai_module = SimpleNamespace(
        InlineAIEngine=_FakeEngine,
        InlineOperation=_InlineOperation,
        InlineContext=_InlineContext,
        ToneStyle=_ToneStyle,
    )

    class _FakeApp:
        HTTPException = _HTTPException

    out = asyncio.run(
        run_inline_ai_workflow(
            request=InlineAIRequest(
                app_v2=_FakeApp(),
                session=_Session(doc_text=""),
                data={
                    "operation": "change_tone",
                    "selected_text": "old",
                    "before_text": "before raw",
                    "after_text": "after raw",
                    "target_tone": "casual",
                    "document_title": "Doc",
                },
                normalize_inline_context_policy_fn=lambda _raw: {"version": "test_v1"},
                trim_inline_context_fn=lambda **_kwargs: ("before kept", "after kept", {"policy_version": "test_v1"}),
                inline_ai_module=inline_ai_module,
            )
        )
    )

    assert out == {
        "ok": 1,
        "generated_text": "better text",
        "operation": "change_tone",
        "context_meta": {"policy_version": "test_v1"},
    }
    context = captured["context"]
    assert isinstance(context, _InlineContext)
    assert context.before_text == "before kept"
    assert context.after_text == "after kept"
    assert context.pretrimmed is True
    assert captured["kwargs"] == {"target_tone": _ToneStyle.CASUAL}


def test_inline_ai_stream_workflow_emits_context_meta_then_events() -> None:
    class _FakeEngine:
        async def execute_operation_stream(self, operation, context, **kwargs):
            _ = operation, context, kwargs
            yield {"type": "start", "operation": "improve"}
            yield {"type": "delta", "content": "piece", "accumulated": "piece"}

    inline_ai_module = SimpleNamespace(
        InlineAIEngine=_FakeEngine,
        InlineOperation=_InlineOperation,
        InlineContext=_InlineContext,
        ToneStyle=_ToneStyle,
    )

    class _Logger:
        def error(self, *_args, **_kwargs):
            return None

    class _FakeApp:
        HTTPException = _HTTPException
        json = json
        logger = _Logger()

    response = asyncio.run(
        run_inline_ai_stream_workflow(
            request=InlineAIRequest(
                app_v2=_FakeApp(),
                session=_Session(doc_text=""),
                data={"operation": "improve", "selected_text": "old", "focus": "style"},
                normalize_inline_context_policy_fn=lambda _raw: {"version": "test_v1"},
                trim_inline_context_fn=lambda **_kwargs: ("", "", {"policy_version": "test_v1"}),
                inline_ai_module=inline_ai_module,
            )
        )
    )

    async def _collect() -> list[str]:
        chunks: list[str] = []
        async for item in response.body_iterator:
            chunks.append(item.decode("utf-8") if isinstance(item, bytes) else str(item))
        return chunks

    body = "".join(asyncio.run(_collect()))
    assert "event: context_meta" in body
    assert '"policy_version": "test_v1"' in body
    assert "event: start" in body
    assert body.index("event: context_meta") < body.index("event: start")


def test_block_edit_workflow_commits_and_persists_updated_doc() -> None:
    session = _Session(doc_text="", doc_ir={"sections": [{"id": "b1", "text": "before"}]})
    commits: list[str] = []
    stored: list[_Session] = []

    class _FakeApp:
        HTTPException = _HTTPException
        store = SimpleNamespace(put=lambda value: stored.append(value))

        @staticmethod
        def doc_ir_from_dict(value):
            return dict(value)

        @staticmethod
        def doc_ir_to_dict(value):
            return dict(value)

        @staticmethod
        def doc_ir_to_text(value):
            return str(value.get("text") or value["sections"][0]["text"])

        @staticmethod
        def _auto_commit_version(_session, label):
            commits.append(label)

        @staticmethod
        async def apply_block_edit(doc_ir, block_id, instruction):
            _ = doc_ir, block_id, instruction
            return ({"sections": [{"id": "b1", "text": "after"}], "text": "after"}, {"mode": "rewrite"})

    out = asyncio.run(
        run_block_edit_workflow(
            request=BlockEditRequest(
                app_v2=_FakeApp(),
                session=session,
                data={"block_id": "b1", "instruction": "rewrite"},
            )
        )
    )

    assert out == {
        "ok": 1,
        "doc_ir": {"sections": [{"id": "b1", "text": "after"}], "text": "after"},
        "text": "after",
        "meta": {"mode": "rewrite"},
    }
    assert commits == ["auto: before update", "auto: after update"]
    assert stored == [session]


def test_block_edit_preview_workflow_returns_candidates_and_errors() -> None:
    session = _Session(doc_text="", doc_ir={"sections": [{"id": "b1", "text": "before"}]})

    class _Index:
        def __init__(self, block_by_id):
            self.block_by_id = block_by_id

    class _FakeApp:
        HTTPException = _HTTPException

        @staticmethod
        def doc_ir_from_dict(value):
            return {
                "sections": [dict(item) for item in value.get("sections", [])],
                "text": value.get("text", value.get("sections", [{}])[0].get("text", "")),
            }

        @staticmethod
        def doc_ir_to_dict(value):
            return {
                "sections": [dict(item) for item in value.get("sections", [])],
                "text": value.get("text", value.get("sections", [{}])[0].get("text", "")),
            }

        @staticmethod
        def doc_ir_to_text(value):
            return str(value.get("text") or value["sections"][0]["text"])

        @staticmethod
        def doc_ir_build_index(value):
            blocks = {item["id"]: item for item in value.get("sections", [])}
            return _Index(blocks)

        @staticmethod
        def doc_ir_render_block_text(block):
            return block.get("text", "")

        @staticmethod
        def doc_ir_diff(before, after):
            return {"before": before.get("text"), "after": after.get("text")}

        @staticmethod
        async def apply_block_edit(doc_ir, block_id, instruction):
            if instruction == "bad":
                raise RuntimeError("boom")
            next_ir = _FakeApp.doc_ir_to_dict(doc_ir)
            next_ir["sections"][0]["text"] = f"after:{instruction}"
            next_ir["text"] = f"after:{instruction}"
            return next_ir, {"instruction": instruction, "block_id": block_id}

    out = asyncio.run(
        run_block_edit_preview_workflow(
            request=BlockEditRequest(
                app_v2=_FakeApp(),
                session=session,
                data={
                    "block_id": "b1",
                    "instruction": "rewrite",
                    "variants": [
                        {"label": "Good", "instruction": "good"},
                        {"label": "Bad", "instruction": "bad"},
                    ],
                },
            )
        )
    )

    assert out["ok"] == 1
    assert out["before"] == "before"
    assert len(out["candidates"]) == 2
    assert out["candidates"][0]["selected_after"] == "after:good"
    assert out["candidates"][1]["error"] == "boom"


def test_doc_ir_ops_workflow_applies_parsed_ops() -> None:
    session = _Session(doc_text="before", doc_ir={"ops_applied": 0})
    stored: list[_Session] = []

    class _DocIROperation:
        @staticmethod
        def parse_obj(value):
            if value.get("kind") == "valid":
                return {"kind": "valid"}
            raise ValueError("skip")

    class _FakeApp:
        HTTPException = _HTTPException
        DocIROperation = _DocIROperation
        store = SimpleNamespace(put=lambda value: stored.append(value))

        @staticmethod
        def doc_ir_from_dict(value):
            return dict(value)

        @staticmethod
        def doc_ir_apply_ops(doc_ir, ops):
            next_ir = dict(doc_ir)
            next_ir["ops_applied"] = len(ops)
            return next_ir

        @staticmethod
        def doc_ir_to_dict(value):
            return dict(value)

        @staticmethod
        def doc_ir_to_text(value):
            return f"ops:{value['ops_applied']}"

    out = run_doc_ir_ops_workflow(
        request=DocIRRequest(
            app_v2=_FakeApp(),
            session=session,
            data={"ops": [{"kind": "valid"}, {"kind": "bad"}]},
        )
    )

    assert out == {"ok": 1, "doc_ir": {"ops_applied": 1}, "text": "ops:1"}
    assert stored == [session]


def test_doc_ir_diff_workflow_returns_diff() -> None:
    session = _Session(doc_text="", doc_ir={"value": "old"})

    class _FakeApp:
        HTTPException = _HTTPException

        @staticmethod
        def doc_ir_from_dict(value):
            return dict(value)

        @staticmethod
        def doc_ir_diff(before, after):
            return {"before": before["value"], "after": after["value"]}

    out = run_doc_ir_diff_workflow(
        request=DocIRRequest(
            app_v2=_FakeApp(),
            session=session,
            data={"doc_ir": {"value": "new"}},
        )
    )

    assert out == {"ok": 1, "diff": {"before": "old", "after": "new"}}


def test_render_figure_workflow_sanitizes_svg() -> None:
    class _FakeApp:
        HTTPException = _HTTPException

        @staticmethod
        def render_figure_svg(spec):
            return (f"<svg>{spec['name']}</svg>", "caption")

        @staticmethod
        def sanitize_html(svg):
            return svg.replace("<", "[").replace(">", "]")

    out = run_render_figure_workflow(
        request=RenderFigureRequest(app_v2=_FakeApp(), data={"spec": {"name": "demo"}})
    )

    assert out == {"svg": "[svg]demo[/svg]", "caption": "caption"}


def test_diagram_generate_workflow_calls_builder() -> None:
    class _FakeApp:
        HTTPException = _HTTPException

    out = run_diagram_generate_workflow(
        request=DiagramGenerateRequest(
            app_v2=_FakeApp(),
            session=_Session(doc_text=""),
            data={"prompt": "show trend", "kind": "line"},
            diagram_spec_from_prompt_fn=lambda prompt, kind: {"prompt": prompt, "kind": kind},
        )
    )

    assert out == {"ok": 1, "spec": {"prompt": "show trend", "kind": "line"}}
