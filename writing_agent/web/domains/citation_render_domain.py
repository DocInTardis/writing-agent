"""Citation Render Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import re

from writing_agent.agents.citations import CitationAgent
from writing_agent.models import Citation, CitationStyle
from writing_agent.v2.doc_ir import from_dict as doc_ir_from_dict
from writing_agent.v2.doc_ir import to_dict as doc_ir_to_dict

_CITATION_MARK_RE = re.compile(r"\[@([a-zA-Z0-9_-]+)\]")
_REFERENCE_HEADING_RE = re.compile(
    r"^(#{1,3})\s*(?:参考文献|参考资料|references?|bibliography)\s*$",
    re.IGNORECASE,
)


def insert_reference_section(text: str, ref_lines: list[str]) -> str:
    if not ref_lines:
        return text
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    heading_idx = None
    for idx, line in enumerate(lines):
        if _REFERENCE_HEADING_RE.match(line.strip()):
            heading_idx = idx
            break
    if heading_idx is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("## 参考文献")
        lines.append("")
        lines.extend(ref_lines)
        return "\n".join(lines).strip() + "\n"
    existing_nums: set[int] = set()
    for i in range(heading_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        if re.match(r"^#{1,3}\s+", line):
            break
        m = re.match(r"^\[(\d+)\]\s*", line)
        if m:
            try:
                existing_nums.add(int(m.group(1)))
            except Exception:
                pass
    to_add: list[str] = []
    for line in ref_lines:
        m = re.match(r"^\[(\d+)\]\s*", line)
        if m:
            try:
                if int(m.group(1)) in existing_nums:
                    continue
            except Exception:
                pass
        to_add.append(line)
    if not to_add:
        return text
    insert_idx = heading_idx + 1
    for i in range(heading_idx + 1, len(lines)):
        if re.match(r"^#{1,3}\s+", lines[i].strip()):
            insert_idx = i
            break
        insert_idx = i + 1
    if insert_idx > 0 and lines[insert_idx - 1].strip():
        to_add = [""] + to_add
    lines[insert_idx:insert_idx] = to_add
    return "\n".join(lines)


def apply_citations_for_export(text: str, citations: dict[str, Citation], style: CitationStyle) -> str:
    if not text:
        return text
    key_to_num: dict[str, int] = {}
    ordered_keys: list[str] = []

    def _assign_key(key: str) -> int:
        if key not in key_to_num:
            key_to_num[key] = len(key_to_num) + 1
            ordered_keys.append(key)
        return key_to_num[key]

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        num = _assign_key(key)
        return f"[{num}]"

    replaced = _CITATION_MARK_RE.sub(_replace, text)
    if not ordered_keys and citations:
        for key in citations.keys():
            _assign_key(key)
    if not ordered_keys:
        return replaced
    citer = CitationAgent()
    ref_lines: list[str] = []
    for key in ordered_keys:
        cite = citations.get(key)
        if cite:
            ref = citer.format_reference(cite, style)
        else:
            ref = f"{key}(citation details not found)"
        ref_lines.append(f"[{key_to_num[key]}] {ref}")
    return insert_reference_section(replaced, ref_lines)


def apply_citations_to_doc_ir(doc_ir, citations: dict[str, Citation], style: CitationStyle):
    if not doc_ir or not citations:
        return doc_ir
    try:
        data = doc_ir_to_dict(doc_ir)
    except Exception:
        return doc_ir
    key_to_num: dict[str, int] = {}
    ordered_keys: list[str] = []

    def _assign_key(key: str) -> int:
        if key not in key_to_num:
            key_to_num[key] = len(key_to_num) + 1
            ordered_keys.append(key)
        return key_to_num[key]

    def _replace_text(text: str) -> str:
        if not text:
            return text
        return _CITATION_MARK_RE.sub(lambda m: f"[{_assign_key(m.group(1))}]", text)

    def _replace_caption(container: dict, field: str) -> None:
        if not isinstance(container, dict):
            return
        val = container.get(field)
        if isinstance(val, str) and val:
            container[field] = _replace_text(val)

    def _process_blocks(blocks: list[dict]) -> None:
        for block in blocks:
            if not isinstance(block, dict):
                continue
            t = str(block.get("type") or "").lower()
            if t in {"paragraph", "text", "p"}:
                block["text"] = _replace_text(str(block.get("text") or ""))
                continue
            if t == "list":
                items = block.get("items")
                if isinstance(items, list):
                    block["items"] = [_replace_text(str(i)) for i in items]
                elif isinstance(block.get("text"), str):
                    block["text"] = _replace_text(str(block.get("text") or ""))
                continue
            if t == "table":
                table = block.get("table") or block.get("data")
                if isinstance(table, dict):
                    _replace_caption(table, "caption")
                continue
            if t == "figure":
                fig = block.get("figure") or block.get("data")
                if isinstance(fig, dict):
                    _replace_caption(fig, "caption")
                continue

    def _walk_sections(sections: list[dict]) -> None:
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            blocks = sec.get("blocks")
            if isinstance(blocks, list):
                _process_blocks(blocks)
            children = sec.get("children")
            if isinstance(children, list):
                _walk_sections(children)

    sections = data.get("sections")
    if isinstance(sections, list):
        _walk_sections(sections)
    if not ordered_keys and citations:
        for key in citations.keys():
            _assign_key(key)
    if not ordered_keys:
        return doc_ir_from_dict(data)
    citer = CitationAgent()
    ref_lines: list[str] = []
    for key in ordered_keys:
        cite = citations.get(key)
        if cite:
            ref = citer.format_reference(cite, style)
        else:
            ref = f"{key}(citation details not found)"
        ref_lines.append(f"[{key_to_num[key]}] {ref}")

    def _find_reference_section(sections: list[dict]) -> dict | None:
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            title = str(sec.get("title") or "").strip()
            if title and re.search(r"(参考文献|参考资料|references?)", title, re.I):
                return sec
            children = sec.get("children")
            if isinstance(children, list):
                found = _find_reference_section(children)
                if found:
                    return found
        return None

    ref_section = None
    if isinstance(sections, list):
        ref_section = _find_reference_section(sections)
        if ref_section is None:
            ref_section = {"title": "参考文献", "level": 2, "blocks": [], "children": []}
            sections.append(ref_section)
    if ref_section is not None:
        ref_section["blocks"] = [{"type": "paragraph", "text": line} for line in ref_lines]
    return doc_ir_from_dict(data)

