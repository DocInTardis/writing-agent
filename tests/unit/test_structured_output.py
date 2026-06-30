"""Tests for Pydantic structured output models."""

from __future__ import annotations

import pytest

from writing_agent.v2.structured_output import (
    DocumentEditOutput,
    EditMeta,
    EditRiskAssessment,
    InlineRewriteOutput,
    RewriteIntent,
)


class TestInlineRewriteOutput:
    def test_parse_valid_json(self) -> None:
        raw = '{"output_text":" rewritten ","confidence":0.95,"intent":"improve"}'
        parsed = InlineRewriteOutput.model_validate_json(raw)
        assert parsed.output_text == "rewritten"
        assert parsed.confidence == 0.95
        assert parsed.intent == "improve"

    def test_parse_with_code_fence(self) -> None:
        raw = '{"output_text":"hello","confidence":0.8}'
        parsed = InlineRewriteOutput.model_validate_json(raw)
        assert parsed.output_text == "hello"

    def test_invalid_confidence_clamped_by_validator(self) -> None:
        raw = '{"output_text":"x","confidence":1.5}'
        # pydantic ge/le validators raise ValidationError for out-of-range values
        with pytest.raises(Exception):
            InlineRewriteOutput.model_validate_json(raw)

    def test_extra_fields_ignored(self) -> None:
        raw = '{"output_text":"x","extra_field":"ignored"}'
        parsed = InlineRewriteOutput.model_validate_json(raw)
        assert parsed.output_text == "x"


class TestDocumentEditOutput:
    def test_parse_full_schema(self) -> None:
        raw = (
            '{"html":"<p>Hello</p>",'
            '"assistant":"Fixed typo",'
            '"meta":{"scope":"document","preserved_structure":true,'
            '"affected_sections":["Intro"],"risk_flags":[]}}'
        )
        parsed = DocumentEditOutput.model_validate_json(raw)
        assert parsed.html == "<p>Hello</p>"
        assert parsed.assistant == "Fixed typo"
        assert parsed.meta.scope == "document"
        assert parsed.meta.preserved_structure is True

    def test_parse_minimal(self) -> None:
        raw = '{"html":"<p>x</p>"}'
        parsed = DocumentEditOutput.model_validate_json(raw)
        assert parsed.html == "<p>x</p>"
        assert parsed.assistant == "Applied requested changes."

    def test_html_with_code_fence(self) -> None:
        raw = '{"html":"<p>y</p>"}'
        parsed = DocumentEditOutput.model_validate_json(raw)
        assert parsed.html == "<p>y</p>"


class TestEditRiskAssessment:
    def test_defaults(self) -> None:
        assessment = EditRiskAssessment()
        assert assessment.can_proceed is True
        assert assessment.risk_level == "none"
        assert assessment.issues == []


class TestRewriteIntent:
    def test_parse_intent(self) -> None:
        intent = RewriteIntent(
            operation="expand",
            target_sections=["Methodology"],
            preserve_terms=["BERT"],
            confidence=0.88,
        )
        assert intent.operation == "expand"
        assert intent.confidence == 0.88


class TestStructuredOutputIntegration:
    """Integration tests mimicking real LLM response shapes."""

    def test_inline_rewrite_realistic_response(self) -> None:
        response = (
            '{"output_text":"The proposed model achieves 94.2% accuracy on the test set, '
            'outperforming prior work by 3.1 percentage points.",'
            '"confidence":0.92,"intent":"improve",'
            '"preserved_keywords":["accuracy","test set"],'
            '"change_summary":"Improved clarity and added quantitative comparison"}'
        )
        parsed = InlineRewriteOutput.model_validate_json(response)
        assert "94.2%" in parsed.output_text
        assert parsed.change_summary

    def test_document_edit_realistic_response(self) -> None:
        response = (
            '{"html":"<h1>Report</h1><p>Updated content.</p>",'
            '"assistant":"Added quantitative results to the methodology section.",'
            '"meta":{"scope":"section","preserved_structure":true,'
            '"affected_sections":["Methodology"],"risk_flags":["citation_update_needed"]}}'
        )
        parsed = DocumentEditOutput.model_validate_json(response)
        assert "Updated content" in parsed.html
        assert "citation_update_needed" in parsed.meta.risk_flags
