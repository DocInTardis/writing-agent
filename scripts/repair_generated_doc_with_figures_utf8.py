#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Dict, List

from docx import Document
from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.v2.figure_render import export_rendered_figure_assets

RUN_ROOT = Path(r"D:\codes\writing-agent\deliverables\codex_full_with_figures_utf8_20260310_131903")
SRC = RUN_ROOT / "final_output.md"
OUT_MD = RUN_ROOT / "final_output_repaired_utf8.md"
OUT_DOCX = RUN_ROOT / "final_output_repaired_utf8.docx"
SUMMARY = RUN_ROOT / "REPAIRED_UTF8_SUMMARY.json"

TITLE = "\u9762\u5411\u9ad8\u6821\u79d1\u7814\u573a\u666f\u7684\u667a\u80fd\u5199\u4f5c\u4ee3\u7406\u7cfb\u7edf\u8bbe\u8ba1\u4e0e\u5b9e\u73b0"
SEC_ABSTRACT = "\u6458\u8981"
SEC_KEYWORDS = "\u5173\u952e\u8bcd"
SEC_INTRO = "\u5f15\u8a00"
SEC_SYSTEM = "\u7cfb\u7edf\u8bbe\u8ba1\u4e0e\u5b9e\u73b0"
SEC_EXPERIMENT = "\u5b9e\u9a8c\u8bbe\u8ba1\u4e0e\u7ed3\u679c"
SEC_CONCLUSION = "\u7ed3\u8bba"
SEC_REFS = "\u53c2\u8003\u6587\u732e"
ORDER = [SEC_ABSTRACT, SEC_KEYWORDS, SEC_INTRO, SEC_SYSTEM, SEC_EXPERIMENT, SEC_CONCLUSION, SEC_REFS]
KEYWORDS_LINE = "\u9ad8\u6821\u79d1\u7814\u573a\u666f\uff1b\u667a\u80fd\u5199\u4f5c\u4ee3\u7406\u7cfb\u7edf\uff1b\u591a\u4ee3\u7406\u534f\u540c\uff1b\u68c0\u7d22\u589e\u5f3a\u751f\u6210\uff1b\u7cfb\u7edf\u8bbe\u8ba1\u4e0e\u5b9e\u73b0\uff1b\u8d28\u91cf\u6821\u9a8c"
REFERENCES = [
    "[1] Lewis P, Perez E, Piktus A, et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks[J]. Advances in Neural Information Processing Systems, 2020. https://arxiv.org/abs/2005.11401",
    "[2] Gao Y, Xiong Y, Gao X, et al. Retrieval-Augmented Generation for Large Language Models: A Survey[J]. arXiv preprint, 2023. https://arxiv.org/abs/2312.10997",
    "[3] Zhang T, Ladhak F, Durmus E, et al. Expository Text Generation: Imitate, Retrieve, Paraphrase[J]. arXiv preprint, 2023. https://arxiv.org/abs/2305.03276",
    "[4] Wang Y, Ma X, Nie P, et al. ScholarCopilot: Training Large Language Models for Academic Writing with Accurate Citations[J]. arXiv preprint, 2025. https://arxiv.org/abs/2504.00824",
    "[5] Hou J, Huikai A L, Chen N, et al. PaperDebugger: A Plugin-Based Multi-Agent System for In-Editor Academic Writing, Review, and Editing[J]. arXiv preprint, 2025. https://arxiv.org/abs/2512.02589",
    "[6] Anonymous. LLM-Ref: Enhancing Reference Handling in Technical Writing with Large Language Models[J]. arXiv preprint, 2024. https://arxiv.org/abs/2411.00294",
    "[7] Wang Z, Moriyama S, Wang W Y, et al. Talk Structurally, Act Hierarchically: A Collaborative Framework for LLM Multi-Agent Systems[J]. arXiv preprint, 2025. https://arxiv.org/abs/2502.11098",
    "[8] Xu Z, Qiu Y, Sun L, et al. GhostCite: A Large-Scale Analysis of Citation Validity in the Age of Large Language Models[J]. arXiv preprint, 2026. https://arxiv.org/abs/2602.06718",
]

