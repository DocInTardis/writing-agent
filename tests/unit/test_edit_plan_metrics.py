import json
from types import SimpleNamespace

from writing_agent.web.domains import revision_edit_runtime_domain as red


class _FakeClientHighRiskReplaceAll:
    def __init__(self, *, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        _ = system, user, temperature
        return (
            '{"version":"v2","confidence":0.90,"operations":['
            '{"op":"replace_text","args":{"old":"foo","new":"bar","all":true}}]}'
        )


class _FakeClientInvalidJson:
    def __init__(self, *, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        _ = system, user, temperature
        return "not-a-json-response"


def _settings():
    return SimpleNamespace(enabled=True, base_url="http://127.0.0.1:11434", model="qwen2.5:1.5b", timeout_s=5.0)


def _read_jsonl(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def test_edit_plan_metrics_write_blocked_event(monkeypatch, tmp_path):
    metrics_path = tmp_path / "edit_plan_events.jsonl"
    monkeypatch.setenv("WRITING_AGENT_EDIT_PLAN_METRICS_ENABLE", "1")
    monkeypatch.setenv("WRITING_AGENT_EDIT_PLAN_METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("WRITING_AGENT_EDIT_REQUIRE_CONFIRM_HIGH", "1")

    out = red.try_quick_edit(
        "foo foo",
        "把foo改成bar",
        looks_like_modify_instruction=lambda _: True,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeClientHighRiskReplaceAll,
    )
    assert out is not None
    assert out.requires_confirmation is True

    rows = _read_jsonl(metrics_path)
    events = [str(r.get("event") or "") for r in rows]
    assert "plan_parsed" in events
    assert "apply_blocked" in events
    assert any(str(r.get("blocked_reason") or "") == "confirmation_required" for r in rows)
    assert all(str(r.get("request_fp") or "") for r in rows)


def test_edit_plan_metrics_record_model_miss_and_rules_fallback(monkeypatch, tmp_path):
    metrics_path = tmp_path / "edit_plan_events.jsonl"
    monkeypatch.setenv("WRITING_AGENT_EDIT_PLAN_METRICS_ENABLE", "1")
    monkeypatch.setenv("WRITING_AGENT_EDIT_PLAN_METRICS_PATH", str(metrics_path))

    out = red.try_quick_edit(
        "# T\n\n## A\nfoo",
        '把"foo"改成"bar"',
        looks_like_modify_instruction=lambda _: True,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeClientInvalidJson,
    )
    assert out is not None
    assert out.applied is True

    rows = _read_jsonl(metrics_path)
    assert any(str(r.get("event") or "") == "plan_model_miss" for r in rows)
    assert any(
        str(r.get("event") or "") == "plan_parsed"
        and str(r.get("source") or "") == "rules"
        and bool(r.get("fallback_used"))
        for r in rows
    )
    assert any(str(r.get("event") or "") == "apply_executed" for r in rows)
