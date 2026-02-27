# Citation Verify Performance Baseline

This document defines baseline performance checks and operating thresholds for the `citation_verify` observability path.

## 1. Objective

Turn observability into governance:

- run repeatable probes after changes,
- produce structured artifacts,
- gate release by measurable thresholds.

## 2. Probe Tool

Primary script:

- `scripts/citation_verify_load_probe.py`

Capabilities:

- concurrent probe for `/api/metrics/citation_verify`
- captures success rate and latency distribution (`p50`, `p95`, `p99`)
- tracks `degraded=true` response ratio
- optionally probes recent alert events with admin key
- writes JSON report and returns exit code:
  - `0`: pass
  - `2`: fail

## 3. Local Run

```powershell
python scripts/citation_verify_load_probe.py `
  --base-url http://127.0.0.1:8000 `
  --requests 400 `
  --concurrency 32 `
  --timeout-s 6 `
  --min-success-rate 0.99 `
  --max-p95-ms 1500 `
  --max-degraded-rate 0.01
```

Default output:

- `.data/out/citation_verify_load_probe_<timestamp>.json`

## 4. Key Fields

- `summary.success_rate`: successful request ratio (`2xx` and no client/runtime error)
- `summary.latency_ms.p95`: p95 latency in milliseconds
- `summary.degraded_rate`: ratio of responses with `degraded=true`
- `checks`: threshold evaluation rows
- `events_probe`: probe result for alert-events endpoint

## 5. Initial Baseline

- `success_rate >= 0.99`
- `p95 <= 1500 ms`
- `degraded_rate <= 0.01`

These are starting values and must be tuned with real traffic.

## 6. Soak Recommendation

Short soak:

- duration: 5-10 minutes
- purpose: detect burst-time error/timeout behavior

Long soak:

- duration: 60+ minutes
- purpose: verify trend continuity, suppression behavior, and memory/queue stability

Alert chaos drill:

- script: `scripts/citation_verify_alert_chaos.py`
- purpose: validate webhook failure suppression and recovery behavior

## 7. Baseline Update Process

1. Run at least 3 rounds in the same environment and use median values.
2. Compare with historical reports.
3. Update thresholds and keep runbook + CI gate aligned.

## 8. CI Gates

- Observability workflow:
  - `.github/workflows/citation-observability.yml`
- Integrated preflight:
  - `.github/workflows/release-preflight.yml`
- Dependency audit:
  - `.github/workflows/dependency-security.yml`
- SBOM generation:
  - `scripts/generate_sbom.py` (output in `.data/out/sbom/`)

## 9. Soak Automation

```powershell
python scripts/citation_verify_soak.py `
  --base-url http://127.0.0.1:8000 `
  --duration-s 1800 `
  --interval-s 30 `
  --requests-per-window 32 `
  --concurrency 8 `
  --min-overall-success-rate 0.995 `
  --max-overall-p95-ms 2000 `
  --max-overall-degraded-rate 0.05
```

Workflows:

- `.github/workflows/citation-soak.yml` (nightly/manual)
- `.github/workflows/citation-soak-long.yml` (12h/24h governance profiles)

## 10. Capacity Guard

To enforce throughput headroom against target peak RPS:

```powershell
python scripts/capacity_guard.py
```

Policy source:

- `security/capacity_policy.json`

Refresh capacity baseline:

```powershell
python scripts/update_capacity_baseline.py --reason "capacity baseline refresh"
```
