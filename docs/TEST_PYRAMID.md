# Test Pyramid

This repository enforces layered testing:

- Unit: deterministic pure functions and domain logic
- Integration: service/flow contracts and storage behavior
- Export: document output and formatting regression

Reference folders:

- `tests/unit`
- `tests/integration`
- `tests/export`

The browser automation suite has been retired. Desktop interaction acceptance
coverage still needs to be established; backend tests do not replace it.

Additional quality gates:

- Prompt/schema regression
- Golden export snapshots
- Concurrency and long-task stress probes
- Citation chain specialized tests
- Flaky test detection and quarantine
