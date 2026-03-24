"""Runtime helpers for resolving plan contracts and targets."""

from __future__ import annotations

def _base():
    from writing_agent.v2 import graph_runner_runtime_session_domain as base

    return base


def _academic_contract_preferred_order(runtime_api, paradigm_name: str) -> list[str]:
    if paradigm_name == "bibliometric":
        return list(runtime_api._bibliometric_section_spine())
    return [
        "摘要",
        "关键词",
        "引言",
        "相关研究",
        "研究设计",
        "研究结果",
        "讨论分析",
        "结论",
        "展望",
        "参考文献",
    ]


def resolve_plan_contract_state(
    runtime_api,
    *,
    instruction: str,
    analysis: dict,
    analysis_summary: str,
    sections: list[str],
    title: str,
    paradigm_name: str,
    force_required_outline_only: bool,
    config,
    settings,
    agg_model: str,
    prompt_trace: list[dict],
    prompt_events: list[dict],
    capture_prompt_trace,
    build_final_event,
):
    base = _base()
    total_chars = runtime_api._target_total_chars(config)
    section_contracts = runtime_api._build_section_contracts(
        paradigm=paradigm_name,
        sections=sections,
        total_chars=total_chars,
        base_min_paras=config.min_section_paragraphs,
    )
    contract_titles: list[str] = []
    existing_section_keys = {
        runtime_api._canonicalize_section_name(runtime_api._section_title(sec) or sec)
        for sec in sections
    }
    for sec in (section_contracts or {}).keys():
        title_hint = str(runtime_api._section_title(sec) or sec).strip()
        canonical = runtime_api._canonicalize_section_name(title_hint)
        if canonical and canonical not in existing_section_keys:
            contract_titles.append(title_hint)
            existing_section_keys.add(canonical)
    if contract_titles:
        candidate_sections = runtime_api._sanitize_section_tokens(
            list(sections) + contract_titles,
            keep_full_titles=True,
        )
        if str(analysis.get("doc_type") or "").strip() == "academic":
            preferred_order = _academic_contract_preferred_order(runtime_api, paradigm_name)
            ordered_sections: list[str] = []
            used_canonicals: set[str] = set()
            for title_hint in preferred_order:
                canonical = runtime_api._canonicalize_section_name(title_hint)
                for sec in candidate_sections:
                    sec_canonical = runtime_api._canonicalize_section_name(runtime_api._section_title(sec) or sec)
                    if sec_canonical == canonical and sec_canonical not in used_canonicals:
                        ordered_sections.append(sec)
                        used_canonicals.add(sec_canonical)
                        break
            for sec in candidate_sections:
                sec_canonical = runtime_api._canonicalize_section_name(runtime_api._section_title(sec) or sec)
                if sec_canonical in used_canonicals:
                    continue
                ordered_sections.append(sec)
                used_canonicals.add(sec_canonical)
            sections = ordered_sections
        else:
            sections = candidate_sections

    section_specs = list(base.build_section_specs(sections))
    section_id_by_token = dict(base.token_to_id_map(section_specs))
    for spec in section_specs:
        title_key = str(spec.title or "").strip()
        if title_key and title_key not in section_id_by_token:
            section_id_by_token[title_key] = str(spec.id or "")
    yield {"event": "section_specs", "items": [spec.to_dict() for spec in section_specs]}

    guard_ok, guard_reasons, guard_meta = runtime_api._analysis_correctness_guard(
        analysis=analysis,
        instruction=instruction,
        sections=sections,
        section_title=runtime_api._section_title,
        is_reference_section=runtime_api._is_reference_section,
    )
    if not guard_ok:
        reason = guard_reasons[0] if guard_reasons else "analysis_guard_failed"
        yield build_final_event(
            text="",
            problems=list(guard_reasons),
            status="failed",
            failure_reason=reason,
            quality_snapshot={
                "status": "failed",
                "reason": reason,
                "guard_reasons": guard_reasons,
                "guard_meta": guard_meta,
            },
            runtime_status="failed",
            runtime_failure_reason=reason,
            quality_passed=False,
            quality_failure_reason=reason,
        )
        return None

    base_targets = runtime_api._compute_section_targets(
        sections=sections,
        base_min_paras=config.min_section_paragraphs,
        total_chars=total_chars,
    )
    skip_plan_detail, skip_plan_reason = runtime_api._plan_detail_skip_decision()
    if (not skip_plan_detail) and skip_plan_reason == "skip_plan_detail_ignored":
        yield {
            "event": "plan_detail_skip_ignored",
            "reason": skip_plan_reason,
            "sections": [(runtime_api._section_title(s) or s) for s in sections],
        }
    if base._env_flag("WRITING_AGENT_FAST_PLAN", "0") or skip_plan_detail:
        plan_map = runtime_api._default_plan_map(
            sections=sections,
            base_targets=base_targets,
            total_chars=total_chars,
        )
        if skip_plan_detail and (not base._env_flag("WRITING_AGENT_FAST_PLAN", "0")):
            yield {
                "event": "plan_detail_skipped",
                "reason": skip_plan_reason or "env_skip_plan_detail",
                "sections": [(runtime_api._section_title(s) or s) for s in sections],
            }
    else:
        plan_raw = runtime_api._plan_sections_with_model(
            base_url=settings.base_url,
            model=agg_model,
            title=title,
            instruction=analysis_summary or instruction,
            sections=sections,
            total_chars=total_chars,
            trace_hook=capture_prompt_trace,
        )
        yield from base._flush_trace(prompt_events)
        plan_map = runtime_api._normalize_plan_map(
            plan_raw=plan_raw,
            sections=sections,
            base_targets=base_targets,
            total_chars=total_chars,
        )
        plan_ok, plan_reasons, plan_meta = runtime_api._validate_plan_detail(
            instruction=instruction,
            sections=sections,
            plan_map=plan_map,
        )
        if not plan_ok:
            yield {
                "event": "plan_detail_retry",
                "reasons": list(plan_reasons),
                "meta": dict(plan_meta or {}),
                "attempt": 1,
            }
            plan_map = runtime_api._default_plan_map(
                sections=sections,
                base_targets=base_targets,
                total_chars=total_chars,
            )
            yield {
                "event": "plan_detail_validation_degraded",
                "reasons": list(plan_reasons),
                "meta": dict(plan_meta or {}),
            }

    if force_required_outline_only and sections:
        default_locked_plan = runtime_api._default_plan_map(
            sections=sections,
            base_targets=base_targets,
            total_chars=total_chars,
        )
        plan_map = {
            sec: (plan_map.get(sec) or default_locked_plan.get(sec))
            for sec in sections
            if (plan_map.get(sec) or default_locked_plan.get(sec)) is not None
        }
    plan_map = runtime_api._stabilize_plan_map_minimums(
        plan_map=plan_map,
        sections=sections,
        base_targets=base_targets,
        total_chars=total_chars,
    )

    targets: dict[str, object] = {}
    for sec in sections:
        base_target = base_targets.get(sec)
        plan = plan_map.get(sec)
        if not plan:
            continue
        contract = section_contracts.get(sec)
        min_paras = base_target.min_paras if base_target else config.min_section_paragraphs
        min_chars = int(plan.min_chars)
        max_chars = int(plan.max_chars)
        if contract:
            min_paras = max(1, int(contract.min_paras))
            min_chars = int(contract.min_chars) if int(contract.min_chars) > 0 else max(0, int(contract.min_chars))
            if int(contract.max_chars) > 0:
                max_chars = int(contract.max_chars)
        targets[sec] = runtime_api.SectionTargets(
            weight=base_target.weight if base_target else 1.0,
            min_paras=min_paras,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=plan.min_tables,
            min_figures=plan.min_figures,
        )
    if runtime_api._is_engineering_instruction(instruction):
        runtime_api._boost_media_targets(targets, sections)
        plan_map = base.evidence_domain._sync_plan_media(plan_map, targets)

    struct_plan = {"title": title, "total_chars": total_chars, "sections": []}
    for sec in sections:
        plan = plan_map.get(sec)
        if not plan:
            continue
        contract = section_contracts.get(sec)
        struct_plan["sections"].append(
            {
                "section_id": str(section_id_by_token.get(sec) or runtime_api._normalize_section_id(sec)),
                "section_token": sec,
                "title": runtime_api._section_title(sec) or sec,
                "target_chars": int(plan.target_chars or 0),
                "key_points": list(plan.key_points or [])[:6],
                "figures": list(plan.figures or [])[:2],
                "tables": list(plan.tables or [])[:2],
                "evidence_queries": list(plan.evidence_queries or [])[:4],
                "contract": contract.to_dict() if contract else {},
            }
        )
    if prompt_trace:
        struct_plan["prompt_trace"] = prompt_trace[-12:]
    yield {
        "event": "plan",
        "title": title,
        "sections": list(sections),
        "total_chars": total_chars,
        "paradigm": paradigm_name,
    }
    yield {"event": "struct_plan", "plan": struct_plan}
    yield {"event": "plan", "title": title, "sections": sections}
    yield {"event": "targets", "targets": {k: targets[k].__dict__ for k in sections if k in targets}}
    contract_type = getattr(base, "SectionContractSpec", None)
    yield {
        "event": "section_contracts",
        "contracts": {
            str(k): v.to_dict()
            for k, v in section_contracts.items()
            if (contract_type is None) or isinstance(v, contract_type)
        },
    }

    return {
        "sections": sections,
        "total_chars": total_chars,
        "section_contracts": section_contracts,
        "section_specs": section_specs,
        "section_id_by_token": section_id_by_token,
        "plan_map": plan_map,
        "targets": targets,
    }



__all__ = [name for name in globals() if not name.startswith("__")]
