from __future__ import annotations

import json

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.models import Citation
from writing_agent.v2.rag.crossref import CrossrefWork
from writing_agent.web.services import citation_service


def _client() -> TestClient:
    return TestClient(app_v2.app)


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


def _prepare_resolve_alert_config_isolation(monkeypatch, tmp_path):
    path = tmp_path / "citation_resolve_alerts_config.json"
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_CONFIG_PATH", path.as_posix())
    citation_service._resolve_alerts_config_reset_cache()
    citation_service._resolve_observe_reset()
    return path


def test_resolve_url_doi_exact_match(monkeypatch):
    session = app_v2.store.create()
    app_v2.store.put(session)

    monkeypatch.setattr(
        citation_service,
        "_fetch_page_metadata",
        lambda url, **_: {
            "title": "Large Language Model Evaluation in Practice",
            "authors": ["Alice Chen"],
            "year": "2024",
            "source": "Journal of LLM Studies",
            "doi": "10.1234/llm.2024.01",
        },
    )
    monkeypatch.setattr(
        app_v2,
        "_collect_citation_candidates",
        lambda query: (
            [
                (
                    "crossref",
                    _crossref_work(
                        title="Large Language Model Evaluation in Practice",
                        published="2024-05-02",
                        authors=["Alice Chen", "Bob Li"],
                        abs_url="https://doi.org/10.1234/llm.2024.01",
                        doi="10.1234/llm.2024.01",
                    ),
                )
            ],
            [],
        ),
    )

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "https://doi.org/10.1234/llm.2024.01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert int(body.get("ok") or 0) == 1
    item = body.get("item") if isinstance(body, dict) else {}
    assert isinstance(item, dict)
    assert str(item.get("title") or "") == "Large Language Model Evaluation in Practice"
    assert str(item.get("url") or "") == "https://doi.org/10.1234/llm.2024.01"
    debug = body.get("debug") if isinstance(body, dict) else {}
    assert isinstance(debug, dict)
    assert str(debug.get("resolver") or "") == "doi_exact"
    assert str(debug.get("provider") or "") == "crossref"
    assert float(body.get("confidence") or 0.0) >= 0.95


def test_resolve_url_rejects_private_host():
    session = app_v2.store.create()
    app_v2.store.put(session)
    client = _client()

    resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "http://127.0.0.1/internal"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "not allowed" in str(body.get("detail") or "")


def test_resolve_url_returns_metadata_only_when_search_unavailable(monkeypatch):
    session = app_v2.store.create()
    app_v2.store.put(session)

    monkeypatch.setattr(
        citation_service,
        "_fetch_page_metadata",
        lambda url, **_: {
            "title": "Understanding Prompt Engineering",
            "authors": ["Jane Doe"],
            "year": "2025",
            "source": "Prompt Journal",
            "doi": "",
        },
    )
    monkeypatch.setattr(app_v2, "_collect_citation_candidates", lambda query: ([], ["openalex:TimeoutError"]))

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "https://example.com/prompt-paper"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert int(body.get("ok") or 0) == 1
    debug = body.get("debug") if isinstance(body, dict) else {}
    assert isinstance(debug, dict)
    assert str(debug.get("resolver") or "") == "metadata_only"
    assert float(body.get("confidence") or 0.0) == 0.45
    warnings = body.get("warnings")
    assert isinstance(warnings, list)
    assert "metadata_only" in warnings
    item = body.get("item") if isinstance(body, dict) else {}
    assert isinstance(item, dict)
    assert str(item.get("title") or "") == "Understanding Prompt Engineering"
    assert str(item.get("author") or "") == "Jane Doe"


def test_resolve_url_generates_unique_id_with_existing_citations(monkeypatch):
    session = app_v2.store.create()
    session.citations = {
        "smith2024large": Citation(
            key="smith2024large",
            title="Large Language Model Evaluation in Practice",
            authors="Alice Smith",
            year="2024",
            venue="Journal of LLM Studies",
            url="",
        )
    }
    app_v2.store.put(session)

    monkeypatch.setattr(
        citation_service,
        "_fetch_page_metadata",
        lambda url, **_: {
            "title": "Large Language Model Evaluation in Practice",
            "authors": ["Alice Smith"],
            "year": "2024",
            "source": "Journal of LLM Studies",
            "doi": "",
        },
    )
    monkeypatch.setattr(app_v2, "_collect_citation_candidates", lambda query: ([], []))

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "https://example.com/llm-eval"},
    )
    assert resp.status_code == 200
    body = resp.json()
    item = body.get("item") if isinstance(body, dict) else {}
    assert isinstance(item, dict)
    assert str(item.get("id") or "") == "smith2024large_2"


