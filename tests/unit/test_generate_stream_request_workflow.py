from __future__ import annotations

from dataclasses import dataclass

from writing_agent.workflows.generate_stream_request_workflow import (
    GenerateStreamDeps,
    GenerateStreamRequest,
    run_generate_stream_graph_with_fallback,
)


@dataclass
class _Session:
    generation_prefs: dict
    template_required_h2: list[str]
    template_outline: list
    doc_text: str


def _drain(gen):
    events = []
    try:
        while True:
            events.append(next(gen))
    except StopIteration as exc:
        return events, exc.value


def test_generate_stream_request_workflow_route_graph_success() -> None:
    metric_rows: list[tuple[str, dict]] = []
    request = GenerateStreamRequest(
        session=_Session(generation_prefs={}, template_required_h2=["Intro"], template_outline=[], doc_text="# Title"),
        raw_instruction="continue intro",
        instruction="continue intro",
        current_text="# Title\n\n## Intro\nold",
        graph_current_text="# Title\n\n## Intro\nold",
        compose_mode="continue",
        resume_sections=["Intro"],
        plan_confirm={},
        cfg=object(),
        target_chars=1200,
        required_h2=["Intro"],
        required_outline=[],
        expand_outline=False,
        stall_s=90.0,
        overall_s=180.0,
        section_stall_s=0.0,
        start_ts=0.0,
        trace_context={"route_path": "", "fallback_trigger": "", "fallback_recovered": False},
        truncate_reason_codes=set(),
        route_metric_meta={"route_id": "", "route_entry": "", "engine": ""},
    )
    deps = GenerateStreamDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
        emit=lambda event, payload: {"event": event, "payload": payload},
        with_terminal=lambda payload: dict(payload),
        with_reason_codes=lambda payload: dict(payload),
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        record_stream_timing=lambda **_kwargs: None,
        extract_error_code=lambda exc, default="": default,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: {
            "text": "# Title\n\n## Intro\nroute graph stream text",
            "problems": [],
            "trace_id": "trace-stream",
            "engine": "native",
            "route_id": "resume_sections",
            "route_entry": "writer",
            "terminal_status": "success",
        },
        run_generate_graph=lambda **_kwargs: iter(()),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        postprocess_output_text=lambda _session, text, _instruction, **_kwargs: text,
        safe_doc_ir_payload=lambda text: {"text": text},
        single_pass_generate_stream=lambda *_args, **_kwargs: iter(()),
        check_generation_quality=lambda _text, _target: [],
        log_graph_error=lambda _exc: None,
    )

    events, result = _drain(run_generate_stream_graph_with_fallback(request=request, deps=deps))
    assert len(events) == 1
    assert events[0]["event"] == "final"
    meta = events[0]["payload"].get("graph_meta") or {}
    assert meta.get("path") == "route_graph"
    assert meta.get("route_id") == "resume_sections"
    assert result["final_text"] == "# Title\n\n## Intro\nroute graph stream text"
    assert any(row[0] == "route_graph_success" for row in metric_rows)
    assert request.route_metric_meta.get("route_id") == "resume_sections"


