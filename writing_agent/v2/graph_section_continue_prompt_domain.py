"""Section continuation prompt helpers."""

from __future__ import annotations

import queue
import time
from collections.abc import Callable

from writing_agent.v2 import graph_section_continue_helpers_domain as helpers_domain

_escape_prompt_text = helpers_domain._escape_prompt_text


def _build_continue_prompt(
    *,
    title: str,
    section: str,
    parent_section: str,
    instruction: str,
    analysis_summary: str,
    evidence_summary: str,
    allowed_urls: list[str],
    plan_hint: str,
    dimension_hints: list[str] | None = None,
    txt: str,
    section_id: str,
    min_paras: int,
    missing_chars: int,
    min_figures: int = 0,
) -> tuple[str, str]:
    system = (
        "You are a continuation writer for one section.\n"
        "Output NDJSON only. Each line is one JSON object representing paragraph/list/table/figure/reference blocks.\n"
        "Do not repeat prior content; only add incremental blocks that extend the current section.\n"
    )
    figure_contract = (
        "If you emit a figure block, the schema must be: "
        '{"section_id":...,"block_id":...,"type":"figure","kind":"flow|architecture|bar|line|pie|timeline|sequence|er","caption":string,"data":object}.\n'
        "Never output caption-only figure blocks. If you cannot provide valid kind+data, output no figure block.\n"
    )
    system += figure_contract
    if evidence_summary:
        system += "Use only the supplied evidence and avoid unsupported URLs.\n"

    escaped_urls = [str(u or "").strip() for u in allowed_urls if str(u or "").strip()]
    urls_block = "\n".join(f"- {_escape_prompt_text(u)}" for u in escaped_urls) if escaped_urls else "- (none)"

    user = (
        "<task>continue_section_draft</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return NDJSON only.\n"
        "- Keep section_id unchanged.\n"
        "- Only output incremental blocks; do not rewrite existing draft blocks.\n"
        "- Output reader-facing academic prose only; no meta commentary, writing advice, or process narration.\n"
        "- Do not restate sentences from analysis_summary or plan_hint.\n"
        "- Forbidden residue: should/must/recommendations, this section, this chapter, topic:, doc_type:, key points:, placeholder templates.\n"
        "- Forbidden placeholder examples: first define the research objective, describe the method path, explain inputs, outputs, and key parameters, construct the evidence chain from data source, metrics, and interpretation.\n"
        "</constraints>\n"
        f"<title>\n{_escape_prompt_text(title)}\n</title>\n"
        f"<section_title>\n{_escape_prompt_text(section)}\n</section_title>\n"
        f"<section_id>\n{_escape_prompt_text(section_id)}\n</section_id>\n"
    )
    if parent_section:
        user += f"<parent_section>\n{_escape_prompt_text(parent_section)}\n</parent_section>\n"
    if analysis_summary:
        user += f"<analysis_summary>\n{_escape_prompt_text(analysis_summary)}\n</analysis_summary>\n"
    else:
        user += f"<user_instruction>\n{_escape_prompt_text(instruction)}\n</user_instruction>\n"
    if plan_hint:
        user += f"<plan_hint>\n{_escape_prompt_text(plan_hint)}\n</plan_hint>\n"

    hints = [str(item).strip() for item in (dimension_hints or []) if str(item).strip()]
    if hints:
        hint_text = "\n".join(f"- {_escape_prompt_text(item)}" for item in hints[:8])
        user += f"<dimension_hints>\n{hint_text}\n</dimension_hints>\n"

    if evidence_summary:
        user += f"<evidence_summary>\n{_escape_prompt_text(evidence_summary)}\n</evidence_summary>\n"
    user += f"<allowed_urls>\n{urls_block}\n</allowed_urls>\n"
    user += f"<current_section_draft>\n{_escape_prompt_text(txt)}\n</current_section_draft>\n"

    target_lines = [
        f"Add at least {max(220, missing_chars)} chars and satisfy minimum {min_paras} paragraphs.",
        "Each paragraph must be semantically complete; do not leave truncated half-sentences.",
        "If still below target length, add NEW information by expanding one or more new dimensions",
        "(for example: policy impact, regional heterogeneity, boundary conditions, risk controls)",
        "instead of repeating previous claims.",
    ]
    if int(min_figures or 0) > 0:
        target_lines.append(
            f"If this section still needs figures, add up to {int(min_figures or 0)} valid figure block(s) using type=figure plus kind+caption+data; never emit caption-only figure blocks."
        )
    user += "<target>\n" + "\n".join(target_lines) + "\n</target>\nReturn NDJSON now."
    return system, user


def _continue_once(
    *,
    client,
    txt: str,
    section: str,
    section_id: str,
    system: str,
    user: str,
    out_queue: queue.Queue[dict],
    max_chars: int,
    missing_chars: int,
    stream_structured_blocks: Callable[..., str],
    predict_num_tokens: Callable[[int, int, bool], int],
    is_reference_section: Callable[[str], bool],
    section_timeout_s: Callable[[], float],
) -> str:
    deadline = time.time() + section_timeout_s()
    extra = stream_structured_blocks(
        client=client,
        system=system,
        user=user,
        out_queue=out_queue,
        section=section,
        section_id=section_id,
        is_reference=is_reference_section(section),
        num_predict=predict_num_tokens(max(220, missing_chars), max_chars, is_reference_section(section)),
        deadline=deadline,
    )
    if not extra:
        return txt
    return (str(txt or "").strip() + "\n\n" + extra).strip()


__all__ = [name for name in globals() if not name.startswith("__")]
