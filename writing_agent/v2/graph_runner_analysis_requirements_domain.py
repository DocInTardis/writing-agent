"""Analysis normalization and requirement helpers."""

from __future__ import annotations

import re

from writing_agent.v2.graph_reference_domain import _topic_tokens



def _analysis_domain_module():
    from writing_agent.v2 import graph_runner_analysis_domain as _analysis_domain

    return _analysis_domain



def _resolve_doc_type_for_prompt(instruction: str) -> str:
    return str(_analysis_domain_module()._resolve_doc_type_for_prompt(instruction))



def _meta_firewall_scan(text: str) -> bool:
    return bool(_analysis_domain_module()._meta_firewall_scan(text))



def _guess_title(instruction: str) -> str:
    return str(_analysis_domain_module()._guess_title(instruction))



def _sanitize_section_tokens(tokens: list[str], *, keep_full_titles: bool = False) -> list[str]:
    return list(_analysis_domain_module()._sanitize_section_tokens(tokens, keep_full_titles=keep_full_titles))



def _bibliometric_section_spine() -> list[str]:
    return list(_analysis_domain_module()._bibliometric_section_spine())



def _is_reference_section(section: str) -> bool:
    return bool(_analysis_domain_module()._is_reference_section(section))



def _is_bibliometric_instruction(instruction: str) -> bool:
    return bool(_analysis_domain_module()._is_bibliometric_instruction(instruction))



def _user_explicitly_requests_engineering_sections(instruction: str) -> bool:
    return bool(_analysis_domain_module()._user_explicitly_requests_engineering_sections(instruction))



def _normalize_reference_query(text: str) -> str:
    return str(_analysis_domain_module().graph_reference_domain.normalize_reference_query(text))



def _process_line(text: str) -> bool:
    return bool(_analysis_domain_module().graph_text_sanitize_domain._looks_like_process_line(text))

def _section_title(section) -> str:
    return str(_analysis_domain_module()._section_title(section))


from writing_agent.v2 import graph_runner_analysis_normalize_domain as normalize_domain


def _dedupe_keep_order(items: list[str]) -> list[str]:
    return list(normalize_domain._dedupe_keep_order(items))


def _extract_required_sections(text: str) -> list[str]:
    return list(normalize_domain._extract_required_sections(text))


def _canonicalize_section_name(text: str) -> str:
    return str(normalize_domain._canonicalize_section_name(text))


def _looks_like_heading_requirement(text: str) -> bool:
    return bool(normalize_domain._looks_like_heading_requirement(text))


def _normalize_must_include_sections(
    *,
    must_include_raw: list[str] | None,
    constraints_raw: list[str] | None,
    instruction: str,
    doc_type: str = "",
) -> list[str]:
    return list(
        normalize_domain._normalize_must_include_sections(
            must_include_raw=must_include_raw,
            constraints_raw=constraints_raw,
            instruction=instruction,
            doc_type=doc_type,
        )
    )


def _analysis_text_is_meta_noise(text: str) -> bool:
    return bool(normalize_domain._analysis_text_is_meta_noise(text))


def _sanitize_analysis_scalar(raw: object) -> str:
    return str(normalize_domain._sanitize_analysis_scalar(raw))


def _normalize_analysis_doc_type(raw: object, instruction: str) -> str:
    return str(normalize_domain._normalize_analysis_doc_type(raw, instruction))


def _normalize_analysis_topic(raw: object, instruction: str) -> str:
    return str(normalize_domain._normalize_analysis_topic(raw, instruction))


def _normalize_analysis_keywords(raw_keywords: object, *, topic: str, instruction: str) -> list[str]:
    return list(normalize_domain._normalize_analysis_keywords(raw_keywords, topic=topic, instruction=instruction))


def _normalize_analysis_for_generation(data: dict, instruction: str) -> dict:
    return dict(normalize_domain._normalize_analysis_for_generation(data, instruction))

def _merge_required_sections_from_analysis(*, sections: list[str], analysis: dict | None, instruction: str) -> list[str]:
    src_sections = [str(x).strip() for x in (sections or []) if str(x).strip()]
    obj = analysis if isinstance(analysis, dict) else {}
    must_include_raw = obj.get("must_include")
    must_include_items = [str(x).strip() for x in must_include_raw] if isinstance(must_include_raw, list) else []
    must_include_items = [x for x in must_include_items if x]
    constraints_raw = obj.get("constraints")
    constraints_items = [str(x).strip() for x in constraints_raw] if isinstance(constraints_raw, list) else []
    constraints_items = [x for x in constraints_items if x]
    doc_type = str(obj.get("doc_type") or "").strip()
    required = _normalize_must_include_sections(
        must_include_raw=must_include_items,
        constraints_raw=constraints_items,
        instruction=instruction,
        doc_type=doc_type,
    )
    paradigm = str(obj.get("_paradigm") or "").strip().lower()
    if paradigm == "bibliometric" and not _user_explicitly_requests_engineering_sections(instruction):
        return _sanitize_section_tokens(_bibliometric_section_spine(), keep_full_titles=True)
    if not required:
        return src_sections

    # For academic tasks, lock the section spine to required sections to avoid planner drift
    # into technical-report chapters (e.g. 用户手册/运维与监控) that break detail validation.
    if _resolve_doc_type_for_prompt(instruction) == "academic":
        is_biblio_mode = _is_bibliometric_instruction(instruction) and not _user_explicitly_requests_engineering_sections(
            instruction
        )
        if is_biblio_mode:
            canonical_order = _bibliometric_section_spine()[:-1]
        else:
            canonical_order = [
                "摘要",
                "关键词",
                "引言",
                "相关研究",
                "研究方法",
                "系统设计与实现",
                "实验设计与结果",
                "讨论",
                "结论",
            ]
        focused: list[str] = []
        required_set = {_canonicalize_section_name(x) for x in required}
        for sec_name in canonical_order:
            # For bibliometric mode, keep the paradigm spine even if model-side must_include drifts.
            if is_biblio_mode:
                focused.append(sec_name)
                continue
            if sec_name in required_set:
                focused.append(sec_name)
        if is_biblio_mode:
            focused.append("参考文献")
            return _sanitize_section_tokens(focused, keep_full_titles=True)
        # Keep additional non-reference sections from requirement extraction as supplements.
        for x in required:
            sec_name = _canonicalize_section_name(x)
            if not sec_name or sec_name in focused or _is_reference_section(sec_name):
                continue
            focused.append(sec_name)
        focused.append("参考文献")
        return _sanitize_section_tokens(focused, keep_full_titles=True)

    required_non_ref = [x for x in required if not _is_reference_section(x)]
    canonical_existing = [_canonicalize_section_name(_section_title(x) or x) for x in src_sections]
    used_idx: set[int] = set()
    ordered: list[str] = []

    # Keep required section order while reusing existing planned titles whenever possible.
    for req in required_non_ref:
        found_idx = -1
        for idx, canonical in enumerate(canonical_existing):
            if idx in used_idx:
                continue
            if canonical == req:
                found_idx = idx
                break
        if found_idx >= 0:
            used_idx.add(found_idx)
            ordered.append(src_sections[found_idx])
        else:
            ordered.append(req)

    # Preserve remaining planned sections as supplements.
    for idx, sec in enumerate(src_sections):
        if idx in used_idx:
            continue
        if _is_reference_section(_section_title(sec) or sec):
            continue
        ordered.append(sec)

    ordered.append("参考文献")
    return _sanitize_section_tokens(ordered, keep_full_titles=True)


__all__ = [name for name in globals() if not name.startswith("__")]
