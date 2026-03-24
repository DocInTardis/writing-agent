import io

import pytest
from docx import Document

from writing_agent.document.v2_report_docx import ExportPrefs, V2ReportDocxExporter
from writing_agent.document.v2_report_docx_helpers import _normalize_export_text, _sanitize_heading_text
from writing_agent.models import FormattingRequirements



def test_normalize_export_text_repairs_utf8_latin1_mojibake() -> None:
    source = "\u9ad8\u6821\u79d1\u7814"
    broken = source.encode("utf-8").decode("latin-1")
    assert _normalize_export_text(broken, field="paragraph") == source



def test_sanitize_heading_text_repairs_gb18030_mojibake_heading() -> None:
    source = "\u6458\u8981"
    broken = source.encode("utf-8").decode("gb18030")
    assert _sanitize_heading_text(broken) == source



def test_docx_export_rejects_unrepaired_mojibake() -> None:
    exporter = V2ReportDocxExporter()
    formatting = FormattingRequirements()
    prefs = ExportPrefs(include_cover=False, include_toc=False, include_header=False, page_numbers=False)
    bad = "\ufffdbroken-title"
    text = f"# {bad}\n\n## Intro\n\nBody"
    with pytest.raises(ValueError, match="docx_export_mojibake_detected"):
        exporter.build_from_text(text, formatting, prefs)



def test_docx_export_repairs_keywords_and_references_headings() -> None:
    exporter = V2ReportDocxExporter()
    formatting = FormattingRequirements()
    prefs = ExportPrefs(include_cover=False, include_toc=False, include_header=False, page_numbers=False)
    kw = "\u5173\u952e\u8bcd".encode("utf-8").decode("latin-1")
    refs = "\u53c2\u8003\u6587\u732e".encode("utf-8").decode("latin-1")
    text = (
        "# \u6d4b\u8bd5\n\n"
        "## \u6458\u8981\n\n\u8fd9\u662f\u6458\u8981\u3002\n\n"
        f"## {kw}\n\n\u533a\u5757\u94fe\uff1b\u519c\u6751\u670d\u52a1\uff1b\u534f\u540c\u6cbb\u7406\n\n"
        f"## {refs}\n\n[1] Example Ref. 2024. https://example.com"
    )
    docx_bytes = exporter.build_from_text(text, formatting, prefs)
    doc = Document(io.BytesIO(docx_bytes))
    body = "\n".join(p.text for p in doc.paragraphs if p.text)
    assert "\u5173\u952e\u8bcd" in body
    assert "\u53c2\u8003\u6587\u732e" in body
