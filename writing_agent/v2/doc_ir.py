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
from writing_agent.v2 import doc_ir_convert_domain as convert_domain
from writing_agent.v2 import doc_ir_parse_domain as parse_domain
from writing_agent.v2 import doc_ir_ops_domain as ops_domain


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
    return convert_domain.build_tree_from_blocks(blocks, title)


def build_index(doc: DocIR) -> DocIRIndex:
    return convert_domain.build_index(doc)


def iter_blocks(doc: DocIR) -> Iterator[DocIRBlock]:
    return convert_domain.iter_blocks(doc)


def paged_blocks(doc: DocIR, page_size: int) -> Iterator[List[DocIRBlock]]:
    return convert_domain.paged_blocks(doc, page_size)


# -------- Conversions --------

def from_text(text: str) -> DocIR:
    return convert_domain.from_text(text)


def from_parsed(parsed: ParsedDoc) -> DocIR:
    return convert_domain.from_parsed(parsed)


def to_parsed(doc: DocIR) -> ParsedDoc:
    return convert_domain.to_parsed(doc)


def to_text(doc: DocIR) -> str:
    return convert_domain.to_text(doc)


def to_dict(doc: DocIR) -> dict:
    return convert_domain.to_dict(doc)


def from_dict(data: dict | None) -> DocIR:
    return convert_domain.from_dict(data)


# -------- Block helpers --------

def get_block_id(b: DocIRBlock) -> str:
    return convert_domain.get_block_id(b)


def render_block_text(block: DocIRBlock, cache: Optional[RenderCache] = None) -> str:
    return convert_domain.render_block_text(block, cache=cache)


def _block_from_docblock(b: DocBlock) -> DocIRBlock:
    return parse_domain._block_from_docblock(b)


def _docblock_from_block(b: DocIRBlock) -> DocBlock:
    return parse_domain._docblock_from_block(b)


# -------- Diff / Ops --------

def myers_diff(a: List[str], b: List[str]) -> List[Tuple[str, int, int]]:
    return ops_domain.myers_diff(a, b)


def _backtrack(trace: List[Dict[int, int]], a: List[str], b: List[str]) -> List[Tuple[str, int, int]]:
    return ops_domain._backtrack(trace, a, b)


def diff_blocks(old: DocIR, new: DocIR) -> List[Tuple[str, int, int]]:
    return ops_domain.diff_blocks(old, new)


def build_inverted_index(doc: DocIR) -> Dict[str, List[str]]:
    return ops_domain.build_inverted_index(doc)


def validate_doc_ir(doc: DocIR) -> List[str]:
    return ops_domain.validate_doc_ir(doc)


def apply_ops(doc: DocIR, ops: List[Operation], *, atomic: bool = False) -> DocIR:
    return ops_domain.apply_ops(doc, ops, atomic=atomic)


def _delete_block_in_section(sec: SectionNode, block_id: str) -> bool:
    return ops_domain._delete_block_in_section(sec, block_id)


def block_from_dict(data: dict) -> DocIRBlock:
    return parse_domain.block_from_dict(data)


def _apply_single_op(doc: DocIR, idx: DocIRIndex, op: Operation) -> bool:
    return ops_domain._apply_single_op(doc, idx, op)


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
    return parse_domain.explode_markers(blocks)


def _safe_json_loads(raw: str) -> Optional[dict]:
    return parse_domain._safe_json_loads(raw)


def _extract_list_items_from_text(text: str) -> Tuple[List[str], bool]:
    return parse_domain._extract_list_items_from_text(text)


def _runs_to_text(runs: Iterable[Dict[str, Any]]) -> str:
    return parse_domain._runs_to_text(runs)


def _looks_like_v1_dict(data: dict) -> bool:
    return parse_domain._looks_like_v1_dict(data)


def migrate_v1_to_v2(data: dict) -> DocIR:
    return parse_domain.migrate_v1_to_v2(data)


def migrate_v2_to_v1(doc: DocIR) -> dict:
    return parse_domain.migrate_v2_to_v1(doc)




__all__ = [name for name in globals() if not name.startswith('__')]

