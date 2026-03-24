from __future__ import annotations

from writing_agent.workflows.orchestration_backend import (
    attach_prompt_trace,
    build_failover_quality_snapshot,
    build_legacy_graph_kwargs,
    build_legacy_graph_meta,
    build_route_graph_kwargs,
    build_route_graph_meta,
    build_route_metric_extra,
    build_single_pass_failover_meta,
    drive_single_pass_stream_recovery,
    finalize_graph_meta,
    handle_single_pass_stream_recovery_failure,
    normalize_prompt_trace,
    prepare_generate_legacy_event_observation,
    prepare_generate_route_graph_outcome,
    prepare_single_pass_stream_recovery_emission_plan,
    prepare_single_pass_stream_recovery_result,
    prepare_single_pass_stream_recovery_success_plan,
    prepare_stream_fallback_trigger,
    prepare_stream_graph_failure_fallback_trigger,
    prepare_stream_insufficient_fallback_trigger,
    prepare_stream_legacy_event_observation,
    prepare_stream_legacy_terminal_payload,
    prepare_stream_route_graph_outcome_plan,
    prepare_stream_route_graph_terminal_payload,
    record_orchestration_metric,
    resolve_stream_graph_path,
    route_graph_enabled,
    run_single_pass_stream_recovery,
    should_skip_semantic_failover,
    sync_route_metric_meta,
    sync_trace_context,
    text_requires_failover,
)