def test_generate_stream_request_workflow_legacy_graph_final_preserves_prompt_trace() -> None:
    metric_rows: list[tuple[str, dict]] = []
    timing_rows: list[dict] = []
    request = GenerateStreamRequest(
        session=_Session(generation_prefs={}, template_required_h2=[], template_outline=[], doc_text=""),
        raw_instruction="write legacy",
        instruction="write legacy",
        current_text="seed",
        graph_current_text="seed",
        compose_mode="auto",
        resume_sections=[],
        plan_confirm={},
        cfg=object(),
        target_chars=600,
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        stall_s=90.0,
        overall_s=180.0,
        section_stall_s=0.0,
        start_ts=0.0,
        trace_context={"route_path": "", "fallback_trigger": "", "fallback_recovered": False},
        truncate_reason_codes=set(),
        route_metric_meta={"route_id": "seed", "route_entry": "seed", "engine": "seed"},
    )
    deps = GenerateStreamDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "0"},
        emit=lambda event, payload: {"event": event, "payload": payload},
        with_terminal=lambda payload: {**dict(payload), "terminal": True},
        with_reason_codes=lambda payload: dict(payload),
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        record_stream_timing=lambda **kwargs: timing_rows.append(dict(kwargs)),
        extract_error_code=lambda exc, default="": default,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('dual engine should not run when route graph is disabled')),
        run_generate_graph=lambda **_kwargs: iter([
            {"event": "prompt_route", "stage": "writer", "metadata": {"policy": "legacy"}},
            {"event": "final", "text": " legacy output content long enough ", "problems": ["warn"]},
        ]),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        postprocess_output_text=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        safe_doc_ir_payload=lambda text: {"text": text},
        single_pass_generate_stream=lambda *_args, **_kwargs: iter(()),
        check_generation_quality=lambda _text, _target: [],
        log_graph_error=lambda _exc: None,
    )

    events, result = _drain(run_generate_stream_graph_with_fallback(request=request, deps=deps))

    assert [event["event"] for event in events] == ["final"]
    payload = events[0]["payload"]
    assert payload["text"] == "LEGACY OUTPUT CONTENT LONG ENOUGH"
    assert payload["doc_ir"] == {"text": "LEGACY OUTPUT CONTENT LONG ENOUGH"}
    assert payload["graph_meta"] == {
        "path": "legacy_graph",
        "trace_id": "",
        "engine": "legacy",
        "route_id": "",
        "route_entry": "",
        "prompt_trace": [{"stage": "writer", "metadata": {"policy": "legacy"}}],
    }
    assert payload["terminal"] is True
    assert result == {"final_text": "LEGACY OUTPUT CONTENT LONG ENOUGH", "stop": False}
    assert request.trace_context["route_path"] == "legacy_graph"
    assert request.route_metric_meta == {"route_id": "", "route_entry": "", "engine": "legacy"}
    assert any(row[0] == "legacy_graph_success" for row in metric_rows)
    assert len(timing_rows) == 1



def test_generate_stream_request_workflow_semantic_failure_skips_fallback() -> None:
    called = {"single": 0}
    metric_rows: list[tuple[str, dict]] = []
    request = GenerateStreamRequest(
        session=_Session(generation_prefs={}, template_required_h2=[], template_outline=[], doc_text=""),
        raw_instruction="write paper",
        instruction="write paper",
        current_text="",
        graph_current_text="",
        compose_mode="auto",
        resume_sections=[],
        plan_confirm={},
        cfg=object(),
        target_chars=1200,
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        stall_s=90.0,
        overall_s=180.0,
        section_stall_s=0.0,
        start_ts=0.0,
        trace_context={"route_path": "", "fallback_trigger": "", "fallback_recovered": False},
        truncate_reason_codes=set(),
        route_metric_meta={"route_id": "", "route_entry": "", "engine": ""},
    )
    deps = GenerateStreamDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
        emit=lambda event, payload: {"event": event, "payload": payload},
        with_terminal=lambda payload: dict(payload),
        with_reason_codes=lambda payload: dict(payload),
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        record_stream_timing=lambda **_kwargs: None,
        extract_error_code=lambda exc, default="": default,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: {
            "text": "",
            "problems": ["analysis_needs_clarification"],
            "trace_id": "trace-semantic",
            "engine": "native",
            "route_id": "compose_mode",
            "route_entry": "planner",
            "terminal_status": "failed",
            "failure_reason": "analysis_needs_clarification",
            "quality_snapshot": {"status": "failed", "reason": "analysis_needs_clarification"},
            "prompt_trace": [{"stage": "planner", "metadata": {"decision": "blocked"}}],
        },
        run_generate_graph=lambda **_kwargs: iter(()),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        postprocess_output_text=lambda _session, text, _instruction, **_kwargs: text,
        safe_doc_ir_payload=lambda text: {"text": text},
        single_pass_generate_stream=lambda *_args, **_kwargs: called.__setitem__("single", called["single"] + 1) or iter(()),
        check_generation_quality=lambda _text, _target: [],
        log_graph_error=lambda _exc: None,
    )

    events, result = _drain(run_generate_stream_graph_with_fallback(request=request, deps=deps))
    assert len(events) == 1
    assert events[0]["event"] == "final"
    payload = events[0]["payload"]
    assert payload.get("failure_reason") == "analysis_needs_clarification"
    assert payload.get("status") == "failed"
    assert payload.get("graph_meta", {}).get("path") == "route_graph"
    assert payload.get("graph_meta", {}).get("prompt_trace") == [
        {"stage": "planner", "metadata": {"decision": "blocked"}}
    ]
    assert request.route_metric_meta == {
        "route_id": "compose_mode",
        "route_entry": "planner",
        "engine": "native",
    }
    assert metric_rows == [(
        "route_graph_semantic_failed",
        {
            "path": "route_graph",
            "fallback_triggered": False,
            "fallback_recovered": False,
        },
    )]
    assert called["single"] == 0
    assert result["stop"] is True


