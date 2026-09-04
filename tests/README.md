# Test Layout

## Layers

- `tests/unit/`
  - Fast, isolated tests for pure functions and local modules.
- `tests/integration/`
  - Service and API integration tests.
- `tests/export/`
  - Export-path verification for Markdown and DOCX behavior.

The browser automation suite and empty E2E placeholder have been retired.
Desktop interaction acceptance coverage remains to be established; the layers above
do not validate the complete editor experience.

## Fixtures

- `tests/fixtures/`
  - Versioned sample inputs, golden files, and reusable datasets.

## Rule

Do not keep deprecated or one-off test scripts in the repository.
If a test is still valuable, promote it into one of the maintained test layers above.
