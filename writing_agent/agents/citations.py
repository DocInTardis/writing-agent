from __future__ import annotations

import re
from dataclasses import dataclass

from writing_agent.models import Citation, CitationStyle, ReportRequest


@dataclass(frozen=True)
class CitationParseResult:
    citations: dict[str, Citation]
    warnings: list[str]


class CitationAgent:
    def parse_manual_sources(self, req: ReportRequest) -> CitationParseResult:
        text = (req.manual_sources_text or "").strip()
        if not text:
            return CitationParseResult(citations={}, warnings=["未提供参考资料：建议在生成前粘贴可验证来源（含 URL/DOI）。"])

        citations: dict[str, Citation] = {}
        warnings: list[str] = []

        for i, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                warnings.append(f"第 {i} 行格式不正确，期望: title | url | authors? | year? | key?")
                continue

            title = parts[0]
            url = parts[1] or None
            authors = parts[2] if len(parts) >= 3 and parts[2] else None
            year = parts[3] if len(parts) >= 4 and parts[3] else None
            key = parts[4] if len(parts) >= 5 and parts[4] else None
            if not key:
                key = self._make_key(title=title, year=year)
            key = self._sanitize_key(key)

            if key in citations:
                warnings.append(f"第 {i} 行引用键重复: {key}，已跳过")
                continue

            citations[key] = Citation(key=key, title=title, url=url, authors=authors, year=year)

        if not citations:
            warnings.append("未解析到有效参考资料。")

        return CitationParseResult(citations=citations, warnings=warnings)

    def format_reference(self, citation: Citation, style: CitationStyle) -> str:
        authors = citation.authors or "佚名"
        year = citation.year or "n.d."
        title = citation.title
        url = citation.url or ""

        if style == CitationStyle.IEEE:
            base = f"{authors}, “{title},” {year}."
        elif style == CitationStyle.APA:
            base = f"{authors} ({year}). {title}."
        else:
            base = f"{authors}. {title} ({year})."

        if url:
            return f"{base} {url}"
        return base

    def _make_key(self, title: str, year: str | None) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9\\u4e00-\\u9fff]+", "-", title).strip("-")
        cleaned = cleaned[:24] if cleaned else "ref"
        suffix = year or "nd"
        return f"{cleaned}-{suffix}"

    def _sanitize_key(self, key: str) -> str:
        key = key.strip()
        key = re.sub(r"[^a-zA-Z0-9_-]+", "-", key)
        key = re.sub(r"-{2,}", "-", key).strip("-")
        return key or "ref"