def test_resolve_url_metrics_tracks_success_failure_and_fallback(monkeypatch):
    citation_service._resolve_observe_reset()
    session = app_v2.store.create()
    app_v2.store.put(session)

    def _fake_fetch_metadata(url, **_):
        if "doi.org" in str(url):
            return {
                "title": "Large Language Model Evaluation in Practice",
                "authors": ["Alice Chen"],
                "year": "2024",
                "source": "Journal of LLM Studies",
                "doi": "10.1234/llm.2024.01",
            }
        return {
            "title": "Fallback Metadata Paper",
            "authors": ["Jane Doe"],
            "year": "2025",
            "source": "Prompt Journal",
            "doi": "",
        }

    def _fake_collect_candidates(query):
        q = str(query or "").lower()
        if "10.1234/llm.2024.01" in q or "large language model evaluation in practice" in q:
            return (
                [
                    (
                        "crossref",
                        _crossref_work(
                            title="Large Language Model Evaluation in Practice",
                            published="2024-05-02",
                            authors=["Alice Chen", "Bob Li"],
                            abs_url="https://doi.org/10.1234/llm.2024.01",
                            doi="10.1234/llm.2024.01",
                        ),
                    )
                ],
                [],
            )
        return ([], [])

    monkeypatch.setattr(citation_service, "_fetch_page_metadata", _fake_fetch_metadata)
    monkeypatch.setattr(app_v2, "_collect_citation_candidates", _fake_collect_candidates)

    client = _client()
    ok_resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "https://doi.org/10.1234/llm.2024.01"},
    )
    assert ok_resp.status_code == 200

    fallback_resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "https://example.com/fallback-only"},
    )
    assert fallback_resp.status_code == 200

    fail_resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "http://127.0.0.1/internal"},
    )
    assert fail_resp.status_code == 400

    metrics_resp = client.get("/api/metrics/citation_resolve_url?limit=10")
    assert metrics_resp.status_code == 200
    body = metrics_resp.json()
    assert int(body.get("ok") or 0) == 1
    totals = body.get("totals") if isinstance(body, dict) else {}
    assert isinstance(totals, dict)
    assert int(totals.get("requests") or 0) == 3
    assert int(totals.get("success") or 0) == 2
    assert int(totals.get("failed") or 0) == 1
    assert int(totals.get("metadata_only") or 0) >= 1
    resolvers = body.get("resolvers")
    assert isinstance(resolvers, dict)
    assert int(resolvers.get("doi_exact") or 0) >= 1
    assert int(resolvers.get("metadata_only") or 0) >= 1
    providers = body.get("providers")
    assert isinstance(providers, dict)
    assert int(providers.get("crossref") or 0) >= 1
    success_rate = float(body.get("success_rate") or 0.0)
    assert 0.6 <= success_rate <= 0.7
    fallback_rate = float(body.get("fallback_rate") or 0.0)
    assert 0.4 <= fallback_rate <= 0.6
    failure_rate = float(body.get("failure_rate") or 0.0)
    assert 0.3 <= failure_rate <= 0.4
    low_confidence_rate = float(body.get("low_confidence_rate") or 0.0)
    assert 0.0 <= low_confidence_rate <= 0.1
    alerts = body.get("alerts")
    assert isinstance(alerts, dict)
    assert alerts.get("enabled") is True
    assert str(alerts.get("severity") or "") in {"ok", "warn", "critical"}
    assert isinstance(alerts.get("rules"), list)
    notification = alerts.get("notification")
    assert isinstance(notification, dict)
    assert "status" in notification
    assert "events_recent" in notification
    recent = body.get("recent")
    assert isinstance(recent, list)
    assert len(recent) == 3
    citation_service._resolve_observe_reset()


