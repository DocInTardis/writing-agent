from __future__ import annotations

from types import SimpleNamespace

from writing_agent.capabilities.fallback_generation import (
    build_fallback_prompt,
    default_llm_provider,
    single_pass_generate,
)


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


def test_build_fallback_prompt_uses_ascii_safe_unicode_blocks_for_non_ascii_input() -> None:
    session = SimpleNamespace(
        title="区块链赋能乡村社会化服务的组织协同机制研究",
        request=None,
        doc_text="",
        template_outline=[],
        template_required_h2=["摘要", "关键词", "引言", "研究方法", "结果与分析", "结论", "参考文献"],
    )

    _, prompt = build_fallback_prompt(
        session,
        instruction="主题：区块链赋能乡村社会化服务的组织协同机制研究",
        length_hint="target 2800 chars",
    )

    assert "<mode>ascii_safe_unicode_decoding</mode>" in prompt
    assert "<title_unicode>" in prompt
    assert "<required_h2_unicode_json>" in prompt
    assert "\\u533a\\u5757\\u94fe" in prompt
    assert "\\u6458\\u8981" in prompt
    assert "Do not add, delete, rename, or repeat H2 headings." in prompt


def test_build_fallback_prompt_prefers_quoted_topic_over_generic_session_title() -> None:
    session = SimpleNamespace(
        title="未命名文档",
        request=None,
        doc_text="",
        template_outline=[],
        template_required_h2=["摘要", "关键词", "引言", "研究方法", "结果与分析", "结论", "参考文献"],
    )

    _, prompt = build_fallback_prompt(
        session,
        instruction="请围绕“区块链赋能乡村社会化服务的组织协同机制研究”生成一篇完整论文，严格使用既定二级标题结构。",
        length_hint="target 2800 chars",
    )

    assert "\\u533a\\u5757\\u94fe\\u8d4b\\u80fd\\u4e61\\u6751\\u793e\\u4f1a\\u5316\\u670d\\u52a1\\u7684\\u7ec4\\u7ec7\\u534f\\u540c\\u673a\\u5236\\u7814\\u7a76" in prompt
    assert "\\u672a\\u547d\\u540d\\u6587\\u6863" not in prompt


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


def test_default_llm_provider_ignores_ollama_model_when_openai_selected(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "openai")

    provider = default_llm_provider(
        settings=SimpleNamespace(enabled=True, model="qwen2.5:7b", timeout_s=8.0),
        get_default_provider_fn=lambda *, model, timeout_s: captured.update({"model": model, "timeout_s": timeout_s}) or "provider",
        ollama_error_cls=RuntimeError,
    )

    assert provider == "provider"
    assert captured["model"] is None
    assert captured["timeout_s"] == 8.0
