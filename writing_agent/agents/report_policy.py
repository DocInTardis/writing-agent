"""Report Policy module.

This module belongs to `writing_agent.agents` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyResult:
    html: str
    fixes: list[str]
    issues: list[str]


class ReportPolicy:
    """
    Enforces a "report must look like a report" baseline:
    - requires common sections (引言/方法/结果/结论/参考文献)
    - requires each section to have at least N paragraphs
    - requires minimum total text length (so it won't be a one-liner)
    """

    def __init__(self, min_section_paragraphs: int = 2, min_total_chars: int = 1200) -> None:
        self.min_section_paragraphs = max(1, int(min_section_paragraphs))
        self.min_total_chars = max(200, int(min_total_chars))

    def enforce(self, html: str, title: str, required_headings: list[str] | None = None) -> PolicyResult:
        fixes: list[str] = []
        issues: list[str] = []

        normalized = (html or "").strip()
        if not normalized:
            normalized = f"<h1>{self._esc(title)}</h1>"
            fixes.append("initialized empty document")

        chunks = self._split_by_headings(normalized)
        if not self._has_h1(chunks):
            chunks.insert(0, _Chunk(heading=f"<h1>{self._esc(title)}</h1>", content=""))
            fixes.append("added missing H1 title")

        if required_headings:
            required_keys = [h.strip() for h in required_headings if h and h.strip()]
        else:
            required = self._required_sections()
            required_keys = list(required.keys())

        for key in required_keys:
            idx = self._find_section(chunks, [key])
            if idx is None:
                chunks.append(_Chunk(heading=f"<h2>{self._esc(key)}</h2>", content=self._default_section_body(key)))
                fixes.append(f"added missing section: {key}")
                continue
            current = chunks[idx]
            para_count = self._count_paragraphs(current.content)
            if para_count < self.min_section_paragraphs:
                need = self.min_section_paragraphs - para_count
                current.content = (current.content or "") + self._pad_paragraphs(key, need)
                fixes.append(f"expanded section '{key}' to {self.min_section_paragraphs} paragraphs")

        text_len = len(self._strip_tags(self._join_chunks(chunks)).strip())
        if text_len < self.min_total_chars:
            issues.append(f"内容偏短（{text_len} chars），已自动补全占位段落。")
            # Prefer enriching 引言/方法/结果/结论
            preferred = ["引言", "方法", "结果", "结论"]
            for key in preferred:
                idx = self._find_section(chunks, [key])
                if idx is None:
                    continue
                chunks[idx].content += self._pad_paragraphs(key, 1)
                fixes.append(f"added extra paragraph to {key}")
                text_len = len(self._strip_tags(self._join_chunks(chunks)).strip())
                if text_len >= self.min_total_chars:
                    break

        out = self._join_chunks(chunks)
        issues.extend(self.validate(out))
        return PolicyResult(html=out, fixes=fixes, issues=issues)

    def validate(self, html: str, required_headings: list[str] | None = None) -> list[str]:
        chunks = self._split_by_headings(html or "")
        problems: list[str] = []
        if not self._has_h1(chunks):
            problems.append("缺少标题（H1）")

        if required_headings:
            required_keys = [h.strip() for h in required_headings if h and h.strip()]
        else:
            required_keys = list(self._required_sections().keys())

        for key in required_keys:
            idx = self._find_section(chunks, [key])
            if idx is None:
                problems.append(f"缺少章节：{key}")
                continue
            para_count = self._count_paragraphs(chunks[idx].content)
            if para_count < self.min_section_paragraphs:
                problems.append(f"章节“{key}”段落过少（{para_count}）")
        text_len = len(self._strip_tags(self._join_chunks(chunks)).strip())
        if text_len < self.min_total_chars:
            problems.append(f"正文总体过短（{text_len} chars）")
        return problems

    def _required_sections(self) -> dict[str, list[str]]:
        return {
            "引言": ["引言", "背景", "绪论", "Introduction"],
            "方法": ["方法", "过程", "实现", "Method", "Methods"],
            "结果": ["结果", "分析", "实验结果", "Results", "Evaluation"],
            "结论": ["结论", "总结", "Conclusion"],
            "参考文献": ["参考文献", "References", "Bibliography"],
        }

    def _split_by_headings(self, html: str) -> list["_Chunk"]:
        pattern = re.compile(r"(<h[1-6][^>]*>.*?</h[1-6]>)", flags=re.IGNORECASE | re.DOTALL)
        parts = pattern.split(html)
        chunks: list[_Chunk] = []
        pre = (parts[0] if parts else "") or ""
        if pre.strip():
            chunks.append(_Chunk(heading=None, content=pre))
        i = 1
        while i < len(parts):
            heading = parts[i]
            content = parts[i + 1] if i + 1 < len(parts) else ""
            chunks.append(_Chunk(heading=heading, content=content or ""))
            i += 2
        return chunks

    def _join_chunks(self, chunks: list["_Chunk"]) -> str:
        out: list[str] = []
        for c in chunks:
            if c.heading:
                out.append(c.heading)
            if c.content:
                out.append(c.content)
        return "".join(out)

    def _has_h1(self, chunks: list["_Chunk"]) -> bool:
        for c in chunks:
            if c.heading and re.match(r"<h1\b", c.heading, flags=re.IGNORECASE):
                return True
        return False

    def _find_section(self, chunks: list["_Chunk"], aliases: list[str]) -> int | None:
        for i, c in enumerate(chunks):
            if not c.heading:
                continue
            if not re.match(r"<h[1-6]\b", c.heading, flags=re.IGNORECASE):
                continue
            title = self._strip_tags(c.heading).strip()
            for a in aliases:
                if a and a in title:
                    return i
        return None

    def _count_paragraphs(self, html: str) -> int:
        return len(re.findall(r"<p\b", html or "", flags=re.IGNORECASE))

    def _default_section_body(self, section: str) -> str:
        if section == "参考文献":
            return (
                "<p>请在此列出可验证来源（URL/DOI）。正文中用 <strong>[@citekey]</strong> 标注引用键。</p>"
                "<p>[待补充]：补充至少 3 条参考资料，并保证与正文引用一致。</p>"
            )
        if section == "引言":
            return (
                "<p>引言说明问题背景、研究意义与本文结构。涉及事实请给出来源或标注为假设。</p>"
                "<p>[待补充]：补充相关背景与本文要解决的问题。</p>"
            )
        if section == "方法":
            return (
                "<p>方法部分描述采用的流程/模型/实验设计，给出关键步骤与参数定义。</p>"
                "<p>[待补充]：补充核心方法细节与实现要点。</p>"
            )
        if section == "结果":
            return (
                "<p>结果部分展示实验/分析产出，用表格或图示表达（可先用文字占位）。</p>"
                "<p>[待补充]：补充关键结果、对比与分析结论（数据用占位）。</p>"
            )
        if section == "结论":
            return (
                "<p>结论总结主要发现、局限性与后续工作建议，保持可验证与可落地。</p>"
                "<p>[待补充]：补充结论要点与建议。</p>"
            )
        return "<p>[待补充]</p><p>[待补充]</p>"

    def _pad_paragraphs(self, section: str, n: int) -> str:
        if n <= 0:
            return ""
        pads = []
        for _ in range(n):
            pads.append(f"<p>[待补充]：补全“{section}”的具体内容与必要细节。</p>")
        return "".join(pads)

    def _strip_tags(self, html: str) -> str:
        return re.sub(r"<[^>]+>", "", html or "")

    def _esc(self, s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass
class _Chunk:
    heading: str | None
    content: str


def extract_template_headings(template_html: str) -> list[str]:
    html = template_html or ""
    headings = re.findall(r"<h2\b[^>]*>(.*?)</h2>", html, flags=re.IGNORECASE | re.DOTALL)
    out: list[str] = []
    for h in headings:
        txt = re.sub(r"<[^>]+>", "", h).strip()
        if not txt:
            continue
        if txt not in out:
            out.append(txt)
    return out
