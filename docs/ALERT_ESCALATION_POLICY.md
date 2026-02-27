# Alert Escalation Policy

This document defines how `citation_verify` alert events are promoted into incident levels.

## Policy file

- `security/alert_escalation_policy.json`

Current policy focuses on these signals inside a recent time window:

- `critical_events_min`
- `warn_events_min`
- `repeat_events_min`
- `suppressed_events_min`
- `webhook_failures_min`
- `slo_guard.fail_as_critical`

## Guard script

Run the escalation guard manually:

```bash
python scripts/alert_escalation_guard.py
```

Strict mode fails when escalation level is not `none`:

```bash
python scripts/alert_escalation_guard.py --strict
```

Quick mode uses a shorter evaluation window:

```bash
python scripts/alert_escalation_guard.py --quick
```

Output artifact:

- `.data/out/alert_escalation_*.json`

## Escalation levels

- `none`
  - No incident is required.
- `p2`
  - Warning-level escalation. Create incident report and notify on-call channel.
- `p1`
  - Critical escalation. Page on-call, freeze release, and prepare rollback.

## Operational notes

- Missing alert events file does not automatically fail non-strict checks.
- If `slo_guard.require_report=true` and no SLO report exists, strict mode fails.
- Keep this policy aligned with `docs/OPERATIONS_RUNBOOK.md` and your on-call process.
