# Preflight Trend Guard

This guard detects consecutive performance degradation trends and can block release in strict mode.
It evaluates both short load probe history and optional long-run soak history.

## Policy file

- `security/performance_trend_policy.json`

Key policy fields:

- `window_runs`
- `min_required_runs`
- `allow_insufficient_history`
- `consecutive_worsen_limit`
- `worsen.*` thresholds for pairwise degradation
- `latest_guard.*` thresholds for latest-vs-median check
- `soak_trend.*` for soak-history trend checks

## Script

- `scripts/preflight_trend_guard.py`

## Commands

Quick check:

```bash
python scripts/preflight_trend_guard.py --quick
```

Strict gate:

```bash
python scripts/preflight_trend_guard.py --strict
```

Require soak evidence and soak trend gate:

```bash
python scripts/preflight_trend_guard.py --strict --require-soak
```

## Blocking rule

When enough history exists, strict mode fails if tail consecutive degraded transitions reach `consecutive_worsen_limit`.

If `--require-soak` is enabled, missing soak history is treated as a hard failure and soak trend checks run in enforce mode.

## Output artifact

- `.data/out/preflight_trend_guard_*.json`

This includes analyzed reports, transition details, and the final gate decision.
