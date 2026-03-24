from __future__ import annotations

from dataclasses import dataclass

from writing_agent.workflows.generate_request_workflow import GenerateGraphRequest, run_generate_graph_with_fallback


@dataclass
class _Session:
    template_required_h2: list[str]
    template_outline: list
    generation_prefs: dict



def _make_generate_deps(**overrides):
    from writing_agent.workflows import generate_request_workflow as workflow

    params = {
        "environ": {},
        "record_route_metric": lambda *_args, **_kwargs: None,
        "should_inject_route_graph_failure": lambda **_kwargs: False,
        "run_generate_graph_dual_engine": lambda **_kwargs: {},
        "run_generate_graph": lambda **_kwargs: iter(()),
        "iter_with_timeout": lambda gen, **_kwargs: gen,
        "single_pass_generate": lambda *_args, **_kwargs: "",
        "extract_error_code": lambda _exc, default="": default,
        "http_exception_factory": lambda **kwargs: RuntimeError(str(kwargs.get("detail") or "boom")),
    }
    params.update(overrides)
    return workflow.GenerateGraphDeps(**params)


def test_generate_request_workflow_uses_route_graph(monkeypatch) -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    monkeypatch.setattr(workflow.route_graph_metrics_domain, "record_route_graph_metric", lambda *_a, **_k: None)
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "should_inject_route_graph_failure", lambda **_k: False)

    class _FakeOS:
        environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "1"}

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph_dual_engine(**_kwargs):
            return {
                "text": "# Title\n\n## Intro\nworkflow route graph text",
                "problems": [],
                "trace_id": "trace-workflow-route",
                "engine": "native",
                "route_id": "resume_sections",
                "route_entry": "writer",
                "terminal_status": "success",
            }

    session = _Session(template_required_h2=["Intro"], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=_FakeApp(),
            session=session,
            instruction="continue intro",
            raw_instruction="continue intro",
            compose_mode="continue",
            resume_sections=["Intro"],
            base_text="# Title\n\n## Intro\nold content",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        )
    )

    assert "workflow route graph text" in final_text
    assert problems == []
    assert graph_meta is not None
    assert graph_meta.get("path") == "route_graph"
    assert graph_meta.get("route_id") == "resume_sections"
    assert graph_meta.get("route_entry") == "writer"
    assert graph_meta.get("engine") == "native"
    assert graph_meta.get("engine_failover") is False


def test_generate_request_workflow_insufficient_output_recovers_via_single_pass(monkeypatch) -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_rows: list[tuple[str, dict]] = []
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "record_route_graph_metric", lambda event, **kwargs: metric_rows.append((event, dict(kwargs))))
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "should_inject_route_graph_failure", lambda **_k: False)

    class _FakeOS:
        environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "1"}

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph_dual_engine(**_kwargs):
            return {
                "text": "too short",
                "problems": [],
                "trace_id": "trace-short",
                "engine": "native",
                "route_id": "compose_mode",
                "route_entry": "writer",
                "terminal_status": "success",
            }

        @staticmethod
        def _single_pass_generate(*_args, **_kwargs):
            return "fallback recovered content long enough"

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=_FakeApp(),
            session=session,
            instruction="write short",
            raw_instruction="write short",
            compose_mode="auto",
            resume_sections=[],
            base_text="seed",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        )
    )

    assert final_text == "fallback recovered content long enough"
    assert "engine_failover_insufficient_output" in problems
    assert graph_meta is not None
    assert graph_meta.get("engine_failover") is True
    assert graph_meta.get("terminal_status") == "interrupted"
    assert graph_meta.get("failure_reason") == "engine_failover_insufficient_output"
    assert [row[0] for row in metric_rows] == ["route_graph_success", "graph_insufficient", "fallback_recovered"]



def test_generate_request_workflow_semantic_failure_skips_single_pass(monkeypatch) -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    monkeypatch.setattr(workflow.route_graph_metrics_domain, "record_route_graph_metric", lambda *_a, **_k: None)
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "should_inject_route_graph_failure", lambda **_k: False)

    called = {"single_pass": 0}

    class _FakeOS:
        environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "1"}

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph_dual_engine(**_kwargs):
            return {
                "text": "",
                "problems": ["analysis_needs_clarification"],
                "terminal_status": "failed",
                "failure_reason": "analysis_needs_clarification",
                "quality_snapshot": {
                    "status": "failed",
                    "reason": "analysis_needs_clarification",
                },
            }

        @staticmethod
        def _single_pass_generate(*_args, **_kwargs):
            called["single_pass"] += 1
            return "fallback-text"

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=_FakeApp(),
            session=session,
            instruction="write paper",
            raw_instruction="write paper",
            compose_mode="auto",
            resume_sections=[],
            base_text="",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        )
    )

    assert called["single_pass"] == 0
    assert final_text == ""
    assert "analysis_needs_clarification" in problems
    assert graph_meta is not None
    assert graph_meta.get("terminal_status") == "failed"
    assert graph_meta.get("failure_reason") == "analysis_needs_clarification"



