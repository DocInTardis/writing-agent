from writing_agent.v2.rag_gate import filter_sources_for_section


def test_filter_sources_for_section_drops_document_relevant_but_section_irrelevant_source() -> None:
    sources = [
        {
            "title": "database schema design for writing agent system",
            "summary": "schema design storage index postgres table relation",
            "url": "https://example.com/db",
        },
        {
            "title": "user satisfaction evaluation for writing agent",
            "summary": "survey evaluation adoption experience writing agent",
            "url": "https://example.com/eval",
        },
    ]
    out = filter_sources_for_section(
        document_title="writing agent system design implementation",
        section_title="database schema design",
        sources=sources,
        min_theme_score=0.1,
        min_section_score=0.34,
        mode="strict",
    )
    kept_titles = [str(row.get("title") or "") for row in (out.get("kept") or [])]
    dropped_reasons = [str(row.get("reason") or "") for row in (out.get("dropped") or [])]
    assert kept_titles == ["database schema design for writing agent system"]
    assert "rag_section_theme_mismatch" in dropped_reasons
