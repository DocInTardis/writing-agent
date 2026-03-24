"""Structure and sentence-level metrics extracted from final_validator_metrics_domain."""

from __future__ import annotations

import re

_SECTION_TOKEN_RE = re.compile(r"^H([23])::(.*)$")
_SENT_SPLIT_RE = re.compile(r"(?:[\u3002\uff01\uff1f!?]+|(?<=[A-Za-z0-9])[.]+)\s*")
_STRUCTURED_BLOCK_RE = re.compile(r"\[\[(?:TABLE|FIGURE):.*?\]\]", re.IGNORECASE | re.DOTALL)


def _title_tokens(text: str) -> list[str]:
    src = str(text or "").strip().lower()
    if not src:
        return []
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z][a-z0-9\-]{2,}", src)
    out: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        token = tok.strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _title_body_alignment_score(title: str, body: str) -> float:
    title_tokens = _title_tokens(title)
    if not title_tokens:
        return 1.0
    if len(title_tokens) == 1 and len(title_tokens[0]) <= 2:
        return 1.0
    body_text = str(body or "").lower()
    if not body_text.strip():
        return 0.0
    overlap = 0
    for tok in title_tokens:
        if tok in body_text:
            overlap += 1
    return float(overlap) / float(max(1, len(title_tokens)))


def _normalize_sentence(text: str) -> str:
    token = str(text or "").strip().lower()
    token = re.sub(r"\s+", "", token)
    token = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", token)
    return token


def _strip_structured_blocks(text: str) -> str:
    return _STRUCTURED_BLOCK_RE.sub(" ", str(text or ""))


def _normalize_expected_heading(section: object) -> str:
    raw = str(section or "").strip()
    if not raw:
        return ""
    match = _SECTION_TOKEN_RE.match(raw)
    if match:
        raw = str(match.group(2) or "").strip()
    raw = re.sub(r"^\u7b2c\s*\d+\s*[\u7ae0\u8282]\s*", "", raw)
    raw = re.sub(r"^\d+(?:\.\d+)*\s*", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    lower = raw.lower()
    if ("\u53c2\u8003\u6587\u732e" in raw) or ("references" in lower) or (raw == "\u6587\u732e"):
        return "\u53c2\u8003\u6587\u732e"
    return raw


def _collect_sentences(text: str) -> list[str]:
    src = _strip_structured_blocks(text)
    src = re.sub(r"(?m)^#+\s+.*$", " ", src)
    src = src.replace("\r", "\n")
    out: list[str] = []
    for chunk in _SENT_SPLIT_RE.split(src):
        token = str(chunk or "").strip()
        if len(token) < 6:
            continue
        out.append(token)
    if out:
        return out
    for chunk in re.split(r"\n\s*\n+", src):
        token = str(chunk or "").strip()
        if len(token) < 6:
            continue
        out.append(token)
    return out


def _paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n+", _strip_structured_blocks(text)) if str(p).strip()]


def _repeat_sentence_ratio(text: str) -> float:
    sents = _collect_sentences(text)
    if not sents:
        return 0.0
    seen: set[str] = set()
    dup = 0
    for sent in sents:
        key = _normalize_sentence(sent)
        if not key:
            continue
        if key in seen:
            dup += 1
            continue
        seen.add(key)
    return float(dup) / float(max(1, len(sents)))


def _sentence_opening_signature(text: str, *, prefix_chars: int = 10) -> str:
    raw = str(text or "").strip().lower()
    lexical = [tok for tok in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z][a-z0-9\-]*", raw) if tok]
    if len(lexical) >= 2:
        signature = " ".join(lexical[:2]).strip()
        if len(signature) >= 6:
            return signature
    key = _normalize_sentence(text)
    if len(key) < max(6, prefix_chars):
        return ""
    return key[:prefix_chars]


def _formulaic_opening_ratio(text: str) -> tuple[float, list[str]]:
    sents = [s for s in _collect_sentences(text) if len(_normalize_sentence(s)) >= 12]
    if not sents:
        return 0.0, []
    counts: dict[str, int] = {}
    samples: dict[str, str] = {}
    signatures: list[str] = []
    for sent in sents:
        sig = _sentence_opening_signature(sent)
        if not sig:
            continue
        signatures.append(sig)
        counts[sig] = int(counts.get(sig, 0)) + 1
        samples.setdefault(sig, str(sent).strip())
    if not signatures:
        return 0.0, []
    repeated = [sig for sig in signatures if int(counts.get(sig, 0)) >= 3]
    hit_fragments = [samples[sig][:200] for sig, count in counts.items() if count >= 3][:8]
    return float(len(repeated)) / float(max(1, len(signatures))), hit_fragments


def _section_body_map(text: str) -> dict[str, list[str]]:
    body = str(text or "")
    matches = list(re.finditer(r"(?m)^(##+)\s+(.+?)\s*$", body))
    out: dict[str, list[str]] = {}
    for idx, match in enumerate(matches):
        title = _normalize_expected_heading(match.group(2))
        if not title:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        section_body = body[start:end].strip()
        out.setdefault(title, []).append(section_body)
    return out


def _section_body_has_content(text: str) -> bool:
    src = str(text or "")
    if not src.strip():
        return False
    stripped = _strip_structured_blocks(src)
    if re.sub(r"\s+", "", stripped):
        return True
    return bool(_STRUCTURED_BLOCK_RE.search(src))


__all__ = [name for name in globals() if not name.startswith("__")]
