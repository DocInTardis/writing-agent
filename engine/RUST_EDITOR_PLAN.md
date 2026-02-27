# Rust + egui Editor Roadmap

This document defines a practical implementation roadmap for the Rust editor stack in this repository.

## Scope

The roadmap covers:
- document core model and editing commands
- layout/render pipeline
- interaction (cursor/selection/input)
- import/export integration with existing Python system
- performance and stability gates

## Workspace Structure

```text
engine/
|- core/        # document model, AST, commands, diff, import/export adapters
|- engine/      # layout + render primitives + caches
|- ui/          # egui application shell
|- bridge/      # FFI bridge to Python runtime
|- benches/     # criterion benchmarks
`- tests/       # integration/e2e samples
```

## Performance Targets

- input latency: `< 8ms`
- 10k block layout: `< 50ms`
- frame render budget: `< 8.33ms` (120fps)
- scroll continuity on large docs: `>= 120fps` on baseline machine
- memory footprint (10k blocks): `< 20MB` incremental growth

## Milestones

### M0: Foundation

Deliverables:
- Rust workspace compiles on Windows/macOS/Linux
- baseline benchmark suite enabled
- CI includes benchmark regression checks

Exit criteria:
- `cargo test` and `cargo bench` pass in CI
- benchmark output is versioned in artifacts

### M1: Document Core

Deliverables:
- immutable-ish document tree model
- editing command set (`insert`, `delete`, `replace`, `format`)
- JSON import/export and compatibility fixtures

Exit criteria:
- deterministic command replay
- snapshot tests for complex mixed content

### M2: Layout Engine

Deliverables:
- paragraph/block layout
- line-break handling for CJK + latin mixed text
- layout cache with dirty-region recomputation

Exit criteria:
- no full relayout on small edits
- layout benchmark within target budget

### M3: Rendering

Deliverables:
- page mode and continuous mode rendering
- dirty-rect repaint optimization
- render cache with invalidation strategy

Exit criteria:
- repaint cost proportional to changed region
- stable frame time under continuous typing/scrolling

### M4: Interaction Layer

Deliverables:
- cursor movement and selection model
- IME-safe text input path
- undo/redo stack and checkpoints

Exit criteria:
- cursor/selection behavior consistent with expected editor semantics
- undo/redo remains stable for long sessions

### M5: Structured Content

Deliverables:
- table and image block support
- list and heading editing operations
- copy/paste handling for rich/plain text

Exit criteria:
- structured blocks survive roundtrip import/export
- command history remains valid after structured edits

### M6: Integration and Export

Deliverables:
- bridge contracts to Python runtime
- DOCX/Markdown export parity checks
- fallback path if Rust export fails

Exit criteria:
- compatibility matrix green for representative fixtures
- rollback path documented and tested

## Risk Register

### Font and shaping variability

Mitigation:
- keep font loading abstraction isolated
- benchmark with multiple font packs
- preflight fallback font verification in CI

### Cross-platform text input differences

Mitigation:
- dedicated IME test scenarios per OS
- explicit keyboard/event normalization layer

### Cache invalidation correctness

Mitigation:
- add property-based tests for dirty-region propagation
- run replay-based regression tests after every cache change

### Export parity drift

Mitigation:
- keep golden fixtures for Markdown and DOCX
- run diff-based compatibility check in pre-release CI

## CI Gates

Required gates:
- `cargo test --workspace`
- `cargo clippy --workspace -- -D warnings`
- `cargo fmt --all -- --check`
- benchmark threshold check (`benches/bench_thresholds.json`)

Optional gates:
- memory profiling run on nightly schedule
- long-run render soak test

## Delivery Checklist

- [ ] core model and command replay stable
- [ ] layout cache and dirty-region logic validated
- [ ] interaction behavior validated with IME cases
- [ ] structured content editing completed
- [ ] export parity report published
- [ ] benchmark baselines refreshed
- [ ] runbook updated
