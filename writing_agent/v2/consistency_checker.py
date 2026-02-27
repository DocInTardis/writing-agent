"""Consistency Checker module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


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
    return issues
