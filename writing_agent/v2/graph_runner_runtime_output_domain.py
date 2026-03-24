"""Output cleanup helpers extracted from runtime section domain."""

from __future__ import annotations

import re


def _base():
    from writing_agent.v2 import graph_runner_runtime_section_domain as base

    return base


def _runtime_split_sentences(text: str) -> list[str]:
    src = str(text or "").strip()
    if not src:
        return []
    out: list[str] = []
    buf: list[str] = []
    end_tokens = {"\u3002", "\uff01", "\uff1f", "!", "?", "\uff1b", ";"}
    for ch in src:
        buf.append(ch)
        if ch in end_tokens:
            token = "".join(buf).strip()
            if token:
                out.append(token)
            buf = []
    if buf:
        token = "".join(buf).strip()
        if token:
            out.append(token)
    return out or [src]


def _runtime_sentence_is_unsupported_claim(text: str) -> bool:
    token = str(text or "").strip()
    if not token:
        return False
    base = _base()
    if base._graph_runner_module.final_validator._SUPPORT_MARKER_RE.search(token):
        return False
    numeric_claim = bool(
        base._graph_runner_module.final_validator._NUMERIC_TOKEN_RE.search(token)
        and base._graph_runner_module.final_validator._CLAIM_COMPARATIVE_RE.search(token)
    )
    signaled_metric_claim = bool(
        base._graph_runner_module.final_validator._NUMERIC_TOKEN_RE.search(token)
        and base._graph_runner_module.final_validator._CLAIM_SIGNAL_RE.search(token)
    )
    if (numeric_claim or signaled_metric_claim) and base._graph_runner_module.final_validator._NON_CLAIM_CONFIGURATION_RE.search(token):
        return False
    return bool(numeric_claim or signaled_metric_claim)


def _prune_unsupported_claim_paragraphs(text: str) -> str:
    base = _base()
    blocks = [blk for blk in re.split(r"\n\s*\n+", str(text or ""))]
    if not blocks:
        return str(text or "")
    out: list[str] = []
    in_reference = False
    for block in blocks:
        token = str(block or "").strip()
        if not token:
            continue
        if re.match(r"^##\s+", token):
            heading = re.sub(r"^##\s+", "", token).strip()
            in_reference = base._is_reference_section(heading)
            out.append(token)
            continue
        if in_reference:
            out.append(token)
            continue
        if "[[TABLE:" in token or "[[FIGURE:" in token:
            markers = re.findall(r"\[\[(?:TABLE|FIGURE):[\s\S]*?\]\]", token, flags=re.IGNORECASE)
            trailing = re.sub(r"\[\[(?:TABLE|FIGURE):[\s\S]*?\]\]", " ", token, flags=re.IGNORECASE).strip()
            if trailing:
                kept_sentences: list[str] = []
                for part in base._runtime_split_sentences(trailing):
                    sentence = str(part or "").strip()
                    if not sentence:
                        continue
                    if base._runtime_sentence_is_unsupported_claim(sentence):
                        continue
                    kept_sentences.append(sentence)
                trailing = "".join(kept_sentences).strip()
            marker_text = "\n\n".join([m.strip() for m in markers if str(m).strip()])
            combined = "\n\n".join([x for x in [marker_text, trailing] if str(x).strip()]).strip()
            if combined:
                out.append(combined)
            continue
        kept_parts: list[str] = []
        for part in base._runtime_split_sentences(token):
            sentence = str(part or "").strip()
            if not sentence:
                continue
            if base._runtime_sentence_is_unsupported_claim(sentence):
                continue
            kept_parts.append(sentence)
        cleaned_token = "".join(kept_parts).strip()
        if cleaned_token:
            out.append(cleaned_token)
    return "\n\n".join(out).strip()


