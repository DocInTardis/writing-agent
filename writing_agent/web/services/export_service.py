"""Export Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import io
import re
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi.responses import Response, StreamingResponse

from .base import app_v2_module


class ExportService:
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
        export_backend = "unknown"
        export_style_path = "plain"
        use_html = app_v2._doc_ir_has_styles(doc_ir)
        if use_html:
            export_backend = "html_docx_exporter"
            export_style_path = "styled_doc_ir"
            html = app_v2._doc_ir_to_html(doc_ir)
            payload = app_v2.html_docx_exporter.build(html, fmt)
        else:
            export_style_path = "parsed_text"
            template_path = app_v2._resolve_export_template_path(session)
            try:
                text = app_v2.doc_ir_to_text(doc_ir)
            except Exception:
                text = base_text
            text = app_v2._normalize_export_text(text, session=session)
            rust_payload = app_v2._try_rust_docx_export(text)
            if rust_payload:
                export_backend = "rust_docx_export"
                payload = rust_payload
            else:
                export_backend = "parsed_docx_exporter"
                payload = app_v2.docx_exporter.build_from_parsed(parsed, fmt, prefs, template_path=template_path or None)
        issues = app_v2._validate_docx_bytes(payload)
        if issues:
            app_v2.logger.warning(f"[docx-validate] {doc_id}: " + ";".join(issues))
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
        use_html = app_v2._doc_ir_has_styles(doc_ir)
        if use_html:
            html = app_v2._doc_ir_to_html(doc_ir)
            docx_bytes = app_v2.html_docx_exporter.build(html, fmt)
        else:
            template_path = app_v2._resolve_export_template_path(session)
            try:
                text = app_v2.doc_ir_to_text(doc_ir)
            except Exception:
                text = base_text
            text = app_v2._normalize_export_text(text, session=session)
            rust_payload = app_v2._try_rust_docx_export(text)
            if rust_payload:
                docx_bytes = rust_payload
            else:
                docx_bytes = app_v2.docx_exporter.build_from_parsed(parsed, fmt, prefs, template_path=template_path or None)
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
            tmp_docx.write(docx_bytes)
            tmp_docx_path = Path(tmp_docx.name)
        tmp_pdf_path = tmp_docx_path.with_suffix(".pdf")
        try:
            app_v2._convert_docx_to_pdf(tmp_docx_path, tmp_pdf_path)
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
            except Exception:
                pass

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
