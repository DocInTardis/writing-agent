from __future__ import annotations

import re

from types import SimpleNamespace

from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.graph_runner import GenerateConfig
from writing_agent.v2.graph_runner_runtime_originality_domain import (
    build_feedback,
    evaluate_hot_sample,
    rewrite_for_originality,
)


_BAD_FORMULAIC = (
    "This study maps service demand across villages using archived request logs and annual statistics. "
    "This study compares response latency across counties using audited workflow timestamps and completion records. "
    "This study examines actor coordination through task routing data, signed confirmations, and error traces. "
    "This study evaluates governance transparency with traceability indicators, dispute logs, and review outcomes. "
    "This study summarizes the final evidence boundary with explicit variables, observed tradeoffs, and implementation limits."
)

_GOOD_ORIGINAL = (
    "Village-level request logs indicate uneven seasonal demand, while audited completion timestamps reveal county-specific response gaps. "
    "Task-routing records further show that coordination failures cluster around cross-agency handoff points rather than intake volume alone. "
    "The section therefore grounds its interpretation in traceability evidence, observed bottlenecks, and explicit operational limits."
)

def _first_h2_body(text: str) -> str:
    matches = list(re.finditer(r"(?m)^##\s+.+$", str(text or "")))
    if not matches:
        return str(text or "")
    start = matches[0].end()
    end = matches[1].start() if len(matches) > 1 else len(text)
    return str(text[start:end]).strip()



def _patch_runtime_basics(monkeypatch, *, provider) -> None:
    monkeypatch.setattr(
        runtime_module,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0),
    )
    monkeypatch.setattr(runtime_module, "get_default_provider", lambda **_kwargs: provider)
    monkeypatch.setattr(runtime_module, "get_provider_name", lambda: "ollama")
    monkeypatch.setattr(runtime_module, "get_provider_snapshot", lambda **_kwargs: {"provider": "ollama"})
    monkeypatch.setattr(runtime_module, "_ollama_installed_models", lambda: [])
    monkeypatch.setattr(runtime_module, "_analysis_correctness_guard", lambda **_kwargs: (True, [], {}))
    monkeypatch.setattr(
        runtime_module,
        "_analyze_instruction",
        lambda **_kwargs: {
            "topic": "Research Workflow",
            "doc_type": "academic",
            "audience": "researcher",
            "style": "formal",
            "keywords": ["workflow", "traceability"],
            "must_include": [],
            "constraints": [],
            "_confidence_score": 0.95,
            "_schema_valid": True,
            "_needs_clarification": False,
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "_classify_paradigm",
        lambda **_kwargs: {
            "paradigm": "engineering",
            "runner_up": "bibliometric",
            "confidence": 0.93,
            "margin": 0.42,
            "reasons": ["test"],
            "score_map": {"engineering": 2.2, "bibliometric": 0.7},
            "source": "classifier",
            "low_confidence": False,
        },
    )
    monkeypatch.setenv("WRITING_AGENT_FAST_PLAN", "1")
    monkeypatch.setenv("WRITING_AGENT_STRICT_JSON", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "0")
    monkeypatch.setenv("WRITING_AGENT_VALIDATE_PLAN", "0")
    monkeypatch.setenv("WRITING_AGENT_ENSURE_MIN_LENGTH", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_CONTRACT_SLOTS", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_META_FIREWALL", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_FINAL_VALIDATION", "0")
    monkeypatch.setenv("WRITING_AGENT_MIN_H2_COUNT", "0")
    monkeypatch.setenv("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_MIN_CHARS", "180")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_FORMULAIC_OPENING_RATIO", "0.20")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_REPEAT_RATIO", "0.10")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_SOURCE_OVERLAP_RATIO", "0.20")


class _PassiveProvider:
    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2, options=None) -> str:
        _ = system, user, temperature, options
        return "OK"

    def chat_stream(self, *, system: str, user: str, temperature: float = 0.2, options=None):
        _ = system, user, temperature, options
        yield "OK"

    def embeddings(self, *, prompt: str, model: str | None = None):
        _ = prompt, model
        return [0.0]


class _RewriteProvider(_PassiveProvider):
    last_user = ""

    def chat(self, *, system: str, user: str, temperature: float = 0.2, options=None) -> str:
        _ = system, temperature, options
        type(self).last_user = user
        if "<task>rewrite_for_originality</task>" in user:
            return _GOOD_ORIGINAL
        return "OK"


class _RuntimeApiStub:
    def __init__(self, provider):
        self._provider = provider

    def _runtime_escape_prompt_text(self, text: str) -> str:
        return str(text or "")

    def get_default_provider(self, **_kwargs):
        return self._provider

    def _section_timeout_s(self) -> float:
        return 3.0

    def get_provider_name(self) -> str:
        return "ollama"

    def _call_with_generation_slot(self, *, fn, **_kwargs):
        return fn()


