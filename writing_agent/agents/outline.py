from __future__ import annotations

import re

from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings
from writing_agent.models import OutlineNode, ReportRequest


class OutlineAgent:
    def generate_outline_markdown(self, req: ReportRequest, template: str) -> str:
        md = self._generate_outline_markdown_llm(req=req)
        if md is not None:
            return md

        title = req.topic.strip() or "未命名报告"
        if template == "experiment":
            headings = [
                ("# " + title, []),
                ("## 摘要", ["概括目的、方法、结果与结论。"]),
                ("## 实验目的", ["说明实验目标与预期。"]),
                ("## 实验原理/背景", ["阐述关键概念与理论依据。"]),
                ("## 实验材料与设备", ["列出材料、软件/硬件与参数。"]),
                ("## 实验方法与步骤", ["按步骤说明流程，包含变量与控制。"]),
                ("## 数据与结果", ["给出数据表/图表占位与描述。"]),
                ("## 讨论与误差分析", ["解释结果，分析误差来源与改进。"]),
                ("## 结论", ["总结主要发现与结论。"]),
                ("## 参考文献", ["列出可验证来源（带 URL/DOI）。"]),
            ]
        elif template == "paper":
            headings = [
                ("# " + title, []),
                ("## 摘要", ["概括问题、方法、贡献与结论。"]),
                ("## 引言", ["提出问题背景、研究意义与本文结构。"]),
                ("## 相关工作", ["对比已有方法，指出差异与不足。"]),
                ("## 方法", ["给出核心方法、假设与推导/流程。"]),
                ("## 实验与结果", ["说明数据集/设置，展示结果与对比。"]),
                ("## 讨论", ["解释现象、局限性与未来工作。"]),
                ("## 结论", ["总结贡献与结论。"]),
                ("## 参考文献", ["列出可验证来源（带 URL/DOI）。"]),
            ]
        else:
            headings = [
                ("# " + title, []),
                ("## 摘要", ["概括主题、方法与结论。"]),
                ("## 引言", ["背景与目的，说明报告结构。"]),
                ("## 理论基础/背景", ["关键概念、定义与相关理论。"]),
                ("## 方法/过程", ["你采用的分析框架、步骤或实验流程。"]),
                ("## 结果/分析", ["用证据支持结论（可插入图表）。"]),
                ("## 结论与建议", ["总结与可执行建议。"]),
                ("## 参考文献", ["列出可验证来源（带 URL/DOI）。"]),
            ]

        lines: list[str] = []
        for h, notes in headings:
            lines.append(h)
            for note in notes:
                lines.append(f"- {note}")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def parse_outline_markdown(self, md: str) -> OutlineNode:
        root = OutlineNode(title="ROOT", level=0)
        stack: list[OutlineNode] = [root]
        current: OutlineNode | None = None

        for raw in md.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            if line.lstrip().startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                title = line.lstrip("#").strip()
                node = OutlineNode(title=title, level=level)
                while stack and stack[-1].level >= level:
                    stack.pop()
                stack[-1].children.append(node)
                stack.append(node)
                current = node
                continue
            if line.strip().startswith("-"):
                if current is not None:
                    current.notes.append(line.strip().lstrip("-").strip())

        return root

    def _generate_outline_markdown_llm(self, req: ReportRequest) -> str | None:
        settings = get_ollama_settings()
        if not settings.enabled:
            return None

        client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
        if not client.is_running():
            return None

        system = (
            "你是一个论文/课程报告写作助手，负责生成“可编辑”的结构化大纲。"
            "要求：输出必须是 Markdown；只使用 # / ## / ### ... 标题；每个章节可附 1-3 条 '- ' 要点。"
            "避免编造不可验证事实；需要数据/结论时用“[待补充]”。不要输出除 Markdown 之外的内容。"
        )
        user = (
            f"主题：{req.topic}\n"
            f"类型：{req.report_type}\n"
            f"标题层级上限：{req.formatting.heading_levels}\n"
            f"字数要求（可选）：{req.formatting.word_count or '未指定'}\n"
            f"写作风格：{req.writing_style}\n"
            "\n请给出一份完整大纲，包含“摘要、引言/背景、方法/过程、结果/分析、结论、参考文献”等必要章节（按类型自适配）。"
        )
        try:
            text = client.chat(system=system, user=user, temperature=0.2)
        except OllamaError:
            return None

        cleaned = text.strip()
        if not cleaned:
            return None
        if not re.search(r"^#\s+", cleaned, flags=re.M):
            return None
        return cleaned + ("\n" if not cleaned.endswith("\n") else "")

