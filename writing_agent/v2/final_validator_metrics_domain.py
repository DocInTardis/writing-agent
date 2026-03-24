"""Text quality and reference metrics for final validator."""

from __future__ import annotations

import re


_SECTION_TOKEN_RE = re.compile(r"^H([23])::(.*)$")

from writing_agent.v2 import final_validator_reference_metrics_domain as reference_metrics_domain

_SENT_SPLIT_RE = re.compile(r"(?:[\u3002\uff01\uff1f!?]+|(?<=[A-Za-z0-9])[.]+)\s*")
_MIRROR_PATTERNS = [
    re.compile(r"^(?:\u5f15\u8a00|\u6458\u8981|\u7ed3\u8bba|\u672c\u8282|\u672c\u7ae0).{0,20}(?:\u805a\u7126|\u7528\u4e8e|\u65e8\u5728|\u5e94|\u9700|\u5efa\u8bae|\u53ef\u7b80\u8ff0|\u53ef\u4ece)", re.IGNORECASE),
    re.compile(r"^(?:\u6458\u8981|\u5f15\u8a00|\u7ed3\u8bba|\u76f8\u5173\u7814\u7a76|\u8ba8\u8bba|\u6570\u636e\u6765\u6e90\u4e0e\u68c0\u7d22\u7b56\u7565).{0,24}(?:\u4ea4\u4ee3|\u754c\u5b9a|\u8bf4\u660e|\u7ed9\u51fa|\u68b3\u7406|\u603b\u7ed3)", re.IGNORECASE),
    re.compile(r"(?:\u5e2e\u52a9\u8bfb\u8005\u7406\u89e3\u4e3a\u4ec0\u4e48\u8981\u505a|\u89e3\u91ca\u672c\u8282\u5e94\u5982\u4f55\u5199|\u5c55\u793a\u7814\u7a76\u8def\u5f84\u7684\u53ef\u590d\u73b0\u6027)", re.IGNORECASE),
]
_TEMPLATE_PADDING_PATTERNS = [
    re.compile(r"(?:引言先界定研究目标与对象，再说明核心问题的形成机制|摘要先界定研究目标与对象，再说明核心问题的形成机制)", re.IGNORECASE),
    re.compile(r"(?:引言给出方法路径、输入输出与关键参数设置，并解释各环节对研究结论的具体贡献|给出方法路径、输入输出与关键参数设置)", re.IGNORECASE),
    re.compile(r"(?:结论基于数据来源、评价指标与结果解释构建证据链，避免空泛表述并提升可核查性|基于数据来源、评价指标与结果解释构建证据链)", re.IGNORECASE),
    re.compile(r"(?:本段应阐明|围绕.+(?:展开|补充)|说明边界条件|构建评价指标体系)", re.IGNORECASE),
]

_LOW_INFORMATION_PATTERNS = [
    re.compile(r"(?:\u7efc\u4e0a\u6240\u8ff0|\u603b\u800c\u8a00\u4e4b|\u901a\u8fc7\u4e0a\u8ff0\u5206\u6790)\uff0c\u6211\u4eec\u53ef\u4ee5\u770b\u5230"),
    re.compile(r"\u672c\u7814\u7a76\u65e8\u5728\u901a\u8fc7.+\u6765\u8fbe\u5230.+(?:\u76ee\u6807|\u76ee\u7684)"),
    re.compile(r"\u7531\u4e8e.+\u7684\u539f\u56e0\uff0c\u56e0\u6b64.+"),
    re.compile(r"(?:\u9996\u5148|\u5176\u6b21|\u6700\u540e)[\uff0c,].{0,20}(?:\u8bf4\u660e|\u5206\u6790|\u9610\u8ff0|\u8ba8\u8bba|\u6307\u51fa)"),
    re.compile(r"(?:\u4e00|\u4e8c|\u4e09|\u56db|\u4e94)[\u3001\uff0c].{0,18}(?:\u8bf4\u660e|\u5206\u6790|\u9610\u8ff0|\u8ba8\u8bba|\u4f53\u73b0|\u53ef\u4ee5\u770b\u5230)"),
    re.compile(r"(?:\u76f8\u5173\u7684\u7814\u7a76\u5bf9\u8c61\u4e0e\u8fb9\u754c\u6761\u4ef6|\u53ef\u7b80\u8ff0\u7814\u7a76\u610f\u4e49\u3001\u76ee\u6807\u4e0e\u7ed3\u6784\u5b89\u6392|\u5f3a\u8c03\u672c\u6587\u89e3\u51b3\u7684\u6838\u5fc3\u95ee\u9898\u4e0e\u8fb9\u754c)"),
    re.compile(r"(?:\u7ed9\u51fa\u65b9\u6cd5\u6d41\u7a0b\u4e0e\u5173\u952e\u53c2\u6570\u8bbe\u7f6e|\u57fa\u4e8e\u53ef\u83b7\u5f97\u7684\u6570\u636e\u6765\u6e90\u6784\u5efa\u8bc4\u4ef7\u6307\u6807\u4f53\u7cfb|\u5bf9\u4e3b\u8981\u7ed3\u679c\u8fdb\u884c\u91cf\u5316\u89e3\u91ca\uff0c\u5e76\u8bf4\u660e\u53ef\u80fd\u7684\u8bef\u5dee\u6765\u6e90)"),
]

