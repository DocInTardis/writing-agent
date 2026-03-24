"""Graph Runner module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, wait
import ctypes
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from writing_agent.v2.prompt_registry import PromptRegistry
from writing_agent.v2.prompts import (
    PromptBuilder,
    build_prompt_route,
    get_prompt_config,
    instruction_language,
    prompt_route_metadata,
)

from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings  # backward-compat exports
from writing_agent.llm.factory import get_default_provider
from writing_agent.sections_catalog import find_section_description, section_catalog_text
from writing_agent.v2.doc_format import DocBlock, ParsedDoc, parse_report_text
from writing_agent.v2.cache import LocalCache, AcademicPhraseCache  # cache backends
from writing_agent.v2 import (
    draft_model_domain,
    graph_aggregate_domain,
    graph_plan_domain,
    graph_reference_domain,
    graph_section_draft_domain,
    graph_text_sanitize_domain,
)
from writing_agent.v2.text_store import TextStore
from writing_agent.v2 import graph_runner_post_domain as post_domain
from writing_agent.v2.graph_runner_policy_domain import *
from writing_agent.v2 import graph_runner_core_outline_domain as core_outline_domain
from writing_agent.v2 import graph_runner_core_utils_domain as core_utils_domain
from writing_agent.v2 import graph_runner_core_plan_domain as core_plan_domain

for _post_name in (
    "_extract_h2_titles _count_citations _light_self_check _plan_title _normalize_title_line _default_title "
    "_fallback_title_from_instruction _plan_title_sections _guess_title _wants_acknowledgement _filter_ack_headings "
    "_filter_ack_outline _filter_disallowed_outline _is_engineering_instruction _boost_media_targets "
    "_generate_section_stream _maybe_rag_context _mcp_rag_enabled _mcp_rag_retrieve _looks_like_rag_meta_line "
    "_has_cjk _is_mostly_ascii_line _strip_rag_meta_lines _plan_point_paragraph _expand_with_context "
    "_select_models_by_memory _default_worker_models _looks_like_embedding_model _ollama_installed_models "
    "_ollama_model_sizes_gb _get_memory_bytes _sanitize_output_text _strip_markdown_noise _should_merge_tail "
    "_clean_generated_text _normalize_final_output _is_reference_section _looks_like_heading_text "
    "_strip_inline_headings _format_references _ensure_media_markers _generic_fill_paragraph _fast_fill_references "
    "_fast_fill_section _postprocess_section _ensure_section_minimums_stream _strip_reference_like_lines "
    "_normalize_section_id _stream_structured_blocks _trim_total_chars _encode_section _split_section_token "
    "_section_title _sections_from_outline _map_section_parents _merge_sections_text _apply_section_updates"
).split():
    globals()[_post_name] = getattr(post_domain, _post_name)
del _post_name



def _dedupe_keep_order(items: list[str]) -> list[str]:
    return list(core_utils_domain._dedupe_keep_order(items))


def _canonicalize_section_name(text: str) -> str:
    return str(core_utils_domain._canonicalize_section_name(text))


@dataclass(frozen=True)
class GenerateConfig:
    workers: int = 8  # default 8 workers (raised from 4 for better CPU utilization)
    worker_models: list[str] | None = None
    aggregator_model: str | None = None
    min_section_paragraphs: int = 4
    min_total_chars: int = 1800
    max_total_chars: int = 0


def _escape_prompt_text(raw: object) -> str:
    return str(core_utils_domain._escape_prompt_text(raw))


from writing_agent.v2.graph_runner_config_domain import *


class ModelPool:
    def __init__(self, models: list[str]) -> None:
        self._models = [m for m in (models or []) if m]
        self._lock = threading.Lock()
        self._i = 0

    def next(self) -> str:
        with self._lock:
            if not self._models:
                return ""
            m = self._models[self._i % len(self._models)]
            self._i += 1
            return m


@dataclass(frozen=True)
class SectionTargets:
    weight: float
    min_paras: int
    min_chars: int
    max_chars: int
    min_tables: int
    min_figures: int


@dataclass(frozen=True)
class PlanSection:
    title: str
    target_chars: int
    min_chars: int
    max_chars: int
    min_tables: int
    min_figures: int
    key_points: list[str]
    figures: list[dict]
    tables: list[dict]
    evidence_queries: list[str]


def _split_csv_env(raw: str) -> list[str]:
    return list(core_utils_domain._split_csv_env(raw))


def _require_json_response(
    *,
    client,
    system: str,
    user: str,
    stage: str,
    temperature: float,
    max_retries: int = 2,
) -> dict:
    return dict(
        core_utils_domain._require_json_response(
            client=client,
            system=system,
            user=user,
            stage=stage,
            temperature=temperature,
            max_retries=max_retries,
        )
    )


def _plan_timeout_s() -> float:
    return float(core_utils_domain._plan_timeout_s())


def _analysis_timeout_s() -> float:
    return float(core_utils_domain._analysis_timeout_s())


def _section_timeout_s() -> float:
    return float(core_utils_domain._section_timeout_s())


def _is_evidence_enabled() -> bool:
    return bool(core_utils_domain._is_evidence_enabled())


def _truncate_text(text: str, *, max_chars: int = 1200) -> str:
    return str(core_utils_domain._truncate_text(text, max_chars=max_chars))

_DISALLOWED_SECTIONS = {"\u76ee\u5f55", "Table of Contents", "Contents"}
_ACK_SECTIONS = {"\u81f4\u8c22", "\u9e23\u8c22"}


def _route_prompt_for_role(
    *,
    role: str,
    instruction: str,
    intent: str,
    section_title: str = "",
    revise_scope: str = "none",
) -> tuple[object, dict[str, str]]:
    return core_utils_domain._route_prompt_for_role(
        role=role,
        instruction=instruction,
        intent=intent,
        section_title=section_title,
        revise_scope=revise_scope,
    )


def _pick_draft_models(worker_models: list[str], *, agg_model: str, fallback: str) -> tuple[str, str]:
    return core_utils_domain._pick_draft_models(worker_models, agg_model=agg_model, fallback=fallback)


def _extract_json_block(text: str) -> str:
    return str(core_utils_domain._extract_json_block(text))

def _compute_section_weights(sections: list[str]) -> dict[str, float]:
    return core_outline_domain._compute_section_weights(sections)


def _classify_section_type(title: str) -> str:
    return core_outline_domain._classify_section_type(title)


def _default_plan_map(
    *,
    sections: list[str],
    base_targets: dict[str, SectionTargets],
    total_chars: int,
) -> dict[str, PlanSection]:
    return core_outline_domain._default_plan_map(
        sections=sections,
        base_targets=base_targets,
        total_chars=total_chars,
    )


def _plan_sections_with_model(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    sections: list[str],
    total_chars: int,
    trace_hook=None,
) -> dict:
    return dict(
        core_plan_domain._plan_sections_with_model(
            base_url=base_url,
            model=model,
            title=title,
            instruction=instruction,
            sections=sections,
            total_chars=total_chars,
            trace_hook=trace_hook,
        )
    )


def _sanitize_planned_sections(sections: list[str]) -> list[str]:
    return core_outline_domain._sanitize_planned_sections(sections)


def _clean_section_title(title: str) -> str:
    return core_outline_domain._clean_section_title(title)


def _clean_outline_title(title: str) -> str:
    return core_outline_domain._clean_outline_title(title)


def _strip_chapter_prefix_local(text: str) -> str:
    return core_outline_domain._strip_chapter_prefix_local(text)


def _sanitize_section_tokens(sections: list[str], *, keep_full_titles: bool = False) -> list[str]:
    return core_outline_domain._sanitize_section_tokens(sections, keep_full_titles=keep_full_titles)


def _sanitize_outline(outline: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return core_outline_domain._sanitize_outline(outline)


def _plan_sections_list_with_model(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    trace_hook=None,
) -> list[str]:
    return list(
        core_plan_domain._plan_sections_list_with_model(
            base_url=base_url,
            model=model,
            title=title,
            instruction=instruction,
            trace_hook=trace_hook,
        )
    )


def _predict_num_tokens(*, min_chars: int, max_chars: int, is_reference: bool) -> int:
    return int(core_utils_domain._predict_num_tokens(min_chars=min_chars, max_chars=max_chars, is_reference=is_reference))


def _normalize_plan_map(
    *,
    plan_raw: dict,
    sections: list[str],
    base_targets: dict[str, SectionTargets],
    total_chars: int,
) -> dict[str, PlanSection]:
    return dict(
        core_plan_domain._normalize_plan_map(
            plan_raw=plan_raw,
            sections=sections,
            base_targets=base_targets,
            total_chars=total_chars,
        )
    )


def _stabilize_plan_map_minimums(
    *,
    plan_map: dict[str, PlanSection],
    sections: list[str],
    base_targets: dict[str, SectionTargets],
    total_chars: int,
) -> dict[str, PlanSection]:
    return dict(
        core_plan_domain._stabilize_plan_map_minimums(
            plan_map=plan_map,
            sections=sections,
            base_targets=base_targets,
            total_chars=total_chars,
        )
    )


__all__ = [name for name in globals() if not name.startswith("__")]