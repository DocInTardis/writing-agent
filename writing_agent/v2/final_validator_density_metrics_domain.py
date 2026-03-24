"""Density and template-style metrics extracted from final_validator_metrics_domain."""

from __future__ import annotations

import re


def _base():
    from writing_agent.v2 import final_validator_metrics_domain as base

    return base


def _paragraphs(text: str) -> list[str]:
    return list(_base()._paragraphs(text))


def _instruction_mirroring_ratio(text: str) -> float:
    paras = _paragraphs(text)
    if not paras:
        return 0.0
    patterns = _base()._MIRROR_PATTERNS
    hits = 0
    for para in paras:
        token = str(para or "").strip()
        if not token:
            continue
        if any(pattern.search(token) for pattern in patterns):
            hits += 1
    return float(hits) / float(max(1, len(paras)))


def _template_padding_ratio(text: str) -> tuple[float, list[str]]:
    paras = _paragraphs(text)
    if not paras:
        return 0.0, []
    patterns = _base()._TEMPLATE_PADDING_PATTERNS
    hit_count = 0
    hit_fragments: list[str] = []
    for para in paras:
        token = str(para or "").strip()
        if not token:
            continue
        if any(pattern.search(token) for pattern in patterns):
            hit_count += 1
            if len(hit_fragments) < 8:
                hit_fragments.append(token[:200])
    return float(hit_count) / float(max(1, len(paras))), hit_fragments


def _low_information_ratio(text: str) -> tuple[float, list[str]]:
    paras = _paragraphs(text)
    if not paras:
        return 0.0, []
    patterns = _base()._LOW_INFORMATION_PATTERNS
    hit_count = 0
    hit_fragments: list[str] = []
    for para in paras:
        token = str(para or "").strip()
        if not token:
            continue
        if any(pattern.search(token) for pattern in patterns):
            hit_count += 1
            if len(hit_fragments) < 8:
                hit_fragments.append(token[:200])
    return float(hit_count) / float(max(1, len(paras))), hit_fragments


def _placeholder_residue_ratio(text: str) -> tuple[float, list[str]]:
    paras = _paragraphs(text)
    if not paras:
        return 0.0, []
    patterns = _base()._PLACEHOLDER_PATTERNS
    hit_count = 0
    hit_fragments: list[str] = []
    for para in paras:
        token = str(para or "").strip()
        if not token:
            continue
        if any(pattern.search(token) for pattern in patterns):
            hit_count += 1
            if len(hit_fragments) < 8:
                hit_fragments.append(token[:200])
    return float(hit_count) / float(max(1, len(paras))), hit_fragments


def _information_density_ratio(text: str) -> tuple[float, list[str], float]:
    paras = _paragraphs(text)
    if not paras:
        return 0.0, [], 0.0
    base = _base()
    info_token_re = base._INFORMATIVE_TOKEN_RE
    generic_tokens = base._GENERIC_INFO_TOKENS
    connector_re = base._INFORMATION_CONNECTOR_RE
    low_info_patterns = base._LOW_INFORMATION_PATTERNS
    low_density = 0
    hit_fragments: list[str] = []
    density_values: list[float] = []
    for para in paras:
        token = str(para or "").strip()
        if not token:
            continue
        raw_tokens = [str(x).strip() for x in info_token_re.findall(token) if str(x).strip()]
        informative = []
        generic_count = 0
        for item in raw_tokens:
            low = item.lower()
            if low in generic_tokens:
                generic_count += 1
                continue
            informative.append(item)
        unique_count = len({x.lower() for x in informative})
        citation_hits = len(re.findall(r"\[\d+\]", token))
        numeric_hits = len(re.findall(r"\d+(?:\.\d+)?%?", token))
        connector_hits = len(connector_re.findall(token))
        density = float(unique_count + citation_hits + min(3, numeric_hits)) / float(max(1, len(token)))
        density_values.append(density)
        is_low_density = bool(
            len(token) >= 40
            and (
                (density < 0.045 and unique_count < 6)
                or (connector_hits >= 2 and unique_count < 5)
                or (unique_count < 4 and citation_hits == 0 and numeric_hits == 0)
                or (generic_count >= max(4, unique_count * 2) and citation_hits == 0 and numeric_hits == 0)
                or (citation_hits == 0 and numeric_hits == 0 and connector_hits >= 1 and any(pattern.search(token) for pattern in low_info_patterns))
            )
        )
        if is_low_density:
            low_density += 1
            if len(hit_fragments) < 8:
                hit_fragments.append(token[:200])
    avg_density = (sum(density_values) / len(density_values)) if density_values else 0.0
    return float(low_density) / float(max(1, len(paras))), hit_fragments, avg_density


__all__ = [name for name in globals() if not name.startswith("__")]
