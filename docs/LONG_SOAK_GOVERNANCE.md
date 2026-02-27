# Long Soak Governance

This document defines long-duration soak evidence governance for `citation_verify`.

## Scope

`PERF-001` is implemented as:

- Scheduled long-soak pipeline (`12h` / `24h` profiles).
- Persistent history retention across workflow runs.
- Regression fail rules against history medians.

## Components

- Soak runner: `scripts/citation_verify_soak.py`
- Long-soak guard: `scripts/citation_verify_long_soak_guard.py`
- Policy: `security/long_soak_policy.json`
- Workflow: `.github/workflows/citation-soak-long.yml`
- History file (cache-backed): `.data/perf/citation_verify_long_soak_history.json`

## Profile Schedule

`citation-soak-long` schedule:

- Weekly `12h` profile (`cron: 0 1 * * 1`)
- Monthly `24h` profile (`cron: 0 1 1 * *`)

Manual dispatch supports:

- `long-12h`
- `long-24h`
- `custom` duration

Runner note:

- `long-12h` / `long-24h` profiles are intended for `self-hosted` runners.
- The workflow exits early if `ubuntu-latest` is selected with a duration above roughly 6 hours.

## Retention Model

History is retained in a cache-restored file:

- path: `.data/perf/citation_verify_long_soak_history.json`
- retention: controlled by `history.retention_days`
- max records: controlled by `history.max_records`

Each guard run merges current soak reports with prior history, deduplicates, trims by age, and caps record count.

## Regression Fail Rules

Rules come from `security/long_soak_policy.json`:

- Evidence freshness:
  - `gate.max_report_age_s`
  - `gate.min_reports`
- Long-duration profile coverage:
  - `profiles[*].min_duration_s`
  - `profiles[*].required_count`
  - `profiles[*].window_days`
- Regression checks (latest vs history median):
  - `regression.max_p95_ratio_to_median`
  - `regression.min_success_rate_delta_to_median`
  - `regression.max_degraded_rate_delta_to_median`

When `--strict` is enabled, failed enforce checks return exit code `2` and block the workflow.

## Local Commands

Run strict guard against retained history:

```powershell
python scripts/citation_verify_long_soak_guard.py `
  --policy security/long_soak_policy.json `
  --history-file .data/perf/citation_verify_long_soak_history.json `
  --strict
```

Artifacts:

- `.data/out/citation_verify_soak_*.json`
- `.data/out/citation_verify_long_soak_guard_*.json`
- `.data/perf/citation_verify_long_soak_history.json`
