"""Parsing, marker, and migration helpers for doc IR."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _base():
    from writing_agent.v2 import doc_ir as base
    return base


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
