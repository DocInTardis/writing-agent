## Summary

- What changed?
- Why was this change needed?

## Scope

- [ ] Backend (`writing_agent/`)
- [ ] Frontend (`writing_agent/web/frontend_svelte/`)
- [ ] Scripts / CI (`scripts/`, `.github/workflows/`)
- [ ] Docs / Governance (`docs/`, `security/`)

## Validation

- [ ] `python -m pytest -q tests`
- [ ] `python scripts/guard_file_line_limits.py --config security/file_line_limits.json --root .`
- [ ] `python scripts/guard_function_complexity.py --config security/function_complexity_limits.json --root .`
- [ ] `python scripts/guard_architecture_boundaries.py --config security/architecture_boundaries.json --root .`
- [ ] `npm --prefix writing_agent/web/frontend_svelte run build` (if frontend changed)

## Compatibility

- [ ] No breaking API changes
- [ ] Breaking changes documented with migration steps
- [ ] N/A

## Checklist

- [ ] I added/updated tests for behavior changes.
- [ ] I updated docs for user-visible changes.
- [ ] I confirmed no secrets are committed.
