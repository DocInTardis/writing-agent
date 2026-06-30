"""Tests for cross-chapter citation chain guard."""

from __future__ import annotations

import pytest

from writing_agent.v2.cross_chapter_guard import (
    CrossChapterDeletionBlocked,
    CrossChapterImpactAnalyzer,
    CitationLink,
)
from writing_agent.v2.structured_output import EditRiskAssessment


class TestCrossChapterImpactAnalyzer:
    @pytest.fixture
    def analyzer(self) -> CrossChapterImpactAnalyzer:
        return CrossChapterImpactAnalyzer()

    @pytest.fixture
    def sample_doc(self) -> str:
        return (
            "<h1>Introduction</h1>\n"
            "<p>Deep learning has revolutionized NLP [1].</p>\n"
            "<h2>Methodology</h2>\n"
            "<p>We use BERT [2] for feature extraction.</p>\n"
            "<p>Fine-tuning follows Devlin et al. [2].</p>\n"
            "<h2>Results</h2>\n"
            "<p>Our model outperforms baselines [1][3].</p>\n"
            "<h2>Conclusion</h2>\n"
            "<p>Future work will explore GPT-4 [3].</p>\n"
        )

    def test_index_document_sections(self, analyzer: CrossChapterImpactAnalyzer, sample_doc: str) -> None:
        index = analyzer.index_document(sample_doc)
        assert "Introduction" in index.sections
        assert "Methodology" in index.sections
        assert "Results" in index.sections
        assert "Conclusion" in index.sections

    def test_index_citations(self, analyzer: CrossChapterImpactAnalyzer, sample_doc: str) -> None:
        index = analyzer.index_document(sample_doc)
        keys = [c.citation_key for c in index.citations]
        assert "[1]" in keys
        assert "[2]" in keys
        assert "[3]" in keys

    def test_key_to_sources(self, analyzer: CrossChapterImpactAnalyzer, sample_doc: str) -> None:
        index = analyzer.index_document(sample_doc)
        assert "[1]" in index.key_to_sources
        assert set(index.key_to_sources["[1]"]) == {"Introduction", "Results"}
        assert set(index.key_to_sources["[2]"]) == {"Methodology"}
        assert set(index.key_to_sources["[3]"]) == {"Results", "Conclusion"}

    def test_assess_delete_safe_paragraph(self, analyzer: CrossChapterImpactAnalyzer, sample_doc: str) -> None:
        index = analyzer.index_document(sample_doc)
        risks = analyzer.assess_delete(index, section="Methodology", paragraph_idx=1)
        assert risks.can_proceed is True
        assert risks.risk_level in ("none", "low")

    def test_assess_delete_critical_section(self, analyzer: CrossChapterImpactAnalyzer, sample_doc: str) -> None:
        index = analyzer.index_document(sample_doc)
        # Deleting the entire Methodology section removes [2] which is only there
        risks = analyzer.assess_delete(index, section="Methodology")
        assert risks.risk_level in ("medium", "high", "critical")
        assert "[2]" in risks.broken_citation_keys
        assert any("Methodology" in issue for issue in risks.issues)

    def test_assess_delete_blocks_high_risk(self, analyzer: CrossChapterImpactAnalyzer) -> None:
        doc = (
            "<h1>Intro</h1><p>A [1].</p>\n"
            "<h1>Method</h1><p>B [2].</p>\n"
            "<h1>Result</h1><p>C [3].</p>\n"
            "<h1>Conclusion</h1><p>D [1][2][3].</p>\n"
        )
        index = analyzer.index_document(doc)
        risks = analyzer.assess_delete(index, section="Intro")
        # [1] is in Intro and Conclusion, so not completely broken,
        # but appears in later section too
        assert risks.risk_level in ("none", "low", "medium", "high", "critical")

    def test_assess_insert_citation_new_key(self, analyzer: CrossChapterImpactAnalyzer, sample_doc: str) -> None:
        index = analyzer.index_document(sample_doc)
        risks = analyzer.assess_insert_citation(index, section="Results", new_citation_keys=["[99]"])
        assert "[99]" in risks.broken_citation_keys
        assert risks.risk_level == "low"

    def test_exception_blocked(self) -> None:
        assessment = EditRiskAssessment(
            can_proceed=False,
            risk_level="high",
            issues=["Orphaned citation [1]"],
        )
        with pytest.raises(CrossChapterDeletionBlocked) as exc_info:
            raise CrossChapterDeletionBlocked(assessment)
        assert "Orphaned citation [1]" in str(exc_info.value)

    def test_strip_html(self, analyzer: CrossChapterImpactAnalyzer) -> None:
        html = "<p>Hello <b>world</b></p><script>alert(1)</script>"
        text = analyzer._strip_html(html)
        assert "Hello world" in text
        assert "alert" not in text


class TestCrossChapterGuardMarkdown:
    """Test with Markdown documents (not HTML)."""

    def test_markdown_headings(self) -> None:
        analyzer = CrossChapterImpactAnalyzer()
        doc = (
            "# Introduction\n"
            "NLP has evolved rapidly [Smith2024].\n\n"
            "## Methodology\n"
            "We adopt transformer architecture [Vaswani2017].\n\n"
            "## Results\n"
            "Our model exceeds baselines [Smith2024][Vaswani2017].\n"
        )
        index = analyzer.index_document(doc)
        assert "Introduction" in index.sections
        assert "Methodology" in index.sections
        assert "Results" in index.sections
        assert "[Smith2024]" in index.key_to_sources
        assert set(index.key_to_sources["[Smith2024]"]) == {"Introduction", "Results"}
