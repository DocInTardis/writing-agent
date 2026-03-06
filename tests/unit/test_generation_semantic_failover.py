from dataclasses import dataclass

from writing_agent.web.services.generation_service import GenerationService


@dataclass
class _Session:
    template_required_h2: list[str]
    template_outline: list
    generation_prefs: dict


def test_semantic_failure_does_not_trigger_single_pass_fallback(monkeypatch) -> None:
    service = GenerationService()
    called = {"single_pass": 0}

    class _FakeOS:
        environ = {
            "WRITING_AGENT_USE_ROUTE_GRAPH": "1",
            "WRITING_AGENT_WORKERS": "2",
        }

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
    final_text, problems, graph_meta = service._run_graph_with_fallback(
        app_v2=_FakeApp(),
        session=session,
        instruction="请写论文",
        raw_instruction="请写论文",
        compose_mode="auto",
        resume_sections=[],
        base_text="",
        cfg=object(),
        target_chars=1200,
        plan_confirm={},
    )
    assert called["single_pass"] == 0
    assert final_text == ""
    assert "analysis_needs_clarification" in problems
    assert graph_meta["terminal_status"] == "failed"
    assert graph_meta["failure_reason"] == "analysis_needs_clarification"