def test_generate_request_workflow_legacy_branch_skips_dual_engine_when_route_graph_disabled(monkeypatch) -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_rows: list[tuple[str, dict]] = []
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "record_route_graph_metric", lambda event, **kwargs: metric_rows.append((event, dict(kwargs))))
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "should_inject_route_graph_failure", lambda **_k: False)

    class _FakeOS:
        environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "0"}

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph_dual_engine(**_kwargs):
            raise RuntimeError("dual engine should not run when route graph is disabled")

        @staticmethod
        def run_generate_graph(**_kwargs):
            return iter(
                [
                    {"event": "prompt_route", "stage": "writer", "metadata": {"policy": "legacy"}},
                    {"event": "final", "text": "legacy path output long enough", "problems": ["warn"]},
                ]
            )

        @staticmethod
        def _iter_with_timeout(gen, **_kwargs):
            return gen

    session = _Session(template_required_h2=["Intro"], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=_FakeApp(),
            session=session,
            instruction="continue intro",
            raw_instruction="continue intro",
            compose_mode="continue",
            resume_sections=["Intro"],
            base_text="# Title\n\n## Intro\nold content",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        )
    )

    assert final_text == "legacy path output long enough"
    assert problems == ["warn"]
    assert graph_meta is not None
    assert graph_meta.get("terminal_status") == "success"
    assert graph_meta.get("engine_failover") is False
    assert graph_meta.get("prompt_trace") == [{"stage": "writer", "metadata": {"policy": "legacy"}}]
    assert [row[0] for row in metric_rows] == ["legacy_graph_success"]



def test_generate_request_workflow_supports_injected_deps() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_rows: list[tuple[str, dict]] = []

    class _FakeHTTPException(Exception):
        def __init__(self, *, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    deps = workflow.GenerateGraphDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: {
            "text": "# Title\n\n## Intro\ninjected deps route graph text",
            "problems": [],
            "trace_id": "trace-injected",
            "engine": "langgraph",
            "route_id": "compose_mode",
            "route_entry": "planner",
            "terminal_status": "success",
        },
        run_generate_graph=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("legacy branch should not run")),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        single_pass_generate=lambda *_args, **_kwargs: "fallback text",
        extract_error_code=lambda _exc, default="": default,
        http_exception_factory=lambda **kwargs: _FakeHTTPException(**kwargs),
    )

    session = _Session(template_required_h2=["Intro"], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=object(),
            session=session,
            instruction="continue intro",
            raw_instruction="continue intro",
            compose_mode="continue",
            resume_sections=["Intro"],
            base_text="# Title\n\n## Intro\nold content",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        ),
        deps=deps,
    )

    assert "injected deps route graph text" in final_text
    assert problems == []
    assert graph_meta is not None
    assert graph_meta.get("path") == "route_graph"
    assert graph_meta.get("route_id") == "compose_mode"
    assert graph_meta.get("route_entry") == "planner"
    assert graph_meta.get("engine") == "langgraph"
    assert [row[0] for row in metric_rows] == ["route_graph_success"]



def test_generate_request_workflow_legacy_insufficient_output_recovers_via_single_pass(monkeypatch) -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_rows: list[tuple[str, dict]] = []
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "record_route_graph_metric", lambda event, **kwargs: metric_rows.append((event, dict(kwargs))))
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "should_inject_route_graph_failure", lambda **_k: False)

    class _FakeOS:
        environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "0"}

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph_dual_engine(**_kwargs):
            raise RuntimeError("dual engine should not run when route graph is disabled")

        @staticmethod
        def run_generate_graph(**_kwargs):
            return iter(
                [
                    {"event": "prompt_route", "stage": "writer", "metadata": {"policy": "legacy"}},
                    {"event": "final", "text": "short", "problems": []},
                ]
            )

        @staticmethod
        def _iter_with_timeout(gen, **_kwargs):
            return gen

        @staticmethod
        def _single_pass_generate(*_args, **_kwargs):
            return "legacy fallback recovered content long enough"

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=_FakeApp(),
            session=session,
            instruction="write short",
            raw_instruction="write short",
            compose_mode="auto",
            resume_sections=[],
            base_text="seed",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        )
    )

    assert final_text == "legacy fallback recovered content long enough"
    assert "engine_failover_insufficient_output" in problems
    assert graph_meta is not None
    assert graph_meta.get("engine_failover") is True
    assert graph_meta.get("terminal_status") == "interrupted"
    assert graph_meta.get("failure_reason") == "engine_failover_insufficient_output"
    assert graph_meta.get("prompt_trace") == [{"stage": "writer", "metadata": {"policy": "legacy"}}]
    assert [row[0] for row in metric_rows] == ["legacy_graph_success", "graph_insufficient", "fallback_recovered"]



def test_generate_request_workflow_graph_failed_recovers_via_single_pass(monkeypatch) -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_rows: list[tuple[str, dict]] = []
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "record_route_graph_metric", lambda event, **kwargs: metric_rows.append((event, dict(kwargs))))
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "should_inject_route_graph_failure", lambda **_k: False)

    class _FakeOS:
        environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "1"}

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph_dual_engine(**_kwargs):
            raise RuntimeError("boom")

        @staticmethod
        def _single_pass_generate(*_args, **_kwargs):
            return "graph failed fallback recovered content long enough"

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=_FakeApp(),
            session=session,
            instruction="write",
            raw_instruction="write",
            compose_mode="auto",
            resume_sections=[],
            base_text="seed",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        )
    )

    assert final_text == "graph failed fallback recovered content long enough"
    assert "engine_failover_graph_failed" in problems
    assert graph_meta is not None
    assert graph_meta.get("engine_failover") is True
    assert graph_meta.get("terminal_status") == "interrupted"
    assert graph_meta.get("failure_reason") == "engine_failover_graph_failed"
    assert [row[0] for row in metric_rows] == ["graph_failed", "fallback_recovered"]



