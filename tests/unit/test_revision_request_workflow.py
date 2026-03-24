from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from writing_agent.workflows.revision_request_workflow import RevisionRequest, run_revision_workflow


@dataclass
class _Session:
    doc_text: str
    doc_ir: dict | None = None


def test_revision_workflow_returns_selected_revision_when_available() -> None:
    session = _Session(doc_text="# T\n\nold sentence")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

    class _FakeApp:
        HTTPException = RuntimeError

        class os:
            environ = {}

        OllamaClient = _FakeClient
        store = SimpleNamespace(put=lambda _session: None)

        @staticmethod
        def get_ollama_settings():
            return SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0)

        @staticmethod
        def _run_message_analysis(*_args, **_kwargs):
            return {"rewritten_query": "rewrite now"}

        @staticmethod
        def _revision_hard_constraints(*_args, **_kwargs):
            return {}

        @staticmethod
        def _revision_decision_with_model(**_kwargs):
            return {"should_apply": True, "plan": []}

        @staticmethod
        def _try_revision_edit(**_kwargs):
            return ("# T\n\nnew sentence", "selected revision")

        @staticmethod
        def _replace_question_headings(text):
            return text

        @staticmethod
        def _postprocess_output_text(_session, text, _instruction, **_kwargs):
            return text

        @staticmethod
        def _set_doc_text(_session, text):
            session.doc_text = text

    out = run_revision_workflow(
        request=RevisionRequest(
            app_v2=_FakeApp(),
            session=session,
            data={"instruction": "please revise", "text": session.doc_text, "selection": {"text": "old sentence"}},
            fallback_normalize_heading_text_fn=lambda value: str(value),
            resolve_target_section_selection_fn=lambda **_kwargs: None,
            build_revision_fallback_prompt_fn=lambda **_kwargs: ("", ""),
            extract_revision_fallback_text_fn=lambda raw: str(raw),
            validate_revision_candidate_fn=lambda *_args, **_kwargs: {"passed": True, "reasons": [], "score_delta": 0.0},
        )
    )

    assert out.get("ok") == 1
    assert out.get("note") == "selected revision"
    assert "new sentence" in str(out.get("text") or "")


def test_revision_workflow_hard_gate_reject_keeps_base_text() -> None:
    session = _Session(doc_text="# T\n\nold sentence")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat_stream(self, **_kwargs):
            yield "<revised_markdown>\n# T\n\nshort\n</revised_markdown>"

    class _FakeApp:
        HTTPException = RuntimeError

        class os:
            environ = {}

        OllamaClient = _FakeClient
        store = SimpleNamespace(put=lambda _session: None)

        @staticmethod
        def get_ollama_settings():
            return SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0)

        @staticmethod
        def _run_message_analysis(*_args, **_kwargs):
            return {"rewritten_query": "rewrite now"}

        @staticmethod
        def _revision_hard_constraints(*_args, **_kwargs):
            return {}

        @staticmethod
        def _revision_decision_with_model(**_kwargs):
            return {"should_apply": True, "plan": []}

        @staticmethod
        def _sanitize_output_text(text):
            return text

        @staticmethod
        def _looks_like_prompt_echo(*_args, **_kwargs):
            return False

        @staticmethod
        def _replace_question_headings(text):
            return text

        @staticmethod
        def _postprocess_output_text(_session, text, _instruction, **_kwargs):
            return text

        @staticmethod
        def _safe_doc_ir_payload(text):
            return {"text": text}

        @staticmethod
        def _set_doc_text(_session, text):
            session.doc_text = text

    out = run_revision_workflow(
        request=RevisionRequest(
            app_v2=_FakeApp(),
            session=session,
            data={"instruction": "please revise", "text": session.doc_text, "allow_unscoped_fallback": True},
            fallback_normalize_heading_text_fn=lambda value: str(value),
            resolve_target_section_selection_fn=lambda **_kwargs: None,
            build_revision_fallback_prompt_fn=lambda **_kwargs: ("system", "user"),
            extract_revision_fallback_text_fn=lambda raw: str(raw).replace("<revised_markdown>", "").replace("</revised_markdown>", "").strip(),
            validate_revision_candidate_fn=lambda *_args, **_kwargs: {"passed": False, "reasons": ["too_short"], "score_delta": -1.0},
        )
    )

    assert out.get("applied") is False
    assert str(out.get("text") or "") == session.doc_text
    meta = out.get("revision_meta") or {}
    assert meta.get("error_code") == "E_REVISION_HARD_GATE_REJECTED"
