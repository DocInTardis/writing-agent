# Audit Trail Integrity

This document describes the tamper-evident operational audit chain implemented for `SEC-002`.

## Purpose

- Keep an append-only evidence trail for critical operational actions.
- Detect tampering (entry edits, deletion, or chain rewrite).
- Enforce integrity in release preflight through a dedicated gate.

## Audit Chain Files

- Log file:
  - `.data/audit/operations_audit_chain.ndjson`
- Continuity state snapshot:
  - `.data/audit/operations_audit_chain_state.json`
- Verification reports:
  - `.data/out/audit_chain_verify_*.json`

## Entry Schema

Each line in the ndjson log is one immutable record:

- `schema_version`
- `seq`
- `ts`
- `action`
- `actor`
- `source`
- `status`
- `context`
- `prev_hash`
- `entry_hash`

`entry_hash` is computed over canonical json content of the entry excluding `entry_hash`.
`prev_hash` must equal the previous entry `entry_hash`.

## Integrated Writers

Operational scripts now append to this chain:

- `scripts/release_channel_control.py`
- `scripts/release_rollout_executor.py`
- `scripts/incident_notify.py`
- `scripts/create_rollback_bundle.py`

## Verification

Manual verification:

```powershell
python scripts/verify_audit_chain.py --strict --require-log
```

With explicit paths and freshness window:

```powershell
python scripts/verify_audit_chain.py `
  --log .data/audit/operations_audit_chain.ndjson `
  --state-file .data/audit/operations_audit_chain_state.json `
  --strict --require-log --max-age-s 7200
```

## Preflight Gate

`scripts/release_preflight.py` runs:

- step id: `audit_trail_integrity`
- command: `python scripts/verify_audit_chain.py ...`

Supported env:

- `WA_AUDIT_CHAIN_LOG`
- `WA_AUDIT_CHAIN_STATE_FILE`
- `WA_AUDIT_CHAIN_STRICT=1`
- `WA_AUDIT_CHAIN_REQUIRE_LOG=1`
- `WA_AUDIT_CHAIN_REQUIRE_STATE=1` (optional)
- `WA_AUDIT_CHAIN_MAX_AGE_S`
- `WA_AUDIT_CHAIN_NO_WRITE_STATE=1` (optional)

## Tamper Response

If verification fails:

1. Freeze release/apply operations.
2. Preserve current audit files as evidence.
3. Investigate mismatched entry hashes and state continuity checks.
4. Rebuild chain only through approved incident process and record the recovery action.