def test_generate_request_workflow_graph_failed_metric_uses_extracted_error_code(monkeypatch) -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_rows: list[tuple[str, dict]] = []
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "record_route_graph_metric", lambda event, **kwargs: metric_rows.append((event, dict(kwargs))))
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "should_inject_route_graph_failure", lambda **_k: False)
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "extract_error_code", lambda _exc, default="": "E_ROUTE_GRAPH_BOOM")

    class _FakeOS:
        environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "1"}

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph_dual_engine(**_kwargs):
            raise RuntimeError("boom")

        @staticmethod
        def _single_pass_generate(*_args, **_kwargs):
            return "route graph failure recovered"

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=_FakeApp(),
            session=session,
            instruction="write",
            raw_instruction="write",
            compose_mode="auto",
            resume_sections=[],
            base_text="seed",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        )
    )

    assert final_text == "route graph failure recovered"
    assert "engine_failover_graph_failed" in problems
    assert graph_meta is not None
    assert metric_rows[0][0] == "graph_failed"
    assert metric_rows[0][1]["path"] == "route_graph"
    assert metric_rows[0][1]["error_code"] == "E_ROUTE_GRAPH_BOOM"



def test_generate_request_workflow_legacy_graph_failed_metric_uses_legacy_path(monkeypatch) -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_rows: list[tuple[str, dict]] = []
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "record_route_graph_metric", lambda event, **kwargs: metric_rows.append((event, dict(kwargs))))
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "should_inject_route_graph_failure", lambda **_k: False)
    monkeypatch.setattr(workflow.route_graph_metrics_domain, "extract_error_code", lambda _exc, default="": "E_LEGACY_GRAPH_BOOM")

    class _FakeOS:
        environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "0"}

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph_dual_engine(**_kwargs):
            raise RuntimeError("dual engine should not run")

        @staticmethod
        def run_generate_graph(**_kwargs):
            raise RuntimeError("legacy boom")

        @staticmethod
        def _single_pass_generate(*_args, **_kwargs):
            return "legacy graph failure recovered"

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=_FakeApp(),
            session=session,
            instruction="write",
            raw_instruction="write",
            compose_mode="auto",
            resume_sections=[],
            base_text="seed",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        )
    )

    assert final_text == "legacy graph failure recovered"
    assert "engine_failover_graph_failed" in problems
    assert graph_meta is not None
    assert metric_rows[0][0] == "graph_failed"
    assert metric_rows[0][1]["path"] == "legacy_graph"
    assert metric_rows[0][1]["error_code"] == "E_LEGACY_GRAPH_BOOM"



def test_generate_request_workflow_supports_injected_deps_legacy_failure_recovery() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_rows: list[tuple[str, dict]] = []

    class _FakeHTTPException(Exception):
        def __init__(self, *, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    deps = workflow.GenerateGraphDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "0"},
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("dual engine should not run")),
        run_generate_graph=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("legacy boom")),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        single_pass_generate=lambda *_args, **_kwargs: "legacy deps recovered",
        extract_error_code=lambda _exc, default="": "E_INJECTED_LEGACY_BOOM",
        http_exception_factory=lambda **kwargs: _FakeHTTPException(**kwargs),
    )

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=object(),
            session=session,
            instruction="write",
            raw_instruction="write",
            compose_mode="auto",
            resume_sections=[],
            base_text="seed",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        ),
        deps=deps,
    )

    assert final_text == "legacy deps recovered"
    assert "engine_failover_graph_failed" in problems
    assert graph_meta is not None
    assert graph_meta.get("engine_failover") is True
    assert graph_meta.get("failure_reason") == "engine_failover_graph_failed"
    assert [row[0] for row in metric_rows] == ["graph_failed", "fallback_recovered"]
    assert metric_rows[0][1]["path"] == "legacy_graph"
    assert metric_rows[0][1]["error_code"] == "E_INJECTED_LEGACY_BOOM"



def test_generate_request_workflow_supports_injected_deps_route_graph_failure_recovery() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_rows: list[tuple[str, dict]] = []

    class _FakeHTTPException(Exception):
        def __init__(self, *, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    deps = workflow.GenerateGraphDeps(
        environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
        record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs))),
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("route graph boom")),
        run_generate_graph=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("legacy branch should not run")),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        single_pass_generate=lambda *_args, **_kwargs: "route graph deps recovered",
        extract_error_code=lambda _exc, default="": "E_INJECTED_ROUTE_BOOM",
        http_exception_factory=lambda **kwargs: _FakeHTTPException(**kwargs),
    )

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = run_generate_graph_with_fallback(
        request=GenerateGraphRequest(
            app_v2=object(),
            session=session,
            instruction="write",
            raw_instruction="write",
            compose_mode="auto",
            resume_sections=[],
            base_text="seed",
            cfg=object(),
            target_chars=1200,
            plan_confirm={},
        ),
        deps=deps,
    )

    assert final_text == "route graph deps recovered"
    assert "engine_failover_graph_failed" in problems
    assert graph_meta is not None
    assert graph_meta.get("engine_failover") is True
    assert graph_meta.get("failure_reason") == "engine_failover_graph_failed"
    assert [row[0] for row in metric_rows] == ["graph_failed", "fallback_recovered"]
    assert metric_rows[0][1]["path"] == "route_graph"
    assert metric_rows[0][1]["error_code"] == "E_INJECTED_ROUTE_BOOM"



def test_build_generate_resolved_inputs_prefers_resume_sections() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(
        template_required_h2=["Template Intro"],
        template_outline=[{"title": "Template Outline"}],
        generation_prefs={"expand_outline": True},
    )
    inputs = workflow.build_generate_resolved_inputs(
        GenerateGraphRequest(
            app_v2=object(),
            session=session,
            instruction="continue intro",
            raw_instruction="continue intro",
            compose_mode="continue",
            resume_sections=["Intro"],
            base_text="seed",
            cfg=object(),
            target_chars=900,
            plan_confirm={"decision": "accept"},
        )
    )

    assert inputs.instruction == "continue intro"
    assert inputs.resume_sections == ["Intro"]
    assert inputs.required_h2 == ["Intro"]
    assert inputs.required_outline == []
    assert inputs.expand_outline is True
    assert inputs.target_chars == 900
    assert inputs.plan_confirm == {"decision": "accept"}



