"""Doc IR helpers: conversion, diff/ops, parsing, and migration."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


def _base():
    from writing_agent.v2 import doc_ir as base
    return base


# -- Conversion and tree-building --


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


# -- Diff, index, and operation helpers --


def myers_diff(a: List[str], b: List[str]) -> List[Tuple[str, int, int]]:
    n, m = len(a), len(b)
    max_d = n + m
    v = {1: 0}
    trace = []
    for d in range(max_d + 1):
        v2 = {}
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v.get(k - 1, 0) < v.get(k + 1, 0)):
                x = v.get(k + 1, 0)
            else:
                x = v.get(k - 1, 0) + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            v2[k] = x
            if x >= n and y >= m:
                trace.append(v2)
                return _backtrack(trace, a, b)
        trace.append(v2)
        v = v2
    return []


def _backtrack(trace: List[Dict[int, int]], a: List[str], b: List[str]) -> List[Tuple[str, int, int]]:
    x = len(a)
    y = len(b)
    edits: List[Tuple[str, int, int]] = []
    for d in range(len(trace) - 1, -1, -1):
        v = trace[d]
        k = x - y
        if d == 0:
            break
        if k == -d or (k != d and v.get(k - 1, 0) < v.get(k + 1, 0)):
            k_prev = k + 1
            x_prev = v.get(k_prev, 0)
            op = "insert"
        else:
            k_prev = k - 1
            x_prev = v.get(k_prev, 0) + 1
            op = "delete"
        y_prev = x_prev - k_prev
        while x > x_prev and y > y_prev:
            edits.append(("equal", x - 1, y - 1))
            x -= 1
            y -= 1
        edits.append((op, x_prev, y_prev))
        x, y = x_prev, y_prev
    edits.reverse()
    return edits


def diff_blocks(old, new) -> List[Tuple[str, int, int]]:
    base = _base()
    old_hashes = [block.content_hash() for block in base.iter_blocks(old)]
    new_hashes = [block.content_hash() for block in base.iter_blocks(new)]
    return myers_diff(old_hashes, new_hashes)


def build_inverted_index(doc) -> Dict[str, List[str]]:
    base = _base()
    index: Dict[str, List[str]] = {}
    for block in base.iter_blocks(doc):
        text = base.render_block_text(block).strip()
        if not text:
            continue
        for token in base._WORD_RE.findall(text):
            token = token.lower()
            index.setdefault(token, []).append(base.get_block_id(block))
    return index


def validate_doc_ir(doc) -> List[str]:
    problems: List[str] = []
    if not doc.title or not doc.title.strip():
        problems.append("missing title")
    if not doc.sections:
        problems.append("missing sections")
    return problems


def apply_ops(doc, ops, *, atomic: bool = False):
    base = _base()
    target = doc.model_copy(deep=True) if atomic else doc
    if not ops:
        return target
    idx = base.build_index(target)
    for op in ops:
        if not _apply_single_op(target, idx, op):
            if atomic:
                return doc
            continue
    return target


def _delete_block_in_section(sec, block_id: str) -> bool:
    base = _base()
    for i, block in enumerate(sec.blocks):
        if base.get_block_id(block) == block_id:
            sec.blocks.pop(i)
            return True
    for child in sec.children:
        if _delete_block_in_section(child, block_id):
            return True
    return False


def _apply_single_op(doc, idx, op) -> bool:
    base = _base()
    if op.op == "insert":
        sec = idx.section_by_id.get(op.parent_id or "")
        if not sec:
            return False
        block = base.block_from_dict(op.payload or {})
        pos = int(op.index or len(sec.blocks))
        sec.blocks.insert(max(0, min(len(sec.blocks), pos)), block)
        bid = base.get_block_id(block)
        if bid:
            idx.block_by_id[bid] = block
            idx.block_parent_by_id[bid] = sec.id
        return True
    if op.op == "delete":
        sec_id = idx.block_parent_by_id.get(op.target_id)
        if not sec_id:
            return False
        sec = idx.section_by_id.get(sec_id)
        if not sec:
            return False
        for i, block in enumerate(sec.blocks):
            if base.get_block_id(block) == op.target_id:
                sec.blocks.pop(i)
                idx.block_by_id.pop(op.target_id, None)
                idx.block_parent_by_id.pop(op.target_id, None)
                return True
        return False
    if op.op == "update":
        block = idx.block_by_id.get(op.target_id)
        if not block or not op.payload:
            return False
        for key, value in op.payload.items():
            if hasattr(block, key):
                setattr(block, key, value)
        return True
    if op.op == "move":
        sec_id = idx.block_parent_by_id.get(op.target_id)
        if not sec_id:
            return False
        src_sec = idx.section_by_id.get(sec_id)
        if not src_sec:
            return False
        moving = None
        for i, block in enumerate(src_sec.blocks):
            if base.get_block_id(block) == op.target_id:
                moving = src_sec.blocks.pop(i)
                break
        if moving is None:
            return False
        dst_id = op.parent_id or sec_id
        dst_sec = idx.section_by_id.get(dst_id)
        if not dst_sec:
            return False
        pos = int(op.index or len(dst_sec.blocks))
        dst_sec.blocks.insert(max(0, min(len(dst_sec.blocks), pos)), moving)
        idx.block_parent_by_id[op.target_id] = dst_sec.id
        return True
    return False


# -- Parsing, marker, and migration helpers --


def _block_from_docblock(block):
    base = _base()
    if block.type == "heading":
        return base.HeadingBlock(level=int(block.level or 1), text=block.text or "")
    if block.type == "paragraph":
        return base.ParagraphBlock(text=block.text or "")
    if block.type == "table":
        return base.TableBlock(table=block.table or {})
    if block.type == "figure":
        return base.FigureBlock(figure=block.figure or {})
    if block.type == "list":
        items, ordered = _extract_list_items_from_text(block.text or "")
        return base.ListBlock(items=items, ordered=ordered)
    return base.ParagraphBlock(text=block.text or "")


def _docblock_from_block(block):
    base = _base()
    if isinstance(block, base.HeadingBlock):
        text = block.text or _runs_to_text(getattr(block, "runs", []))
        return base.DocBlock(type="heading", level=block.level, text=text)
    if isinstance(block, base.ParagraphBlock):
        text = block.text or _runs_to_text(getattr(block, "runs", []))
        return base.DocBlock(type="paragraph", text=text)
    if isinstance(block, base.ListBlock):
        items = block.items if isinstance(block.items, list) else []
        cleaned = [str(it).strip() for it in items if str(it).strip()]
        if block.ordered:
            text = "\n".join([f"{i + 1}. {item}" for i, item in enumerate(cleaned)])
        else:
            text = "\n".join([f"\u2022 {item}" for item in cleaned])
        return base.DocBlock(type="paragraph", text=text)
    if isinstance(block, base.TableBlock):
        return base.DocBlock(type="table", table=block.table)
    if isinstance(block, base.FigureBlock):
        return base.DocBlock(type="figure", figure=block.figure)
    return base.DocBlock(type="paragraph", text=getattr(block, "text", ""))


def block_from_dict(data: dict):
    base = _base()
    if not isinstance(data, dict):
        return base.ParagraphBlock(text="")
    t = str(data.get("type") or "paragraph")
    block_id = str(data.get("id") or "").strip()
    id_kw = {"id": block_id} if block_id else {}
    style = data.get("style")
    style_kw = {"style": style} if isinstance(style, dict) else {}
    runs = data.get("runs")
    runs_kw = {"runs": runs} if isinstance(runs, list) else {}
    if t == "heading":
        return base.HeadingBlock(level=int(data.get("level") or 1), text=str(data.get("text") or ""), **id_kw, **style_kw, **runs_kw)
    if t == "paragraph":
        return base.ParagraphBlock(text=str(data.get("text") or ""), **id_kw, **style_kw, **runs_kw)
    if t == "list":
        return base.ListBlock(items=[str(x) for x in (data.get("items") or [])], ordered=bool(data.get("ordered")), **id_kw, **style_kw)
    if t == "table":
        return base.TableBlock(table=dict(data.get("table") or {}), **id_kw, **style_kw)
    if t == "figure":
        return base.FigureBlock(figure=dict(data.get("figure") or {}), **id_kw, **style_kw)
    return base.ParagraphBlock(text=str(data.get("text") or ""), **id_kw, **style_kw)


def explode_markers(blocks):
    base = _base()
    out: list = []
    for block in blocks:
        if block.type != "paragraph" or not (block.text or "").strip():
            out.append(block)
            continue
        txt = block.text or ""
        pos = 0
        for match in base._MARKER_RE.finditer(txt):
            before = txt[pos:match.start()].strip()
            if before:
                out.append(base.DocBlock(type="paragraph", text=before))
            kind = (match.group(1) or "").lower()
            raw = (match.group(2) or "").strip()
            data = _safe_json_loads(raw)
            if kind == "table":
                out.append(base.DocBlock(type="table", table=data if isinstance(data, dict) else {"raw": raw}))
            else:
                out.append(base.DocBlock(type="figure", figure=data if isinstance(data, dict) else {"raw": raw}))
            pos = match.end()
        tail = txt[pos:].strip()
        if tail:
            out.append(base.DocBlock(type="paragraph", text=tail))
    return out


def _safe_json_loads(raw: str) -> Optional[dict]:
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _extract_list_items_from_text(text: str) -> Tuple[List[str], bool]:
    if not text:
        return [], False
    items: List[str] = []
    total = 0
    num_hits = 0
    num_re = re.compile(r"^(\d+)[\.\)]\s+")
    for line in str(text).replace("\r", "").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        total += 1
        if stripped.startswith("\u2022 "):
            items.append(stripped[2:].strip())
            continue
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
            continue
        match = num_re.match(stripped)
        if match:
            num_hits += 1
            items.append(stripped[match.end():].strip())
        else:
            items.append(stripped)
    ordered = total > 0 and num_hits == total
    return items, ordered


def _runs_to_text(runs: Iterable[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for run in runs or []:
        if not isinstance(run, dict):
            continue
        txt = str(run.get("text") or "")
        if txt:
            parts.append(txt)
    return "".join(parts).strip()


def _looks_like_v1_dict(data: dict) -> bool:
    sections = data.get("sections")
    if not isinstance(sections, list):
        return False
    if not sections:
        return False
    return all(isinstance(section, dict) and "children" not in section for section in sections)


def migrate_v1_to_v2(data: dict):
    base = _base()
    title = str(data.get("title") or base.DEFAULT_TITLE).strip() or base.DEFAULT_TITLE
    sections = data.get("sections") or []
    blocks: list = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        level = int(sec.get("level") or 1)
        sec_title = str(sec.get("title") or "").strip() or base.DEFAULT_SECTION_TITLE
        blocks.append(base.DocBlock(type="heading", level=level, text=sec_title))
        for raw in sec.get("blocks") or []:
            if isinstance(raw, dict):
                blocks.append(_docblock_from_block(block_from_dict(raw)))
    blocks = explode_markers(blocks)
    return base.build_tree_from_blocks(blocks, title)


def migrate_v2_to_v1(doc) -> dict:
    flat_sections: list[dict] = []

    def walk(sec):
        flat_sections.append({"title": sec.title, "level": sec.level, "blocks": [block.model_dump() for block in sec.blocks]})
        for child in sec.children:
            walk(child)

    for section in doc.sections:
        walk(section)
    return {"title": doc.title, "sections": flat_sections}


__all__ = [name for name in globals() if not name.startswith("__")]
