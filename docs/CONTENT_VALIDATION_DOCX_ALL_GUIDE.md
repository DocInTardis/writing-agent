# Content Validation DOCX-All Guide

## Goal

Use frontend Playwright flow to execute content validation cases, and export a DOCX file for every selected case's final content.

This runner now supports:

- `--export-docx-all`: export DOCX for all selected single + multiround cases.
- Markdown snapshot for each case final content.
- Multiround per-round markdown snapshots.
- Export fallback chain:
  - top-bar `Export Word` button
  - direct browser download route fallback
  - local text-to-docx fallback (last resort)

## Script

- `scripts/ui_content_validation_runner.py`

## Full Run Command (70 + 24)

```powershell
python -u scripts/ui_content_validation_runner.py `
  --dataset tests/fixtures/content_validation/content_cases_70.json `
  --multiround tests/fixtures/content_validation/multiround_cases_24.json `
  --run-all `
  --start-server `
  --timeout-s 220 `
  --export-docx-all `
  --checkpoint .data/out/content_validation_docx_all_checkpoint.json `
  --resume
```

## Output Layout

Runner output root:

- `.data/out/content_validation_<timestamp>/`

Per case artifacts:

- Single case:
  - `.data/out/content_validation_<ts>/artifacts/<case_id>/<case_id>.docx`
  - `.data/out/content_validation_<ts>/artifacts/<case_id>/<case_id>.md`
- Multiround case:
  - `.data/out/content_validation_<ts>/artifacts/<case_id>/<case_id>.docx`
  - `.data/out/content_validation_<ts>/artifacts/<case_id>/<case_id>.md` (final)
  - `.data/out/content_validation_<ts>/artifacts/<case_id>/round_01.md`, `round_02.md`, ...

Run-level summary:

- `.data/out/content_validation_<ts>/content_validation_run_<ts>.json`
- `.data/out/content_validation_<ts>/content_validation_summary_<ts>.md`

## Recent Verification Runs

- `content_validation_20260223_175025`:
  - selected single=`1`, multiround=`0`
  - `C-001` exported: `.data/out/content_validation_20260223_175025/artifacts/C-001/C-001.docx`
- `content_validation_20260223_175344`:
  - selected single=`1`, multiround=`1`
  - `C-001` exported: `.data/out/content_validation_20260223_175344/artifacts/C-001/C-001.docx`
  - `MR-001` exported: `.data/out/content_validation_20260223_175344/artifacts/MR-001/MR-001.docx`
- `content_validation_20260223_180936` (model disabled failure-path test):
  - selected single=`1`, multiround=`0`
  - `C-001` exported with method `local_text_fallback`:
    `.data/out/content_validation_20260223_180936/artifacts/C-001/C-001.docx`

## Quick Verification (Count exported DOCX)

```powershell
@'
import json
from pathlib import Path

run_dir = Path('.data/out/content_validation_20260223_175344')
run_json = next(run_dir.glob('content_validation_run_*.json'))
data = json.loads(run_json.read_text(encoding='utf-8'))

rows = data['results']['single'] + data['results']['multiround']
ok = 0
for r in rows:
    exp = r.get('docx_export') or {}
    if exp.get('ok') and Path(exp.get('path', '')).exists():
        ok += 1
print('cases=', len(rows), 'docx_ok=', ok)
'@ | python -
```
