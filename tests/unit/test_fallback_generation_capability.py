from __future__ import annotations

from types import SimpleNamespace

from writing_agent.capabilities.fallback_generation import build_fallback_prompt, single_pass_generate


def test_build_fallback_prompt_uses_tagged_channels() -> None:
    session = SimpleNamespace(template_outline=[], template_required_h2=["Overview", "Method"])

    system, prompt = build_fallback_prompt(
        session,
        instruction="write <important> details",
        length_hint="target <1200 chars>",
    )

    assert "Output Markdown only" in system
    assert "<task>full_document_generation</task>" in prompt
    assert "<required_h2_order>" in prompt
    assert "<length_hint>" in prompt
    assert "<user_requirement>" in prompt
    assert "&lt;important&gt;" in prompt
    assert "&lt;1200 chars&gt;" in prompt


def test_single_pass_generate_uses_length_control_and_sanitize() -> None:
    captured: dict[str, object] = {}

    class _Provider:
        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float, options=None):
            captured["system"] = system
            captured["user"] = user
            captured["temperature"] = temperature
            captured["options"] = options
            return " raw markdown "

    session = SimpleNamespace(template_outline=[], template_required_h2=["Overview"])

    out = single_pass_generate(
        session=session,
        instruction="write report",
        current_text="",
        target_chars=1200,
        get_ollama_settings_fn=lambda: SimpleNamespace(enabled=True, model="m", timeout_s=3.0),
        default_llm_provider_fn=lambda _settings: _Provider(),
        sanitize_output_text_fn=lambda raw: raw.strip(),
        ollama_error_cls=RuntimeError,
    )

    assert out == "raw markdown"
    assert captured["temperature"] == 0.5
    assert captured["options"] == {"num_predict": 1320}
    assert "<task>full_document_generation</task>" in str(captured["user"])

