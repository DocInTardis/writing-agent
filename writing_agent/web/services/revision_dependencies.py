"""Legacy Web composition boundary for the explicitly injected revision workflow."""
from functools import partial
from typing import Any

from writing_agent.workflows.revision_request_workflow import (
    HeadingNormalizer, RevisionDeps, RevisionPromptBuilder, RevisionTextExtractor,
    RevisionValidator, SectionResolver,
)


def build_revision_deps(
    app: Any, *, fallback_normalize_heading_text_fn: HeadingNormalizer,
    resolve_target_section_selection_fn: SectionResolver,
    build_revision_fallback_prompt_fn: RevisionPromptBuilder,
    extract_revision_fallback_text_fn: RevisionTextExtractor,
    validate_revision_candidate_fn: RevisionValidator,
) -> RevisionDeps:
    normalize = getattr(app, '_normalize_heading_text', None)
    return RevisionDeps(
        environ=dict(app.os.environ),
        exception_factory=app.HTTPException,
        doc_ir_from_dict=lambda value: app.doc_ir_from_dict(value),
        doc_ir_to_text=lambda value: app.doc_ir_to_text(value),
        get_model_settings=app.get_ollama_settings,
        create_model_client=app.OllamaClient,
        analyze_message=app._run_message_analysis,
        hard_constraints=app._revision_hard_constraints,
        decide_revision=app._revision_decision_with_model,
        try_selected_edit=lambda **kwargs: app._try_revision_edit(**kwargs),
        replace_question_headings=app._replace_question_headings,
        postprocess_output=app._postprocess_output_text,
        set_doc_text=app._set_doc_text,
        persist_session=app.store.put,
        sanitize_output=lambda text: app._sanitize_output_text(text),
        looks_like_prompt_echo=lambda *args: app._looks_like_prompt_echo(*args),
        safe_doc_ir_payload=lambda text: app._safe_doc_ir_payload(text),
        normalize_heading_text_fn=normalize if callable(normalize) else fallback_normalize_heading_text_fn,
        resolve_target_section_selection_fn=resolve_target_section_selection_fn,
        build_revision_fallback_prompt_fn=build_revision_fallback_prompt_fn,
        extract_revision_fallback_text_fn=extract_revision_fallback_text_fn,
        validate_revision_candidate_fn=partial(validate_revision_candidate_fn, app),
    )
