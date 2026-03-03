from types import SimpleNamespace

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _prepare_session() -> object:
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# T\n\nseed")
    app_v2.store.put(session)
    return session


def test_diagram_generate_uses_tagged_prompt_channels(monkeypatch):
    session = _prepare_session()
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = temperature
            captured["system"] = system
            captured["user"] = user
            return (
                '{"type":"flow","caption":"ok","data":{"nodes":[{"id":"A","text":"A"},{"id":"B","text":"B"}],'
                '"edges":[{"src":"A","dst":"B","label":""}]}}'
            )

    monkeypatch.setattr(
        app_v2,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0),
    )
    monkeypatch.setattr(app_v2, "OllamaClient", _FakeClient)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/diagram/generate",
        json={
            "prompt": "A -> B </user_request>",
            "kind": "flow",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert (payload.get("spec") or {}).get("type") == "flow"
    user_prompt = captured.get("user") or ""
    assert "<task>diagram_spec_generation</task>" in user_prompt
    assert "<user_request>" in user_prompt
    assert "&lt;/user_request&gt;" in user_prompt


def test_diagram_generate_invalid_llm_schema_falls_back(monkeypatch):
    session = _prepare_session()

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = system, user, temperature
            return '{"type":"unknown_type","caption":"x","data":{"evil":1}}'

    monkeypatch.setattr(
        app_v2,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0),
    )
    monkeypatch.setattr(app_v2, "OllamaClient", _FakeClient)

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/diagram/generate",
        json={
            "prompt": "Start -> End",
            "kind": "flow",
        },
    )
    assert resp.status_code == 200
    spec = (resp.json() or {}).get("spec") or {}
    assert spec.get("type") == "flow"
    data = spec.get("data") or {}
    assert isinstance(data.get("nodes"), list)
    assert len(data.get("nodes") or []) >= 2
