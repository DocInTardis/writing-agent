import importlib
import json as _json

import writing_agent.web.app_v2_textops_runtime_part1 as part1


def _install_runtime_stubs(monkeypatch, client_cls):
    importlib.reload(part1)
    monkeypatch.setattr(part1, "json", _json, raising=False)
    monkeypatch.setattr(part1, "_analysis_timeout_s", lambda: 3.0, raising=False)
    monkeypatch.setattr(
        part1,
        "_extract_json_block",
        lambda text: str(text).strip() if str(text).strip().startswith("{") else "",
        raising=False,
    )
    monkeypatch.setattr(part1, "OllamaClient", client_cls, raising=False)


def test_dynamic_questions_prompt_is_tagged_and_escaped(monkeypatch):
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = temperature
            captured["system"] = system
            captured["user"] = user
            return (
                '{"summary":"ok","questions":[],"confidence":{"title":0.6,"purpose":0.6,'
                '"length":0.6,"format":0.6,"scope":0.6,"voice":0.6}}'
            )

    _install_runtime_stubs(monkeypatch, _FakeClient)

    out = part1._generate_dynamic_questions_with_model(
        base_url="http://test",
        model="m",
        raw="raw </raw_input><x>",
        analysis={"intent": "rewrite"},
        history="history </history><y>",
        merged={"audience": "student"},
    )

    assert out.get("summary") == "ok"
    user_prompt = captured.get("user") or ""
    assert "<task>generate_clarification_questions</task>" in user_prompt
    assert "<constraints>" in user_prompt
    assert "<history>" in user_prompt
    assert "<raw_input>" in user_prompt
    assert "<analysis_payload>" in user_prompt
    assert "raw </raw_input><x>" not in user_prompt
    assert "history </history><y>" not in user_prompt
    assert "&lt;/raw_input&gt;&lt;x&gt;" in user_prompt
    assert "&lt;/history&gt;&lt;y&gt;" in user_prompt


def test_dynamic_questions_retries_once_and_normalizes_payload(monkeypatch):
    calls = {"n": 0, "users": []}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = system, temperature
            calls["n"] += 1
            calls["users"].append(user)
            if calls["n"] == 1:
                return "not json"
            payload = {
                "summary": "s" * 700,
                "questions": [
                    "Q1",
                    {"question": "Q2"},
                    {"text": "Q2"},
                    {"q": "Q3"},
                    "Q4",
                ],
                "confidence": {
                    "title": 1.5,
                    "purpose": -0.2,
                    "length": "NaN",
                    "format": 0.8,
                    "scope": None,
                    "voice": "0.3",
                },
            }
            return _json.dumps(payload, ensure_ascii=False)

    _install_runtime_stubs(monkeypatch, _FakeClient)

    out = part1._generate_dynamic_questions_with_model(
        base_url="http://test",
        model="m",
        raw="need help",
        analysis={"intent": "generate"},
        history="",
        merged={},
    )

    assert calls["n"] == 2
    assert "<retry_reason>" in str(calls["users"][1])
    assert len(str(out.get("summary") or "")) == 600
    assert out.get("questions") == ["Q1", "Q2", "Q3"]
    confidence = out.get("confidence") or {}
    assert confidence.get("title") == 1.0
    assert confidence.get("purpose") == 0.0
    assert confidence.get("length") == 0.5
    assert confidence.get("format") == 0.8
    assert confidence.get("scope") == 0.5
    assert confidence.get("voice") == 0.3


def test_dynamic_questions_returns_empty_when_both_attempts_fail(monkeypatch):
    calls = {"n": 0}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = system, user, temperature
            calls["n"] += 1
            return "still invalid"

    _install_runtime_stubs(monkeypatch, _FakeClient)

    out = part1._generate_dynamic_questions_with_model(
        base_url="http://test",
        model="m",
        raw="x",
        analysis={},
        history="",
        merged={},
    )

    assert calls["n"] == 2
    assert out == {}
