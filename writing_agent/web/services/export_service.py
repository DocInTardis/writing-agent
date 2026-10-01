"""Export Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import io
import os
import re
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi.responses import Response, StreamingResponse

from .base import app_v2_module


class ExportService:
    _SINGLE_DOCX_BACKEND_MODE = "single_parsed"

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

        styled_blocks: list[tuple[str, str]] = []
        def collect_blocks(nodes) -> None:
            for node in nodes or []:
                if not isinstance(node, dict):
                    continue
                style_id = str(node.get("styleId") or node.get("style_id") or "")
                text = node_text(node).strip()
                if style_id in word_names and text:
                    styled_blocks.append((text, style_id))
                content = node.get("content")
                if isinstance(content, list) and node.get("type") in {"bulletList", "orderedList", "listItem"}:
                    collect_blocks(content)
        for section in raw.get("sections") or []:
            if isinstance(section, dict):
                collect_blocks(section.get("content") or [])

        paragraph_index = 0
        for text, style_id in styled_blocks:
            wanted = re.sub(r"\s+", "", text)
            for index in range(paragraph_index, len(document.paragraphs)):
                if re.sub(r"\s+", "", document.paragraphs[index].text) == wanted:
                    document.paragraphs[index].style = document.styles[word_names[style_id]]
                    paragraph_index = index + 1
                    break
        output = io.BytesIO()
        document.save(output)
        return output.getvalue()

    @staticmethod
    def _compact_for_compare(text: str) -> str:
        return re.sub(r"\s+", "", str(text or ""))

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
        fixed_text = str(quality.get("fixed_text") or base_text)
        if fixed_text and fixed_text != base_text:
            base_text = fixed_text
            if app_v2._persist_export_autofix_enabled():
                app_v2._set_doc_text(session, fixed_text)
                app_v2.store.put(session)
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
        base_text = app_v2._safe_doc_text(session)
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
        docx_bytes = app_v2.docx_exporter.build_from_parsed(parsed, fmt, prefs, template_path=template_path or None)
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