def test_build_generate_execution_context_preserves_state_and_inputs() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction="write",
        raw_instruction="write",
        compose_mode="auto",
        resume_sections=[],
        base_text="seed",
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    deps = workflow.GenerateGraphDeps(
        environ={},
        record_route_metric=lambda *_args, **_kwargs: None,
        should_inject_route_graph_failure=lambda **_kwargs: False,
        run_generate_graph_dual_engine=None,
        run_generate_graph=lambda **_kwargs: iter(()),
        iter_with_timeout=lambda gen, **_kwargs: gen,
        single_pass_generate=lambda *_args, **_kwargs: "",
        extract_error_code=lambda _exc, default="": default,
        http_exception_factory=lambda **kwargs: RuntimeError(str(kwargs.get("detail") or "boom")),
    )
    state = workflow.GenerateGraphRuntimeState(use_route_graph=True)

    context = workflow.build_generate_execution_context(
        request=request,
        deps=deps,
        inputs=inputs,
        state=state,
        started_at=12.5,
    )

    assert context.session is session
    assert context.inputs is inputs
    assert context.state is state
    assert context.started_at == 12.5
    assert context.state.use_route_graph is True



def test_build_generate_branch_selection_respects_route_graph_toggle() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    enabled = workflow.build_generate_branch_selection(
        deps=_make_generate_deps(
            environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
            run_generate_graph_dual_engine=lambda **_kwargs: {"text": "ok"},
        )
    )
    disabled = workflow.build_generate_branch_selection(
        deps=_make_generate_deps(
            environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "0"},
            run_generate_graph_dual_engine=lambda **_kwargs: {"text": "ok"},
        )
    )
    unavailable = workflow.build_generate_branch_selection(
        deps=_make_generate_deps(
            environ={"WRITING_AGENT_USE_ROUTE_GRAPH": "1"},
            run_generate_graph_dual_engine=None,
        )
    )

    assert enabled.use_route_graph is True
    assert disabled.use_route_graph is False
    assert unavailable.use_route_graph is False



def test_build_generate_legacy_timeout_policy_prefers_nonstream_env() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    policy = workflow.build_generate_legacy_timeout_policy(
        environ={
            "WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S": "15",
            "WRITING_AGENT_STREAM_EVENT_TIMEOUT_S": "90",
            "WRITING_AGENT_NONSTREAM_MAX_S": "35",
            "WRITING_AGENT_STREAM_MAX_S": "180",
        }
    )
    fallback_policy = workflow.build_generate_legacy_timeout_policy(
        environ={
            "WRITING_AGENT_STREAM_EVENT_TIMEOUT_S": "91",
            "WRITING_AGENT_STREAM_MAX_S": "181",
        }
    )

    assert policy.stall_s == 15.0
    assert policy.overall_s == 35.0
    assert fallback_policy.stall_s == 91.0
    assert fallback_policy.overall_s == 181.0



def test_build_generate_graph_failed_failover_request_preserves_error_context() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction="write",
        raw_instruction="write",
        compose_mode="auto",
        resume_sections=[],
        base_text="seed",
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(),
        inputs=inputs,
        state=workflow.GenerateGraphRuntimeState(use_route_graph=True),
        started_at=1.0,
    )
    exc = RuntimeError("route graph boom")

    failover_request = workflow.build_generate_graph_failed_failover_request(context=context, exc=exc)

    assert failover_request.trigger_event == "graph_failed"
    assert failover_request.use_route_graph is True
    assert failover_request.failover_reason == "engine_failover_graph_failed"
    assert failover_request.default_error_code == "E_GRAPH_FAILED"
    assert failover_request.exc is exc
    assert "route graph boom" in failover_request.failure_detail



def test_build_generate_finalization_plan_requests_failover_for_insufficient_output() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction="write",
        raw_instruction="write",
        compose_mode="auto",
        resume_sections=[],
        base_text="seed",
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(),
        inputs=inputs,
        state=workflow.GenerateGraphRuntimeState(final_text="short", use_route_graph=False),
        started_at=1.0,
    )

    plan = workflow.build_generate_finalization_plan(context=context)

    assert plan.final_text == "short"
    assert plan.requires_failover is True
    assert plan.failover_request is not None
    assert plan.failover_request.trigger_event == "graph_insufficient"
    assert plan.failover_request.use_route_graph is False
    assert plan.failover_request.error_code == "E_TEXT_INSUFFICIENT"



def test_build_generate_finalization_plan_skips_semantic_failover() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction="write",
        raw_instruction="write",
        compose_mode="auto",
        resume_sections=[],
        base_text="seed",
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(),
        inputs=inputs,
        state=workflow.GenerateGraphRuntimeState(
            final_text="short",
            terminal_status="failed",
            failure_reason="analysis_guard_failed",
            use_route_graph=True,
        ),
        started_at=1.0,
    )

    plan = workflow.build_generate_finalization_plan(context=context)

    assert plan.final_text == "short"
    assert plan.requires_failover is False
    assert plan.failover_request is None



