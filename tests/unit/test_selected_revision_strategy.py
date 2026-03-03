from types import SimpleNamespace

from writing_agent.web.domains import revision_edit_runtime_domain as red


def _settings():
    return SimpleNamespace(enabled=True, base_url="http://127.0.0.1:11434", model="qwen2.5:1.5b", timeout_s=5.0)


class _FakeStructuredClient:
    last_user = ""

    def __init__(self, *, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        _ = system, temperature
        _FakeStructuredClient.last_user = user
        return (
            '{"ops":[{"op":"replace","value":"Improved sentence."}],'
            '"meta":{"risk_level":"low","notes":"ok"},'
            '"checks":{"preserve_markers":true}}'
        )


class _FakeMarkerBreakClient:
    def __init__(self, *, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        _ = system, user, temperature
        return (
            '{"ops":[{"op":"replace","value":"marker removed"}],'
            '"meta":{"risk_level":"low","notes":"break"},'
            '"checks":{"preserve_markers":false}}'
        )


class _FakeRefineClient:
    calls = 0

    def __init__(self, *, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        _ = system, user, temperature
        _FakeRefineClient.calls += 1
        if _FakeRefineClient.calls == 1:
            return "just rewrite text without json"
        return (
            '{"ops":[{"op":"replace","value":"Refined sentence."}],'
            '"meta":{"risk_level":"low","notes":"refined"},'
            '"checks":{"preserve_markers":true}}'
        )


def test_selected_revision_uses_context_tags_and_applies_locally():
    base = "Before context. Old sentence. After context."
    start = base.index("Old")
    end = start + len("Old")

    out = red.try_revision_edit(
        session=None,
        instruction="make it clearer",
        text=base,
        selection={"start": start, "end": end, "text": "Old"},
        analysis=None,
        context_policy={"version": "dynamic_v1"},
        sanitize_output_text=lambda x: str(x or "").strip(),
        replace_question_headings=lambda x: x,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeStructuredClient,
    )
    assert out is not None
    updated, note = out
    assert updated == "Before context. Improved sentence. After context."
    assert "policy=dynamic_v1" in note
    assert "<left_context>" in _FakeStructuredClient.last_user
    assert "<selected_text>" in _FakeStructuredClient.last_user
    assert "<right_context>" in _FakeStructuredClient.last_user


def test_selected_revision_rejects_anchor_mismatch():
    base = "Alpha. Target sentence. Omega."
    start = base.index("Target")
    end = start + len("Target")

    out = red.try_revision_edit(
        session=None,
        instruction="rewrite",
        text=base,
        selection={"start": start, "end": end, "text": "Wrong"},
        analysis=None,
        context_policy={"version": "dynamic_v1"},
        sanitize_output_text=lambda x: str(x or "").strip(),
        replace_question_headings=lambda x: x,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeStructuredClient,
    )
    assert out is None


def test_selected_revision_preserves_markers():
    base = 'Before [[TABLE:{"id":1}]] After.'
    start = base.index("[[TABLE:")
    end = base.index("]]", start) + 2

    out = red.try_revision_edit(
        session=None,
        instruction="rewrite marker segment",
        text=base,
        selection={"start": start, "end": end, "text": base[start:end]},
        analysis=None,
        context_policy={"version": "dynamic_v1"},
        sanitize_output_text=lambda x: str(x or "").strip(),
        replace_question_headings=lambda x: x,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeMarkerBreakClient,
    )
    assert out is None


def test_selected_revision_refine_fallback_on_schema_error(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_REVISE_ALLOW_PLAIN_TEXT", "0")
    _FakeRefineClient.calls = 0
    base = "Start. Old sentence. End."
    start = base.index("Old sentence.")
    end = start + len("Old sentence.")

    out = red.try_revision_edit(
        session=None,
        instruction="rewrite selected sentence",
        text=base,
        selection={"start": start, "end": end, "text": "Old sentence."},
        analysis=None,
        context_policy={"version": "dynamic_v1"},
        sanitize_output_text=lambda x: str(x or "").strip(),
        replace_question_headings=lambda x: x,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeRefineClient,
    )
    assert out is not None
    updated, _note = out
    assert updated == "Start. Refined sentence. End."
    assert _FakeRefineClient.calls == 2
