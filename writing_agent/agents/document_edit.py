from __future__ import annotations

from dataclasses import dataclass

from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings
from writing_agent.agents.report_policy import ReportPolicy, extract_template_headings
from writing_agent.web.html_sanitize import sanitize_html


@dataclass(frozen=True)
class EditResult:
    html: str
    assistant: str


class DocumentEditAgent:
    def __init__(self) -> None:
        self._policy = ReportPolicy(min_section_paragraphs=2, min_total_chars=1200)

    def build_prompts(
        self,
        *,
        html: str,
        instruction: str,
        selection: str | None = None,
        template_html: str | None = None,
    ) -> tuple[str, str, list[str] | None]:
        required_headings = extract_template_headings(template_html or "") if (template_html or "").strip() else None

        sel = (selection or "").strip()
        selection_hint = ""
        if sel:
            selection_hint = f"\n用户选中内容（优先针对这段修改）：\n{sel}\n"

        section_rule = "必须包含这些章节：摘要、引言、方法、结果、结论、参考文献。"
        if required_headings:
            section_rule = f"必须包含这些章节（按模板）：{', '.join(required_headings)}。"

        system = (
            "你是一个“文档编辑 Agent”。你会收到当前文档 HTML，以及用户的自然语言修改要求。"
            "你的任务是把要求直接应用到文档上，并输出“修改后的 HTML”。\n"
            "强制规范（必须遵守）：\n"
            f"1) 输出必须是完整报告，而不是一句话；{section_rule}\n"
            "2) 每个章节至少 2 段（<p>），段落要有具体说明；缺失信息用 [待补充]，不要编造数据或引用。\n"
            "3) 只输出 HTML（不要 Markdown、不要代码块、不要解释）。\n"
            "4) 禁止输出 <script>、事件处理属性（on*）或任何危险内容。\n"
            "5) 优先使用 h1-h3 + p/ul/ol/li；允许使用 table（表格）与 svg（内嵌图表）；不要删除已有有用内容。\n"
            "6) 你需要自己判断何时插入表格/图片：\n"
            "   - 对比、指标、清单、实验结果等结构化信息：用 <table class=\"tbl\"> 展示。\n"
            "   - 需要可视化流程/架构/实体关系：在合适位置插入标记 [[FLOW: ...]] 或 [[ER: ...]]（系统会自动渲染为图）。\n"
            "   - 需要图片但无法给出真实图片：插入 [[IMG: 图注/用途]] 作为图片占位（用户后续上传替换）。\n"
        )
        user = (
            f"当前HTML：\n{html}\n\n"
            f"用户要求：\n{instruction}\n"
            f"{selection_hint}\n"
            "请直接给出修改后的 HTML。"
        )

        return system, user, required_headings

    def apply_instruction(
        self,
        html: str,
        instruction: str,
        selection: str | None = None,
        template_html: str | None = None,
        title: str = "报告",
    ) -> EditResult:
        settings = get_ollama_settings()
        if not settings.enabled:
            raise OllamaError("未启用Ollama（WRITING_AGENT_USE_OLLAMA=0）")

        client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
        if not client.is_running():
            raise OllamaError("Ollama 未运行")

        system, user, required_headings = self.build_prompts(
            html=html,
            instruction=instruction,
            selection=selection,
            template_html=template_html,
        )

        edited = client.chat(system=system, user=user, temperature=0.2)
        cleaned = sanitize_html(edited)
        enforced = self._policy.enforce(cleaned, title=title, required_headings=required_headings)
        if not enforced.html.strip():
            raise OllamaError("模型返回为空")
        assistant = "已应用修改到左侧文档。"
        if enforced.fixes:
            assistant += "（已自动补齐结构）"
        return EditResult(html=enforced.html, assistant=assistant)

    def bootstrap(self, topic: str | None = None, template_html: str | None = None) -> str:
        t = (topic or "").strip() or "未命名报告"
        base = (template_html or "").strip()
        if base:
            base = base.replace("{{TITLE}}", t).replace("[TITLE]", t)
            if "<h1" not in base.lower():
                base = f"<h1>{t}</h1>" + base
            raw = base
        else:
            raw = f"<h1>{t}</h1>"
        required_headings = extract_template_headings(base) if base else None
        enforced = self._policy.enforce(raw, title=t, required_headings=required_headings)
        return sanitize_html(enforced.html)