def test_build_generate_route_graph_run_request_captures_inputs() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(
        template_required_h2=['Intro'],
        template_outline=[{'title': 'Template'}],
        generation_prefs={'expand_outline': True},
    )
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='continue intro',
        raw_instruction='continue intro',
        compose_mode='continue',
        resume_sections=['Intro'],
        base_text='seed text',
        cfg=object(),
        target_chars=900,
        plan_confirm={'decision': 'accept'},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(),
        inputs=inputs,
        started_at=1.0,
    )

    run_request = workflow.build_generate_route_graph_run_request(context=context)

    assert run_request.kwargs['instruction'] == 'continue intro'
    assert run_request.kwargs['current_text'] == 'seed text'
    assert run_request.kwargs['required_h2'] == ['Intro']
    assert run_request.kwargs['required_outline'] == []
    assert run_request.kwargs['compose_mode'] == 'continue'
    assert run_request.kwargs['resume_sections'] == ['Intro']
    assert run_request.kwargs['format_only'] is False
    assert run_request.kwargs['plan_confirm'] == {'decision': 'accept'}



def test_build_generate_legacy_graph_run_request_includes_timeout_policy() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(
        template_required_h2=['Intro'],
        template_outline=[{'title': 'Template'}],
        generation_prefs={'expand_outline': False},
    )
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write article',
        raw_instruction='write article',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed text',
        cfg=object(),
        target_chars=1200,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(
            environ={
                'WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S': '22',
                'WRITING_AGENT_NONSTREAM_MAX_S': '44',
            }
        ),
        inputs=inputs,
        started_at=1.0,
    )

    run_request = workflow.build_generate_legacy_graph_run_request(context=context)

    assert run_request.kwargs['instruction'] == 'write article'
    assert run_request.kwargs['current_text'] == 'seed text'
    assert run_request.kwargs['required_h2'] == ['Intro']
    assert run_request.kwargs['required_outline'] == [{'title': 'Template'}]
    assert run_request.kwargs['expand_outline'] is False
    assert run_request.timeout_policy.stall_s == 22.0
    assert run_request.timeout_policy.overall_s == 44.0



def test_build_generate_single_pass_request_preserves_text_and_target() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='rewrite',
        raw_instruction='rewrite',
        compose_mode='auto',
        resume_sections=[],
        base_text='draft body',
        cfg=object(),
        target_chars=1500,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(),
        inputs=inputs,
        started_at=1.0,
    )

    single_pass_request = workflow.build_generate_single_pass_request(context=context)

    assert single_pass_request.instruction == 'rewrite'
    assert single_pass_request.current_text == 'draft body'
    assert single_pass_request.target_chars == 1500



def test_build_generate_primary_success_metric_plan_uses_branch_path() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    route_plan = workflow.build_generate_primary_success_metric_plan(use_route_graph=True)
    legacy_plan = workflow.build_generate_primary_success_metric_plan(use_route_graph=False)

    assert route_plan.event == 'route_graph_success'
    assert route_plan.path == 'route_graph'
    assert route_plan.fallback_triggered is False
    assert route_plan.fallback_recovered is False
    assert legacy_plan.event == 'legacy_graph_success'
    assert legacy_plan.path == 'legacy_graph'
    assert legacy_plan.fallback_triggered is False
    assert legacy_plan.fallback_recovered is False



def test_build_generate_route_graph_primary_outcome_maps_result() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    outcome = workflow.build_generate_route_graph_primary_outcome(
        route_result={
            'text': '# Title\n\n## Intro\nroute body',
            'problems': [],
            'trace_id': 'trace-1',
            'engine': 'native',
            'route_id': 'resume_sections',
            'route_entry': 'writer',
            'terminal_status': 'success',
            'quality_snapshot': {'score': 0.8},
            'prompt_trace': [{'stage': 'route', 'metadata': {'k': 'v'}}],
        }
    )

    assert outcome.use_route_graph is True
    assert 'route body' in str(outcome.final_text)
    assert outcome.problems == []
    assert outcome.terminal_status == 'success'
    assert outcome.failure_reason == ''
    assert outcome.quality_snapshot == {'score': 0.8}
    assert outcome.graph_meta is not None
    assert outcome.graph_meta.get('path') == 'route_graph'
    assert outcome.success_metric is not None
    assert outcome.success_metric.event == 'route_graph_success'



def test_build_generate_legacy_primary_outcome_maps_observation_and_trace() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    outcome = workflow.build_generate_legacy_primary_outcome(
        observation={
            'final_text': 'legacy final body',
            'problems': ['p1'],
            'terminal_status': 'interrupted',
            'failure_reason': 'engine_failover_graph_failed',
            'quality_snapshot': {'score': 0.4},
        },
        prompt_trace=[{'stage': 'prompt_route', 'metadata': {'branch': 'legacy'}}],
    )

    assert outcome.use_route_graph is False
    assert outcome.final_text == 'legacy final body'
    assert outcome.problems == ['p1']
    assert outcome.terminal_status == 'interrupted'
    assert outcome.failure_reason == 'engine_failover_graph_failed'
    assert outcome.quality_snapshot == {'score': 0.4}
    assert outcome.prompt_trace == [{'stage': 'prompt_route', 'metadata': {'branch': 'legacy'}}]
    assert outcome.success_metric is not None
    assert outcome.success_metric.event == 'legacy_graph_success'
    assert outcome.success_metric.path == 'legacy_graph'