def test_generate_stream_request_workflow_legacy_graph_failure_recovers_via_single_pass_stream() -> None:
    metric_rows: list[tuple[str, dict]] = []
    timing_rows: list[dict] = []
    request = GenerateStreamRequest(
        session=_Session(generation_prefs={}, template_required_h2=[], template_outline=[], doc_text=""),
        raw_instruction="write fallback",
        instruction="write fallback",
        current_text="seed",
        graph_current_text="seed",
        compose_mode="auto",
        resume_sections=[],
        plan_confirm={},
        cfg=object(),
        target_chars=600,
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        stall_s=90.0,
        overall_s=180.0,
        section_stall_s=0.0,
        start_ts=0.0,
        trace_context={"route_path": "", "fallback_trigger": "", "fallback_recovered": False},
        truncate_reason_codes=set(),
        route_metric_meta={"route_id": "", "route_entry": "", "engine": ""},
    )
    deps = GenerateStreamDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "0"},
        emit=lambda event, payload: {"event": event, "payload": payload},
        with_terminal=lambda payload: {**dict(payload), "terminal": True},
        with_reason_codes=lambda payload: dict(payload),
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        record_stream_timing=lambda **kwargs: timing_rows.append(dict(kwargs)),
        extract_error_code=lambda exc, default="": default,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: {},
        run_generate_graph=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('legacy boom')),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        postprocess_output_text=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        safe_doc_ir_payload=lambda text: {"text": text},
        single_pass_generate_stream=lambda *_args, **_kwargs: iter([
            {"event": "result", "text": " legacy graph fallback recovery content "},
        ]),
        check_generation_quality=lambda _text, _target: [],
        log_graph_error=lambda _exc: None,
    )

    events, result = _drain(run_generate_stream_graph_with_fallback(request=request, deps=deps))

    assert [event["event"] for event in events] == ["section", "final"]
    assert events[0]["payload"] == {
        "section": "fallback",
        "phase": "delta",
        "delta": "LEGACY GRAPH FALLBACK RECOVERY CONTENT",
    }
    assert events[1]["payload"]["text"] == "LEGACY GRAPH FALLBACK RECOVERY CONTENT"
    assert events[1]["payload"]["graph_meta"]["path"] == "single_pass_stream"
    assert result == {"final_text": "LEGACY GRAPH FALLBACK RECOVERY CONTENT", "stop": False}
    assert request.trace_context["route_path"] == "single_pass_stream"
    assert request.trace_context["fallback_trigger"] == "E_GRAPH_FAILED"
    assert request.trace_context["fallback_recovered"] is True
    assert any(row[0] == "graph_failed" and row[1]["path"] == "legacy_graph" for row in metric_rows)
    assert any(row[0] == "fallback_recovered" for row in metric_rows)
    assert len(timing_rows) == 1



