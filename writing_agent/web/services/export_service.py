"""Export Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import logging
import io
import os
import re
import tempfile
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi.responses import Response, StreamingResponse

from .base import app_v2_module

logger = logging.getLogger(__name__)


class ExportService:
    _SINGLE_DOCX_BACKEND_MODE = "single_parsed"

    @staticmethod
    def _unchanged_imported_docx(session) -> bytes | None:
        """Return the original DOCX when its canonical V3 content is unchanged."""
        expected = str(getattr(session, "import_source_fingerprint", "") or "")
        raw_v3 = getattr(session, "document_v3", None)
        if not expected or not isinstance(raw_v3, dict):
            return None
        try:
            from writing_agent.v3.docx_import import document_v3_fingerprint

            if document_v3_fingerprint(raw_v3) != expected:
                return None
            app_v2 = app_v2_module()
            source_path = app_v2.store.source_document_path(session.id)
            return source_path.read_bytes() if source_path is not None else None
        except Exception as exc:
            logger.warning("Could not use lossless imported-DOCX export for %s: %s", session.id, exc)
            return None

    @staticmethod
    def _patched_imported_docx(session) -> bytes | None:
        """Apply editable V3 paragraph/table changes onto the original Word package.

        This preserves cover art, fields, section breaks, drawing anchors and
        other OOXML details that a text-first rebuild cannot reproduce.
        """
        raw_v3 = getattr(session, "document_v3", None)
        if not isinstance(raw_v3, dict) or not str(getattr(session, "import_source_fingerprint", "") or ""):
            return None
        app_v2 = app_v2_module()
        source_path = app_v2.store.source_document_path(session.id)
        if source_path is None:
            return None
        try:
            from docx import Document
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml import OxmlElement
            from docx.shared import Pt, RGBColor
            from writing_agent.v3 import DocumentV3

            model = DocumentV3.model_validate(raw_v3)
            document = Document(str(source_path))
            original_paragraphs = list(document.paragraphs)
            original_tables = list(document.tables)
            styles = {style.id: style for style in model.styles}

            def inline_text(block) -> str:
                pieces: list[str] = []
                for node in block.content:
                    node_type = getattr(node, "type", "")
                    if node_type == "text":
                        pieces.append(str(getattr(node, "text", "") or ""))
                    elif node_type == "hardBreak":
                        pieces.append("\n")
                return "".join(pieces)

            def apply_inline(paragraph, block) -> None:
                desired = inline_text(block)
                if paragraph.text == desired:
                    return
                preserved_drawings = [
                    deepcopy(node)
                    for node in paragraph._p.xpath(".//w:drawing | .//w:pict")
                ]
                p_pr = paragraph._p.pPr
                for child in list(paragraph._p):
                    if child is not p_pr:
                        paragraph._p.remove(child)
                for node in block.content:
                    node_type = getattr(node, "type", "")
                    if node_type == "hardBreak":
                        paragraph.add_run().add_break()
                        continue
                    if node_type != "text":
                        continue
                    run = paragraph.add_run(str(getattr(node, "text", "") or ""))
                    for mark in list(getattr(node, "marks", []) or []):
                        mark_type = str(mark.get("type") or "")
                        attrs = mark.get("attrs") if isinstance(mark.get("attrs"), dict) else {}
                        if mark_type == "bold":
                            run.bold = True
                        elif mark_type == "italic":
                            run.italic = True
                        elif mark_type == "underline":
                            run.underline = True
                        elif mark_type == "strike":
                            run.font.strike = True
                        elif mark_type == "subscript":
                            run.font.subscript = True
                        elif mark_type == "superscript":
                            run.font.superscript = True
                        elif mark_type == "textStyle":
                            if attrs.get("fontFamily"):
                                run.font.name = str(attrs["fontFamily"])
                            size = str(attrs.get("fontSize") or "").removesuffix("pt")
                            try:
                                if size:
                                    run.font.size = Pt(float(size))
                            except ValueError:
                                pass
                            color = str(attrs.get("color") or "").lstrip("#")
                            if re.fullmatch(r"[0-9A-Fa-f]{6}", color):
                                run.font.color.rgb = RGBColor.from_string(color.upper())
                for drawing in preserved_drawings:
                    paragraph.add_run()._r.append(drawing)

            def apply_paragraph_format(paragraph, block) -> None:
                style = styles.get(str(block.style_id or ""))
                if style is not None:
                    for candidate in (style.name, style.id):
                        try:
                            paragraph.style = candidate
                            break
                        except (KeyError, ValueError):
                            continue
                attrs = block.attrs or {}
                alignment = str(attrs.get("textAlign") or "")
                paragraph.alignment = {
                    "left": WD_ALIGN_PARAGRAPH.LEFT,
                    "center": WD_ALIGN_PARAGRAPH.CENTER,
                    "right": WD_ALIGN_PARAGRAPH.RIGHT,
                    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
                }.get(alignment, paragraph.alignment)
                fmt = paragraph.paragraph_format
                numeric_fields = {
                    "spaceBeforePt": "space_before",
                    "spaceAfterPt": "space_after",
                }
                for key, attr_name in numeric_fields.items():
                    if attrs.get(key) is not None:
                        setattr(fmt, attr_name, Pt(float(attrs[key])))
                if attrs.get("lineSpacing") is not None:
                    fmt.line_spacing = float(attrs["lineSpacing"])
                for key, attr_name in (("keepWithNext", "keep_with_next"), ("keepLinesTogether", "keep_together"), ("pageBreakBefore", "page_break_before")):
                    if attrs.get(key) is not None:
                        setattr(fmt, attr_name, bool(attrs[key]))

            def iter_main_blocks(blocks):
                for block in blocks:
                    if block.type in {"paragraph", "heading"}:
                        yield block
                    elif block.type in {"bulletList", "orderedList", "listItem", "blockquote"}:
                        yield from iter_main_blocks([item for item in block.content if hasattr(item, "type")])

            paragraph_blocks = [block for section in model.sections for block in iter_main_blocks(section.content)]
            def iter_all_blocks(blocks):
                for block in blocks:
                    yield block
                    children = getattr(block, "content", [])
                    yield from iter_all_blocks([item for item in children if hasattr(item, "content")])

            represented_now: set[int] = {
                int(block.attrs["sourceParagraphIndex"])
                for section in model.sections
                for block in iter_all_blocks(section.content)
                if isinstance(block.attrs.get("sourceParagraphIndex"), int)
            }
            for block in paragraph_blocks:
                source_index = block.attrs.get("sourceParagraphIndex")
                if isinstance(source_index, int) and 0 <= source_index < len(original_paragraphs):
                    paragraph = original_paragraphs[source_index]
                    apply_inline(paragraph, block)
                    apply_paragraph_format(paragraph, block)

            represented_before = {
                int(value)
                for value in list(model.metadata.get("representedParagraphs") or [])
                if isinstance(value, int) or str(value).isdigit()
            }
            for source_index in sorted(represented_before - represented_now, reverse=True):
                if 0 <= source_index < len(original_paragraphs):
                    element = original_paragraphs[source_index]._p
                    element.getparent().remove(element)

            # New paragraphs have no source index. Insert them relative to the
            # nearest imported paragraph so editor order remains deterministic.
            for position, block in enumerate(paragraph_blocks):
                if isinstance(block.attrs.get("sourceParagraphIndex"), int):
                    continue
                next_source = next(
                    (
                        candidate.attrs.get("sourceParagraphIndex")
                        for candidate in paragraph_blocks[position + 1 :]
                        if isinstance(candidate.attrs.get("sourceParagraphIndex"), int)
                    ),
                    None,
                )
                new_p = OxmlElement("w:p")
                if isinstance(next_source, int) and 0 <= next_source < len(original_paragraphs):
                    original_paragraphs[next_source]._p.addprevious(new_p)
                else:
                    body = document.element.body
                    sect_pr = body.sectPr
                    if sect_pr is not None:
                        sect_pr.addprevious(new_p)
                    else:
                        body.append(new_p)
                from docx.text.paragraph import Paragraph

                paragraph = Paragraph(new_p, document)
                apply_inline(paragraph, block)
                apply_paragraph_format(paragraph, block)

            for section in model.sections:
                for block in section.content:
                    if block.type != "table":
                        continue
                    source_index = block.attrs.get("sourceTableIndex")
                    if not isinstance(source_index, int) or not 0 <= source_index < len(original_tables):
                        continue
                    raw_table = block.attrs.get("table") if isinstance(block.attrs.get("table"), dict) else {}
                    cells = raw_table.get("cells") if isinstance(raw_table.get("cells"), list) else []
                    table = original_tables[source_index]
                    for row_index, row in enumerate(cells):
                        if row_index >= len(table.rows) or not isinstance(row, list):
                            continue
                        for cell_index, cell in enumerate(row):
                            if cell_index < len(table.rows[row_index].cells) and isinstance(cell, dict):
                                desired = str(cell.get("text") or "")
                                if table.rows[row_index].cells[cell_index].text != desired:
                                    table.rows[row_index].cells[cell_index].text = desired

            output = io.BytesIO()
            document.save(output)
            return ExportService._apply_document_v3_styles(output.getvalue(), session)
        except Exception as exc:
            logger.warning("Could not patch imported DOCX for %s: %s", session.id, exc)
            return None

    @staticmethod
    def _v3_region_text(session, region: str) -> str:
        raw = getattr(session, "document_v3", None)
        if not isinstance(raw, dict):
            return ""
        sections = raw.get("sections")
        if not isinstance(sections, list) or not sections or not isinstance(sections[0], dict):
            return ""
        header_footer = sections[0].get("headerFooter") or sections[0].get("header_footer")
        if not isinstance(header_footer, dict):
            return ""
        blocks = header_footer.get(region)
        if not isinstance(blocks, list):
            return ""

        parts: list[str] = []

        def collect(value) -> None:
            if isinstance(value, dict):
                text = value.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
                for key in ("content", "children", "rows", "cells"):
                    collect(value.get(key))
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(blocks)
        return "".join(parts).strip()

    @classmethod
    def _render_lightweight_pdf(cls, text: str, pdf_path: Path, session) -> None:
        """Render a dependency-light, multi-page PDF when office software is absent.

        CairoSVG already brings cairocffi into the application runtime, so this
        fallback adds no heavyweight browser or office-suite dependency.  It is
        intentionally conservative: Unicode text, paragraphs, title emphasis,
        headers, footers and live page numbers are preserved.
        """
        try:
            import cairocffi as cairo
        except Exception as exc:  # pragma: no cover - protected by dependency metadata
            raise RuntimeError("cairocffi not available for lightweight PDF export") from exc

        width, height = 595.28, 841.89  # A4 points
        margin_x, margin_top, margin_bottom = 72.0, 72.0, 72.0
        body_width = width - margin_x * 2
        font_family = "Microsoft YaHei" if os.name == "nt" else "Noto Sans CJK SC"
        measure_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        measure = cairo.Context(measure_surface)

        def wrapped_lines(value: str, size: float) -> list[str]:
            measure.select_font_face(font_family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            measure.set_font_size(size)
            value = str(value or "").replace("\t", "    ")
            if not value:
                return [""]
            lines: list[str] = []
            current = ""
            for char in value:
                candidate = current + char
                if current and measure.text_extents(candidate)[4] > body_width:
                    lines.append(current)
                    current = char
                else:
                    current = candidate
            lines.append(current)
            return lines

        paragraphs = str(text or "").replace("\r", "").split("\n")
        rows: list[tuple[str, float, bool, float]] = []
        first_content = True
        for raw_line in paragraphs:
            stripped = raw_line.strip()
            if not stripped:
                rows.append(("", 11.5, False, 9.0))
                continue
            heading = len(stripped) - len(stripped.lstrip("#"))
            content = stripped[heading:].strip() if heading else stripped
            is_title = first_content
            size = 18.0 if is_title else (16.0 if heading == 1 else 14.0 if heading == 2 else 11.5)
            bold = is_title or heading > 0
            line_height = size * 1.6
            for line in wrapped_lines(content, size):
                rows.append((line, size, bold, line_height))
            rows.append(("", 11.5, False, 6.0 if is_title or heading else 3.0))
            first_content = False

        usable_height = height - margin_top - margin_bottom
        pages: list[list[tuple[str, float, bool, float]]] = [[]]
        used = 0.0
        for row in rows:
            row_height = row[3]
            if pages[-1] and used + row_height > usable_height:
                pages.append([])
                used = 0.0
            pages[-1].append(row)
            used += row_height
        if not pages:
            pages = [[]]

        header = cls._v3_region_text(session, "header")
        footer = cls._v3_region_text(session, "footer")
        surface = cairo.PDFSurface(str(pdf_path), width, height)
        context = cairo.Context(surface)
        for page_index, page_rows in enumerate(pages, start=1):
            context.set_source_rgb(1, 1, 1)
            context.paint()
            context.set_source_rgb(0.12, 0.14, 0.17)
            if header:
                context.select_font_face(font_family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                context.set_font_size(9.0)
                context.move_to(margin_x, 38.0)
                context.show_text(header)
            y = margin_top
            for line, size, bold, line_height in page_rows:
                y += line_height
                if not line:
                    continue
                context.select_font_face(
                    font_family,
                    cairo.FONT_SLANT_NORMAL,
                    cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
                )
                context.set_font_size(size)
                context.move_to(margin_x, y)
                context.show_text(line)
            context.select_font_face(font_family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            context.set_font_size(9.0)
            if footer:
                context.move_to(margin_x, height - 35.0)
                context.show_text(footer)
            page_label = f"第 {page_index} 页，共 {len(pages)} 页"
            extents = context.text_extents(page_label)
            context.move_to((width - extents[4]) / 2, height - 35.0)
            context.show_text(page_label)
            context.show_page()
        surface.finish()

    @staticmethod
    def _apply_document_v3_styles(payload: bytes, session) -> bytes:
        """Project canonical V3 paragraph styles into the generated Word file.

        The legacy exporter remains responsible for complex document objects,
        while this final pass makes the saved V3 style library authoritative for
        paragraph appearance in Word.  Invalid or absent V3 data leaves the
        already-valid DOCX untouched.
        """
        raw = getattr(session, "document_v3", None)
        if not isinstance(raw, dict) or not isinstance(raw.get("styles"), list):
            return payload
        try:
            from docx import Document
            from docx.enum.style import WD_STYLE_TYPE
            from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
            from docx.shared import Pt, RGBColor
        except Exception:
            return payload

        styles = [item for item in raw.get("styles", []) if isinstance(item, dict) and item.get("id")]
        if not styles:
            return payload
        by_id = {str(item["id"]): item for item in styles}

        def node_text(value) -> str:
            if isinstance(value, dict):
                return str(value.get("text") or "") + "".join(node_text(child) for child in value.get("content") or [])
            if isinstance(value, list):
                return "".join(node_text(child) for child in value)
            return ""

        def properties(style_id: str, visiting: set[str] | None = None) -> dict:
            visiting = set(visiting or ())
            if style_id in visiting:
                return {}
            visiting.add(style_id)
            style = by_id.get(style_id, {})
            inherited = properties(str(style.get("basedOn") or style.get("based_on") or ""), visiting) if (style.get("basedOn") or style.get("based_on")) else {}
            raw_own = style.get("properties") if isinstance(style.get("properties"), dict) else {}
            own = {key: value for key, value in raw_own.items() if value is not None}
            return {**inherited, **own}

        builtin_names = {
            "normal": "Normal",
            "title": "Title",
            "subtitle": "Subtitle",
            "quote": "Quote",
            "caption": "Caption",
            **{f"heading-{level}": f"Heading {level}" for level in range(1, 7)},
        }
        document = Document(io.BytesIO(payload))
        numbering_definitions = [item for item in raw.get("numbering", []) if isinstance(item, dict) and item.get("id")]
        word_num_ids: dict[str, int] = {}
        if numbering_definitions:
            numbering_root = document.part.numbering_part.element
            abstract_ids = [int(value) for value in numbering_root.xpath("./w:abstractNum/@w:abstractNumId") if str(value).isdigit()]
            number_ids = [int(value) for value in numbering_root.xpath("./w:num/@w:numId") if str(value).isdigit()]
            next_abstract_id = max(abstract_ids, default=-1) + 1
            next_num_id = max(number_ids, default=0) + 1
            format_names = {
                "bullet": "bullet",
                "decimal": "decimal",
                "lowerLetter": "lowerLetter",
                "upperLetter": "upperLetter",
                "lowerRoman": "lowerRoman",
                "upperRoman": "upperRoman",
            }
            for definition in numbering_definitions:
                abstract_id = next_abstract_id
                num_id = next_num_id
                next_abstract_id += 1
                next_num_id += 1
                abstract = OxmlElement("w:abstractNum")
                abstract.set(qn("w:abstractNumId"), str(abstract_id))
                multi = OxmlElement("w:multiLevelType")
                multi.set(qn("w:val"), "multilevel")
                abstract.append(multi)
                for raw_level in sorted((level for level in definition.get("levels", []) if isinstance(level, dict)), key=lambda level: int(level.get("level") or 0)):
                    level_index = max(0, min(8, int(raw_level.get("level") or 0)))
                    level = OxmlElement("w:lvl")
                    level.set(qn("w:ilvl"), str(level_index))
                    start = OxmlElement("w:start")
                    start.set(qn("w:val"), str(max(1, int(raw_level.get("startAt") or 1))))
                    level.append(start)
                    num_fmt = OxmlElement("w:numFmt")
                    num_fmt.set(qn("w:val"), format_names.get(str(raw_level.get("format") or "decimal"), "decimal"))
                    level.append(num_fmt)
                    level_text = OxmlElement("w:lvlText")
                    level_text.set(qn("w:val"), str(raw_level.get("bulletChar") or raw_level.get("text") or f"%{level_index + 1}."))
                    level.append(level_text)
                    suffix = OxmlElement("w:suff")
                    suffix.set(qn("w:val"), "tab")
                    level.append(suffix)
                    paragraph_properties = OxmlElement("w:pPr")
                    tabs = OxmlElement("w:tabs")
                    tab = OxmlElement("w:tab")
                    tab.set(qn("w:val"), "num")
                    font_pt = 12.0
                    left_twips = round(float(raw_level.get("leftIndentEm") or 0) * font_pt * 20)
                    hanging_twips = round(float(raw_level.get("hangingIndentEm") or 0) * font_pt * 20)
                    tab.set(qn("w:pos"), str(max(0, left_twips)))
                    tabs.append(tab)
                    paragraph_properties.append(tabs)
                    indent = OxmlElement("w:ind")
                    indent.set(qn("w:left"), str(max(0, left_twips)))
                    indent.set(qn("w:hanging"), str(max(0, hanging_twips)))
                    paragraph_properties.append(indent)
                    level.append(paragraph_properties)
                    abstract.append(level)
                numbering_root.append(abstract)
                number = OxmlElement("w:num")
                number.set(qn("w:numId"), str(num_id))
                abstract_ref = OxmlElement("w:abstractNumId")
                abstract_ref.set(qn("w:val"), str(abstract_id))
                number.append(abstract_ref)
                numbering_root.append(number)
                word_num_ids[str(definition["id"])] = num_id
        v3_text_blocks: list[str] = []
        for section in raw.get("sections") or []:
            if not isinstance(section, dict):
                continue
            for block in section.get("content") or []:
                if isinstance(block, dict) and block.get("type") in {"paragraph", "heading", "blockquote", "codeBlock"}:
                    text = node_text(block).strip()
                    if text:
                        v3_text_blocks.append(text)
        if v3_text_blocks and len(document.paragraphs) >= 2:
            compact = lambda value: re.sub(r"\s+", "", str(value or ""))
            first = compact(v3_text_blocks[0])
            v3_intentionally_repeats = len(v3_text_blocks) > 1 and compact(v3_text_blocks[1]) == first
            nonempty_paragraphs = [paragraph for paragraph in document.paragraphs if compact(paragraph.text)]
            if not v3_intentionally_repeats and len(nonempty_paragraphs) >= 2 and compact(nonempty_paragraphs[0].text) == first and compact(nonempty_paragraphs[1].text) == first:
                duplicate = nonempty_paragraphs[0]._element
                duplicate.getparent().remove(duplicate)
        word_names: dict[str, str] = {}
        for item in styles:
            style_id = str(item["id"])
            preferred = builtin_names.get(style_id) or str(item.get("name") or style_id)
            name = preferred
            try:
                word_style = document.styles[name]
                if word_style.type != WD_STYLE_TYPE.PARAGRAPH:
                    raise KeyError(name)
            except KeyError:
                suffix = 1
                while True:
                    try:
                        document.styles[name]
                        suffix += 1
                        name = f"{preferred} ({suffix})"
                    except KeyError:
                        break
                word_style = document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            word_names[style_id] = name

        alignments = {
            "left": WD_ALIGN_PARAGRAPH.LEFT,
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
            "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
        }
        tab_alignments = {
            "left": WD_TAB_ALIGNMENT.LEFT,
            "center": WD_TAB_ALIGNMENT.CENTER,
            "right": WD_TAB_ALIGNMENT.RIGHT,
            "decimal": WD_TAB_ALIGNMENT.DECIMAL,
        }

        def color(value):
            token = str(value or "").strip().lstrip("#")
            return RGBColor.from_string(token.upper()) if re.fullmatch(r"[0-9a-fA-F]{6}", token) else None

        for item in styles:
            style_id = str(item["id"])
            word_style = document.styles[word_names[style_id]]
            based_on = str(item.get("basedOn") or item.get("based_on") or "")
            next_style = str(item.get("nextStyle") or item.get("next_style") or "")
            if based_on in word_names and based_on != style_id:
                word_style.base_style = document.styles[word_names[based_on]]
            if next_style in word_names:
                word_style.next_paragraph_style = document.styles[word_names[next_style]]
            p = properties(style_id)
            font = word_style.font
            if p.get("fontFamily"):
                font.name = str(p["fontFamily"])
                font._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), str(p["fontFamily"]))
            if p.get("fontSizePt") is not None:
                font.size = Pt(float(p["fontSizePt"]))
            for key in ("bold", "italic", "underline"):
                if key in p and p[key] is not None:
                    setattr(font, key, bool(p[key]))
            font_color = color(p.get("color"))
            if font_color is not None:
                font.color.rgb = font_color
            if p.get("textTransform") == "uppercase":
                font.all_caps = True
            elif p.get("textTransform") == "none":
                font.all_caps = False
            if p.get("letterSpacingPt") is not None:
                r_pr = word_style._element.get_or_add_rPr()
                spacing = r_pr.find(qn("w:spacing"))
                if spacing is None:
                    spacing = OxmlElement("w:spacing")
                    r_pr.append(spacing)
                spacing.set(qn("w:val"), str(round(float(p["letterSpacingPt"]) * 20)))
            fmt = word_style.paragraph_format
            if p.get("alignment") in alignments:
                fmt.alignment = alignments[p["alignment"]]
            if p.get("lineSpacing") is not None:
                fmt.line_spacing = float(p["lineSpacing"])
            font_pt = float(p.get("fontSizePt") or 12)
            if p.get("firstLineIndentEm") is not None:
                fmt.first_line_indent = Pt(float(p["firstLineIndentEm"]) * font_pt)
            if p.get("leftIndentEm") is not None:
                fmt.left_indent = Pt(float(p["leftIndentEm"]) * font_pt)
            if p.get("rightIndentEm") is not None:
                fmt.right_indent = Pt(float(p["rightIndentEm"]) * font_pt)
            if p.get("spaceBeforePt") is not None:
                fmt.space_before = Pt(float(p["spaceBeforePt"]))
            if p.get("spaceAfterPt") is not None:
                fmt.space_after = Pt(float(p["spaceAfterPt"]))
            if p.get("keepWithNext") is not None:
                fmt.keep_with_next = bool(p["keepWithNext"])
            if p.get("keepLinesTogether") is not None:
                fmt.keep_together = bool(p["keepLinesTogether"])
            if p.get("pageBreakBefore") is not None:
                fmt.page_break_before = bool(p["pageBreakBefore"])
            for tab in p.get("tabStops") or []:
                if isinstance(tab, dict) and tab.get("alignment") in tab_alignments:
                    fmt.tab_stops.add_tab_stop(Pt(float(tab.get("positionEm") or 0) * font_pt), tab_alignments[tab["alignment"]])
            p_pr = word_style._element.get_or_add_pPr()
            numbering_id = str(p.get("numberingId") or "")
            if numbering_id in word_num_ids:
                num_pr = p_pr.find(qn("w:numPr"))
                if num_pr is None:
                    num_pr = OxmlElement("w:numPr")
                    p_pr.append(num_pr)
                ilvl = num_pr.find(qn("w:ilvl"))
                if ilvl is None:
                    ilvl = OxmlElement("w:ilvl")
                    num_pr.append(ilvl)
                ilvl.set(qn("w:val"), str(max(0, min(8, int(p.get("numberingLevel") or 0)))))
                num_id = num_pr.find(qn("w:numId"))
                if num_id is None:
                    num_id = OxmlElement("w:numId")
                    num_pr.append(num_id)
                num_id.set(qn("w:val"), str(word_num_ids[numbering_id]))
            if p.get("outlineLevel") is not None:
                outline = p_pr.find(qn("w:outlineLvl"))
                if outline is None:
                    outline = OxmlElement("w:outlineLvl")
                outline.set(qn("w:val"), str(max(0, int(p["outlineLevel"]) - 1)))
                if outline.getparent() is None:
                    p_pr.append(outline)
            shading = color(p.get("shadingColor") or p.get("backgroundColor"))
            if shading is not None:
                shd = p_pr.find(qn("w:shd"))
                if shd is None:
                    shd = OxmlElement("w:shd")
                shd.set(qn("w:fill"), str(shading))
                if shd.getparent() is None:
                    p_pr.append(shd)
            border_style = str(p.get("borderStyle") or "")
            if border_style:
                borders = p_pr.find(qn("w:pBdr"))
                if borders is None:
                    borders = OxmlElement("w:pBdr")
                    p_pr.append(borders)
                word_border = {"solid": "single", "dashed": "dashed", "double": "double", "none": "nil"}.get(border_style, "single")
                border_color = str(p.get("borderColor") or "000000").lstrip("#")
                border_size = max(0, round(float(p.get("borderWidthPt") or 0.5) * 8))
                for side in ("top", "left", "bottom", "right"):
                    edge = borders.find(qn(f"w:{side}"))
                    if edge is None:
                        edge = OxmlElement(f"w:{side}")
                        borders.append(edge)
                    edge.set(qn("w:val"), word_border)
                    edge.set(qn("w:sz"), str(border_size))
                    edge.set(qn("w:color"), border_color)

        styled_blocks: list[tuple[str, str, str, int]] = []
        def collect_blocks(nodes, inherited_numbering_id: str = "", inherited_level: int = 0) -> None:
            for node in nodes or []:
                if not isinstance(node, dict):
                    continue
                style_id = str(node.get("styleId") or node.get("style_id") or "")
                attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
                numbering_id = str(attrs.get("numberingId") or attrs.get("numbering_id") or inherited_numbering_id)
                numbering_level = max(0, min(8, int(attrs.get("numberingLevel") or attrs.get("numbering_level") or inherited_level)))
                text = node_text(node).strip()
                if text and (style_id in word_names or numbering_id in word_num_ids) and node.get("type") not in {"bulletList", "orderedList", "listItem"}:
                    styled_blocks.append((text, style_id, numbering_id, numbering_level))
                content = node.get("content")
                if isinstance(content, list) and node.get("type") in {"bulletList", "orderedList", "listItem"}:
                    collect_blocks(content, numbering_id, numbering_level)
        for section in raw.get("sections") or []:
            if isinstance(section, dict):
                collect_blocks(section.get("content") or [])

        paragraph_index = 0
        for text, style_id, numbering_id, numbering_level in styled_blocks:
            wanted = re.sub(r"\s+", "", text)
            for index in range(paragraph_index, len(document.paragraphs)):
                if re.sub(r"\s+", "", document.paragraphs[index].text) == wanted:
                    paragraph = document.paragraphs[index]
                    if style_id in word_names:
                        paragraph.style = document.styles[word_names[style_id]]
                    if numbering_id in word_num_ids:
                        p_pr = paragraph._p.get_or_add_pPr()
                        num_pr = p_pr.find(qn("w:numPr"))
                        if num_pr is None:
                            num_pr = OxmlElement("w:numPr")
                            p_pr.append(num_pr)
                        ilvl = num_pr.find(qn("w:ilvl"))
                        if ilvl is None:
                            ilvl = OxmlElement("w:ilvl")
                            num_pr.append(ilvl)
                        ilvl.set(qn("w:val"), str(numbering_level))
                        num_id = num_pr.find(qn("w:numId"))
                        if num_id is None:
                            num_id = OxmlElement("w:numId")
                            num_pr.append(num_id)
                        num_id.set(qn("w:val"), str(word_num_ids[numbering_id]))
                    paragraph_index = index + 1
                    break
        output = io.BytesIO()
        document.save(output)
        return output.getvalue()

    @staticmethod
    def _compact_for_compare(text: str) -> str:
        return re.sub(r"\s+", "", str(text or ""))

    @staticmethod
    def _document_v3_export_text(session, fallback: str) -> str:
        raw = getattr(session, "document_v3", None)
        if not isinstance(raw, dict):
            return fallback
        try:
            from writing_agent.v3 import DocumentV3
            from writing_agent.v3.document_model import to_plain_text

            return to_plain_text(DocumentV3.model_validate(raw), include_resource_data=True) or fallback
        except Exception:
            return fallback

    @staticmethod
    def _canonicalize_docx_payload(payload: bytes) -> tuple[bytes, str]:
        """
        Best-effort DOCX normalization for Word compatibility.
        Returns (payload, status) where status is one of:
        - skipped
        - canonicalized
        - failed:<reason>
        """
        raw_flag = str(os.environ.get("WRITING_AGENT_DOCX_CANONICALIZE", "0")).strip().lower()
        enabled = raw_flag in {"1", "true", "yes", "on"}
        if not enabled:
            return payload, "skipped"
        try:
            from docx import Document as PythonDocxDocument  # type: ignore
        except Exception as exc:
            return payload, f"failed:python-docx-unavailable:{exc}"

        try:
            src = io.BytesIO(payload)
            doc = PythonDocxDocument(src)
            out = io.BytesIO()
            doc.save(out)
            normalized = out.getvalue()
            if not normalized:
                return payload, "failed:empty-output"
            return normalized, "canonicalized"
        except Exception as exc:
            return payload, f"failed:{exc}"

    @staticmethod
    def _docx_validation_enforce_enabled() -> bool:
        raw = str(os.environ.get("WRITING_AGENT_DOCX_VALIDATION_ENFORCE", "1")).strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def export_check(self, doc_id: str, format: str = "docx", auto_fix: int = 1) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")

        policy = app_v2._export_gate_policy(session)
        text = app_v2._safe_doc_text(session)
        if not str(text or "").strip():
            return {
                "ok": 1,
                "format": format,
                "policy": policy,
                "can_export": False,
                "issues": [{"code": "empty_document", "message": "document is empty", "blocking": True}],
                "warnings": [],
            }

        report = app_v2._export_quality_report(session, text, auto_fix=bool(auto_fix))
        return {
            "ok": 1,
            "format": format,
            "policy": str(report.get("policy") or policy),
            "can_export": bool(report.get("can_export")),
            "issues": report.get("issues", []),
            "warnings": report.get("warnings", []),
            "fixed_preview_chars": len(str(report.get("fixed_text") or "").strip()),
        }

    def download_docx(self, doc_id: str) -> StreamingResponse:
        app_v2 = app_v2_module()
        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        base_text = app_v2._safe_doc_text(session)
        use_autofix = bool(app_v2._strict_doc_format_enabled(session))
        quality = app_v2._export_quality_report(session, base_text, auto_fix=use_autofix)
        app_v2._raise_export_blocking_error(quality)
        original_payload = self._unchanged_imported_docx(session)
        imported_payload = original_payload or self._patched_imported_docx(session)
        if imported_payload is not None:
            issues = app_v2._validate_docx_bytes(imported_payload)
            if issues and self._docx_validation_enforce_enabled():
                raise app_v2.HTTPException(status_code=500, detail=f"DOCX导出失败：原文档结构校验未通过（{';'.join(issues[:4])}）")
            filename = str(getattr(session, "import_source_name", "") or session.title or "document.docx")
            if not filename.lower().endswith(".docx"):
                filename += ".docx"
            filename = re.sub(r'[\r\n"]+', "", filename)
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename) or "document.docx"
            quoted = quote(filename, safe="")
            return StreamingResponse(
                io.BytesIO(imported_payload),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{quoted}',
                    "X-Docx-Export-Backend": "lossless_import_roundtrip" if original_payload is not None else "structured_import_patch",
                    "X-Docx-Style-Path": "source_document" if original_payload is not None else "source_document_patch",
                    "X-Docx-Validation": "warning" if issues else "ok",
                },
            )
        fixed_text = str(quality.get("fixed_text") or base_text)
        if fixed_text and fixed_text != base_text:
            base_text = fixed_text
            if app_v2._persist_export_autofix_enabled():
                app_v2._set_doc_text(session, fixed_text)
                app_v2.store.put(session)
        base_text = self._document_v3_export_text(session, base_text)
        doc_ir = None
        if session.doc_ir:
            try:
                doc_ir = app_v2.doc_ir_from_dict(session.doc_ir)
            except Exception:
                doc_ir = None
        if doc_ir is not None:
            try:
                doc_ir_text = app_v2.doc_ir_to_text(doc_ir)
            except Exception:
                doc_ir_text = ""
            # Guard against stale doc_ir after postprocess/repair: export should reflect latest text.
            if self._compact_for_compare(doc_ir_text) != self._compact_for_compare(base_text):
                try:
                    text = app_v2._normalize_export_text(base_text, session=session)
                    doc_ir = app_v2.doc_ir_from_text(text)
                except Exception:
                    doc_ir = None
        if doc_ir is None:
            if not (base_text or "").strip():
                raise app_v2.HTTPException(status_code=400, detail="document is empty")
            text = app_v2._normalize_export_text(base_text, session=session)
            doc_ir = app_v2.doc_ir_from_text(text)
        doc_ir = app_v2._normalize_doc_ir_for_export(doc_ir, session)
        style = app_v2._citation_style_from_session(session)
        doc_ir = app_v2._apply_citations_to_doc_ir(doc_ir, session.citations or {}, style)
        parsed = app_v2.doc_ir_to_parsed(doc_ir)
        fmt = app_v2._formatting_from_session(session)
        prefs = app_v2._export_prefs_from_session(session)
        export_backend = "parsed_docx_exporter"
        export_style_path = "parsed_single_mode"
        backend_mode = self._SINGLE_DOCX_BACKEND_MODE
        template_path = app_v2._resolve_export_template_path(session)
        payload = app_v2.docx_exporter.build_from_parsed(parsed, fmt, prefs, template_path=template_path or None)
        payload = self._apply_document_v3_styles(payload, session)
        payload, canonicalize_status = self._canonicalize_docx_payload(payload)
        issues = app_v2._validate_docx_bytes(payload)
        repair_strategy = "none"
        if issues:
            # Last-resort fallback: remove TOC/header/page-number complexity and rebuild.
            # We prefer returning a compatible document over returning a potentially broken one.
            try:
                fallback_prefs = replace(
                    prefs,
                    include_toc=False,
                    include_header=False,
                    page_numbers=False,
                )
                fallback_payload = app_v2.docx_exporter.build_from_parsed(
                    parsed, fmt, fallback_prefs, template_path=template_path or None
                )
                fallback_payload = self._apply_document_v3_styles(fallback_payload, session)
                fallback_payload, fallback_canon = self._canonicalize_docx_payload(fallback_payload)
                fallback_issues = app_v2._validate_docx_bytes(fallback_payload)
                if not fallback_issues:
                    payload = fallback_payload
                    issues = []
                    canonicalize_status = fallback_canon
                    repair_strategy = "fallback_no_toc_header_pagenum"
                    export_style_path = "parsed_single_mode_fallback"
                else:
                    issues.extend([f"fallback:{x}" for x in fallback_issues if x])
                    repair_strategy = "fallback_failed"
            except Exception as exc:
                issues.append(f"fallback-build:{exc}")
                repair_strategy = "fallback_exception"
        if issues:
            app_v2.logger.warning(f"[docx-validate] {doc_id}: " + ";".join(issues))
            if self._docx_validation_enforce_enabled():
                raise app_v2.HTTPException(
                    status_code=500,
                    detail=f"DOCX导出失败：结构校验未通过（{';'.join(issues[:4])}）",
                )
        filename = f"{parsed.title or 'document'}.docx"
        filename = re.sub(r'[\r\n"]+', "", filename)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename) or "document.docx"
        quoted = quote(filename, safe="")
        headers = {
            "Content-Disposition": f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{quoted}',
            "X-Docx-Export-Backend": export_backend,
            "X-Docx-Style-Path": export_style_path,
            "X-Docx-Template": Path(template_path).name if 'template_path' in locals() and template_path else "",
            "X-Docx-Export-Policy": str(quality.get("policy") or ""),
            "X-Docx-Validation": "warning" if issues else "ok",
            "X-Docx-Canonicalized": canonicalize_status,
            "X-Docx-Backend-Mode": backend_mode,
            "X-Docx-Repair": repair_strategy,
        }
        if issues:
            headers["X-Docx-Warn"] = ",".join(issues)[:256]
        return StreamingResponse(
            io.BytesIO(payload),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )

    def download_pdf(self, doc_id: str) -> StreamingResponse:
        app_v2 = app_v2_module()
        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        original_docx = self._unchanged_imported_docx(session) or self._patched_imported_docx(session)
        base_text = self._document_v3_export_text(session, app_v2._safe_doc_text(session))
        doc_ir = None
        if session.doc_ir:
            try:
                doc_ir = app_v2.doc_ir_from_dict(session.doc_ir)
            except Exception:
                doc_ir = None
        if doc_ir is None:
            if not (base_text or "").strip():
                raise app_v2.HTTPException(status_code=400, detail="document is empty")
            text = app_v2._normalize_export_text(base_text, session=session)
            doc_ir = app_v2.doc_ir_from_text(text)
        doc_ir = app_v2._normalize_doc_ir_for_export(doc_ir, session)
        style = app_v2._citation_style_from_session(session)
        doc_ir = app_v2._apply_citations_to_doc_ir(doc_ir, session.citations or {}, style)
        parsed = app_v2.doc_ir_to_parsed(doc_ir)
        fmt = app_v2._formatting_from_session(session)
        prefs = app_v2._export_prefs_from_session(session)
        template_path = app_v2._resolve_export_template_path(session)
        docx_bytes = original_docx or app_v2.docx_exporter.build_from_parsed(parsed, fmt, prefs, template_path=template_path or None)
        if original_docx is None:
            docx_bytes = self._apply_document_v3_styles(docx_bytes, session)
        issues = app_v2._validate_docx_bytes(docx_bytes)
        if issues and self._docx_validation_enforce_enabled():
            raise app_v2.HTTPException(
                status_code=500,
                detail=f"PDF导出失败：中间DOCX校验未通过（{';'.join(issues[:4])}）",
            )
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
            tmp_docx.write(docx_bytes)
            tmp_docx_path = Path(tmp_docx.name)
        tmp_pdf_path = tmp_docx_path.with_suffix(".pdf")
        try:
            try:
                app_v2._convert_docx_to_pdf(tmp_docx_path, tmp_pdf_path)
            except RuntimeError as exc:
                if "not available for PDF export" not in str(exc):
                    raise
                self._render_lightweight_pdf(base_text, tmp_pdf_path, session)
            with open(tmp_pdf_path, "rb") as f:
                pdf_bytes = f.read()
            filename = f"{parsed.title or 'document'}.pdf"
            filename = re.sub(r'[\r\n"]+', "", filename)
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename) or "document.pdf"
            quoted = quote(filename, safe="")
            headers = {"Content-Disposition": f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{quoted}'}
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type="application/pdf",
                headers=headers,
            )
        finally:
            try:
                tmp_docx_path.unlink(missing_ok=True)
                tmp_pdf_path.unlink(missing_ok=True)
            except Exception as _exc:
                logger.debug("Ignored error in export_service.py: %s", _exc, exc_info=True)

    def export_multi_format(self, doc_id: str, format: str) -> Response:
        app_v2 = app_v2_module()
        session = app_v2.store.get(doc_id)
        if not session:
            raise app_v2.HTTPException(404, "document not found")

        text = session.doc_text or ""
        if not text.strip():
            raise app_v2.HTTPException(400, "document is empty")

        title = app_v2._extract_title(text)

        if format == "md":
            metadata = f"""---
