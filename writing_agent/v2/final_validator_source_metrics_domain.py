"""Source-overlap metrics extracted from final_validator_metrics_domain."""

from __future__ import annotations


def _base():
    from writing_agent.v2 import final_validator_metrics_domain as base

    return base


def _normalize_sentence(text: str) -> str:
    return str(_base()._normalize_sentence(text))


def _collect_sentences(text: str) -> list[str]:
    return list(_base()._collect_sentences(text))


def _source_text_fragments(source_rows: list[dict] | None) -> list[str]:
    if not source_rows:
        return []
    out: list[str] = []
    seen: set[str] = set()
    candidate_keys = (
        "summary",
        "abstract",
        "snippet",
        "excerpt",
        "text",
        "content",
        "body",
        "source_text",
        "context",
    )
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        for key in candidate_keys:
            value = row.get(key)
            values = value if isinstance(value, list) else [value]
            for item in values:
                chunk = str(item or "").strip()
                norm = _normalize_sentence(chunk)
                if len(norm) < 24 or norm in seen:
                    continue
                seen.add(norm)
                out.append(chunk)
                if len(out) >= 120:
                    return out
    return out


def _char_shingles(text: str, *, size: int = 6) -> set[str]:
    normalized = _normalize_sentence(text)
    if len(normalized) < max(8, size + 2):
        return set()
    return {normalized[idx: idx + size] for idx in range(0, len(normalized) - size + 1)}


def _source_overlap_metrics(text: str, source_rows: list[dict] | None) -> tuple[float, list[str], int]:
    source_fragments = _source_text_fragments(source_rows)
    if not source_fragments:
        return 0.0, [], 0
    source_sentences: list[tuple[str, set[str], str]] = []
    for fragment in source_fragments:
        for sent in _collect_sentences(fragment):
            norm = _normalize_sentence(sent)
            if len(norm) < 18:
                continue
            shingles = _char_shingles(norm)
            if not shingles:
                continue
            source_sentences.append((norm, shingles, sent.strip()))
            if len(source_sentences) >= 240:
                break
        if len(source_sentences) >= 240:
            break
    if not source_sentences:
        return 0.0, [], 0
    candidate_sentences = [s for s in _collect_sentences(text) if len(_normalize_sentence(s)) >= 18]
    if not candidate_sentences:
        return 0.0, [], 0
    hit_count = 0
    hit_fragments: list[str] = []
    for sent in candidate_sentences:
        norm = _normalize_sentence(sent)
        if len(norm) < 18:
            continue
        shingles = _char_shingles(norm)
        if not shingles:
            continue
        copied = False
        for src_norm, src_shingles, _src_text in source_sentences:
            shorter = min(len(norm), len(src_norm))
            if shorter >= 18 and (norm in src_norm or src_norm in norm):
                copied = True
            else:
                overlap = len(shingles & src_shingles)
                base = float(max(1, min(len(shingles), len(src_shingles))))
                score = float(overlap) / base
                if score >= 0.88 or (score >= 0.8 and shorter >= 28):
                    copied = True
            if copied:
                hit_count += 1
                if len(hit_fragments) < 8:
                    hit_fragments.append(str(sent).strip()[:200])
                break
    return float(hit_count) / float(max(1, len(candidate_sentences))), hit_fragments, len(candidate_sentences)


__all__ = [name for name in globals() if not name.startswith("__")]