def test_resolve_url_metrics_alerts_respect_thresholds(monkeypatch):
    citation_service._resolve_observe_reset()
    session = app_v2.store.create()
    app_v2.store.put(session)

    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_MIN_RUNS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_FAILURE_RATE", "0.20")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_FALLBACK_RATE", "0.20")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_P95_MS", "100")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_LOW_CONF_RATE", "0.20")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_NOTIFY", "1")
    monkeypatch.delenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_WEBHOOK_URL", raising=False)

    monkeypatch.setattr(
        citation_service,
        "_fetch_page_metadata",
        lambda url, **_: {
            "title": "Fallback Metadata Paper",
            "authors": ["Jane Doe"],
            "year": "2025",
            "source": "Prompt Journal",
            "doi": "",
        },
    )
    monkeypatch.setattr(app_v2, "_collect_citation_candidates", lambda query: ([], []))

    client = _client()
    ok_resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "https://example.com/fallback-only"},
    )
    assert ok_resp.status_code == 200

    fail_resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "http://127.0.0.1/internal"},
    )
    assert fail_resp.status_code == 400

    metrics_resp = client.get("/api/metrics/citation_resolve_url?limit=10")
    assert metrics_resp.status_code == 200
    body = metrics_resp.json()
    alerts = body.get("alerts") if isinstance(body, dict) else {}
    assert isinstance(alerts, dict)
    assert alerts.get("enabled") is True
    assert str(alerts.get("severity") or "") == "critical"
    assert int(alerts.get("triggered") or 0) >= 1
    triggered_rules = alerts.get("triggered_rules")
    assert isinstance(triggered_rules, list)
    assert "failure_rate" in triggered_rules
    rules = alerts.get("rules")
    assert isinstance(rules, list) and rules
    assert any(str((row or {}).get("id") or "") == "failure_rate" for row in rules if isinstance(row, dict))
    notification = alerts.get("notification")
    assert isinstance(notification, dict)
    assert str(notification.get("status") or "") == "no_webhook"
    citation_service._resolve_observe_reset()


def test_resolve_url_metrics_alerts_send_and_dedupe(monkeypatch):
    citation_service._resolve_observe_reset()
    session = app_v2.store.create()
    app_v2.store.put(session)

    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_MIN_RUNS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_FAILURE_RATE", "0.10")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_NOTIFY", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_WEBHOOK_URL", "https://notify.example/webhook")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_NOTIFY_COOLDOWN_S", "30")

    monkeypatch.setattr(
        citation_service,
        "_fetch_page_metadata",
        lambda url, **_: {
            "title": "Fallback Metadata Paper",
            "authors": ["Jane Doe"],
            "year": "2025",
            "source": "Prompt Journal",
            "doi": "",
        },
    )
    monkeypatch.setattr(app_v2, "_collect_citation_candidates", lambda query: ([], []))

    sent: list[dict] = []

    def _fake_notify(url: str, payload: dict, *, timeout_s: float):
        sent.append({"url": url, "payload": payload, "timeout_s": timeout_s})
        return True, "http_200"

    monkeypatch.setattr(citation_service, "_resolve_alert_notify_webhook", _fake_notify)

    client = _client()
    ok_resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "https://example.com/fallback-only"},
    )
    assert ok_resp.status_code == 200

    fail_resp = client.post(
        f"/api/doc/{session.id}/citations/resolve-url",
        json={"url": "http://127.0.0.1/internal"},
    )
    assert fail_resp.status_code == 400

    first = client.get("/api/metrics/citation_resolve_url?limit=10")
    assert first.status_code == 200
    body1 = first.json()
    alerts1 = body1.get("alerts") if isinstance(body1, dict) else {}
    notification1 = alerts1.get("notification") if isinstance(alerts1, dict) else {}
    assert isinstance(notification1, dict)
    assert notification1.get("sent") is True
    assert str(notification1.get("status") or "") == "http_200"
    assert len(sent) == 1

    second = client.get("/api/metrics/citation_resolve_url?limit=10")
    assert second.status_code == 200
    body2 = second.json()
    alerts2 = body2.get("alerts") if isinstance(body2, dict) else {}
    notification2 = alerts2.get("notification") if isinstance(alerts2, dict) else {}
    assert isinstance(notification2, dict)
    assert notification2.get("dedupe_hit") is True
    assert str(notification2.get("status") or "") == "dedupe_skip"
    assert len(sent) == 1
    citation_service._resolve_observe_reset()


