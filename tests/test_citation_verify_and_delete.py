from __future__ import annotations

import json

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.models import Citation
from writing_agent.storage import InMemoryStore
from writing_agent.v2.rag.crossref import CrossrefSearchResult, CrossrefWork
from writing_agent.v2.rag.openalex import OpenAlexSearchResult, OpenAlexWork


def _client() -> TestClient:
    return TestClient(app_v2.app)


def _work(*, title: str, published: str, authors: list[str], abs_url: str) -> OpenAlexWork:
    return OpenAlexWork(
        paper_id="openalex:W1",
        title=title,
        summary="",
        authors=authors,
        published=published,
        updated=published,
        abs_url=abs_url,
        pdf_url="",
        categories=["Journal of LLM Studies"],
        primary_category="Journal of LLM Studies",
    )


def _crossref_work(*, title: str, published: str, authors: list[str], abs_url: str, doi: str) -> CrossrefWork:
    return CrossrefWork(
        paper_id="crossref:W1",
        title=title,
        summary="",
        authors=authors,
        published=published,
        updated=published,
        abs_url=abs_url,
        pdf_url="",
        categories=["Journal of LLM Studies"],
        primary_category="Journal of LLM Studies",
        doi=doi,
    )


def _empty_crossref_result() -> CrossrefSearchResult:
    return CrossrefSearchResult(query="q", max_results=8, works=[])


def _prepare_alert_config_isolation(monkeypatch, tmp_path):
    path = tmp_path / "citation_verify_alerts_config.json"
    events_path = tmp_path / "citation_verify_alert_events.json"
    trends_path = tmp_path / "citation_verify_metrics_trends.json"
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_ALERTS_CONFIG_PATH", path)
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_ALERTS_CONFIG_CACHE", None)
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_ALERTS_CONFIG_LOADED", False)
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_ALERT_EVENTS_PATH", events_path)
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_METRICS_TRENDS_PATH", trends_path)
    app_v2._citation_verify_alert_notify_state_reset()
    return path