def test_generate_stream_request_workflow_graph_failure_recovers_via_single_pass_stream() -> None:
    metric_rows: list[tuple[str, dict]] = []
    timing_rows: list[dict] = []
    request = GenerateStreamRequest(
        session=_Session(generation_prefs={}, template_required_h2=[], template_outline=[], doc_text=""),
        raw_instruction="write fallback",
        instruction="write fallback",
        current_text="seed",
        graph_current_text="seed",
        compose_mode="auto",
        resume_sections=[],
        plan_confirm={},
        cfg=object(),
        target_chars=600,
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        stall_s=90.0,
        overall_s=180.0,
        section_stall_s=0.0,
        start_ts=0.0,
        trace_context={"route_path": "", "fallback_trigger": "", "fallback_recovered": False},
        truncate_reason_codes=set(),
        route_metric_meta={"route_id": "", "route_entry": "", "engine": ""},
    )
    deps = GenerateStreamDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
        emit=lambda event, payload: {"event": event, "payload": payload},
        with_terminal=lambda payload: {**dict(payload), "terminal": True},
        with_reason_codes=lambda payload: dict(payload),
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        record_stream_timing=lambda **kwargs: timing_rows.append(dict(kwargs)),
        extract_error_code=lambda exc, default="": default,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('boom')),
        run_generate_graph=lambda **_kwargs: iter(()),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        postprocess_output_text=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        safe_doc_ir_payload=lambda text: {"text": text},
        single_pass_generate_stream=lambda *_args, **_kwargs: iter([
            {"event": "heartbeat", "message": "tick"},
            {"event": "section", "section": "Body", "phase": "delta", "delta": "draft"},
            {"event": "result", "text": " final fallback draft content "},
        ]),
        check_generation_quality=lambda _text, _target: [],
        log_graph_error=lambda _exc: None,
    )

    events, result = _drain(run_generate_stream_graph_with_fallback(request=request, deps=deps))

    assert [event["event"] for event in events] == ["delta", "section", "final"]
    assert events[0]["payload"] == {"delta": "tick"}
    assert events[1]["payload"] == {"event": "section", "section": "Body", "phase": "delta", "delta": "draft"}
    assert events[2]["payload"]["text"] == "FINAL FALLBACK DRAFT CONTENT"
    assert events[2]["payload"]["graph_meta"]["path"] == "single_pass_stream"
    assert events[2]["payload"]["terminal"] is True
    assert result == {"final_text": "FINAL FALLBACK DRAFT CONTENT", "stop": False}
    assert request.trace_context["route_path"] == "single_pass_stream"
    assert request.trace_context["fallback_recovered"] is True
    assert any(row[0] == "graph_failed" for row in metric_rows)
    assert any(row[0] == "fallback_recovered" for row in metric_rows)
    assert len(timing_rows) == 1


def test_generate_stream_request_workflow_insufficient_output_fallback_failure_stops() -> None:
    metric_rows: list[tuple[str, dict]] = []
    request = GenerateStreamRequest(
        session=_Session(generation_prefs={}, template_required_h2=[], template_outline=[], doc_text=""),
        raw_instruction="write short",
        instruction="write short",
        current_text="seed",
        graph_current_text="seed",
        compose_mode="auto",
        resume_sections=[],
        plan_confirm={},
        cfg=object(),
        target_chars=600,
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        stall_s=90.0,
        overall_s=180.0,
        section_stall_s=0.0,
        start_ts=0.0,
        trace_context={"route_path": "route_graph", "fallback_trigger": "", "fallback_recovered": True},
        truncate_reason_codes=set(),
        route_metric_meta={"route_id": "", "route_entry": "", "engine": ""},
    )
    deps = GenerateStreamDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
        emit=lambda event, payload: {"event": event, "payload": payload},
        with_terminal=lambda payload: {**dict(payload), "terminal": True},
        with_reason_codes=lambda payload: dict(payload),
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        record_stream_timing=lambda **_kwargs: None,
        extract_error_code=lambda exc, default="": f"ERR_{type(exc).__name__.upper()}" if exc else default,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: {
            "text": "too short",
            "problems": [],
            "trace_id": "trace-short",
            "engine": "native",
            "route_id": "compose_mode",
            "route_entry": "writer",
            "terminal_status": "success",
        },
        run_generate_graph=lambda **_kwargs: iter(()),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        postprocess_output_text=lambda _session, text, _instruction, **_kwargs: text,
        safe_doc_ir_payload=lambda text: {"text": text},
        single_pass_generate_stream=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('fallback exploded')),
        check_generation_quality=lambda _text, _target: [],
        log_graph_error=lambda _exc: None,
    )

    events, result = _drain(run_generate_stream_graph_with_fallback(request=request, deps=deps))

    assert [event["event"] for event in events] == ["final", "error"]
    assert events[0]["payload"]["text"] == "too short"
    assert events[1]["payload"] == {"message": "generation failed and fallback failed: fallback exploded"}
    assert result == {"final_text": None, "stop": True}
    assert request.trace_context["fallback_trigger"] == "E_TEXT_INSUFFICIENT"
    assert request.trace_context["fallback_recovered"] is False
    assert any(row[0] == "graph_insufficient" for row in metric_rows)
    assert any(row[0] == "fallback_failed" for row in metric_rows)


