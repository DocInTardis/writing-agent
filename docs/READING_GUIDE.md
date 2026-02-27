# Code Reading Guide

This guide is for quickly understanding `writing-agent` as a working system.

## 1. Start from Runtime Entrypoints

Read in this order:

1. `writing_agent/launch.py`
2. `writing_agent/web/app_v2.py`
3. `writing_agent/web/api/` (HTTP route modules)
4. `writing_agent/web/services/` (business orchestration)

What to extract:
- how a request enters the system
- where request state is loaded/saved
- where generation is dispatched

## 2. Follow the Generation Pipeline

Core generation path:

1. `writing_agent/web/services/generation_service.py`
2. `writing_agent/web/app_v2_generate_stream_runtime.py`
3. `writing_agent/v2/graph_runner_runtime.py`
4. `writing_agent/v2/graph_runner.py`
5. `writing_agent/v2/graph_runner_post_domain.py`

What to extract:
- planning stage vs drafting stage vs aggregation stage
- timeout / retry / fallback behavior
- where quality checks are applied

## 3. Understand State and Persistence

Read:

1. `writing_agent/storage.py`
2. `writing_agent/state_engine/`
3. `writing_agent/v2/text_store.py`

What to extract:
- in-memory session layout
- versioning and replay responsibilities
- text block storage and IDs

## 4. Understand LLM Provider Routing

Read:

1. `writing_agent/llm/provider.py`
2. `writing_agent/llm/factory.py`
3. `writing_agent/llm/model_router.py`
4. `writing_agent/llm/providers/`

What to extract:
- provider contract
- backend selection (`ollama`, node gateway, OpenAI-compatible)
- model fallback behavior

## 5. Read Frontend in Vertical Slices

Read:

1. `writing_agent/web/frontend_svelte/src/App.svelte`
2. `writing_agent/web/frontend_svelte/src/AppWorkbench.svelte`
3. `writing_agent/web/frontend_svelte/src/lib/components/EditorWorkbench.svelte`
4. `writing_agent/web/frontend_svelte/src/lib/flows/workbenchStateMachine.ts`

What to extract:
- UI state transitions
- stream event handling (`delta`, `section`, `final`)
- error and recovery paths

## 6. Read Validation and Guardrails

Read:

1. `scripts/` guards (size, complexity, architecture boundaries)
2. `security/*.json` policy-as-code
3. `.github/workflows/`

What to extract:
- what quality gates are enforced in CI
- which failures are warning vs blocking

## 7. Practical Reading Strategy

Use this checklist while reading any module:

1. Identify inputs and outputs first.
2. Find external dependencies (LLM, storage, file system).
3. Identify fallback and timeout branches.
4. Mark side effects (state write, file write, network call).
5. Confirm where errors are surfaced to API responses.

## 8. Fast Debug Entry Map

If a feature breaks, start here:

- Generation output wrong: `writing_agent/v2/graph_runner_runtime.py`
- Stream interrupted: `writing_agent/web/app_v2_generate_stream_runtime.py`
- Export issues: `writing_agent/web/api/export_flow.py`
- Citation verify issues: `writing_agent/web/api/citation_flow.py`
- UI rendering/interaction: `writing_agent/web/frontend_svelte/src/lib/components/`
