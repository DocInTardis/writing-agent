# Incident Response Automation

This project can generate incident reports directly from release and observability artifacts.

## Script

- `scripts/create_incident_report.py`

Default behavior:

- Reads latest escalation report: `.data/out/alert_escalation_*.json`
- Reads latest SLO guard report: `.data/out/slo_guard_*.json`
- Reads latest load probe report: `.data/out/citation_verify_load_probe_*.json`
- Reads alert events from: `.data/citation_verify_alert_events.json`
- Writes:
  - `.data/out/incident_report_*.json`
  - `.data/out/incident_report_*.md`

## Commands

Generate report only when escalation exists:

```bash
python scripts/create_incident_report.py --only-when-escalated
```

Force generation with custom owner/title:

```bash
python scripts/create_incident_report.py --owner oncall-a --title "Citation verify incident"
```

Strict mode:

```bash
python scripts/create_incident_report.py --strict
```

## Report sections

- Incident metadata (severity, owner, status)
- Escalation trigger context
- Current key metrics (load probe + SLO observed)
- Timeline table from recent alert events
- Recommended actions checklist
- Evidence paths for fast triage

## CI / preflight integration

`scripts/release_preflight.py` invokes:

1. `scripts/alert_escalation_guard.py`
2. `scripts/create_incident_report.py --only-when-escalated`
3. `scripts/incident_notify.py --only-when-escalated`
4. `scripts/incident_config_guard.py`
5. `scripts/sensitive_output_scan.py`
6. `scripts/preflight_trend_guard.py`

These artifacts are uploaded in `.github/workflows/release-preflight.yml`.

On-call roster enforcement in preflight:

- `WA_INCIDENT_ONCALL_ROSTER_FILE=security/oncall_roster.json`
- `WA_INCIDENT_REQUIRE_ONCALL_ROSTER=1`
- `WA_INCIDENT_USE_ONCALL_ROSTER=1`