def test_generate_stream_request_workflow_insufficient_output_recovers_via_single_pass_stream() -> None:
    metric_rows: list[tuple[str, dict]] = []
    timing_rows: list[dict] = []
    request = GenerateStreamRequest(
        session=_Session(generation_prefs={}, template_required_h2=[], template_outline=[], doc_text=""),
        raw_instruction="write short",
        instruction="write short",
        current_text="seed",
        graph_current_text="seed",
        compose_mode="auto",
        resume_sections=[],
        plan_confirm={},
        cfg=object(),
        target_chars=600,
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        stall_s=90.0,
        overall_s=180.0,
        section_stall_s=0.0,
        start_ts=0.0,
        trace_context={"route_path": "route_graph", "fallback_trigger": "", "fallback_recovered": False},
        truncate_reason_codes=set(),
        route_metric_meta={"route_id": "", "route_entry": "", "engine": ""},
    )
    deps = GenerateStreamDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
        emit=lambda event, payload: {"event": event, "payload": payload},
        with_terminal=lambda payload: {**dict(payload), "terminal": True},
        with_reason_codes=lambda payload: dict(payload),
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        record_stream_timing=lambda **kwargs: timing_rows.append(dict(kwargs)),
        extract_error_code=lambda exc, default="": default,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: {
            "text": "too short",
            "problems": [],
            "trace_id": "trace-short",
            "engine": "native",
            "route_id": "compose_mode",
            "route_entry": "writer",
            "terminal_status": "success",
        },
        run_generate_graph=lambda **_kwargs: iter(()),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        postprocess_output_text=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        safe_doc_ir_payload=lambda text: {"text": text},
        single_pass_generate_stream=lambda *_args, **_kwargs: iter([
            {"event": "result", "text": " sufficient fallback stream content "},
        ]),
        check_generation_quality=lambda _text, _target: [],
        log_graph_error=lambda _exc: None,
    )

    events, result = _drain(run_generate_stream_graph_with_fallback(request=request, deps=deps))

    assert [event["event"] for event in events] == ["final", "section", "final"]
    assert events[0]["payload"]["text"] == "TOO SHORT"
    assert events[1]["payload"] == {"section": "fallback", "phase": "delta", "delta": "SUFFICIENT FALLBACK STREAM CONTENT"}
    assert events[2]["payload"]["text"] == "SUFFICIENT FALLBACK STREAM CONTENT"
    assert events[2]["payload"]["graph_meta"]["path"] == "single_pass_stream"
    assert events[2]["payload"]["terminal"] is True
    assert result == {"final_text": "SUFFICIENT FALLBACK STREAM CONTENT", "stop": False}
    assert request.trace_context["route_path"] == "single_pass_stream"
    assert request.trace_context["fallback_trigger"] == "E_TEXT_INSUFFICIENT"
    assert request.trace_context["fallback_recovered"] is True
    assert any(row[0] == "graph_insufficient" for row in metric_rows)
    assert any(row[0] == "fallback_recovered" for row in metric_rows)
    assert len(timing_rows) == 2


