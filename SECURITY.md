# Security Policy

## Supported Versions
Security fixes are applied to the latest mainline version in this repository.

## Reporting a Vulnerability
1. Do not open a public issue for unpatched vulnerabilities.
2. Provide:
- impact summary
- reproduction steps
- affected files or endpoints
- proposed mitigation (if available)
3. Use private contact channels defined by project maintainers.

## Security Controls in This Repository
- policy-as-code configs under `security/`
- dependency and SBOM tooling under `scripts/`
- release preflight and guardrails integrated in CI workflows
