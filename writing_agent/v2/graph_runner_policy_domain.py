"""Policy, paradigm, contract, and validation helpers for graph runner."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from writing_agent.v2.paradigm_lock import ParadigmLock
from writing_agent.v2.section_contract import SectionContract, SectionContractSpec
from writing_agent.v2.meta_firewall import MetaFirewall
from writing_agent.v2 import rag_gate
from writing_agent.v2 import final_validator


_DISALLOWED_SECTIONS = {"\u76ee\u5f55", "Table of Contents", "Contents"}
_ACK_SECTIONS = {"\u81f4\u8c22", "\u9e23\u8c22"}


def _strip_chapter_prefix_local(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(r"^\u7b2c\s*\d+\s*\u7ae0\s*", "", s)
    s = re.sub(r"^\d+(?:\.\d+)*\s*", "", s)
    return s


def _clean_section_title(title: str) -> str:
    s = _strip_chapter_prefix_local(str(title or "")).strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
    s = re.sub(r"\s*#+\s*$", "", s).strip()
    return s


_PARADIGM_LOCK = ParadigmLock()
_SECTION_CONTRACT = SectionContract()
_META_FIREWALL = MetaFirewall()

_PHASE_METRICS_PATH = Path(".data/metrics/phase_timing.json")
_PHASE_METRICS_LOCK = threading.Lock()


def _load_phase_metrics() -> dict:
    if not _PHASE_METRICS_PATH.exists():
        return {"runs": []}
    try:
        data = json.loads(_PHASE_METRICS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("runs"), list):
            return data
    except Exception:
        pass
    return {"runs": []}


def _save_phase_metrics(data: dict) -> None:
    _PHASE_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PHASE_METRICS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_phase_timing(run_id: str, payload: dict) -> None:
    with _PHASE_METRICS_LOCK:
        data = _load_phase_metrics()
        runs = data.get("runs") if isinstance(data.get("runs"), list) else []
        entry = {"run_id": run_id, "ts": time.time()}
        entry.update(payload or {})
        runs.append(entry)
        data["runs"] = runs[-200:]
        _save_phase_metrics(data)

def _filter_disallowed_sections(items: list[str]) -> list[str]:
    if not items:
        return []
    return [s for s in items if s not in _DISALLOWED_SECTIONS]

def _strip_disallowed_sections_text(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines()
    out: list[str] = []
    skip = False
    for line in lines:
        m = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
        if m:
            title = (m.group(2) or "").strip()
            title = _clean_section_title(title)
            if title in _DISALLOWED_SECTIONS:
                skip = True
                continue
            skip = False
        if skip:
            continue
        out.append(line)
    return "\n".join(out).strip()


def _strip_ack_sections_text(text: str, *, allow_ack: bool) -> str:
    if allow_ack or not text:
        return text
    lines = text.splitlines()
    out: list[str] = []
    skip = False
    skip_level = 0
    for line in lines:
        m = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
        if m:
            level = len(m.group(1))
            title = (m.group(2) or "").strip()
            title = _clean_section_title(title)
            if title in _ACK_SECTIONS:
                skip = True
                skip_level = level
                continue
            if skip and level <= skip_level:
                skip = False
        if skip:
            continue
        if line.strip() in _ACK_SECTIONS:
            continue
        out.append(line)
    return "\n".join(out).strip()


def _default_outline_from_instruction(text: str) -> list[str]:
    src = str(text or "")
    if re.search(r"(周报|weekly|this week|next week)", src, flags=re.IGNORECASE):
        return [
            "本周工作",
            "问题与风险",
            "下周计划",
            "需协助事项",
        ]
    if _is_bibliometric_instruction(src):
        return list(_bibliometric_section_spine())
    # Academic/technical intents should not inherit weekly defaults.
    return []


def _prompt_quality_profile() -> str:
    raw = os.environ.get("WRITING_AGENT_QUALITY_PROFILE", "").strip()
    return raw or "academic_cnki_default"


def _resolve_doc_type_for_prompt(instruction: str) -> str:
    text = str(instruction or "")
    if re.search(r"(周报|weekly|this week|next week)", text, flags=re.IGNORECASE):
        return "weekly"
    if re.search(r"(技术报告|report|架构|implementation|工程)", text, flags=re.IGNORECASE):
        return "technical_report"
    return "academic"


def _is_bibliometric_instruction(text: str) -> bool:
    src = str(text or "")
    if not src.strip():
        return False
    return bool(
        re.search(
            r"(citespace|bibliometric|文献计量|可视化分析|知识图谱|关键词共现|突现分析|聚类分析|研究热点分析|发文量)",
            src,
            flags=re.IGNORECASE,
        )
    )


def _bibliometric_section_spine() -> list[str]:
    return [
        "摘要",
        "关键词",
        "引言",
        "相关研究",
        "数据来源与检索策略",
        "发文量时空分布",
        "作者与机构合作网络",
        "关键词共现与聚类分析",
        "研究热点演化与突现分析",
        "讨论",
        "结论",
        "参考文献",
    ]


def _classify_paradigm(
    *,
    instruction: str,
    analysis: dict | None,
    user_override: str = "",
) -> dict[str, object]:
    decision = _PARADIGM_LOCK.classify(
        instruction=instruction,
        analysis=analysis if isinstance(analysis, dict) else {},
        user_override=user_override,
    )
    return decision.to_dict(low_confidence=_PARADIGM_LOCK.is_low_confidence(decision))


def _dual_outline_probe(
    *,
    instruction: str,
    analysis: dict | None,
    primary_paradigm: str,
    secondary_paradigm: str,
) -> dict[str, object]:
    primary = _PARADIGM_LOCK.outline_for(primary_paradigm, bibliometric_outline=_bibliometric_section_spine())
    secondary = _PARADIGM_LOCK.outline_for(secondary_paradigm, bibliometric_outline=_bibliometric_section_spine())
    return _PARADIGM_LOCK.dual_outline_probe(
        instruction=instruction,
        analysis=analysis if isinstance(analysis, dict) else {},
        primary_paradigm=primary_paradigm,
        secondary_paradigm=secondary_paradigm,
        primary_outline=primary,
        secondary_outline=secondary,
    )


def _enforce_paradigm_sections(
    *,
    sections: list[str],
    paradigm: str,
    instruction: str,
) -> list[str]:
    allow_engineering = _user_explicitly_requests_engineering_sections(instruction)
    return _PARADIGM_LOCK.enforce_sections(
        sections=sections,
        paradigm=paradigm,
        allow_engineering=allow_engineering,
        bibliometric_outline=_bibliometric_section_spine(),
    )


def _build_section_contracts(
    *,
    paradigm: str,
    sections: list[str],
    total_chars: int,
    base_min_paras: int,
) -> dict[str, SectionContractSpec]:
    return _SECTION_CONTRACT.build_contracts(
        paradigm=paradigm,
        sections=sections,
        total_chars=total_chars,
        base_min_paras=base_min_paras,
    )


def _rebalance_section_contracts(
    *,
    contracts: dict[str, SectionContractSpec],
    evidence_by_section: dict[str, dict],
) -> tuple[dict[str, SectionContractSpec], list[dict[str, object]]]:
    return _SECTION_CONTRACT.rebalance_contracts_by_evidence(
        contracts=contracts,
        evidence_by_section=evidence_by_section if isinstance(evidence_by_section, dict) else {},
    )


def _apply_contract_slot_filling(
    *,
    section_title: str,
    text: str,
    analysis: dict | None,
    contract: SectionContractSpec | None,
) -> str:
    return _SECTION_CONTRACT.fill_slots(
        section_title=section_title,
        text=text,
        analysis=analysis if isinstance(analysis, dict) else {},
        contract=contract,
    )


def _validate_contract_slots(
    *,
    section_title: str,
    text: str,
    contract: SectionContractSpec | None,
) -> list[str]:
    return _SECTION_CONTRACT.validate_slots(
        section_title=section_title,
        text=text,
        contract=contract,
    )


def _meta_firewall_scan(text: str) -> list[str]:
    result = _META_FIREWALL.scan(text)
    return list(result.fragments if result.has_meta else [])


def _meta_firewall_strip(text: str) -> str:
    return _META_FIREWALL.strip(text)


def _meta_firewall_rewrite_prompt(*, section_title: str, draft: str, hit_fragments: list[str]) -> tuple[str, str]:
    return _META_FIREWALL.build_rewrite_prompt(
        section_title=section_title,
        draft=draft,
        hit_fragments=hit_fragments,
    )


def _rag_theme_entity_gate(*, title: str, sources: list[dict], min_theme_score: float, mode: str = "strict") -> dict[str, object]:
    return rag_gate.filter_sources(
        title=title,
        sources=sources,
        min_theme_score=min_theme_score,
        mode=mode,
    )


def _validate_final_document(
    *,
    title: str,
    text: str,
    sections: list[str],
    problems: list[str],
    rag_gate_dropped: list[dict] | None = None,
    source_rows: list[dict] | None = None,
) -> dict[str, object]:
    return final_validator.validate_final_document(
        title=title,
        text=text,
        sections=sections,
        problems=problems,
        rag_gate_dropped=rag_gate_dropped,
        source_rows=source_rows,
    )


def _user_explicitly_requests_engineering_sections(text: str) -> bool:
    src = str(text or "")
    if not src.strip():
        return False
    return bool(
        re.search(
            r"(系统设计与实现|实验设计与结果|研究方法|方法设计|系统架构|工程实现|实验验证)",
            src,
            flags=re.IGNORECASE,
        )
    )


__all__ = [name for name in globals() if not name.startswith("__")]
