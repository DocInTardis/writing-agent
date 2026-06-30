"""Plagiarism module.

This module belongs to `writing_agent.quality` in the writing-agent codebase.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", flags=re.IGNORECASE)
_KEEP_CHAR_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+", flags=re.IGNORECASE)


def _stable_hash64(value: str) -> int:
    digest = hashlib.blake2b(value.encode("utf-8", errors="ignore"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)


def _clamp_float(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _normalize_text(text: str, *, max_chars: int = 220_000) -> str:
    src = str(text or "")
    if len(src) > max_chars:
        src = src[:max_chars]
    src = src.lower()
    src = _KEEP_CHAR_RE.sub("", src)
    return src


def _tokenize_for_simhash(text: str, *, max_chars: int = 220_000) -> list[str]:
    src = str(text or "")
    if len(src) > max_chars:
        src = src[:max_chars]
    src = src.lower()
    return _TOKEN_RE.findall(src)


def _char_ngrams(text: str, n: int) -> set[str]:
    if n <= 1:
        return {ch for ch in text if ch}
    if len(text) < n:
        return {text} if text else set()
    out: set[str] = set()
    for idx in range(0, len(text) - n + 1):
        out.add(text[idx : idx + n])
    return out


def _winnowing_fingerprints(text: str, *, k: int, window: int) -> list[tuple[int, int]]:
    """Return (hash, position) pairs via rightmost-minimum winnowing."""
    if not text:
        return []
    k = max(3, int(k))
    w = max(1, int(window))
    if len(text) < k:
        return [(_stable_hash64(text), 0)]
    hashes: list[int] = []
    for i in range(0, len(text) - k + 1):
        hashes.append(_stable_hash64(text[i : i + k]))
    if not hashes:
        return []
    # Fallback when the number of k-grams is smaller than one window.
    if len(hashes) <= w:
        m = min(hashes)
        pos = max(i for i, v in enumerate(hashes) if v == m)
        return [(m, pos)]

    out: list[tuple[int, int]] = []
    picked_pos: set[int] = set()
    for start in range(0, len(hashes) - w + 1):
        win = hashes[start : start + w]
        min_hash = min(win)
        rel = 0
        for j in range(w - 1, -1, -1):
            if win[j] == min_hash:
                rel = j
                break
        abs_pos = start + rel
        if abs_pos in picked_pos:
            continue
        picked_pos.add(abs_pos)
        out.append((min_hash, abs_pos))
    return out


def _simhash64(tokens: list[str]) -> int:
    if not tokens:
        return 0
    vec = [0] * 64
    for token in tokens:
        hv = _stable_hash64(token)
        for bit in range(64):
            if (hv >> bit) & 1:
                vec[bit] += 1
            else:
                vec[bit] -= 1
    out = 0
    for bit, val in enumerate(vec):
        if val >= 0:
            out |= 1 << bit
    return out


def _hamming_distance64(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _evidence_blocks(source_text: str, reference_text: str, *, min_match_chars: int) -> list[dict[str, Any]]:
    src = str(source_text or "")
    ref = str(reference_text or "")
    if not src or not ref:
        return []
    matcher = SequenceMatcher(None, src, ref, autojunk=False)
    blocks = matcher.get_matching_blocks()
    # Last block is a sentinel (size=0).
    blocks = [b for b in blocks if b.size >= max(12, int(min_match_chars))]
    blocks.sort(key=lambda b: b.size, reverse=True)
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for block in blocks[:5]:
        key = (block.a, block.b)
        if key in seen:
            continue
        seen.add(key)
        snippet = src[block.a : block.a + min(block.size, 140)].strip()
        out.append(
            {
                "source_start": int(block.a),
                "reference_start": int(block.b),
                "match_chars": int(block.size),
                "snippet": snippet,
            }
        )
    return out


def _build_revision_advice(*, metrics: dict[str, Any], suspected: bool) -> list[str]:
    advice: list[str] = []
    containment = float(metrics.get("containment") or 0.0)
    jaccard = float(metrics.get("jaccard_resemblance") or 0.0)
    winnowing = float(metrics.get("winnowing_overlap") or 0.0)
    longest = int(metrics.get("longest_match_chars") or 0)
    if suspected or containment >= 0.35:
        advice.append("优先重写证据后的分析句群，而不是只删句或只做同义词替换。")
    if containment >= 0.45:
        advice.append("当前文本对来源表述的覆盖度偏高，建议先脱离原文组织顺序，再按自己的论证结构重写。")
    if longest >= 40:
        advice.append("连续命中片段较长；必要直接引语请保留引号和出处，其余内容改写为你自己的分析。")
    if max(jaccard, winnowing) >= 0.35:
        advice.append("局部相似块较多，建议拆分段落并重组论证顺序，把来源事实转成比较、解释或限制。")
    if not advice:
        advice.append("当前未见明显高重合信号，但导出前仍建议与历史稿、样本文本或资料库做一次交叉扫描。")
    return advice[:4]


@dataclass
class PlagiarismConfig:
    ngram_size: int = 7
    winnowing_k: int = 13
    winnowing_window: int = 17
    min_match_chars: int = 24

    def normalized(self) -> "PlagiarismConfig":
        return PlagiarismConfig(
            ngram_size=max(3, min(16, int(self.ngram_size))),
            winnowing_k=max(5, min(64, int(self.winnowing_k))),
            winnowing_window=max(4, min(128, int(self.winnowing_window))),
            min_match_chars=max(16, min(320, int(self.min_match_chars))),
        )


@dataclass
class PlagiarismWeights:
    containment: float = 0.36
    jaccard: float = 0.24
    winnowing_overlap: float = 0.20
    simhash_similarity: float = 0.12
    sequence_ratio: float = 0.08

    def normalized(self) -> "PlagiarismWeights":
        raw = [
            max(0.0, float(self.containment)),
            max(0.0, float(self.jaccard)),
            max(0.0, float(self.winnowing_overlap)),
            max(0.0, float(self.simhash_similarity)),
            max(0.0, float(self.sequence_ratio)),
        ]
        total = sum(raw)
        if total <= 0:
            return PlagiarismWeights()
        return PlagiarismWeights(
            containment=raw[0] / total,
            jaccard=raw[1] / total,
            winnowing_overlap=raw[2] / total,
            simhash_similarity=raw[3] / total,
            sequence_ratio=raw[4] / total,
        )

    def as_dict(self) -> dict[str, float]:
        normalized = self.normalized()
        return {
            "containment": round(normalized.containment, 6),
            "jaccard": round(normalized.jaccard, 6),
            "winnowing_overlap": round(normalized.winnowing_overlap, 6),
            "simhash_similarity": round(normalized.simhash_similarity, 6),
            "sequence_ratio": round(normalized.sequence_ratio, 6),
        }


def compare_text_pair(
    source_text: str,
    reference_text: str,
    *,
    threshold: float = 0.35,
    config: PlagiarismConfig | None = None,
    weights: PlagiarismWeights | None = None,
) -> dict[str, Any]:
    cfg = (config or PlagiarismConfig()).normalized()
    score_weights = (weights or PlagiarismWeights()).normalized()
    th = _clamp_float(float(threshold), 0.05, 0.95)

    source_norm = _normalize_text(source_text)
    ref_norm = _normalize_text(reference_text)
    source_chars = len(source_norm)
    ref_chars = len(ref_norm)

    if source_chars == 0 or ref_chars == 0:
        return {
            "score": 0.0,
            "threshold": th,
            "suspected": False,
            "metrics": {
                "source_chars": source_chars,
                "reference_chars": ref_chars,
                "jaccard_resemblance": 0.0,
                "containment": 0.0,
                "winnowing_overlap": 0.0,
                "simhash_similarity": 0.0,
                "sequence_ratio": 0.0,
                "longest_match_chars": 0,
                "longest_match_ratio": 0.0,
                "shared_ngrams": 0,
            },
            "evidence": [],
            "revision_advice": ["文本为空或参考文本为空，无法形成有效比对。"],
        }

    source_grams = _char_ngrams(source_norm, cfg.ngram_size)
    ref_grams = _char_ngrams(ref_norm, cfg.ngram_size)
    shared_grams = source_grams.intersection(ref_grams)
    union_grams = source_grams.union(ref_grams)
    jaccard = (len(shared_grams) / len(union_grams)) if union_grams else 0.0
    containment = (len(shared_grams) / len(source_grams)) if source_grams else 0.0

    src_fp = _winnowing_fingerprints(source_norm, k=cfg.winnowing_k, window=cfg.winnowing_window)
    ref_fp = _winnowing_fingerprints(ref_norm, k=cfg.winnowing_k, window=cfg.winnowing_window)
    src_fp_set = {h for h, _ in src_fp}
    ref_fp_set = {h for h, _ in ref_fp}
    winnowing_overlap = (len(src_fp_set.intersection(ref_fp_set)) / len(src_fp_set)) if src_fp_set else 0.0

    src_tokens = _tokenize_for_simhash(source_text)
    ref_tokens = _tokenize_for_simhash(reference_text)
    src_hash = _simhash64(src_tokens)
    ref_hash = _simhash64(ref_tokens)
    hamming = _hamming_distance64(src_hash, ref_hash)
    simhash_similarity = 1.0 - (hamming / 64.0)

    seq = SequenceMatcher(None, source_norm, ref_norm, autojunk=False)
    seq_ratio = float(seq.ratio())
    longest = 0
    for block in seq.get_matching_blocks():
        if block.size > longest:
            longest = int(block.size)
    longest_ratio = (longest / source_chars) if source_chars else 0.0

    # Hybrid score:
    # - containment/resemblance from shingling (Broder style)
    # - robust local overlap from winnowing fingerprints
    # - lexical robustness from SimHash
    # - global sequence ratio as a tie-breaker signal
    score = (
        score_weights.containment * containment
        + score_weights.jaccard * jaccard
        + score_weights.winnowing_overlap * winnowing_overlap
        + score_weights.simhash_similarity * simhash_similarity
        + score_weights.sequence_ratio * seq_ratio
    )
    score = _clamp_float(score, 0.0, 1.0)

    evidence = _evidence_blocks(source_text, reference_text, min_match_chars=cfg.min_match_chars)
    metrics = {
        "source_chars": source_chars,
        "reference_chars": ref_chars,
        "jaccard_resemblance": round(jaccard, 4),
        "containment": round(containment, 4),
        "winnowing_overlap": round(winnowing_overlap, 4),
        "simhash_similarity": round(simhash_similarity, 4),
        "sequence_ratio": round(seq_ratio, 4),
        "longest_match_chars": int(longest),
        "longest_match_ratio": round(longest_ratio, 4),
        "shared_ngrams": int(len(shared_grams)),
    }
    revision_advice = _build_revision_advice(metrics=metrics, suspected=bool(score >= th))

    return {
        "score": round(score, 4),
        "threshold": round(th, 4),
        "suspected": bool(score >= th),
        "metrics": metrics,
        "evidence": evidence,
        "revision_advice": revision_advice,
        "weights": score_weights.as_dict(),
    }


def compare_against_references(
    source_text: str,
    references: list[dict[str, Any]],
    *,
    threshold: float = 0.35,
    top_k: int = 10,
    config: PlagiarismConfig | None = None,
    weights: PlagiarismWeights | None = None,
) -> dict[str, Any]:
    cfg = (config or PlagiarismConfig()).normalized()
    score_weights = (weights or PlagiarismWeights()).normalized()
    th = _clamp_float(float(threshold), 0.05, 0.95)
    k = max(1, min(100, int(top_k)))
    src = str(source_text or "")

    rows: list[dict[str, Any]] = []
    for idx, raw in enumerate(references):
        if not isinstance(raw, dict):
            continue
        rid = str(raw.get("id") or f"ref_{idx + 1}").strip()[:120] or f"ref_{idx + 1}"
        title = str(raw.get("title") or rid).strip()[:200] or rid
        ref_text = str(raw.get("text") or "")
        if not ref_text.strip():
            continue
        one = compare_text_pair(src, ref_text, threshold=th, config=cfg, weights=score_weights)
        rows.append(
            {
                "reference_id": rid,
                "reference_title": title,
                "score": one.get("score", 0.0),
                "threshold": one.get("threshold", th),
                "suspected": bool(one.get("suspected")),
                "metrics": one.get("metrics", {}),
                "evidence": one.get("evidence", []),
                "revision_advice": one.get("revision_advice", []),
                "weights": one.get("weights", {}),
            }
        )

    rows.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    rows = rows[:k]
    max_score = max((float(x.get("score") or 0.0) for x in rows), default=0.0)
    flagged_count = sum(1 for x in rows if bool(x.get("suspected")))
    top_metrics = rows[0].get("metrics", {}) if rows else {}
    revision_advice = _build_revision_advice(metrics=top_metrics, suspected=bool(max_score >= th))

    return {
        "source_chars": len(_normalize_text(src)),
        "threshold": round(th, 4),
        "total_references": len(rows),
        "flagged_count": int(flagged_count),
        "max_score": round(max_score, 4),
        "suspected": bool(max_score >= th),
        "revision_advice": revision_advice,
        "results": rows,
        "config": {
            "ngram_size": cfg.ngram_size,
            "winnowing_k": cfg.winnowing_k,
            "winnowing_window": cfg.winnowing_window,
            "min_match_chars": cfg.min_match_chars,
            "weights": score_weights.as_dict(),
        },
    }
