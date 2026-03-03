from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


PROMPT_CONTRACT_MARKERS: dict[str, tuple[str, ...]] = {
    "writing_agent/v2/prompts.py": (
        "<task>plan_document_structure</task>",
        "<task>analyze_user_requirement</task>",
        "<task>write_section_blocks</task>",
        "<task>format_references</task>",
        "<task>revise_document</task>",
        "<constraints>",
    ),
    "writing_agent/v2/graph_runner.py": (
        "<retry_reason>",
        "<task>plan_sections_list</task>",
        "<constraints>",
    ),
    "writing_agent/v2/graph_runner_runtime.py": (
        "<available_sources>",
        "_runtime_escape_prompt_text",
    ),
    "writing_agent/v2/graph_section_draft_domain.py": (
        "<task>continue_section_draft</task>",
        "<constraints>",
        "<retry_reason>",
    ),
    "writing_agent/v2/graph_reference_domain.py": (
        "<task>evidence_extraction</task>",
        "<constraints>",
        "<available_sources>",
    ),
    "writing_agent/v2/graph_aggregate_domain.py": (
        "<task>aggregate_conclusion_and_transitions</task>",
        "<task>aggregate_full_draft</task>",
        "<task>repair_draft</task>",
        "<constraints>",
    ),
    "writing_agent/web/services/generation_service.py": (
        "<task>revise_full_document</task>",
        "<constraints>",
        "<revised_markdown>",
    ),
    "writing_agent/web/api/editing_flow.py": (
        "<task>diagram_spec_generation</task>",
        "<constraints>",
        "<user_request>",
    ),
    "writing_agent/web/app_v2_generation_helpers_runtime.py": (
        "<task>full_document_generation</task>",
        "<constraints>",
    ),
    "writing_agent/web/domains/revision_edit_runtime_domain.py": (
        "<task>plan_edit_operations</task>",
        "<task>rewrite_selected_text</task>",
        "<task>revise_full_document</task>",
        "<revised_document>",
    ),
    "writing_agent/agents/outline.py": (
        "<task>generate_outline_markdown</task>",
        "<constraints>",
        "_escape_prompt_text",
    ),
    "writing_agent/agents/writing.py": (
        "<task>write_section_paragraphs</task>",
        "<task>rewrite_paragraph</task>",
        "<constraints>",
        "_escape_prompt_text",
    ),
    "writing_agent/agents/document_edit.py": (
        "<task>apply_instruction_to_html</task>",
        "<constraints>",
        "<retry_reason>",
    ),
    "writing_agent/agents/diagram_agent.py": (
        "<task>diagram_spec_generation</task>",
        "<constraints>",
        "<retry_reason>",
    ),
    "writing_agent/web/app.py": (
        "<task>rewrite_single_section</task>",
        "<task>aggregate_report_html</task>",
        "<constraints>",
        "escape_prompt_text",
    ),
}


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_prompt_contract_markers_are_present() -> None:
    missing: list[str] = []
    for rel_path, markers in PROMPT_CONTRACT_MARKERS.items():
        text = _read(rel_path)
        for marker in markers:
            if marker not in text:
                missing.append(f"{rel_path}: missing marker {marker}")
    assert not missing, "\n".join(missing)


def test_graph_runner_json_retry_keeps_context_on_repair() -> None:
    text = _read("writing_agent/v2/graph_runner.py")
    assert 'f"{base_user}\\n"' in text
    assert "<retry_reason>" in text
    assert 'attempt_user = "Return only a JSON object."' not in text
