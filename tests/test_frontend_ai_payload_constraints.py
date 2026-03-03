from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_ai_payload_helper_defines_core_guardrails() -> None:
    text = _read("writing_agent/web/frontend_svelte/src/lib/utils/ai_payload.ts")
    assert "sanitizeAiInputText" in text
    assert "sanitizeAiDocumentText" in text
    assert "sanitizeAiSelectionPayload" in text
    assert "buildGenerateRequestPayload" in text
    assert "normalizeContextPolicy" in text
    assert "DEFAULT_CONTEXT_POLICY" in text
    assert "dynamic_v1" in text
    assert "CONTROL_CHAR_RE" in text


def test_app_workbench_uses_ai_payload_guardrails() -> None:
    text = _read("writing_agent/web/frontend_svelte/src/AppWorkbench.svelte")
    assert "from './lib/utils/ai_payload'" in text
    assert "buildGenerateRequestPayload(" in text
    assert "sanitizeAiInputText(" in text
    assert "sanitizeAiDocumentText(" in text
    assert "sanitizeAiSelectionPayload(" in text
    assert "sanitizeAiStringList(" in text


def test_diagram_canvas_uses_prompt_sanitizer() -> None:
    text = _read("writing_agent/web/frontend_svelte/src/lib/components/DiagramCanvas.svelte")
    assert "sanitizeDiagramPrompt" in text
    assert "const finalPrompt = sanitizeDiagramPrompt" in text
