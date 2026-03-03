from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
import writing_agent.v2.inline_ai as inline_ai


def _prepare_session(text: str):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, text)
    app_v2.store.put(session)
    return session


def test_inline_ai_stream_emits_context_meta_before_tokens(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")

    class _FakeEngine:
        async def execute_operation_stream(self, operation, context, **kwargs):
            _ = context, kwargs
            yield {"type": "start", "operation": operation.value}
            yield {"type": "delta", "content": "piece", "accumulated": "piece"}
            yield {"type": "done", "content": "piece", "operation": operation.value}

    monkeypatch.setattr(inline_ai, "InlineAIEngine", _FakeEngine)

    client = TestClient(app_v2.app)
    with client.stream(
        "POST",
        f"/api/doc/{session.id}/inline-ai/stream",
        json={
            "operation": "improve",
            "selected_text": "old",
            "before_text": "A" * 500,
            "after_text": "B" * 500,
            "focus": "style",
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")

    assert resp.status_code == 200
    assert "event: context_meta" in body
    assert '"policy_version": "dynamic_v1"' in body
    assert "event: start" in body
    assert body.index("event: context_meta") < body.index("event: start")