def test_generate_stream_request_workflow_non_dict_route_graph_output_recovers_via_single_pass_stream() -> None:
    metric_rows: list[tuple[str, dict]] = []
    timing_rows: list[dict] = []
    request = GenerateStreamRequest(
        session=_Session(generation_prefs={}, template_required_h2=[], template_outline=[], doc_text=""),
        raw_instruction="write fallback",
        instruction="write fallback",
        current_text="seed",
        graph_current_text="seed",
        compose_mode="auto",
        resume_sections=[],
        plan_confirm={},
        cfg=object(),
        target_chars=600,
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        stall_s=90.0,
        overall_s=180.0,
        section_stall_s=0.0,
        start_ts=0.0,
        trace_context={"route_path": "", "fallback_trigger": "", "fallback_recovered": False},
        truncate_reason_codes=set(),
        route_metric_meta={"route_id": "", "route_entry": "", "engine": ""},
    )
    deps = GenerateStreamDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
        emit=lambda event, payload: {"event": event, "payload": payload},
        with_terminal=lambda payload: {**dict(payload), "terminal": True},
        with_reason_codes=lambda payload: dict(payload),
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        record_stream_timing=lambda **kwargs: timing_rows.append(dict(kwargs)),
        extract_error_code=lambda exc, default="": default,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: None,
        run_generate_graph=lambda **_kwargs: iter(()),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        postprocess_output_text=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        safe_doc_ir_payload=lambda text: {"text": text},
        single_pass_generate_stream=lambda *_args, **_kwargs: iter([
            {"event": "result", "text": " recovered from non dict route graph output "},
        ]),
        check_generation_quality=lambda _text, _target: [],
        log_graph_error=lambda _exc: None,
    )

    events, result = _drain(run_generate_stream_graph_with_fallback(request=request, deps=deps))

    assert [event["event"] for event in events] == ["section", "final"]
    assert events[0]["payload"] == {
        "section": "fallback",
        "phase": "delta",
        "delta": "RECOVERED FROM NON DICT ROUTE GRAPH OUTPUT",
    }
    assert events[1]["payload"]["text"] == "RECOVERED FROM NON DICT ROUTE GRAPH OUTPUT"
    assert events[1]["payload"]["graph_meta"]["path"] == "single_pass_stream"
    assert result == {"final_text": "RECOVERED FROM NON DICT ROUTE GRAPH OUTPUT", "stop": False}
    assert request.trace_context["route_path"] == "single_pass_stream"
    assert request.trace_context["fallback_trigger"] == "E_TEXT_INSUFFICIENT"
    assert request.trace_context["fallback_recovered"] is True
    assert any(row[0] == "graph_insufficient" for row in metric_rows)
    assert any(row[0] == "fallback_recovered" for row in metric_rows)
    assert len(timing_rows) == 1



