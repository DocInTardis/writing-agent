# Ops RBAC Baseline

This document defines RBAC for operational alert endpoints.

## Scope

Protected endpoints:

- `GET /api/metrics/citation_verify/alerts/config` requires `alerts.read`
- `POST /api/metrics/citation_verify/alerts/config` requires `alerts.write`
- `GET /api/metrics/citation_verify/alerts/events` requires `alerts.read`
- `GET /api/metrics/citation_verify/alerts/event/{event_id}` requires `alerts.read`

## Policy

Policy file:

- `security/ops_rbac_policy.json`

Default roles in baseline policy:

- `viewer`: `alerts.read`
- `operator`: `alerts.read`, `alerts.write`
- `admin`: `*`

Principals are mapped by token environment variable (`token_env`).

## Environment Variables

- `WRITING_AGENT_OPS_RBAC_ENABLED`
  - default: `1`
  - when disabled, system falls back to legacy admin-key check
- `WRITING_AGENT_OPS_RBAC_POLICY`
  - optional override for policy file path
- `WRITING_AGENT_ADMIN_API_KEY`
  - legacy superuser key, still supported and always full-permission
- `WRITING_AGENT_OPS_VIEWER_API_KEY`
  - optional viewer principal token source
- `WRITING_AGENT_OPS_OPERATOR_API_KEY`
  - optional operator principal token source

## Authentication Header

One of:

- `X-Admin-Key: <token>`
- `Authorization: Bearer <token>`

## Compatibility

If no RBAC principal token and no admin key is configured, endpoints remain open (same as previous behavior with empty admin key).

## Tests

Role separation coverage:

- `tests/test_citation_verify_and_delete.py::test_citation_verify_alert_ops_rbac_role_separation`

Legacy compatibility coverage:

- `tests/test_citation_verify_and_delete.py::test_citation_verify_alert_admin_key_guard_on_config_and_events`
