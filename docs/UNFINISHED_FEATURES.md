# Unfinished Features Backlog

This file tracks unfinished productization work for `writing-agent`.
Status is updated continuously as items are delivered.

## P0 Release And Reliability

| ID | Area | Gap | Done Criteria | Status |
|---|---|---|---|---|
| REL-001 | Release rollout execution | Rollout currently depends on local channel state updates; lacks hardened real traffic execution integration and rollback-safe execution flow. | Rollout executor supports external traffic command execution, records command evidence, and prevents partial local commit on command failure. | completed |
| REL-002 | Rollout execution integration | CI/workflow supports dry-run and basic apply flow, but no environment-level standardized traffic adapter contract document and examples. | Standardized adapter contract documented with examples for ingress/gateway/service mesh. | completed |
| REL-003 | Upgrade/rollback matrix breadth | Compatibility matrix exists but has limited cases and schemas. | Matrix includes N-1/N/N+1 schema transitions and failure-mode fixtures with strict enforcement in CI. | completed |
| REL-004 | Rollback rehearsal depth | Drill guard checks artifacts and optional history rollback rehearsal, but no mandatory automated rollback rehearsal schedule with signed evidence policy. | Scheduled rehearsal run produces signed evidence and blocked release on stale/missing rehearsal. | completed |
| REL-005 | Release gating traceability | Gates exist but no single trace object linking release candidate ID to all gate artifacts. | Release manifest includes immutable gate evidence map keyed by release candidate ID. | completed |

## P0 Operations And Incident Response

| ID | Area | Gap | Done Criteria | Status |
|---|---|---|---|---|
| OPS-001 | On-call schedule integration | Incident and drill automation exist but no native on-call roster escalation source integration. | Pager/on-call source integrated and escalation target validated in drills. | completed |
| OPS-002 | Incident timeline correlation | Alert, incident, and release artifacts are generated separately with weak cross-linking. | Shared correlation IDs across alert events, incident reports, and release rollout actions. | completed |
| OPS-003 | Runbook localization/encoding quality | Some ops docs show encoding artifacts and mixed language quality. | UTF-8 clean docs with validated rendering and consistent language style. | completed |

## P1 Performance Governance

| ID | Area | Gap | Done Criteria | Status |
|---|---|---|---|---|
| PERF-001 | Long-duration soak evidence | Current soak/stress checks are present, but long-running (12h/24h) production-like baselines are not fully automated. | Scheduled long-soak pipeline with trend retention and regression fail rules. | completed |
| PERF-002 | Capacity model calibration | Threshold suggestion and policy drift exist, but capacity model lacks environment-specific calibration automation. | Per-environment capacity baselines and calibrated thresholds auto-maintained. | completed |
| PERF-003 | Capacity planning model | No explicit capacity forecast model tied to observed growth. | Forecast report generated from trend history and included in release readiness. | completed |

## P1 Security And Compliance

| ID | Area | Gap | Done Criteria | Status |
|---|---|---|---|---|
| SEC-001 | RBAC for operational endpoints | Admin key controls exist; role-based permission model is missing. | Endpoint-level RBAC policy and tests for role separation. | completed |
| SEC-002 | Audit trail integrity | Operational actions recorded, but tamper-evident audit chain is missing. | Append-only audit log with hash chain and verification script. | completed |
| SEC-003 | Privacy/data classification | Sensitive output scan exists, but data classification and retention policy enforcement are incomplete. | Data class policy documented and automated checks for retention/masking. | completed |

## P1 Developer Experience And Docs

| ID | Area | Gap | Done Criteria | Status |
|---|---|---|---|---|
| DX-001 | End-to-end onboarding | Docs are split across many files without single bootstrap path. | One start-to-runbook guide with verified commands on clean machine. | completed |
| DX-002 | Failure troubleshooting map | Many reports are generated but troubleshooting flow is fragmented. | Decision tree mapping common failures to exact scripts/artifacts. | completed |
| DX-003 | Artifact schema catalog | Report JSONs exist but schema references are not centralized. | Artifact schema index doc with field descriptions and compatibility notes. | completed |

## P2 Product Surface

| ID | Area | Gap | Done Criteria | Status |
|---|---|---|---|---|
| PROD-001 | Public packaging/distribution | Release engineering improved, but public package/release channel publishing contract is incomplete. | Versioned package publishing pipeline with changelog/release notes automation. | completed |
| PROD-002 | Migration assistant | Compatibility checks exist but no operator-facing migration assistant. | Guided migration script and validation report for upgrades/rollbacks. | completed |

## Current Execution Order

1. No pending todo items. Keep completed gates green in tests and CI preflight.
