from types import SimpleNamespace

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.web.app_v2 import _extract_format_only_updates, _should_route_to_revision, _try_format_only_update


def test_extract_format_only_updates_font_and_spacing():
    instruction = "\u628a\u5168\u6587\u5b57\u4f53\u6539\u6210\u5b8b\u4f53\uff0c\u5b57\u53f7\u5c0f\u56db\uff0c\u884c\u8ddd1.5\u500d"
    parsed = _extract_format_only_updates(instruction)
    assert parsed is not None
    fmt = parsed["formatting"]
    assert fmt.get("font_name_east_asia") == "\u5b8b\u4f53"
    assert fmt.get("font_size_pt") == 12
    assert fmt.get("line_spacing") == 1.5


def test_should_not_route_to_revision_for_format_only_instruction():
    text = "# T\n\n## \u5f15\u8a00\n\u6b63\u6587"
    instruction = "\u5b57\u4f53\u6539\u6210\u5b8b\u4f53\uff0c\u5b57\u53f7\u5c0f\u56db"
    assert _should_route_to_revision(instruction, text) is False


def test_should_route_to_revision_for_rewrite_instruction():
    text = "# T\n\n## \u5f15\u8a00\n\u8fd9\u662f\u539f\u6587\u5185\u5bb9\u3002"
    instruction = "\u8bf7\u628a\u5168\u6587\u91cd\u5199\u5f97\u66f4\u5b66\u672f\u4e00\u4e9b"
    assert _should_route_to_revision(instruction, text) is True


def test_try_format_only_update_changes_session_without_rewrite():
    session = SimpleNamespace(formatting={}, generation_prefs={})
    instruction = "\u628a\u5168\u6587\u5b57\u4f53\u6539\u6210\u9ed1\u4f53\uff0c\u5b57\u53f7\u5c0f\u56db\uff0c\u884c\u8ddd1.5\u500d"
    note = _try_format_only_update(session, instruction)
    assert note and "\u6b63\u6587\u4fdd\u6301\u4e0d\u53d8" in note
    assert session.formatting.get("font_name_east_asia") == "\u9ed1\u4f53"
    assert session.formatting.get("font_size_pt") == 12
    assert session.formatting.get("line_spacing") == 1.5


