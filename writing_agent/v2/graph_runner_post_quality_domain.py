"""Quality and residue checks extracted from graph_runner_post_domain."""

from __future__ import annotations

import os
import re

from writing_agent.v2 import graph_reference_domain, graph_text_sanitize_domain


def _base():
    from writing_agent.v2 import graph_runner_post_domain as base

    return base


_PROMPT_CONTAMINATION_PATTERNS: tuple[str, ...] = (
    r"(?mi)^\s*(?:topic|doc_type|audience|style|keywords?|key\s*points?)\s*:",
    "\u5e94\u7ed9\u51fa.*\u9a8c\u6536\u89c4\u5219",
    r"(?:\u672c\u8282|\u672c\u6bb5|\u672c\u7ae0).{0,16}(?:\u5e94|\u9700|\u5efa\u8bae|\u8bf7).{0,24}(?:\u9a8c\u6536|\u8fb9\u754c|\u7ea6\u675f|\u53ef\u590d\u6838|\u53ef\u590d\u73b0)",
    r"(?:\u56f4\u7ed5|\u9488\u5bf9).{0,24}(?:\u5e94\u8bf4\u660e|\u9700\u4ea4\u4ee3|\u8865\u5145).{0,40}(?:\u9a8c\u6536\u6807\u51c6|\u53ef\u590d\u6838|\u53ef\u590d\u73b0|\u65b9\u6cd5\u8def\u5f84|\u8f93\u5165\u8f93\u51fa|\u5173\u952e\u53c2\u6570|\u6837\u672c\u8fb9\u754c|\u53d8\u91cf(?:\u5b9a\u4e49|\u63a7\u5236)|\u8bba\u8bc1\u8def\u5f84|\u8bc1\u636e\u652f\u6491)",
    r"(?:\u6b64\u5916|\u540c\u65f6|\u8fdb\u4e00\u6b65).{0,8}(?:\u56f4\u7ed5|\u8865\u5145).{0,48}(?:\u672c\u8282|\u672c\u7ae0|\u6838\u5fc3\u95ee\u9898|\u5173\u952e\u95ee\u9898|\u8bba\u8bc1\u8def\u5f84|\u8bc1\u636e\u652f\u6491)",
    r"(?:\u56f4\u7ed5|around).{0,8}[\"'\u201c\u2018\u300a\u300c].+[\"'\u201d\u2019\u300b\u300d](?:\uff0c|,)?(?:\u8fdb\u4e00\u6b65)?(?:\u8865\u5145|\u5c55\u5f00)",
    "\u8865\u5145\u8bf4\u660e\uff1a\u672c\u7814\u7a76\u8fdb\u4e00\u6b65\u660e\u786e\u4e86\u65b9\u6cd5\u8fb9\u754c\u3001\u590d\u73b0\u6761\u4ef6\u4e0e\u5e94\u7528\u573a\u666f",
    "\u9644\u5f55\uff1a\u76f8\u5173\u6587\u732e\u5217\u8868",
    r"(?:\u6458\u8981|\u5f15\u8a00|\u5173\u952e\u8bcd|\u672c\u8282).{0,20}(?:\u5e94\u5f53|\u5e94\u8986\u76d6|\u5148\u754c\u5b9a|\u8865\u5145|\u805a\u7126\u4ea4\u4ee3)",
    r"(?:\u5b9e\u9a8c\u9879|\u5e8f\u53f7\u5360\u4f4d\u7b26|\u6b65\u9aa4[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\d]+)\s*[:\uff1a]",
    r"(?i)based on the available sources",
    r"(?i)the sources listed are",
    r"(?i)experiment\s*item\s*:",
)


_GENERIC_FIGURE_CAPTION_RE = re.compile(
    r'\[\[FIGURE:\{[^\]]*"caption"\s*:\s*"(?:\u65b9\u6cd5\u6d41\u7a0b\u56fe|\u5173\u952e\u6d41\u7a0b\u793a\u610f\u56fe)"',
    flags=re.IGNORECASE,
)


def _extract_h2_titles(text: str) -> list[str]:
    base = _base()
    out: list[str] = []
    for line in (text or "").splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if not match:
            continue
        title = base._clean_section_title(match.group(1))
        if title:
            out.append(title)
    return out


def _count_citations(text: str) -> int:
    return len(re.findall(r"\[\d+\]", text or ""))


def _detect_prompt_contamination(text: str) -> list[str]:
    src = str(text or "")
    if not src:
        return []
    hits: list[str] = []
    for pattern in _PROMPT_CONTAMINATION_PATTERNS:
        match = re.search(pattern, src, flags=re.IGNORECASE)
        if not match:
            continue
        snippet = re.sub(r"\s+", " ", str(match.group(0) or "")).strip()
        hits.append(snippet[:120] if snippet else pattern)
    return hits


