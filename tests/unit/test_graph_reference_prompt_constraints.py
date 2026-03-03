import writing_agent.v2.graph_reference_domain as reference_domain


def test_summarize_evidence_uses_tagged_channels_and_escape():
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

    def _fake_require_json_response(*, client, system: str, user: str, stage: str, temperature: float, max_retries: int):
        _ = client, stage, temperature, max_retries
        captured["system"] = system
        captured["user"] = user
        return {"facts": [], "missing": []}

    out = reference_domain.summarize_evidence(
        base_url="http://test",
        model="m",
        section="Method <s>",
        analysis_summary="Need facts </analysis_summary>",
        context="Material </evidence_material>",
        sources=[
            {"title": "Paper <1>", "url": "https://example.com?id=<x>"},
        ],
        require_json_response=_fake_require_json_response,
        ollama_client_cls=_FakeClient,
    )

    assert out == {"facts": [], "missing": []}
    assert "Return JSON only" in (captured.get("system") or "")
    user_prompt = captured.get("user") or ""
    assert "<task>evidence_extraction</task>" in user_prompt
    assert "<available_sources>" in user_prompt
    assert "<evidence_material>" in user_prompt
    assert "&lt;/analysis_summary&gt;" in user_prompt
    assert "&lt;/evidence_material&gt;" in user_prompt
    assert "Paper &lt;1&gt;" in user_prompt
