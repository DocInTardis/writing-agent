from types import SimpleNamespace

from fastapi.testclient import TestClient

import writing_agent.v2.inline_ai as inline_ai
import writing_agent.web.app_v2 as app_v2


def _prepare_session(text: str):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, text)
    app_v2.store.put(session)
    return session


def test_inline_ai_passes_question_for_ask_ai(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")
    captured: dict[str, object] = {}

    class _FakeEngine:
        async def execute_operation(self, operation, context, **kwargs):
            _ = context
            captured["operation"] = operation.value
            captured["kwargs"] = kwargs
            return SimpleNamespace(success=True, generated_text="ok", operation=operation, error=None)

    monkeypatch.setattr(inline_ai, "InlineAIEngine", _FakeEngine)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/inline-ai",
        json={
            "operation": "ask_ai",
            "selected_text": "x",
            "question": "what?",
        },
    )
    assert resp.status_code == 200
    assert captured.get("operation") == "ask_ai"
    assert (captured.get("kwargs") or {}).get("question") == "what?"


def test_inline_ai_passes_target_language_for_translate(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")
    captured: dict[str, object] = {}

    class _FakeEngine:
        async def execute_operation(self, operation, context, **kwargs):
            _ = context
            captured["operation"] = operation.value
            captured["kwargs"] = kwargs
            return SimpleNamespace(success=True, generated_text="ok", operation=operation, error=None)

    monkeypatch.setattr(inline_ai, "InlineAIEngine", _FakeEngine)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/inline-ai",
        json={
            "operation": "translate",
            "selected_text": "x",
            "target_language": "ja",
        },
    )
    assert resp.status_code == 200
    assert captured.get("operation") == "translate"
    assert (captured.get("kwargs") or {}).get("target_language") == "ja"
