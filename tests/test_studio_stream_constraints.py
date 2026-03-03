from types import SimpleNamespace

from fastapi.testclient import TestClient

import writing_agent.web.app as legacy_app


def _prepare_session(html: str):
    session = legacy_app.store.create()
    session.html = html
    legacy_app.store.put(session)
    return session


def test_studio_stream_uses_structured_worker_and_aggregator_outputs(monkeypatch):
    session = _prepare_session("<h1>T</h1><h2>A</h2><p>old</p><p>old2</p>")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = user, temperature
            if "constrained section editor" in system:
                return '{"section_html":"<h2>A</h2><p>worker text</p><p>worker text 2</p>"}'
            if "constrained HTML report aggregator" in system:
                return '{"html":"<h1>T</h1><h2>A</h2><p>agg text</p><p>agg text 2</p>","assistant_note":"ok"}'
            return '{"html":"<h1>T</h1><h2>A</h2><p>fallback</p><p>fallback 2</p>"}'

    monkeypatch.setattr(
        legacy_app,
        "get_ollama_settings",
        lambda: SimpleNamespace(base_url="http://test", model="m", timeout_s=3.0, enabled=True),
    )
    monkeypatch.setattr(legacy_app, "OllamaClient", _FakeClient)

    client = TestClient(legacy_app.app)
    with client.stream(
        "POST",
        f"/api/studio/{session.id}/chat/stream",
        json={
            "instruction": "rewrite section A",
            "html": session.html,
            "selection": "old",
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")

    assert resp.status_code == 200
    assert "event: final" in body
    assert "agg text" in body
    updated = legacy_app.store.get(session.id)
    assert updated is not None
    assert "agg text" in str(updated.html or "")


def test_studio_stream_worker_invalid_json_fails_closed_to_original_section(monkeypatch):
    session = _prepare_session("<h1>T</h1><h2>A</h2><p>old</p><p>old2</p>")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = user, temperature
            if "constrained section editor" in system:
                return "worker free-text invalid json <p>hacked-worker</p>"
            if "constrained HTML report aggregator" in system:
                return "aggregator free-text invalid json <p>hacked-agg</p>"
            return "invalid"

    monkeypatch.setattr(
        legacy_app,
        "get_ollama_settings",
        lambda: SimpleNamespace(base_url="http://test", model="m", timeout_s=3.0, enabled=True),
    )
    monkeypatch.setattr(legacy_app, "OllamaClient", _FakeClient)

    client = TestClient(legacy_app.app)
    with client.stream(
        "POST",
        f"/api/studio/{session.id}/chat/stream",
        json={
            "instruction": "rewrite section A",
            "html": session.html,
            "selection": "old",
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")

    assert resp.status_code == 200
    assert "event: final" in body
    updated = legacy_app.store.get(session.id)
    assert updated is not None
    final_html = str(updated.html or "")
    assert "old" in final_html
    assert "old2" in final_html
    assert "hacked-worker" not in final_html
    assert "hacked-agg" not in final_html


def test_studio_stream_aggregator_invalid_json_falls_back_to_merged(monkeypatch):
    session = _prepare_session("<h1>T</h1><h2>A</h2><p>old</p><p>old2</p>")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = user, temperature
            if "constrained section editor" in system:
                return '{"section_html":"<h2>A</h2><p>worker merged text</p><p>worker merged text 2</p>"}'
            if "constrained HTML report aggregator" in system:
                return "aggregator invalid free text <p>hacked-agg</p>"
            return "invalid"

    monkeypatch.setattr(
        legacy_app,
        "get_ollama_settings",
        lambda: SimpleNamespace(base_url="http://test", model="m", timeout_s=3.0, enabled=True),
    )
    monkeypatch.setattr(legacy_app, "OllamaClient", _FakeClient)

    client = TestClient(legacy_app.app)
    with client.stream(
        "POST",
        f"/api/studio/{session.id}/chat/stream",
        json={
            "instruction": "rewrite section A",
            "html": session.html,
            "selection": "old",
        },
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore")

    assert resp.status_code == 200
    assert "event: final" in body
    updated = legacy_app.store.get(session.id)
    assert updated is not None
    final_html = str(updated.html or "")
    assert "worker merged text" in final_html
    assert "hacked-agg" not in final_html
