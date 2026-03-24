from __future__ import annotations

from types import SimpleNamespace

from writing_agent.v2 import graph_reference_domain as ref_domain
from writing_agent.v2.rag import retrieve as retrieve_module
from writing_agent.v2.rag import store as store_module


def _year(text: str) -> str:
    digits = ''.join(ch for ch in str(text or '') if ch.isdigit())
    return digits[:4]


def test_fallback_reference_sources_uses_crossref_and_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WRITING_AGENT_MIN_REFERENCE_ITEMS", "3")
    monkeypatch.setenv("WRITING_AGENT_REFERENCE_ONLINE_PROVIDERS", "crossref")
    monkeypatch.setenv("WRITING_AGENT_REFERENCE_QUERY_SEED_CAP", "1")

    calls = {"crossref": 0}

    def _fake_crossref(query_seed: str, *, max_results: int):
        calls["crossref"] += 1
        return [
            {
                "id": f"crossref:{idx}",
                "title": title,
                "url": f"https://example.test/{idx}",
                "authors": ["A. Author"],
                "published": f"202{idx}-01-01",
                "updated": f"202{idx}-01-01",
                "source": "crossref",
                "kind": "fallback_crossref",
            }
            for idx, title in enumerate(
                [
                    "Blockchain for decentralised rural development and governance",
                    "Hot Spots and Trends of Credit Research Based on Blockchain Technology-A CiteSpace Visual Analysis",
                    "The Impact of Agricultural Socialized Service on Grain Production: Evidence from Rural China",
                ],
                start=1,
            )
        ]

    monkeypatch.setattr(ref_domain, "_search_crossref_rows", _fake_crossref)
    monkeypatch.setattr(ref_domain, "_search_openalex_rows", lambda *args, **kwargs: [])
    monkeypatch.setattr(ref_domain, "_fallback_query_seeds", lambda query: ["blockchain rural service citespace"])
    monkeypatch.setattr(retrieve_module, "retrieve_context", lambda **kwargs: SimpleNamespace(context=""))

    class _EmptyStore:
        def __init__(self, _rag_dir):
            pass

        def list_papers(self):
            return []

    monkeypatch.setattr(store_module, "RagStore", _EmptyStore)

    query = "blockchain rural socialized service citespace"
    rows = ref_domain.fallback_reference_sources(
        instruction=query,
        mcp_rag_retrieve=lambda **kwargs: ("", []),
        extract_sources_from_context=lambda text: [],
        enrich_sources_with_rag_fn=lambda rows: rows,
        extract_year_fn=_year,
    )
    assert len(rows) >= 3
    assert calls["crossref"] == 1

    monkeypatch.setattr(ref_domain, "_search_crossref_rows", lambda *args, **kwargs: [])
    rows_cached = ref_domain.fallback_reference_sources(
        instruction=query,
        mcp_rag_retrieve=lambda **kwargs: ("", []),
        extract_sources_from_context=lambda text: [],
        enrich_sources_with_rag_fn=lambda rows: rows,
        extract_year_fn=_year,
    )
    assert len(rows_cached) >= 3



def test_sort_reference_sources_prefers_topical_entries():
    rows = [
        {
            "title": "Knowledge Mapping of Rural Elderly Health Research - A CiteSpace Bibliometric Analysis",
            "published": "2024-01-01",
            "updated": "2024-01-01",
            "authors": [],
            "url": "https://example.test/method",
            "source": "crossref",
        },
        {
            "title": "Blockchain for decentralised rural development and governance",
            "published": "2022-01-01",
            "updated": "2022-01-01",
            "authors": [],
            "url": "https://example.test/topic",
            "source": "crossref",
        },
        {
            "title": "Hot Spots and Trends of Credit Research Based on Blockchain Technology-A CiteSpace Visual Analysis",
            "published": "2023-01-01",
            "updated": "2023-01-01",
            "authors": [],
            "url": "https://example.test/mixed",
            "source": "crossref",
        },
    ]
    ranked = ref_domain.sort_reference_sources(
        rows,
        query="blockchain rural socialized service citespace",
        extract_year_fn=_year,
    )
    titles = [str(row.get("title") or "") for row in ranked]
    assert titles[0] in {
        "Hot Spots and Trends of Credit Research Based on Blockchain Technology-A CiteSpace Visual Analysis",
        "Blockchain for decentralised rural development and governance",
    }
    assert titles[1] in {
        "Hot Spots and Trends of Credit Research Based on Blockchain Technology-A CiteSpace Visual Analysis",
        "Blockchain for decentralised rural development and governance",
    }
    assert titles[-1] == "Knowledge Mapping of Rural Elderly Health Research - A CiteSpace Bibliometric Analysis"