def _normalize_final_output(text: str, *, expected_sections: list[str] | None = None, title_override: str = "") -> str:
    base = _base()
    cleaned = base._strip_markdown_noise(text or "")
    cleaned = re.sub(r"(?m)^(#{1,3}\s+.+?)\s*#+\s*$", r"\1", cleaned)
    cleaned = re.sub(r"(?m)^\s*#+\s*$", "", cleaned)
    parsed = base.parse_report_text(cleaned)
    expected: list[tuple[int, str]] = []
    expected_index: dict[str, tuple[int, str]] = {}
    if expected_sections:
        for sec in expected_sections:
            lvl, title = base._split_section_token(sec)
            clean = base._clean_outline_title(title)
            if not clean:
                continue
            if clean in base._DISALLOWED_SECTIONS or clean in base._ACK_SECTIONS:
                continue
            normalized_title = "\u53c2\u8003\u6587\u732e" if base._is_reference_section(clean) else clean
            lvl_i = 3 if lvl >= 3 else 2
            if normalized_title in expected_index:
                continue
            row = (lvl_i, normalized_title)
            expected.append(row)
            expected_index[normalized_title] = row

    out_blocks: list = []
    collected_blocks: dict[str, list] = {title: [] for _, title in expected}
    skip_level: int | None = None
    current_expected_title = ""
    for block in parsed.blocks:
        if block.type == "heading":
            lvl = int(block.level or 1)
            if skip_level is not None and lvl <= skip_level:
                skip_level = None
            if skip_level is not None:
                continue
            title_raw = (block.text or "").strip()
            title = base._clean_section_title(title_raw)
            if not title:
                current_expected_title = ""
                skip_level = lvl
                continue
            if int(block.level or 1) == 1:
                current_expected_title = ""
                continue
            normalized_title = "\u53c2\u8003\u6587\u732e" if base._is_reference_section(title) else title
            if expected:
                if normalized_title not in expected_index:
                    current_expected_title = ""
                    skip_level = lvl
                    continue
                current_expected_title = normalized_title
                continue
            current_expected_title = ""
            out_blocks.append(base.DocBlock(type="heading", level=(3 if lvl >= 3 else 2), text=normalized_title))
            continue
        if skip_level is not None:
            continue
        if expected and current_expected_title:
            collected_blocks.setdefault(current_expected_title, []).append(block)
            continue
        if not expected:
            out_blocks.append(block)
    if expected:
        rebuilt_blocks: list = []
        for lvl_i, title_i in expected:
            rebuilt_blocks.append(base.DocBlock(type="heading", level=lvl_i, text=title_i))
            rebuilt_blocks.extend(collected_blocks.get(title_i) or [])
        if out_blocks and out_blocks[0].type == "heading" and int(out_blocks[0].level or 0) == 1:
            out_blocks = [out_blocks[0], *rebuilt_blocks]
        else:
            out_blocks = rebuilt_blocks
    if not any(block.type == "heading" and int(block.level or 0) == 1 for block in out_blocks):
        title_line = base._normalize_title_line(title_override or parsed.title or base._default_title())
        out_blocks.insert(0, base.DocBlock(type="heading", level=1, text=title_line))
    normalized = base._blocks_to_doc_text(out_blocks)
    normalized = base._prune_unsupported_claim_paragraphs(normalized)
    if title_override:
        forced_title = base._normalize_title_line(title_override)
        if re.search(r"(?m)^#\s+.+$", normalized):
            normalized = re.sub(r"(?m)^#\s+.+$", f"# {forced_title}", normalized, count=1)
        else:
            normalized = f"# {forced_title}\n\n" + normalized.lstrip()
    expects_reference = any(base._is_reference_section(base._section_title(sec) or sec) for sec in (expected_sections or []))
    if expects_reference and ('## \u53c2\u8003\u6587\u732e' not in normalized) and re.search(r"(?m)^\[\d+\]\s+", normalized):
        normalized = re.sub(
            r"(?m)^(\[\d+\]\s+)",
            lambda match: '## \u53c2\u8003\u6587\u732e' + "\n\n" + match.group(1),
            normalized,
            count=1,
        )
    return normalized


__all__ = [name for name in globals() if not name.startswith("__")]