def test_resolve_url_alerts_config_endpoint_roundtrip(monkeypatch, tmp_path):
    path = _prepare_resolve_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_MIN_RUNS", "8")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_FAILURE_RATE", "0.35")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_FALLBACK_RATE", "0.55")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_P95_MS", "4500")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_LOW_CONF_RATE", "0.40")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_NOTIFY", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_NOTIFY_COOLDOWN_S", "300")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_NOTIFY_TIMEOUT_S", "4")

    client = _client()
    resp0 = client.get("/api/metrics/citation_resolve_url/alerts/config")
    assert resp0.status_code == 200
    body0 = resp0.json()
    assert int(body0.get("ok") or 0) == 1
    assert body0.get("source") == "env"
    cfg0 = body0.get("config")
    assert isinstance(cfg0, dict)
    assert bool(cfg0.get("enabled")) is True
    assert int(cfg0.get("min_runs") or 0) == 8
    assert abs(float(cfg0.get("failure_rate") or 0) - 0.35) < 1e-6
    assert abs(float(cfg0.get("fallback_rate") or 0) - 0.55) < 1e-6
    assert int(cfg0.get("p95_ms") or 0) == 4500
    assert abs(float(cfg0.get("low_confidence_rate") or 0) - 0.40) < 1e-6
    assert bool(cfg0.get("notify_enabled")) is True

    resp1 = client.post(
        "/api/metrics/citation_resolve_url/alerts/config",
        json={
            "config": {
                "enabled": False,
                "min_runs": 5,
                "failure_rate": 0.22,
                "fallback_rate": 0.33,
                "p95_ms": 1800,
                "low_confidence_rate": 0.27,
                "notify_enabled": False,
                "notify_cooldown_s": 120,
                "notify_timeout_s": 7,
            }
        },
    )
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert int(body1.get("ok") or 0) == 1
    assert body1.get("source") == "file"
    cfg1 = body1.get("config")
    assert isinstance(cfg1, dict)
    assert bool(cfg1.get("enabled")) is False
    assert int(cfg1.get("min_runs") or 0) == 5
    assert abs(float(cfg1.get("failure_rate") or 0) - 0.22) < 1e-6
    assert abs(float(cfg1.get("fallback_rate") or 0) - 0.33) < 1e-6
    assert int(cfg1.get("p95_ms") or 0) == 1800
    assert abs(float(cfg1.get("low_confidence_rate") or 0) - 0.27) < 1e-6
    assert bool(cfg1.get("notify_enabled")) is False
    assert int(cfg1.get("notify_cooldown_s") or 0) == 120
    assert int(cfg1.get("notify_timeout_s") or 0) == 7
    assert path.exists()

    resp2 = client.get("/api/metrics/citation_resolve_url/alerts/config")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2.get("source") == "file"
    cfg2 = body2.get("config")
    assert isinstance(cfg2, dict)
    assert bool(cfg2.get("enabled")) is False
    assert int(cfg2.get("min_runs") or 0) == 5
    assert int(cfg2.get("p95_ms") or 0) == 1800
    assert bool(cfg2.get("notify_enabled")) is False

    resp3 = client.post("/api/metrics/citation_resolve_url/alerts/config", json={"reset": True})
    assert resp3.status_code == 200
    body3 = resp3.json()
    assert int(body3.get("ok") or 0) == 1
    assert body3.get("source") == "env"
    assert bool(body3.get("reset")) is True
    assert not path.exists()
    citation_service._resolve_alerts_config_reset_cache()


def test_resolve_url_metrics_alerts_use_saved_config(monkeypatch, tmp_path):
    _prepare_resolve_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_MIN_RUNS", "20")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_FAILURE_RATE", "0.90")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_FALLBACK_RATE", "0.90")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_P95_MS", "9000")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_LOW_CONF_RATE", "0.90")
    monkeypatch.setenv("WRITING_AGENT_CITATION_RESOLVE_ALERT_NOTIFY", "1")

    client = _client()
    save_resp = client.post(
        "/api/metrics/citation_resolve_url/alerts/config",
        json={
            "config": {
                "enabled": True,
                "min_runs": 1,
                "failure_rate": 0.2,
                "fallback_rate": 0.2,
                "p95_ms": 1000,
                "low_confidence_rate": 0.2,
                "notify_enabled": False,
                "notify_cooldown_s": 30,
                "notify_timeout_s": 5,
            }
        },
    )
    assert save_resp.status_code == 200
    assert int(save_resp.json().get("ok") or 0) == 1

    citation_service._resolve_observe_record(
        ok=True,
        elapsed_ms=3200,
        resolver="metadata_only",
        provider="metadata",
        confidence=0.35,
        warnings=["metadata_only", "low_confidence_match"],
    )
    citation_service._resolve_observe_record(
        ok=False,
        elapsed_ms=120,
        resolver="invalid_url",
        provider="metadata",
        confidence=0.0,
        warnings=[],
        error="url host is not allowed",
    )

    metrics_resp = client.get("/api/metrics/citation_resolve_url?limit=10")
    assert metrics_resp.status_code == 200
    body = metrics_resp.json()
    alerts = body.get("alerts") if isinstance(body, dict) else {}
    assert isinstance(alerts, dict)
    thresholds = alerts.get("thresholds")
    assert isinstance(thresholds, dict)
    assert abs(float(thresholds.get("failure_rate") or 0) - 0.2) < 1e-6
    assert abs(float(thresholds.get("fallback_rate") or 0) - 0.2) < 1e-6
    assert int(thresholds.get("p95_ms") or 0) == 1000
    assert abs(float(thresholds.get("low_confidence_rate") or 0) - 0.2) < 1e-6
    assert alerts.get("warmup") is False
    assert str(alerts.get("severity") or "") == "critical"
    triggered_rules = alerts.get("triggered_rules")
    assert isinstance(triggered_rules, list)
    assert "failure_rate" in triggered_rules
    assert "fallback_rate" in triggered_rules
    assert "p95_ms" in triggered_rules
    assert "low_confidence_rate" in triggered_rules
    notification = alerts.get("notification")
    assert isinstance(notification, dict)
    assert notification.get("enabled") is False
    assert str(notification.get("status") or "") == "notify_disabled"

    citation_service._resolve_observe_reset()
    citation_service._resolve_alerts_config_reset()
    citation_service._resolve_alerts_config_reset_cache()


