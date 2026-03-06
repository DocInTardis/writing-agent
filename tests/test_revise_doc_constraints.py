from types import SimpleNamespace

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.web.services.generation_service import GenerationService


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
            long_para = "这是用于验证回退改写写回门禁的扩展段落，" * 24
            yield "intro text ignored\n"
            yield f"<revised_markdown>\n# T\n\n{long_para}\n</revised_markdown>\n"
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
    assert "验证回退改写写回门禁" in str(data.get("text") or "")
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


def test_validate_revision_candidate_reports_structured_reasons() -> None:
    base_text = (
        "# 标题\n\n"
        "## 摘要\n这是完整摘要。\n\n"
        "## 关键词\n关键词A；关键词B\n\n"
        "## 引言\n这里是引言段落。\n\n"
        "## 研究方法\n方法细节。\n\n"
        "## 参考文献\n[1] 参考文献A\n[2] 参考文献B\n"
    )
    candidate_text = "# 标题\n\n## 引言\n内容过短。"
    hard_constraints = {
        "min_chars": 120,
        "required_h2": ["摘要", "关键词", "引言", "研究方法", "参考文献"],
        "min_refs": 2,
        "min_tables": 0,
        "min_figures": 0,
        "epsilon": 1.0,
    }
    result = GenerationService.validate_revision_candidate(
        app_v2,
        candidate_text=candidate_text,
        base_text=base_text,
        hard_constraints=hard_constraints,
    )
    assert result.get("passed") is False
    reasons = " | ".join(result.get("reasons") or [])
    assert "required_h2_coverage_insufficient" in reasons
    assert "refs_below_min" in reasons
    assert float(result.get("score_delta") or 0.0) < 0


def test_revise_doc_unscoped_fallback_rejects_candidate_below_hard_gate(monkeypatch):
    session = _prepare_session(
        "# 标题\n\n## 摘要\n原始摘要内容较完整。\n\n## 引言\n原始引言内容较完整。\n\n## 参考文献\n[1] A\n[2] B\n"
    )
    session.template_required_h2 = ["摘要", "引言", "参考文献"]
    session.generation_prefs = {
        "min_reference_count": 2,
        "revision_quality_epsilon": 1.0,
    }
    app_v2.store.put(session)

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat_stream(self, **kwargs):
            _ = kwargs
            yield "<revised_markdown>\n# 标题\n\n## 引言\n过短。\n</revised_markdown>"

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
    assert data.get("applied") is False
    assert str(data.get("text") or "").strip() == str(session.doc_text or "").strip()
    meta = data.get("revision_meta") or {}
    assert str(meta.get("error_code") or "") == "E_REVISION_HARD_GATE_REJECTED"
    assert isinstance(meta.get("validation"), dict)
