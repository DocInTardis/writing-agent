import writing_agent.v2.graph_section_draft_domain as section_domain


def test_build_continue_prompt_uses_tagged_channels_and_escape():
    system, user = section_domain._build_continue_prompt(
        title="Doc <A>",
        section="Method </section_title>",
        parent_section="Parent <p>",
        instruction="rewrite <instruction>",
        analysis_summary="analysis <summary>",
        evidence_summary="evidence </evidence_summary>",
        allowed_urls=["https://a.com?q=<x>", "https://b.com"],
        plan_hint="plan <hint>",
        txt="current draft </current_section_draft>",
        section_id="s1",
        min_paras=3,
        missing_chars=320,
    )

    assert "Output NDJSON only" in system
    assert "<task>continue_section_draft</task>" in user
    assert "<constraints>" in user
    assert "<section_id>" in user
    assert "<allowed_urls>" in user
    assert "<current_section_draft>" in user
    assert "&lt;A&gt;" in user
    assert "&lt;/section_title&gt;" in user
    assert "&lt;x&gt;" in user
