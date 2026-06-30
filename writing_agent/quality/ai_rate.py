"""Ai Rate module.

This module belongs to `writing_agent.quality` in the writing-agent codebase.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", flags=re.IGNORECASE)
_SENT_SPLIT_RE = re.compile(r"[。！？!?]+|\n{2,}")
_PUNCT_RE = re.compile(r"[。！？!?]")

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
    return [item.strip() for item in _SENT_SPLIT_RE.split(src) if str(item or "").strip()]


def _entropy_normalized(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    freq: dict[str, int] = {}
    for token in tokens:
        freq[token] = int(freq.get(token, 0)) + 1
    if len(freq) <= 1:
        return 0.0
    total = float(len(tokens))
    entropy = 0.0
    for count in freq.values():
        p = float(count) / total
        entropy -= p * math.log2(p)
    max_entropy = math.log2(float(len(freq)))
    if max_entropy <= 0:
        return 0.0
    return _clamp(entropy / max_entropy)


def _sentence_length_cv(sentences: list[str]) -> float:
    if not sentences:
        return 0.0
    lengths = [max(1, len(_TOKEN_RE.findall(sentence))) for sentence in sentences]
    if len(lengths) <= 1:
        return 0.0
    mean = sum(lengths) / len(lengths)
    if mean <= 0:
        return 0.0
    variance = sum((value - mean) ** 2 for value in lengths) / len(lengths)
    return float(math.sqrt(max(variance, 0.0)) / mean)


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
    repeated = sum(max(0, count - 1) for count in counts.values())
    return float(repeated / grams)


def _dominant_punctuation_ratio(text: str) -> float:
    marks = _PUNCT_RE.findall(str(text or ""))
    if not marks:
        return 0.0
    freq: dict[str, int] = {}
    for mark in marks:
        freq[mark] = int(freq.get(mark, 0)) + 1
    return float(max(freq.values()) / len(marks)) if freq else 0.0


def _connector_density_per_1k(text: str) -> float:
    src = str(text or "")
    if not src:
        return 0.0
    hits = 0
    for connector in _CONNECTORS:
        hits += src.count(connector)
    return float(hits * 1000.0 / max(1, len(src)))


def _template_heading_density(text: str) -> float:
    lines = [item.strip() for item in str(text or "").splitlines() if item.strip()]
    if not lines:
        return 0.0
    pattern = re.compile(r"^(#+\s+|\d+[.)、]\s*|[一二三四五六七八九十]+、)")
    hits = sum(1 for line in lines if pattern.search(line))
    return float(hits / len(lines))


@dataclass
class AiRateConfig:
    threshold: float = 0.65
    prior: float = 0.45
    confidence_start_tokens: int = 40
    confidence_full_tokens: int = 300

    def normalized_threshold(self) -> float:
        return _clamp(float(self.threshold), 0.05, 0.95)

    def normalized_prior(self) -> float:
        return _clamp(float(self.prior), 0.0, 1.0)

    def normalized_confidence_start_tokens(self) -> int:
        return max(0, int(self.confidence_start_tokens))

    def normalized_confidence_full_tokens(self) -> int:
        return max(self.normalized_confidence_start_tokens() + 1, int(self.confidence_full_tokens))


@dataclass
class AiRateWeights:
    burstiness_low: float = 0.20
    repetition_high: float = 0.20
    connector_high: float = 0.16
    punctuation_uniform: float = 0.14
    entropy_low: float = 0.15
    lexical_diversity_low: float = 0.10
    template_density_high: float = 0.05

    def normalized(self) -> "AiRateWeights":
        raw = [
            max(0.0, float(self.burstiness_low)),
            max(0.0, float(self.repetition_high)),
            max(0.0, float(self.connector_high)),
            max(0.0, float(self.punctuation_uniform)),
            max(0.0, float(self.entropy_low)),
            max(0.0, float(self.lexical_diversity_low)),
            max(0.0, float(self.template_density_high)),
        ]
        total = sum(raw)
        if total <= 0:
            return AiRateWeights()
        return AiRateWeights(
            burstiness_low=raw[0] / total,
            repetition_high=raw[1] / total,
            connector_high=raw[2] / total,
            punctuation_uniform=raw[3] / total,
            entropy_low=raw[4] / total,
            lexical_diversity_low=raw[5] / total,
            template_density_high=raw[6] / total,
        )

    def as_dict(self) -> dict[str, float]:
        normalized = self.normalized()
        return {
            "burstiness_low": round(normalized.burstiness_low, 6),
            "repetition_high": round(normalized.repetition_high, 6),
            "connector_high": round(normalized.connector_high, 6),
            "punctuation_uniform": round(normalized.punctuation_uniform, 6),
            "entropy_low": round(normalized.entropy_low, 6),
            "lexical_diversity_low": round(normalized.lexical_diversity_low, 6),
            "template_density_high": round(normalized.template_density_high, 6),
        }


def _build_improvement_actions(
    *,
    score_burst: float,
    score_repeat: float,
    score_connector: float,
    score_punct: float,
    score_entropy: float,
    score_lex: float,
    score_template: float,
    confidence: float,
) -> list[str]:
    actions: list[str] = []
    if score_repeat >= 0.45:
        actions.append("rewrite repeated sentence openings and repeated 3-gram fragments")
    if max(score_connector, score_template) >= 0.45:
        actions.append("reduce stacked connectors and replace template transitions with concrete claims")
    if max(score_entropy, score_lex) >= 0.45:
        actions.append("add concrete entities, variables, time ranges, outcomes, and limits")
    if max(score_burst, score_punct) >= 0.45:
        actions.append("mix shorter and longer sentences instead of keeping a uniform rhythm")
    if confidence < 0.45:
        actions.append("expand the valid prose body before interpreting the estimate")
    if not actions:
        actions.append("keep concrete reasoning, verified citations, and human review in the loop")
    return actions[:5]


def estimate_ai_rate(
    text: str,
    *,
    threshold: float = 0.65,
    config: AiRateConfig | None = None,
    weights: AiRateWeights | None = None,
) -> dict[str, Any]:
    src = str(text or "")
    effective_config = config or AiRateConfig(threshold=threshold)
    effective_weights = (weights or AiRateWeights()).normalized()
    tokens = _tokenize(src)
    sentences = _split_sentences(src)
    token_count = len(tokens)
    char_count = len(src.strip())
    sentence_count = len(sentences)
    threshold_norm = effective_config.normalized_threshold()

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
                "sub_scores": {
                    "burstiness_low": 0.0,
                    "repetition_high": 0.0,
                    "connector_high": 0.0,
                    "punctuation_uniform": 0.0,
                    "entropy_low": 0.0,
                    "lexical_diversity_low": 0.0,
                    "template_density_high": 0.0,
                },
            },
            "evidence": ["text is empty"],
            "improvement_actions": ["add substantive body text before running AI-risk estimation"],
            "weights": effective_weights.as_dict(),
            "note": "heuristic estimate only; not a final determination",
        }

    unique_tokens = len(set(tokens))
    lexical_diversity = float(unique_tokens / max(1, token_count))
    sentence_burstiness = _sentence_length_cv(sentences)
    repeated_ratio = _repeated_ngram_ratio(tokens, n=3)
    connector_density = _connector_density_per_1k(src)
    punct_dominant = _dominant_punctuation_ratio(src)
    entropy_norm = _entropy_normalized(tokens)
    template_density = _template_heading_density(src)

    score_burst = _clamp((0.52 - sentence_burstiness) / 0.52)
    score_repeat = _clamp((repeated_ratio - 0.02) / 0.20)
    score_connector = _clamp((connector_density - 1.8) / 6.0)
    score_punct = _clamp((punct_dominant - 0.72) / 0.25)
    score_entropy = _clamp((0.82 - entropy_norm) / 0.30)
    score_lex = _clamp((0.38 - lexical_diversity) / 0.22)
    score_template = _clamp((template_density - 0.20) / 0.40)

    raw_score = (
        effective_weights.burstiness_low * score_burst
        + effective_weights.repetition_high * score_repeat
        + effective_weights.connector_high * score_connector
        + effective_weights.punctuation_uniform * score_punct
        + effective_weights.entropy_low * score_entropy
        + effective_weights.lexical_diversity_low * score_lex
        + effective_weights.template_density_high * score_template
    )
    raw_score = _clamp(raw_score)

    confidence_start = effective_config.normalized_confidence_start_tokens()
    confidence_full = effective_config.normalized_confidence_full_tokens()
    confidence = _clamp((token_count - confidence_start) / max(1, confidence_full - confidence_start))
    prior = effective_config.normalized_prior()
    ai_rate = _clamp(raw_score * confidence + prior * (1.0 - confidence))

    evidence: list[str] = []
    if score_repeat >= 0.6:
        evidence.append("repeated n-gram ratio is high")
    if score_burst >= 0.6:
        evidence.append("sentence-length variation is low")
    if score_connector >= 0.6:
        evidence.append("connector density is high")
    if score_punct >= 0.6:
        evidence.append("punctuation distribution is overly uniform")
    if score_entropy >= 0.6:
        evidence.append("token entropy is low")
    if score_lex >= 0.6:
        evidence.append("lexical diversity is low")
    if token_count < 120:
        evidence.append("short sample; confidence is limited")
    if not evidence:
        evidence.append("no dominant model-like signal observed")

    if ai_rate >= 0.78:
        risk_level = "high"
    elif ai_rate >= 0.58:
        risk_level = "medium"
    else:
        risk_level = "low"

    improvement_actions = _build_improvement_actions(
        score_burst=score_burst,
        score_repeat=score_repeat,
        score_connector=score_connector,
        score_punct=score_punct,
        score_entropy=score_entropy,
        score_lex=score_lex,
        score_template=score_template,
        confidence=confidence,
    )

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
        "improvement_actions": improvement_actions,
        "weights": effective_weights.as_dict(),
        "note": "heuristic estimate only; not a final determination",
    }
