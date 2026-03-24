"""Runtime section streaming, segmentation, and final normalization helpers."""

from __future__ import annotations

from writing_agent.v2.graph_runner import *  # noqa: F401,F403
from writing_agent.v2 import graph_runner as _graph_runner_module
from writing_agent.v2.graph_runner_runtime_common_domain import (
    _guarded_stream_structured_blocks,
    _runtime_escape_prompt_text,
    _validate_reference_items,
)
from writing_agent.v2.graph_runner_runtime_segment_domain import (
    _assemble_section_segment_texts,
    _collect_section_segment_hints,
    _draft_section_with_optional_segments,
    _drain_segment_trace_events,
    _is_segment_candidate_title,
    _plan_section_segments,
    _section_segment_enabled,
    _section_segment_max_segments,
    _section_segment_target_chars,
    _section_segment_threshold_chars,
    _split_integer_budget,
    _split_list_evenly,
)
from writing_agent.v2 import graph_runner_runtime_output_domain as output_domain

# Ensure helper module sees internal/private symbols re-exported by graph_runner.
for _name in dir(_graph_runner_module):
    if _name.startswith("__"):
        continue
    if _name not in globals():
        globals()[_name] = getattr(_graph_runner_module, _name)

def _compute_section_targets(*, sections: list[str], base_min_paras: int, total_chars: int) -> dict[str, SectionTargets]:
    weights = _load_section_weights()
    out: dict[str, SectionTargets] = {}
    total_weight = 0.0
    per_sec_weight: dict[str, float] = {}
    for sec in sections:
        title = _section_title(sec) or sec
        w = weights.get(title)
        if w is None:
            w = _guess_section_weight(title)
        per_sec_weight[sec] = max(0.2, float(w))
        total_weight += per_sec_weight[sec]
    total_weight = total_weight or max(1.0, float(len(sections)))
    for sec in sections:
        title = (_section_title(sec) or sec).strip()
        share = int(round(float(total_chars) * (per_sec_weight.get(sec, 1.0) / total_weight))) if total_chars > 0 else 0
        min_chars = max(220, int(share * 0.7)) if share > 0 else 800
        max_chars = _max_chars_for_section(title)
        min_tables = 1 if "结果" in title or "数据" in title else 0
        min_figures = 0
        out[sec] = SectionTargets(
            weight=per_sec_weight.get(sec, 1.0),
            min_paras=base_min_paras,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
        )
    return out


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