def test_generate_stream_request_workflow_timeout_failure_marks_timeout_fallback_reason() -> None:
    metric_rows: list[tuple[str, dict]] = []
    request = GenerateStreamRequest(
        session=_Session(generation_prefs={}, template_required_h2=[], template_outline=[], doc_text=""),
        raw_instruction="write fallback",
        instruction="write fallback",
        current_text="seed",
        graph_current_text="seed",
        compose_mode="auto",
        resume_sections=[],
        plan_confirm={},
        cfg=object(),
        target_chars=600,
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        stall_s=90.0,
        overall_s=180.0,
        section_stall_s=0.0,
        start_ts=0.0,
        trace_context={"route_path": "", "fallback_trigger": "", "fallback_recovered": False},
        truncate_reason_codes=set(),
        route_metric_meta={"route_id": "", "route_entry": "", "engine": ""},
    )
    deps = GenerateStreamDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
        emit=lambda event, payload: {"event": event, "payload": payload},
        with_terminal=lambda payload: {**dict(payload), "terminal": True},
        with_reason_codes=lambda payload: dict(payload),
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        record_stream_timing=lambda **kwargs: None,
        extract_error_code=lambda exc, default="": default,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: (_ for _ in ()).throw(TimeoutError('section stalled')),
        run_generate_graph=lambda **_kwargs: iter(()),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        postprocess_output_text=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        safe_doc_ir_payload=lambda text: {"text": text},
        single_pass_generate_stream=lambda *_args, **_kwargs: iter([
            {"event": "result", "text": " timeout fallback recovery content "},
        ]),
        check_generation_quality=lambda _text, _target: [],
        log_graph_error=lambda _exc: None,
    )

    events, result = _drain(run_generate_stream_graph_with_fallback(request=request, deps=deps))

    assert events[-1]["event"] == "final"
    assert events[-1]["payload"]["text"] == "TIMEOUT FALLBACK RECOVERY CONTENT"
    assert result == {"final_text": "TIMEOUT FALLBACK RECOVERY CONTENT", "stop": False}
    assert request.trace_context["fallback_trigger"] == "E_GRAPH_FAILED"
    assert request.trace_context["fallback_recovered"] is True
    assert request.truncate_reason_codes == {"timeout_fallback"}
    assert any(row[0] == "graph_failed" for row in metric_rows)
    assert any(row[0] == "fallback_recovered" for row in metric_rows)


def test_generate_stream_request_workflow_graph_failure_fallback_failure_cascades_into_insufficient_branch() -> None:
    metric_rows: list[tuple[str, dict]] = []
    request = GenerateStreamRequest(
        session=_Session(generation_prefs={}, template_required_h2=[], template_outline=[], doc_text=""),
        raw_instruction="write fallback",
        instruction="write fallback",
        current_text="seed",
        graph_current_text="seed",
        compose_mode="auto",
        resume_sections=[],
        plan_confirm={},
        cfg=object(),
        target_chars=600,
        required_h2=[],
        required_outline=[],
        expand_outline=False,
        stall_s=90.0,
        overall_s=180.0,
        section_stall_s=0.0,
        start_ts=0.0,
        trace_context={"route_path": "", "fallback_trigger": "", "fallback_recovered": False},
        truncate_reason_codes=set(),
        route_metric_meta={"route_id": "", "route_entry": "", "engine": ""},
    )
    deps = GenerateStreamDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
        emit=lambda event, payload: {"event": event, "payload": payload},
        with_terminal=lambda payload: {**dict(payload), "terminal": True},
        with_reason_codes=lambda payload: dict(payload),
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        record_stream_timing=lambda **_kwargs: None,
        extract_error_code=lambda exc, default="": f"ERR_{type(exc).__name__.upper()}" if exc else default,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('boom')),
        run_generate_graph=lambda **_kwargs: iter(()),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        postprocess_output_text=lambda _session, text, _instruction, **_kwargs: str(text).strip().upper(),
        safe_doc_ir_payload=lambda text: {"text": text},
        single_pass_generate_stream=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('fallback exploded')),
        check_generation_quality=lambda _text, _target: [],
        log_graph_error=lambda _exc: None,
    )

    events, result = _drain(run_generate_stream_graph_with_fallback(request=request, deps=deps))

    assert [event["event"] for event in events] == ["error", "error"]
    assert events[0]["payload"] == {"message": "generation failed: boom; fallback failed: fallback exploded"}
    assert events[1]["payload"] == {"message": "generation failed and fallback failed: fallback exploded"}
    assert result == {"final_text": None, "stop": True}
    assert request.trace_context["fallback_trigger"] == "ERR_RUNTIMEERROR"
    assert request.trace_context["fallback_recovered"] is False
    assert any(row[0] == "graph_failed" for row in metric_rows)
    assert any(row[0] == "graph_insufficient" for row in metric_rows)
    assert len([row for row in metric_rows if row[0] == "fallback_failed"]) == 2
