"""Conversion and tree-building helpers for doc IR."""

from __future__ import annotations

from typing import Iterator, Optional


def _base():
    from writing_agent.v2 import doc_ir as base
    return base


def build_tree_from_blocks(blocks, title: str):
    base = _base()
    root_sections: list = []
    stack: list[tuple[int, object]] = []
    orphan_blocks: list = []
    doc_title = (title or "").strip() or base.DEFAULT_TITLE

    for block in blocks:
        if block.type == "heading":
            level = max(1, min(6, int(block.level or 1)))
            node = base.SectionNode(title=(block.text or "").strip() or base.DEFAULT_SECTION_TITLE, level=level)
            if orphan_blocks and not stack:
                implicit = base.SectionNode(title=doc_title, level=1, blocks=orphan_blocks)
                root_sections.append(implicit)
                stack.append((1, implicit))
                orphan_blocks = []
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].children.append(node)
            else:
                root_sections.append(node)
            stack.append((level, node))
            continue

        ir_block = base._block_from_docblock(block)
        if stack:
            stack[-1][1].blocks.append(ir_block)
        else:
            orphan_blocks.append(ir_block)

    if orphan_blocks and not root_sections:
        root_sections.append(base.SectionNode(title=doc_title, level=1, blocks=orphan_blocks))
    return base.DocIR(title=doc_title, sections=root_sections)


def build_index(doc):
    base = _base()
    idx = base.DocIRIndex()

    def walk(sec, parent_id):
        idx.section_by_id[sec.id] = sec
        idx.parent_by_id[sec.id] = parent_id
        idx.section_order.append(sec.id)
        for block in sec.blocks:
            bid = base.get_block_id(block)
            idx.block_by_id[bid] = block
            idx.block_parent_by_id[bid] = sec.id
        for child in sec.children:
            walk(child, sec.id)

    for section in doc.sections:
        walk(section, None)
    return idx


def iter_blocks(doc) -> Iterator:
    stack = list(reversed(doc.sections))
    while stack:
        sec = stack.pop()
        for block in sec.blocks:
            yield block
        if sec.children:
            stack.extend(reversed(sec.children))


def paged_blocks(doc, page_size: int) -> Iterator[list]:
    buf: list = []
    for block in iter_blocks(doc):
        buf.append(block)
        if len(buf) >= page_size:
            yield buf
            buf = []
    if buf:
        yield buf


def from_text(text: str):
    base = _base()
    parsed = base.parse_report_text(text or "")
    return from_parsed(parsed)


def from_parsed(parsed):
    base = _base()
    blocks = base.explode_markers(parsed.blocks or [])
    return build_tree_from_blocks(blocks, parsed.title or base.DEFAULT_TITLE)


def to_parsed(doc):
    base = _base()
    blocks: list = []

    def walk(sec):
        blocks.append(base.DocBlock(type="heading", level=sec.level, text=sec.title))
        for block in sec.blocks:
            blocks.append(base._docblock_from_block(block))
        for child in sec.children:
            walk(child)

    for section in doc.sections:
        walk(section)
    if not any(block.type == "heading" and (block.level or 0) == 1 for block in blocks):
        blocks.insert(0, base.DocBlock(type="heading", level=1, text=doc.title or base.DEFAULT_TITLE))
    return base.ParsedDoc(title=doc.title or base.DEFAULT_TITLE, blocks=blocks)


def to_text(doc) -> str:
    base = _base()
    parsed = to_parsed(doc)
    out: list[str] = []
    for block in parsed.blocks:
        if block.type == "heading":
            level = block.level or 1
            txt = (block.text or "").strip()
            if txt:
                out.append(f"{'#' * level} {txt}")
        elif block.type == "paragraph":
            txt = (block.text or "").strip()
            if txt:
                out.append(txt)
        elif block.type == "table":
            out.append(f"[[TABLE:{base._safe_json(block.table or {})}]]")
        elif block.type == "figure":
            out.append(f"[[FIGURE:{base._safe_json(block.figure or {})}]]")
        elif block.type == "list":
            items = block.items if isinstance(block.items, list) else []
            cleaned = [str(it).strip() for it in items if str(it).strip()]
            if block.ordered:
                for i, txt in enumerate(cleaned):
                    out.append(f"{i + 1}. {txt}")
            else:
                for txt in cleaned:
                    out.append(f"\u2022 {txt}")
    return "\n\n".join([s for s in out if s]).strip()


def to_dict(doc) -> dict:
    return doc.model_dump()


def from_dict(data: dict | None):
    base = _base()
    if not isinstance(data, dict):
        return base.DocIR()
    if base._looks_like_v1_dict(data):
        return base.migrate_v1_to_v2(data)
    return base.DocIR.model_validate(data)


def get_block_id(block) -> str:
    return getattr(block, "id", "")


def render_block_text(block, cache: Optional[object] = None) -> str:
    base = _base()
    key = block.content_hash()
    if cache:
        cached = cache.get(key)
        if cached is not None:
            return cached
    if isinstance(block, base.ParagraphBlock):
        out = block.text.strip() if block.text else base._runs_to_text(getattr(block, "runs", []))
    elif isinstance(block, base.HeadingBlock):
        out = block.text.strip() if block.text else base._runs_to_text(getattr(block, "runs", []))
    elif isinstance(block, base.ListBlock):
        items = [str(it).strip() for it in (block.items or []) if str(it).strip()]
        if block.ordered:
            out = "\n".join([f"{i + 1}. {item}" for i, item in enumerate(items)])
        else:
            out = "\n".join([f"\u2022 {item}" for item in items])
    elif isinstance(block, base.TableBlock):
        out = f"[[TABLE:{base._safe_json(block.table)}]]"
    elif isinstance(block, base.FigureBlock):
        out = f"[[FIGURE:{base._safe_json(block.figure)}]]"
    else:
        out = ""
    if cache:
        cache.set(key, out)
    return out


__all__ = [name for name in globals() if not name.startswith("__")]