def test_generate_format_only_bypasses_model_ready(monkeypatch):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# T\n\n## A\n\u6b63\u6587\u5185\u5bb9")
    app_v2.store.put(session)

    def _fail_ready():
        raise AssertionError("should not call _ensure_ollama_ready for format-only request")

    monkeypatch.setattr(app_v2, "_ensure_ollama_ready", _fail_ready)
    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        json={
            "instruction": "\u5b57\u4f53\u6539\u6210\u5b8b\u4f53\uff0c\u5b57\u53f7\u5c0f\u56db\uff0c\u884c\u8ddd1.5\u500d",
            "text": session.doc_text,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == session.doc_text
    assert data.get("formatting", {}).get("font_name_east_asia") == "\u5b8b\u4f53"


def test_generate_stream_format_only_bypasses_model_ready(monkeypatch):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# T\n\n## A\n\u6b63\u6587\u5185\u5bb9")
    app_v2.store.put(session)

    def _fail_ready_iter():
        raise AssertionError("should not call _ensure_ollama_ready_iter for format-only request")

    monkeypatch.setattr(app_v2, "_ensure_ollama_ready_iter", _fail_ready_iter)
    client = TestClient(app_v2.app)
    with client.stream(
        "POST",
        f"/api/doc/{session.id}/generate/stream",
        json={
            "instruction": "\u5b57\u4f53\u6539\u6210\u9ed1\u4f53\uff0c\u5b57\u53f7\u5c0f\u56db",
            "text": session.doc_text,
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    assert resp.status_code == 200
    assert "event: final" in body
    assert "model preparing" not in body


def test_generate_rejects_when_stream_generation_busy():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# T\n\n## A\n正文内容")
    app_v2.store.put(session)

    token = app_v2._try_begin_doc_generation(session.id, mode="stream")
    assert token
    client = TestClient(app_v2.app)
    try:
        resp = client.post(
            f"/api/doc/{session.id}/generate",
            json={"instruction": "请继续补充内容", "text": session.doc_text},
        )
        assert resp.status_code == 409
    finally:
        app_v2._finish_doc_generation(session.id, token)


def test_generate_stream_rejects_when_stream_generation_busy():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# T\n\n## A\n正文内容")
    app_v2.store.put(session)

    token = app_v2._try_begin_doc_generation(session.id, mode="stream")
    assert token
    client = TestClient(app_v2.app)
    try:
        with client.stream(
            "POST",
            f"/api/doc/{session.id}/generate/stream",
            json={"instruction": "请继续补充内容", "text": session.doc_text},
        ) as resp:
            _ = resp.read().decode("utf-8", errors="ignore")
        assert resp.status_code == 409
    finally:
        app_v2._finish_doc_generation(session.id, token)


def test_stream_section_token_helpers():
    assert app_v2._decode_section_title_for_stream("H2::关键技术") == "关键技术"
    assert app_v2._normalize_section_key_for_stream("H3::关键 技术") == "关键技术"


def test_generate_format_only_releases_lock_after_return():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# T\n\n## A\n正文内容")
    app_v2.store.put(session)
    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        json={
            "instruction": "字体改成宋体，字号小四",
            "text": session.doc_text,
        },
    )
    assert resp.status_code == 200
    assert app_v2._is_doc_generation_busy(session.id) is False


def test_generate_overwrite_mode_uses_empty_generation_context(monkeypatch):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Title\n\n## A\nold content")
    app_v2.store.put(session)

    seen: dict[str, str] = {}

    monkeypatch.setattr(app_v2, "_ensure_ollama_ready", lambda: (True, ""))
    monkeypatch.setattr(app_v2, "_try_quick_edit", lambda *_: None)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app_v2, "_try_ai_intent_edit", lambda *_: None)
    monkeypatch.setattr(app_v2, "_should_route_to_revision", lambda *_: False)
    monkeypatch.setattr(app_v2, "_should_use_fast_generate", lambda *_: False)

    def _fake_graph(**kwargs):
        seen["current_text"] = str(kwargs.get("current_text") or "")
        yield {"event": "final", "text": "# New\n\n## A\nfresh content", "problems": []}

    monkeypatch.setattr(app_v2, "run_generate_graph", _fake_graph)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        json={
            "instruction": "please rewrite this document",
            "text": session.doc_text,
            "compose_mode": "overwrite",
        },
    )
    assert resp.status_code == 200
    assert seen.get("current_text") == ""


def test_generate_uses_session_text_when_request_text_is_empty(monkeypatch):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Title\n\n## A\nsession text")
    original_text = session.doc_text
    app_v2.store.put(session)

    seen: dict[str, str] = {}

    monkeypatch.setattr(app_v2, "_ensure_ollama_ready", lambda: (True, ""))
    monkeypatch.setattr(app_v2, "_try_quick_edit", lambda *_: None)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app_v2, "_try_ai_intent_edit", lambda *_: None)
    monkeypatch.setattr(app_v2, "_should_route_to_revision", lambda *_: False)
    monkeypatch.setattr(app_v2, "_should_use_fast_generate", lambda *_: False)

    def _fake_graph(**kwargs):
        seen["current_text"] = str(kwargs.get("current_text") or "")
        yield {"event": "final", "text": "# Kept\n\n## A\nok", "problems": []}

    monkeypatch.setattr(app_v2, "run_generate_graph", _fake_graph)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        json={
            "instruction": "continue",
            "text": "",
        },
    )
    assert resp.status_code == 200
    assert seen.get("current_text") == original_text


def test_generate_section_uses_doc_text_fields(monkeypatch):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Title\n\n## A\nbase")
    app_v2.store.put(session)

    seen: dict[str, str] = {}

    def _fake_graph(**kwargs):
        seen["current_text"] = str(kwargs.get("current_text") or "")
        yield {"event": "final", "text": "# Title\n\n## A\nsection rewrite"}

    monkeypatch.setattr(app_v2, "run_generate_graph", _fake_graph)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/generate/section",
        json={"section": "A", "instruction": "rewrite section A"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") == 1
    assert isinstance(body.get("doc_ir"), dict)
    assert seen.get("current_text") == "# Title\n\n## A\nbase"


def test_export_html_escapes_dangerous_text():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Title\n\n## Intro\n<script>alert(1)</script>")
    app_v2.store.put(session)

    client = TestClient(app_v2.app)
    resp = client.get(f"/export/{session.id}/html")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8", errors="ignore")
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