def test_route_graph_enabled_requires_flag_and_runner() -> None:
    assert route_graph_enabled(environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"}, dual_engine_runner=object()) is True
    assert route_graph_enabled(environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "0"}, dual_engine_runner=object()) is False
    assert route_graph_enabled(environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"}, dual_engine_runner=None) is False



def test_build_legacy_graph_kwargs_keeps_legacy_backend_inputs() -> None:
    payload = build_legacy_graph_kwargs(
        instruction="write",
        current_text="old",
        required_h2=["Intro"],
        required_outline=[{"title": "Intro"}],
        expand_outline=True,
        config={"k": 1},
    )

    assert payload == {
        "instruction": "write",
        "current_text": "old",
        "required_h2": ["Intro"],
        "required_outline": [{"title": "Intro"}],
        "expand_outline": True,
        "config": {"k": 1},
    }



def test_build_route_graph_kwargs_keeps_workflow_backend_inputs() -> None:
    payload = build_route_graph_kwargs(
        instruction="write",
        current_text="old",
        required_h2=["Intro"],
        required_outline=[{"title": "Intro"}],
        expand_outline=True,
        config={"k": 1},
        compose_mode="continue",
        resume_sections=["Intro"],
        format_only=False,
        plan_confirm={"confirmed": True},
    )

    assert payload == {
        "instruction": "write",
        "current_text": "old",
        "required_h2": ["Intro"],
        "required_outline": [{"title": "Intro"}],
        "expand_outline": True,
        "config": {"k": 1},
        "compose_mode": "continue",
        "resume_sections": ["Intro"],
        "format_only": False,
        "plan_confirm": {"confirmed": True},
    }



def test_prepare_generate_legacy_event_observation_tracks_prompt_route() -> None:
    prompt_trace: list[dict[str, object]] = []

    observation = prepare_generate_legacy_event_observation(
        {"event": "prompt_route", "stage": "writer", "metadata": {"policy": "legacy"}},
        prompt_trace=prompt_trace,
    )

    assert prompt_trace == [{"stage": "writer", "metadata": {"policy": "legacy"}}]
    assert observation == {
        "skip_event": True,
        "is_final": False,
        "final_text": "",
        "problems": [],
        "terminal_status": "success",
        "failure_reason": "",
        "quality_snapshot": {},
    }



def test_prepare_generate_legacy_event_observation_parses_final_semantic_failure() -> None:
    prompt_trace: list[dict[str, object]] = []

    observation = prepare_generate_legacy_event_observation(
        {
            "event": "final",
            "text": "",
            "problems": [],
            "status": "failed",
            "failure_reason": "analysis_needs_clarification",
            "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
        },
        prompt_trace=prompt_trace,
    )

    assert prompt_trace == []
    assert observation == {
        "skip_event": False,
        "is_final": True,
        "final_text": "",
        "problems": ["analysis_needs_clarification"],
        "terminal_status": "failed",
        "failure_reason": "analysis_needs_clarification",
        "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
    }



def test_prepare_generate_route_graph_outcome_builds_success_payload() -> None:
    outcome = prepare_generate_route_graph_outcome(
        {
            "text": "draft",
            "problems": ["warn"],
            "trace_id": "trace-1",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
            "terminal_status": "success",
            "plan_feedback": {"decision": "accepted"},
            "prompt_trace": [{"stage": "planner", "metadata": {"route": "resume_sections"}}],
        }
    )

    assert outcome == {
        "final_text": "draft",
        "problems": ["warn"],
        "terminal_status": "success",
        "failure_reason": "",
        "quality_snapshot": {},
        "prompt_trace": [{"stage": "planner", "metadata": {"route": "resume_sections"}}],
        "graph_meta": {
            "path": "route_graph",
            "trace_id": "trace-1",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
            "plan_feedback": {"decision": "accepted"},
        },
        "record_success_metric": True,
    }



def test_prepare_generate_route_graph_outcome_propagates_semantic_failure_reason() -> None:
    outcome = prepare_generate_route_graph_outcome(
        {
            "text": "",
            "problems": [],
            "trace_id": "trace-2",
            "engine": "native",
            "route_id": "compose_mode",
            "route_entry": "planner",
            "terminal_status": "failed",
            "failure_reason": "analysis_needs_clarification",
            "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
            "prompt_trace": [{"stage": "planner", "metadata": {"decision": "blocked"}}],
        }
    )

    assert outcome == {
        "final_text": "",
        "problems": ["analysis_needs_clarification"],
        "terminal_status": "failed",
        "failure_reason": "analysis_needs_clarification",
        "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
        "prompt_trace": [{"stage": "planner", "metadata": {"decision": "blocked"}}],
        "graph_meta": {
            "path": "route_graph",
            "trace_id": "trace-2",
            "engine": "native",
            "route_id": "compose_mode",
            "route_entry": "planner",
            "plan_feedback": {},
        },
        "record_success_metric": False,
    }



def test_build_route_graph_meta_and_prompt_trace_normalization() -> None:
    result = {
        "trace_id": "trace-1",
        "engine": "native",
        "route_id": "resume_sections",
        "route_entry": "writer",
        "terminal_status": "interrupted",
        "failure_reason": "needs_review",
        "quality_snapshot": {"status": "interrupted"},
        "plan_feedback": {"decision": "accepted"},
        "prompt_trace": [
            {"stage": "planner", "metadata": {"route": "resume_sections"}},
            "skip-me",
        ],
    }

    meta = build_route_graph_meta(result, include_plan_feedback=True, include_terminal_state=True)
    trace = normalize_prompt_trace(result["prompt_trace"])
    attach_prompt_trace(meta, trace)

    assert meta["path"] == "route_graph"
    assert meta["trace_id"] == "trace-1"
    assert meta["plan_feedback"] == {"decision": "accepted"}
    assert meta["terminal_status"] == "interrupted"
    assert meta["failure_reason"] == "needs_review"
    assert meta["quality_snapshot"] == {"status": "interrupted"}
    assert meta["prompt_trace"] == [{"stage": "planner", "metadata": {"route": "resume_sections"}}]



def test_prepare_stream_route_graph_outcome_plan_builds_success_plan() -> None:
    route_metric_meta = {"route_id": "", "route_entry": "", "engine": ""}

    plan = prepare_stream_route_graph_outcome_plan(
        {
            "text": " draft text ",
            "problems": ["warn"],
            "trace_id": "trace-1",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
            "terminal_status": "success",
        },
        session=object(),
        raw_instruction="write",
        current_text="seed",
        route_metric_meta=route_metric_meta,
        postprocess_output_text_fn=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        safe_doc_ir_payload_fn=lambda text: {"text": text},
    )

    assert plan == {
        "action": "emit_success",
        "payload": {
            "text": "DRAFT TEXT",
            "problems": ["warn"],
            "doc_ir": {"text": "DRAFT TEXT"},
            "graph_meta": {
                "path": "route_graph",
                "trace_id": "trace-1",
                "engine": "native",
                "route_id": "resume_sections",
                "route_entry": "writer",
                "plan_feedback": {},
                "terminal_status": "success",
                "failure_reason": "",
                "quality_snapshot": {},
            },
        },
        "final_text": "DRAFT TEXT",
        "skip_insufficient_failover": False,
        "metric_event": "route_graph_success",
        "with_terminal": True,
        "with_reason_codes": False,
        "stop": False,
    }
    assert route_metric_meta == {
        "route_id": "resume_sections",
        "route_entry": "writer",
        "engine": "native",
    }



def test_prepare_stream_route_graph_outcome_plan_builds_semantic_stop_plan() -> None:
    route_metric_meta = {"route_id": "", "route_entry": "", "engine": ""}

    plan = prepare_stream_route_graph_outcome_plan(
        {
            "text": "",
            "problems": ["analysis_needs_clarification"],
            "trace_id": "trace-2",
            "engine": "native",
            "route_id": "compose_mode",
            "route_entry": "planner",
            "terminal_status": "failed",
            "failure_reason": "analysis_needs_clarification",
            "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
        },
        session=object(),
        raw_instruction="write",
        current_text="seed",
        route_metric_meta=route_metric_meta,
        postprocess_output_text_fn=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        safe_doc_ir_payload_fn=lambda text: {"text": text},
    )

    assert plan == {
        "action": "emit_semantic_failure",
        "payload": {
            "text": "",
            "problems": ["analysis_needs_clarification"],
            "doc_ir": {"text": ""},
            "graph_meta": {
                "path": "route_graph",
                "trace_id": "trace-2",
                "engine": "native",
                "route_id": "compose_mode",
                "route_entry": "planner",
                "plan_feedback": {},
                "terminal_status": "failed",
                "failure_reason": "analysis_needs_clarification",
                "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
            },
            "status": "failed",
            "failure_reason": "analysis_needs_clarification",
            "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
        },
        "final_text": None,
        "skip_insufficient_failover": True,
        "metric_event": "route_graph_semantic_failed",
        "with_terminal": True,
        "with_reason_codes": True,
        "stop": True,
    }
    assert route_metric_meta == {
        "route_id": "compose_mode",
        "route_entry": "planner",
        "engine": "native",
    }



def test_prepare_stream_route_graph_outcome_plan_returns_continue_for_nonterminal_short_result() -> None:
    route_metric_meta = {"route_id": "", "route_entry": "", "engine": ""}

    plan = prepare_stream_route_graph_outcome_plan(
        {
            "text": "",
            "problems": [],
            "trace_id": "trace-3",
            "engine": "native",
            "route_id": "compose_mode",
            "route_entry": "writer",
            "terminal_status": "success",
            "failure_reason": "",
        },
        session=object(),
        raw_instruction="write",
        current_text="seed",
        route_metric_meta=route_metric_meta,
        postprocess_output_text_fn=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        safe_doc_ir_payload_fn=lambda text: {"text": text},
    )

    assert plan == {
        "action": "continue",
        "payload": None,
        "final_text": None,
        "skip_insufficient_failover": False,
        "metric_event": "",
        "with_terminal": False,
        "with_reason_codes": False,
        "stop": False,
    }
    assert route_metric_meta == {"route_id": "", "route_entry": "", "engine": ""}



def test_prepare_stream_route_graph_terminal_payload_builds_success_payload() -> None:
    route_metric_meta = {"route_id": "", "route_entry": "", "engine": ""}

    payload = prepare_stream_route_graph_terminal_payload(
        {
            "trace_id": "trace-1",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
            "terminal_status": "success",
            "plan_feedback": {"decision": "accepted"},
            "prompt_trace": [
                {"stage": "planner", "metadata": {"route": "resume_sections"}},
                "skip-me",
            ],
        },
        route_metric_meta=route_metric_meta,
        safe_doc_ir_payload_fn=lambda text: {"text": text},
        text="FINAL",
        problems=["warn"],
    )

    assert payload == {
        "text": "FINAL",
        "problems": ["warn"],
        "doc_ir": {"text": "FINAL"},
        "graph_meta": {
            "path": "route_graph",
            "trace_id": "trace-1",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
            "plan_feedback": {"decision": "accepted"},
            "terminal_status": "success",
            "failure_reason": "",
            "quality_snapshot": {},
            "prompt_trace": [{"stage": "planner", "metadata": {"route": "resume_sections"}}],
        },
    }
    assert route_metric_meta == {
        "route_id": "resume_sections",
        "route_entry": "writer",
        "engine": "native",
    }



def test_prepare_stream_route_graph_terminal_payload_builds_semantic_failure_payload() -> None:
    route_metric_meta = {"route_id": "", "route_entry": "", "engine": ""}

    payload = prepare_stream_route_graph_terminal_payload(
        {
            "trace_id": "trace-2",
            "engine": "native",
            "route_id": "compose_mode",
            "route_entry": "planner",
            "terminal_status": "failed",
            "failure_reason": "analysis_needs_clarification",
            "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
            "prompt_trace": [
                {"stage": "planner", "metadata": {"decision": "blocked"}},
                "skip-me",
            ],
        },
        route_metric_meta=route_metric_meta,
        safe_doc_ir_payload_fn=lambda text: {"text": text},
        text="",
        problems=["analysis_needs_clarification"],
        status="failed",
        failure_reason="analysis_needs_clarification",
        quality_snapshot={"status": "failed", "reason": "analysis_needs_clarification"},
    )

    assert payload == {
        "text": "",
        "problems": ["analysis_needs_clarification"],
        "doc_ir": {"text": ""},
        "graph_meta": {
            "path": "route_graph",
            "trace_id": "trace-2",
            "engine": "native",
            "route_id": "compose_mode",
            "route_entry": "planner",
            "plan_feedback": {},
            "terminal_status": "failed",
            "failure_reason": "analysis_needs_clarification",
            "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
            "prompt_trace": [{"stage": "planner", "metadata": {"decision": "blocked"}}],
        },
        "status": "failed",
        "failure_reason": "analysis_needs_clarification",
        "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
    }
    assert route_metric_meta == {
        "route_id": "compose_mode",
        "route_entry": "planner",
        "engine": "native",
    }



def test_prepare_stream_legacy_event_observation_tracks_prompt_route_and_gap() -> None:
    prompt_trace: list[dict[str, object]] = []
    ticks = iter([8.0])

    result = prepare_stream_legacy_event_observation(
        {"event": "prompt_route", "stage": "writer", "metadata": {"policy": "legacy"}},
        prompt_trace=prompt_trace,
        last_event_at=5.0,
        last_section_at=None,
        max_gap_s=1.0,
        section_stall_s=30.0,
        now_fn=lambda: next(ticks),
    )

    assert prompt_trace == [{"stage": "writer", "metadata": {"policy": "legacy"}}]
    assert result == {
        "event_name": "prompt_route",
        "skip_event": True,
        "section_timeout": False,
        "last_event_at": 8.0,
        "last_section_at": None,
        "max_gap_s": 3.0,
    }



def test_prepare_stream_legacy_event_observation_updates_section_timestamp() -> None:
    prompt_trace: list[dict[str, object]] = []
    ticks = iter([10.0, 10.5, 10.6])

    result = prepare_stream_legacy_event_observation(
        {"event": "section", "phase": "delta", "delta": "draft"},
        prompt_trace=prompt_trace,
        last_event_at=8.0,
        last_section_at=None,
        max_gap_s=1.0,
        section_stall_s=5.0,
        now_fn=lambda: next(ticks),
    )

    assert prompt_trace == []
    assert result == {
        "event_name": "section",
        "skip_event": False,
        "section_timeout": False,
        "last_event_at": 10.0,
        "last_section_at": 10.5,
        "max_gap_s": 2.0,
    }



def test_prepare_stream_legacy_event_observation_detects_section_stall() -> None:
    prompt_trace: list[dict[str, object]] = []
    ticks = iter([12.0, 12.0])

    result = prepare_stream_legacy_event_observation(
        {"event": "delta", "delta": "tick"},
        prompt_trace=prompt_trace,
        last_event_at=10.0,
        last_section_at=1.0,
        max_gap_s=1.0,
        section_stall_s=5.0,
        now_fn=lambda: next(ticks),
    )

    assert prompt_trace == []
    assert result == {
        "event_name": "delta",
        "skip_event": False,
        "section_timeout": True,
        "last_event_at": 12.0,
        "last_section_at": 1.0,
        "max_gap_s": 2.0,
    }



def test_prepare_stream_legacy_terminal_payload_builds_legacy_payload() -> None:
    route_metric_meta = {"route_id": "", "route_entry": "", "engine": ""}

    payload = prepare_stream_legacy_terminal_payload(
        {"event": "final", "text": "draft", "problems": ["warn"]},
        route_metric_meta=route_metric_meta,
        safe_doc_ir_payload_fn=lambda text: {"text": text},
        text="FINAL",
        prompt_trace=[{"stage": "writer", "metadata": {"policy": "legacy"}}],
    )

    assert payload == {
        "event": "final",
        "text": "FINAL",
        "problems": ["warn"],
        "doc_ir": {"text": "FINAL"},
        "graph_meta": {
            "path": "legacy_graph",
            "trace_id": "",
            "engine": "legacy",
            "route_id": "",
            "route_entry": "",
            "prompt_trace": [{"stage": "writer", "metadata": {"policy": "legacy"}}],
        },
    }
    assert route_metric_meta == {
        "route_id": "",
        "route_entry": "",
        "engine": "legacy",
    }



def test_build_legacy_graph_meta_uses_legacy_defaults() -> None:
    meta = build_legacy_graph_meta(prompt_trace=[{"stage": "writer", "metadata": {}}])

    assert meta == {
        "path": "legacy_graph",
        "trace_id": "",
        "engine": "legacy",
        "route_id": "",
        "route_entry": "",
        "prompt_trace": [{"stage": "writer", "metadata": {}}],
    }



def test_build_failover_quality_snapshot_marks_review() -> None:
    snapshot = build_failover_quality_snapshot(
        terminal_status="interrupted",
        failure_reason="engine_failover_graph_failed",
        problem_count=2,
    )

    assert snapshot == {
        "status": "interrupted",
        "reason": "engine_failover_graph_failed",
        "problem_count": 2,
        "needs_review": True,
    }



def test_finalize_graph_meta_applies_terminal_fields_and_trace() -> None:
    meta = finalize_graph_meta(
        {"path": "route_graph", "engine": "native"},
        terminal_status="interrupted",
        failure_reason="engine_failover_insufficient_output",
        quality_snapshot={"status": "interrupted"},
        engine_failover=True,
        prompt_trace=[{"stage": "planner", "metadata": {}}],
    )

    assert meta["path"] == "route_graph"
    assert meta["engine"] == "native"
    assert meta["terminal_status"] == "interrupted"
    assert meta["failure_reason"] == "engine_failover_insufficient_output"
    assert meta["quality_snapshot"] == {"status": "interrupted"}
    assert meta["engine_failover"] is True
    assert meta["needs_review"] is True
    assert meta["prompt_trace"] == [{"stage": "planner", "metadata": {}}]



def test_build_single_pass_failover_meta_uses_single_pass_defaults() -> None:
    meta = build_single_pass_failover_meta(prompt_trace=[{"stage": "writer", "metadata": {}}])

    assert meta == {
        "path": "single_pass_stream",
        "trace_id": "",
        "engine": "single_pass",
        "route_id": "",
        "route_entry": "",
        "engine_failover": True,
        "terminal_status": "interrupted",
        "needs_review": True,
        "prompt_trace": [{"stage": "writer", "metadata": {}}],
    }



def test_sync_route_metric_meta_updates_route_identifiers() -> None:
    payload = {"route_id": "resume_sections", "route_entry": "writer", "engine": "native"}
    target = {"route_id": "", "route_entry": "", "engine": ""}

    sync_route_metric_meta(target, payload)

    assert target == {"route_id": "resume_sections", "route_entry": "writer", "engine": "native"}



def test_sync_trace_context_preserves_existing_trigger_when_requested() -> None:
    trace = {"route_path": "", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": False}

    sync_trace_context(trace, route_path="single_pass_stream", fallback_recovered=True)
    sync_trace_context(
        trace,
        fallback_trigger="E_TEXT_INSUFFICIENT",
        fallback_recovered=False,
        preserve_existing_trigger=True,
    )

    assert trace == {
        "route_path": "single_pass_stream",
        "fallback_trigger": "E_GRAPH_FAILED",
        "fallback_recovered": False,
    }



def test_record_orchestration_metric_builds_expected_payload() -> None:
    captured: list[tuple[str, dict]] = []

    def _recorder(event, **kwargs):
        captured.append((event, dict(kwargs)))

    record_orchestration_metric(
        _recorder,
        event="route_graph_success",
        phase="generate",
        path="route_graph",
        meta={"route_id": "resume_sections", "route_entry": "writer", "engine": "native"},
        fallback_triggered=False,
        fallback_recovered=False,
        error_code="",
        elapsed_ms=12.5,
        compose_mode="continue",
        resume_sections=["Intro"],
    )

    assert captured == [
        (
            "route_graph_success",
            {
                "phase": "generate",
                "path": "route_graph",
                "route_id": "resume_sections",
                "route_entry": "writer",
                "engine": "native",
                "fallback_triggered": False,
                "fallback_recovered": False,
                "error_code": "",
                "elapsed_ms": 12.5,
                "extra": build_route_metric_extra(compose_mode="continue", resume_sections=["Intro"]),
            },
        )
    ]



def test_should_skip_semantic_failover_matches_known_reason_set() -> None:
    assert should_skip_semantic_failover(
        terminal_status="failed",
        failure_reason="analysis_needs_clarification",
    ) is True
    assert should_skip_semantic_failover(
        terminal_status="success",
        failure_reason="analysis_needs_clarification",
    ) is False
    assert should_skip_semantic_failover(
        terminal_status="failed",
        failure_reason="other_reason",
    ) is False



def test_text_requires_failover_uses_trimmed_min_chars_threshold() -> None:
    assert text_requires_failover("   short   ", min_chars=20) is True
    assert text_requires_failover("x" * 20, min_chars=20) is False
    assert text_requires_failover(None, min_chars=1) is True



def test_prepare_single_pass_stream_recovery_result_builds_terminal_payload() -> None:
    result = prepare_single_pass_stream_recovery_result(
        raw_text=" draft text ",
        session=object(),
        raw_instruction="write intro",
        current_text="current",
        target_chars=120,
        prompt_trace=[{"stage": "writer", "metadata": {}}],
        postprocess_output_text_fn=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        check_generation_quality_fn=lambda text, _target: [f"len={len(text)}"],
        safe_doc_ir_payload_fn=lambda text: {"text": text},
    )

    assert result["final_text"] == "DRAFT TEXT"
    assert result["quality_issues"] == ["len=10"]
    assert result["graph_meta"]["path"] == "single_pass_stream"
    assert result["graph_meta"]["engine_failover"] is True
    assert result["section_payload"] == {"section": "fallback", "phase": "delta", "delta": "DRAFT TEXT"}
    assert result["final_payload"] == {
        "text": "DRAFT TEXT",
        "problems": ["len=10"],
        "doc_ir": {"text": "DRAFT TEXT"},
        "graph_meta": result["graph_meta"],
    }

def test_prepare_single_pass_stream_recovery_emission_plan_adds_terminal_and_missing_section() -> None:
    plan = prepare_single_pass_stream_recovery_emission_plan(
        {
            "emit_events": [{"event": "delta", "payload": {"delta": "tick"}}],
            "saw_stream_delta": False,
            "final_text": "FINAL TEXT",
            "recovery": {
                "section_payload": {"section": "fallback", "phase": "delta", "delta": "FINAL TEXT"},
                "final_payload": {"text": "FINAL TEXT", "doc_ir": {"text": "FINAL TEXT"}, "problems": []},
            },
        },
    )

    assert plan == {
        "passthrough_events": [
            {"event": "delta", "payload": {"delta": "tick"}},
        ],
        "completion_events": [
            {"event": "section", "payload": {"section": "fallback", "phase": "delta", "delta": "FINAL TEXT"}},
            {"event": "final", "payload": {"text": "FINAL TEXT", "doc_ir": {"text": "FINAL TEXT"}, "problems": []}},
        ],
        "emit_events": [
            {"event": "delta", "payload": {"delta": "tick"}},
            {"event": "section", "payload": {"section": "fallback", "phase": "delta", "delta": "FINAL TEXT"}},
            {"event": "final", "payload": {"text": "FINAL TEXT", "doc_ir": {"text": "FINAL TEXT"}, "problems": []}},
        ],
        "final_text": "FINAL TEXT",
        "recovered": True,
    }








def test_resolve_stream_graph_path_maps_route_flag() -> None:
    assert resolve_stream_graph_path(use_route_graph=True) == "route_graph"
    assert resolve_stream_graph_path(use_route_graph=False) == "legacy_graph"



def test_prepare_stream_fallback_trigger_dispatches_graph_failed() -> None:
    trace_context = {"route_path": "route_graph", "fallback_trigger": "", "fallback_recovered": True}
    truncate_reason_codes: set[str] = set()
    metrics: list[tuple[str, dict]] = []

    result = prepare_stream_fallback_trigger(
        kind="graph_failed",
        use_route_graph=False,
        exc=TimeoutError("section stalled"),
        trace_context=trace_context,
        truncate_reason_codes=truncate_reason_codes,
        record_route_metric_fn=lambda event, **kwargs: metrics.append((event, dict(kwargs))),
        extract_error_code_fn=lambda exc, default="": default,
    )

    assert trace_context == {"route_path": "route_graph", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": False}
    assert truncate_reason_codes == {"timeout_fallback"}
    assert metrics == [(
        "graph_failed",
        {
            "path": "legacy_graph",
            "fallback_triggered": True,
            "fallback_recovered": False,
            "error_code": "E_GRAPH_FAILED",
        },
    )]
    assert result == {
        "fallback_trigger": "E_GRAPH_FAILED",
        "metric_payload": {
            "event": "graph_failed",
            "kwargs": {
                "path": "legacy_graph",
                "fallback_triggered": True,
                "fallback_recovered": False,
                "error_code": "E_GRAPH_FAILED",
            },
        },
        "truncate_reason_codes": ["timeout_fallback"],
    }



def test_prepare_stream_fallback_trigger_dispatches_graph_insufficient() -> None:
    trace_context = {"route_path": "route_graph", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": True}
    truncate_reason_codes: set[str] = set()
    metrics: list[tuple[str, dict]] = []

    result = prepare_stream_fallback_trigger(
        kind="graph_insufficient",
        use_route_graph=True,
        trace_context=trace_context,
        truncate_reason_codes=truncate_reason_codes,
        record_route_metric_fn=lambda event, **kwargs: metrics.append((event, dict(kwargs))),
    )

    assert trace_context == {"route_path": "route_graph", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": False}
    assert truncate_reason_codes == {"insufficient_output_fallback"}
    assert metrics == [(
        "graph_insufficient",
        {
            "path": "route_graph",
            "fallback_triggered": True,
            "fallback_recovered": False,
            "error_code": "E_TEXT_INSUFFICIENT",
        },
    )]
    assert result == {
        "fallback_trigger": "E_TEXT_INSUFFICIENT",
        "metric_payload": {
            "event": "graph_insufficient",
            "kwargs": {
                "path": "route_graph",
                "fallback_triggered": True,
                "fallback_recovered": False,
                "error_code": "E_TEXT_INSUFFICIENT",
            },
        },
        "truncate_reason_codes": ["insufficient_output_fallback"],
    }



def test_prepare_stream_graph_failure_fallback_trigger_sets_timeout_reason_and_metric() -> None:
    trace_context = {"route_path": "route_graph", "fallback_trigger": "", "fallback_recovered": True}
    truncate_reason_codes: set[str] = set()
    metrics: list[tuple[str, dict]] = []

    result = prepare_stream_graph_failure_fallback_trigger(
        exc=TimeoutError("section stalled"),
        trace_context=trace_context,
        truncate_reason_codes=truncate_reason_codes,
        record_route_metric_fn=lambda event, **kwargs: metrics.append((event, dict(kwargs))),
        extract_error_code_fn=lambda exc, default="": default,
        graph_path="route_graph",
    )

    assert trace_context == {"route_path": "route_graph", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": False}
    assert truncate_reason_codes == {"timeout_fallback"}
    assert metrics == [(
        "graph_failed",
        {
            "path": "route_graph",
            "fallback_triggered": True,
            "fallback_recovered": False,
            "error_code": "E_GRAPH_FAILED",
        },
    )]
    assert result == {
        "fallback_trigger": "E_GRAPH_FAILED",
        "metric_payload": {
            "event": "graph_failed",
            "kwargs": {
                "path": "route_graph",
                "fallback_triggered": True,
                "fallback_recovered": False,
                "error_code": "E_GRAPH_FAILED",
            },
        },
        "truncate_reason_codes": ["timeout_fallback"],
    }


def test_prepare_stream_insufficient_fallback_trigger_preserves_existing_trigger() -> None:
    trace_context = {"route_path": "route_graph", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": True}
    truncate_reason_codes: set[str] = set()
    metrics: list[tuple[str, dict]] = []

    result = prepare_stream_insufficient_fallback_trigger(
        trace_context=trace_context,
        truncate_reason_codes=truncate_reason_codes,
        record_route_metric_fn=lambda event, **kwargs: metrics.append((event, dict(kwargs))),
        graph_path="legacy_graph",
    )

    assert trace_context == {"route_path": "route_graph", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": False}
    assert truncate_reason_codes == {"insufficient_output_fallback"}
    assert metrics == [(
        "graph_insufficient",
        {
            "path": "legacy_graph",
            "fallback_triggered": True,
            "fallback_recovered": False,
            "error_code": "E_TEXT_INSUFFICIENT",
        },
    )]
    assert result == {
        "fallback_trigger": "E_TEXT_INSUFFICIENT",
        "metric_payload": {
            "event": "graph_insufficient",
            "kwargs": {
                "path": "legacy_graph",
                "fallback_triggered": True,
                "fallback_recovered": False,
                "error_code": "E_TEXT_INSUFFICIENT",
            },
        },
        "truncate_reason_codes": ["insufficient_output_fallback"],
    }


def test_drive_single_pass_stream_recovery_returns_success_plan() -> None:
    result = drive_single_pass_stream_recovery(
        attempt_fn=lambda: {"k": 1},
        finalize_success_fn=lambda payload: {
            "emit_events": [{"event": "final", "payload": {"text": str(payload["k"])}}],
            "timing_payload": {"total_s": 1.0, "max_gap_s": 0.5},
            "metric_payload": {"event": "fallback_recovered", "kwargs": {"path": "single_pass_stream"}},
            "final_text": "done",
            "recovered": True,
        },
        handle_failure_fn=lambda exc: {"event": "error", "payload": {"message": str(exc)}, "stop": True},
    )

    assert result == {
        "emit_events": [{"event": "final", "payload": {"text": "1"}}],
        "timing_payload": {"total_s": 1.0, "max_gap_s": 0.5},
        "metric_payload": {"event": "fallback_recovered", "kwargs": {"path": "single_pass_stream"}},
        "final_text": "done",
        "recovered": True,
        "failure": None,
        "stop": False,
    }


def test_drive_single_pass_stream_recovery_maps_failure_plan() -> None:
    result = drive_single_pass_stream_recovery(
        attempt_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        finalize_success_fn=lambda payload: payload,
        handle_failure_fn=lambda exc: {"event": "error", "payload": {"message": str(exc)}, "stop": True},
    )

    assert result == {
        "emit_events": [{"event": "error", "payload": {"message": "boom"}}],
        "timing_payload": None,
        "metric_payload": None,
        "final_text": None,
        "recovered": False,
        "failure": {"event": "error", "payload": {"message": "boom"}, "stop": True},
        "stop": True,
    }


def test_prepare_single_pass_stream_recovery_success_plan_syncs_trace_and_wraps_final() -> None:
    trace_context = {"route_path": "route_graph", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": False}

    result = prepare_single_pass_stream_recovery_success_plan(
        {
            "passthrough_events": [{"event": "delta", "payload": {"delta": "tick"}}],
            "completion_events": [
                {"event": "section", "payload": {"section": "fallback", "phase": "delta", "delta": "FINAL TEXT"}},
                {"event": "final", "payload": {"text": "FINAL TEXT", "doc_ir": {"text": "FINAL TEXT"}, "problems": []}},
            ],
            "final_text": "FINAL TEXT",
            "recovered": True,
        },
        trace_context=trace_context,
        with_terminal_fn=lambda payload: {**dict(payload), "terminal": True, "trace_route": trace_context.get("route_path")},
        total_s=3.5,
        max_gap_s=1.25,
    )

    assert trace_context == {"route_path": "single_pass_stream", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": True}
    assert result == {
        "emit_events": [
            {"event": "delta", "payload": {"delta": "tick"}},
            {"event": "section", "payload": {"section": "fallback", "phase": "delta", "delta": "FINAL TEXT"}},
            {"event": "final", "payload": {"text": "FINAL TEXT", "doc_ir": {"text": "FINAL TEXT"}, "problems": [], "terminal": True, "trace_route": "single_pass_stream"}},
        ],
        "passthrough_events": [
            {"event": "delta", "payload": {"delta": "tick"}},
        ],
        "completion_events": [
            {"event": "section", "payload": {"section": "fallback", "phase": "delta", "delta": "FINAL TEXT"}},
            {"event": "final", "payload": {"text": "FINAL TEXT", "doc_ir": {"text": "FINAL TEXT"}, "problems": [], "terminal": True, "trace_route": "single_pass_stream"}},
        ],
        "timing_payload": {"total_s": 3.5, "max_gap_s": 1.25},
        "metric_payload": {
            "event": "fallback_recovered",
            "kwargs": {"path": "single_pass_stream", "fallback_triggered": True, "fallback_recovered": True},
        },
        "final_text": "FINAL TEXT",
        "recovered": True,
    }


def test_handle_single_pass_stream_recovery_failure_records_trace_metric_and_error_event() -> None:
    trace_context = {"route_path": "route_graph", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": True}
    metrics: list[tuple[str, dict]] = []

    result = handle_single_pass_stream_recovery_failure(
        exc=RuntimeError("boom"),
        trace_context=trace_context,
        record_route_metric_fn=lambda event, **kwargs: metrics.append((event, dict(kwargs))),
        extract_error_code_fn=lambda exc, default="": f"ERR_{type(exc).__name__.upper()}" if exc else default,
        error_message="fallback exploded",
        stop=True,
    )

    assert trace_context == {"route_path": "route_graph", "fallback_trigger": "E_GRAPH_FAILED", "fallback_recovered": False}
    assert metrics == [(
        "fallback_failed",
        {
            "path": "single_pass_stream",
            "fallback_triggered": True,
            "fallback_recovered": False,
            "error_code": "ERR_RUNTIMEERROR",
        },
    )]
    assert result == {
        "event": "error",
        "payload": {"message": "fallback exploded"},
        "stop": True,
        "error_code": "ERR_RUNTIMEERROR",
    }



def test_run_single_pass_stream_recovery_collects_passthrough_events_and_recovery() -> None:
    result = run_single_pass_stream_recovery(
        stream=[
            {"event": "heartbeat", "message": "tick"},
            {"event": "section", "section": "Body", "phase": "delta", "delta": "draft"},
            {"event": "result", "text": " final text "},
        ],
        session=object(),
        raw_instruction="write body",
        current_text="current",
        target_chars=200,
        prompt_trace=[{"stage": "writer", "metadata": {}}],
        postprocess_output_text_fn=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        check_generation_quality_fn=lambda text, _target: [f"len={len(text)}"],
        safe_doc_ir_payload_fn=lambda text: {"text": text},
    )

    assert result["emit_events"] == [
        {"event": "delta", "payload": {"delta": "tick"}},
        {"event": "section", "payload": {"event": "section", "section": "Body", "phase": "delta", "delta": "draft"}},
    ]
    assert result["saw_stream_delta"] is True
    assert result["raw_final_text"] == " final text "
    assert result["final_text"] == "FINAL TEXT"
    assert result["recovery"]["final_payload"]["graph_meta"]["path"] == "single_pass_stream"


def test_run_single_pass_stream_recovery_handles_empty_result_without_recovery() -> None:
    result = run_single_pass_stream_recovery(
        stream=[{"event": "heartbeat", "message": "tick"}],
        session=object(),
        raw_instruction="write body",
        current_text="current",
        target_chars=200,
        prompt_trace=None,
        postprocess_output_text_fn=lambda _session, text, _instruction, **_kwargs: str(text).strip(),
        check_generation_quality_fn=lambda text, _target: [text],
        safe_doc_ir_payload_fn=lambda text: {"text": text},
    )

    assert result == {
        "emit_events": [{"event": "delta", "payload": {"delta": "tick"}}],
        "saw_stream_delta": False,
        "raw_final_text": None,
        "final_text": None,
        "recovery": None,
    }
