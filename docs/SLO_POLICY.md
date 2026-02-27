# SLO Policy

Release SLO targets are defined in:

- `security/slo_targets.json`

Current tracked targets:

- `success_rate_min`
- `latency_p95_ms_max`
- `degraded_rate_max`
- `events_recent_min`

Validate SLO against the latest load probe report:

```powershell
python scripts/slo_guard.py
```

Quick mode (used in quick preflight):

```powershell
python scripts/slo_guard.py --quick
```

Output:

- `.data/out/slo_guard_*.json`
