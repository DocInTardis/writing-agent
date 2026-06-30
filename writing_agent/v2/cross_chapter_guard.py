"""Cross-chapter impact analysis and citation-chain breakage guard.

Scans documents for citation relationships and blocks deletions that would
orphan references or break citation chains across sections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from writing_agent.v2.structured_output import EditRiskAssessment


# Citation key patterns: [1], [Smith2024], [Smith et al., 2024], [1-3], [1,2,3]
_CITATION_KEY_RE = re.compile(
    r"\["
    r"(?:"
    r"\d+(?:\s*[-,]\s*\d+)*"           # [1], [1-3], [1,2,3]
    r"|[A-Za-z][A-Za-z0-9_]*(?:\s+et\s+al\.?)?,?\s*\d{4}"  # [Smith2024], [Smith et al., 2024]
    r")"
    r"\]"
)

# Section heading pattern (Markdown / HTML)
_SECTION_HEADING_RE = re.compile(r"(?m)^(?:#{1,6}\s+|<h[1-6][^>]*>)(.+?)(?:</h[1-6]>)?$")


@dataclass(frozen=True)
class CitationLink:
    """A directed citation link: source section → citation key."""

    source_section: str
    citation_key: str
    context_snippet: str
    paragraph_index: int


@dataclass(frozen=True)
class ChapterIndex:
    """Indexed view of a document's chapters/sections and their citations."""

    sections: list[str]
    section_paragraphs: dict[str, list[str]]
    citations: list[CitationLink]
    key_to_sources: dict[str, list[str]]  # citation key → list of source sections


