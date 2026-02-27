"""Outline module.

This module belongs to `writing_agent.agents` in the writing-agent codebase.
"""

from __future__ import annotations

import re

from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings
from writing_agent.models import OutlineNode, ReportRequest
from writing_agent.sections_catalog import section_catalog_text


class OutlineAgent:
    def generate_outline_markdown(self, req: ReportRequest, template: str) -> str:
        md = self._generate_outline_markdown_llm(req=req)
        if md is not None:
            return md

        title = req.topic.strip() or "自动生成文档"
        if template == "experiment":
            headings = [
                ("# " + title, []),
                ("## 引言", ["交代实验背景、问题来源与实验目标，说明本文结构安排。", "可简要点出实验的意义与预期贡献。"]),
                ("## 实验目的", ["说明实验要验证的核心假设与目标指标。", "补充实验成功与失败的判定标准。"]),
                ("## 实验原理/背景", ["阐述关键概念、理论依据或相关公式，明确实验逻辑。", "必要时说明与已有工作/现象的联系。"]),
                ("## 实验材料与设备", ["列出材料、软件/硬件与关键参数配置，确保可复现。", "说明仪器精度或版本信息。"]),
                ("## 实验方法与步骤", ["按步骤描述操作流程、变量控制与采样方式。", "强调关键步骤与注意事项。"]),
                ("## 数据与结果", ["以表格/图示呈现数据并做简要说明。", "标注对比基准或参考范围。"]),
                ("## 结果分析与讨论", ["解释实验结果的原因与意义，分析异常与误差来源。", "给出改进建议或进一步验证思路。"]),
                ("## 结论", ["总结主要发现与结论，呼应实验目的。", "指出实验局限与后续工作方向。"]),
                ("## 参考文献", ["列出可验证来源（带 URL/DOI），与正文引用对应。"]),
            ]
        elif template == "paper":
            headings = [
                ("# " + title, []),
                ("## 引言", ["提出问题背景、研究意义与本文结构安排。", "明确研究目标与范围边界。"]),
                ("## 相关工作与文献综述", ["归纳已有方法与结论，指出不足与差异。", "强调本研究与现有工作的关系。"]),
                ("## 理论基础", ["说明关键概念、术语与理论依据。", "为方法部分提供统一的理论框架。"]),
                ("## 方法", ["给出核心方法、假设、流程与关键参数。", "必要时补充伪代码或流程图说明。"]),
                ("## 实验与结果", ["说明数据集/实验环境、评价指标与对比基线。", "用图表展示结果并给出简要解释。"]),
                ("## 讨论", ["解释现象、局限性与潜在影响，提出改进方向。", "对比预期结果，给出原因分析。"]),
                ("## 结论", ["总结主要贡献与结论，呼应研究目标。", "简述后续工作方向。"]),
                ("## 参考文献", ["列出可验证来源（带 URL/DOI），与正文引用一致。"]),
            ]
        else:
            headings = [
                ("# " + title, []),
                ("## 引言", ["说明项目/报告背景、目的与本文结构安排。", "交代研究范围与限制条件。"]),
                ("## 需求分析", ["描述业务场景、角色与功能需求，并补充非功能指标。", "明确约束、假设与边界。"]),
                ("## 总体设计", ["给出系统架构与模块划分，说明关键流程与数据流。", "可配合架构图或流程图说明设计思路。"]),
                ("## 详细设计", ["展开核心模块的设计细节与接口逻辑。", "说明关键算法、数据结构与异常处理。"]),
                ("## 实现与部署", ["说明技术栈、实现步骤与部署方式，强调可复现性。", "补充运行环境、依赖与配置。"]),
                ("## 测试与结果分析", ["描述测试方案与覆盖范围，展示关键结果。", "结合指标做对比与解释。"]),
                ("## 结论", ["总结主要工作与成果，突出价值与改进点。", "给出后续完善方向。"]),
                ("## 参考文献", ["列出可验证来源（带 URL/DOI），与正文引用对应。"]),
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

        catalog = section_catalog_text()
        system = (
            "你是一个论文/课程报告写作助手，负责生成“可编辑”的结构化大纲。"
            "要求：输出必须是 Markdown；只使用 # / ## / ### ... 标题；每个章节可附 1-3 条 '- ' 要点。"
            "不要输出 JSON/代码/表格/其他非大纲内容。"
            "避免编造不可验证事实；需要数据/结论时用“[待补充]”。不要输出除 Markdown 之外的内容。"
            "示例：\n"
            "# 工资管理系统\n"
            "## 引言\n"
            "- 背景与问题来源\n"
            "- 报告目标与结构安排\n"
        )
        user = (
            f"主题：{req.topic}\n"
            f"类型：{req.report_type}\n"
            f"标题层级上限：{req.formatting.heading_levels}\n"
            f"字数要求（可选）：{req.formatting.word_count or '未指定'}\n"
            f"写作风格：{req.writing_style}\n"
            f"\n可选章节库（按需挑选，不必全部使用）：\n{catalog}\n"
            "\n请给出一份完整大纲，包含“引言/背景、方法/过程、结果/分析、结论、参考文献”等必要章节（按类型自适配）。"
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
