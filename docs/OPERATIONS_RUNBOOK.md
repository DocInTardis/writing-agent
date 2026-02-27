# Writing Agent Operations Runbook

This runbook covers operational monitoring and alert handling for the `citation_verify` path.

## 1. Scope

Operational endpoints:

- metrics: `/api/metrics/citation_verify`
- alert config: `/api/metrics/citation_verify/alerts/config`
- alert events: `/api/metrics/citation_verify/alerts/events`
- alert detail: `/api/metrics/citation_verify/alerts/event/{event_id}`
- trend points: `/api/metrics/citation_verify/trends`

## 2. On-Call SLO (Initial Targets)

- metrics endpoint availability: `>= 99.5%`
- metrics endpoint p95 latency: `<= 1500 ms`
- `degraded=true` response rate: `<= 1%`
- continuous `suppressed` alert state: `< 30 min`

These are initial operational targets and must be tuned with production evidence.

## 3. Alert Thresholds And Configuration

Persisted alert configuration file:

- `.data/citation_verify_alerts_config.json`

Default checks:

- `latency_p95_ms >= p95_ms`
- `error_rate_per_run >= error_rate_per_run`
- `cache_delta_hit_rate <= cache_delta_hit_rate`
- `metrics_degraded == true`

Notification channels:

- `log` (default)
- `webhook` (enabled with `WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL`)

## 4. Common Commands

```powershell
# 1) Current metrics snapshot
curl http://127.0.0.1:8000/api/metrics/citation_verify

# 2) Alert configuration (requires token if auth configured)
curl -H "X-Admin-Key: <token>" http://127.0.0.1:8000/api/metrics/citation_verify/alerts/config

# 3) Recent alert events
curl -H "X-Admin-Key: <token>" "http://127.0.0.1:8000/api/metrics/citation_verify/alerts/events?limit=20"

# 4) Event detail with trend context
curl -H "X-Admin-Key: <token>" "http://127.0.0.1:8000/api/metrics/citation_verify/alerts/event/<event_id>?context=12"
```

Validate incident routing and on-call roster before release:

```powershell
python scripts/incident_config_guard.py --strict --oncall-roster security/oncall_roster.json --require-oncall-roster
```

Validate tamper-evident audit trail integrity:

```powershell
python scripts/verify_audit_chain.py --strict --require-log
```

Validate privacy classification and retention guard:

```powershell
python scripts/data_classification_guard.py --strict
```

## 5. Incident Severity And Actions

P1 (critical):

- `severity=critical` sustained for more than 5 minutes with persistent error-rate threshold breach
- metrics endpoint HTTP `5xx` sustained for more than 5 minutes

Actions:

1. Freeze release rollout.
2. Inspect recent events and trend context.
3. If caused by release change, execute rollback workflow.

P2 (warning):

- `severity=warn` sustained for more than 15 minutes
- `suppressed` keeps growing without `recover`

Actions:

1. Check webhook/log notification channel health.
2. Confirm traffic model changed before threshold tuning.
3. Record incident and include in daily review.

## 6. Security And Access

Required in production:

- `WRITING_AGENT_ADMIN_API_KEY`

RBAC policy (recommended):

- `WRITING_AGENT_OPS_RBAC_ENABLED=1`
- `WRITING_AGENT_OPS_RBAC_POLICY=security/ops_rbac_policy.json`
- optional principal tokens:
  - `WRITING_AGENT_OPS_VIEWER_API_KEY`
  - `WRITING_AGENT_OPS_OPERATOR_API_KEY`

Reference:

- `docs/OPS_RBAC.md`

## 7. Daily Checklist

1. Verify metrics endpoint availability and degraded ratio.
2. Review last 24h event stream (`repeat`/`suppressed` anomalies).
3. Validate growth of `events_total` and trend points against traffic.
4. Verify security headers and access controls remain active.
5. Confirm `security/oncall_roster.json` is present and has a valid on-call target.

## 8. Weekly Drills

1. Load probe:
  - `python scripts/citation_verify_load_probe.py --base-url http://127.0.0.1:8000`
2. Alert webhook chaos:
  - `python scripts/citation_verify_alert_chaos.py`
3. Dependency audit:
  - `python scripts/dependency_audit.py`
4. SBOM generation:
  - `python scripts/generate_sbom.py --out-dir .data/out/sbom --strict`

## 9. Dependency Baseline Refresh

- Command:
  - `python scripts/update_dependency_baseline.py --reason "<baseline change reason>"`
- Policy:
  - `docs/DEPENDENCY_BASELINE_POLICY.md`
