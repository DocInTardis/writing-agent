from __future__ import annotations

import json

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.models import Citation

def _client() -> TestClient:
    return TestClient(app_v2.app)

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


def test_citation_verify_effective_workers_falls_back_to_base_when_disabled_or_insufficient_history(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", "6")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_WORKERS", "0")
    monkeypatch.setattr(
        app_v2,
        "_citation_verify_observe_snapshot",
        lambda **_: {
            "runs": 12,
            "elapsed_ms": {"p95": 9000.0},
            "errors": {"rate_per_run": 0.9},
            "items": {"avg": 20.0},
        },
    )
    assert app_v2._citation_verify_effective_workers(10) == 6

    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_WORKERS", "1")
    monkeypatch.setattr(
        app_v2,
        "_citation_verify_observe_snapshot",
        lambda **_: {
            "runs": 4,
            "elapsed_ms": {"p95": 900.0},
            "errors": {"rate_per_run": 0.0},
            "items": {"avg": 12.0},
        },
    )
    assert app_v2._citation_verify_effective_workers(10) == 6

def test_citation_verify_debug_request_reports_worker_count(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", "3")
    session = app_v2.store.create()
    session.citations = {
        "a1": Citation(key="a1", title="Alpha", authors="A", year="2024", venue="", url=""),
        "b2": Citation(key="b2", title="Beta", authors="B", year="2024", venue="", url=""),
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
            "providers": {"openalex": 1},
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
    request_info = dbg.get("request")
    assert isinstance(request_info, dict)
    # Configured 3 workers but only 2 items, so effective workers should be 2.
    assert int(request_info.get("workers") or 0) == 2
    cache_info = dbg.get("cache")
    assert isinstance(cache_info, dict)
    assert int(cache_info.get("max_entries") or 0) >= 1

def test_citation_verify_debug_includes_observe_window(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE_METRICS", {"hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0})
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_OBSERVE_RUNS", [])
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", "2")
    session = app_v2.store.create()
    session.citations = {
        "a1": Citation(key="a1", title="Alpha", authors="A", year="2024", venue="", url=""),
        "b2": Citation(key="b2", title="Beta", authors="B", year="2024", venue="", url=""),
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
            "providers": {"openalex": 1},
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
    observe = dbg.get("observe")
    assert isinstance(observe, dict)
    req_obs = observe.get("request")
    assert isinstance(req_obs, dict)
    assert int(req_obs.get("item_count") or 0) == 2
    assert int(req_obs.get("worker_count") or 0) == 2
    assert isinstance(req_obs.get("cache_delta"), dict)
    window = observe.get("window")
    assert isinstance(window, dict)
    assert int(window.get("runs") or 0) >= 1
    assert isinstance(window.get("elapsed_ms"), dict)
    assert isinstance(window.get("workers"), dict)
    assert isinstance(window.get("cache_delta"), dict)
    recent = window.get("recent")
    assert isinstance(recent, list)
    assert len(recent) >= 1
    row = recent[-1] if isinstance(recent[-1], dict) else {}
    assert isinstance(row.get("cache_delta"), dict)
    assert isinstance((row.get("cache_delta") or {}).get("hit_rate"), (int, float))

def test_citation_verify_metrics_endpoint_returns_observe_snapshot(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE_METRICS", {"hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0})
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_OBSERVE_RUNS", [])
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", "1")
    session = app_v2.store.create()
    session.citations = {
        "a1": Citation(key="a1", title="Alpha", authors="A", year="2024", venue="", url=""),
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
            "providers": {"openalex": 1},
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
    resp_verify = client.post(
        f"/api/doc/{session.id}/citations/verify",
        json={"persist": False, "debug": False},
    )
    assert resp_verify.status_code == 200

    resp = client.get("/api/metrics/citation_verify")
    assert resp.status_code == 200
    body = resp.json()
    assert int(body.get("ok") or 0) == 1
    assert body.get("degraded") is False
    assert body.get("errors") == []
    alerts = body.get("alerts")
    assert isinstance(alerts, dict)
    assert alerts.get("enabled") is True
    assert alerts.get("severity") in {"ok", "warn", "critical"}
    assert isinstance(alerts.get("rules"), list)
    assert isinstance(alerts.get("triggered_rules"), list)
    assert isinstance(alerts.get("warmup"), bool)
    note = alerts.get("notification")
    assert isinstance(note, dict)
    assert note.get("enabled") in {True, False}
    assert isinstance(note.get("channels"), list)
    cache = body.get("cache")
    assert isinstance(cache, dict)
    assert int(cache.get("max_entries") or 0) >= 1
    observe = body.get("observe")
    assert isinstance(observe, dict)
    assert int(observe.get("runs") or 0) >= 1
    assert isinstance(observe.get("elapsed_ms"), dict)
    assert isinstance(observe.get("items"), dict)
    assert isinstance(observe.get("workers"), dict)
    assert isinstance(observe.get("errors"), dict)
    assert isinstance(observe.get("cache_delta"), dict)
    recent = observe.get("recent")
    assert isinstance(recent, list)
    assert len(recent) >= 1
    row = recent[-1] if isinstance(recent[-1], dict) else {}
    assert isinstance(row.get("cache_delta"), dict)
    assert isinstance((row.get("cache_delta") or {}).get("hit_rate"), (int, float))

def test_citation_verify_metrics_endpoint_soft_fails_when_snapshot_errors(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    def _boom_cache():
        raise RuntimeError("cache broken")

    def _boom_observe(*args, **kwargs):
        raise ValueError("observe broken")

    monkeypatch.setattr(app_v2, "_citation_verify_cache_snapshot", _boom_cache)
    monkeypatch.setattr(app_v2, "_citation_verify_observe_snapshot", _boom_observe)

    client = _client()
    resp = client.get("/api/metrics/citation_verify")
    assert resp.status_code == 200
    body = resp.json()
    assert int(body.get("ok") or 0) == 1
    assert body.get("degraded") is True
    errors = body.get("errors")
    assert isinstance(errors, list)
    assert any(str(err).startswith("cache_snapshot:") for err in errors)
    assert any(str(err).startswith("observe_snapshot:") for err in errors)

    cache = body.get("cache")
    assert isinstance(cache, dict)
    assert int(cache.get("size") or 0) == 0
    assert int(cache.get("max_entries") or 0) >= 1

    observe = body.get("observe")
    assert isinstance(observe, dict)
    assert int(observe.get("runs") or 0) == 0
    recent = observe.get("recent")
    assert isinstance(recent, list)
    assert len(recent) == 0
    alerts = body.get("alerts")
    assert isinstance(alerts, dict)
    assert alerts.get("enabled") in {True, False}
    assert alerts.get("severity") in {"ok", "warn", "critical"}
    assert isinstance(alerts.get("rules"), list)
    assert isinstance(alerts.get("triggered_rules"), list)
    note = alerts.get("notification")
    assert isinstance(note, dict)
    assert note.get("enabled") in {True, False}
    assert isinstance(note.get("channels"), list)

def test_citation_verify_metrics_endpoint_alerts_trigger_on_thresholds(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_P95_MS", "1200")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_ERROR_RATE", "0.2")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_HIT_RATE", "0.7")

    monkeypatch.setattr(
        app_v2,
        "_citation_verify_cache_snapshot",
        lambda: {
            "size": 12,
            "ttl_s": 3600.0,
            "max_entries": 2048,
            "hit": 10,
            "miss": 20,
            "set": 12,
            "expired": 0,
            "evicted": 0,
        },
    )
    monkeypatch.setattr(
        app_v2,
        "_citation_verify_observe_snapshot",
        lambda *args, **kwargs: {
            "window_s": 1800.0,
            "max_runs": 240,
            "runs": 9,
            "elapsed_ms": {"avg": 1600.0, "p50": 1200.0, "p95": 2800.0, "max": 4900.0},
            "items": {"total": 90, "avg": 10.0, "p50": 10.0, "p95": 14.0, "max": 20},
            "workers": {"avg": 4.0, "max": 6},
            "errors": {"total": 4, "rate_per_run": 0.44},
            "cache_delta": {"hit": 3, "miss": 12, "set": 10, "expired": 0, "evicted": 0, "hit_rate": 0.2},
            "recent": [],
        },
    )

    client = _client()
    resp = client.get("/api/metrics/citation_verify")
    assert resp.status_code == 200
    body = resp.json()
    assert int(body.get("ok") or 0) == 1
    assert body.get("degraded") is False
    alerts = body.get("alerts")
    assert isinstance(alerts, dict)
    assert alerts.get("enabled") is True
    assert alerts.get("warmup") is False
    assert alerts.get("severity") == "critical"
    assert int(alerts.get("triggered") or 0) >= 2
    triggered_rules = alerts.get("triggered_rules")
    assert isinstance(triggered_rules, list)
    assert "latency_p95_ms" in triggered_rules
    assert "error_rate_per_run" in triggered_rules
    assert "cache_delta_hit_rate" in triggered_rules

def test_citation_verify_alerts_config_endpoint_roundtrip(monkeypatch, tmp_path):
    path = _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "8")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_P95_MS", "4500")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_ERROR_RATE", "0.3")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_HIT_RATE", "0.35")

    client = _client()
    resp0 = client.get("/api/metrics/citation_verify/alerts/config")
    assert resp0.status_code == 200
    body0 = resp0.json()
    assert int(body0.get("ok") or 0) == 1
    assert body0.get("source") == "env"
    cfg0 = body0.get("config")
    assert isinstance(cfg0, dict)
    assert bool(cfg0.get("enabled")) is True
    assert int(cfg0.get("min_runs") or 0) == 8
    assert int(cfg0.get("p95_ms") or 0) == 4500

    resp1 = client.post(
        "/api/metrics/citation_verify/alerts/config",
        json={
            "config": {
                "enabled": False,
                "min_runs": 5,
                "p95_ms": 1800,
                "error_rate_per_run": 0.12,
                "cache_delta_hit_rate": 0.66,
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
    assert abs(float(cfg1.get("error_rate_per_run") or 0) - 0.12) < 1e-6
    assert path.exists()

    resp2 = client.get("/api/metrics/citation_verify/alerts/config")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2.get("source") == "file"
    cfg2 = body2.get("config")
    assert isinstance(cfg2, dict)
    assert bool(cfg2.get("enabled")) is False
    assert int(cfg2.get("p95_ms") or 0) == 1800

    resp3 = client.post("/api/metrics/citation_verify/alerts/config", json={"reset": True})
    assert resp3.status_code == 200
    body3 = resp3.json()
    assert int(body3.get("ok") or 0) == 1
    assert body3.get("source") == "env"
    assert bool(body3.get("reset")) is True
    assert not path.exists()

def test_citation_verify_metrics_alerts_use_saved_config(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "20")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_P95_MS", "9000")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_ERROR_RATE", "0.9")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_HIT_RATE", "0.1")

    client = _client()
    save_resp = client.post(
        "/api/metrics/citation_verify/alerts/config",
        json={
            "config": {
                "enabled": True,
                "min_runs": 1,
                "p95_ms": 1100,
                "error_rate_per_run": 0.2,
                "cache_delta_hit_rate": 0.8,
            }
        },
    )
    assert save_resp.status_code == 200
    assert int(save_resp.json().get("ok") or 0) == 1

    monkeypatch.setattr(
        app_v2,
        "_citation_verify_cache_snapshot",
        lambda: {
            "size": 1,
            "ttl_s": 3600.0,
            "max_entries": 2048,
            "hit": 1,
            "miss": 2,
            "set": 1,
            "expired": 0,
            "evicted": 0,
        },
    )
    monkeypatch.setattr(
        app_v2,
        "_citation_verify_observe_snapshot",
        lambda *args, **kwargs: {
            "window_s": 1800.0,
            "max_runs": 240,
            "runs": 5,
            "elapsed_ms": {"avg": 1700.0, "p50": 1200.0, "p95": 2600.0, "max": 4700.0},
            "items": {"total": 60, "avg": 12.0, "p50": 10.0, "p95": 18.0, "max": 22},
            "workers": {"avg": 4.0, "max": 6},
            "errors": {"total": 2, "rate_per_run": 0.4},
            "cache_delta": {"hit": 2, "miss": 8, "set": 4, "expired": 0, "evicted": 0, "hit_rate": 0.2},
            "recent": [],
        },
    )

    metrics_resp = client.get("/api/metrics/citation_verify")
    assert metrics_resp.status_code == 200
    body = metrics_resp.json()
    alerts = body.get("alerts")
    assert isinstance(alerts, dict)
    thresholds = alerts.get("thresholds")
    assert isinstance(thresholds, dict)
    assert int(thresholds.get("p95_ms") or 0) == 1100
    assert abs(float(thresholds.get("error_rate_per_run") or 0) - 0.2) < 1e-6
    assert abs(float(thresholds.get("cache_delta_hit_rate") or 0) - 0.8) < 1e-6
    assert alerts.get("warmup") is False
    assert alerts.get("severity") == "critical"
    triggered_rules = alerts.get("triggered_rules")
    assert isinstance(triggered_rules, list)
    assert "latency_p95_ms" in triggered_rules
    assert "error_rate_per_run" in triggered_rules
    assert "cache_delta_hit_rate" in triggered_rules

def test_citation_verify_alert_notification_suppressed_and_recover(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_P95_MS", "1000")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_ERROR_RATE", "0.2")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_HIT_RATE", "0.8")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_COOLDOWN_S", "300")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL", "")

    clock = [1700000000.0]
    monkeypatch.setattr(app_v2.time, "time", lambda: clock[0])
    monkeypatch.setattr(
        app_v2,
        "_citation_verify_cache_snapshot",
        lambda: {
            "size": 1,
            "ttl_s": 3600.0,
            "max_entries": 2048,
            "hit": 1,
            "miss": 2,
            "set": 1,
            "expired": 0,
            "evicted": 0,
        },
    )
    observe_bad = {
        "window_s": 1800.0,
        "max_runs": 240,
        "runs": 6,
        "elapsed_ms": {"avg": 1800.0, "p50": 1200.0, "p95": 2600.0, "max": 5200.0},
        "items": {"total": 60, "avg": 10.0, "p50": 10.0, "p95": 18.0, "max": 22},
        "workers": {"avg": 4.0, "max": 6},
        "errors": {"total": 3, "rate_per_run": 0.5},
        "cache_delta": {"hit": 2, "miss": 8, "set": 4, "expired": 0, "evicted": 0, "hit_rate": 0.2},
        "recent": [],
    }
    observe_ok = {
        "window_s": 1800.0,
        "max_runs": 240,
        "runs": 7,
        "elapsed_ms": {"avg": 800.0, "p50": 700.0, "p95": 900.0, "max": 1300.0},
        "items": {"total": 70, "avg": 10.0, "p50": 10.0, "p95": 12.0, "max": 16},
        "workers": {"avg": 3.0, "max": 4},
        "errors": {"total": 0, "rate_per_run": 0.0},
        "cache_delta": {"hit": 9, "miss": 1, "set": 2, "expired": 0, "evicted": 0, "hit_rate": 0.9},
        "recent": [],
    }
    state = {"observe": observe_bad}
    monkeypatch.setattr(app_v2, "_citation_verify_observe_snapshot", lambda *args, **kwargs: state["observe"])

    client = _client()
    first = client.get("/api/metrics/citation_verify")
    assert first.status_code == 200
    body1 = first.json()
    alerts1 = body1.get("alerts")
    assert isinstance(alerts1, dict)
    note1 = alerts1.get("notification")
    assert isinstance(note1, dict)
    assert note1.get("sent") is True
    assert note1.get("event_type") in {"raise", "change"}
    assert "log" in (note1.get("channels") or [])

    clock[0] += 15.0
    second = client.get("/api/metrics/citation_verify")
    assert second.status_code == 200
    note2 = (second.json().get("alerts") or {}).get("notification")
    assert isinstance(note2, dict)
    assert note2.get("sent") is False
    assert note2.get("status") == "suppressed"
    assert int(note2.get("suppressed") or 0) >= 1

    state["observe"] = observe_ok
    clock[0] += 5.0
    third = client.get("/api/metrics/citation_verify")
    assert third.status_code == 200
    body3 = third.json()
    assert ((body3.get("alerts") or {}).get("severity")) == "ok"
    note3 = (body3.get("alerts") or {}).get("notification")
    assert isinstance(note3, dict)
    assert note3.get("sent") is True
    assert note3.get("event_type") == "recover"

def test_citation_verify_alert_notification_webhook_channel(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_P95_MS", "1000")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_ERROR_RATE", "0.2")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_HIT_RATE", "0.8")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_COOLDOWN_S", "10")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL", "https://example.test/hook")

    calls: list[dict] = []

    def _fake_webhook(url: str, payload: dict, *, timeout_s: float):
        calls.append({"url": url, "payload": payload, "timeout_s": timeout_s})
        return True, "http_200"

    monkeypatch.setattr(app_v2, "_alert_notify_webhook", _fake_webhook)
    monkeypatch.setattr(
        app_v2,
        "_citation_verify_cache_snapshot",
        lambda: {
            "size": 1,
            "ttl_s": 3600.0,
            "max_entries": 2048,
            "hit": 1,
            "miss": 2,
            "set": 1,
            "expired": 0,
            "evicted": 0,
        },
    )
    monkeypatch.setattr(
        app_v2,
        "_citation_verify_observe_snapshot",
        lambda *args, **kwargs: {
            "window_s": 1800.0,
            "max_runs": 240,
            "runs": 6,
            "elapsed_ms": {"avg": 1800.0, "p50": 1200.0, "p95": 2600.0, "max": 5200.0},
            "items": {"total": 60, "avg": 10.0, "p50": 10.0, "p95": 18.0, "max": 22},
            "workers": {"avg": 4.0, "max": 6},
            "errors": {"total": 3, "rate_per_run": 0.5},
            "cache_delta": {"hit": 2, "miss": 8, "set": 4, "expired": 0, "evicted": 0, "hit_rate": 0.2},
            "recent": [],
        },
    )

    client = _client()
    resp = client.get("/api/metrics/citation_verify")
    assert resp.status_code == 200
    body = resp.json()
    note = (body.get("alerts") or {}).get("notification")
    assert isinstance(note, dict)
    assert note.get("sent") is True
    channels = note.get("channels")
    assert isinstance(channels, list)
    assert "log" in channels
    assert "webhook" in channels
    assert note.get("status") == "http_200"
    assert len(calls) == 1
    assert calls[0]["url"] == "https://example.test/hook"
    assert str((calls[0]["payload"] or {}).get("source") or "") == "citation_verify"

def test_citation_verify_alert_notification_signature_change_triggers_change(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_P95_MS", "1200")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_ERROR_RATE", "0.8")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_HIT_RATE", "0.7")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_COOLDOWN_S", "600")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL", "")

    clock = [1700000100.0]
    monkeypatch.setattr(app_v2.time, "time", lambda: clock[0])
    monkeypatch.setattr(
        app_v2,
        "_citation_verify_cache_snapshot",
        lambda: {
            "size": 1,
            "ttl_s": 3600.0,
            "max_entries": 2048,
            "hit": 1,
            "miss": 2,
            "set": 1,
            "expired": 0,
            "evicted": 0,
        },
    )
    state = {
        "observe": {
            "window_s": 1800.0,
            "max_runs": 240,
            "runs": 6,
            "elapsed_ms": {"avg": 1500.0, "p50": 1200.0, "p95": 2200.0, "max": 2600.0},
            "items": {"total": 60, "avg": 10.0, "p50": 10.0, "p95": 14.0, "max": 20},
            "workers": {"avg": 4.0, "max": 6},
            "errors": {"total": 0, "rate_per_run": 0.0},
            "cache_delta": {"hit": 9, "miss": 1, "set": 4, "expired": 0, "evicted": 0, "hit_rate": 0.9},
            "recent": [],
        }
    }
    monkeypatch.setattr(app_v2, "_citation_verify_observe_snapshot", lambda *args, **kwargs: state["observe"])

    client = _client()
    first = client.get("/api/metrics/citation_verify")
    assert first.status_code == 200
    note1 = ((first.json().get("alerts") or {}).get("notification") or {})
    assert note1.get("sent") is True
    assert note1.get("event_type") in {"raise", "change"}

    # Same severity(warn), but add low-hit-rate rule -> signature changes -> should notify "change".
    state["observe"] = {
        "window_s": 1800.0,
        "max_runs": 240,
        "runs": 7,
        "elapsed_ms": {"avg": 1500.0, "p50": 1200.0, "p95": 2200.0, "max": 2600.0},
        "items": {"total": 70, "avg": 10.0, "p50": 10.0, "p95": 14.0, "max": 20},
        "workers": {"avg": 4.0, "max": 6},
        "errors": {"total": 0, "rate_per_run": 0.0},
        "cache_delta": {"hit": 2, "miss": 8, "set": 4, "expired": 0, "evicted": 0, "hit_rate": 0.2},
        "recent": [],
    }
    clock[0] += 5.0
    second = client.get("/api/metrics/citation_verify")
    assert second.status_code == 200
    note2 = ((second.json().get("alerts") or {}).get("notification") or {})
    assert note2.get("sent") is True
    assert note2.get("event_type") == "change"
    assert note2.get("dedupe_hit") is False

