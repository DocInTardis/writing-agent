from __future__ import annotations

from scripts import alert_escalation_guard


def _policy() -> dict:
    return {
        "version": 1,
        "citation_verify": {
            "lookback_minutes": 30,
            "thresholds": {
                "critical_events_min": 1,
                "warn_events_min": 2,
                "repeat_events_min": 4,
                "suppressed_events_min": 3,
                "webhook_failures_min": 2,
            },
            "slo_guard": {"require_report": False, "fail_as_critical": True},
            "actions": {"p1": ["page_oncall"], "p2": ["create_incident_report"]},
        },
    }


def test_normalize_events_supports_dict_and_list() -> None:
    rows = [{"id": "a"}, {"id": "b"}]
    assert len(alert_escalation_guard._normalize_events(rows)) == 2
    assert len(alert_escalation_guard._normalize_events({"events": rows})) == 2
    assert alert_escalation_guard._normalize_events({"events": "bad"}) == []


def test_evaluate_critical_event_escalates_to_p1() -> None:
    now = 1_700_000_000.0
    events = [
        {"id": "e1", "ts": now - 20, "severity": "critical", "event_type": "raise", "status": "http_500"},
    ]
    out = alert_escalation_guard._evaluate(policy=_policy(), events=events, now_ts=now, quick=False, slo_ok=True)
    escalation = out["escalation"]
    assert escalation["level"] == "p1"
    assert "critical_events" in escalation["triggered_by"]


def test_evaluate_warn_burst_escalates_to_p2() -> None:
    now = 1_700_000_000.0
    events = [
        {"id": "e1", "ts": now - 30, "severity": "warn", "event_type": "raise", "status": "log_only"},
        {"id": "e2", "ts": now - 15, "severity": "warn", "event_type": "repeat", "status": "suppressed", "dedupe_hit": True},
    ]
    out = alert_escalation_guard._evaluate(policy=_policy(), events=events, now_ts=now, quick=False, slo_ok=True)
    escalation = out["escalation"]
    assert escalation["level"] == "p2"
    assert "warn_events" in escalation["triggered_by"]


def test_evaluate_slo_failure_escalates_to_p1() -> None:
    out = alert_escalation_guard._evaluate(
        policy=_policy(),
        events=[],
        now_ts=1_700_000_000.0,
        quick=False,
        slo_ok=False,
    )
    escalation = out["escalation"]
    assert escalation["level"] == "p1"
    assert "slo_guard_failed" in escalation["triggered_by"]


def test_evaluate_extracts_correlation_context_from_recent_events() -> None:
    now = 1_700_000_000.0
    events = [
        {
            "id": "e1",
            "ts": now - 20,
            "severity": "warn",
            "event_type": "raise",
            "status": "log_only",
            "correlation_id": "corr-1",
            "release_candidate_id": "rc-1",
        },
    ]
    out = alert_escalation_guard._evaluate(policy=_policy(), events=events, now_ts=now, quick=False, slo_ok=True)
    correlation = out["correlation"]
    assert correlation["correlation_id"] == "corr-1"
    assert correlation["release_candidate_id"] == "rc-1"