LATIN1_NOISE_RE = re.compile(r"[\u0080-\u00ff]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def score(s: str) -> int:
    return len(CJK_RE.findall(s)) * 3 - len(LATIN1_NOISE_RE.findall(s)) * 2 - s.count('?') * 4


def try_full_repair(s: str) -> str:
    try:
        return s.encode('latin1').decode('utf-8')
    except Exception:
        return s


def try_segment_repair(s: str) -> str:
    def repl(m: re.Match[str]) -> str:
        chunk = m.group(0)
        try:
            return chunk.encode('latin1').decode('utf-8')
        except Exception:
            return chunk
    return re.sub(r'[\u0080-\u00ff]+', repl, s)


def repair_line(line: str) -> str:
    s = line.rstrip('\n')
    if not s.strip():
        return s
    if s.startswith('#') or s.startswith('[[') or re.match(r'^\s*\[\d+\]\s+', s):
        return s
    candidates = [s, try_segment_repair(s), try_full_repair(s)]
    return max(candidates, key=score)


def main() -> int:
    text = SRC.read_text(encoding='utf-8')
    fixed_lines = [repair_line(line) for line in text.splitlines()]
    for i, line in enumerate(fixed_lines):
        if line.startswith('# '):
            fixed_lines[i] = f'# {TITLE}'
            break

    sections: Dict[str, List[str]] = {}
    current = ''
    for line in fixed_lines:
        if line.startswith('## '):
            current = line[3:].strip()
            sections[current] = []
            continue
        if current:
            sections[current].append(line)

    sections[SEC_KEYWORDS] = ['', KEYWORDS_LINE, '']
    sections[SEC_REFS] = [''] + REFERENCES + ['']

    assembled: List[str] = [f'# {TITLE}', '']
    for sec in ORDER:
        body = sections.get(sec)
        if not body:
            continue
        assembled.append(f'## {sec}')
        assembled.extend(body)
        if assembled[-1] != '':
            assembled.append('')
    cleaned = '\n'.join(assembled).rstrip() + '\n'
    OUT_MD.write_text(cleaned, encoding='utf-8')

    figure_manifest = export_rendered_figure_assets(cleaned, RUN_ROOT / 'figure_assets_repaired_utf8')

    client = TestClient(app_v2.app)
    resp = client.get('/', follow_redirects=False)
    doc_id = (resp.headers.get('location') or '').split('/workbench/')[-1]
    save = client.post(
        f'/api/doc/{doc_id}/save',
        json={
            'text': cleaned,
            'generation_prefs': {'export_gate_policy': 'off', 'strict_doc_format': False, 'strict_citation_verify': False},
        },
    )
    dl = client.get(f'/download/{doc_id}.docx')
    if dl.status_code == 200 and dl.content:
        OUT_DOCX.write_bytes(dl.content)

    inline_shapes = 0
    if OUT_DOCX.exists():
        inline_shapes = len(Document(io.BytesIO(OUT_DOCX.read_bytes())).inline_shapes)

    summary = {
        'repaired_markdown_file': str(OUT_MD.resolve()),
        'repaired_docx_file': str(OUT_DOCX.resolve()) if OUT_DOCX.exists() else '',
        'figure_manifest_file': str((RUN_ROOT / 'figure_assets_repaired_utf8' / 'manifest.json').resolve()),
        'figure_count': int(figure_manifest.get('count', 0)),
        'figure_score_avg': float(figure_manifest.get('avg_score', 0.0) or 0.0),
        'figure_score_min': int(figure_manifest.get('min_score', 0) or 0),
        'figure_score_max': int(figure_manifest.get('max_score', 0) or 0),
        'figure_passed_count': int(figure_manifest.get('passed_count', 0) or 0),
        'inline_shapes': inline_shapes,
        'save_status': save.status_code,
        'download_status': dl.status_code,
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
