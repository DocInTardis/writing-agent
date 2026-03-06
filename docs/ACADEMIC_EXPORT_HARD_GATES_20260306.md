# Academic Export Hard Gates (2026-03-06)

This document defines the mandatory export checks for thesis-style documents.

## Scope
- Applied in `strict_doc_format=true` and `academic_like=true` flows.
- Implemented in `writing_agent/web/domains/export_structure_domain.py`.

## Mandatory Gates
1. H2 depth gate
- Code: `heading_depth_h2_insufficient`
- Rule: non-structural H2 count must be `>= min_h2_count`.
- Excluded from count: TOC / References / Abstract / Keywords headings.

2. H3 depth gate
- Code: `heading_depth_h3_insufficient`
- Rule: non-structural H3 count must be `>= min_h3_count`.
- Excluded from count: TOC / References / Abstract / Keywords headings.

3. Reference numbering gate
- Code: `reference_numbering_invalid`
- Rule: reference indices must be sequential (`[1]...[N]`) inside reference section.
- Also flags malformed escaped forms when numbering cannot be resolved.

4. GB/T 7714 field-level gate
- Code: `reference_gbt7714_noncompliant`
- Rule per reference item:
  - has document type marker (`[J]`, `[M]`, `[C]`, `[S]`, `[EB/OL]`, etc.)
  - has year (`19xx` or `20xx`)
  - if URL exists: has access date (`[YYYY-MM-DD]`)
  - if URL exists: uses online marker (`[EB/OL]` / `[DB/OL]` / `[CP/OL]` / `[DS/OL]`)

## Auto-fix Behavior
- Enabled when `auto_fix=1` during export check.
- Current normalization:
  - normalize escaped index markers (`\\[1\\]` -> `[1]`)
  - renumber references sequentially
  - add default type marker if missing:
    - URL item -> `[EB/OL]`
    - non-URL item -> `[J]`
  - add access date for URL items if missing (`[today]`)

## Defaults
- `WRITING_AGENT_ENFORCE_HEADING_DEPTH=1`
- `WRITING_AGENT_MIN_H2_COUNT=3`
- `WRITING_AGENT_MIN_H3_COUNT=1`
- `WRITING_AGENT_ENFORCE_GBT7714_REFERENCE=1`

## Per-document Overrides (`generation_prefs`)
- `enforce_heading_depth: bool`
- `min_h2_count: int`
- `min_h3_count: int`
- `enforce_gbt7714_reference: bool`

## Related Changes
- `CitationAgent.format_reference` now emits GB/T-style output when `CitationStyle.GBT`.
- `graph_reference_domain.format_reference_items` now emits GB/T-style rows by default.
