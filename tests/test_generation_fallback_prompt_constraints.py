from types import SimpleNamespace

import writing_agent.web.app_v2 as app_v2


def test_build_fallback_prompt_uses_tagged_channels():
    session = SimpleNamespace(
        template_outline=[],
        template_required_h2=["Overview", "Method"],
    )
    system, prompt = app_v2._build_fallback_prompt(
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
