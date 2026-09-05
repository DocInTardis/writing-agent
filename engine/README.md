# Rust document engine

This workspace is the performance-sensitive document core, not a second desktop application.

- `core`: document AST, edit commands, history, import/export and selection.
- `engine`: pagination, layout, font measurement, hit testing and render caches.
- `bridge`: WebAssembly boundary used by the embedded Svelte editor.

Python remains responsible for agents, providers, RAG, persistence and desktop lifecycle. The
desktop package should contain only compiled Rust artifacts; Cargo, `target/` and source files are
development inputs and must not be copied into the installer.

Run `cargo test --workspace --manifest-path engine/Cargo.toml` during development. The application
must never invoke Cargo or download a Rust toolchain at runtime.
