import queue

import writing_agent.v2.graph_runner_runtime as runtime


def test_generate_section_stream_injects_available_sources_tag(monkeypatch):
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

    monkeypatch.setattr(runtime, "OllamaClient", _FakeClient)
    monkeypatch.setattr(runtime, "_section_timeout_s", lambda: 3.0, raising=False)
    monkeypatch.setattr(runtime, "_section_title", lambda section: section, raising=False)
    monkeypatch.setattr(runtime, "_is_reference_section", lambda _section: False, raising=False)
    monkeypatch.setattr(runtime, "_maybe_rag_context", lambda **_kwargs: "", raising=False)
    monkeypatch.setattr(runtime, "_normalize_section_id", lambda _section: "H2::method", raising=False)
    monkeypatch.setattr(runtime, "_predict_num_tokens", lambda **_kwargs: 256, raising=False)

    class _Cfg:
        temperature = 0.2

    monkeypatch.setattr(runtime, "get_prompt_config", lambda _name: _Cfg(), raising=False)
    monkeypatch.setattr(runtime.PromptBuilder, "build_writer_prompt", lambda **_kwargs: ("sys", "<task>base</task>"))

    def _fake_stream(**kwargs):
        captured["user"] = str(kwargs.get("user") or "")
        return "generated body"

    monkeypatch.setattr(runtime, "_stream_structured_blocks", _fake_stream, raising=False)
    monkeypatch.setattr(runtime, "_postprocess_section", lambda _section, txt, **_kwargs: txt, raising=False)

    out = runtime._generate_section_stream(
        base_url="http://test",
        model="m",
        title="Doc",
        section="Method",
        parent_section="",
        instruction="inst",
        analysis_summary="analysis",
        evidence_summary="",
        allowed_urls=[],
        plan_hint="",
        min_paras=2,
        min_chars=100,
        max_chars=0,
        min_tables=0,
        min_figures=0,
        out_queue=queue.Queue(),
        reference_items=[
            {"title": "Paper <A>", "url": "https://example.com?x=<1>"},
        ],
        text_store=None,
    )

    assert "generated body" in out
    user_prompt = captured.get("user") or ""
    assert "<available_sources>" in user_prompt
    assert "Paper &lt;A&gt;" in user_prompt
    assert "&lt;1&gt;" in user_prompt
