# Content Validation Execution Dataset (70 single + 24 multiround)

This document maps to executable assets:

- `tests/fixtures/content_validation/content_cases_70.json`
- `tests/fixtures/content_validation/multiround_cases_24.json`

## 1. Schema

- Single case fields: `id/group/group_label/genre/audience/topic/prompt/constraints/acceptance`
- Multiround case fields: `id/title/group/topic/anchors/rounds[]`
- Round fields: `round/round_input/must_keep/must_change/acceptance_checks`

## 2. Single Coverage (70)

| Group | Count |
|---|---:|
| `academic_research` | 7 |
| `customer_service` | 7 |
| `enterprise_management` | 7 |
| `finance_literacy` | 7 |
| `government_public` | 7 |
| `healthcare_science` | 7 |
| `inclusive_education` | 7 |
| `legal_compliance` | 7 |
| `marketing_brand` | 7 |
| `technical_manual` | 7 |

## 3. Multiround Coverage (24)

| Group | Count |
|---|---:|
| `academic_research` | 3 |
| `customer_service` | 1 |
| `enterprise_management` | 3 |
| `finance_literacy` | 1 |
| `government_public` | 2 |
| `healthcare_science` | 1 |
| `inclusive_education` | 3 |
| `legal_compliance` | 2 |
| `marketing_brand` | 3 |
| `technical_manual` | 5 |

## 4. Constraint Coverage

- Font and size constraints in every single group via `font_size_strict`.
- Bilingual terminology constraints in every single group via `bilingual_terms`.
- Safety boundary and disclaimers in high-risk domains (health, legal, finance).
- 24 multiround scenarios expanded into 4 rounds with per-round acceptance checks.

## 5. Run Commands

```bash
python scripts/ui_content_validation_runner.py --dataset tests/fixtures/content_validation/content_cases_70.json --multiround tests/fixtures/content_validation/multiround_cases_24.json --group-smoke --start-server
python scripts/ui_content_validation_runner.py --dataset tests/fixtures/content_validation/content_cases_70.json --multiround tests/fixtures/content_validation/multiround_cases_24.json --run-all --start-server --checkpoint .data/out/content_validation_checkpoint.json
```

## 6. Outputs

- Run JSON: `.data/out/content_validation_<timestamp>/content_validation_run_<timestamp>.json`
- Summary MD: `.data/out/content_validation_<timestamp>/content_validation_summary_<timestamp>.md`
- Case artifacts: `.data/out/content_validation_<timestamp>/artifacts/<case_id>/`
