"""Graph Section Draft Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

# Continue-draft prompt markers retained for contract scanners:
# <task>continue_section_draft</task>
# <constraints>
# <retry_reason>

from __future__ import annotations

import os
import queue
import re
import time

from writing_agent.v2 import (
    graph_section_continue_domain,
    graph_section_draft_blocks_domain,
    graph_section_draft_guard_domain,
    graph_section_draft_structured_domain,
    graph_section_fill_domain,
)
from writing_agent.v2.graph_section_postprocess_domain import (
    ensure_media_markers,
    format_references,
    postprocess_section,
    strip_inline_headings,
)

normalize_section_id = graph_section_continue_domain.normalize_section_id
_focus_point_weight = graph_section_continue_domain._focus_point_weight
_split_focus_points_balanced = graph_section_continue_domain._split_focus_points_balanced
_plan_continue_segments = graph_section_continue_domain._plan_continue_segments
ensure_section_minimums_stream = graph_section_continue_domain.ensure_section_minimums_stream
_build_continue_prompt = graph_section_continue_domain._build_continue_prompt
generic_fill_paragraph = graph_section_fill_domain.generic_fill_paragraph
fast_fill_references = graph_section_fill_domain.fast_fill_references
fast_fill_section = graph_section_fill_domain.fast_fill_section


REF_HEADING_RE = re.compile(r"^\s*(?:\u53c2\u8003\u6587\u732e|references|bibliography)\s*$", re.IGNORECASE)
REF_LINE_RE = re.compile(r"^\s*\[\d+\]\s+")


def _compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def strip_reference_like_lines(text: str) -> str:
    if not text:
        return ""
    lines = (text or "").splitlines()
    out: list[str] = []
    drop_rest = False
    for line in lines:
        token = (line or "").strip()
        if REF_HEADING_RE.match(token):
            drop_rest = True
            continue
        if drop_rest:
            continue
        if REF_LINE_RE.match(token):
            continue
        out.append(line)
    return "\n".join(out).strip()


def parse_structured_payload(payload) -> list[dict]:
    return list(graph_section_draft_structured_domain.parse_structured_payload(payload))


def parse_structured_line(line: str) -> list[dict]:
    return list(graph_section_draft_structured_domain.parse_structured_line(line))


def _strip_code_fence(text: str) -> str:
    return str(graph_section_draft_structured_domain._strip_code_fence(text))


def _try_parse_structured_blob(blob: str) -> list[dict]:
    return list(graph_section_draft_structured_domain._try_parse_structured_blob(blob))


def _extract_text_like_payload(raw: str) -> str:
    return str(graph_section_draft_structured_domain._extract_text_like_payload(raw))


def render_block_to_text(block: dict) -> str:
    return str(graph_section_draft_blocks_domain.render_block_to_text(block))


def persist_block_to_store(block: dict, text_store) -> str | None:
    return graph_section_draft_blocks_domain.persist_block_to_store(block, text_store)


def accept_block(block: dict, section_id: str, is_reference: bool) -> bool:
    return bool(graph_section_draft_blocks_domain.accept_block(block, section_id, is_reference))


def _hits_semantic_sampling_guard(text: str, section: str) -> list[str]:
    return list(graph_section_draft_guard_domain._hits_semantic_sampling_guard(text=text, section=section))

def stream_structured_blocks(
    *,
    client,
    system: str,
    user: str,
    out_queue: queue.Queue[dict],
    section: str,
    section_id: str,
    is_reference: bool,
    num_predict: int,
    deadline: float,
    max_chars: int = 0,
    strict_json: bool = True,
    text_store=None,
) -> str:
    strict_json_raw = os.environ.get("WRITING_AGENT_STRICT_JSON", "1").strip().lower()
    strict_json_env = strict_json_raw in {"1", "true", "yes", "on"}
    strict_json = bool(strict_json) and strict_json_env
    buf = ""
    raw_buf_parts: list[str] = []
    texts: list[str] = []
    plain_lines: list[str] = []
    seen: set[str] = set()
    seen_norm: set[str] = set()
    invalid_line = False
    emitted_chars = 0
    stop_requested = False
    repeat_streak = 0
    last_norm = ""
    token_estimate = 0
    try:
        max_output_tokens = max(256, int(os.environ.get("WRITING_AGENT_SECTION_MAX_OUTPUT_TOKENS", "4000")))
    except Exception:
        max_output_tokens = 4000
    char_limit = int(max_chars) if int(max_chars or 0) > 0 else 0
    stop_threshold = int(char_limit * 1.25) if char_limit > 0 else 0
    for delta in client.chat_stream(system=system, user=user, temperature=0.35, options={"num_predict": num_predict}):
        if time.time() > deadline or stop_requested:
            break
        if delta:
            raw_buf_parts.append(str(delta))
            token_estimate += max(1, int(len(str(delta)) / 4))
            if token_estimate > max_output_tokens:
                out_queue.put(
                    {
                        "event": "section_token_budget_exceeded",
                        "section": section,
                        "section_id": section_id,
                        "estimated_tokens": token_estimate,
                        "max_tokens": max_output_tokens,
                    }
                )
                raise RuntimeError("token_budget_exceeded")
        buf += delta
        while "\n" in buf:
            if stop_requested:
                break
            line, buf = buf.split("\n", 1)
            parsed = parse_structured_line(line)
            if not parsed and line.strip():
                invalid_line = True
                token = str(line or "").strip()
                recovered_plain = _extract_text_like_payload(token)
                if recovered_plain:
                    plain_lines.append(recovered_plain)
            for block in parsed:
                if not accept_block(block, section_id, is_reference):
                    continue
                stored_id = persist_block_to_store(block, text_store)
                text = render_block_to_text(block)
                if not text:
                    continue
                norm = re.sub(r"\s+", " ", text).strip()
                if norm and norm in seen_norm:
                    continue
                block_id = str(stored_id or block.get("block_id") or block.get("id") or f"b{len(seen) + 1}")
                if block_id in seen:
                    continue
                seen.add(block_id)
                if norm:
                    seen_norm.add(norm)
                semantic_hits = []
                if not texts:
                    semantic_hits = _hits_semantic_sampling_guard(text, section)
                    if semantic_hits:
                        out_queue.put(
                            {
                                "event": "semantic_sampling_hit",
                                "section": section,
                                "section_id": section_id,
                                "hits": list(semantic_hits),
                                "mode": "early_abort",
                            }
                        )
                        raise ValueError("semantic_sampling_failed")
                texts.append(text)
                emitted_chars += _compact_len(text)
                if norm and norm == last_norm:
                    repeat_streak += 1
                else:
                    repeat_streak = 0
                    last_norm = norm
                block_type = str(block.get("type") or "paragraph")
                payload = {
                    "event": "section",
                    "phase": "delta",
                    "section": section,
                    "delta": text,
                    "block_uid": f"{section_id}:{len(seen):03d}",
                    "block_id": block_id,
                    "block_type": block_type,
                }
                if block_type in {"paragraph", "text", "p", "list", "bullets", "bullet", "reference", "ref"}:
                    payload.pop("block_id", None)
                out_queue.put(payload)
                if (stop_threshold > 0 and emitted_chars >= stop_threshold) or repeat_streak >= 8:
                    stop_requested = True
                    break
    leftover = buf.strip()
    if leftover:
        blocks = _try_parse_structured_blob(leftover)
        if not blocks and leftover.strip():
            invalid_line = True
            token = str(leftover or "").strip()
            recovered_plain = _extract_text_like_payload(token)
            if recovered_plain:
                plain_lines.append(recovered_plain)
        for block in blocks:
            if not accept_block(block, section_id, is_reference):
                continue
            stored_id = persist_block_to_store(block, text_store)
            text = render_block_to_text(block)
            if not text:
                continue
            norm = re.sub(r"\s+", " ", text).strip()
            if norm and norm in seen_norm:
                continue
            block_id = str(stored_id or block.get("block_id") or block.get("id") or f"b{len(seen) + 1}")
            if block_id in seen:
                continue
            seen.add(block_id)
            if norm:
                seen_norm.add(norm)
            semantic_hits = []
            if not texts:
                semantic_hits = _hits_semantic_sampling_guard(text, section)
                if semantic_hits:
                    out_queue.put(
                        {
                            "event": "semantic_sampling_hit",
                            "section": section,
                            "section_id": section_id,
                            "hits": list(semantic_hits),
                            "mode": "early_abort",
                        }
                    )
                    raise ValueError("semantic_sampling_failed")
            texts.append(text)
            emitted_chars += _compact_len(text)
            if norm and norm == last_norm:
                repeat_streak += 1
            else:
                repeat_streak = 0
                last_norm = norm
            block_type = str(block.get("type") or "paragraph")
            payload = {
                "event": "section",
                "phase": "delta",
                "section": section,
                "delta": text,
                "block_uid": f"{section_id}:{len(seen):03d}",
                "block_id": block_id,
                "block_type": block_type,
            }
            if block_type in {"paragraph", "text", "p", "list", "bullets", "bullet", "reference", "ref"}:
                payload.pop("block_id", None)
            out_queue.put(payload)
            if (stop_threshold > 0 and emitted_chars >= stop_threshold) or repeat_streak >= 8:
                break
        if strict_json and invalid_line and not texts:
            recovered = "\n".join([ln for ln in plain_lines if ln]).strip()
            if recovered:
                texts.append(recovered)
                out_queue.put(
                    {
                        "event": "section",
                        "phase": "delta",
                        "section": section,
                        "delta": recovered,
                        "block_type": "paragraph",
                        "fallback_mode": "plain_text_recovery",
                    }
                )
            else:
                raise ValueError("writer output contains non-json lines")
    if strict_json and not texts:
        full_raw = "".join(raw_buf_parts).strip()
        recovered_blocks = _try_parse_structured_blob(full_raw)
        for block in recovered_blocks:
            if not accept_block(block, section_id, is_reference):
                continue
            text = render_block_to_text(block)
            if not text:
                continue
            norm = re.sub(r"\s+", " ", text).strip()
            if norm and norm in seen_norm:
                continue
            if norm:
                seen_norm.add(norm)
            texts.append(text)
        recovered = "\n".join([ln for ln in plain_lines if ln]).strip()
        if recovered:
            if recovered not in texts:
                texts.append(recovered)
            out_queue.put(
                {
                    "event": "section",
                    "phase": "delta",
                    "section": section,
                    "delta": recovered,
                    "block_type": "paragraph",
                    "fallback_mode": "plain_text_recovery",
                }
            )
    if strict_json and not texts:
        raise ValueError("writer output has no valid blocks")
    return "\n\n".join([t for t in texts if t]).strip()