def _looks_like_structured_marker_fragment(token: str) -> bool:
    txt = str(token or "").strip()
    if not txt:
        return False
    if txt.startswith("[[TABLE:") or txt.startswith("[[FIGURE:"):
        return True
    if txt.startswith(",") and '"caption"' in txt and "}]]" in txt:
        return True
    jsonish_keys = ('"caption"', '"columns"', '"rows"', '"type"', '"data"')
    if any(key in txt for key in jsonish_keys) and ("}]]" in txt or txt.endswith("}")):
        stripped = re.sub(r'[\s\[\]\{\}\(\)",:]', "", txt)
        if len(stripped) <= max(32, len(txt) // 3):
            return True
    return False


def _detect_paragraph_repetition(text: str) -> int:
    counts: dict[str, int] = {}
    for para in re.split(r"\n\s*\n+", str(text or "")):
        token = re.sub(r"\s+", " ", str(para or "")).strip()
        if not token:
            continue
        if token.startswith("#"):
            continue
        if _looks_like_structured_marker_fragment(token):
            continue
        if graph_text_sanitize_domain._looks_like_process_line(token):
            continue
        if re.match(r"^\[\d+\]\s+", token):
            continue
        if len(token) < 12:
            continue
        counts[token] = int(counts.get(token, 0)) + 1
    return max(counts.values()) if counts else 0


def _reference_relevance_ratio(*, query: str, sources: list[dict]) -> float:
    q = str(query or "").strip()
    rows = [s for s in (sources or []) if isinstance(s, dict)]
    if not q or not rows:
        return 1.0
    matched = 0
    total = 0
    for row in rows:
        score = graph_reference_domain.source_relevance_score(query=q, source=row)
        total += 1
        if score >= 1:
            matched += 1
    return float(matched) / float(total) if total > 0 else 1.0


def _reference_rows_from_text(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in (text or "").splitlines():
        token = str(line or "").strip()
        match = re.match(r"^\[(\d+)\]\s+(.+)$", token)
        if not match:
            continue
        title = str(match.group(2) or "").strip()
        if title:
            rows.append({"title": title})
    return rows


def _reference_relevance_ratio_from_text(*, query: str, text: str) -> tuple[float, int]:
    q = str(query or "").strip()
    if not q:
        return 1.0, 0
    rows = _reference_rows_from_text(text)
    if not rows:
        return 1.0, 0
    return _reference_relevance_ratio(query=q, sources=rows), len(rows)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return float(default)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return int(default)


def _light_self_check(
    *,
    text: str,
    sections: list[str],
    target_chars: int,
    evidence_enabled: bool,
    reference_sources: list[dict],
    reference_query: str = "",
) -> list[str]:
    base = _base()
    problems: list[str] = []
    body_len = base._doc_body_len(text)
    if target_chars > 0:
        lower = int(target_chars * 0.9)
        upper = int(target_chars * 1.1)
        if body_len < lower or body_len > upper:
            problems.append(f"target_chars_mismatch:{body_len}/{target_chars}")
    if sections:
        expected = [base._clean_section_title(base._section_title(s) or s) for s in sections]
        got = set(_extract_h2_titles(text))
        missing = [s for s in expected if s and s not in got]
        if missing:
            problems.append("missing_sections:" + ",".join(missing[:6]))
    if evidence_enabled:
        if not reference_sources:
            problems.append("missing_reference_sources")
        else:
            cites = _count_citations(text)
            if cites == 0:
                problems.append("missing_citations")
    contamination = _detect_prompt_contamination(text)
    if contamination:
        problems.append(f"prompt_contamination:{len(contamination)}")
    generic_fig_hits = len(_GENERIC_FIGURE_CAPTION_RE.findall(text or ""))
    if generic_fig_hits >= 6:
        problems.append("figure_repetition_generic")
    repeated_para = _detect_paragraph_repetition(text)
    if repeated_para >= 3:
        problems.append(f"paragraph_repetition:{repeated_para}")
    top_heading = ""
    match_h1 = re.search(r"(?m)^#\s+(.+?)\s*$", text or "")
    if match_h1:
        top_heading = base._clean_section_title(match_h1.group(1))
    if top_heading and base._is_reference_section(top_heading):
        problems.append("title_is_reference")
    if evidence_enabled and reference_sources:
        ratio = _reference_relevance_ratio(query=reference_query, sources=reference_sources)
        min_ratio = _float_env("WRITING_AGENT_REFERENCE_MIN_RELEVANCE_RATIO", 0.35)
        if ratio < min_ratio:
            problems.append(f"reference_topic_mismatch:{ratio:.2f}")
    if reference_query:
        ratio_text, ref_row_count = _reference_relevance_ratio_from_text(query=reference_query, text=text)
        min_ratio = _float_env("WRITING_AGENT_REFERENCE_MIN_RELEVANCE_RATIO", 0.35)
        min_rows = max(4, _int_env("WRITING_AGENT_REFERENCE_TEXT_MIN_ROWS", 8))
        if ref_row_count >= min_rows and ratio_text < min_ratio:
            problems.append(f"reference_text_topic_mismatch:{ratio_text:.2f}")
    return problems


__all__ = [name for name in globals() if not name.startswith("__")]
