from __future__ import annotations

from types import SimpleNamespace

from writing_agent.capabilities.generation_policy import (
    should_use_fast_generate,
    summarize_analysis,
    system_pressure_high,
)


def test_system_pressure_high_uses_thresholds() -> None:
    os_module = SimpleNamespace(environ={"WRITING_AGENT_FAST_CPU": "70", "WRITING_AGENT_FAST_MEM": "80"})
    psutil_module = SimpleNamespace(
        cpu_percent=lambda interval=0.2: 75.0,
        virtual_memory=lambda: SimpleNamespace(percent=50.0),
    )
    assert system_pressure_high(os_module=os_module, psutil_module=psutil_module) is True


def test_should_use_fast_generate_respects_env_and_prefs() -> None:
    os_module = SimpleNamespace(environ={})
    assert should_use_fast_generate(
        raw_instruction="write",
        target_chars=1000,
        prefs={"fast_generate": True},
        os_module=os_module,
        system_pressure_high_fn=lambda: False,
    ) is True


def test_summarize_analysis_builds_summary_and_steps() -> None:
    out = summarize_analysis(
        raw="write report",
        analysis={
            "intent": {"name": "report"},
            "entities": {"title": "AI", "audience": "team"},
            "constraints": ["formal", "markdown"],
            "steps": ["draft", "review"],
            "missing": ["deadline"],
        },
    )

    assert "requirement: write report" in out["summary"]
    assert "intent: report" in out["summary"]
    assert out["missing"] == ["deadline"]
    assert out["steps"] == ["draft", "review"]
