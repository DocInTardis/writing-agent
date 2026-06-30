from writing_agent.v2.graph_runner_evidence_support_domain import _extract_sources_from_context


def test_extract_sources_supports_structured_context() -> None:
    context = (
        "[paper_id=openalex:W1 section_id=sec_1] A Study > Results [level=L2]\n"
        "https://example.org/study\n"
        "A concise section summary.\n"
        "[evidence_id=ev_1 p.8 type=result] Recall improved by 20 percent."
    )

    sources = _extract_sources_from_context(context)

    assert sources == [
        {
            "id": "openalex:W1",
            "paper_id": "openalex:W1",
            "section_id": "sec_1",
            "evidence_ids": ["ev_1"],
            "title": "A Study",
            "kind": "structured",
            "data_level": "L2",
            "url": "https://example.org/study",
        }
    ]
