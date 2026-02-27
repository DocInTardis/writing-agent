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



def test_citation_verify_alert_events_endpoint_returns_recent(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_COOLDOWN_S", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL", "")

    clock = [1700000200.0]
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
    levels = [
        {
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
        {
            "window_s": 1800.0,
            "max_runs": 240,
            "runs": 7,
            "elapsed_ms": {"avg": 900.0, "p50": 700.0, "p95": 900.0, "max": 1300.0},
            "items": {"total": 70, "avg": 10.0, "p50": 10.0, "p95": 12.0, "max": 16},
            "workers": {"avg": 3.0, "max": 4},
            "errors": {"total": 0, "rate_per_run": 0.0},
            "cache_delta": {"hit": 9, "miss": 1, "set": 2, "expired": 0, "evicted": 0, "hit_rate": 0.9},
            "recent": [],
        },
    ]
    idx = {"i": 0}

    def _observe(*args, **kwargs):
        return levels[min(idx["i"], len(levels) - 1)]

    monkeypatch.setattr(app_v2, "_citation_verify_observe_snapshot", _observe)
    client = _client()
    client.get("/api/metrics/citation_verify")
    idx["i"] = 1
    clock[0] += 2.0
    client.get("/api/metrics/citation_verify")

    resp = client.get("/api/metrics/citation_verify/alerts/events?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert int(body.get("ok") or 0) == 1
    assert int(body.get("limit") or 0) == 2
    assert int(body.get("total") or 0) >= 2
    events = body.get("events")
    assert isinstance(events, list)
    assert len(events) <= 2
    assert all(isinstance(row, dict) for row in events)
    assert all(str((row or {}).get("id") or "") for row in events)

def test_citation_verify_alert_events_include_release_correlation_fields(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_COOLDOWN_S", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL", "")
    monkeypatch.setenv("WRITING_AGENT_CORRELATION_ID", "corr-alert-1")
    monkeypatch.setenv("WRITING_AGENT_RELEASE_CANDIDATE_ID", "rc-alert-1")
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
    events_resp = client.get("/api/metrics/citation_verify/alerts/events?limit=3")
    assert events_resp.status_code == 200
    events = events_resp.json().get("events")
    assert isinstance(events, list) and events
    row = events[-1] if isinstance(events[-1], dict) else {}
    assert str(row.get("correlation_id") or "") == "corr-alert-1"
    assert str(row.get("release_candidate_id") or "") == "rc-alert-1"

def test_citation_verify_alert_event_detail_endpoint_returns_trend_context(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_COOLDOWN_S", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL", "")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_TREND_ENABLED", "1")
    clock = [1700000300.0]
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
    rows = [
        {
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
        {
            "window_s": 1800.0,
            "max_runs": 240,
            "runs": 7,
            "elapsed_ms": {"avg": 1200.0, "p50": 900.0, "p95": 1400.0, "max": 2600.0},
            "items": {"total": 70, "avg": 10.0, "p50": 10.0, "p95": 14.0, "max": 20},
            "workers": {"avg": 3.0, "max": 5},
            "errors": {"total": 0, "rate_per_run": 0.0},
            "cache_delta": {"hit": 8, "miss": 2, "set": 4, "expired": 0, "evicted": 0, "hit_rate": 0.8},
            "recent": [],
        },
        {
            "window_s": 1800.0,
            "max_runs": 240,
            "runs": 8,
            "elapsed_ms": {"avg": 1500.0, "p50": 1100.0, "p95": 2300.0, "max": 3300.0},
            "items": {"total": 80, "avg": 10.0, "p50": 10.0, "p95": 16.0, "max": 20},
            "workers": {"avg": 4.0, "max": 6},
            "errors": {"total": 1, "rate_per_run": 0.2},
            "cache_delta": {"hit": 4, "miss": 6, "set": 5, "expired": 0, "evicted": 0, "hit_rate": 0.4},
            "recent": [],
        },
    ]
    idx = {"i": 0}
    monkeypatch.setattr(app_v2, "_citation_verify_observe_snapshot", lambda *args, **kwargs: rows[idx["i"]])

    client = _client()
    client.get("/api/metrics/citation_verify")
    idx["i"] = 1
    clock[0] += 1.5
    client.get("/api/metrics/citation_verify")
    idx["i"] = 2
    clock[0] += 1.5
    client.get("/api/metrics/citation_verify")

    events_resp = client.get("/api/metrics/citation_verify/alerts/events?limit=5")
    assert events_resp.status_code == 200
    events = events_resp.json().get("events")
    assert isinstance(events, list) and events
    event_id = str((events[-1] or {}).get("id") or "")
    assert event_id

    detail_resp = client.get(f"/api/metrics/citation_verify/alerts/event/{event_id}?context=4")
    assert detail_resp.status_code == 200
    body = detail_resp.json()
    assert int(body.get("ok") or 0) == 1
    event = body.get("event")
    assert isinstance(event, dict)
    assert str(event.get("id") or "") == event_id
    trend_ctx = body.get("trend_context")
    assert isinstance(trend_ctx, dict)
    assert int(trend_ctx.get("limit") or 0) == 4
    assert int(trend_ctx.get("total") or 0) >= 3
    points = trend_ctx.get("points")
    assert isinstance(points, list)
    assert 1 <= len(points) <= 4
    assert all(isinstance(row, dict) and str((row or {}).get("id") or "") for row in points)

def test_citation_verify_alert_admin_key_guard_on_config_and_events(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
    monkeypatch.setenv("WRITING_AGENT_ADMIN_API_KEY", "secret-123")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_COOLDOWN_S", "1")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL", "")
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
    client.get("/api/metrics/citation_verify")

    no_key_config = client.get("/api/metrics/citation_verify/alerts/config")
    assert no_key_config.status_code == 403
    no_key_events = client.get("/api/metrics/citation_verify/alerts/events")
    assert no_key_events.status_code == 403

    headers = {"X-Admin-Key": "secret-123"}
    ok_config = client.get("/api/metrics/citation_verify/alerts/config", headers=headers)
    assert ok_config.status_code == 200
    ok_events = client.get("/api/metrics/citation_verify/alerts/events", headers=headers)
    assert ok_events.status_code == 200
    events = ok_events.json().get("events")
    assert isinstance(events, list) and events
    event_id = str((events[-1] or {}).get("id") or "")
    assert event_id
    ok_detail = client.get(f"/api/metrics/citation_verify/alerts/event/{event_id}", headers=headers)
    assert ok_detail.status_code == 200

def test_citation_verify_alert_ops_rbac_role_separation(monkeypatch, tmp_path):
    _prepare_alert_config_isolation(monkeypatch, tmp_path)
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
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1")

    client = _client()

    no_key_config = client.get("/api/metrics/citation_verify/alerts/config")
    assert no_key_config.status_code == 403

    viewer_headers = {"X-Admin-Key": "viewer-key"}
    viewer_get = client.get("/api/metrics/citation_verify/alerts/config", headers=viewer_headers)
    assert viewer_get.status_code == 200
    viewer_events = client.get("/api/metrics/citation_verify/alerts/events", headers=viewer_headers)
    assert viewer_events.status_code == 200
    viewer_post = client.post(
        "/api/metrics/citation_verify/alerts/config",
        headers=viewer_headers,
        json={"config": {"enabled": True}},
    )
    assert viewer_post.status_code == 403

    operator_headers = {"X-Admin-Key": "operator-key"}
    operator_post = client.post(
        "/api/metrics/citation_verify/alerts/config",
        headers=operator_headers,
        json={"config": {"enabled": False}},
    )
    assert operator_post.status_code == 200

    admin_headers = {"X-Admin-Key": "admin-ops-key"}
    admin_post = client.post(
        "/api/metrics/citation_verify/alerts/config",
        headers=admin_headers,
        json={"config": {"enabled": True}},
    )
    assert admin_post.status_code == 200

