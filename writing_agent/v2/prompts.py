"""Prompt registry and routing for v2 graph generation flows.

This module centralizes prompt suites for planner / analysis / writer / revision and
provides a deterministic router based on intent/doc_type/language/quality_profile.
"""

# Prompt contract markers retained in the compatibility shell:
# <task>plan_document_structure</task>
# <task>analyze_user_requirement</task>
# <task>write_section_blocks</task>
# <task>format_references</task>
# <task>revise_document</task>
# <constraints>

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from writing_agent.v2.prompt_registry import PromptRegistry
from writing_agent.v2.prompt_builder_domain import (
    _suite_for as _prompt_builder_suite_for,
    build_analysis_prompt as _prompt_builder_build_analysis_prompt,
    build_planner_prompt as _prompt_builder_build_planner_prompt,
    build_reference_prompt as _prompt_builder_build_reference_prompt,
    build_revision_prompt as _prompt_builder_build_revision_prompt,
    build_route_context as _prompt_builder_build_route_context,
    build_writer_prompt as _prompt_builder_build_writer_prompt,
)


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
    revise_scope: str = "none"
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


from writing_agent.v2 import prompts_suite_domain as suite_domain


_PROMPT_SUITES: dict[str, PromptSuite] = suite_domain.build_prompt_suites(PromptSuite)


def _escape_prompt_text(raw: object) -> str:
    return suite_domain._escape_prompt_text(raw)


def _contains_cjk(text: str) -> bool:
    return suite_domain._contains_cjk(text)


def _language_of(text: str) -> str:
    return suite_domain._language_of(text)


def _writer_visual_preference(plan_hint: str, section_title: str) -> str:
    return suite_domain._writer_visual_preference(plan_hint, section_title)


def _planner_system_cn(role_hint: str) -> str:
    return suite_domain._planner_system_cn(role_hint)


def _analysis_system_cn() -> str:
    return suite_domain._analysis_system_cn()


def _writer_system_cn(doc_style: str) -> str:
    return suite_domain._writer_system_cn(doc_style)


def _revision_system_cn(scope: str) -> str:
    return suite_domain._revision_system_cn(scope)


def _infer_doc_type(instruction: str, doc_type: str) -> str:
    return suite_domain._infer_doc_type(instruction, doc_type)


def _infer_intent(instruction: str, intent: str) -> str:
    return suite_domain._infer_intent(instruction, intent)


def _select_suite(context: PromptRouteContext) -> tuple[str, str]:
    return suite_domain._select_suite(context)


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
    @staticmethod
    def build_route_context(*args, **kwargs):
        return _prompt_builder_build_route_context(*args, **kwargs)

    @staticmethod
    def _suite_for(*args, **kwargs):
        return _prompt_builder_suite_for(*args, **kwargs)

    @staticmethod
    def build_planner_prompt(*args, **kwargs):
        return _prompt_builder_build_planner_prompt(*args, **kwargs)

    @staticmethod
    def build_analysis_prompt(*args, **kwargs):
        return _prompt_builder_build_analysis_prompt(*args, **kwargs)

    @staticmethod
    def build_writer_prompt(*args, **kwargs):
        return _prompt_builder_build_writer_prompt(*args, **kwargs)

    @staticmethod
    def build_reference_prompt(*args, **kwargs):
        return _prompt_builder_build_reference_prompt(*args, **kwargs)

    @staticmethod
    def build_revision_prompt(*args, **kwargs):
        return _prompt_builder_build_revision_prompt(*args, **kwargs)


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
    return suite_domain.looks_like_weekly_instruction(instruction)


__all__ = [name for name in globals() if not name.startswith("__")]
