# Test Layout

## Layers

- `tests/unit/`
  - Fast, isolated tests for pure functions and local modules.
- `tests/integration/`
  - Service and API integration tests.
- `tests/export/`
  - Export-path verification for Markdown and DOCX behavior.
- `tests/ui/`
  - Frontend and workbench flow validation.
- `tests/e2e/`
  - End-to-end scenarios that exercise larger product flows.

## Fixtures

- `tests/fixtures/`
  - Versioned sample inputs, golden files, and reusable datasets.

## Rule

Do not keep deprecated or one-off test scripts in the repository.
If a test is still valuable, promote it into one of the maintained test layers above.
