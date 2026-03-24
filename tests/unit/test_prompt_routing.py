from __future__ import annotations

import queue

import writing_agent.v2.graph_runner as graph_runner
import writing_agent.v2.graph_runner_runtime as runtime
from writing_agent.v2.prompts import PromptBuilder, build_prompt_route


def test_prompt_router_selects_academic_cn_for_chinese_thesis() -> None:
    _ctx, route = build_prompt_route(
        role="planner",
        instruction="请生成一篇关于多智能体写作系统的本科毕业论文，包含摘要和关键词",
        intent="generate",
    )
    assert route.suite_id == "academic_cn"
    assert route.prompt_id.startswith("planner.")
    assert "doc_type=academic" in route.route_reason


def test_prompt_router_selects_weekly_suite_for_weekly_intent() -> None:
    _ctx, route = build_prompt_route(
        role="planner",
        instruction="请输出本周工作、问题与风险、下周计划的周报",
        intent="generate",
    )
    assert route.suite_id == "weekly_cn"
    assert route.prompt_id.startswith("planner.")


def test_analyze_instruction_emits_prompt_route_trace(monkeypatch) -> None:
    captured: list[dict] = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

    def _fake_require_json_response(*, client, system: str, user: str, stage: str, temperature: float, max_retries: int):
        _ = client, stage, temperature, max_retries
        assert "JSON" in system
        assert "<task>analyze_user_requirement</task>" in user
        return {"topic": "x", "doc_type": "academic"}

    monkeypatch.setattr(graph_runner, "OllamaClient", _FakeClient)
    monkeypatch.setattr(graph_runner, "_require_json_response", _fake_require_json_response)

    out = graph_runner._analyze_instruction(
        base_url="http://test",
        model="m",
        instruction="请写一篇技术报告",
        current_text="",
        trace_hook=lambda row: captured.append(dict(row)),
    )
    assert out.get("doc_type") == "academic"
    assert captured
    assert captured[0].get("event") == "prompt_route"
    assert "prompt_id" in (captured[0].get("metadata") or {})


def test_generate_section_stream_emits_prompt_route_event(monkeypatch) -> None:
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
    monkeypatch.setattr(runtime, "_postprocess_section", lambda _section, txt, **_kwargs: txt, raising=False)

    class _Cfg:
        temperature = 0.2

    monkeypatch.setattr(runtime, "get_prompt_config", lambda _name, route=None: _Cfg(), raising=False)
    monkeypatch.setattr(runtime.PromptBuilder, "build_writer_prompt", lambda **_kwargs: ("sys", "<task>base</task>"))
    monkeypatch.setattr(runtime, "_stream_structured_blocks", lambda **_kwargs: "generated body", raising=False)

    out_q: queue.Queue[dict] = queue.Queue()
    out = runtime._generate_section_stream(
        base_url="http://test",
        model="m",
        title="Doc",
        section="Method",
        parent_section="",
        instruction="请生成技术报告章节",
        analysis_summary="analysis",
        evidence_summary="",
        allowed_urls=[],
        plan_hint="",
        min_paras=2,
        min_chars=100,
        max_chars=0,
        min_tables=0,
        min_figures=0,
        out_queue=out_q,
        reference_items=[],
        text_store=None,
    )
    assert out == "generated body"
    first = out_q.get_nowait()
    assert first.get("event") == "prompt_route"
    meta = first.get("metadata") if isinstance(first.get("metadata"), dict) else {}
    assert "prompt_id" in meta



def test_analyze_instruction_fast_force_uses_resolved_doc_type(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_ANALYSIS_FAST", "force")
    out = graph_runner._analyze_instruction(
        base_url="http://unused",
        model="dummy",
        instruction="Generate an academic paper with abstract and keywords.",
        current_text="",
        trace_hook=None,
    )
    assert str(out.get("doc_type") or "") == "academic"



def test_writer_prompt_includes_figure_contract() -> None:
    system, user = PromptBuilder.build_writer_prompt(
        section_title="System Architecture",
        plan_hint="Need one architecture figure.",
        doc_title="Doc",
        analysis_summary="Write a technical section.",
        section_id="H2::system_architecture",
        previous_content=None,
        rag_context=None,
    )
    joined = system + "\n" + user
    assert 'kind+caption+data' in joined
    assert 'caption-only figure blocks' in joined
    assert 'flow/architecture/bar/line/pie/timeline/sequence/er' in joined


def test_writer_prompt_keeps_global_guardrails_when_route_overrides_writer_system() -> None:
    _ctx, route = build_prompt_route(
        role="writer",
        instruction="Write a system architecture section and add a diagram only if needed.",
        intent="generate",
        doc_type="technical_report",
    )
    system, _user = PromptBuilder.build_writer_prompt(
        section_title="System Architecture",
        plan_hint="Need one architecture figure.",
        doc_title="Doc",
        analysis_summary="Write a technical section.",
        section_id="H2::system_architecture",
        previous_content=None,
        rag_context=None,
        route=route,
    )
    assert "\u4e25\u7981\u8f93\u51fa\u4efb\u4f55\u5199\u4f5c\u8fc7\u7a0b\u89e3\u91ca" in system
    assert "\u529f\u80fd\u6027\u8bf4\u660e\u53e5" in system
