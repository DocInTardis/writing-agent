# coding: utf-8
"""Docx Format Sample Check command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import os
import random
import re
from pathlib import Path
from docx import Document
from zipfile import ZipFile
import xml.etree.ElementTree as ET

OUT = Path('.data') / 'out'
SAMPLE_N = int(os.environ.get('SAMPLE_N', '10'))
SEED = int(os.environ.get('SAMPLE_SEED', '7'))

random.seed(SEED)

def is_heading(p) -> bool:
    try:
        name = (p.style.name or '').lower()
    except Exception:
        name = ''
    if 'heading' in name or '标题' in name:
        return True
    txt = (p.text or '').strip()
    return bool(re.match(r'^第\d+章\s*\S+', txt) or re.match(r'^\d+\.\d+\s+\S+', txt))


def check_doc(path: Path) -> dict:
    doc = Document(str(path))
    paras = [p for p in doc.paragraphs if p.text and p.text.strip()]
    texts = [p.text.strip() for p in paras]
    toc = any(t in s for s in texts for t in ('目录', '目 录'))
    ref = any('参考文献' in s for s in texts)
    bad = any('####' in s or '乱码占位' in s or '？？？' in s for s in texts)

    headings = [p for p in paras if is_heading(p)]
    body = [p for p in paras if not is_heading(p)]

    # indent check: first_line_indent in twips (1/20 pt). If None -> 0.
    indents = []
    for p in body:
        try:
            ind = p.paragraph_format.first_line_indent
            if ind is None:
                indents.append(0)
            else:
                indents.append(int(ind))
        except Exception:
            indents.append(0)

    # count paragraphs with non-zero first-line indent
    indent_ok = sum(1 for v in indents if v >= 200)  # ~10pt
    indent_rate = (indent_ok / max(1, len(indents))) if indents else 0.0

    # font check (best-effort): majority font name
    fonts = []
    for p in body[:80]:
        for run in p.runs[:3]:
            name = (run.font.name or '').strip()
            if name:
                fonts.append(name)
    font_main = ''
    if fonts:
        font_main = max(set(fonts), key=fonts.count)

    # line spacing (best-effort)
    spacing_vals = []
    for p in body[:120]:
        try:
            ls = p.paragraph_format.line_spacing
        except Exception:
            ls = None
        if ls is None:
            continue
        try:
            spacing_vals.append(float(ls))
        except Exception:
            pass
    line_spacing_main = None
    if spacing_vals:
        line_spacing_main = max(set(spacing_vals), key=spacing_vals.count)
    line_spacing_rate = 0.0
    if spacing_vals:
        line_spacing_rate = sum(1 for v in spacing_vals if 1.45 <= v <= 1.6) / max(1, len(spacing_vals))

    # margins / headers / footers / page numbering (via XML)
    margins = {}
    has_header = False
    has_footer = False
    has_page_field = False
    has_pg_num_type = False
    with ZipFile(path, 'r') as zf:
        if 'word/document.xml' in zf.namelist():
            root = ET.fromstring(zf.read('word/document.xml'))
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            sect = root.find('.//w:sectPr', ns)
            if sect is not None:
                pgmar = sect.find('w:pgMar', ns)
                if pgmar is not None:
                    for key in ('top', 'bottom', 'left', 'right'):
                        val = pgmar.get(f'{{{ns["w"]}}}{key}')
                        if val:
                            margins[key] = int(val)
                if sect.find('w:pgNumType', ns) is not None:
                    has_pg_num_type = True
        for name in zf.namelist():
            if name.startswith('word/header') and name.endswith('.xml'):
                data = zf.read(name)
                if b'<w:t' in data:
                    has_header = True
            if name.startswith('word/footer') and name.endswith('.xml'):
                data = zf.read(name)
                if b'<w:t' in data:
                    has_footer = True
                if b'PAGE' in data or b'\\x00PAGE' in data:
                    has_page_field = True

    return {
        'toc': toc,
        'ref': ref,
        'bad': bad,
        'headings': len(headings),
        'paras': len(paras),
        'indent_rate': round(indent_rate, 2),
        'font': font_main,
        'line_spacing': line_spacing_main,
        'line_spacing_rate': round(line_spacing_rate, 2),
        'margins': margins,
        'header': has_header,
        'footer': has_footer,
        'page_field': has_page_field,
        'pg_num_type': has_pg_num_type,
    }


def main() -> None:
    files = sorted(OUT.glob('ui_case_*.docx'))
    if not files:
        print('no ui_case_*.docx found')
        return
    sample = files if SAMPLE_N >= len(files) else random.sample(files, SAMPLE_N)
    print(f'sample size: {len(sample)}')
    for f in sample:
        res = check_doc(f)
        print(
            f"{f.name}: toc={res['toc']} ref={res['ref']} bad={res['bad']} "
            f"headings={res['headings']} paras={res['paras']} "
            f"indent_rate={res['indent_rate']} font={res['font']} "
            f"line_spacing={res['line_spacing']} line_spacing_rate={res['line_spacing_rate']} "
            f"margins={res['margins']} header={res['header']} footer={res['footer']} "
            f"page_field={res['page_field']} pg_num_type={res['pg_num_type']}"
        )


if __name__ == '__main__':
    main()