def test_build_generate_primary_state_plan_maps_primary_outcome() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    primary_result = workflow.GeneratePrimaryOutcome(
        use_route_graph=True,
        final_text='generated body',
        problems=['p1'],
        terminal_status='interrupted',
        failure_reason='engine_failover_graph_failed',
        quality_snapshot={'score': 0.2},
        prompt_trace=[{'stage': 'route', 'metadata': {'engine': 'native'}}],
        graph_meta={'path': 'route_graph', 'route_id': 'resume_sections'},
        success_metric=workflow.build_generate_primary_success_metric_plan(use_route_graph=True),
    )

    state_plan = workflow.build_generate_primary_state_plan(primary_result=primary_result)

    assert state_plan.use_route_graph is True
    assert state_plan.final_text == 'generated body'
    assert state_plan.problems == ['p1']
    assert state_plan.terminal_status == 'interrupted'
    assert state_plan.failure_reason == 'engine_failover_graph_failed'
    assert state_plan.quality_snapshot == {'score': 0.2}
    assert state_plan.prompt_trace == [{'stage': 'route', 'metadata': {'engine': 'native'}}]
    assert state_plan.graph_meta == {'path': 'route_graph', 'route_id': 'resume_sections'}
    assert state_plan.success_metric is not None
    assert state_plan.success_metric.event == 'route_graph_success'



def test_apply_generate_primary_state_plan_updates_state_and_records_metric() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_rows: list[tuple[str, dict]] = []
    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write',
        raw_instruction='write',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(record_route_metric=lambda event, **kwargs: metric_rows.append((event, dict(kwargs)))),
        inputs=inputs,
        started_at=1.0,
    )
    state_plan = workflow.GeneratePrimaryStatePlan(
        use_route_graph=True,
        final_text='generated body',
        problems=['p1'],
        terminal_status='success',
        failure_reason='',
        quality_snapshot={'score': 0.9},
        prompt_trace=[{'stage': 'route', 'metadata': {'engine': 'native'}}],
        graph_meta={'path': 'route_graph', 'route_id': 'resume_sections', 'route_entry': 'writer', 'engine': 'native'},
        success_metric=workflow.build_generate_primary_success_metric_plan(use_route_graph=True),
    )

    workflow.apply_generate_primary_state_plan(context=context, state_plan=state_plan)

    assert context.state.use_route_graph is True
    assert context.state.final_text == 'generated body'
    assert context.state.problems == ['p1']
    assert context.state.graph_meta is not None
    assert context.state.graph_meta.get('route_id') == 'resume_sections'
    assert [row[0] for row in metric_rows] == ['route_graph_success']
    assert metric_rows[0][1]['path'] == 'route_graph'



def test_build_generate_failover_state_plan_appends_failure_reason_once() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    state_plan = workflow.build_generate_failover_state_plan(
        recovered_text='fallback body',
        failover_reason='engine_failover_graph_failed',
        existing_problems=['p1', 'engine_failover_graph_failed'],
    )

    assert state_plan.final_text == 'fallback body'
    assert state_plan.problems == ['p1', 'engine_failover_graph_failed']
    assert state_plan.terminal_status == 'interrupted'
    assert state_plan.failure_reason == 'engine_failover_graph_failed'
    assert state_plan.quality_snapshot['status'] == 'interrupted'
    assert state_plan.quality_snapshot['reason'] == 'engine_failover_graph_failed'
    assert state_plan.quality_snapshot['problem_count'] == 2
    assert state_plan.engine_failover is True



def test_apply_generate_failover_state_plan_updates_runtime_state() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write',
        raw_instruction='write',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(),
        inputs=inputs,
        state=workflow.GenerateGraphRuntimeState(problems=['p0']),
        started_at=1.0,
    )
    state_plan = workflow.GenerateFailoverStatePlan(
        final_text='fallback body',
        problems=['p0', 'engine_failover_graph_failed'],
        terminal_status='interrupted',
        failure_reason='engine_failover_graph_failed',
        quality_snapshot={'status': 'interrupted', 'reason': 'engine_failover_graph_failed', 'problem_count': 1, 'needs_review': True},
        engine_failover=True,
    )

    workflow.apply_generate_failover_state_plan(context=context, state_plan=state_plan)

    assert context.state.final_text == 'fallback body'
    assert context.state.problems == ['p0', 'engine_failover_graph_failed']
    assert context.state.terminal_status == 'interrupted'
    assert context.state.failure_reason == 'engine_failover_graph_failed'
    assert context.state.quality_snapshot['problem_count'] == 1
    assert context.state.engine_failover is True



def test_build_generate_failover_recovered_metric_plan_uses_single_pass_path() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    metric_plan = workflow.build_generate_failover_recovered_metric_plan(use_route_graph=True)

    assert metric_plan.event == 'fallback_recovered'
    assert metric_plan.path == 'single_pass'
    assert metric_plan.fallback_triggered is True
    assert metric_plan.fallback_recovered is True
    assert metric_plan.error_code == ''



def test_build_generate_failover_failed_metric_plan_uses_extracted_error_code() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write',
        raw_instruction='write',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(extract_error_code=lambda _exc, default='': 'E_FAILOVER_CUSTOM'),
        inputs=inputs,
        state=workflow.GenerateGraphRuntimeState(use_route_graph=True),
        started_at=1.0,
    )

    metric_plan = workflow.build_generate_failover_failed_metric_plan(
        context=context,
        exc=RuntimeError('fallback boom'),
    )

    assert metric_plan.event == 'fallback_failed'
    assert metric_plan.path == 'single_pass'
    assert metric_plan.fallback_triggered is True
    assert metric_plan.fallback_recovered is False
    assert metric_plan.error_code == 'E_FAILOVER_CUSTOM'



