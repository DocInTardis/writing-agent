# Prompt Registry

Core modules:

- `writing_agent/v2/prompt_registry.py`
- `writing_agent/v2/context_governance.py`
- `writing_agent/v2/prompt_injection_guard.py`
- `scripts/prompt_lint.py`
- `scripts/prompt_ab_test.py`
- `templates/prompt_registry/prompts.json`
- `templates/few_shot/README.md`

Delivered features:

- prompt version/tag/cohort/rollback registry
- layer split: system/developer/task/style/citation
- schema validation and fallback
- prompt lint checks (length/coverage/forbidden tokens)
- A/B assignment scaffold
- few-shot sample repository
- token budgeting + context compression
- prompt-injection scan and quote sanitization
