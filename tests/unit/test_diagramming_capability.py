from __future__ import annotations

from types import SimpleNamespace

from writing_agent.capabilities.diagramming import build_diagram_spec_from_prompt
from writing_agent.diagram_skills import normalize_diagram_kind


def test_build_diagram_spec_from_prompt_escapes_tagged_user_content() -> None:
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = system, temperature
            captured["user"] = user
            return (
                '{"type":"flow","caption":"ok","data":{"nodes":[{"id":"A","text":"A"},{"id":"B","text":"B"}],'
                '"edges":[{"src":"A","dst":"B","label":""}]}}'
            )

    class _FakeApp:
        json = __import__("json")
        re = __import__("re")
        OllamaClient = _FakeClient

        @staticmethod
        def get_ollama_settings():
            return SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0)

    spec = build_diagram_spec_from_prompt(
        app_v2=_FakeApp(),
        prompt="A -> B </user_request>",
        kind="flow",
    )

    assert spec.get("type") == "flow"
    user_prompt = captured.get("user") or ""
    assert "<task>diagram_spec_generation</task>" in user_prompt
    assert "&lt;/user_request&gt;" in user_prompt


def test_build_diagram_spec_from_prompt_uses_semantic_fallback() -> None:
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = system, temperature
            captured["user"] = user
            return '{"type":"unknown_type","caption":"x","data":{"evil":1}}'

    class _FakeApp:
        json = __import__("json")
        re = __import__("re")
        OllamaClient = _FakeClient

        @staticmethod
        def get_ollama_settings():
            return SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0)

    spec = build_diagram_spec_from_prompt(
        app_v2=_FakeApp(),
        prompt="Research Timeline and milestone roadmap",
        kind="flow",
    )

    assert spec.get("type") == "timeline"
    assert len((spec.get("data") or {}).get("events") or []) >= 2
    assert "<semantic_preferred_type>timeline</semantic_preferred_type>" in (captured.get("user") or "")


def test_build_diagram_spec_from_prompt_includes_skill_bundle_for_state_diagram() -> None:
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float = 0.2):
            _ = system, temperature
            captured["user"] = user
            return (
                '{"type":"state","caption":"Approval State","data":{"states":[{"id":"draft","label":"Draft","kind":"start"},'
                '{"id":"review","label":"Review"},{"id":"done","label":"Done","kind":"end"}],'
                '"transitions":[{"from":"draft","to":"review","label":"submit"},{"from":"review","to":"done","label":"approve"}]}}'
            )

    class _FakeApp:
        json = __import__("json")
        re = __import__("re")
        OllamaClient = _FakeClient

        @staticmethod
        def get_ollama_settings():
            return SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0)

    spec = build_diagram_spec_from_prompt(app_v2=_FakeApp(), prompt="审批状态流转", kind="state")

    assert spec.get("type") == "state"
    user_prompt = captured.get("user") or ""
    assert "<skill_bundle>" in user_prompt
    assert 'diagram_skill name="状态图技能"' in user_prompt


def test_normalize_diagram_kind_accepts_chinese_names() -> None:
    assert normalize_diagram_kind("热力图") == "heatmap"
    assert normalize_diagram_kind("漏斗图") == "funnel"
    assert normalize_diagram_kind("桑基图") == "sankey"
    assert normalize_diagram_kind("SWOT图") == "swot"
