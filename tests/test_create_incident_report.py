from __future__ import annotations

from scripts import create_incident_report


def test_pick_incident_severity() -> None:
    assert create_incident_report._pick_incident_severity("p1") == "critical"
    assert create_incident_report._pick_incident_severity("p2") == "high"
    assert create_incident_report._pick_incident_severity("none") == "low"
    assert create_incident_report._pick_incident_severity("unknown", fallback="medium") == "medium"


def test_build_timeline_sorted_and_trimmed() -> None:
    events = [
        {
            "id": "a",
            "ts": 30,
            "severity": "warn",
            "event_type": "raise",
            "status": "log_only",
            "correlation_id": "corr-a",
        },
        {"id": "b", "ts": 10, "severity": "warn", "event_type": "repeat", "status": "suppressed"},
        {"id": "c", "ts": 20, "severity": "critical", "event_type": "change", "status": "http_500"},
    ]
    rows = create_incident_report._build_timeline(events, limit=2)
    assert len(rows) == 2
    assert rows[0]["id"] == "c"
    assert rows[1]["id"] == "a"
    assert rows[1]["correlation_id"] == "corr-a"


def test_render_markdown_contains_sections() -> None:
    payload = {
        "incident_id": "INC-1",
        "title": "citation incident",
        "severity": "critical",
        "escalation_level": "p1",
        "triggered_by": ["critical_events"],
        "owner": "oncall",
        "created_at_iso": "2026-01-01T00:00:00Z",
        "correlation_id": "corr-1",
        "release_candidate_id": "rc-1",
        "status": "open",
        "scope": "citation_verify",
        "recommended_actions": ["page_oncall"],
        "timeline": [
            {
                "id": "evt-1",
                "ts_iso": "2026-01-01T00:00:00Z",
                "severity": "critical",
                "event_type": "raise",
                "status": "http_500",
            }
        ],
        "evidence_paths": {
            "escalation_report": ".data/out/alert_escalation_x.json",
            "rollout_report": ".data/out/release_rollout_executor_x.json",
            "slo_report": ".data/out/slo_guard_x.json",
            "load_report": ".data/out/citation_verify_load_probe_x.json",
            "events_file": ".data/citation_verify_alert_events.json",
        },
        "load_summary": {"success_rate": 0.95, "degraded_rate": 0.2, "latency_ms": {"p95": 2200}},
        "slo_observed": {"success_rate": 0.95, "latency_p95_ms": 2200, "degraded_rate": 0.2},
    }
    md = create_incident_report._render_markdown(payload)
    assert "# Incident Report: INC-1" in md
    assert "## Timeline" in md
    assert "| Time (UTC) | Severity | Event | Status | Event ID |" in md
    assert "page_oncall" in md
    assert "Correlation ID: corr-1" in md
    assert "Release Candidate ID: rc-1" in md


def test_extract_correlation_prefers_correlation_node() -> None:
    raw = {
        "correlation": {
            "correlation_id": "corr-1",
            "release_candidate_id": "rc-1",
        },
        "incident": {
            "correlation_id": "corr-2",
            "release_candidate_id": "rc-2",
        },
    }
    correlation_id, release_candidate_id = create_incident_report._extract_correlation(raw)
    assert correlation_id == "corr-1"
    assert release_candidate_id == "rc-1"
