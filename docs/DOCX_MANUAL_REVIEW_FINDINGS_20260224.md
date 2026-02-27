# DOCX Manual Review Findings (2026-02-24)

## Scope
- Trigger: user manual review feedback on exported DOCX quality.
- Cases:
  - `C-001.docx` from `.data/out/content_validation_20260224_202304/artifacts/C-001/C-001.docx`
  - `MR-001.docx` from `.data/out/content_validation_20260224_202304/artifacts/MR-001/MR-001.docx`
- Note: this record is diagnosis only; code changes are intentionally deferred.

## User-Reported Issues
1. `C-001.docx` formatting is chaotic:
   - title not centered
   - inconsistent font behavior
   - overall style rules not respected
2. `MR-001.docx` has:
   - Word compatibility warning(s) at open
   - content anomalies (truncation/fragmented section content, mixed heading/body residue such as `结论` + `(Conclusion)`)
   - body paragraphs too short for expected depth

## Evidence Snapshot
- Run summary:
  - `.data/out/content_validation_20260224_202304/content_validation_run_20260224_202304.json`
- Observed export methods:
  - `C-001`: `local_text_fallback`
  - `MR-001`: `ui_button` (server `/download/{doc_id}.docx`)
- Generated markdown snapshots:
  - `.data/out/content_validation_20260224_202304/artifacts/C-001/C-001.md`
  - `.data/out/content_validation_20260224_202304/artifacts/MR-001/MR-001.md`

## Root Cause Analysis
### A. `C-001.docx` formatting defects
- `C-001` was exported via `local_text_fallback` path.
- This fallback route is text-first and does not enforce full style mapping (title alignment, East-Asia font binding, run-level formatting consistency).
- Result: Word applies defaults, causing user-visible format drift.

### B. `MR-001.docx` compatibility/content defects
- `MR-001` was exported via server-side UI download path, not local fallback.
- During multi-round generation, status instability existed (busy/preparing/stream conflict states were observed in nearby runs).
- The final content itself already contained structural quality issues before DOCX packaging (short sections, bilingual residue).
- Compatibility warning likely comes from a specific server-side export branch, but the exact branch provenance was not persisted in the run artifact, so branch-level attribution is currently incomplete.

## Process Reflection (What was missed)
1. "Export succeeded" was treated as too-close proxy for "format quality passed".
2. Fallback export (`local_text_fallback`) was not hard-blocked for format-sensitive scenarios.
3. Soft-pass logic in unstable generation states allowed low-quality outputs to pass acceptance in edge cases.
4. No explicit compatibility-gate existed before final pass.
5. Export branch provenance was not logged, increasing root-cause latency.

## Deferred Fix Backlog (To execute together later)
1. Add export provenance logging into validation artifacts:
   - exact branch used (`html_docx_exporter` / `rust_docx_export` / parsed builder / local fallback)
2. Add hard fail rule:
   - for format-sensitive cases, reject `local_text_fallback` as pass condition
3. Add DOCX compatibility precheck gate:
   - fail run when compatibility warnings are detected
4. Tighten multi-round acceptance gates:
   - minimum section richness
   - forbid heading-body residue patterns
   - stronger "content completeness" checks
5. Add post-export style compliance checks:
   - heading alignment
   - font consistency
   - paragraph-level rule conformance

## Decision Status
- Current status: **recorded, pending bundled remediation**
- Owner: ongoing validation/hardening track
- Planned execution mode: implement all above items in one dedicated fix batch, then rerun `C-001` + `MR-001` first, then wider suite.