_PLACEHOLDER_PATTERNS = reference_metrics_domain._PLACEHOLDER_PATTERNS
_CLAIM_SIGNAL_RE = reference_metrics_domain._CLAIM_SIGNAL_RE
_NUMERIC_TOKEN_RE = reference_metrics_domain._NUMERIC_TOKEN_RE
_CLAIM_COMPARATIVE_RE = reference_metrics_domain._CLAIM_COMPARATIVE_RE
_SUPPORT_MARKER_RE = reference_metrics_domain._SUPPORT_MARKER_RE
_REFERENCE_HEADING_RE = reference_metrics_domain._REFERENCE_HEADING_RE
_REFERENCE_LINE_RE = reference_metrics_domain._REFERENCE_LINE_RE
_REFERENCE_YEAR_OR_LOCATOR_RE = reference_metrics_domain._REFERENCE_YEAR_OR_LOCATOR_RE
_REFERENCE_TOKEN_RE = reference_metrics_domain._REFERENCE_TOKEN_RE
_NON_CLAIM_CONFIGURATION_RE = reference_metrics_domain._NON_CLAIM_CONFIGURATION_RE
_INFORMATION_CONNECTOR_RE = reference_metrics_domain._INFORMATION_CONNECTOR_RE
_INFORMATIVE_TOKEN_RE = reference_metrics_domain._INFORMATIVE_TOKEN_RE
_GENERIC_INFO_TOKENS = reference_metrics_domain._GENERIC_INFO_TOKENS


def _body_without_reference_section(text: str) -> str:
    return reference_metrics_domain._body_without_reference_section(text)


def _extract_reference_section(text: str) -> str:
    return reference_metrics_domain._extract_reference_section(text)


def _extract_reference_lines(text: str) -> list[str]:
    return reference_metrics_domain._extract_reference_lines(text)


def _extract_reference_nonitem_lines(text: str) -> list[str]:
    return reference_metrics_domain._extract_reference_nonitem_lines(text)


def _normalize_reference_signature(text: str) -> str:
    return reference_metrics_domain._normalize_reference_signature(text)


def _reference_quality_metrics(text: str) -> dict[str, object]:
    return reference_metrics_domain._reference_quality_metrics(text)


def _unsupported_claim_metrics(text: str) -> tuple[float, list[str], int, int]:
    return reference_metrics_domain._unsupported_claim_metrics(text, collect_sentences_fn=_collect_sentences)

from writing_agent.v2 import (
    final_validator_density_metrics_domain as density_metrics_domain,
    final_validator_source_metrics_domain as source_metrics_domain,
    final_validator_structure_metrics_domain as structure_metrics_domain,
)


def _title_tokens(text: str) -> list[str]:
    return list(structure_metrics_domain._title_tokens(text))


def _title_body_alignment_score(title: str, body: str) -> float:
    return float(structure_metrics_domain._title_body_alignment_score(title, body))


def _normalize_sentence(text: str) -> str:
    return str(structure_metrics_domain._normalize_sentence(text))


def _strip_structured_blocks(text: str) -> str:
    return str(structure_metrics_domain._strip_structured_blocks(text))


def _normalize_expected_heading(section: object) -> str:
    return str(structure_metrics_domain._normalize_expected_heading(section))


def _collect_sentences(text: str) -> list[str]:
    return list(structure_metrics_domain._collect_sentences(text))


def _paragraphs(text: str) -> list[str]:
    return list(structure_metrics_domain._paragraphs(text))


def _repeat_sentence_ratio(text: str) -> float:
    return float(structure_metrics_domain._repeat_sentence_ratio(text))


def _sentence_opening_signature(text: str, *, prefix_chars: int = 10) -> str:
    return str(structure_metrics_domain._sentence_opening_signature(text, prefix_chars=prefix_chars))


def _formulaic_opening_ratio(text: str) -> tuple[float, list[str]]:
    ratio, hits = structure_metrics_domain._formulaic_opening_ratio(text)
    return float(ratio), list(hits)


def _source_text_fragments(source_rows: list[dict] | None) -> list[str]:
    return list(source_metrics_domain._source_text_fragments(source_rows))


def _char_shingles(text: str, *, size: int = 6) -> set[str]:
    return set(source_metrics_domain._char_shingles(text, size=size))


def _source_overlap_metrics(text: str, source_rows: list[dict] | None) -> tuple[float, list[str], int]:
    ratio, hits, sentence_count = source_metrics_domain._source_overlap_metrics(text, source_rows)
    return float(ratio), list(hits), int(sentence_count)


def _instruction_mirroring_ratio(text: str) -> float:
    return float(density_metrics_domain._instruction_mirroring_ratio(text))


def _template_padding_ratio(text: str) -> tuple[float, list[str]]:
    ratio, hits = density_metrics_domain._template_padding_ratio(text)
    return float(ratio), list(hits)


def _low_information_ratio(text: str) -> tuple[float, list[str]]:
    ratio, hits = density_metrics_domain._low_information_ratio(text)
    return float(ratio), list(hits)


def _placeholder_residue_ratio(text: str) -> tuple[float, list[str]]:
    ratio, hits = density_metrics_domain._placeholder_residue_ratio(text)
    return float(ratio), list(hits)


def _information_density_ratio(text: str) -> tuple[float, list[str], float]:
    ratio, hits, avg = density_metrics_domain._information_density_ratio(text)
    return float(ratio), list(hits), float(avg)


def _section_body_map(text: str) -> dict[str, list[str]]:
    return dict(structure_metrics_domain._section_body_map(text))


def _section_body_has_content(text: str) -> bool:
    return bool(structure_metrics_domain._section_body_has_content(text))


__all__ = [name for name in globals() if not name.startswith("__")]
