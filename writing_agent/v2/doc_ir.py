"""Doc Ir module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any, Dict, Iterable, Iterator, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from writing_agent.v2.doc_format import DocBlock, ParsedDoc, parse_report_text


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        return "{}"


DEFAULT_TITLE = "\u81ea\u52a8\u751f\u6210\u6587\u6863"
DEFAULT_SECTION_TITLE = "\u7ae0\u8282"


class BlockBase(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: str
    style: Dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        data = self.model_dump(exclude={"id"})
        return _hash_text(_safe_json(data))


class HeadingBlock(BlockBase):
    type: Literal["heading"] = "heading"
    level: int = 1
    text: str = ""
    runs: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("level")
    @classmethod
    def _valid_level(cls, v: int) -> int:
        if v < 1 or v > 6:
            return 1
        return v


class ParagraphBlock(BlockBase):
    type: Literal["paragraph"] = "paragraph"
    text: str = ""
    runs: List[Dict[str, Any]] = Field(default_factory=list)


class ListBlock(BlockBase):
    type: Literal["list"] = "list"
    items: List[str] = Field(default_factory=list)
    ordered: bool = False


class TableBlock(BlockBase):
    type: Literal["table"] = "table"
    table: Dict[str, Any] = Field(default_factory=dict)


class FigureBlock(BlockBase):
    type: Literal["figure"] = "figure"
    figure: Dict[str, Any] = Field(default_factory=dict)


DocIRBlock = Union[HeadingBlock, ParagraphBlock, ListBlock, TableBlock, FigureBlock]


class SectionNode(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    title: str
    level: int = 1
    style: Dict[str, Any] = Field(default_factory=dict)
    blocks: List[DocIRBlock] = Field(default_factory=list)
    children: List["SectionNode"] = Field(default_factory=list)

    @field_validator("level")
    @classmethod
    def _valid_level(cls, v: int) -> int:
        if v < 1:
            return 1
        if v > 6:
            return 6
        return v

    @model_validator(mode="before")
    @classmethod
    def _coerce_blocks(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        raw_blocks = values.get("blocks") or []
        blocks: List[DocIRBlock] = []
        for b in raw_blocks:
            if isinstance(b, BaseModel):
                blocks.append(b)  # type: ignore[arg-type]
            elif isinstance(b, dict):
                blocks.append(block_from_dict(b))
        values["blocks"] = blocks
        return values


class DocIR(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    title: str = DEFAULT_TITLE
    sections: List[SectionNode] = Field(default_factory=list)


SectionNode.model_rebuild()


class DocIRIndex(BaseModel):
    section_by_id: Dict[str, SectionNode] = Field(default_factory=dict)
    parent_by_id: Dict[str, Optional[str]] = Field(default_factory=dict)
    block_by_id: Dict[str, DocIRBlock] = Field(default_factory=dict)
    block_parent_by_id: Dict[str, str] = Field(default_factory=dict)
    section_order: List[str] = Field(default_factory=list)


class RenderCache(BaseModel):
    cache: Dict[str, str] = Field(default_factory=dict)

    def get(self, key: str) -> Optional[str]:
        return self.cache.get(key)

    def set(self, key: str, value: str) -> None:
        self.cache[key] = value


class Operation(BaseModel):
    op: Literal["insert", "delete", "update", "move"]
    target_id: str
    parent_id: Optional[str] = None
    index: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None


class OperationLog(BaseModel):
    ops: List[Operation] = Field(default_factory=list)
    cursor: int = 0

    def record(self, op: Operation) -> None:
        if self.cursor < len(self.ops):
            self.ops = self.ops[: self.cursor]
        self.ops.append(op)
        self.cursor += 1

    def undo(self) -> Optional[Operation]:
        if self.cursor <= 0:
            return None
        self.cursor -= 1
        return self.ops[self.cursor]

    def redo(self) -> Optional[Operation]:
        if self.cursor >= len(self.ops):
            return None
        op = self.ops[self.cursor]
        self.cursor += 1
        return op


# -------- Tree building (O(n)) --------

def build_tree_from_blocks(blocks: List[DocBlock], title: str) -> DocIR:
    root_sections: List[SectionNode] = []
    stack: List[Tuple[int, SectionNode]] = []
    orphan_blocks: List[DocIRBlock] = []
    doc_title = (title or "").strip() or DEFAULT_TITLE

    for b in blocks:
        if b.type == "heading":
            level = max(1, min(6, int(b.level or 1)))
            node = SectionNode(title=(b.text or "").strip() or DEFAULT_SECTION_TITLE, level=level)

            if orphan_blocks and not stack:
                implicit = SectionNode(title=doc_title, level=1, blocks=orphan_blocks)
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

        block = _block_from_docblock(b)
        if stack:
            stack[-1][1].blocks.append(block)
        else:
            orphan_blocks.append(block)

    if orphan_blocks and not root_sections:
        root_sections.append(SectionNode(title=doc_title, level=1, blocks=orphan_blocks))

    return DocIR(title=doc_title, sections=root_sections)


def build_index(doc: DocIR) -> DocIRIndex:
    idx = DocIRIndex()

    def walk(sec: SectionNode, parent_id: Optional[str]) -> None:
        idx.section_by_id[sec.id] = sec
        idx.parent_by_id[sec.id] = parent_id
        idx.section_order.append(sec.id)
        for b in sec.blocks:
            bid = get_block_id(b)
            idx.block_by_id[bid] = b
            idx.block_parent_by_id[bid] = sec.id
        for ch in sec.children:
            walk(ch, sec.id)

    for s in doc.sections:
        walk(s, None)
    return idx


def iter_blocks(doc: DocIR) -> Iterator[DocIRBlock]:
    stack = list(reversed(doc.sections))
    while stack:
        sec = stack.pop()
        for b in sec.blocks:
            yield b
        if sec.children:
            stack.extend(reversed(sec.children))


def paged_blocks(doc: DocIR, page_size: int) -> Iterator[List[DocIRBlock]]:
    buf: List[DocIRBlock] = []
    for b in iter_blocks(doc):
        buf.append(b)
        if len(buf) >= page_size:
            yield buf
            buf = []
    if buf:
        yield buf


# -------- Conversions --------

def from_text(text: str) -> DocIR:
    parsed = parse_report_text(text or "")
    return from_parsed(parsed)


def from_parsed(parsed: ParsedDoc) -> DocIR:
    blocks = explode_markers(parsed.blocks or [])
    return build_tree_from_blocks(blocks, parsed.title or DEFAULT_TITLE)


def to_parsed(doc: DocIR) -> ParsedDoc:
    blocks: List[DocBlock] = []

    def walk(sec: SectionNode) -> None:
        blocks.append(DocBlock(type="heading", level=sec.level, text=sec.title))
        for b in sec.blocks:
            blocks.append(_docblock_from_block(b))
        for ch in sec.children:
            walk(ch)

    for s in doc.sections:
        walk(s)
    if not any(b.type == "heading" and (b.level or 0) == 1 for b in blocks):
        blocks.insert(0, DocBlock(type="heading", level=1, text=doc.title or DEFAULT_TITLE))
    return ParsedDoc(title=doc.title or DEFAULT_TITLE, blocks=blocks)


def to_text(doc: DocIR) -> str:
    parsed = to_parsed(doc)
    out: List[str] = []
    for b in parsed.blocks:
        if b.type == "heading":
            level = b.level or 1
            txt = (b.text or "").strip()
            if txt:
                out.append(f"{'#' * level} {txt}")
        elif b.type == "paragraph":
            txt = (b.text or "").strip()
            if txt:
                out.append(txt)
        elif b.type == "table":
            out.append(f"[[TABLE:{_safe_json(b.table or {})}]]")
        elif b.type == "figure":
            out.append(f"[[FIGURE:{_safe_json(b.figure or {})}]]")
        elif b.type == "list":
            items = b.items if isinstance(b.items, list) else []
            cleaned = [str(it).strip() for it in items if str(it).strip()]
            if b.ordered:
                for i, txt in enumerate(cleaned):
                    out.append(f"{i + 1}. {txt}")
            else:
                for txt in cleaned:
                    out.append(f"\u2022 {txt}")
    return "\n\n".join([s for s in out if s]).strip()


def to_dict(doc: DocIR) -> dict:
    return doc.model_dump()


def from_dict(data: dict | None) -> DocIR:
    if not isinstance(data, dict):
        return DocIR()
    if _looks_like_v1_dict(data):
        return migrate_v1_to_v2(data)
    return DocIR.model_validate(data)


# -------- Block helpers --------

def get_block_id(b: DocIRBlock) -> str:
    return getattr(b, "id", "")


def render_block_text(block: DocIRBlock, cache: Optional[RenderCache] = None) -> str:
    key = block.content_hash()
    if cache:
        cached = cache.get(key)
        if cached is not None:
            return cached
    if isinstance(block, ParagraphBlock):
        out = block.text.strip() if block.text else _runs_to_text(getattr(block, "runs", []))
    elif isinstance(block, HeadingBlock):
        out = block.text.strip() if block.text else _runs_to_text(getattr(block, "runs", []))
    elif isinstance(block, ListBlock):
        items = [str(it).strip() for it in (block.items or []) if str(it).strip()]
        if block.ordered:
            out = "\n".join([f"{i + 1}. {item}" for i, item in enumerate(items)])
        else:
            out = "\n".join([f"\u2022 {item}" for item in items])
    elif isinstance(block, TableBlock):
        out = f"[[TABLE:{_safe_json(block.table)}]]"
    elif isinstance(block, FigureBlock):
        out = f"[[FIGURE:{_safe_json(block.figure)}]]"
    else:
        out = ""
    if cache:
        cache.set(key, out)
    return out


def _block_from_docblock(b: DocBlock) -> DocIRBlock:
    if b.type == "heading":
        return HeadingBlock(level=int(b.level or 1), text=b.text or "")
    if b.type == "paragraph":
        return ParagraphBlock(text=b.text or "")
    if b.type == "table":
        return TableBlock(table=b.table or {})
    if b.type == "figure":
        return FigureBlock(figure=b.figure or {})
    if b.type == "list":
        items, ordered = _extract_list_items_from_text(b.text or "")
        return ListBlock(items=items, ordered=ordered)
    return ParagraphBlock(text=b.text or "")


def _docblock_from_block(b: DocIRBlock) -> DocBlock:
    if isinstance(b, HeadingBlock):
        text = b.text or _runs_to_text(getattr(b, "runs", []))
        return DocBlock(type="heading", level=b.level, text=text)
    if isinstance(b, ParagraphBlock):
        text = b.text or _runs_to_text(getattr(b, "runs", []))
        return DocBlock(type="paragraph", text=text)
    if isinstance(b, ListBlock):
        # Flatten list items into paragraph lines.
        items = b.items if isinstance(b.items, list) else []
        cleaned = [str(it).strip() for it in items if str(it).strip()]
        if b.ordered:
            text = "\n".join([f"{i + 1}. {item}" for i, item in enumerate(cleaned)])
        else:
            text = "\n".join([f"\u2022 {item}" for item in cleaned])
        return DocBlock(type="paragraph", text=text)
    if isinstance(b, TableBlock):
        return DocBlock(type="table", table=b.table)
    if isinstance(b, FigureBlock):
        return DocBlock(type="figure", figure=b.figure)
    return DocBlock(type="paragraph", text=getattr(b, "text", ""))


# -------- Diff (Myers) --------

def myers_diff(a: List[str], b: List[str]) -> List[Tuple[str, int, int]]:
    # returns list of (op, i, j) where op in {"equal","insert","delete"}
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


def diff_blocks(old: DocIR, new: DocIR) -> List[Tuple[str, int, int]]:
    old_hashes = [b.content_hash() for b in iter_blocks(old)]
    new_hashes = [b.content_hash() for b in iter_blocks(new)]
    return myers_diff(old_hashes, new_hashes)


def build_inverted_index(doc: DocIR) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    for b in iter_blocks(doc):
        text = render_block_text(b).strip()
        if not text:
            continue
        for token in _WORD_RE.findall(text):
            token = token.lower()
            index.setdefault(token, []).append(get_block_id(b))
    return index


def validate_doc_ir(doc: DocIR) -> List[str]:
    problems: List[str] = []
    if not doc.title or not doc.title.strip():
        problems.append("missing title")
    if not doc.sections:
        problems.append("missing sections")
    return problems


# -------- Operations / Merge --------

def apply_ops(doc: DocIR, ops: List[Operation], *, atomic: bool = False) -> DocIR:
    target = doc.model_copy(deep=True) if atomic else doc
    if not ops:
        return target
    idx = build_index(target)
    for op in ops:
        if not _apply_single_op(target, idx, op):
            if atomic:
                return doc
            continue
    return target


def _delete_block_in_section(sec: SectionNode, block_id: str) -> bool:
    for i, b in enumerate(sec.blocks):
        if get_block_id(b) == block_id:
            sec.blocks.pop(i)
            return True
    for ch in sec.children:
        if _delete_block_in_section(ch, block_id):
            return True
    return False


def block_from_dict(data: dict) -> DocIRBlock:
    if not isinstance(data, dict):
        return ParagraphBlock(text="")
    t = str(data.get("type") or "paragraph")
    block_id = str(data.get("id") or "").strip()
    id_kw = {"id": block_id} if block_id else {}
    style = data.get("style")
    style_kw = {"style": style} if isinstance(style, dict) else {}
    runs = data.get("runs")
    runs_kw = {"runs": runs} if isinstance(runs, list) else {}
    if t == "heading":
        return HeadingBlock(
            level=int(data.get("level") or 1),
            text=str(data.get("text") or ""),
            **id_kw,
            **style_kw,
            **runs_kw,
        )
    if t == "paragraph":
        return ParagraphBlock(text=str(data.get("text") or ""), **id_kw, **style_kw, **runs_kw)
    if t == "list":
        return ListBlock(
            items=[str(x) for x in (data.get("items") or [])],
            ordered=bool(data.get("ordered")),
            **id_kw,
            **style_kw,
        )
    if t == "table":
        return TableBlock(table=dict(data.get("table") or {}), **id_kw, **style_kw)
    if t == "figure":
        return FigureBlock(figure=dict(data.get("figure") or {}), **id_kw, **style_kw)
    return ParagraphBlock(text=str(data.get("text") or ""), **id_kw, **style_kw)


# -------- Serialization (MessagePack optional) --------

def dumps(doc: DocIR) -> bytes:
    try:
        import msgpack  # type: ignore

        return msgpack.packb(doc.model_dump(), use_bin_type=True)
    except Exception:
        return json.dumps(doc.model_dump(), ensure_ascii=False).encode("utf-8")


def loads(raw: bytes) -> DocIR:
    try:
        import msgpack  # type: ignore

        return DocIR.model_validate(msgpack.unpackb(raw, raw=False))
    except Exception:
        return DocIR.model_validate(json.loads(raw.decode("utf-8")))


_MARKER_RE = re.compile(r"\[\[(FIGURE|TABLE)\s*:\s*(\{[\s\S]*?\})\s*\]\]", flags=re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z0-9]+|[\\u4e00-\\u9fff]{1,4}")


def explode_markers(blocks: List[DocBlock]) -> List[DocBlock]:
    out: List[DocBlock] = []
    for b in blocks:
        if b.type != "paragraph" or not (b.text or "").strip():
            out.append(b)
            continue
        txt = b.text or ""
        pos = 0
        for m in _MARKER_RE.finditer(txt):
            before = txt[pos:m.start()].strip()
            if before:
                out.append(DocBlock(type="paragraph", text=before))
            kind = (m.group(1) or "").lower()
            raw = (m.group(2) or "").strip()
            data = _safe_json_loads(raw)
            if kind == "table":
                out.append(DocBlock(type="table", table=data if isinstance(data, dict) else {"raw": raw}))
            else:
                out.append(DocBlock(type="figure", figure=data if isinstance(data, dict) else {"raw": raw}))
            pos = m.end()
        tail = txt[pos:].strip()
        if tail:
            out.append(DocBlock(type="paragraph", text=tail))
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
        m = num_re.match(stripped)
        if m:
            num_hits += 1
            items.append(stripped[m.end():].strip())
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
    return all(isinstance(s, dict) and "children" not in s for s in sections)


def migrate_v1_to_v2(data: dict) -> DocIR:
    title = str(data.get("title") or DEFAULT_TITLE).strip() or DEFAULT_TITLE
    sections = data.get("sections") or []
    blocks: List[DocBlock] = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        level = int(sec.get("level") or 1)
        sec_title = str(sec.get("title") or "").strip() or DEFAULT_SECTION_TITLE
        blocks.append(DocBlock(type="heading", level=level, text=sec_title))
        for raw in sec.get("blocks") or []:
            if isinstance(raw, dict):
                blocks.append(_docblock_from_block(block_from_dict(raw)))
    blocks = explode_markers(blocks)
    return build_tree_from_blocks(blocks, title)


def migrate_v2_to_v1(doc: DocIR) -> dict:
    flat_sections: List[dict] = []

    def walk(sec: SectionNode) -> None:
        flat_sections.append(
            {
                "title": sec.title,
                "level": sec.level,
                "blocks": [b.model_dump() for b in sec.blocks],
            }
        )
        for ch in sec.children:
            walk(ch)

    for s in doc.sections:
        walk(s)
    return {"title": doc.title, "sections": flat_sections}


def _apply_single_op(doc: DocIR, idx: DocIRIndex, op: Operation) -> bool:
    if op.op == "insert":
        sec = idx.section_by_id.get(op.parent_id or "")
        if not sec:
            return False
        block = block_from_dict(op.payload or {})
        pos = int(op.index or len(sec.blocks))
        sec.blocks.insert(max(0, min(len(sec.blocks), pos)), block)
        bid = get_block_id(block)
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
        for i, b in enumerate(sec.blocks):
            if get_block_id(b) == op.target_id:
                sec.blocks.pop(i)
                idx.block_by_id.pop(op.target_id, None)
                idx.block_parent_by_id.pop(op.target_id, None)
                return True
        return False
    if op.op == "update":
        block = idx.block_by_id.get(op.target_id)
        if not block or not op.payload:
            return False
        for k, v in op.payload.items():
            if hasattr(block, k):
                setattr(block, k, v)
        return True
    if op.op == "move":
        sec_id = idx.block_parent_by_id.get(op.target_id)
        if not sec_id:
            return False
        src_sec = idx.section_by_id.get(sec_id)
        if not src_sec:
            return False
        moving = None
        for i, b in enumerate(src_sec.blocks):
            if get_block_id(b) == op.target_id:
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

