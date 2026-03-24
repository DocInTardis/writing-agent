from __future__ import annotations

from writing_agent.capabilities.contracts import GenerateWorkflowDeps, GenerateWorkflowRequest
from writing_agent.workflows import generate_workflow


def test_generate_workflow_runs_full_chain_with_native_engine(monkeypatch) -> None:
    monkeypatch.setattr(generate_workflow, "should_use_langgraph", lambda: False)

    def _fake_run_generate_graph(**_kwargs):
        yield {"event": "prompt_route", "stage": "writer", "metadata": {"model": "stub"}}
        yield {
            "event": "final",
            "text": "workflow text",
            "problems": [],
            "status": "success",
            "failure_reason": "",
            "quality_snapshot": {"status": "success", "problem_count": 0},
        }

    out = generate_workflow.run_generate_workflow(
        request=GenerateWorkflowRequest(
            instruction="write",
            current_text="",
            required_h2=["Introduction"],
            required_outline=[],
            expand_outline=False,
            config=object(),
            compose_mode="auto",
            resume_sections=[],
            format_only=False,
            plan_confirm={},
        ),
        deps=GenerateWorkflowDeps(
            run_generate_graph=_fake_run_generate_graph,
            light_self_check=lambda **_kwargs: [],
            target_total_chars=lambda _config: 1200,
            is_evidence_enabled=lambda: False,
        ),
    )

    assert out.get("ok") == 1
    assert out.get("text") == "workflow text"
    assert out.get("engine") == "native"
    assert out.get("route_id") == "compose_mode"
    assert out.get("route_entry") == "planner"
    assert isinstance(out.get("prompt_trace"), list)


def test_generate_workflow_skips_composition_when_plan_interrupted(monkeypatch) -> None:
    monkeypatch.setattr(generate_workflow, "should_use_langgraph", lambda: False)
    called = {"run_generate_graph": 0}

    def _fake_run_generate_graph(**_kwargs):
        called["run_generate_graph"] += 1
        yield {"event": "final", "text": "should not run", "problems": [], "status": "success"}

    out = generate_workflow.run_generate_workflow(
        request=GenerateWorkflowRequest(
            instruction="write",
            current_text="# Existing",
            required_h2=[],
            required_outline=[],
            expand_outline=False,
            config=object(),
            compose_mode="continue",
            resume_sections=[],
            format_only=False,
            plan_confirm={"decision": "interrupted", "score": 2, "note": "pause"},
        ),
        deps=GenerateWorkflowDeps(
            run_generate_graph=_fake_run_generate_graph,
            light_self_check=lambda **_kwargs: [],
            target_total_chars=lambda _config: 800,
            is_evidence_enabled=lambda: False,
        ),
    )

    assert called["run_generate_graph"] == 0
    assert out.get("terminal_status") == "interrupted"
    assert out.get("failure_reason") == "plan_not_confirmed_by_user"
    assert out.get("text") == "# Existing"
