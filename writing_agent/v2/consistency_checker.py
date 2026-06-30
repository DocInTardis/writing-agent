"""Consistency Checker module.

Checks document-level consistency including:
- Heading duplication and drift
- Terminology consistency
- Logic order contradictions
- Cross-chapter citation chain integrity
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from writing_agent.v2.cross_chapter_guard import CrossChapterImpactAnalyzer


@dataclass(frozen=True)
class ConsistencyIssue:
    kind: str
    detail: str


def self_check(text: str) -> list[ConsistencyIssue]:
    body = str(text or "")
    issues: list[ConsistencyIssue] = []
    if not body.strip():
        return [ConsistencyIssue(kind="empty", detail="text is empty")]

    # repeated heading drift
    headings = re.findall(r"(?m)^#{1,3}\s+(.+)$", body)
    lowered = [h.strip().lower() for h in headings if h.strip()]
    if len(lowered) != len(set(lowered)):
        issues.append(ConsistencyIssue(kind="heading_repeat", detail="duplicate headings detected"))

    # crude terminology drift check
    terms = ["模型", "系统", "策略", "评测"]
    for term in terms:
        count = body.count(term)
        if count == 1:
            issues.append(ConsistencyIssue(kind="term_drift", detail=f"term '{term}' appears only once"))

    # contradiction marker
    if "但是" in body and "因此" in body and body.find("但是") > body.find("因此"):
        issues.append(ConsistencyIssue(kind="logic_order", detail="possible logic contradiction order"))

    # cross-chapter citation chain check
    issues.extend(_check_cross_chapter_citations(body))

    return issues


def _check_cross_chapter_citations(body: str) -> list[ConsistencyIssue]:
    """Check for orphaned citations and broken reference chains."""
    issues: list[ConsistencyIssue] = []
    analyzer = CrossChapterImpactAnalyzer()
    try:
        index = analyzer.index_document(body)
    except Exception:
        return issues

    # Find citation keys that appear only once
    for key, sources in index.key_to_sources.items():
        if len(sources) == 1:
            issues.append(
                ConsistencyIssue(
                    kind="orphaned_citation",
                    detail=f"Citation {key} appears only in section '{sources[0]}'; "
                           "if that section is edited, the reference may become orphaned.",
                )
            )

    # Find citation keys cited in sections but never defined/referenced elsewhere
    all_keys = set(index.key_to_sources.keys())
    for section in index.sections:
        paras = index.section_paragraphs.get(section, [])
        for para in paras:
            for m in analyzer._citation_re.finditer(para):
                key = m.group(0)
                if key not in all_keys:
                    issues.append(
                        ConsistencyIssue(
                            kind="undefined_citation",
                            detail=f"Citation {key} in section '{section}' does not appear "
                                   "in any other section; may be a dangling reference.",
                        )
                    )

    return issues
