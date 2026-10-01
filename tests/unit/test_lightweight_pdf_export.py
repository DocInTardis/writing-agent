from __future__ import annotations

from types import SimpleNamespace
import io

from docx import Document

from writing_agent.web.services.export_service import ExportService


def test_lightweight_pdf_fallback_writes_unicode_pdf(tmp_path) -> None:
    session = SimpleNamespace(
        document_v3={
            "sections": [
                {
                    "headerFooter": {
                        "header": [{"content": [{"type": "text", "text": "论文页眉"}]}],
                        "footer": [{"content": [{"type": "text", "text": "论文页脚"}]}],
                    }
                }
            ]
        }
    )
    output = tmp_path / "fallback.pdf"
    text = "毕业论文标题\n\n" + "中文正文用于验证无 Office 环境的 PDF 导出。\n\n" * 180

    ExportService._render_lightweight_pdf(text, output, session)

    payload = output.read_bytes()
    assert payload.startswith(b"%PDF")
    assert len(payload) > 10_000
    assert payload.rstrip().endswith(b"%%EOF")


def test_document_v3_custom_style_is_projected_into_word_docx() -> None:
    document = Document()
    document.add_paragraph("需要按样式导出的正文")
    # The legacy parsed exporter can repeat the first V3 block as a synthetic
    # title.  The V3 projection pass must collapse that exporter artifact.
    document.add_paragraph("需要按样式导出的正文")
    source = io.BytesIO()
    document.save(source)
    session = SimpleNamespace(
        document_v3={
            "styles": [
                {
                    "id": "normal",
                    "name": "正文",
                    "kind": "paragraph",
                    "visible": True,
                    "properties": {"fontFamily": "SimSun", "fontSizePt": 12, "bold": True},
                },
                {
                    "id": "thesis-body",
                    "name": "论文正文",
                    "kind": "paragraph",
                    "basedOn": "normal",
                    "nextStyle": "thesis-body",
                    "visible": True,
                    "properties": {
                        "fontFamily": "Microsoft YaHei",
                        "fontSizePt": 11,
                        "bold": False,
                        "letterSpacingPt": 0.5,
                        "lineSpacing": 1.5,
                        "firstLineIndentEm": 2,
                        "borderStyle": "solid",
                        "borderColor": "#123456",
                        "borderWidthPt": 1,
                    },
                },
            ],
            "sections": [
                {
                    "content": [
                        {
                            "id": "p1",
                            "type": "paragraph",
                            "styleId": "thesis-body",
                            "content": [{"type": "text", "text": "需要按样式导出的正文"}],
                        }
                    ]
                }
            ],
        }
    )

    result = ExportService._apply_document_v3_styles(source.getvalue(), session)
    exported = Document(io.BytesIO(result))

    assert [paragraph.text for paragraph in exported.paragraphs] == ["需要按样式导出的正文"]
    assert exported.paragraphs[0].style.name == "论文正文"
    assert exported.styles["论文正文"].font.name == "Microsoft YaHei"
    assert exported.styles["论文正文"].font.size.pt == 11
    assert exported.styles["论文正文"].font.bold is False
    assert exported.styles["论文正文"].paragraph_format.line_spacing == 1.5
    style_xml = exported.styles["论文正文"]._element.xml
    assert 'w:spacing w:val="10"' in style_xml
    assert 'w:color="123456"' in style_xml
