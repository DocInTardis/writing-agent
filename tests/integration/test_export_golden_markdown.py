from pathlib import Path

from writing_agent.v2.doc_format import parse_report_text


def test_golden_markdown_parse_shape() -> None:
    text = Path('tests/fixtures/golden/report.md').read_text(encoding='utf-8')
    parsed = parse_report_text(text)
    assert parsed.title
    assert any((b.type == 'heading' and (b.text or '').strip() == '背景') for b in parsed.blocks)
    assert any((b.type == 'heading' and (b.text or '').strip() == '方案') for b in parsed.blocks)
    assert any((b.type == 'heading' and (b.text or '').strip() == '结论') for b in parsed.blocks)
