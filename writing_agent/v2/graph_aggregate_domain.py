"""Graph Aggregate Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

from typing import Callable

from writing_agent.llm import OllamaClient  # backward-compat for tests monkeypatching this symbol
from writing_agent.llm.factory import get_default_provider
from writing_agent.v2 import graph_aggregate_patch_domain, graph_aggregate_prompt_domain


def split_sentences(text: str) -> list[str]:
    return list(graph_aggregate_prompt_domain.split_sentences(text))


def extract_key_points(text: str, *, max_points: int = 3, max_chars: int = 320) -> list[str]:
    return list(graph_aggregate_prompt_domain.extract_key_points(text, max_points=max_points, max_chars=max_chars))


def extract_sections_from_text(text: str) -> dict[str, str]:
    return dict(graph_aggregate_prompt_domain.extract_sections_from_text(text))


def _escape_prompt_text(raw: object) -> str:
    return str(graph_aggregate_prompt_domain._escape_prompt_text(raw))


def _build_provider(*, model: str, timeout_s: float, route_key: str):
    return get_default_provider(model=model, timeout_s=timeout_s, route_key=route_key)


def build_aggregate_brief(
    title: str,
    instruction: str,
    sections: list[str],
    section_text: dict[str, str],
    merged_draft: str,
    *,
    section_level: Callable[[str], int],
    section_title: Callable[[str], str],
) -> str:
    return str(
        graph_aggregate_prompt_domain.build_aggregate_brief(
            title=title,
            instruction=instruction,
            sections=sections,
            section_text=section_text,
            merged_draft=merged_draft,
            section_level=section_level,
            section_title=section_title,
        )
    )

def _build_provider(*, model: str, timeout_s: float, route_key: str):
    return get_default_provider(model=model, timeout_s=timeout_s, route_key=route_key)



def extract_section_from_parsed(parsed, name: str) -> str:
    return str(graph_aggregate_patch_domain.extract_section_from_parsed(parsed, name))


def blocks_to_text(blocks) -> str:
    return str(graph_aggregate_patch_domain.blocks_to_text(blocks))


def extract_transitions(
    patch_text: str,
    sections: list[str],
    *,
    section_title: Callable[[str], str],
) -> dict[str, str]:
    return dict(graph_aggregate_patch_domain.extract_transitions(patch_text, sections, section_title=section_title))


def apply_section_updates(base_text: str, updates: dict[str, str], transitions: dict[str, str]) -> str:
    return str(graph_aggregate_patch_domain.apply_section_updates(base_text, updates, transitions))


def apply_aggregate_patch(
    base_text: str,
    patch_text: str,
    sections: list[str],
    *,
    section_title: Callable[[str], str],
) -> str:
    return str(
        graph_aggregate_patch_domain.apply_aggregate_patch(
            base_text,
            patch_text,
            sections,
            section_title=section_title,
        )
    )

def aggregate_fix_stream_iter_compressed(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    brief: str,
    sections: list[str],
    required_h2: list[str] | None,
    filter_disallowed_sections: Callable[[list[str]], list[str]],
    section_level: Callable[[str], int],
    section_title: Callable[[str], str],
):
    client = _build_provider(model=model, timeout_s=120.0, route_key="v2.aggregate.compressed")
    required = [h.strip() for h in (required_h2 or []) if h and h.strip()]
    if not required:
        required = ["Introduction", "Method", "Results", "Conclusion", "References"]
    required = filter_disallowed_sections(required)

    transitions = []
    h2_sections = [s for s in sections if section_level(s) <= 2]
    for i in range(len(h2_sections) - 1):
        frm = section_title(h2_sections[i]) or h2_sections[i]
        to = section_title(h2_sections[i + 1]) or h2_sections[i + 1]
        if frm and to:
            transitions.append(f"{frm} -> {to}")
    transition_hint = "; ".join(transitions) if transitions else "Introduction -> Method"

    system = (
        "You are an aggregation pass. Output plain text only.\n"
        "Only output two sections:\n"
        "1) ## Conclusion (compressed and polished)\n"
        "2) ## Transitions (one bridge sentence for each adjacent section pair).\n"
        f"Required section order: {'; '.join(required)}. Suggested transitions: {transition_hint}."
    )
    user = (
        "<task>aggregate_conclusion_and_transitions</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return plain text only.\n"
        "- Output only the required sections requested by system prompt.\n"
        "</constraints>\n"
        f"<title>\n{_escape_prompt_text(title)}\n</title>\n"
        f"<instruction>\n{_escape_prompt_text(instruction)}\n</instruction>\n"
        f"<compressed_input>\n{_escape_prompt_text(brief)}\n</compressed_input>\n"
        "Return output now."
    )
    for delta in client.chat_stream(system=system, user=user, temperature=0.2):
        yield delta


def aggregate_fix_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    draft: str,
    required_h2: list[str] | None,
    targets: dict | None,
    filter_disallowed_sections: Callable[[list[str]], list[str]],
    format_section_constraints: Callable[[list[str], dict | None], str],
    doc_body_len: Callable[[str], int],
) -> str:
    client = _build_provider(model=model, timeout_s=180.0, route_key="v2.aggregate.full")
    required = [h.strip() for h in (required_h2 or []) if h and h.strip()]
    if not required:
        required = ["Introduction", "Method", "Results", "Conclusion", "References"]
    required = filter_disallowed_sections(required)

    constraints = format_section_constraints(required, targets)
    draft_len = doc_body_len(draft)
    system = (
        "You are a report aggregation agent. Output plain text only.\n"
        "Keep heading structure and preserve original content whenever possible.\n"
        f"Required sections in order: {'; '.join(required)}.\n"
        f"Section constraints:\n{constraints}\n"
        f"Do not compress aggressively. Output length should be >= 85% of draft length ({draft_len}).\n"
        "Preserve [[TABLE:...]] and [[FIGURE:...]] markers with valid JSON payloads."
    )
    user = (
        "<task>aggregate_full_draft</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return plain text only.\n"
        "- Keep complete heading structure and preserve markers.\n"
        "</constraints>\n"
        f"<title>\n{_escape_prompt_text(title)}\n</title>\n"
        f"<instruction>\n{_escape_prompt_text(instruction)}\n</instruction>\n"
        f"<draft>\n{_escape_prompt_text(draft)}\n</draft>\n"
        "Return final revised draft."
    )

    buf: list[str] = []
    for delta in client.chat_stream(system=system, user=user, temperature=0.2):
        buf.append(delta)
    return "".join(buf).strip() or draft


def aggregate_fix_stream_iter(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    draft: str,
    required_h2: list[str] | None,
    targets: dict | None,
    filter_disallowed_sections: Callable[[list[str]], list[str]],
    format_section_constraints: Callable[[list[str], dict | None], str],
    doc_body_len: Callable[[str], int],
):
    client = _build_provider(model=model, timeout_s=180.0, route_key="v2.aggregate.full.iter")
    required = [h.strip() for h in (required_h2 or []) if h and h.strip()]
    if not required:
        required = ["Introduction", "Method", "Results", "Conclusion", "References"]
    required = filter_disallowed_sections(required)

    constraints = format_section_constraints(required, targets)
    draft_len = doc_body_len(draft)
    system = (
        "You are a report aggregation agent. Output plain text only.\n"
        f"Required sections in order: {'; '.join(required)}.\n"
        f"Section constraints:\n{constraints}\n"
        f"Output length should be >= 95% of draft length ({draft_len})."
    )
    user = (
        "<task>aggregate_full_draft</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return plain text only.\n"
        "- Keep complete heading structure and preserve markers.\n"
        "</constraints>\n"
        f"<title>\n{_escape_prompt_text(title)}\n</title>\n"
        f"<instruction>\n{_escape_prompt_text(instruction)}\n</instruction>\n"
        f"<draft>\n{_escape_prompt_text(draft)}\n</draft>\n"
        "Return revised draft."
    )

    for delta in client.chat_stream(system=system, user=user, temperature=0.2):
        yield delta


def repair_stream_iter(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    draft: str,
    problems: list[str],
    required_h2: list[str] | None,
    targets: dict | None,
    filter_disallowed_sections: Callable[[list[str]], list[str]],
    format_section_constraints: Callable[[list[str], dict | None], str],
    doc_body_len: Callable[[str], int],
):
    client = _build_provider(model=model, timeout_s=180.0, route_key="v2.aggregate.repair.iter")
    required = [h.strip() for h in (required_h2 or []) if h and h.strip()]
    if not required:
        required = ["Introduction", "Method", "Results", "Conclusion", "References"]
    required = filter_disallowed_sections(required)

    constraints = format_section_constraints(required, targets)
    draft_len = doc_body_len(draft)
    system = (
        "You are a repair pass for a report draft. Output plain text only.\n"
        f"Required sections in order: {'; '.join(required)}.\n"
        f"Section constraints:\n{constraints}\n"
        f"Output length should be >= 95% of draft length ({draft_len}).\n"
        "Preserve table/figure markers and avoid unsupported factual claims."
    )
    problem_lines = "\n".join(f"- {_escape_prompt_text(item)}" for item in problems) or "- no-problem-provided"
    user = (
        "<task>repair_draft</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return plain text only.\n"
        "- Resolve listed problems while preserving heading structure and markers.\n"
        "</constraints>\n"
        f"<title>\n{_escape_prompt_text(title)}\n</title>\n"
        f"<instruction>\n{_escape_prompt_text(instruction)}\n</instruction>\n"
        f"<problems>\n{problem_lines}\n</problems>\n"
        f"<draft>\n{_escape_prompt_text(draft)}\n</draft>\n"
        "Return repaired final draft."
    )

    for delta in client.chat_stream(system=system, user=user, temperature=0.2):
        yield delta


def repair_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    draft: str,
    problems: list[str],
    required_h2: list[str] | None,
    targets: dict | None,
    filter_disallowed_sections: Callable[[list[str]], list[str]],
    format_section_constraints: Callable[[list[str], dict | None], str],
    doc_body_len: Callable[[str], int],
) -> str:
    client = _build_provider(model=model, timeout_s=180.0, route_key="v2.aggregate.repair")
    required = [h.strip() for h in (required_h2 or []) if h and h.strip()]
    if not required:
        required = ["Introduction", "Method", "Results", "Conclusion", "References"]
    required = filter_disallowed_sections(required)

    constraints = format_section_constraints(required, targets)
    draft_len = doc_body_len(draft)
    system = (
        "You are a repair pass for a report draft. Output plain text only.\n"
        f"Required sections in order: {'; '.join(required)}.\n"
        f"Section constraints:\n{constraints}\n"
        f"Output length should be >= 85% of draft length ({draft_len}).\n"
        "Preserve table/figure markers and avoid unsupported factual claims."
    )
    problem_lines = "\n".join(f"- {_escape_prompt_text(item)}" for item in problems) or "- no-problem-provided"
    user = (
        "<task>repair_draft</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return plain text only.\n"
        "- Resolve listed problems while preserving heading structure and markers.\n"
        "</constraints>\n"
        f"<title>\n{_escape_prompt_text(title)}\n</title>\n"
        f"<instruction>\n{_escape_prompt_text(instruction)}\n</instruction>\n"
        f"<problems>\n{problem_lines}\n</problems>\n"
        f"<draft>\n{_escape_prompt_text(draft)}\n</draft>\n"
        "Return repaired final draft."
    )

    buf: list[str] = []
    for delta in client.chat_stream(system=system, user=user, temperature=0.2):
        buf.append(delta)
    return "".join(buf).strip() or draft
