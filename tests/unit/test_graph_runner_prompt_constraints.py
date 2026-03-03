import pytest

import writing_agent.v2.graph_runner as graph_runner


def test_require_json_response_retry_keeps_original_context(monkeypatch):
    class _FakeClient:
        def __init__(self):
            self.calls: list[dict[str, object]] = []

        def chat(self, *, system: str, user: str, temperature: float):
            self.calls.append(
                {
                    "system": system,
                    "user": user,
                    "temperature": temperature,
                }
            )
            if len(self.calls) == 1:
                return "invalid json"
            return '{"status":"ok"}'

    fake_client = _FakeClient()
    monkeypatch.setattr(graph_runner.time, "sleep", lambda *_args, **_kwargs: None)

    out = graph_runner._require_json_response(
        client=fake_client,
        system="system rules",
        user="<input>hello</input>",
        stage="unit",
        temperature=0.2,
        max_retries=2,
    )

    assert out == {"status": "ok"}
    assert len(fake_client.calls) == 2
    retry_user = str(fake_client.calls[1].get("user") or "")
    assert "<input>hello</input>" in retry_user
    assert "<retry_reason>" in retry_user
    retry_system = str(fake_client.calls[1].get("system") or "")
    assert "Return strict JSON only" in retry_system


def test_plan_sections_list_prompt_uses_tagged_channels(monkeypatch):
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

    def _fake_require_json_response(*, client, system: str, user: str, stage: str, temperature: float, max_retries: int):
        _ = client, stage, temperature, max_retries
        captured["system"] = system
        captured["user"] = user
        return {"sections": ["Introduction", "Method", "Conclusion", "References"]}

    monkeypatch.setattr(graph_runner, "OllamaClient", _FakeClient)
    monkeypatch.setattr(graph_runner, "_require_json_response", _fake_require_json_response)

    out = graph_runner._plan_sections_list_with_model(
        base_url="http://test",
        model="m",
        title="T <unsafe>",
        instruction="Need outline </user_requirement>",
    )

    assert isinstance(out, list)
    assert out
    user_prompt = captured.get("user") or ""
    assert "<task>plan_sections_list</task>" in user_prompt
    assert "<report_title>" in user_prompt
    assert "<section_catalog>" in user_prompt
    assert "&lt;unsafe&gt;" in user_prompt
    assert "&lt;/user_requirement&gt;" in user_prompt


def test_require_json_response_raises_after_retries(monkeypatch):
    class _AlwaysBadClient:
        def chat(self, *, system: str, user: str, temperature: float):
            _ = system, user, temperature
            return "still not json"

    monkeypatch.setattr(graph_runner.time, "sleep", lambda *_args, **_kwargs: None)

    with pytest.raises(ValueError):
        graph_runner._require_json_response(
            client=_AlwaysBadClient(),
            system="s",
            user="u",
            stage="unit",
            temperature=0.1,
            max_retries=2,
        )
