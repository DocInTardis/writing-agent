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


def test_format_reference_items_emits_gbt_style_for_online_sources():
    rows = reference_domain.format_reference_items(
        [
            {
                "title": "Structured Outputs",
                "authors": ["OpenAI"],
                "published": "2024-08-06",
                "updated": "",
                "source": "OpenAI",
                "url": "https://platform.openai.com/docs/guides/structured-output",
            }
        ],
        extract_year_fn=lambda text: "2024",
        format_authors_fn=lambda authors: "; ".join(authors),
    )
    assert len(rows) == 1
    line = rows[0]
    assert line.startswith("[1] ")
    assert "[EB/OL]" in line
    assert "https://platform.openai.com/docs/guides/structured-output" in line


def test_format_reference_items_emits_gbt_style_for_journal_like_rows():
    rows = reference_domain.format_reference_items(
        [
            {
                "title": "A Survey on Writing Agents",
                "authors": ["Smith J"],
                "published": "2022",
                "updated": "",
                "source": "Journal of Intelligent Systems",
                "url": "",
            }
        ],
        extract_year_fn=lambda text: "2022",
        format_authors_fn=lambda authors: "; ".join(authors),
    )
    assert len(rows) == 1
    line = rows[0]
    assert "[J]" in line
    assert "Journal of Intelligent Systems, 2022." in line
