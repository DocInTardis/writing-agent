from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document


@dataclass(frozen=True)
class TemplateInfo:
    name: str
    required_h2: list[str]


def parse_template_file(path: Path, name: str) -> TemplateInfo:
    suffix = path.suffix.lower()
    if suffix in {".docx"}:
        return TemplateInfo(name=name, required_h2=_parse_docx_h2(path))
    if suffix in {".html", ".htm"}:
        return TemplateInfo(name=name, required_h2=_parse_html_h2(path.read_text(encoding="utf-8", errors="replace")))
    # default: treat as text
    return TemplateInfo(name=name, required_h2=_parse_text_h2(path.read_text(encoding="utf-8", errors="replace")))


def _parse_docx_h2(path: Path) -> list[str]:
    doc = Document(str(path))
    out: list[str] = []
    for p in doc.paragraphs:
        txt = (p.text or "").strip()
        if not txt:
            continue
        style = ""
        try:
            style = str(p.style.name or "")
        except Exception:
            style = ""
        s = style.lower()
        is_h2 = ("heading 2" in s) or ("标题 2" in style) or ("标题2" in style)
        if is_h2:
            _push_unique(out, txt)
    return out


def _parse_html_h2(html: str) -> list[str]:
    headings = re.findall(r"<h2\b[^>]*>(.*?)</h2>", html or "", flags=re.IGNORECASE | re.DOTALL)
    out: list[str] = []
    for h in headings:
        txt = re.sub(r"<[^>]+>", "", h).strip()
        if txt:
            _push_unique(out, txt)
    return out


def _parse_text_h2(text: str) -> list[str]:
    out: list[str] = []
    for line in (text or "").splitlines():
        m = re.match(r"^\s*##\s+(.+?)\s*$", line)
        if m:
            _push_unique(out, m.group(1).strip())
    return out


def _push_unique(out: list[str], s: str) -> None:
    if s and s not in out:
        out.append(s)