def test_verify_one_citation_marks_verified_and_enriches_fields(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    cite = Citation(
        key="llm2024",
        title="Large Language Model Evaluation in Practice",
        authors="Alice Chen",
        year="2024",
        venue=None,
        url=None,
    )

    result = OpenAlexSearchResult(
        query="q",
        max_results=8,
        works=[
            _work(
                title="Large Language Model Evaluation in Practice",
                published="2024-05-02",
                authors=["Alice Chen", "Bob Li"],
                abs_url="https://openalex.org/W123",
            )
        ],
    )
    monkeypatch.setattr(app_v2, "search_openalex", lambda **_: result)
    monkeypatch.setattr(app_v2, "search_crossref", lambda **_: _empty_crossref_result())

    item, updated = app_v2._verify_one_citation(cite)

    assert item["status"] == "verified"
    assert item["provider"] == "openalex"
    assert float(item["score"]) >= 0.82
    assert item["matched_title"] == "Large Language Model Evaluation in Practice"
    assert item["matched_year"] == "2024"
    assert updated.url == "https://openalex.org/W123"
    assert updated.year == "2024"


def test_verify_one_citation_returns_not_found_for_low_confidence(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    cite = Citation(
        key="llm2024",
        title="Large Language Model Evaluation in Practice",
        authors="Alice Chen",
        year="2024",
        venue=None,
        url=None,
    )

    result = OpenAlexSearchResult(
        query="q",
        max_results=8,
        works=[
            _work(
                title="A Survey of Ancient Pottery in Bronze Age Europe",
                published="2005-01-01",
                authors=["Someone Else"],
                abs_url="https://openalex.org/W999",
            )
        ],
    )
    monkeypatch.setattr(app_v2, "search_openalex", lambda **_: result)
    monkeypatch.setattr(app_v2, "search_crossref", lambda **_: _empty_crossref_result())

    item, updated = app_v2._verify_one_citation(cite)

    assert item["status"] == "not_found"
    assert item["provider"] in {"openalex", "crossref"}
    assert item["reason"] == "low_confidence_match"
    assert updated == cite


def test_verify_one_citation_reports_search_error(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    cite = Citation(
        key="llm2024",
        title="Large Language Model Evaluation in Practice",
        authors="Alice Chen",
        year="2024",
        venue=None,
        url=None,
    )

    def _raise(**kwargs):
        raise TimeoutError("timeout")

    monkeypatch.setattr(app_v2, "search_openalex", _raise)
    monkeypatch.setattr(app_v2, "search_crossref", lambda **_: _empty_crossref_result())
    item, updated = app_v2._verify_one_citation(cite)

    assert item["status"] == "error"
    assert item["provider"] == "openalex+crossref"
    assert str(item["reason"]).startswith("search_error:")
    assert updated == cite


def test_verify_one_citation_falls_back_to_crossref_when_openalex_low_confidence(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    cite = Citation(
        key="llm2024",
        title="Large Language Model Evaluation in Practice",
        authors="Alice Chen",
        year="2024",
        venue=None,
        url=None,
    )

    openalex_result = OpenAlexSearchResult(
        query="q",
        max_results=8,
        works=[
            _work(
                title="A Survey of Ancient Pottery in Bronze Age Europe",
                published="2005-01-01",
                authors=["Someone Else"],
                abs_url="https://openalex.org/W999",
            )
        ],
    )
    crossref_result = CrossrefSearchResult(
        query="q",
        max_results=8,
        works=[
            _crossref_work(
                title="Large Language Model Evaluation in Practice",
                published="2024-05-02",
                authors=["Alice Chen", "Bob Li"],
                abs_url="https://doi.org/10.1234/llm.2024.01",
                doi="10.1234/llm.2024.01",
            )
        ],
    )
    monkeypatch.setattr(app_v2, "search_openalex", lambda **_: openalex_result)
    monkeypatch.setattr(app_v2, "search_crossref", lambda **_: crossref_result)

    item, updated = app_v2._verify_one_citation(cite)

    assert item["status"] == "verified"
    assert item["provider"] == "crossref"
    assert item["doi"] == "10.1234/llm.2024.01"
    assert updated.url == "https://doi.org/10.1234/llm.2024.01"


def test_verify_one_citation_uses_cache_for_same_query(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    cite = Citation(
        key="llm2024",
        title="Large Language Model Evaluation in Practice",
        authors="Alice Chen",
        year="2024",
        venue=None,
        url=None,
    )

    calls = {"openalex": 0, "crossref": 0}

    def _search_openalex(**kwargs):
        calls["openalex"] += 1
        return OpenAlexSearchResult(
            query="q",
            max_results=8,
            works=[
                _work(
                    title="A Survey of Ancient Pottery in Bronze Age Europe",
                    published="2005-01-01",
                    authors=["Someone Else"],
                    abs_url="https://openalex.org/W999",
                )
            ],
        )

    def _search_crossref(**kwargs):
        calls["crossref"] += 1
        return _empty_crossref_result()

    monkeypatch.setattr(app_v2, "search_openalex", _search_openalex)
    monkeypatch.setattr(app_v2, "search_crossref", _search_crossref)

    item1, updated1 = app_v2._verify_one_citation(cite)
    item2, updated2 = app_v2._verify_one_citation(cite)

    assert item1["status"] == "not_found"
    assert item2["status"] == "not_found"
    assert updated1 == cite
    assert updated2 == cite
    assert calls["openalex"] == 1
    assert calls["crossref"] == 1


def test_inmemory_store_delete_removes_session():
    store = InMemoryStore()
    session = store.create()

    assert store.get(session.id) is not None
    assert store.delete(session.id) is True
    assert store.get(session.id) is None
    assert store.delete(session.id) is False


def test_doc_delete_route_uses_store_delete(monkeypatch):
    called: dict[str, str] = {}

    def _fake_delete(doc_id: str) -> bool:
        called["doc_id"] = doc_id
        return True

    monkeypatch.setattr(app_v2.store, "delete", _fake_delete)
    client = _client()
    resp = client.post("/api/doc/abc123/delete")
    assert resp.status_code == 200
    assert called.get("doc_id") == "abc123"


def test_citation_verify_api_returns_debug_payload_and_cache_hit(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    session = app_v2.store.create()
    session.citations = {
        "llm2024": Citation(
            key="llm2024",
            title="Large Language Model Evaluation in Practice",
            authors="Alice Chen",
            year="2024",
            venue="",
            url="",
        )
    }
    app_v2.store.put(session)

    monkeypatch.setattr(
        app_v2,
        "search_openalex",
        lambda **_: OpenAlexSearchResult(
            query="q",
            max_results=8,
            works=[
                _work(
                    title="A Survey of Ancient Pottery in Bronze Age Europe",
                    published="2005-01-01",
                    authors=["Someone Else"],
                    abs_url="https://openalex.org/W999",
                )
            ],
        ),
    )
    monkeypatch.setattr(app_v2, "search_crossref", lambda **_: _empty_crossref_result())

    client = _client()
    resp1 = client.post(f"/api/doc/{session.id}/citations/verify", json={"persist": False, "debug": True})
    assert resp1.status_code == 200
    body1 = resp1.json()
    debug1 = body1.get("debug") if isinstance(body1, dict) else {}
    assert isinstance(debug1, dict)
    cache1 = debug1.get("cache")
    assert isinstance(cache1, dict)
    assert int(cache1.get("max_entries") or 0) >= 1
    assert int(cache1.get("set") or 0) >= 1
    assert isinstance(debug1.get("elapsed_ms"), (int, float))
    rows1 = debug1.get("items")
    assert isinstance(rows1, list) and rows1
    first1 = rows1[0] if isinstance(rows1[0], dict) else {}
    assert first1.get("cache_hit") is False
    assert "openalex" in (first1.get("providers") or {})

    resp2 = client.post(f"/api/doc/{session.id}/citations/verify", json={"persist": False, "debug": True})
    assert resp2.status_code == 200
    body2 = resp2.json()
    debug2 = body2.get("debug") if isinstance(body2, dict) else {}
    cache2 = debug2.get("cache")
    assert isinstance(cache2, dict)
    assert int(cache2.get("hit") or 0) >= 1
    assert int(cache2.get("miss") or 0) >= 1
    rows2 = debug2.get("items")
    assert isinstance(rows2, list) and rows2
    first2 = rows2[0] if isinstance(rows2[0], dict) else {}
    assert first2.get("cache_hit") is True


def test_citation_verify_api_default_response_has_no_debug(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    session = app_v2.store.create()
    session.citations = {
        "llm2024": Citation(
            key="llm2024",
            title="Large Language Model Evaluation in Practice",
            authors="Alice Chen",
            year="2024",
            venue="",
            url="",
        )
    }
    app_v2.store.put(session)

    monkeypatch.setattr(
        app_v2,
        "search_openalex",
        lambda **_: OpenAlexSearchResult(
            query="q",
            max_results=8,
            works=[
                _work(
                    title="A Survey of Ancient Pottery in Bronze Age Europe",
                    published="2005-01-01",
                    authors=["Someone Else"],
                    abs_url="https://openalex.org/W999",
                )
            ],
        ),
    )
    monkeypatch.setattr(app_v2, "search_crossref", lambda **_: _empty_crossref_result())

    client = _client()
    resp = client.post(f"/api/doc/{session.id}/citations/verify", json={"persist": False})
    assert resp.status_code == 200
    body = resp.json()
    assert "debug" not in body


def test_citation_verify_debug_safe_level_masks_sensitive_fields(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    session = app_v2.store.create()
    session.citations = {
        "llm2024": Citation(
            key="llm2024",
            title="Large Language Model Evaluation in Practice",
            authors="Alice Chen",
            year="2024",
            venue="",
            url="",
        )
    }
    app_v2.store.put(session)

    def _fake_verify_detail(cite: Citation):
        item = {
            "id": cite.key,
            "author": cite.authors or "",
            "title": cite.title or "",
            "year": cite.year or "",
            "source": cite.venue or cite.url or "",
            "status": "not_found",
            "provider": "openalex",
            "score": 0.22,
            "matched_title": "",
            "matched_year": "",
            "matched_source": "",
            "doi": "",
            "url": "",
            "reason": "low_confidence_match",
        }
        debug = {
            "cache_hit": False,
            "query": "alice@example.com sk-supersecrettoken123456 https://example.com/path?a=1&token=abcdef",
            "providers": {"openalex": 1, "crossref": 0},
            "errors": ["openalex:RuntimeError token=sk-abcdef1234567890"],
            "picked_provider": "openalex",
            "picked_title_score": 0.52,
            "picked_year_score": 0.1,
            "picked_total_score": 0.31,
            "elapsed_ms": 12.3,
        }
        return item, cite, debug

    monkeypatch.setattr(app_v2, "_verify_one_citation_detail", _fake_verify_detail)
    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/citations/verify",
        json={"persist": False, "debug": True, "debug_level": "safe"},
    )
    assert resp.status_code == 200
    body = resp.json()
    dbg = body.get("debug") if isinstance(body, dict) else {}
    assert isinstance(dbg, dict)
    assert dbg.get("level") == "safe"
    assert dbg.get("sanitized") is True
    items = dbg.get("items")
    assert isinstance(items, list) and items
    row = items[0] if isinstance(items[0], dict) else {}
    query = str(row.get("query") or "")
    errors = row.get("errors")
    assert "alice@example.com" not in query
    assert "sk-supersecrettoken123456" not in query
    assert "?a=1&token=abcdef" not in query
    assert isinstance(errors, list)
    assert all("sk-abcdef1234567890" not in str(x) for x in errors)


def test_citation_verify_debug_full_level_keeps_raw_fields(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    session = app_v2.store.create()
    session.citations = {
        "llm2024": Citation(
            key="llm2024",
            title="Large Language Model Evaluation in Practice",
            authors="Alice Chen",
            year="2024",
            venue="",
            url="",
        )
    }
    app_v2.store.put(session)

    raw_query = "alice@example.com sk-supersecrettoken123456 https://example.com/path?a=1&token=abcdef"
    raw_error = "openalex:RuntimeError token=sk-abcdef1234567890"

    def _fake_verify_detail(cite: Citation):
        item = {
            "id": cite.key,
            "author": cite.authors or "",
            "title": cite.title or "",
            "year": cite.year or "",
            "source": cite.venue or cite.url or "",
            "status": "not_found",
            "provider": "openalex",
            "score": 0.22,
            "matched_title": "",
            "matched_year": "",
            "matched_source": "",
            "doi": "",
            "url": "",
            "reason": "low_confidence_match",
        }
        debug = {
            "cache_hit": False,
            "query": raw_query,
            "providers": {"openalex": 1, "crossref": 0},
            "errors": [raw_error],
            "picked_provider": "openalex",
            "picked_title_score": 0.52,
            "picked_year_score": 0.1,
            "picked_total_score": 0.31,
            "elapsed_ms": 12.3,
        }
        return item, cite, debug

    monkeypatch.setattr(app_v2, "_verify_one_citation_detail", _fake_verify_detail)
    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/citations/verify",
        json={"persist": False, "debug": True, "debug_level": "full"},
    )
    assert resp.status_code == 200
    body = resp.json()
    dbg = body.get("debug") if isinstance(body, dict) else {}
    assert isinstance(dbg, dict)
    assert dbg.get("level") == "full"
    assert dbg.get("sanitized") is False
    items = dbg.get("items")
    assert isinstance(items, list) and items
    row = items[0] if isinstance(items[0], dict) else {}
    assert str(row.get("query") or "") == raw_query
    errors = row.get("errors")
    assert isinstance(errors, list) and errors
    assert str(errors[0]) == raw_error


def test_citation_verify_debug_strict_level_hides_query_and_errors(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    session = app_v2.store.create()
    session.citations = {
        "llm2024": Citation(
            key="llm2024",
            title="Large Language Model Evaluation in Practice",
            authors="Alice Chen",
            year="2024",
            venue="",
            url="",
        )
    }
    app_v2.store.put(session)

    def _fake_verify_detail(cite: Citation):
        item = {
            "id": cite.key,
            "author": cite.authors or "",
            "title": cite.title or "",
            "year": cite.year or "",
            "source": cite.venue or cite.url or "",
            "status": "not_found",
            "provider": "openalex",
            "score": 0.22,
            "matched_title": "",
            "matched_year": "",
            "matched_source": "",
            "doi": "",
            "url": "",
            "reason": "low_confidence_match",
        }
        debug = {
            "cache_hit": False,
            "query": "alice@example.com sk-supersecrettoken123456",
            "providers": {"openalex": 1, "crossref": 0},
            "errors": ["openalex:RuntimeError token=sk-abcdef1234567890"],
            "picked_provider": "openalex",
            "picked_title_score": 0.52,
            "picked_year_score": 0.1,
            "picked_total_score": 0.31,
            "elapsed_ms": 12.3,
        }
        return item, cite, debug

    monkeypatch.setattr(app_v2, "_verify_one_citation_detail", _fake_verify_detail)
    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/citations/verify",
        json={"persist": False, "debug": True, "debug_level": "strict"},
    )
    assert resp.status_code == 200
    body = resp.json()
    dbg = body.get("debug") if isinstance(body, dict) else {}
    assert isinstance(dbg, dict)
    assert dbg.get("requested_level") == "strict"
    assert dbg.get("level") == "strict"
    assert dbg.get("sanitized") is True
    items = dbg.get("items")
    assert isinstance(items, list) and items
    row = items[0] if isinstance(items[0], dict) else {}
    assert str(row.get("query") or "") == ""
    errors = row.get("errors")
    assert isinstance(errors, list) and len(errors) == 0


def test_citation_verify_debug_level_raw_alias_maps_to_full(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    monkeypatch.setattr(app_v2, "_DEBUG_FULL_RATE_BUCKETS", {})
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_DEBUG_FULL_MAX_PER_MIN", "8")
    session = app_v2.store.create()
    session.citations = {
        "llm2024": Citation(
            key="llm2024",
            title="Large Language Model Evaluation in Practice",
            authors="Alice Chen",
            year="2024",
            venue="",
            url="",
        )
    }
    app_v2.store.put(session)

    raw_query = "alice@example.com sk-supersecrettoken123456"

    def _fake_verify_detail(cite: Citation):
        item = {
            "id": cite.key,
            "author": cite.authors or "",
            "title": cite.title or "",
            "year": cite.year or "",
            "source": cite.venue or cite.url or "",
            "status": "not_found",
            "provider": "openalex",
            "score": 0.22,
            "matched_title": "",
            "matched_year": "",
            "matched_source": "",
            "doi": "",
            "url": "",
            "reason": "low_confidence_match",
        }
        debug = {
            "cache_hit": False,
            "query": raw_query,
            "providers": {"openalex": 1, "crossref": 0},
            "errors": [],
            "picked_provider": "openalex",
            "picked_title_score": 0.52,
            "picked_year_score": 0.1,
            "picked_total_score": 0.31,
            "elapsed_ms": 12.3,
        }
        return item, cite, debug

    monkeypatch.setattr(app_v2, "_verify_one_citation_detail", _fake_verify_detail)
    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/citations/verify",
        json={"persist": False, "debug": True, "debug_level": "raw"},
    )
    assert resp.status_code == 200
    body = resp.json()
    dbg = body.get("debug") if isinstance(body, dict) else {}
    assert isinstance(dbg, dict)
    assert dbg.get("requested_level") == "full"
    assert dbg.get("level") == "full"
    assert dbg.get("sanitized") is False
    items = dbg.get("items")
    assert isinstance(items, list) and items
    row = items[0] if isinstance(items[0], dict) else {}
    assert str(row.get("query") or "") == raw_query


def test_citation_verify_debug_full_is_rate_limited_and_downgraded(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    monkeypatch.setattr(app_v2, "_DEBUG_FULL_RATE_BUCKETS", {})
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_DEBUG_FULL_MAX_PER_MIN", "1")
    session = app_v2.store.create()
    session.citations = {
        "llm2024": Citation(
            key="llm2024",
            title="Large Language Model Evaluation in Practice",
            authors="Alice Chen",
            year="2024",
            venue="",
            url="",
        )
    }
    app_v2.store.put(session)

    def _fake_verify_detail(cite: Citation):
        item = {
            "id": cite.key,
            "author": cite.authors or "",
            "title": cite.title or "",
            "year": cite.year or "",
            "source": cite.venue or cite.url or "",
            "status": "not_found",
            "provider": "openalex",
            "score": 0.22,
            "matched_title": "",
            "matched_year": "",
            "matched_source": "",
            "doi": "",
            "url": "",
            "reason": "low_confidence_match",
        }
        debug = {
            "cache_hit": False,
            "query": "alice@example.com sk-supersecrettoken123456",
            "providers": {"openalex": 1, "crossref": 0},
            "errors": [],
            "picked_provider": "openalex",
            "picked_title_score": 0.52,
            "picked_year_score": 0.1,
            "picked_total_score": 0.31,
            "elapsed_ms": 12.3,
        }
        return item, cite, debug

    monkeypatch.setattr(app_v2, "_verify_one_citation_detail", _fake_verify_detail)
    client = _client()
    resp1 = client.post(
        f"/api/doc/{session.id}/citations/verify",
        json={"persist": False, "debug": True, "debug_level": "full"},
    )
    assert resp1.status_code == 200
    dbg1 = resp1.json().get("debug")
    assert isinstance(dbg1, dict)
    assert dbg1.get("requested_level") == "full"
    assert dbg1.get("level") == "full"
    assert dbg1.get("rate_limited_full") is False

    resp2 = client.post(
        f"/api/doc/{session.id}/citations/verify",
        json={"persist": False, "debug": True, "debug_level": "full"},
    )
    assert resp2.status_code == 200
    dbg2 = resp2.json().get("debug")
    assert isinstance(dbg2, dict)
    assert dbg2.get("requested_level") == "full"
    assert dbg2.get("level") == "safe"
    assert dbg2.get("rate_limited_full") is True


def test_citation_verify_debug_items_are_sampled(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_DEBUG_ITEM_SAMPLE_LIMIT", "2")
    session = app_v2.store.create()
    session.citations = {
        "a1": Citation(key="a1", title="Alpha", authors="A", year="2024", venue="", url=""),
        "b2": Citation(key="b2", title="Beta", authors="B", year="2024", venue="", url=""),
        "c3": Citation(key="c3", title="Gamma", authors="C", year="2024", venue="", url=""),
        "d4": Citation(key="d4", title="Delta", authors="D", year="2024", venue="", url=""),
    }
    app_v2.store.put(session)

    def _fake_verify_detail(cite: Citation):
        item = {
            "id": cite.key,
            "author": cite.authors or "",
            "title": cite.title or "",
            "year": cite.year or "",
            "source": cite.venue or cite.url or "",
            "status": "not_found",
            "provider": "openalex",
            "score": 0.11,
            "matched_title": "",
            "matched_year": "",
            "matched_source": "",
            "doi": "",
            "url": "",
            "reason": "low_confidence_match",
        }
        debug = {
            "cache_hit": False,
            "query": f"query-{cite.key}",
            "providers": {"openalex": 1, "crossref": 0},
            "errors": [],
            "picked_provider": "openalex",
            "picked_title_score": 0.1,
            "picked_year_score": 0.1,
            "picked_total_score": 0.1,
            "elapsed_ms": 1.0,
        }
        return item, cite, debug

    monkeypatch.setattr(app_v2, "_verify_one_citation_detail", _fake_verify_detail)
    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/citations/verify",
        json={"persist": False, "debug": True, "debug_level": "safe"},
    )
    assert resp.status_code == 200
    body = resp.json()
    dbg = body.get("debug")
    assert isinstance(dbg, dict)
    sampling = dbg.get("sampling")
    assert isinstance(sampling, dict)
    assert int(sampling.get("input_items") or 0) == 4
    assert int(sampling.get("output_items") or 0) == 2
    assert int(sampling.get("limit") or 0) == 2
    assert bool(sampling.get("truncated")) is True
    items = dbg.get("items")
    assert isinstance(items, list) and len(items) == 2


def test_citation_verify_debug_empty_payload_keeps_sampling_shape(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_DEBUG_ITEM_SAMPLE_LIMIT", "3")
    session = app_v2.store.create()
    session.citations = {}
    app_v2.store.put(session)

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/citations/verify",
        json={"persist": False, "debug": True, "debug_level": "safe"},
    )
    assert resp.status_code == 200
    body = resp.json()
    dbg = body.get("debug")
    assert isinstance(dbg, dict)
    sampling = dbg.get("sampling")
    assert isinstance(sampling, dict)
    assert int(sampling.get("input_items") or 0) == 0
    assert int(sampling.get("output_items") or 0) == 0
    assert int(sampling.get("limit") or 0) == 3
    assert bool(sampling.get("truncated")) is False
    items = dbg.get("items")
    assert isinstance(items, list) and len(items) == 0


def test_full_debug_rate_bucket_prunes_stale_and_caps_keys(monkeypatch):
    now = 1700000000.0
    floor = now - 60.0
    monkeypatch.setattr(app_v2, "_DEBUG_FULL_RATE_BUCKETS", {})
    monkeypatch.setattr(app_v2.time, "time", lambda: now)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_DEBUG_FULL_MAX_PER_MIN", "5")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_DEBUG_FULL_MAX_KEYS", "2")
    app_v2._DEBUG_FULL_RATE_BUCKETS.update(
        {
            "old_a": [now - 200.0],
            "old_b": [now - 120.0],
            "recent_1": [now - 5.0],
            "recent_2": [now - 4.0],
            "recent_3": [now - 3.0],
        }
    )

    allowed = app_v2._allow_full_debug("active_doc")
    assert allowed is True

    buckets = app_v2._DEBUG_FULL_RATE_BUCKETS
    assert "old_a" not in buckets
    assert "old_b" not in buckets
    assert "active_doc" in buckets
    assert len(buckets) <= 2
    for rows in buckets.values():
        assert isinstance(rows, list)
        assert rows
        assert all(float(ts) >= floor for ts in rows)


def test_citation_verify_max_workers_env_is_clamped(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", "-1")
    assert app_v2._citation_verify_max_workers(5) == 1

    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", "99")
    assert app_v2._citation_verify_max_workers(5) == 5

    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", "4")
    assert app_v2._citation_verify_max_workers(2) == 2


def test_citation_verify_effective_workers_reduces_on_high_latency(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", "8")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_WORKERS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_REDUCE_STEP", "3")
    monkeypatch.setattr(
        app_v2,
        "_citation_verify_observe_snapshot",
        lambda **_: {
            "runs": 12,
            "elapsed_ms": {"p95": 5200.0},
            "errors": {"rate_per_run": 0.02},
            "items": {"avg": 10.0},
        },
    )

    assert app_v2._citation_verify_effective_workers(10) == 5


def test_citation_verify_effective_workers_boosts_on_healthy_window(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", "4")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_WORKERS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_BOOST_STEP", "2")
    monkeypatch.setattr(
        app_v2,
        "_citation_verify_observe_snapshot",
        lambda **_: {
            "runs": 9,
            "elapsed_ms": {"p95": 1200.0},
            "errors": {"rate_per_run": 0.01},
            "items": {"avg": 6.0},
        },
    )

    # Base workers is 4, adaptive boost should lift to 6 for large enough batches.
    assert app_v2._citation_verify_effective_workers(10) == 6


