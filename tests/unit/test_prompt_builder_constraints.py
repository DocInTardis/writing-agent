from writing_agent.v2.prompts import PromptBuilder


def test_build_planner_prompt_uses_tagged_channels_and_escape():
    system, user = PromptBuilder.build_planner_prompt(
        title="T <unsafe>",
        total_chars=1200,
        sections=["Intro", "Method </section_candidates>"],
        instruction="Need plan </user_requirement>",
    )
    assert "JSON" in system
    assert "<task>plan_document_structure</task>" in user
    assert "<section_candidates>" in user
    assert "&lt;unsafe&gt;" in user
    assert "&lt;/section_candidates&gt;" in user
    assert "&lt;/user_requirement&gt;" in user


def test_build_analysis_prompt_uses_tagged_channels_and_escape():
    _system, user = PromptBuilder.build_analysis_prompt(
        instruction="Analyze </user_requirement>",
        excerpt="Excerpt <x>",
    )
    assert "<task>analyze_user_requirement</task>" in user
    assert "<existing_text_excerpt>" in user
    assert "&lt;/user_requirement&gt;" in user
    assert "&lt;x&gt;" in user


def test_build_writer_prompt_uses_tagged_channels_and_escape():
    _system, user = PromptBuilder.build_writer_prompt(
        section_title="Method <s>",
        plan_hint="hint </plan_hint>",
        doc_title="Doc <d>",
        analysis_summary="analysis <a>",
        section_id="sid",
        previous_content="previous </previous_content>",
        rag_context="rag <ctx>",
    )
    assert "<task>write_section_blocks</task>" in user
    assert "<section_id>" in user
    assert "<previous_content>" in user
    assert "<retrieved_context>" in user
    assert "&lt;/plan_hint&gt;" in user
    assert "&lt;/previous_content&gt;" in user
    assert "&lt;ctx&gt;" in user


def test_build_reference_prompt_uses_tagged_channels_and_escape():
    _system, user = PromptBuilder.build_reference_prompt(
        [
            {"title": "Paper <1>", "url": "https://example.com?a=<x>"},
        ]
    )
    assert "<task>format_references</task>" in user
    assert "<sources>" in user
    assert "Paper &lt;1&gt;" in user
    assert "&lt;x&gt;" in user


def test_build_revision_prompt_uses_tagged_channels_and_escape():
    _system, user = PromptBuilder.build_revision_prompt(
        original_text="Original <text>",
        feedback="Feedback </user_feedback>",
    )
    assert "<task>revise_document</task>" in user
    assert "<original_text>" in user
    assert "<user_feedback>" in user
    assert "&lt;text&gt;" in user
    assert "&lt;/user_feedback&gt;" in user