def test_runtime_rejects_fast_draft_when_originality_hot_sample_fails(monkeypatch):
    _patch_runtime_basics(monkeypatch, provider=_PassiveProvider())
    monkeypatch.setenv("WRITING_AGENT_FAST_DRAFT", "1")
    monkeypatch.setattr(runtime_module, "_is_evidence_enabled", lambda: False)
    monkeypatch.setattr(runtime_module, "_fast_fill_section", lambda *args, **kwargs: _BAD_FORMULAIC)
    monkeypatch.setattr(
        runtime_module,
        "_draft_section_with_optional_segments",
        lambda **_kwargs: (_GOOD_ORIGINAL, False),
    )

    events = list(
        runtime_module.run_generate_graph(
            instruction="write a paper",
            current_text="",
            required_h2=["Introduction"],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1, min_total_chars=0),
        )
    )

    assert any(str(ev.get("event") or "") == "section_fast_draft_rejected" for ev in events if isinstance(ev, dict))
    hot_sample_events = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "section_originality_hot_sample"]
    assert any(str(ev.get("phase") or "") == "fast_draft" and bool(ev.get("passed")) is False for ev in hot_sample_events)
    assert any(str(ev.get("section_profile") or "") == "introduction" for ev in hot_sample_events)
    final = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "final"][-1]
    final_text = str(final.get("text") or "")
    intro_body = _first_h2_body(final_text)
    assert "Village-level request logs indicate uneven seasonal demand" in intro_body
    assert _BAD_FORMULAIC not in final_text
    snapshot = dict(final.get("quality_snapshot") or {})
    originality = dict(snapshot.get("section_originality_hot_sample") or {})
    assert originality.get("enabled") is True
    assert int(originality.get("failed_event_count") or 0) >= 1
    assert int(originality.get("fast_draft_rejected_count") or 0) == 1
    assert int(originality.get("rewrite_count") or 0) == 0
    assert int(originality.get("checked_section_count") or 0) >= 1


def test_runtime_rewrites_section_when_originality_hot_sample_fails(monkeypatch):
    _patch_runtime_basics(monkeypatch, provider=_RewriteProvider())
    monkeypatch.setenv("WRITING_AGENT_FAST_DRAFT", "0")
    monkeypatch.setattr(runtime_module, "_is_evidence_enabled", lambda: False)
    monkeypatch.setattr(
        runtime_module,
        "_draft_section_with_optional_segments",
        lambda **_kwargs: (_BAD_FORMULAIC, False),
    )

    events = list(
        runtime_module.run_generate_graph(
            instruction="write a paper",
            current_text="",
            required_h2=["Introduction"],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1, min_total_chars=0),
        )
    )

    assert any(str(ev.get("event") or "") == "section_originality_hot_sample_rewrite" for ev in events if isinstance(ev, dict))
    hot_sample_events = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "section_originality_hot_sample"]
    assert any(str(ev.get("phase") or "") == "initial" and bool(ev.get("passed")) is False for ev in hot_sample_events)
    assert any(str(ev.get("phase") or "") == "post_rewrite" and bool(ev.get("passed")) is True for ev in hot_sample_events)
    final = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "final"][-1]
    final_text = str(final.get("text") or "")
    intro_body = _first_h2_body(final_text)
    assert len(intro_body.strip()) > 120
    assert intro_body.count("This study") <= 1
    assert _BAD_FORMULAIC not in final_text
    snapshot = dict(final.get("quality_snapshot") or {})
    originality = dict(snapshot.get("section_originality_hot_sample") or {})
    assert int(originality.get("rewrite_count") or 0) == 1
    assert int(originality.get("retry_count") or 0) == 0
    rows = list(originality.get("rows") or [])
    assert any("post_rewrite" in list(row.get("phases") or []) for row in rows)


def test_evaluate_hot_sample_checks_middle_and_tail_for_formulaic_output(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_FORMULAIC_OPENING_RATIO", "0.20")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_REPEAT_RATIO", "0.20")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_SOURCE_OVERLAP_RATIO", "1.0")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_LOW_INFORMATION_RATIO", "1.0")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_TEMPLATE_PADDING_RATIO", "1.0")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_AI_RATE", "1.0")
    monkeypatch.setenv("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_SENTENCES", "6")
    monkeypatch.setenv("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_MIN_CHARS", "180")

    text = (
        "Village request logs show that service demand spikes around subsidy windows, while county audit records indicate slower closure in cross-agency cases. "
        "Interview summaries further suggest that routing bottlenecks arise when village clerks and county reviewers rely on different verification thresholds. "
        "These patterns show that coordination cost, not intake volume alone, shapes the observed response gap. "
        + _BAD_FORMULAIC
    )

    metrics = evaluate_hot_sample(text=text, source_rows=[], section_title="Introduction")

    assert metrics["checked"] is True
    assert metrics["passed"] is False
    assert metrics["section_profile"] == "introduction"
    assert float(metrics["formulaic_opening_ratio"]) > float(metrics["max_formulaic_opening_ratio"])
    assert metrics["formulaic_opening_hits"]