def test_resolve_url_alerts_config_admin_key_guard(monkeypatch, tmp_path):
    _prepare_resolve_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_ADMIN_API_KEY", "resolve-secret")

    client = _client()
    no_key_get = client.get("/api/metrics/citation_resolve_url/alerts/config")
    assert no_key_get.status_code == 403
    no_key_post = client.post("/api/metrics/citation_resolve_url/alerts/config", json={"config": {"enabled": False}})
    assert no_key_post.status_code == 403

    headers = {"X-Admin-Key": "resolve-secret"}
    ok_get = client.get("/api/metrics/citation_resolve_url/alerts/config", headers=headers)
    assert ok_get.status_code == 200
    ok_post = client.post(
        "/api/metrics/citation_resolve_url/alerts/config",
        headers=headers,
        json={"config": {"enabled": False}},
    )
    assert ok_post.status_code == 200
    citation_service._resolve_alerts_config_reset()
    citation_service._resolve_alerts_config_reset_cache()


def test_resolve_url_alerts_config_ops_rbac_role_separation(monkeypatch, tmp_path):
    _prepare_resolve_alert_config_isolation(monkeypatch, tmp_path)
    policy_path = tmp_path / "ops_rbac_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "roles": {
                    "viewer": ["alerts.read"],
                    "operator": ["alerts.read", "alerts.write"],
                    "admin": ["*"],
                },
                "principals": [
                    {"id": "viewer", "role": "viewer", "token_env": "WRITING_AGENT_OPS_VIEWER_API_KEY"},
                    {"id": "operator", "role": "operator", "token_env": "WRITING_AGENT_OPS_OPERATOR_API_KEY"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("WRITING_AGENT_OPS_RBAC_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_OPS_RBAC_POLICY", policy_path.as_posix())
    monkeypatch.setenv("WRITING_AGENT_ADMIN_API_KEY", "admin-ops-key")
    monkeypatch.setenv("WRITING_AGENT_OPS_VIEWER_API_KEY", "viewer-key")
    monkeypatch.setenv("WRITING_AGENT_OPS_OPERATOR_API_KEY", "operator-key")

    client = _client()
    no_key_get = client.get("/api/metrics/citation_resolve_url/alerts/config")
    assert no_key_get.status_code == 403

    viewer_headers = {"X-Admin-Key": "viewer-key"}
    viewer_get = client.get("/api/metrics/citation_resolve_url/alerts/config", headers=viewer_headers)
    assert viewer_get.status_code == 200
    viewer_post = client.post(
        "/api/metrics/citation_resolve_url/alerts/config",
        headers=viewer_headers,
        json={"config": {"enabled": True}},
    )
    assert viewer_post.status_code == 403

    operator_headers = {"X-Admin-Key": "operator-key"}
    operator_post = client.post(
        "/api/metrics/citation_resolve_url/alerts/config",
        headers=operator_headers,
        json={"config": {"enabled": False}},
    )
    assert operator_post.status_code == 200

    admin_headers = {"X-Admin-Key": "admin-ops-key"}
    admin_post = client.post(
        "/api/metrics/citation_resolve_url/alerts/config",
        headers=admin_headers,
        json={"config": {"enabled": True}},
    )
    assert admin_post.status_code == 200
    citation_service._resolve_alerts_config_reset()
    citation_service._resolve_alerts_config_reset_cache()
