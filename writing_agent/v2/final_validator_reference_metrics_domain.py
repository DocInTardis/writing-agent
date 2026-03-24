"""Reference and supported-claim metrics for final validator."""

from __future__ import annotations

import os
import re


_PLACEHOLDER_PATTERNS = [
    re.compile(r"(?:实验项|步骤一|步骤二|步骤三|序号占位符|占位符|待补充|placeholder|tbd|todo)", re.IGNORECASE),
    re.compile(r"\[\d+\]\s*[?;]\s*[一-鿿A-Za-z]"),
]

_INFORMATION_CONNECTOR_RE = re.compile(
    r"(?:因此|所以|首先|其次|最后|综上所述|总而言之|通过上述分析|进一步|此外|同时|在此基础上)",
    re.IGNORECASE,
)

_INFORMATIVE_TOKEN_RE = re.compile(r"\[\d+\]|[A-Za-z]{2,}(?:-[A-Za-z0-9]+)?|\d+(?:\.\d+)?%?|[一-鿿]{2,}")
_GENERIC_INFO_TOKENS = {
    "研究",
    "分析",
    "问题",
    "内容",
    "部分",
    "方面",
    "结果",
    "结论",
    "方法",
    "路径",
    "机制",
    "作用",
    "进行",
    "提出",
    "说明",
    "讨论",
    "影响",
    "提升",
    "优化",
    "现状",
    "相关",
    "目标",
    "意义",
}

_CLAIM_SIGNAL_RE = re.compile(
    r"(?:结果表明|研究发现|实验表明|数据显示|验证了|证明了|可见|回归测试显示|在线回归测试显示|\bshows? that\b|\bresults? show\b|\bfindings? show\b|\bdemonstrates?\b|\bvalidated?\b|\bproved?\b)",
    re.IGNORECASE,
)
_NUMERIC_TOKEN_RE = re.compile(r"(?:\d{1,3}(?:\.\d+)?\s*%|\d+(?:\.\d+)?)", re.IGNORECASE)
_CLAIM_COMPARATIVE_RE = re.compile(
    r"(?:提高|提升|提高了|提升了|降低|减少|增长|下降|下降了|降至|达到|超过|优于|显著|improv(?:e|ed|es)|reduc(?:e|ed|es)|increase(?:d|s)?|decrease(?:d|s)?|outperform(?:ed|s)?|significant(?:ly)?)",
    re.IGNORECASE,
)
_SUPPORT_MARKER_RE = re.compile(r"(?:\[\d+\]|见表\d+|见图\d+|表\d+|图\d+|TABLE\s*\d+|FIGURE\s*\d+)", re.IGNORECASE)
_REFERENCE_HEADING_RE = re.compile(r"(?m)^##\s*(?:\u53c2\u8003\u6587\u732e|References?)\s*$", re.IGNORECASE)
_REFERENCE_LINE_RE = re.compile(r"^\s*\[(\d+)\]\s+(.+?)\s*$")
_REFERENCE_YEAR_OR_LOCATOR_RE = re.compile(r"(?:\b(?:19|20)\d{2}\b|doi[:\s]|https?://)", re.IGNORECASE)
_REFERENCE_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{2,}|\d+")


_NON_CLAIM_CONFIGURATION_RE = re.compile(r"(?:\u7c92\u5ea6|\u533a\u95f4|\u8303\u56f4|\u53c2\u6570|top[_ -]?k|token|\u4e0a\u4e0b\u6587|\u7a97\u53e3|\u6279\u5927\u5c0f|\u9636\u6bb5|\u65f6\u95f4\u7a97\u53e3)", re.IGNORECASE)


def _body_without_reference_section(text: str) -> str:
    body = str(text or "")
    match = _REFERENCE_HEADING_RE.search(body)
    if not match:
        return body
    return body[: match.start()].rstrip()


def _extract_reference_section(text: str) -> str:
    body = str(text or "")
    match = _REFERENCE_HEADING_RE.search(body)
    if not match:
        return ""
    return body[match.end() :].strip()


def _extract_reference_lines(text: str) -> list[str]:
    section = _extract_reference_section(text)
    if not section:
        return []
    out: list[str] = []
    for raw in section.splitlines():
        line = str(raw or "").strip()
        if not line:
            continue
        if _REFERENCE_LINE_RE.match(line):
            out.append(line)
    return out



def _extract_reference_nonitem_lines(text: str) -> list[str]:
    section = _extract_reference_section(text)
    if not section:
        return []
    out: list[str] = []
    for raw in section.splitlines():
        line = str(raw or "").strip()
        if not line:
            continue
        if _REFERENCE_LINE_RE.match(line):
            continue
        out.append(line)
    return out


def _normalize_reference_signature(text: str) -> str:
    token = re.sub(r"^\s*\[\d+\]\s+", "", str(text or "").strip())
    token = token.lower()
    token = re.sub(r"doi[:\s]*", " ", token, flags=re.IGNORECASE)
    token = re.sub(r"https?://\S+", " ", token, flags=re.IGNORECASE)
    token = re.sub(r"\s+", " ", token)
    token = re.sub(r"[^0-9a-z一-鿿]+", "", token)
    return token