def test_evaluate_hot_sample_produces_revision_actions(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_FORMULAIC_OPENING_RATIO", "0.20")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_REPEAT_RATIO", "0.20")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_SOURCE_OVERLAP_RATIO", "0.18")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_LOW_INFORMATION_RATIO", "1.0")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_TEMPLATE_PADDING_RATIO", "1.0")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_AI_RATE", "0.70")
    monkeypatch.setenv("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_SENTENCES", "6")
    monkeypatch.setenv("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_MIN_CHARS", "180")

    source_rows = [
        {
            "title": "Audit summary",
            "summary": "Village request logs indicate uneven seasonal demand and county workflow timestamps show cross-agency backlog during subsidy windows.",
        }
    ]
    text = (
        "Firstly, this study explains the target, path, and execution in a uniform way. "
        "Secondly, this study explains the target, path, and execution in a uniform way. "
        "Village request logs indicate uneven seasonal demand and county workflow timestamps show cross-agency backlog during subsidy windows. "
        "Finally, this study explains the target, path, and execution in a uniform way."
    )

    metrics = evaluate_hot_sample(text=text, source_rows=source_rows, section_title="Results")

    assert metrics["checked"] is True
    assert metrics["section_profile"] == "results"
    assert isinstance(metrics.get("ai_improvement_actions"), list)
    assert metrics.get("ai_improvement_actions")
    assert isinstance(metrics.get("source_revision_advice"), list)
    assert metrics.get("source_revision_advice")
    feedback = build_feedback(metrics)
    assert "Originality correction:" in feedback
    assert any(item in feedback for item in metrics.get("ai_improvement_actions", []))


def test_rewrite_prompt_includes_runtime_revision_actions(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_ORIGINALITY_REWRITE_ENABLED", "1")
    provider = _RewriteProvider()
    runtime_api = _RuntimeApiStub(provider)
    source_rows = [
        {
            "title": "Traceability note",
            "summary": "Village request logs indicate uneven seasonal demand and county workflow timestamps reveal cross-agency backlog.",
        }
    ]
    metrics = evaluate_hot_sample(
        text=(
            "This study maps service demand across villages using archived request logs and annual statistics. "
            "This study compares response latency across counties using audited workflow timestamps and completion records. "
            "Village request logs indicate uneven seasonal demand and county workflow timestamps reveal cross-agency backlog."
        ),
        source_rows=source_rows,
        section_title="Introduction",
    )

    rewritten, changed = rewrite_for_originality(
        runtime_api,
        section_key="intro",
        section_id="intro",
        section_title="Introduction",
        model="m",
        draft_text=_BAD_FORMULAIC,
        metrics=metrics,
        source_rows=source_rows,
        out_queue=None,
    )

    assert changed is True
    assert rewritten == _GOOD_ORIGINAL
    assert "<ai_revision_actions>" in _RewriteProvider.last_user
    assert "<source_revision_actions>" in _RewriteProvider.last_user
    assert any(action in _RewriteProvider.last_user for action in metrics.get("ai_improvement_actions", []))
    assert any(action in _RewriteProvider.last_user for action in metrics.get("source_revision_advice", []))


def test_evaluate_hot_sample_uses_section_specific_threshold_profiles(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_FORMULAIC_OPENING_RATIO", "0.34")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_REPEAT_RATIO", "0.20")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_SOURCE_OVERLAP_RATIO", "0.18")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_LOW_INFORMATION_RATIO", "0.22")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_TEMPLATE_PADDING_RATIO", "0.12")
    monkeypatch.setenv("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_AI_RATE", "0.72")
    monkeypatch.setenv("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_SENTENCES", "6")
    monkeypatch.setenv("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_MIN_CHARS", "180")

    text = (
        "This study maps service demand across villages using archived request logs and annual statistics. "
        "This study compares response latency across counties using audited workflow timestamps and completion records. "
        "This study examines actor coordination through task routing data, signed confirmations, and error traces. "
        "This study evaluates governance transparency with traceability indicators, dispute logs, and review outcomes."
    )

    abstract_metrics = evaluate_hot_sample(text=text, source_rows=[], section_title="Abstract")
    method_metrics = evaluate_hot_sample(text=text, source_rows=[], section_title="研究方法")
    results_metrics = evaluate_hot_sample(text=text, source_rows=[], section_title="结果与分析")

    assert abstract_metrics["section_profile"] == "abstract"
    assert method_metrics["section_profile"] == "method"
    assert results_metrics["section_profile"] == "results"
    assert float(abstract_metrics["max_formulaic_opening_ratio"]) < float(method_metrics["max_formulaic_opening_ratio"])
    assert float(results_metrics["max_formulaic_opening_ratio"]) < 0.34
    assert float(method_metrics["max_source_overlap_ratio"]) >= 0.22
    assert float(abstract_metrics["max_ai_rate"]) < float(method_metrics["max_ai_rate"])
