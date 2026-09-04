# Changelog

## Unreleased

### Added
- A maintained feature and implementation map for the Web, AI, RAG, export, quality, and desktop paths.
- A single CI workflow covering Python, Svelte, the Node gateway, and the Rust engine.

### Changed
- Separate full-document and section-generation task inputs from explicit workflow dependencies; keep legacy Web assembly in a dedicated adapter.
- Reuse the default Python environment on normal launches; install dependencies only on bootstrap or explicit request, without a pip download cache.
- Document a Web-first runtime with optional development stacks and explicit storage boundaries.
- Simplified Web and PySide launchers so they respect user model settings and do not read credentials from other applications.
- Marked the Tauri shell as experimental and added a usable development backend fallback and proxy.
- Made API ownership tests compatible with both flat and nested FastAPI router representations.

### Fixed
- Close section model generators on final output and failure, and guard migrated workflow boundaries with headless tests.
- Declare the requests runtime dependency instead of relying on development tools to install it indirectly.
- Restore missing HTML conversion imports used by editor paragraph splitting, with a browser regression test.
- Declared missing runtime and TestClient dependencies and repaired the pinned dependency set.
- Closed the Tauri-managed Python child process on application exit.
- Removed stale workflows and commands that referenced deleted release and capacity scripts.
- Removed current Python syntax and datetime deprecation warnings in touched runtime paths.

This project maintains historical change records in `CHANGES.md`.

For upcoming releases, keep entries grouped by:
- Added
- Changed
- Fixed
- Removed

Recommended format:

```markdown
## [x.y.z] - YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Fixed
- ...
```
