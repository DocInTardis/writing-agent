# Test Pyramid

This repository enforces layered testing:

- Unit: deterministic pure functions and domain logic
- Integration: service/flow contracts and storage behavior
- E2E: UI and full-chain scenarios (Playwright + runtime smoke)

Reference folders:

- `tests/unit`
- `tests/integration`
- `tests/e2e`

Additional quality gates:

- Prompt/schema regression
- Golden export snapshots
- Concurrency and long-task stress probes
- Citation chain specialized tests
- Flaky test detection and quarantine