def _reference_quality_metrics(text: str) -> dict[str, object]:
    try:
        max_weak_ratio = max(0.0, min(1.0, float(os.environ.get("WRITING_AGENT_REFERENCE_MAX_WEAK_RATIO", "0.0"))))
    except Exception:
        max_weak_ratio = 0.0

    section = _extract_reference_section(text)
    lines = _extract_reference_lines(text)
    nonitem_lines = _extract_reference_nonitem_lines(text)
    if not lines:
        issues: list[str] = []
        weak_items: list[dict[str, object]] = []
        if section:
            issues.append("reference_items_missing_or_unformatted")
            weak_items.append({"number": 0, "line": section[:200], "issues": ["reference_items_missing_or_unformatted"]})
            return {
                "count": 0,
                "sequence_passed": False,
                "quality_passed": False,
                "weak_ratio": 1.0,
                "max_weak_ratio": max_weak_ratio,
                "weak_items": weak_items,
                "weak_item_count": 1,
                "duplicate_items": [],
                "duplicate_item_count": 0,
                "unformatted_items": [
                    {"line": str(row or "")[:200], "issues": ["reference_unformatted_line"]}
                    for row in nonitem_lines[:8]
                ],
                "unformatted_item_count": len(nonitem_lines),
                "issues": issues,
            }
        return {
            "count": 0,
            "sequence_passed": True,
            "quality_passed": True,
            "weak_ratio": 0.0,
            "max_weak_ratio": max_weak_ratio,
            "weak_items": [],
            "weak_item_count": 0,
            "duplicate_items": [],
            "duplicate_item_count": 0,
            "unformatted_items": [],
            "unformatted_item_count": 0,
            "issues": [],
        }

    numbers: list[int] = []
    weak_item_count = 0
    duplicate_item_count = 0
    unformatted_item_count = len(nonitem_lines)
    weak_items: list[dict[str, object]] = []
    duplicate_items: list[dict[str, object]] = []
    unformatted_items: list[dict[str, object]] = [
        {"line": str(row or "")[:200], "issues": ["reference_unformatted_line"]}
        for row in nonitem_lines[:8]
    ]
    signature_first_seen: dict[str, dict[str, object]] = {}

    for line in lines:
        match = _REFERENCE_LINE_RE.match(line)
        if not match:
            continue
        number = int(match.group(1) or 0)
        content = str(match.group(2) or "").strip()
        numbers.append(number)

        weak_reasons: list[str] = []
        if any(pattern.search(content) for pattern in _PLACEHOLDER_PATTERNS):
            weak_reasons.append("placeholder_residue")
        compact = re.sub(r"\s+", "", content)
        if len(compact) < 10:
            weak_reasons.append("too_short")
        if len(_REFERENCE_TOKEN_RE.findall(content)) < 2:
            weak_reasons.append("low_information")
        if not _REFERENCE_YEAR_OR_LOCATOR_RE.search(content):
            weak_reasons.append("missing_year_or_locator")
        if weak_reasons:
            weak_item_count += 1
            if len(weak_items) < 8:
                weak_items.append({"number": number, "line": line[:200], "issues": weak_reasons})

        signature = _normalize_reference_signature(content)
        if signature:
            first_seen = signature_first_seen.get(signature)
            if first_seen is not None:
                duplicate_item_count += 1
                if len(duplicate_items) < 8:
                    duplicate_items.append(
                        {
                            "number": number,
                            "line": line[:200],
                            "duplicate_of": int(first_seen.get("number") or 0),
                        }
                    )
            else:
                signature_first_seen[signature] = {"number": number, "line": line}

    expected_numbers = list(range(1, len(lines) + 1))
    sequence_passed = numbers == expected_numbers
    issues: list[str] = []
    if not sequence_passed:
        issues.append("reference_sequence_broken")
    if duplicate_item_count > 0:
        issues.append("reference_duplicates_detected")
    if unformatted_item_count > 0:
        issues.append("reference_unformatted_lines_detected")
    weak_ratio = float(weak_item_count) / float(max(1, len(lines)))
    if weak_ratio > max_weak_ratio:
        issues.append("reference_weak_items_exceeded")
    quality_passed = bool(
        sequence_passed
        and duplicate_item_count == 0
        and unformatted_item_count == 0
        and weak_ratio <= max_weak_ratio
    )
    return {
        "count": len(lines),
        "sequence_passed": sequence_passed,
        "quality_passed": quality_passed,
        "weak_ratio": weak_ratio,
        "max_weak_ratio": max_weak_ratio,
        "weak_items": weak_items,
        "weak_item_count": weak_item_count,
        "duplicate_items": duplicate_items,
        "duplicate_item_count": duplicate_item_count,
        "unformatted_items": unformatted_items,
        "unformatted_item_count": unformatted_item_count,
        "issues": issues,
    }


def _unsupported_claim_metrics(text: str, *, collect_sentences_fn) -> tuple[float, list[str], int, int]:
    body = _body_without_reference_section(text)
    sentences = collect_sentences_fn(body)
    if not sentences:
        return 0.0, [], 0, 0

    claim_total = 0
    unsupported_total = 0
    unsupported_numeric = 0
    hits: list[str] = []
    for sentence in sentences:
        token = str(sentence or "").strip()
        if len(token) < 8:
            continue
        numeric_claim = bool(_NUMERIC_TOKEN_RE.search(token) and _CLAIM_COMPARATIVE_RE.search(token))
        claim_like = numeric_claim or bool(_CLAIM_SIGNAL_RE.search(token))
        if not claim_like:
            continue
        if numeric_claim and _NON_CLAIM_CONFIGURATION_RE.search(token):
            continue
        claim_total += 1
        if _SUPPORT_MARKER_RE.search(token):
            continue
        unsupported_total += 1
        if numeric_claim:
            unsupported_numeric += 1
        if len(hits) < 8:
            hits.append(token[:120])
    if claim_total <= 0:
        return 0.0, [], 0, 0
    return float(unsupported_total) / float(claim_total), hits, claim_total, unsupported_numeric





__all__ = [name for name in globals() if not name.startswith("__")]