def test_build_generate_graph_meta_finalization_request_preserves_state_fields() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write',
        raw_instruction='write',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(),
        inputs=inputs,
        state=workflow.GenerateGraphRuntimeState(
            graph_meta={'path': 'route_graph', 'route_id': 'resume_sections'},
            terminal_status='interrupted',
            failure_reason='engine_failover_graph_failed',
            quality_snapshot={'status': 'interrupted', 'reason': 'engine_failover_graph_failed', 'problem_count': 1, 'needs_review': True},
            engine_failover=True,
            prompt_trace=[{'stage': 'route', 'metadata': {'engine': 'native'}}],
        ),
        started_at=1.0,
    )

    finalization_request = workflow.build_generate_graph_meta_finalization_request(context=context)

    assert finalization_request.graph_meta == {'path': 'route_graph', 'route_id': 'resume_sections'}
    assert finalization_request.terminal_status == 'interrupted'
    assert finalization_request.failure_reason == 'engine_failover_graph_failed'
    assert finalization_request.quality_snapshot['problem_count'] == 1
    assert finalization_request.engine_failover is True
    assert finalization_request.prompt_trace == [{'stage': 'route', 'metadata': {'engine': 'native'}}]



def test_build_generate_finalized_graph_meta_merges_terminal_fields() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    graph_meta = workflow.build_generate_finalized_graph_meta(
        request=workflow.GenerateGraphMetaFinalizationRequest(
            graph_meta={'path': 'route_graph', 'route_id': 'resume_sections'},
            terminal_status='interrupted',
            failure_reason='engine_failover_graph_failed',
            quality_snapshot={'status': 'interrupted', 'reason': 'engine_failover_graph_failed', 'problem_count': 1, 'needs_review': True},
            engine_failover=True,
            prompt_trace=[{'stage': 'route', 'metadata': {'engine': 'native'}}],
        )
    )

    assert graph_meta is not None
    assert graph_meta.get('path') == 'route_graph'
    assert graph_meta.get('route_id') == 'resume_sections'
    assert graph_meta.get('terminal_status') == 'interrupted'
    assert graph_meta.get('failure_reason') == 'engine_failover_graph_failed'
    assert graph_meta.get('engine_failover') is True
    assert graph_meta.get('prompt_trace') == [{'stage': 'route', 'metadata': {'engine': 'native'}}]



def test_build_generate_failover_trigger_metric_plan_uses_request_and_extractor() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write',
        raw_instruction='write',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(extract_error_code=lambda _exc, default='': 'E_TRIGGER_CUSTOM'),
        inputs=inputs,
        state=workflow.GenerateGraphRuntimeState(use_route_graph=True),
        started_at=1.0,
    )
    failover_request = workflow.GenerateFailoverRequest(
        trigger_event='graph_failed',
        use_route_graph=True,
        failover_reason='engine_failover_graph_failed',
        failure_detail='generation failed: {exc}',
        exc=RuntimeError('boom'),
        default_error_code='E_GRAPH_FAILED',
    )

    metric_plan = workflow.build_generate_failover_trigger_metric_plan(
        context=context,
        failover_request=failover_request,
    )

    assert metric_plan.event == 'graph_failed'
    assert metric_plan.path == 'route_graph'
    assert metric_plan.fallback_triggered is True
    assert metric_plan.fallback_recovered is False
    assert metric_plan.error_code == 'E_TRIGGER_CUSTOM'



def test_build_generate_failover_execution_plan_preserves_metric_and_reason() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write',
        raw_instruction='write',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(extract_error_code=lambda _exc, default='': 'E_EXEC_PLAN'),
        inputs=inputs,
        state=workflow.GenerateGraphRuntimeState(use_route_graph=False),
        started_at=1.0,
    )
    failover_request = workflow.GenerateFailoverRequest(
        trigger_event='graph_failed',
        use_route_graph=False,
        failover_reason='engine_failover_graph_failed',
        failure_detail='generation failed: {exc}',
        graph_path='legacy_graph',
        exc=RuntimeError('legacy boom'),
        default_error_code='E_GRAPH_FAILED',
    )

    execution_plan = workflow.build_generate_failover_execution_plan(
        context=context,
        failover_request=failover_request,
    )

    assert execution_plan.trigger_metric.event == 'graph_failed'
    assert execution_plan.trigger_metric.path == 'legacy_graph'
    assert execution_plan.trigger_metric.error_code == 'E_EXEC_PLAN'
    assert execution_plan.failover_reason == 'engine_failover_graph_failed'
    assert execution_plan.failure_detail == 'generation failed: {exc}'



def test_build_generate_driver_run_request_preserves_state_and_builds_driver_deps() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write',
        raw_instruction='write',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    state = workflow.GenerateGraphRuntimeState()
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(),
        inputs=inputs,
        state=state,
        started_at=1.0,
    )

    driver_run_request = workflow.build_generate_driver_run_request(context=context)

    assert driver_run_request.state is state
    assert callable(driver_run_request.driver_deps.execute_primary_fn)
    assert callable(driver_run_request.driver_deps.apply_primary_result_fn)
    assert callable(driver_run_request.driver_deps.execute_graph_failed_failover_fn)
    assert callable(driver_run_request.driver_deps.finalize_result_fn)



def test_build_generate_workflow_bootstrap_supports_injected_deps() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=['Intro'], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='continue intro',
        raw_instruction='continue intro',
        compose_mode='continue',
        resume_sections=['Intro'],
        base_text='seed',
        cfg=object(),
        target_chars=900,
        plan_confirm={'decision': 'accept'},
    )
    deps = _make_generate_deps(environ={'WRITING_AGENT_USE_ROUTE_GRAPH': '1'})

    bootstrap = workflow.build_generate_workflow_bootstrap(request=request, deps=deps)

    assert bootstrap.deps is deps
    assert bootstrap.inputs.instruction == 'continue intro'
    assert bootstrap.inputs.resume_sections == ['Intro']
    assert bootstrap.context.deps is deps
    assert bootstrap.context.inputs is bootstrap.inputs
    assert bootstrap.driver_run_request.state is bootstrap.context.state



