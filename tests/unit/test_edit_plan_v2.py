from types import SimpleNamespace

from writing_agent.web.domains import revision_edit_runtime_domain as red


class _FakeClientReplace:
    def __init__(self, *, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        _ = system, user, temperature
        return (
            '{"version":"v2","confidence":0.93,"operations":['
            '{"op":"replace_text","args":{"old":"foo","new":"bar"}}]}'
        )


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


class _FakeClientMissingTarget:
    def __init__(self, *, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        _ = system, user, temperature
        return (
            '{"version":"v2","confidence":0.80,"operations":['
            '{"op":"move_section","args":{"title":"不存在章节","anchor":"实施计划","position":"after"}}]}'
        )


def _settings():
    return SimpleNamespace(enabled=True, base_url="http://127.0.0.1:11434", model="qwen2.5:1.5b", timeout_s=5.0)


def test_try_quick_edit_prefers_schema_model_plan():
    text = "# T\n\n## A\nfoo"
    out = red.try_quick_edit(
        text,
        "把foo改成bar",
        looks_like_modify_instruction=lambda _: True,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeClientReplace,
    )
    assert out is not None
    assert "bar" in out.text
    assert "source=model" in out.note
    assert out.applied is True


def test_try_quick_edit_high_risk_requires_confirmation(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_EDIT_REQUIRE_CONFIRM_HIGH", "1")
    text = "foo foo"
    blocked = red.try_quick_edit(
        text,
        "把foo改成bar",
        looks_like_modify_instruction=lambda _: True,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeClientHighRiskReplaceAll,
    )
    assert blocked is not None
    assert blocked.text == text
    assert "确认执行" in blocked.note
    assert blocked.requires_confirmation is True
    assert blocked.applied is False

    allowed = red.try_quick_edit(
        text,
        "把foo改成bar，确认执行",
        looks_like_modify_instruction=lambda _: True,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeClientHighRiskReplaceAll,
    )
    assert allowed is not None
    assert allowed.text == "bar bar"
    assert "source=model" in allowed.note
    assert allowed.applied is True


def test_try_quick_edit_falls_back_to_rules_when_model_invalid():
    text = "# T\n\n## A\nfoo"
    out = red.try_quick_edit(
        text,
        '把"foo"改为"bar"',
        looks_like_modify_instruction=lambda _: True,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeClientInvalidJson,
    )
    assert out is not None
    assert "bar" in out.text
    assert "source=rules" in out.note


def test_try_quick_edit_rejects_invalid_model_plan():
    text = "# T\n\n## 实施计划\ntext"
    out = red.try_quick_edit(
        text,
        "把不存在章节移到实施计划后面",
        looks_like_modify_instruction=lambda _: True,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeClientMissingTarget,
    )
    assert out is None


def test_parse_edit_ops_colloquial_delete():
    ops = red._parse_edit_ops("第3节不要了")
    assert ops
    assert ops[0].op == "delete_section"
    assert int(ops[0].args.get("index") or 0) == 3


def test_parse_edit_ops_replace_does_not_capture_ba_prefix():
    ops = red._parse_edit_ops("把市场规模改为市场容量")
    assert ops
    assert ops[0].op == "replace_text"
    assert ops[0].args.get("old") == "市场规模"
    assert ops[0].args.get("new") == "市场容量"
