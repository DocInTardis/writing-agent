from __future__ import annotations

from dataclasses import dataclass

from writing_agent.workflows.generate_section_request_workflow import GenerateSectionRequest, run_generate_section_graph


@dataclass
class _Session:
    generation_prefs: dict


def test_generate_section_request_workflow_uses_route_graph() -> None:
    class _FakeOS:
        environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "1"}

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph_dual_engine(**_kwargs):
            return {
                "text": "# Title\n\n## Intro\nsection text",
                "trace_id": "trace-section",
                "engine": "native",
                "route_id": "resume_sections",
                "route_entry": "writer",
            }

    final_text, graph_meta = run_generate_section_graph(
        request=GenerateSectionRequest(
            app_v2=_FakeApp(),
            session=_Session(generation_prefs={}),
            section="Intro",
            instruction="continue intro",
            current_text="# Title\n\n## Intro\nold",
            cfg=object(),
        )
    )

    assert "section text" in final_text
    assert graph_meta is not None
    assert graph_meta.get("path") == "route_graph"
    assert graph_meta.get("route_id") == "resume_sections"
    assert graph_meta.get("route_entry") == "writer"


def test_generate_section_request_workflow_uses_legacy_graph_when_disabled() -> None:
    class _FakeOS:
        environ = {"WRITING_AGENT_USE_ROUTE_GRAPH": "0"}

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph(**_kwargs):
            yield {"event": "final", "text": "# Title\n\n## Intro\nlegacy section text"}

    final_text, graph_meta = run_generate_section_graph(
        request=GenerateSectionRequest(
            app_v2=_FakeApp(),
            session=_Session(generation_prefs={}),
            section="Intro",
            instruction="continue intro",
            current_text="# Title\n\n## Intro\nold",
            cfg=object(),
        )
    )

    assert "legacy section text" in final_text
    assert graph_meta is None
