## Summary

- What changed?
- Why was this change needed?

## Scope

- [ ] Backend (`writing_agent/`)
- [ ] Frontend (`writing_agent/web/frontend_svelte/`)
- [ ] Scripts / CI (`scripts/`, `.github/workflows/`)
- [ ] Docs / configuration (`docs/`, `security/`)

## Validation

- [ ] `python -m pytest -q tests`
- [ ] `python -m compileall -q writing_agent scripts`
- [ ] `npm --prefix writing_agent/web/frontend_svelte run build` (if frontend changed)

## Compatibility

- [ ] No breaking API changes
- [ ] Breaking changes documented with migration steps
- [ ] N/A

## Checklist

- [ ] I added/updated tests for behavior changes.
- [ ] I updated docs for user-visible changes.
- [ ] I confirmed no secrets are committed.
