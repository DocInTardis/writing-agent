from __future__ import annotations

from types import SimpleNamespace

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
