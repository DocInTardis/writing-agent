# Frontend Workbench Architecture

Decoupling layout:

- `src/lib/flows/workbenchStateMachine.ts` (state transitions)
- `src/lib/flows/streamPatcher.ts` (incremental patch apply)
- `src/lib/flows/sessionRecovery.ts` (refresh/disconnect recovery)
- `src/lib/flows/aiSdkClient.ts` (stream transport)
- `src/lib/stores/workbenchState.ts` (state stores)
- `src/lib/components/ParagraphDiffPanel.svelte` (diff/patch review)
- `src/lib/components/CitationReviewPanel.svelte` (citation panel)
- `src/lib/components/TemplateLintPanel.svelte` (template lint UX)
- `src/lib/components/ErrorPathPanel.svelte` (exception-path UX)

Responsibility split:

- state machine
- render components
- command/data flow
- recovery/error handling