def test_build_generate_workflow_response_normalizes_execution_result() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    response = workflow.build_generate_workflow_response(
        execution=workflow.GenerateExecutionResult(
            final_text='final body',
            problems=['p1'],
            graph_meta={'path': 'route_graph'},
        )
    )

    assert response == ('final body', ['p1'], {'path': 'route_graph'})



def test_build_generate_route_graph_branch_execution_plan_collects_injection_and_request() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=['Intro'], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='continue intro',
        raw_instruction='continue intro',
        compose_mode='continue',
        resume_sections=['Intro'],
        base_text='seed',
        cfg=object(),
        target_chars=900,
        plan_confirm={'decision': 'accept'},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(should_inject_route_graph_failure=lambda **_kwargs: True),
        inputs=inputs,
        started_at=1.0,
    )

    execution_plan = workflow.build_generate_route_graph_branch_execution_plan(context=context)

    assert execution_plan.inject_failure is True
    assert execution_plan.run_request.kwargs['instruction'] == 'continue intro'
    assert execution_plan.run_request.kwargs['resume_sections'] == ['Intro']
    assert execution_plan.run_request.kwargs['plan_confirm'] == {'decision': 'accept'}



def test_build_generate_legacy_event_loop_request_preserves_generator_timeout_and_trace() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    generator = iter(())
    session = _Session(template_required_h2=['Intro'], template_outline=[{'title': 'Outline'}], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write article',
        raw_instruction='write article',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=1200,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    state = workflow.GenerateGraphRuntimeState(prompt_trace=[{'stage': 'existing', 'metadata': {'k': 'v'}}])
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(
            environ={
                'WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S': '12',
                'WRITING_AGENT_NONSTREAM_MAX_S': '34',
            },
            run_generate_graph=lambda **_kwargs: generator,
        ),
        inputs=inputs,
        state=state,
        started_at=1.0,
    )
    run_request = workflow.build_generate_legacy_graph_run_request(context=context)

    loop_request = workflow.build_generate_legacy_event_loop_request(
        context=context,
        run_request=run_request,
    )

    assert loop_request.generator is generator
    assert loop_request.stall_s == 12.0
    assert loop_request.overall_s == 34.0
    assert loop_request.prompt_trace is state.prompt_trace



def test_drive_generate_legacy_event_loop_returns_final_observation_and_prompt_trace() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write',
        raw_instruction='write',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(iter_with_timeout=lambda gen, **_kwargs: gen),
        inputs=inputs,
        started_at=1.0,
    )
    loop_request = workflow.GenerateLegacyEventLoopRequest(
        generator=iter(
            [
                {'event': 'prompt_route', 'stage': 'route', 'metadata': {'path': 'legacy_graph'}},
                {'event': 'final', 'text': 'legacy done', 'status': 'success', 'problems': []},
            ]
        ),
        stall_s=12.0,
        overall_s=34.0,
        prompt_trace=context.state.prompt_trace,
    )

    loop_result = workflow.drive_generate_legacy_event_loop(
        context=context,
        request=loop_request,
    )

    assert loop_result.final_observation is not None
    assert loop_result.final_observation['final_text'] == 'legacy done'
    assert loop_result.final_observation['terminal_status'] == 'success'
    assert loop_result.prompt_trace == [{'stage': 'route', 'metadata': {'path': 'legacy_graph'}}]



def test_build_generate_legacy_branch_execution_plan_bundles_run_and_loop_requests() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    generator = iter(())
    session = _Session(template_required_h2=['Intro'], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write article',
        raw_instruction='write article',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=1200,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(
            environ={
                'WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S': '21',
                'WRITING_AGENT_NONSTREAM_MAX_S': '43',
            },
            run_generate_graph=lambda **_kwargs: generator,
        ),
        inputs=inputs,
        started_at=1.0,
    )

    execution_plan = workflow.build_generate_legacy_branch_execution_plan(context=context)

    assert execution_plan.run_request.timeout_policy.stall_s == 21.0
    assert execution_plan.run_request.timeout_policy.overall_s == 43.0
    assert execution_plan.event_loop_request.generator is generator
    assert execution_plan.event_loop_request.stall_s == 21.0
    assert execution_plan.event_loop_request.overall_s == 43.0



def test_build_generate_primary_branch_execution_plan_selects_path() -> None:
    from writing_agent.workflows import generate_request_workflow as workflow

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    request = GenerateGraphRequest(
        app_v2=object(),
        session=session,
        instruction='write',
        raw_instruction='write',
        compose_mode='auto',
        resume_sections=[],
        base_text='seed',
        cfg=object(),
        target_chars=800,
        plan_confirm={},
    )
    inputs = workflow.build_generate_resolved_inputs(request)
    route_context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(
            environ={'WRITING_AGENT_USE_ROUTE_GRAPH': '1'},
            run_generate_graph_dual_engine=lambda **_kwargs: {'text': 'ok'},
        ),
        inputs=inputs,
        started_at=1.0,
    )
    legacy_context = workflow.build_generate_execution_context(
        request=request,
        deps=_make_generate_deps(
            environ={'WRITING_AGENT_USE_ROUTE_GRAPH': '0'},
            run_generate_graph_dual_engine=lambda **_kwargs: {'text': 'ok'},
        ),
        inputs=inputs,
        started_at=1.0,
    )

    route_plan = workflow.build_generate_primary_branch_execution_plan(context=route_context)
    legacy_plan = workflow.build_generate_primary_branch_execution_plan(context=legacy_context)

    assert route_plan.use_route_graph is True
    assert route_plan.path == 'route_graph'
    assert legacy_plan.use_route_graph is False
    assert legacy_plan.path == 'legacy_graph'