class CrossChapterImpactAnalyzer:
    """Analyzes cross-chapter impact of proposed edits.

    Usage:
        analyzer = CrossChapterImpactAnalyzer()
        index = analyzer.index_document(html_doc)
        risks = analyzer.assess_delete(index, section="Methodology", paragraph_idx=3)
        if risks.risk_level in ("high", "critical"):
            raise CrossChapterDeletionBlocked(risks.issues)
    """

    def __init__(self, citation_re: re.Pattern[str] | None = None) -> None:
        self._citation_re = citation_re or _CITATION_KEY_RE

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_document(self, doc_html: str) -> ChapterIndex:
        """Build a ChapterIndex from an HTML/Markdown document."""
        sections: list[str] = []
        section_paragraphs: dict[str, list[str]] = {}
        citations: list[CitationLink] = []
        key_to_sources: dict[str, list[str]] = {}

        current_section = "__preamble__"
        current_paras: list[str] = []
        para_idx = 0

        # Extract headings from raw HTML before stripping tags
        raw_lines = doc_html.splitlines()
        heading_map: dict[int, str] = {}
        for li, line in enumerate(raw_lines):
            hm = _SECTION_HEADING_RE.match(line.strip())
            if hm:
                heading_map[li] = hm.group(1).strip()

        # Normalize: strip HTML tags for analysis
        text = self._strip_html(doc_html)
        lines = text.splitlines()

        for li, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Detect section heading (from pre-extracted heading map)
            if li in heading_map:
                # Save previous section
                if current_paras:
                    section_paragraphs[current_section] = current_paras
                current_section = heading_map[li]
                sections.append(current_section)
                current_paras = []
                para_idx = 0
                continue

            # Accumulate paragraphs (blank-line separated)
            current_paras.append(line)

            # Scan citations in this paragraph
            for m in self._citation_re.finditer(line):
                key = m.group(0)
                link = CitationLink(
                    source_section=current_section,
                    citation_key=key,
                    context_snippet=line[:120],
                    paragraph_index=para_idx,
                )
                citations.append(link)
                key_to_sources.setdefault(key, []).append(current_section)

            para_idx += 1

        # Save last section
        if current_paras:
            section_paragraphs[current_section] = current_paras

        return ChapterIndex(
            sections=sections,
            section_paragraphs=section_paragraphs,
            citations=citations,
            key_to_sources=key_to_sources,
        )

    # ------------------------------------------------------------------
    # Risk assessment
    # ------------------------------------------------------------------

    def assess_delete(
        self,
        index: ChapterIndex,
        *,
        section: str,
        paragraph_idx: int | None = None,
        html_snippet: str | None = None,
    ) -> EditRiskAssessment:
        """Assess risk of deleting content in a section."""
        issues: list[str] = []
        broken_keys: list[str] = []
        orphaned_refs: list[str] = []
        affected_chapters: list[str] = []
        mitigations: list[str] = []

        all_section_paras = index.section_paragraphs.get(section, [])

        # If no paragraph index, treat as whole-section deletion
        target_paras = (
            [all_section_paras[paragraph_idx]]
            if paragraph_idx is not None and 0 <= paragraph_idx < len(all_section_paras)
            else all_section_paras
        )

        # Collect citations in the target content
        keys_in_target: set[str] = set()
        for para in target_paras:
            for m in self._citation_re.finditer(para):
                keys_in_target.add(m.group(0))

        # Check: for each key in target, does it remain in the section after deletion?
        for key in keys_in_target:
            # Count occurrences in the whole section vs target
            total_in_section = sum(
                len(self._citation_re.findall(p)) for p in all_section_paras
            )
            in_target = sum(
                len(self._citation_re.findall(p)) for p in target_paras
            )
            remains_in_section = total_in_section > in_target

            # Also check if cited in other sections
            sources = index.key_to_sources.get(key, [])
            other_sections = {s for s in sources if s != section}

            if remains_in_section or other_sections:
                # Key survives elsewhere; no breakage
                continue

            # Only cited in this section, and all occurrences are in target → broken
            broken_keys.append(key)
            affected_chapters.append(section)
            issues.append(
                f"Citation {key} appears only in section '{section}' and all "
                "occurrences are within the deleted content. This will orphan the reference."
            )

        # Check: does the deleted content contain *definitions* or *first mentions*
        # of terms cited later? (Heuristic: if a term appears in this section
        # and is cited with [key] in later sections, flag it.)
        for later_section in index.sections:
            if later_section == section:
                continue
            later_paras = index.section_paragraphs.get(later_section, [])
            for para in later_paras:
                for key in keys_in_target:
                    if key in para:
                        # The same key appears in a later section
                        if key not in broken_keys:
                            broken_keys.append(key)
                        if later_section not in affected_chapters:
                            affected_chapters.append(later_section)
                        issues.append(
                            f"Citation {key} is cited in '{section}' but also referenced "
                            f"in later section '{later_section}'. Deletion may break continuity."
                        )

        # Determine risk level
        risk_level = "none"
        if len(broken_keys) >= 5 or len(affected_chapters) >= 3:
            risk_level = "critical"
        elif len(broken_keys) >= 3 or len(affected_chapters) >= 2:
            risk_level = "high"
        elif len(broken_keys) >= 1 or len(affected_chapters) >= 1:
            risk_level = "medium"

        can_proceed = risk_level not in ("high", "critical")

        if not can_proceed:
            mitigations.append(
                "Consider moving cited content to another section instead of deleting it."
            )
            mitigations.append(
                "Update or remove downstream citations before deleting upstream definitions."
            )

        return EditRiskAssessment(
            can_proceed=can_proceed,
            risk_level=risk_level,  # type: ignore[arg-type]
            issues=issues,
            broken_citation_keys=broken_keys,
            orphaned_references=orphaned_refs,
            affected_chapters=affected_chapters,
            suggested_mitigations=mitigations,
        )

    def assess_insert_citation(
        self,
        index: ChapterIndex,
        *,
        section: str,
        new_citation_keys: list[str],
    ) -> EditRiskAssessment:
        """Assess risk of inserting new citations."""
        issues: list[str] = []
        broken_keys: list[str] = []
        mitigations: list[str] = []

        for key in new_citation_keys:
            if key not in index.key_to_sources:
                issues.append(
                    f"New citation {key} is not referenced elsewhere. Ensure it has a "
                    "corresponding bibliographic entry."
                )
                broken_keys.append(key)

        risk_level = "low" if broken_keys else "none"
        return EditRiskAssessment(
            can_proceed=True,
            risk_level=risk_level,  # type: ignore[arg-type]
            issues=issues,
            broken_citation_keys=broken_keys,
            orphaned_references=[],
            affected_chapters=[section],
            suggested_mitigations=mitigations,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_html(raw: str) -> str:
        import re as _re

        text = _re.sub(r"<script[^>]*>[\s\S]*?</script>", "", raw, flags=_re.I)
        text = _re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=_re.I)
        text = _re.sub(r"<[^>]+>", "", text)
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        return text


class CrossChapterDeletionBlocked(Exception):
    """Raised when a cross-chapter deletion is blocked by the guard."""

    def __init__(self, assessment: EditRiskAssessment) -> None:
        self.assessment = assessment
        msg = (
            f"Cross-chapter deletion blocked ({assessment.risk_level}): "
            + "; ".join(assessment.issues)
        )
        super().__init__(msg)
