import json

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _client() -> TestClient:
    return TestClient(app_v2.app)


def _prepare_session():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Title\n\n## Intro\nold content")
    app_v2.store.put(session)
    return session


def _read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _patch_generate_common(monkeypatch):
    monkeypatch.setattr(app_v2, "_ensure_ollama_ready", lambda: (True, ""))
    monkeypatch.setattr(app_v2, "_try_quick_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app_v2, "_try_ai_intent_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_should_route_to_revision", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(app_v2, "_should_use_fast_generate", lambda *_args, **_kwargs: False)


class _QuickEditStub:
    def __init__(self, text: str, note: str = "quick edit") -> None:
        self.text = text
        self.note = note
        self.requires_confirmation = False
        self.confirmation_reason = ""
        self.risk_level = "low"
        self.source = "rules"
        self.operations_count = 1


def test_generate_uses_route_graph_when_enabled(monkeypatch):
    session = _prepare_session()
    _patch_generate_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "1")

    seen: dict[str, object] = {}

    def _dual(**kwargs):
        seen.update(kwargs)
        return {
            "ok": 1,
            "text": "# Title\n\n## Intro\nroute graph text",
            "problems": [],
            "trace_id": "t-route-generate",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
        }

    def _legacy(**_kwargs):
        raise AssertionError("legacy graph should not be called when route graph is enabled")
        yield {}  # pragma: no cover

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(app_v2, "run_generate_graph", _legacy)

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        json={
            "instruction": "continue writing intro",
            "text": session.doc_text,
            "compose_mode": "continue",
            "resume_sections": ["Intro"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") == 1
    assert seen
    assert seen.get("compose_mode") == "continue"
    assert seen.get("resume_sections") == ["Intro"]
    graph_meta = body.get("graph_meta") or {}
    assert graph_meta.get("path") == "route_graph"
    assert graph_meta.get("route_id") == "resume_sections"
    assert graph_meta.get("route_entry") == "writer"
    assert graph_meta.get("engine") == "native"


def test_generate_keeps_legacy_graph_when_route_graph_disabled(monkeypatch):
    session = _prepare_session()
    _patch_generate_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "0")

    def _dual(**_kwargs):
        raise AssertionError("route graph should not be called when disabled")

    legacy_called = {"v": False}

    def _legacy(**_kwargs):
        legacy_called["v"] = True
        yield {"event": "final", "text": "# Title\n\n## Intro\nlegacy graph text", "problems": []}

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(app_v2, "run_generate_graph", _legacy)

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        json={
            "instruction": "continue writing intro",
            "text": session.doc_text,
            "compose_mode": "continue",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") == 1
    assert legacy_called["v"] is True
    assert "graph_meta" not in body


def test_generate_route_graph_enabled_but_quick_edit_shortcut_has_no_graph_meta(monkeypatch):
    session = _prepare_session()
    _patch_generate_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "1")

    def _dual(**_kwargs):
        raise AssertionError("route graph should not run when quick-edit shortcut is used")

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(
        app_v2,
        "_try_quick_edit",
        lambda *_args, **_kwargs: _QuickEditStub("# Title\n\n## Intro\nquick edited"),
    )

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        json={
            "instruction": "polish wording",
            "text": session.doc_text,
            "compose_mode": "continue",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") == 1
    assert "quick edited" in str(body.get("text") or "")
    assert "graph_meta" not in body


def test_generate_route_graph_falls_back_to_single_pass_when_dual_raises(monkeypatch):
    session = _prepare_session()
    _patch_generate_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "1")

    seen = {"dual": False, "single": False}

    def _dual(**_kwargs):
        seen["dual"] = True
        raise RuntimeError("dual graph failed")

    def _legacy(**_kwargs):
        raise AssertionError("legacy graph should not be called when route graph is enabled")
        yield {}  # pragma: no cover

    def _single_pass_generate(*_args, **_kwargs):
        seen["single"] = True
        return "# Title\n\n## Intro\nsingle pass fallback text with enough length"

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(app_v2, "run_generate_graph", _legacy)
    monkeypatch.setattr(app_v2, "_single_pass_generate", _single_pass_generate)

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        json={
            "instruction": "continue writing intro",
            "text": session.doc_text,
            "compose_mode": "continue",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") == 1
    assert str(body.get("text") or "").strip()
    assert seen["dual"] is True
    assert seen["single"] is True
    assert "graph_meta" not in body


def test_generate_stream_uses_route_graph_when_enabled(monkeypatch):
    session = _prepare_session()
    _patch_generate_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "1")
    monkeypatch.setattr(app_v2, "_ensure_ollama_ready_iter", lambda: (True, ""))

    seen: dict[str, object] = {}

    def _dual(**kwargs):
        seen.update(kwargs)
        return {
            "ok": 1,
            "text": "# Title\n\n## Intro\nroute graph stream text",
            "problems": [],
            "trace_id": "t-route-stream",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
        }

    def _legacy(**_kwargs):
        raise AssertionError("legacy graph should not be called when route graph is enabled")
        yield {}  # pragma: no cover

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(app_v2, "run_generate_graph", _legacy)

    client = _client()
    with client.stream(
        "POST",
        f"/api/doc/{session.id}/generate/stream",
        json={
            "instruction": "continue writing intro",
            "text": session.doc_text,
            "compose_mode": "continue",
            "resume_sections": ["Intro"],
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")

    assert resp.status_code == 200
    assert "event: final" in body
    assert '"graph_meta"' in body
    assert '"route_id": "resume_sections"' in body
    assert seen
    assert seen.get("compose_mode") == "continue"
    assert seen.get("resume_sections") == ["Intro"]


def test_generate_stream_keeps_legacy_graph_when_route_graph_disabled(monkeypatch):
    session = _prepare_session()
    _patch_generate_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "0")
    monkeypatch.setattr(app_v2, "_ensure_ollama_ready_iter", lambda: (True, ""))

    def _dual(**_kwargs):
        raise AssertionError("route graph should not be called when disabled")

    legacy_called = {"v": False}

    def _legacy(**_kwargs):
        legacy_called["v"] = True
        yield {"event": "final", "text": "# Title\n\n## Intro\nlegacy stream text", "problems": []}

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(app_v2, "run_generate_graph", _legacy)

    client = _client()
    with client.stream(
        "POST",
        f"/api/doc/{session.id}/generate/stream",
        json={
            "instruction": "continue writing intro",
            "text": session.doc_text,
            "compose_mode": "continue",
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")

    assert resp.status_code == 200
    assert "event: final" in body
    assert legacy_called["v"] is True
    assert '"graph_meta"' not in body


def test_generate_stream_route_graph_falls_back_when_dual_raises(monkeypatch):
    session = _prepare_session()
    _patch_generate_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "1")
    monkeypatch.setattr(app_v2, "_ensure_ollama_ready_iter", lambda: (True, ""))

    seen = {"dual": False, "single": False}

    def _dual(**_kwargs):
        seen["dual"] = True
        raise RuntimeError("dual graph stream failed")

    def _legacy(**_kwargs):
        raise AssertionError("legacy graph should not be called when route graph is enabled")
        yield {}  # pragma: no cover

    def _single_pass_generate_stream(*_args, **_kwargs):
        seen["single"] = True
        yield {"event": "result", "text": "# Title\n\n## Intro\nstream single-pass fallback text"}

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(app_v2, "run_generate_graph", _legacy)
    monkeypatch.setattr(app_v2, "_single_pass_generate_stream", _single_pass_generate_stream)

    client = _client()
    with client.stream(
        "POST",
        f"/api/doc/{session.id}/generate/stream",
        json={
            "instruction": "continue writing intro",
            "text": session.doc_text,
            "compose_mode": "continue",
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")

    assert resp.status_code == 200
    assert "event: final" in body
    assert '"graph_meta"' not in body
    assert seen["dual"] is True
    assert seen["single"] is True


def test_generate_stream_route_graph_enabled_but_quick_edit_shortcut_has_no_graph_meta(monkeypatch):
    session = _prepare_session()
    _patch_generate_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "1")
    monkeypatch.setattr(app_v2, "_ensure_ollama_ready_iter", lambda: (True, ""))

    def _dual(**_kwargs):
        raise AssertionError("route graph should not run when quick-edit shortcut is used")

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(
        app_v2,
        "_try_quick_edit",
        lambda *_args, **_kwargs: _QuickEditStub("# Title\n\n## Intro\nstream quick edited"),
    )

    client = _client()
    with client.stream(
        "POST",
        f"/api/doc/{session.id}/generate/stream",
        json={
            "instruction": "polish intro",
            "text": session.doc_text,
            "compose_mode": "continue",
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")

    assert resp.status_code == 200
    assert "event: final" in body
    assert '"delta": "quick edit"' in body
    assert '"graph_meta"' not in body


def test_generate_section_uses_route_graph_when_enabled(monkeypatch):
    session = _prepare_session()
    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "1")
    seen: dict[str, object] = {}

    def _dual(**kwargs):
        seen.update(kwargs)
        return {
            "ok": 1,
            "text": "# Title\n\n## Intro\nsection via route graph",
            "problems": [],
            "trace_id": "t-route-section",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
        }

    def _legacy(**_kwargs):
        raise AssertionError("legacy graph should not be called when route graph is enabled")
        yield {}  # pragma: no cover

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(app_v2, "run_generate_graph", _legacy)

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/generate/section",
        json={"section": "Intro", "instruction": "rewrite intro"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") == 1
    assert seen
    assert seen.get("compose_mode") == "continue"
    assert seen.get("resume_sections") == ["Intro"]
    graph_meta = body.get("graph_meta") or {}
    assert graph_meta.get("path") == "route_graph"
    assert graph_meta.get("route_id") == "resume_sections"
    assert graph_meta.get("route_entry") == "writer"


def test_generate_section_keeps_legacy_graph_when_route_graph_disabled(monkeypatch):
    session = _prepare_session()
    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "0")

    def _dual(**_kwargs):
        raise AssertionError("route graph should not be called when disabled")

    legacy_called = {"v": False}

    def _legacy(**_kwargs):
        legacy_called["v"] = True
        yield {"event": "final", "text": "# Title\n\n## Intro\nlegacy section text", "problems": []}

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(app_v2, "run_generate_graph", _legacy)

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/generate/section",
        json={"section": "Intro", "instruction": "rewrite intro"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") == 1
    assert legacy_called["v"] is True
    assert "graph_meta" not in body


def test_generate_route_graph_failure_injection_records_metrics_and_recovers(monkeypatch, tmp_path):
    session = _prepare_session()
    _patch_generate_common(monkeypatch)
    metrics_path = tmp_path / "route_graph_events.jsonl"

    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "1")
    monkeypatch.setenv("WRITING_AGENT_FAIL_INJECT_ROUTE_GRAPH", "1")
    monkeypatch.setenv("WRITING_AGENT_ROUTE_GRAPH_METRICS_ENABLE", "1")
    monkeypatch.setenv("WRITING_AGENT_ROUTE_GRAPH_METRICS_PATH", str(metrics_path))

    called = {"dual": False, "single": False}

    def _dual(**_kwargs):
        called["dual"] = True
        return {
            "ok": 1,
            "text": "# Title\n\n## Intro\ndual text",
            "problems": [],
            "trace_id": "t-injected",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
        }

    def _single_pass_generate(*_args, **_kwargs):
        called["single"] = True
        return "# Title\n\n## Intro\nsingle-pass fallback text with enough length"

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(app_v2, "_single_pass_generate", _single_pass_generate)

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        json={
            "instruction": "continue writing intro",
            "text": session.doc_text,
            "compose_mode": "continue",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") == 1
    assert str(body.get("text") or "").strip()
    assert "graph_meta" not in body
    # Failure is injected before dual engine invocation.
    assert called["dual"] is False
    assert called["single"] is True

    rows = _read_jsonl(metrics_path)
    assert any(
        str(r.get("phase") or "") == "generate"
        and str(r.get("event") or "") == "graph_failed"
        and str(r.get("error_code") or "") == "E_INJECTED_ROUTE_GRAPH_FAILURE"
        and bool(r.get("fallback_triggered")) is True
        for r in rows
    )
    assert any(
        str(r.get("phase") or "") == "generate"
        and str(r.get("event") or "") == "fallback_recovered"
        and bool(r.get("fallback_recovered")) is True
        for r in rows
    )


def test_generate_stream_route_graph_failure_injection_records_metrics_and_recovers(monkeypatch, tmp_path):
    session = _prepare_session()
    _patch_generate_common(monkeypatch)
    metrics_path = tmp_path / "route_graph_events_stream.jsonl"

    monkeypatch.setenv("WRITING_AGENT_USE_ROUTE_GRAPH", "1")
    monkeypatch.setenv("WRITING_AGENT_FAIL_INJECT_ROUTE_GRAPH", "1")
    monkeypatch.setenv("WRITING_AGENT_ROUTE_GRAPH_METRICS_ENABLE", "1")
    monkeypatch.setenv("WRITING_AGENT_ROUTE_GRAPH_METRICS_PATH", str(metrics_path))
    monkeypatch.setattr(app_v2, "_ensure_ollama_ready_iter", lambda: (True, ""))

    called = {"dual": False, "single": False}

    def _dual(**_kwargs):
        called["dual"] = True
        return {
            "ok": 1,
            "text": "# Title\n\n## Intro\ndual stream text",
            "problems": [],
            "trace_id": "t-injected-stream",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
        }

    def _single_pass_generate_stream(*_args, **_kwargs):
        called["single"] = True
        yield {"event": "result", "text": "# Title\n\n## Intro\nstream single-pass fallback text"}

    monkeypatch.setattr(app_v2, "run_generate_graph_dual_engine", _dual)
    monkeypatch.setattr(app_v2, "_single_pass_generate_stream", _single_pass_generate_stream)

    client = _client()
    with client.stream(
        "POST",
        f"/api/doc/{session.id}/generate/stream",
        json={
            "instruction": "continue writing intro",
            "text": session.doc_text,
            "compose_mode": "continue",
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")

    assert resp.status_code == 200
    assert "event: final" in body
    assert called["dual"] is False
    assert called["single"] is True

    rows = _read_jsonl(metrics_path)
    assert any(
        str(r.get("phase") or "") == "generate_stream"
        and str(r.get("event") or "") == "graph_failed"
        and str(r.get("error_code") or "") == "E_INJECTED_ROUTE_GRAPH_FAILURE"
        and bool(r.get("fallback_triggered")) is True
        for r in rows
    )
    assert any(
        str(r.get("phase") or "") == "generate_stream"
        and str(r.get("event") or "") == "fallback_recovered"
        and bool(r.get("fallback_recovered")) is True
        for r in rows
    )
