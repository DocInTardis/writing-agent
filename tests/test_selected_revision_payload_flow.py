from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _prepare_session(text: str):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, text)
    app_v2.store.put(session)
    return session


def test_generate_passes_selection_object_and_context_policy(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")
    captured: dict[str, object] = {}

    monkeypatch.setattr(app_v2, "_try_handle_format_only_request", lambda **_kwargs: None)
    monkeypatch.setattr(app_v2, "_try_quick_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app_v2, "_try_ai_intent_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_should_route_to_revision", lambda *_args, **_kwargs: True)

    def _fake_revision_edit(
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
        return (str(text).replace("old", "new"), "ok")

    monkeypatch.setattr(app_v2, "_try_revision_edit", _fake_revision_edit)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/generate",
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
    assert isinstance(captured.get("selection"), dict)
    assert captured.get("selection") == {"start": 5, "end": 8, "text": "old"}
    assert isinstance(captured.get("context_policy"), dict)
    assert str((captured.get("context_policy") or {}).get("version")) == "dynamic_v1"


def test_generate_stream_passes_selection_object_and_context_policy(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")
    captured: dict[str, object] = {}

    monkeypatch.setattr(app_v2, "_try_handle_format_only_request", lambda **_kwargs: None)
    monkeypatch.setattr(app_v2, "_ensure_ollama_ready_iter", lambda: (True, ""))
    monkeypatch.setattr(app_v2, "_try_quick_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app_v2, "_try_ai_intent_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_should_route_to_revision", lambda *_args, **_kwargs: True)

    def _fake_revision_edit(
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
        return (str(text).replace("old", "new"), "ok")

    monkeypatch.setattr(app_v2, "_try_revision_edit", _fake_revision_edit)

    client = TestClient(app_v2.app)
    with client.stream(
        "POST",
        f"/api/doc/{session.id}/generate/stream",
        json={
            "instruction": "rewrite selected text",
            "text": session.doc_text,
            "selection": {"start": 5, "end": 8, "text": "old"},
            "context_policy": {"version": "dynamic_v1", "window_min_chars": 200},
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    assert resp.status_code == 200
    assert "event: final" in body
    assert isinstance(captured.get("selection"), dict)
    assert captured.get("selection") == {"start": 5, "end": 8, "text": "old"}
    assert isinstance(captured.get("context_policy"), dict)
    assert str((captured.get("context_policy") or {}).get("version")) == "dynamic_v1"