def _generate_section_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    section: str,
    section_id_override: str = "",
    parent_section: str,
    instruction: str,
    analysis_summary: str,
    evidence_summary: str,
    allowed_urls: list[str],
    plan_hint: str,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
    reference_items: list[dict],
    text_store: TextStore | None,
) -> str:
    client = get_default_provider(
        model=model,
        timeout_s=_section_timeout_s(),
        route_key=f"v2.section.draft:{section}",
    )
    table_hint = ""
    fig_hint = ""
    if min_tables > 0 or section in {"结果", "数据分析", "Results"}:
        table_hint = "\nPlease include at least one table (use table blocks)."
    if min_figures > 0:
        fig_hint = (
            "\nPlease include at least one figure block only when the section truly needs a diagram. "
            "Each figure block must use type=figure plus kind+caption+data; kind is limited to flow/architecture/bar/line/pie/timeline/sequence/er. "
            "Match kind to caption semantics: share/composition->pie, trend/change/growth->line, comparison/ranking->bar, stage/roadmap/evolution->timeline, entity/schema->er, interaction->sequence, architecture/framework->architecture, and use flow only for real stepwise processes. "
            "Never emit caption-only figure blocks."
        )

    sec_name = (_section_title(section) or section).strip()
    is_reference = _is_reference_section(sec_name)
    rag_context = _maybe_rag_context(instruction=instruction, section=sec_name)
    ref_items = reference_items or []
    section_id = str(section_id_override or "").strip() or _normalize_section_id(section)

    if is_reference and ref_items:
        lines = _format_reference_items(ref_items)
        ref_issues = _validate_reference_items(lines)
        if ref_issues:
            out_queue.put(
                {
                    "event": "reference_format_violation",
                    "section": section,
                    "section_id": section_id,
                    "issues": list(ref_issues),
                }
            )
            raise ValueError("reference_format_violation")
        text = "\n".join([ln for ln in lines if ln.strip()]).strip()
        if text:
            block_id = text_store.put_text(text) if text_store else ""
            payload = {"event": "section", "phase": "delta", "section": section, "delta": text, "block_type": "reference"}
            if block_id:
                payload["block_id"] = block_id
            out_queue.put(payload)
        return text

    route, prompt_meta = _route_prompt_for_role(
        role="writer",
        instruction=instruction,
        intent="generate",
        section_title=sec_name,
    )
    try:
        config = get_prompt_config("writer", route=route)
    except TypeError:
        config = get_prompt_config("writer")
    out_queue.put(
        {
            "event": "prompt_route",
            "stage": "writer_section",
            "section": section,
            "section_id": section_id,
            "metadata": prompt_meta,
        }
    )
    system, user = PromptBuilder.build_writer_prompt(
        section_title=sec_name,
        plan_hint=plan_hint or "",
        doc_title=title,
        analysis_summary=analysis_summary or instruction,
        section_id=section_id,
        previous_content=None,
        rag_context=rag_context,
        route=route,
    )
    if table_hint:
        system += f"{table_hint}"
    if fig_hint:
        system += f"{fig_hint}"
    if ref_items:
        system += "\nUse bracket citations like [1]; citation numbers must come from the available source list.\n"
        source_lines = [
            f"[{i+1}] {_runtime_escape_prompt_text(str(s.get('title') or s.get('url') or s.get('id') or '').strip())} "
            f"{_runtime_escape_prompt_text(str(s.get('url') or '').strip())}".strip()
            for i, s in enumerate(ref_items[:12])
        ]
        user += (
            "\n<available_sources>\n"
            + ("\n".join(source_lines) if source_lines else "(none)")
            + "\n</available_sources>\n\n"
        )
    provider_name = get_provider_name()
    num_predict = _predict_num_tokens(min_chars=min_chars, max_chars=max_chars, is_reference=is_reference)
    deadline = time.time() + _section_timeout_s()
    txt = _guarded_stream_structured_blocks(
        provider_name=provider_name,
        model=model,
        client=client,
        system=system,
        user=user,
        out_queue=out_queue,
        section=section,
        section_id=section_id,
        is_reference=is_reference,
        num_predict=num_predict,
        deadline=deadline,
        strict_json=True,
        text_store=text_store,
    )
    out = _postprocess_section(
        section,
        txt,
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
    )
    if ref_items and not is_reference and not re.search(r"\[\d+\]", out):
        out = out.rstrip() + " [1]"
    return out

def _runtime_split_sentences(text: str) -> list[str]:
    return list(output_domain._runtime_split_sentences(text))



def _runtime_sentence_is_unsupported_claim(text: str) -> bool:
    return bool(output_domain._runtime_sentence_is_unsupported_claim(text))



def _prune_unsupported_claim_paragraphs(text: str) -> str:
    return str(output_domain._prune_unsupported_claim_paragraphs(text))



def _normalize_final_output(text: str, *, expected_sections: list[str] | None = None, title_override: str = "") -> str:
    return str(
        output_domain._normalize_final_output(
            text,
            expected_sections=expected_sections,
            title_override=title_override,
        )
    )





def _ensure_section_minimums_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    section: str,
    parent_section: str,
    instruction: str,
    analysis_summary: str,
    evidence_summary: str,
    allowed_urls: list[str],
    plan_hint: str,
    dimension_hints: list[str] | None,
    draft: str,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
) -> str:
    provider_name = get_provider_name()

    def _runtime_continue_stream(**kwargs):
        return _guarded_stream_structured_blocks(
            provider_name=provider_name,
            model=model,
            **kwargs,
        )

    try:
        return graph_section_draft_domain.ensure_section_minimums_stream(
            base_url=base_url,
            model=model,
            title=title,
            section=section,
            parent_section=parent_section,
            instruction=instruction,
            analysis_summary=analysis_summary,
            evidence_summary=evidence_summary,
            allowed_urls=allowed_urls,
            plan_hint=plan_hint,
            dimension_hints=dimension_hints,
            draft=draft,
            min_paras=min_paras,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
            out_queue=out_queue,
            postprocess_section=_postprocess_section,
            stream_structured_blocks=_runtime_continue_stream,
            normalize_section_id=_normalize_section_id,
            predict_num_tokens=lambda min_chars, max_chars, is_reference: _predict_num_tokens(
                min_chars=min_chars,
                max_chars=max_chars,
                is_reference=is_reference,
            ),
            is_reference_section=_is_reference_section,
            section_timeout_s=_section_timeout_s,
            provider_factory=get_default_provider,
        )
    except AttributeError:
        return _postprocess_section(
            section,
            draft,
            min_paras=min_paras,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
        )



__all__ = [name for name in globals() if not name.startswith("__")]
