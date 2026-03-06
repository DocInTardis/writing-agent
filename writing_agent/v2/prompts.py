"""Prompt registry and routing for v2 graph generation flows.

This module centralizes prompt suites for planner / analysis / writer / revision and
provides a deterministic router based on intent/doc_type/language/quality_profile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from writing_agent.v2.prompt_registry import PromptRegistry


def _escape_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))


def _language_of(text: str) -> str:
    s = str(text or "")
    if not s.strip():
        return "zh-CN"
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    alpha = sum(1 for ch in s if ch.isascii() and ch.isalpha())
    if cjk == 0 and alpha > 0:
        return "en"
    if cjk >= max(4, alpha // 2):
        return "zh-CN"
    return "mixed"


@dataclass(frozen=True)
class PromptConfig:
    temperature: float = 0.2
    max_tokens: Optional[int] = None


@dataclass(frozen=True)
class PlannerConfig(PromptConfig):
    temperature: float = 0.25


@dataclass(frozen=True)
class AnalysisConfig(PromptConfig):
    temperature: float = 0.1


@dataclass(frozen=True)
class WriterConfig(PromptConfig):
    temperature: float = 0.2
    stream: bool = True


@dataclass(frozen=True)
class RevisionConfig(PromptConfig):
    temperature: float = 0.15


@dataclass(frozen=True)
class PromptRouteContext:
    intent: str = "generate"
    doc_type: str = "academic"
    language: str = "zh-CN"
    quality_profile: str = "academic_cnki_default"
    revise_scope: str = "none"  # none|local|full
    instruction: str = ""
    section_title: str = ""


@dataclass(frozen=True)
class PromptSuite:
    suite_id: str
    planner_system: str
    planner_few_shot: str
    analysis_system: str
    writer_system: str
    writer_note: str
    revision_system: str


@dataclass(frozen=True)
class PromptRouteDecision:
    role: str
    suite_id: str
    prompt_id: str
    version: str
    owner: str
    route_reason: str
    route_key: str
    payload: dict[str, Any]


_ACADEMIC_CN_PLANNER_FEW_SHOT = """示例1:
{
  "title":"面向多智能体写作系统的质量闭环机制研究",
  "total_chars":9000,
  "sections":[
    {"title":"摘要","target_chars":300,"key_points":["研究目标","方法概述","主要结论"],"context_from_previous":false,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"关键词","target_chars":80,"key_points":["3-5个关键词"],"context_from_previous":false,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"引言","target_chars":1200,"key_points":["研究背景","问题定义","贡献点"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":["研究现状"]},
    {"title":"系统架构与方法","target_chars":2400,"key_points":["状态机","路由机制","质量门禁"],"context_from_previous":true,"figures":[{"type":"flow","caption":"系统流程图"}],"tables":[{"caption":"模块职责对照","columns":["模块","职责"]}],"evidence_queries":["state machine","quality gate"]},
    {"title":"实验与结果分析","target_chars":2200,"key_points":["实验设置","评价指标","消融对比"],"context_from_previous":true,"figures":[{"type":"line","caption":"关键指标趋势"}],"tables":[{"caption":"实验结果对比","columns":["方法","指标","结果"]}],"evidence_queries":["benchmark","ablation"]},
    {"title":"结论与展望","target_chars":900,"key_points":["结论总结","局限性","后续工作"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"参考文献","target_chars":600,"key_points":["GB/T 7714"],"context_from_previous":false,"figures":[],"tables":[],"evidence_queries":["可核验来源"]}
  ]
}

示例2:
{
  "title":"知识增强写作代理在技术文档自动化中的应用",
  "total_chars":7000,
  "sections":[
    {"title":"摘要","target_chars":260,"key_points":["问题","方法","效果"],"context_from_previous":false,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"关键词","target_chars":70,"key_points":["知识增强","文档生成","可追溯性"],"context_from_previous":false,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"需求分析","target_chars":1100,"key_points":["业务目标","约束条件"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"关键技术实现","target_chars":2100,"key_points":["Prompt 路由","结构化输出","错误恢复"],"context_from_previous":true,"figures":[{"type":"architecture","caption":"模块架构图"}],"tables":[],"evidence_queries":["structured output"]},
    {"title":"工程验证","target_chars":1800,"key_points":["稳定性","可维护性","导出一致性"],"context_from_previous":true,"figures":[],"tables":[{"caption":"回归测试集","columns":["场景","期望","结果"]}],"evidence_queries":[]},
    {"title":"结论","target_chars":700,"key_points":["价值与边界"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"参考文献","target_chars":500,"key_points":["可核验来源"],"context_from_previous":false,"figures":[],"tables":[],"evidence_queries":[]}
  ]
}"""

_TECH_REPORT_PLANNER_FEW_SHOT = """示例:
{
  "title":"写作代理系统技术报告",
  "total_chars":5000,
  "sections":[
    {"title":"背景与目标","target_chars":700,"key_points":["目标与范围"],"context_from_previous":false,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"系统架构","target_chars":1400,"key_points":["模块边界","数据流"],"context_from_previous":true,"figures":[{"type":"architecture","caption":"系统架构"}],"tables":[],"evidence_queries":[]},
    {"title":"关键实现","target_chars":1500,"key_points":["路由逻辑","状态管理","异常兜底"],"context_from_previous":true,"figures":[],"tables":[{"caption":"接口清单","columns":["接口","输入","输出"]}],"evidence_queries":[]},
    {"title":"测试与质量","target_chars":900,"key_points":["测试覆盖","质量门禁"],"context_from_previous":true,"figures":[],"tables":[{"caption":"测试结果","columns":["用例","结果"]}],"evidence_queries":[]},
    {"title":"结论与后续计划","target_chars":500,"key_points":["结论","改进方向"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":[]}
  ]
}"""

_WEEKLY_REPORT_PLANNER_FEW_SHOT = """示例:
{
  "title":"项目周报",
  "total_chars":1800,
  "sections":[
    {"title":"本周工作","target_chars":800,"key_points":["完成项","结果"],"context_from_previous":false,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"问题与风险","target_chars":450,"key_points":["阻塞点","影响"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"下周计划","target_chars":450,"key_points":["目标","里程碑"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"需协助事项","target_chars":100,"key_points":["资源诉求"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":[]}
  ]
}"""


def _planner_system_cn(role_hint: str) -> str:
    return (
        "你是严格的文档规划代理。\n"
        "只返回 JSON，不要 markdown，不要解释。\n"
        "Schema: {title:string,total_chars:number,sections:[{title:string,target_chars:number,key_points:[string],"
        "context_from_previous:boolean,figures:[{type,caption}],tables:[{caption,columns}],evidence_queries:[string]}]}.\n"
        f"当前任务类型: {role_hint}."
    )


def _analysis_system_cn() -> str:
    return (
        "你是需求解析代理。\n"
        "只返回 JSON，不要 markdown。\n"
        "Schema: {topic:string,doc_type:string,audience:string,style:string,keywords:[string],must_include:[string],"
        "avoid_sections:[string],constraints:[string],questions:[string],doc_structure:string,confidence:{title:number,purpose:number,length:number,format:number}}."
    )


def _writer_system_cn(doc_style: str) -> str:
    return (
        "你是严格的分节写作代理。\n"
        "只返回 NDJSON，每行一个 JSON 对象。\n"
        "Schema: {\"section_id\":string,\"block_id\":string,\"type\":\"paragraph\"|\"list\"|\"table\"|\"figure\"|\"reference\","
        "\"text\"?:string,\"items\"?:[string],\"caption\"?:string,\"columns\"?:[string],\"rows\"?:[[string]]}.\n"
        f"文体要求: {doc_style}."
    )


def _revision_system_cn(scope: str) -> str:
    scope_note = "局部改写" if scope == "local" else "全文改写"
    return (
        "你是文档改写代理。\n"
        "严格遵守用户指令，尽量少改无关内容。\n"
        f"当前模式: {scope_note}."
    )


_PROMPT_SUITES: dict[str, PromptSuite] = {
    "academic_cn": PromptSuite(
        suite_id="academic_cn",
        planner_system=_planner_system_cn("学术论文"),
        planner_few_shot=_ACADEMIC_CN_PLANNER_FEW_SHOT,
        analysis_system=_analysis_system_cn(),
        writer_system=_writer_system_cn("中文学术论文"),
        writer_note=(
            "段落必须完整、可直接提交。"
            "避免口语化和提示词回声。"
            "引用必须可追溯，禁止编造来源。"
        ),
        revision_system=_revision_system_cn("full"),
    ),
    "technical_report_cn": PromptSuite(
        suite_id="technical_report_cn",
        planner_system=_planner_system_cn("技术报告"),
        planner_few_shot=_TECH_REPORT_PLANNER_FEW_SHOT,
        analysis_system=_analysis_system_cn(),
        writer_system=_writer_system_cn("中文技术报告"),
        writer_note=(
            "强调工程细节、接口定义与验证结果。"
            "段落必须完整，不输出占位符。"
        ),
        revision_system=_revision_system_cn("full"),
    ),
    "weekly_cn": PromptSuite(
        suite_id="weekly_cn",
        planner_system=_planner_system_cn("周报"),
        planner_few_shot=_WEEKLY_REPORT_PLANNER_FEW_SHOT,
        analysis_system=_analysis_system_cn(),
        writer_system=_writer_system_cn("中文周报"),
        writer_note="条目清晰，避免冗长。",
        revision_system=_revision_system_cn("full"),
    ),
    "revise_local_cn": PromptSuite(
        suite_id="revise_local_cn",
        planner_system=_planner_system_cn("局部改写"),
        planner_few_shot=_TECH_REPORT_PLANNER_FEW_SHOT,
        analysis_system=_analysis_system_cn(),
        writer_system=_writer_system_cn("局部改写"),
        writer_note="仅修改指定范围，保持上下文一致。",
        revision_system=_revision_system_cn("local"),
    ),
    "revise_full_cn": PromptSuite(
        suite_id="revise_full_cn",
        planner_system=_planner_system_cn("全文改写"),
        planner_few_shot=_TECH_REPORT_PLANNER_FEW_SHOT,
        analysis_system=_analysis_system_cn(),
        writer_system=_writer_system_cn("全文改写"),
        writer_note="保持章节结构与术语一致。",
        revision_system=_revision_system_cn("full"),
    ),
    "generic_en": PromptSuite(
        suite_id="generic_en",
        planner_system=(
            "You are a strict planning agent. Return JSON only. "
            "Schema: {title,total_chars,sections:[{title,target_chars,key_points,context_from_previous,figures,tables,evidence_queries}]}."
        ),
        planner_few_shot=_TECH_REPORT_PLANNER_FEW_SHOT,
        analysis_system=(
            "You are a requirement-analysis agent. Return JSON only. "
            "Schema: {topic,doc_type,audience,style,keywords,must_include,avoid_sections,constraints,questions,doc_structure}."
        ),
        writer_system=(
            "You are a strict section writer. Return NDJSON only with schema: "
            "{section_id,block_id,type,text,items,caption,columns,rows}."
        ),
        writer_note="Produce complete paragraphs and avoid meta instructions.",
        revision_system="You are a revision agent. Follow user feedback precisely.",
    ),
}


def _infer_doc_type(instruction: str, doc_type: str) -> str:
    explicit = str(doc_type or "").strip().lower()
    if explicit:
        return explicit
    raw = str(instruction or "").lower()
    if any(k in raw for k in ["周报", "weekly", "this week", "next week"]):
        return "weekly"
    if any(k in raw for k in ["技术报告", "report", "implementation", "工程"]):
        return "technical_report"
    if any(k in raw for k in ["论文", "thesis", "paper", "摘要", "关键词"]):
        return "academic"
    return "academic"


def _infer_intent(instruction: str, intent: str) -> str:
    explicit = str(intent or "").strip().lower()
    if explicit:
        return explicit
    raw = str(instruction or "").lower()
    if any(k in raw for k in ["改写", "润色", "rewrite", "revise"]):
        return "revise"
    if any(k in raw for k in ["提纲", "outline", "结构"]):
        return "plan"
    return "generate"


def _select_suite(context: PromptRouteContext) -> tuple[str, str]:
    lang = str(context.language or "zh-CN").lower()
    intent = str(context.intent or "generate").lower()
    doc_type = str(context.doc_type or "academic").lower()
    revise_scope = str(context.revise_scope or "none").lower()

    if not lang.startswith("zh") and lang != "mixed":
        return "generic_en", "language=en"

    if intent == "revise":
        if revise_scope == "local":
            return "revise_local_cn", "intent=revise,scope=local"
        return "revise_full_cn", "intent=revise,scope=full"

    if doc_type in {"weekly", "week", "weekly_report"}:
        return "weekly_cn", "doc_type=weekly"

    if doc_type in {"technical", "technical_report", "report"}:
        return "technical_report_cn", "doc_type=technical_report"

    return "academic_cn", "doc_type=academic"


def route_prompt(
    *,
    role: str,
    context: PromptRouteContext,
    registry: PromptRegistry | None = None,
    cohort: str = "default",
    user_key: str = "",
) -> PromptRouteDecision:
    role_key = str(role or "").strip().lower() or "writer"
    suite_id, reason = _select_suite(context)
    route_key = "|".join(
        [
            f"intent={context.intent}",
            f"doc_type={context.doc_type}",
            f"lang={context.language}",
            f"quality={context.quality_profile}",
            f"suite={suite_id}",
        ]
    )
    prompt_id = f"{role_key}.{suite_id}"
    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {}
    version = "builtin-v1"
    owner = "core-team"

    reg = registry or PromptRegistry()
    effective_cohort = str(cohort or "default").strip() or "default"
    policy = reg.release_policy()
    if effective_cohort in {"ab", "auto", "auto_ab"}:
        ratio_a = float(policy.get("ab_ratio_a", 0.5))
        cohort_seed = str(user_key or context.instruction or context.route_key if hasattr(context, "route_key") else "")
        effective_cohort = reg.choose_ab(prompt_id, user_key=cohort_seed or "anonymous", ratio_a=ratio_a)
        reason = f"{reason};ab={effective_cohort}"
    variant = reg.get_active(prompt_id, cohort=effective_cohort)
    if variant is not None:
        payload = dict(variant.payload or {})
        version = str(variant.version or version)
        owner = str(variant.owner or owner)

    return PromptRouteDecision(
        role=role_key,
        suite_id=suite_id,
        prompt_id=prompt_id,
        version=version,
        owner=owner,
        route_reason=f"{reason};cohort={effective_cohort};ts={now}",
        route_key=route_key,
        payload=payload,
    )


class PromptBuilder:
    """Prompt builders with route-aware suite selection and XML-tagged channels."""

    @staticmethod
    def build_route_context(
        *,
        instruction: str,
        intent: str = "",
        doc_type: str = "",
        language: str = "",
        quality_profile: str = "academic_cnki_default",
        revise_scope: str = "none",
        section_title: str = "",
    ) -> PromptRouteContext:
        inferred_lang = str(language or "").strip() or _language_of(instruction)
        inferred_intent = _infer_intent(instruction, intent)
        inferred_doc_type = _infer_doc_type(instruction, doc_type)
        return PromptRouteContext(
            intent=inferred_intent,
            doc_type=inferred_doc_type,
            language=inferred_lang,
            quality_profile=str(quality_profile or "academic_cnki_default"),
            revise_scope=str(revise_scope or "none"),
            instruction=str(instruction or ""),
            section_title=str(section_title or ""),
        )

    @staticmethod
    def _suite_for(route: PromptRouteDecision | None, context: PromptRouteContext | None) -> PromptSuite:
        if route and route.suite_id in _PROMPT_SUITES:
            return _PROMPT_SUITES[route.suite_id]
        if context:
            suite_id, _ = _select_suite(context)
            return _PROMPT_SUITES.get(suite_id, _PROMPT_SUITES["academic_cn"])
        return _PROMPT_SUITES["academic_cn"]

    @staticmethod
    def build_planner_prompt(
        title: str,
        total_chars: int,
        sections: list[str],
        instruction: str,
        *,
        route: PromptRouteDecision | None = None,
        context: PromptRouteContext | None = None,
    ) -> tuple[str, str]:
        suite = PromptBuilder._suite_for(route, context)
        system = suite.planner_system + "\n" + suite.planner_few_shot
        if route and route.payload.get("planner_system"):
            system = str(route.payload.get("planner_system") or system)
        section_list = "\n".join(
            [f"- {_escape_prompt_text(s)}" for s in (sections or []) if str(s).strip()]
        ) or "- (none)"
        user = (
            "<task>plan_document_structure</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Return strict JSON only.\n"
            "- Keep section titles within provided section_candidates.\n"
            "</constraints>\n"
            f"<report_title>\n{_escape_prompt_text(title)}\n</report_title>\n"
            f"<total_chars>\n{int(total_chars or 0)}\n</total_chars>\n"
            f"<section_candidates>\n{section_list}\n</section_candidates>\n"
            f"<user_requirement>\n{_escape_prompt_text(instruction)}\n</user_requirement>\n"
            "Return planning JSON now."
        )
        return system, user

    @staticmethod
    def build_analysis_prompt(
        instruction: str,
        excerpt: str,
        *,
        route: PromptRouteDecision | None = None,
        context: PromptRouteContext | None = None,
    ) -> tuple[str, str]:
        suite = PromptBuilder._suite_for(route, context)
        system = suite.analysis_system
        if route and route.payload.get("analysis_system"):
            system = str(route.payload.get("analysis_system") or system)
        user = (
            "<task>analyze_user_requirement</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Return strict JSON only.\n"
            "</constraints>\n"
            f"<user_requirement>\n{_escape_prompt_text(instruction)}\n</user_requirement>\n"
            f"<existing_text_excerpt>\n{_escape_prompt_text(excerpt)}\n</existing_text_excerpt>\n"
            "Return analysis JSON now."
        )
        return system, user

    @staticmethod
    def build_writer_prompt(
        section_title: str,
        plan_hint: str,
        doc_title: str,
        analysis_summary: str,
        section_id: str,
        previous_content: Optional[str] = None,
        rag_context: Optional[str] = None,
        *,
        route: PromptRouteDecision | None = None,
        context: PromptRouteContext | None = None,
    ) -> tuple[str, str]:
        suite = PromptBuilder._suite_for(route, context)
        system = suite.writer_system + "\n" + suite.writer_note
        if route and route.payload.get("writer_system"):
            system = str(route.payload.get("writer_system") or system)
        user = (
            "<task>write_section_blocks</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Return NDJSON only.\n"
            "- section_id must match exactly.\n"
            "</constraints>\n"
            f"<section_id>\n{_escape_prompt_text(section_id)}\n</section_id>\n"
            f"<section_title>\n{_escape_prompt_text(section_title)}\n</section_title>\n"
            f"<document_title>\n{_escape_prompt_text(doc_title)}\n</document_title>\n"
            f"<analysis_summary>\n{_escape_prompt_text(analysis_summary)}\n</analysis_summary>\n"
            f"<plan_hint>\n{_escape_prompt_text(plan_hint)}\n</plan_hint>\n"
        )
        if previous_content:
            user += f"<previous_content>\n{_escape_prompt_text(previous_content)}\n</previous_content>\n"
        if rag_context:
            user += f"<retrieved_context>\n{_escape_prompt_text(rag_context)}\n</retrieved_context>\n"
        user += "Return NDJSON now."
        return system, user

    @staticmethod
    def build_reference_prompt(sources: list[dict]) -> tuple[str, str]:
        system = (
            "你是参考文献格式化代理。输出最终参考文献列表，不要解释。"
            "优先采用 GB/T 7714-2015。"
        )
        sources_text = "\n".join(
            [
                f"[{i + 1}] {_escape_prompt_text(s.get('title', ''))} {_escape_prompt_text(s.get('url', ''))}".strip()
                for i, s in enumerate(sources or [])
            ]
        ) or "(none)"
        user = (
            "<task>format_references</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Follow GB/T 7714-2015 style.\n"
            "</constraints>\n"
            f"<sources>\n{sources_text}\n</sources>\n"
            "Return formatted references now."
        )
        return system, user

    @staticmethod
    def build_revision_prompt(
        original_text: str,
        feedback: str,
        *,
        route: PromptRouteDecision | None = None,
        context: PromptRouteContext | None = None,
    ) -> tuple[str, str]:
        suite = PromptBuilder._suite_for(route, context)
        system = suite.revision_system
        if route and route.payload.get("revision_system"):
            system = str(route.payload.get("revision_system") or system)
        user = (
            "<task>revise_document</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Keep style consistent and minimize unnecessary edits.\n"
            "</constraints>\n"
            f"<original_text>\n{_escape_prompt_text(original_text)}\n</original_text>\n"
            f"<user_feedback>\n{_escape_prompt_text(feedback)}\n</user_feedback>\n"
            "Return revised content."
        )
        return system, user


def get_prompt_config(agent_type: str, *, route: PromptRouteDecision | None = None) -> PromptConfig:
    role = str(agent_type or "").strip().lower()
    default_map: dict[str, PromptConfig] = {
        "planner": PlannerConfig(),
        "analysis": AnalysisConfig(),
        "writer": WriterConfig(),
        "reference": PromptConfig(temperature=0.1),
        "revision": RevisionConfig(),
    }
    cfg = default_map.get(role, PromptConfig())
    if route and isinstance(route.payload, dict):
        value = route.payload.get("temperature")
        try:
            if value is not None:
                cfg = PromptConfig(temperature=float(value), max_tokens=cfg.max_tokens)
        except Exception:
            pass
    return cfg


def build_prompt_route(
    *,
    role: str,
    instruction: str,
    intent: str = "",
    doc_type: str = "",
    language: str = "",
    quality_profile: str = "academic_cnki_default",
    revise_scope: str = "none",
    section_title: str = "",
    registry: PromptRegistry | None = None,
    cohort: str = "default",
    user_key: str = "",
) -> tuple[PromptRouteContext, PromptRouteDecision]:
    context = PromptBuilder.build_route_context(
        instruction=instruction,
        intent=intent,
        doc_type=doc_type,
        language=language,
        quality_profile=quality_profile,
        revise_scope=revise_scope,
        section_title=section_title,
    )
    decision = route_prompt(
        role=role,
        context=context,
        registry=registry,
        cohort=cohort,
        user_key=user_key,
    )
    return context, decision


def prompt_route_metadata(route: PromptRouteDecision | None) -> dict[str, str]:
    if route is None:
        return {}
    return {
        "prompt_id": route.prompt_id,
        "prompt_version": route.version,
        "prompt_owner": route.owner,
        "prompt_suite": route.suite_id,
        "prompt_route_reason": route.route_reason,
        "prompt_route_key": route.route_key,
    }


def instruction_language(instruction: str) -> str:
    return _language_of(instruction)


def looks_like_weekly_instruction(instruction: str) -> bool:
    s = str(instruction or "").lower()
    if not s.strip():
        return False
    return bool(re.search(r"(周报|weekly|this week|next week)", s, flags=re.IGNORECASE))
