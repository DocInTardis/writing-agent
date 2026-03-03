from types import SimpleNamespace

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _prepare_session(text: str):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, text)
    app_v2.store.put(session)
    return session


class _DummyClient:
    def __init__(self, *args, **kwargs):
        _ = args, kwargs

    def is_running(self) -> bool:
        return True

    def chat_stream(self, **kwargs):
        _ = kwargs
        if False:
            yield ""


def test_revise_doc_uses_constrained_selected_revision(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        app_v2,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0),
    )
    monkeypatch.setattr(app_v2, "OllamaClient", _DummyClient)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app_v2, "_revision_decision_with_model", lambda **_kwargs: {"should_apply": True, "plan": []})
    monkeypatch.setattr(app_v2, "_replace_question_headings", lambda text: text)
    monkeypatch.setattr(
        app_v2,
        "_postprocess_output_text",
        lambda _session, text, _instruction, **_kwargs: text,
    )

    def _fake_try_revision_edit(
        *,
        session,
        instruction,
        text,
        selection="",
        analysis=None,
        context_policy=None,
        report_status=None,
    ):
        _ = session, instruction, analysis
        captured["selection"] = selection
        captured["context_policy"] = context_policy
        if callable(report_status):
            report_status({"ok": True, "error_code": "", "policy_version": "dynamic_v1"})
        return (str(text).replace("old", "new"), "selected revise ok")

    monkeypatch.setattr(app_v2, "_try_revision_edit", _fake_try_revision_edit)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/revise",
        json={
            "instruction": "rewrite selected text",
            "text": session.doc_text,
            "selection": {"start": 5, "end": 8, "text": "old"},
            "context_policy": {"version": "dynamic_v1", "window_min_chars": 200},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "new sentence" in str(data.get("text") or "")
    assert str(data.get("note") or "") == "selected revise ok"
    assert isinstance(captured.get("selection"), dict)
    assert captured.get("selection") == {"start": 5, "end": 8, "text": "old"}
    assert isinstance(captured.get("context_policy"), dict)
    assert str((captured.get("context_policy") or {}).get("version")) == "dynamic_v1"
    meta = data.get("revision_meta") or {}
    assert meta.get("ok") is True


def test_revise_doc_does_not_fallback_to_unscoped_rewrite_by_default(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")

    monkeypatch.setattr(
        app_v2,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0),
    )
    monkeypatch.setattr(app_v2, "OllamaClient", _DummyClient)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app_v2, "_revision_decision_with_model", lambda **_kwargs: {"should_apply": True, "plan": []})

    def _fake_try_revision_edit(
        *,
        session,
        instruction,
        text,
        selection="",
        analysis=None,
        context_policy=None,
        report_status=None,
    ):
        _ = session, instruction, text, selection, analysis, context_policy
        if callable(report_status):
            report_status({"ok": False, "error_code": "E_SCHEMA_INVALID"})
        return None

    monkeypatch.setattr(app_v2, "_try_revision_edit", _fake_try_revision_edit)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/revise",
        json={
            "instruction": "rewrite selected text",
            "text": session.doc_text,
            "selection": {"start": 5, "end": 8, "text": "old"},
            "context_policy": {"version": "dynamic_v1"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("applied") is False
    assert "old sentence" in str(data.get("text") or "")
    meta = data.get("revision_meta") or {}
    assert meta.get("ok") is False
    assert str(meta.get("error_code") or "") == "E_SCHEMA_INVALID"


def test_revise_doc_unscoped_fallback_uses_tagged_prompt_and_extracts_revised_block(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat_stream(self, **kwargs):
            captured["system"] = str(kwargs.get("system") or "")
            captured["user"] = str(kwargs.get("user") or "")
            yield "intro text ignored\n"
            yield "<revised_markdown>\n# T\n\nnew sentence\n</revised_markdown>\n"
            yield "tail ignored"

    monkeypatch.setattr(
        app_v2,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0),
    )
    monkeypatch.setattr(app_v2, "OllamaClient", _FakeClient)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {"rewritten_query": "rewrite now"})
    monkeypatch.setattr(app_v2, "_revision_decision_with_model", lambda **_kwargs: {"should_apply": True, "plan": ["fix wording"]})
    monkeypatch.setattr(app_v2, "_replace_question_headings", lambda text: text)
    monkeypatch.setattr(
        app_v2,
        "_postprocess_output_text",
        lambda _session, text, _instruction, **_kwargs: text,
    )

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/revise",
        json={
            "instruction": "please revise",
            "text": session.doc_text,
            "allow_unscoped_fallback": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "new sentence" in str(data.get("text") or "")
    assert "<revised_markdown>" not in str(data.get("text") or "")

    user_prompt = captured.get("user") or ""
    assert "<revision_request>" in user_prompt
    assert "<execution_plan>" in user_prompt
    assert "<original_document>" in user_prompt


def test_revise_doc_unscoped_fallback_prompt_echo_fails_closed(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat_stream(self, **kwargs):
            _ = kwargs
            yield "You are a document revision assistant.\nRevision request:\nrewrite now\n"

    monkeypatch.setattr(
        app_v2,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0),
    )
    monkeypatch.setattr(app_v2, "OllamaClient", _FakeClient)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {"rewritten_query": "rewrite now"})
    monkeypatch.setattr(app_v2, "_revision_decision_with_model", lambda **_kwargs: {"should_apply": True, "plan": []})
    monkeypatch.setattr(app_v2, "_replace_question_headings", lambda text: text)
    monkeypatch.setattr(
        app_v2,
        "_postprocess_output_text",
        lambda _session, text, _instruction, **_kwargs: text,
    )

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/revise",
        json={
            "instruction": "please revise",
            "text": session.doc_text,
            "allow_unscoped_fallback": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "old sentence" in str(data.get("text") or "")
