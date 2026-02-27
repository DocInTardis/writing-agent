"""Ai Rate module.

This module belongs to `writing_agent.quality` in the writing-agent codebase.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", flags=re.IGNORECASE)
_SENT_SPLIT_RE = re.compile(r"[。！？!?；;]+|\n{2,}")
_PUNCT_RE = re.compile(r"[。！？!?；;]")

# Common discourse markers often overused in templated model outputs.
_CONNECTORS = [
    "首先",
    "其次",
    "再次",
    "最后",
    "此外",
    "另外",
    "总之",
    "综上",
    "需要指出",
    "值得注意",
    "因此",
    "与此同时",
    "一方面",
    "另一方面",
    "在此基础上",
]


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _tokenize(text: str, *, max_chars: int = 260_000) -> list[str]:
    src = str(text or "")
    if len(src) > max_chars:
        src = src[:max_chars]
    return _TOKEN_RE.findall(src.lower())


def _split_sentences(text: str, *, max_chars: int = 260_000) -> list[str]:
    src = str(text or "")
    if len(src) > max_chars:
        src = src[:max_chars]
    parts = [x.strip() for x in _SENT_SPLIT_RE.split(src) if str(x or "").strip()]
    return parts


def _entropy_normalized(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    freq: dict[str, int] = {}
    for token in tokens:
        freq[token] = int(freq.get(token, 0)) + 1
    if len(freq) <= 1:
        return 0.0
    total = float(len(tokens))
    h = 0.0
    for count in freq.values():
        p = float(count) / total
        h -= p * math.log2(p)
    h_max = math.log2(float(len(freq)))
    if h_max <= 0:
        return 0.0
    return _clamp(h / h_max)


def _sentence_length_cv(sentences: list[str]) -> float:
    if not sentences:
        return 0.0
    lengths = [max(1, len(_TOKEN_RE.findall(sentence))) for sentence in sentences]
    if not lengths:
        return 0.0
    mean = sum(lengths) / len(lengths)
    if mean <= 0:
        return 0.0
    if len(lengths) == 1:
        return 0.0
    var = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    std = math.sqrt(max(var, 0.0))
    return float(std / mean)


def _repeated_ngram_ratio(tokens: list[str], n: int = 3) -> float:
    n = max(2, min(6, int(n)))
    if len(tokens) < n:
        return 0.0
    counts: dict[tuple[str, ...], int] = {}
    grams = 0
    for idx in range(0, len(tokens) - n + 1):
        gram = tuple(tokens[idx : idx + n])
        counts[gram] = int(counts.get(gram, 0)) + 1
        grams += 1
    if grams <= 0:
        return 0.0
    repeated = sum(max(0, c - 1) for c in counts.values())
    return float(repeated / grams)


def _dominant_punctuation_ratio(text: str) -> float:
    marks = _PUNCT_RE.findall(str(text or ""))
    if not marks:
        return 0.0
    freq: dict[str, int] = {}
    for mark in marks:
        freq[mark] = int(freq.get(mark, 0)) + 1
    top = max(freq.values()) if freq else 0
    return float(top / len(marks)) if marks else 0.0


def _connector_density_per_1k(text: str) -> float:
    src = str(text or "")
    if not src:
        return 0.0
    hits = 0
    for connector in _CONNECTORS:
        if not connector:
            continue
        hits += src.count(connector)
    return float(hits * 1000.0 / max(1, len(src)))


def _template_heading_density(text: str) -> float:
    lines = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    if not lines:
        return 0.0
    pattern = re.compile(r"^(#+\s+|\d+[.)、]\s*|[一二三四五六七八九十]+、)")
    hits = sum(1 for line in lines if pattern.search(line))
    return float(hits / len(lines))


@dataclass
class AiRateConfig:
    threshold: float = 0.65

    def normalized_threshold(self) -> float:
        return _clamp(float(self.threshold), 0.05, 0.95)


def estimate_ai_rate(
    text: str,
    *,
    threshold: float = 0.65,
) -> dict[str, Any]:
    src = str(text or "")
    tokens = _tokenize(src)
    sentences = _split_sentences(src)
    token_count = len(tokens)
    char_count = len(src.strip())
    sentence_count = len(sentences)
    threshold_norm = AiRateConfig(threshold=threshold).normalized_threshold()

    if token_count == 0 or char_count == 0:
        return {
            "ai_rate": 0.0,
            "ai_rate_percent": 0,
            "threshold": threshold_norm,
            "suspected_ai": False,
            "risk_level": "low",
            "confidence": 0.0,
            "signals": {
                "token_count": token_count,
                "char_count": char_count,
                "sentence_count": sentence_count,
                "sentence_burstiness_cv": 0.0,
                "lexical_diversity": 0.0,
                "repeated_3gram_ratio": 0.0,
                "connector_density_per_1k_chars": 0.0,
                "dominant_punctuation_ratio": 0.0,
                "token_entropy_norm": 0.0,
                "template_heading_density": 0.0,
            },
            "evidence": ["文本为空，无法评估。"],
            "note": "该结果仅为启发式估计，不能作为唯一判定依据。",
        }

    unique_tokens = len(set(tokens))
    lexical_diversity = float(unique_tokens / max(1, token_count))
    sentence_burstiness = _sentence_length_cv(sentences)
    repeated_ratio = _repeated_ngram_ratio(tokens, n=3)
    connector_density = _connector_density_per_1k(src)
    punct_dominant = _dominant_punctuation_ratio(src)
    entropy_norm = _entropy_normalized(tokens)
    template_density = _template_heading_density(src)

    # Higher score means more model-like signal.
    score_burst = _clamp((0.52 - sentence_burstiness) / 0.52)
    score_repeat = _clamp((repeated_ratio - 0.02) / 0.20)
    score_connector = _clamp((connector_density - 1.8) / 6.0)
    score_punct = _clamp((punct_dominant - 0.72) / 0.25)
    score_entropy = _clamp((0.82 - entropy_norm) / 0.30)
    score_lex = _clamp((0.38 - lexical_diversity) / 0.22)
    score_template = _clamp((template_density - 0.20) / 0.40)

    raw_score = (
        0.20 * score_burst
        + 0.20 * score_repeat
        + 0.16 * score_connector
        + 0.14 * score_punct
        + 0.15 * score_entropy
        + 0.10 * score_lex
        + 0.05 * score_template
    )
    raw_score = _clamp(raw_score)

    # Confidence grows with sample length; for short text keep estimate conservative
    # but avoid collapsing to a fixed 0.5 for moderately short passages.
    confidence = _clamp((token_count - 40) / 260)
    prior = 0.45
    ai_rate = _clamp(raw_score * confidence + prior * (1.0 - confidence))

    evidence: list[str] = []
    if score_repeat >= 0.6:
        evidence.append("重复 n-gram 比例偏高，存在模板化复用特征。")
    if score_burst >= 0.6:
        evidence.append("句长波动较低，节奏较均一。")
    if score_connector >= 0.6:
        evidence.append("连接词密度偏高，结构化过渡语较密集。")
    if score_punct >= 0.6:
        evidence.append("句末标点分布过于集中。")
    if score_entropy >= 0.6:
        evidence.append("词项熵偏低，词汇分布集中。")
    if score_lex >= 0.6:
        evidence.append("词汇多样性偏低。")
    if token_count < 120:
        evidence.append("文本较短，检测置信度有限。")
    if not evidence:
        evidence.append("未观察到显著的单项异常信号。")

    if ai_rate >= 0.78:
        risk_level = "high"
    elif ai_rate >= 0.58:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "ai_rate": round(ai_rate, 4),
        "ai_rate_percent": int(round(ai_rate * 100)),
        "threshold": round(threshold_norm, 4),
        "suspected_ai": bool(ai_rate >= threshold_norm),
        "risk_level": risk_level,
        "confidence": round(confidence, 4),
        "signals": {
            "token_count": token_count,
            "char_count": char_count,
            "sentence_count": sentence_count,
            "sentence_burstiness_cv": round(sentence_burstiness, 4),
            "lexical_diversity": round(lexical_diversity, 4),
            "repeated_3gram_ratio": round(repeated_ratio, 4),
            "connector_density_per_1k_chars": round(connector_density, 4),
            "dominant_punctuation_ratio": round(punct_dominant, 4),
            "token_entropy_norm": round(entropy_norm, 4),
            "template_heading_density": round(template_density, 4),
            "sub_scores": {
                "burstiness_low": round(score_burst, 4),
                "repetition_high": round(score_repeat, 4),
                "connector_high": round(score_connector, 4),
                "punctuation_uniform": round(score_punct, 4),
                "entropy_low": round(score_entropy, 4),
                "lexical_diversity_low": round(score_lex, 4),
                "template_density_high": round(score_template, 4),
            },
        },
        "evidence": evidence[:8],
        "note": "该结果仅为启发式估计，不能作为唯一判定依据。",
    }