title: {title}
author: user
date: {datetime.now().strftime('%Y-%m-%d')}
version: {session.current_version_id or 'draft'}
---
"""
            content = metadata + text
            return Response(
                content=content.encode("utf-8"),
                media_type="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="{quote(title)}.md"'},
            )

        if format == "html":
            parsed = app_v2.parse_report_text(text)
            html_body = app_v2._render_blocks_to_html(parsed.blocks)
            full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: 'Times New Roman', 'SimSun', serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 20px; }}
        h1 {{ text-align: center; font-size: 24pt; margin-bottom: 20px; }}
        h2 {{ font-size: 18pt; margin-top: 20px; }}
        h3 {{ font-size: 14pt; margin-top: 16px; }}
        p {{ text-align: justify; text-indent: 2em; margin-bottom: 12px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        .citation-ref {{ color: #0066cc; font-size: 0.85em; font-weight: 600; vertical-align: super; }}
    </style>
</head>
<body>
{html_body}
</body>
</html>"""
            return Response(
                content=full_html.encode("utf-8"),
                media_type="text/html",
                headers={"Content-Disposition": f'attachment; filename="{quote(title)}.html"'},
            )

        if format == "tex":
            latex_content = app_v2._convert_to_latex(text, title)
            return Response(
                content=latex_content.encode("utf-8"),
                media_type="application/x-latex",
                headers={"Content-Disposition": f'attachment; filename="{quote(title)}.tex"'},
            )

        if format == "txt":
            plain = re.sub(r'#{1,3}\s+', '', text)
            plain = re.sub(r'\*\*(.+?)\*\*', r'\1', plain)
            plain = re.sub(r'\*(.+?)\*', r'\1', plain)
            plain = re.sub(r'\[@([a-zA-Z0-9_-]+)\]', '', plain)
            return Response(
                content=plain.encode("utf-8"),
                media_type="text/plain",
                headers={"Content-Disposition": f'attachment; filename="{quote(title)}.txt"'},
            )

        raise app_v2.HTTPException(400, f"unsupported format: {format}, expected one of md/html/tex/txt")
