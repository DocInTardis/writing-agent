"""Canonical, editor-neutral document model used by users and AI commands."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


STRICT_CONFIG = ConfigDict(extra="forbid", alias_generator=_to_camel, populate_by_name=True)
FLEXIBLE_CONFIG = ConfigDict(extra="allow", alias_generator=_to_camel, populate_by_name=True)


class StyleProperties(BaseModel):
    model_config = STRICT_CONFIG

    font_family: str | None = None
    font_size_pt: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    color: str | None = None
    background_color: str | None = None
    letter_spacing_pt: float | None = None
    text_transform: Literal["none", "uppercase", "lowercase", "capitalize"] | None = None
    alignment: Literal["left", "center", "right", "justify"] | None = None
    line_spacing: float | None = None
    first_line_indent_em: float | None = None
    left_indent_em: float | None = None
    right_indent_em: float | None = None
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    outline_level: int | None = None
    keep_with_next: bool | None = None
    keep_lines_together: bool | None = None
    page_break_before: bool | None = None
    border_color: str | None = None
    border_width_pt: float | None = None
    border_style: Literal["none", "solid", "dashed", "double"] | None = None
    shading_color: str | None = None
    tab_stops: list[dict[str, Any]] | None = None


class StyleDefinition(BaseModel):
    model_config = STRICT_CONFIG

    id: str
    name: str
    kind: Literal["paragraph", "character", "table"] = "paragraph"
    based_on: str | None = None
    next_style: str | None = None
    visible: bool = True
    properties: StyleProperties = Field(default_factory=StyleProperties)


class InlineNode(BaseModel):
    model_config = FLEXIBLE_CONFIG

    type: Literal[
        "text",
        "hardBreak",
        "field",
        "footnoteReference",
        "citation",
        "bookmark",
    ]
    text: str | None = None
    marks: list[dict[str, Any]] = Field(default_factory=list)
    attrs: dict[str, Any] = Field(default_factory=dict)


class BlockNode(BaseModel):
    model_config = FLEXIBLE_CONFIG

    id: str = Field(default_factory=lambda: _id("block"))
    type: Literal[
        "paragraph",
        "heading",
        "bulletList",
        "orderedList",
        "listItem",
        "blockquote",
        "codeBlock",
        "table",
        "figure",
        "equationBlock",
        "horizontalRule",
        "pageBreak",
        "sectionBreak",
        "tableOfContents",
        "bibliography",
    ]
    style_id: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    content: list["BlockNode | InlineNode"] = Field(default_factory=list)


class PageLayout(BaseModel):
    model_config = STRICT_CONFIG

    page_size: Literal["A4", "A3", "Letter", "custom"] = "A4"
    width_mm: float | None = None
    height_mm: float | None = None
    orientation: Literal["portrait", "landscape"] = "portrait"
    margin_top_mm: float = 25.4
    margin_right_mm: float = 25.4
    margin_bottom_mm: float = 25.4
    margin_left_mm: float = 31.8
    columns: int = 1

    @field_validator("columns")
    @classmethod
    def _valid_columns(cls, value: int) -> int:
        if not 1 <= value <= 12:
            raise ValueError("columns must be between 1 and 12")
        return value


class PageNumberDefinition(BaseModel):
    model_config = STRICT_CONFIG

    enabled: bool = True
    format: Literal["arabic", "lowerRoman", "upperRoman", "lowerLetter", "upperLetter"] = "arabic"
    start_at: int | None = None
    position: Literal["header", "footer"] = "footer"
    alignment: Literal["left", "center", "right"] = "center"


class HeaderFooterDefinition(BaseModel):
    model_config = STRICT_CONFIG

    link_header_to_previous: bool = True
    link_footer_to_previous: bool = True
    different_first_page: bool = False
    different_odd_even: bool = False
    header: list[BlockNode] = Field(default_factory=list)
    footer: list[BlockNode] = Field(default_factory=list)
    first_page_header: list[BlockNode] = Field(default_factory=list)
    first_page_footer: list[BlockNode] = Field(default_factory=list)
    even_page_header: list[BlockNode] = Field(default_factory=list)
    even_page_footer: list[BlockNode] = Field(default_factory=list)
    page_number: PageNumberDefinition = Field(default_factory=PageNumberDefinition)


class SectionV3(BaseModel):
    model_config = STRICT_CONFIG

    id: str = Field(default_factory=lambda: _id("section"))
    break_type: Literal["nextPage", "continuous", "oddPage", "evenPage"] = "nextPage"
    layout: PageLayout = Field(default_factory=PageLayout)
    header_footer: HeaderFooterDefinition = Field(default_factory=HeaderFooterDefinition)
    content: list[BlockNode] = Field(default_factory=list)


class DocumentV3(BaseModel):
    model_config = STRICT_CONFIG

    schema_version: Literal[3] = 3
    id: str = Field(default_factory=lambda: _id("doc"))
    title: str = "未命名文档"
    metadata: dict[str, Any] = Field(default_factory=dict)
    styles: list[StyleDefinition] = Field(default_factory=list)
    numbering: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[SectionV3] = Field(default_factory=list)
    notes: dict[str, Any] = Field(default_factory=dict)
    citations: dict[str, Any] = Field(default_factory=dict)
    comments: list[dict[str, Any]] = Field(default_factory=list)
    revisions: list[dict[str, Any]] = Field(default_factory=list)
    resources: dict[str, Any] = Field(default_factory=dict)


BlockNode.model_rebuild()


def default_styles() -> list[StyleDefinition]:
    styles = [
        StyleDefinition(
            id="normal",
            name="正文",
            next_style="normal",
            properties=StyleProperties(
                font_family="SimSun",
                font_size_pt=12,
                alignment="justify",
                line_spacing=1.5,
                first_line_indent_em=2,
            ),
        ),
        StyleDefinition(
            id="title",
            name="文档标题",
            based_on="normal",
            next_style="normal",
            properties=StyleProperties(
                font_family="SimHei",
                font_size_pt=22,
                bold=True,
                alignment="center",
                outline_level=0,
            ),
        ),
    ]
    for level in range(1, 7):
        styles.append(
            StyleDefinition(
                id=f"heading-{level}",
                name=f"标题 {level}",
                based_on="normal",
                next_style="normal",
                properties=StyleProperties(
                    font_family="SimHei" if level <= 2 else "SimSun",
                    font_size_pt=max(12, 18 - ((level - 1) * 1.5)),
                    bold=True,
                    alignment="left",
                    outline_level=level,
                    keep_with_next=True,
                    page_break_before=level == 1,
                ),
            )
        )
    return styles


def create_document(title: str = "未命名文档") -> DocumentV3:
    paragraph = BlockNode(type="paragraph", style_id="normal")
    return DocumentV3(
        title=title,
        styles=default_styles(),
        sections=[SectionV3(content=[paragraph])],
    )


def _text_content(value: Any) -> list[InlineNode]:
    text = str(value or "")
    return [InlineNode(type="text", text=text)] if text else []


def _legacy_block(raw: dict[str, Any]) -> BlockNode:
    block_type = str(raw.get("type") or "paragraph").lower()
    block_id = str(raw.get("id") or _id("block"))
    direct_formatting = deepcopy(raw.get("style") or {})
    if block_type == "heading":
        level = min(6, max(1, int(raw.get("level") or 1)))
        return BlockNode(
            id=block_id,
            type="heading",
            style_id=f"heading-{level}",
            attrs={"level": level, "directFormatting": direct_formatting},
            content=_text_content(raw.get("text")),
        )
    if block_type == "list":
        items = []
        for text in raw.get("items") or []:
            items.append(
                BlockNode(
                    type="listItem",
                    content=[BlockNode(type="paragraph", style_id="normal", content=_text_content(text))],
                )
            )
        return BlockNode(
            id=block_id,
            type="orderedList" if raw.get("ordered") else "bulletList",
            attrs={"directFormatting": direct_formatting},
            content=items,
        )
    if block_type == "table":
        return BlockNode(id=block_id, type="table", attrs={"table": deepcopy(raw.get("table") or {})})
    if block_type == "figure":
        return BlockNode(id=block_id, type="figure", attrs={"figure": deepcopy(raw.get("figure") or {})})
    if block_type == "page_break":
        return BlockNode(id=block_id, type="pageBreak")
    return BlockNode(
        id=block_id,
        type="paragraph",
        style_id="normal",
        attrs={"directFormatting": direct_formatting},
        content=_text_content(raw.get("text")),
    )


def migrate_doc_ir(raw: dict[str, Any] | None) -> DocumentV3:
    source = raw or {}
    doc = create_document(str(source.get("title") or "未命名文档"))
    content: list[BlockNode] = []

    def walk(sections: list[Any]) -> None:
        for item in sections:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if title:
                level = min(6, max(1, int(item.get("level") or 1)))
                content.append(
                    BlockNode(
                        id=str(item.get("id") or _id("heading")),
                        type="heading",
                        style_id=f"heading-{level}",
                        attrs={"level": level, "legacySection": True},
                        content=_text_content(title),
                    )
                )
            for block in item.get("blocks") or []:
                if isinstance(block, dict):
                    content.append(_legacy_block(block))
            walk(item.get("children") or [])

    walk(source.get("sections") or [])
    if content:
        doc.sections[0].content = content
    doc.metadata["migratedFrom"] = "DocIR-v2"
    return doc


def iter_blocks(doc: DocumentV3):
    def walk(nodes: list[BlockNode]):
        for node in nodes:
            yield node
            children = [child for child in node.content if isinstance(child, BlockNode)]
            if children:
                yield from walk(children)

    for section in doc.sections:
        yield from walk(section.content)


def validate_unique_ids(doc: DocumentV3) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for section in doc.sections:
        if section.id in seen:
            duplicates.append(section.id)
        seen.add(section.id)
    for block in iter_blocks(doc):
        if block.id in seen:
            duplicates.append(block.id)
        seen.add(block.id)
    return duplicates


def to_plain_text(doc: DocumentV3) -> str:
    """Return semantic text without serializing page chrome or computed fields."""

    lines: list[str] = []

    def inline_text(node: BlockNode) -> str:
        parts: list[str] = []
        for child in node.content:
            if isinstance(child, InlineNode):
                if child.type == "text":
                    parts.append(child.text or "")
                elif child.type == "hardBreak":
                    parts.append("\n")
            elif isinstance(child, BlockNode):
                parts.append(inline_text(child))
        return "".join(parts)

    for section in doc.sections:
        for block in section.content:
            if block.type == "table":
                payload = block.attrs.get("table") if isinstance(block.attrs, dict) else None
                if isinstance(payload, dict):
                    lines.append(f"[[TABLE:{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}]]")
                continue
            if block.type == "figure":
                payload = block.attrs.get("figure") if isinstance(block.attrs, dict) else None
                if isinstance(payload, dict):
                    lines.append(f"[[FIGURE:{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}]]")
                continue
            text = inline_text(block).strip()
            if not text:
                continue
            if block.type == "heading":
                level = min(6, max(1, int(block.attrs.get("level") or 1)))
                lines.append(f"{'#' * level} {text}")
            else:
                lines.append(text)
    return "\n\n".join(lines).strip()
