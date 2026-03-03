from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _prepare_session(text: str):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, text)
    app_v2.store.put(session)
    return session


def test_generate_includes_revision_meta_when_selected_revision_fails(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")

    monkeypatch.setattr(app_v2, "_try_handle_format_only_request", lambda **_kwargs: None)
    monkeypatch.setattr(app_v2, "_try_quick_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app_v2, "_try_ai_intent_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_should_route_to_revision", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(app_v2, "_ensure_ollama_ready", lambda: (True, ""))
    monkeypatch.setattr(app_v2, "_should_use_fast_generate", lambda *_args, **_kwargs: False)

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
        _ = session, instruction, text, selection, analysis, context_policy
        if callable(report_status):
            report_status(
                {
                    "ok": False,
                    "error_code": "E_SCHEMA_INVALID",
                    "policy_version": "dynamic_v1",
                    "fallback_triggered": True,
                    "fallback_recovered": False,
                }
            )
        return None

    monkeypatch.setattr(app_v2, "_try_revision_edit", _fake_revision_edit)

    def _fake_graph(**_kwargs):
        yield {"event": "final", "text": "# T\n\nnew sentence with enough length", "problems": []}

    monkeypatch.setattr(app_v2, "run_generate_graph", _fake_graph)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        headers={"x-idempotency-key": f"test-revision-meta-{session.id}"},
        json={
            "instruction": "rewrite selected text",
            "text": session.doc_text,
            "selection": {"start": 5, "end": 8, "text": "old"},
            "context_policy": {"version": "dynamic_v1"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert str(data.get("text") or "").strip()
    meta = data.get("revision_meta") or {}
    assert meta.get("error_code") == "E_SCHEMA_INVALID"
    assert meta.get("policy_version") == "dynamic_v1"
    assert meta.get("fallback_triggered") is True
    assert meta.get("fallback_recovered") is False


def test_generate_stream_emits_revision_status_event(monkeypatch):
    session = _prepare_session("# T\n\nold sentence")

    monkeypatch.setattr(app_v2, "_try_handle_format_only_request", lambda **_kwargs: None)
    monkeypatch.setattr(app_v2, "_ensure_ollama_ready_iter", lambda: (True, ""))
    monkeypatch.setattr(app_v2, "_try_quick_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app_v2, "_try_ai_intent_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_should_route_to_revision", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(app_v2, "_should_use_fast_generate", lambda *_args, **_kwargs: True)

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
        _ = session, instruction, text, selection, analysis, context_policy
        if callable(report_status):
            report_status(
                {
                    "ok": False,
                    "error_code": "E_SCHEMA_INVALID",
                    "policy_version": "dynamic_v1",
                    "fallback_triggered": True,
                    "fallback_recovered": False,
                }
            )
        return None

    monkeypatch.setattr(app_v2, "_try_revision_edit", _fake_revision_edit)

    def _fake_single_pass_generate_stream(*_args, **_kwargs):
        yield {"event": "result", "text": "# T\n\nnew sentence"}

    monkeypatch.setattr(app_v2, "_single_pass_generate_stream", _fake_single_pass_generate_stream)

    client = TestClient(app_v2.app)
    with client.stream(
        "POST",
        f"/api/doc/{session.id}/generate/stream",
        headers={"x-idempotency-key": f"test-revision-stream-{session.id}"},
        json={
            "instruction": "rewrite selected text",
            "text": session.doc_text,
            "selection": {"start": 5, "end": 8, "text": "old"},
            "context_policy": {"version": "dynamic_v1"},
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    assert resp.status_code == 200
    assert "event: revision_status" in body
    assert "E_SCHEMA_INVALID" in body
    assert "event: final" in body
