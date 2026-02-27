"""Graph Aggregate Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from writing_agent.llm import OllamaClient
from writing_agent.v2.doc_format import DocBlock, ParsedDoc, parse_report_text


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[。！？!?])\s*", text)
    return [p for p in parts if p and p.strip()]


def extract_key_points(text: str, *, max_points: int = 3, max_chars: int = 320) -> list[str]:
    src = (text or "").replace("\r", "")
    src = re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", src, flags=re.IGNORECASE)
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", src) if p.strip()]
    points: list[str] = []
    total = 0
    for para in paragraphs:
        for sent in split_sentences(para):
            sentence = sent.strip()
            if not sentence:
                continue
            if len(sentence) > 120:
                sentence = sentence[:120] + "..."
            if total + len(sentence) > max_chars:
                return points
            points.append(sentence)
            total += len(sentence)
            if len(points) >= max_points:
                return points
    return points


def extract_sections_from_text(text: str) -> dict[str, str]:
    src = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", src))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        name = (match.group(1) or "").strip()
        start = match.end()
        if start < len(src) and src[start] == "\n":
            start += 1
        end = matches[i + 1].start() if i + 1 < len(matches) else len(src)
        sections[name] = src[start:end].strip()
    return sections


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
    focus_map = extract_sections_from_text(merged_draft)
    brief_lines = [
        f"标题：{title}",
        f"用户要求：{instruction}",
        "",
        "【结论原文】",
        (focus_map.get("结论") or section_text.get("结论") or "").strip(),
        "",
        "【各章节关键要点】",
    ]
    for sec in sections:
        if section_level(sec) > 2:
            continue
        content = (section_text.get(sec) or "").strip()
        points = extract_key_points(content)
        if not points:
            continue
        brief_lines.append(f"- {section_title(sec) or sec}：")
        for point in points:
            brief_lines.append(f"  - {point}")
    return "\n".join([line for line in brief_lines if line is not None]).strip()


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
    client = OllamaClient(base_url=base_url, model=model, timeout_s=120.0)
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
        f"title: {title}\n"
        f"instruction: {instruction}\n\n"
        f"compressed input:\n{brief}\n\n"
        "Output now."
    )
    for delta in client.chat_stream(system=system, user=user, temperature=0.2):
        yield delta


def extract_section_from_parsed(parsed: ParsedDoc, name: str) -> str:
    cur = None
    buf: list[DocBlock] = []
    for block in parsed.blocks:
        if block.type == "heading" and int(block.level or 0) == 2:
            cur = (block.text or "").strip()
            continue
        if cur == name:
            buf.append(block)
    if not buf:
        return ""
    return blocks_to_text(buf)


def blocks_to_text(blocks: list[DocBlock]) -> str:
    out: list[str] = []
    for block in blocks:
        if block.type == "paragraph":
            text = (block.text or "").strip()
            if text:
                out.append(text)
        elif block.type == "table":
            out.append("[[TABLE:{}]]".format(json.dumps(block.table or {}, ensure_ascii=False)))
        elif block.type == "figure":
            out.append("[[FIGURE:{}]]".format(json.dumps(block.figure or {}, ensure_ascii=False)))
    return "\n\n".join(out).strip()


def extract_transitions(
    patch_text: str,
    sections: list[str],
    *,
    section_title: Callable[[str], str],
) -> dict[str, str]:
    transitions: dict[str, str] = {}
    if not patch_text:
        return transitions
    allowed = {section_title(section) or section for section in sections if section}
    for line in patch_text.splitlines():
        m = re.match(r"^\s*[-*]?\s*([^>]+?)\s*->\s*([^:：]+?)[:：]\s*(.+)$", line)
        if not m:
            continue
        frm = m.group(1).strip()
        to = m.group(2).strip()
        text = m.group(3).strip()
        if not text or frm not in allowed or to not in allowed:
            continue
        transitions[frm] = text
    return transitions


def apply_section_updates(base_text: str, updates: dict[str, str], transitions: dict[str, str]) -> str:
    src = (base_text or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", src))
    if not matches:
        return base_text
    out: list[str] = []
    cursor = 0
    for i, match in enumerate(matches):
        name = (match.group(1) or "").strip()
        content_start = match.end()
        if content_start < len(src) and src[content_start] == "\n":
            content_start += 1
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(src)
        out.append(src[cursor:content_start])
        body = src[content_start:content_end]
        body_text = body.strip()
        if name in updates:
            body_text = updates[name].strip()
        if name in transitions:
            trans = transitions[name].strip()
            if trans:
                body_text = (body_text + "\n\n" + trans).strip() if body_text else trans
        out.append(body_text + ("\n\n" if body_text else ""))
        cursor = content_end
    out.append(src[cursor:])
    return "".join(out).strip() + "\n"


def apply_aggregate_patch(
    base_text: str,
    patch_text: str,
    sections: list[str],
    *,
    section_title: Callable[[str], str],
) -> str:
    if not patch_text.strip():
        return base_text
    parsed = parse_report_text(patch_text)
    conclusion_text = extract_section_from_parsed(parsed, "结论")
    transitions = extract_transitions(patch_text, sections, section_title=section_title)
    updates: dict[str, str] = {}
    if conclusion_text:
        updates["结论"] = conclusion_text
    if not updates and not transitions:
        return base_text
    return apply_section_updates(base_text, updates, transitions)


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
    client = OllamaClient(base_url=base_url, model=model, timeout_s=180.0)
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
        f"title: {title}\n"
        f"instruction: {instruction}\n\n"
        f"draft:\n{draft}\n\n"
        "Return final revised draft now."
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
    client = OllamaClient(base_url=base_url, model=model, timeout_s=180.0)
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
        f"title: {title}\n"
        f"instruction: {instruction}\n\n"
        f"draft:\n{draft}\n\n"
        "Return revised draft now."
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
    client = OllamaClient(base_url=base_url, model=model, timeout_s=180.0)
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
    user = (
        f"title: {title}\n"
        f"instruction: {instruction}\n\n"
        f"problems:\n- " + "\n- ".join(problems) + "\n\n"
        f"draft:\n{draft}\n\n"
        "Return repaired final draft now."
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
    client = OllamaClient(base_url=base_url, model=model, timeout_s=180.0)
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
    user = (
        f"title: {title}\n"
        f"instruction: {instruction}\n\n"
        f"problems:\n- " + "\n- ".join(problems) + "\n\n"
        f"draft:\n{draft}\n\n"
        "Return repaired final draft now."
    )

    buf: list[str] = []
    for delta in client.chat_stream(system=system, user=user, temperature=0.2):
        buf.append(delta)
    return "".join(buf).strip() or draft
