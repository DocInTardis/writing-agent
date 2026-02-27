# Privacy And Data Classification

`SEC-003` introduces policy-driven classification and retention enforcement for operational artifacts.

## Policy

- file: `security/data_classification_policy.json`
- enforced by: `scripts/data_classification_guard.py`

Policy covers:

- artifact path rules (glob + classification)
- max retention window (`max_age_days`)
- sensitive pattern detection
- per-class unmasked finding thresholds

## Run

```powershell
python scripts/data_classification_guard.py --strict --require-rules
```

Custom policy:

```powershell
python scripts/data_classification_guard.py --policy security/data_classification_policy.json --strict
```

## Output

- `.data/out/data_classification_guard_*.json`

Key fields:

- `rules`
- `findings_by_class`
- `findings`
- `retention_violations`
- `checks`

## Preflight Integration

`scripts/release_preflight.py` step:

- step id: `data_classification_guard`

Supported env:

- `WA_DATA_CLASS_POLICY_FILE`
- `WA_DATA_CLASS_GUARD_STRICT=1`
- `WA_DATA_CLASS_GUARD_REQUIRE_RULES=1`
- `WA_DATA_CLASS_GUARD_MAX_UNMASKED_FINDINGS`
