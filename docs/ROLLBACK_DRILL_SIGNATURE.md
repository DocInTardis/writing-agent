# Rollback Drill Signature Policy

This document defines signed-evidence requirements for rollback drill automation.

## Policy

- Policy file: `security/rollback_drill_signature_policy.json`
- Algorithm: HMAC-SHA256
- Signing key env: `WA_ROLLBACK_DRILL_SIGNING_KEY`
- Key id env: `WA_ROLLBACK_DRILL_SIGNING_KEY_ID`

## Evidence Signing

Generate signed evidence report:

```powershell
python scripts/sign_rollback_drill_evidence.py --require-key --strict
```

Output:

- `.data/out/rollback_drill_signature_*.json`

## Guard Validation

Validate rollback drill evidence with signature verification:

```powershell
python scripts/rollback_drill_guard.py `
  --strict `
  --require-email-drill `
  --require-history-rollback `
  --require-signature `
  --signing-key "<key>"
```

Guard checks include:

- signature report existence and freshness
- HMAC signature verification
- artifact hash verification
- evidence coverage for latest incident + rollback drill reports
