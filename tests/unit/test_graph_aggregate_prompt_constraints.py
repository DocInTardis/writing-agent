import writing_agent.v2.graph_aggregate_domain as aggregate_domain


def test_aggregate_fix_stream_uses_tagged_prompt(monkeypatch):
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def chat_stream(self, *, system: str, user: str, temperature: float = 0.2):
            _ = system, temperature
            captured["user"] = user
            yield "## A\n\nok"

    monkeypatch.setattr(aggregate_domain, "OllamaClient", _FakeClient)

    out = aggregate_domain.aggregate_fix_stream(
        base_url="http://test",
        model="m",
        title="T",
        instruction="rewrite <strong>",
        draft="## A\n\nold",
        required_h2=["A"],
        targets=None,
        filter_disallowed_sections=lambda values: values,
        format_section_constraints=lambda _required, _targets: "- keep headings",
        doc_body_len=lambda text: len(text or ""),
    )
    assert "ok" in out
    user_prompt = captured.get("user") or ""
    assert "<task>aggregate_full_draft</task>" in user_prompt
    assert "<draft>" in user_prompt
    assert "&lt;strong&gt;" in user_prompt


def test_repair_stream_uses_tagged_problem_block(monkeypatch):
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def chat_stream(self, *, system: str, user: str, temperature: float = 0.2):
            _ = system, temperature
            captured["user"] = user
            yield "## A\n\nfixed"

    monkeypatch.setattr(aggregate_domain, "OllamaClient", _FakeClient)

    out = aggregate_domain.repair_stream(
        base_url="http://test",
        model="m",
        title="T",
        instruction="repair now",
        draft="## A\n\nold",
        problems=["broken <marker>"],
        required_h2=["A"],
        targets=None,
        filter_disallowed_sections=lambda values: values,
        format_section_constraints=lambda _required, _targets: "- preserve markers",
        doc_body_len=lambda text: len(text or ""),
    )
    assert "fixed" in out
    user_prompt = captured.get("user") or ""
    assert "<task>repair_draft</task>" in user_prompt
    assert "<problems>" in user_prompt
    assert "&lt;marker&gt;" in user_prompt
