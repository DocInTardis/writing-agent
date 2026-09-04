"""Protect the migrated agent boundary without requiring a Web server or model."""

from __future__ import annotations

import ast
import inspect
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

import pytest

from writing_agent.web.services.generation_dependencies import build_generate_section_deps
from writing_agent.workflows.generate_request_workflow import GenerateGraphRequest, run_generate_graph_with_fallback
from writing_agent.workflows.generate_section_request_workflow import (
    GenerateSectionDeps,
    GenerateSectionRequest,
    run_generate_section_graph,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("module", ["generate_request_workflow", "generate_section_request_workflow"])
def test_migrated_workflow_does_not_reach_back_into_web(module):
    tree = ast.parse((ROOT / "writing_agent" / "workflows" / f"{module}.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(("writing_agent.web", "fastapi", "starlette"))
        elif isinstance(node, ast.Import):
            assert not any(item.name.startswith(("writing_agent.web", "fastapi", "starlette")) for item in node.names)
        elif isinstance(node, ast.Name):
            assert node.id != "app_v2"


@pytest.mark.parametrize("request_cls", [GenerateGraphRequest, GenerateSectionRequest])
def test_task_inputs_cannot_carry_the_web_application(request_cls):
    assert "app_v2" not in {field.name for field in fields(request_cls)}


@pytest.mark.parametrize("runner", [run_generate_graph_with_fallback, run_generate_section_graph])
def test_execution_requires_explicit_capabilities(runner):
    assert inspect.signature(runner).parameters["deps"].default is inspect.Parameter.empty


def test_web_adapter_snapshots_configuration_for_each_run():
    environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "0"}
    app = SimpleNamespace(os=SimpleNamespace(environ=environ), run_generate_graph=lambda **_: iter(()))
    deps = build_generate_section_deps(app)
    environ["WRITING_AGENT_USE_ROUTE_GRAPH"] = "1"
    assert deps.environ["WRITING_AGENT_USE_ROUTE_GRAPH"] == "0"
    assert build_generate_section_deps(app).environ["WRITING_AGENT_USE_ROUTE_GRAPH"] == "1"


@pytest.mark.parametrize("fails", [False, True])
def test_headless_section_execution_closes_model_stream(fails):
    closed = []

    def tool(**kwargs):
        assert kwargs["required_h2"] == ["Intro"]
        try:
            yield {"event": "delta", "text": "partial"}
            if fails:
                raise RuntimeError("model unavailable")
            yield {"event": "final", "text": "completed section"}
            pytest.fail("workflow must stop at final")
        finally:
            closed.append(True)

    request = GenerateSectionRequest(section="Intro", instruction="write", current_text="", cfg=object())
    deps = GenerateSectionDeps(environ={}, run_generate_graph=tool)
    if fails:
        with pytest.raises(RuntimeError, match="model unavailable"):
            run_generate_section_graph(request=request, deps=deps)
    else:
        assert run_generate_section_graph(request=request, deps=deps) == ("completed section", None)
    assert closed == [True]


def test_two_headless_runs_do_not_share_tools_or_configuration():
    request = GenerateSectionRequest(section="Intro", instruction="write", current_text="", cfg=object())
    first = GenerateSectionDeps(environ={}, run_generate_graph=lambda **_: iter([{"event": "final", "text": "one"}]))
    second = GenerateSectionDeps(environ={}, run_generate_graph=lambda **_: iter([{"event": "final", "text": "two"}]))
    assert run_generate_section_graph(request=request, deps=first)[0] == "one"
    assert run_generate_section_graph(request=request, deps=second)[0] == "two"
