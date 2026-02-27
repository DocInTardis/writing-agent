# Migration Assistant

`PROD-002` adds an operator-facing migration guide generator.

## Script

- `scripts/migration_assistant.py`

Inputs:

- package version (`writing_agent/__init__.py`)
- compatibility matrix (`security/release_compat_matrix.json`)
- release policy (`security/release_policy.json`)

Outputs:

- `.data/out/migration_assistant_*.json`
- `.data/out/migration_assistant_*.md`

## Command

```powershell
python scripts/migration_assistant.py --strict
```

With explicit versions:

```powershell
python scripts/migration_assistant.py --from-version 0.0.9 --to-version 0.1.0 --strict
```

## Preflight Integration

`scripts/release_preflight.py` step:

- step id: `migration_assistant`

Supported env:

- `WA_MIGRATION_ASSISTANT_STRICT=1`
- `WA_MIGRATION_FROM_VERSION`
- `WA_MIGRATION_TO_VERSION`
- `WA_MIGRATION_MATRIX_FILE`
- `WA_MIGRATION_POLICY_FILE`
- `WA_MIGRATION_OUT_MD`
