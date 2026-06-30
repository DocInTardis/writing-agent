"""Section continuation prompt helpers."""

from __future__ import annotations

import queue
import time
from collections.abc import Callable

from writing_agent.v2 import graph_section_continue_helpers_domain as helpers_domain

_escape_prompt_text = helpers_domain._escape_prompt_text


def _section_originality_profile(section_title: str) -> str:
    title = str(section_title or "").strip().lower()
    if any(token in title for token in ["摘要", "abstract"]):
        return "abstract"
    if any(token in title for token in ["引言", "绪论", "introduction", "background"]):
        return "introduction"
    if any(token in title for token in ["方法", "method", "methodology", "数据来源", "research design", "materials"]):
        return "method"
    if any(token in title for token in ["结果", "discussion", "讨论", "分析", "results", "findings"]):
        return "results"
    if any(token in title for token in ["结论", "启示", "conclusion", "implication", "recommendation"]):
        return "conclusion"
    return "general"


def _build_continue_originality_guidance(*, section: str, has_evidence_summary: bool, has_current_draft: bool) -> list[str]:
    title = str(section or "").strip().lower()
    profile = _section_originality_profile(section)
    lines = [
        "Add new substance instead of rephrasing the current draft with the same sentence skeleton.",
        "Do not follow source snippets in their original sentence order; convert them into your own claim-evidence structure.",
        "Prefer concrete actors, variables, process details, observed differences, and boundary conditions over generic recap sentences.",
        "Vary paragraph openings and punctuation rhythm when extending the section.",
    ]
    if profile == "introduction":
        lines.append("For introduction sections, continue by sharpening the research gap, object, or scope instead of adding another broad background paragraph.")
    elif profile == "method":
        lines.append("For method sections, extend with operational details such as sample boundary, variable definition, workflow step, or parameter choice.")
    elif profile == "results":
        lines.append("For results or discussion sections, extend with a new comparison, mechanism, anomaly, or boundary condition rather than a generic summary.")
    elif profile == "conclusion":
        lines.append("For conclusion sections, add implication or limitation details instead of repeating earlier findings in the same wording.")
    elif profile == "abstract":
        lines.append("For abstract sections, extend only with dense problem-method-result-implication content; avoid bridge sentences and padding.")
    if has_evidence_summary:
        lines.append("When evidence_summary is present, synthesize across multiple facts instead of serially paraphrasing a single source fragment.")
    if has_current_draft:
        lines.append("Extend the draft by opening a new analytical angle rather than repeating the previous paragraph's transition phrase.")
    if any(token in title for token in ["结论", "discussion", "讨论", "分析", "results", "result"]):
        lines.append("For interpretation-heavy sections, end additions with implication, comparison, or limitation instead of a generic wrap-up.")
    return lines[:6]


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
    originality_guidance = _build_continue_originality_guidance(
        section=section,
        has_evidence_summary=bool(str(evidence_summary or "").strip()),
        has_current_draft=bool(str(txt or "").strip()),
    )

    user = (
        "<task>continue_section_draft</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return NDJSON only.\n"
        "- Keep section_id unchanged.\n"
        "- Only output incremental blocks; do not rewrite existing draft blocks.\n"
        "- Output reader-facing academic prose only; no meta commentary, writing advice, or process narration.\n"
        "- Do not restate sentences from analysis_summary or plan_hint.\n"
        "- Each added paragraph must contribute a concrete claim, observation, comparison, mechanism, or limitation.\n"
        "- Prefer concrete evidence, actors, variables, process details, or boundary conditions over generic summary language.\n"
        "- Avoid stock transitions and repeated openings such as 'This study...', 'First...', 'Second...', or 'In conclusion...' unless they add unique meaning.\n"
        "- Do not inherit retrieved/source sentence order when extending the draft; reorganize evidence around your own analytical sequence.\n"
        "- Do not continue with the same opener, discourse marker, or clause rhythm used in the previous paragraph.\n"
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
    if originality_guidance:
        user += "<originality_guidance>\n" + "\n".join(f"- {_escape_prompt_text(item)}" for item in originality_guidance) + "\n</originality_guidance>\n"

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
