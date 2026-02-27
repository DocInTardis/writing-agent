"""Writing module.

This module belongs to `writing_agent.agents` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings
from writing_agent.models import DraftDocument, OutlineNode, Paragraph, ReportRequest, SectionDraft


@dataclass(frozen=True)
class WriteResult:
    draft: DraftDocument
    citation_usage: dict[str, list[str]]  # citekey -> ["Section", ...]


class WritingAgent:
    CITE_PATTERN = re.compile(r"\[@(?P<key>[a-zA-Z0-9_-]+)\]")

    def generate_draft(self, req: ReportRequest, outline: OutlineNode, citations: dict[str, object]) -> WriteResult:
        title = req.topic.strip() or "自动生成文档"
        sections: list[SectionDraft] = []
        usage: dict[str, list[str]] = {}

        for node in outline.children:
            sections.extend(self._write_node(node=node, req=req, citations=citations, usage=usage))

        return WriteResult(draft=DraftDocument(title=title, sections=sections), citation_usage=usage)

    def regenerate_section(
        self, req: ReportRequest, outline: OutlineNode, citations: dict[str, object], section_title: str
    ) -> tuple[list[SectionDraft], dict[str, list[str]]]:
        usage: dict[str, list[str]] = {}
        new_sections: list[SectionDraft] = []
        for node in outline.walk():
            if node.title.strip() == section_title.strip() and node.level > 0:
                new_sections.extend(self._write_node(node=node, req=req, citations=citations, usage=usage))
                break
        return new_sections, usage

    def rewrite_paragraph(self, req: ReportRequest, paragraph: str) -> str:
        text = paragraph.strip()
        if not text:
            return ""
        improved = self._rewrite_paragraph_llm(req=req, paragraph=text)
        if improved is not None:
            return improved
        return f"{text}\n\n（润色建议：请补充关键数据/定义，并将结论与证据对应；如有引用请使用 `[@citekey]` 标注。）"

    def _write_node(
        self,
        node: OutlineNode,
        req: ReportRequest,
        citations: dict[str, object],
        usage: dict[str, list[str]],
    ) -> list[SectionDraft]:
        if any(k in node.title for k in ["参考文献", "References", "Bibliography"]):
            return []

        section = SectionDraft(title=node.title, level=max(1, min(node.level, req.formatting.heading_levels)))
        notes = "；".join(node.notes) if node.notes else "（请根据你的课程/研究要求补充要点）"

        llm_paras = self._write_section_llm(req=req, title=node.title, notes=notes, cite_keys=list(citations.keys()))
        if llm_paras is not None:
            section.paragraphs.extend([Paragraph(text=p) for p in llm_paras if p.strip()])
            self._track_citations_usage(section_title=node.title, paragraphs=llm_paras, usage=usage)
        else:
            cite_keys = list(citations.keys())
            cite_hint = ""
            if cite_keys:
                chosen = self._choose_citations(node.title, cite_keys)
                if chosen:
                    cite_hint = " " + " ".join([f"[@{k}]" for k in chosen])
                    for k in chosen:
                        usage.setdefault(k, [])
                        if node.title not in usage[k]:
                            usage[k].append(node.title)

            section.paragraphs.append(
                Paragraph(
                    text=(
                        f"本节围绕“{node.title}”展开，目标是在保证可验证性的前提下给出清晰的论证结构。{cite_hint}".strip()
                    )
                )
            )
            section.paragraphs.append(
                Paragraph(
                    text=(
                        f"要点提示：{notes}。为避免不可验证表述，涉及事实/数据的地方请以来源支撑，"
                        f"或明确标注为假设/待补充。{cite_hint}"
                    ).strip()
                )
            )

        children: list[SectionDraft] = [section]
        for child in node.children:
            children.extend(self._write_node(node=child, req=req, citations=citations, usage=usage))
        return children

    def _choose_citations(self, title: str, keys: list[str]) -> list[str]:
        title_low = title.lower()
        scored: list[tuple[int, str]] = []
        for k in keys:
            s = 0
            if any(tok in k.lower() for tok in re.findall(r"[a-zA-Z0-9]+", title_low)):
                s += 2
            if any(ch in title for ch in ["方法", "理论", "背景", "相关", "实验", "结果", "讨论"]):
                s += 1
            scored.append((s, k))
        scored.sort(key=lambda x: (-x[0], x[1]))
        picked = [k for s, k in scored if s > 0][:2]
        if not picked:
            picked = keys[:1]
        return picked

    def _write_section_llm(self, req: ReportRequest, title: str, notes: str, cite_keys: list[str]) -> list[str] | None:
        settings = get_ollama_settings()
        if not settings.enabled:
            return None
        client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
        if not client.is_running():
            return None

        cite_rule = "不要凭空创造引用键。"
        if cite_keys:
            cite_rule = f"只能使用这些引用键进行标注：{', '.join([f'[@{k}]' for k in cite_keys])}。不要发明新的键。"

        system = (
            "你是一个学术写作助手，负责为指定章节写作内容。"
            "必须避免编造不可验证事实；需要具体数据/结论时用'[待补充]'。"
            "**重要**：凡是引用他人观点、数据或结论，必须在句末添加引用标记（如 [@key]），以便读者验证来源。"
            "输出仅包含该章节的正文段落，段落之间用一个空行分隔，不要输出标题。"
        )
        user = (
            f"主题：{req.topic}\n"
            f"章节：{title}\n"
            f"要点提示：{notes}\n"
            f"写作风格：{req.writing_style}\n"
            f"引用规则：{cite_rule}\n"
            "\n请写 2-4 段正文，每段 2-5 句，行文连贯。"
            "**必须在陈述事实、引用观点或数据的句子末尾添加引用标记** [@key]，例如："
            '\n"根据研究表明，XX方法可以提升性能 [@zhang2020]。"'
            "\n确保至少在2-3处添加引用标记，以增强论证可信度。"
        )
        try:
            text = client.chat(system=system, user=user, temperature=0.3).strip()
        except OllamaError:
            return None

        if not text:
            return None
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paras:
            return None
        return paras[:4]

    def _rewrite_paragraph_llm(self, req: ReportRequest, paragraph: str) -> str | None:
        settings = get_ollama_settings()
        if not settings.enabled:
            return None
        client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
        if not client.is_running():
            return None

        system = (
            "你是一个论文润色助手。"
            "要求：保留原意；增强逻辑与表达；避免编造事实；缺失数据用“[待补充]”；如需引用用 [@key]（若用户未给 key 则不添加）。"
        )
        user = f"请润色以下段落（输出润色后的段落文本即可）：\n\n{paragraph}"
        try:
            out = client.chat(system=system, user=user, temperature=0.2).strip()
        except OllamaError:
            return None
        return out or None

    def _track_citations_usage(self, section_title: str, paragraphs: list[str], usage: dict[str, list[str]]) -> None:
        for p in paragraphs:
            for m in self.CITE_PATTERN.finditer(p):
                k = m.group("key")
                usage.setdefault(k, [])
                if section_title not in usage[k]:
                    usage[k].append(section_title)
