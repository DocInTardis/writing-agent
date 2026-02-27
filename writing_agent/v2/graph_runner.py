"""Graph Runner module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, wait
import ctypes
import subprocess
from pathlib import Path
from urllib.parse import quote

from writing_agent.v2.prompts import PromptBuilder, get_prompt_config

from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings
from writing_agent.sections_catalog import find_section_description, section_catalog_text
from writing_agent.v2.doc_format import DocBlock, ParsedDoc, parse_report_text
from writing_agent.v2.cache import LocalCache, AcademicPhraseCache  # 鏂板缂撳瓨
from writing_agent.v2 import (
    draft_model_domain,
    graph_aggregate_domain,
    graph_plan_domain,
    graph_reference_domain,
    graph_section_draft_domain,
    graph_text_sanitize_domain,
)
from writing_agent.v2.text_store import TextStore


@dataclass(frozen=True)
class GenerateConfig:
    workers: int = 8  # 4鈫? 骞跺彂鎻愬崌
    worker_models: list[str] | None = None
    aggregator_model: str | None = None
    min_section_paragraphs: int = 4
    min_total_chars: int = 1800
    max_total_chars: int = 0


def _target_total_chars(config: GenerateConfig) -> int:
    if config.max_total_chars and config.max_total_chars > 0:
        return max(config.min_total_chars or 0, config.max_total_chars)
    if config.min_total_chars and config.min_total_chars > 0:
        return config.min_total_chars
    return 1800


def _load_section_weights() -> dict[str, float]:
    return {}


def _guess_section_weight(section: str) -> float:
    s = (section or "").strip()
    if not s:
        return 1.0
    if _is_reference_section(s):
        return 0.4
    if any(k in s for k in ["寮曡█", "鑳屾櫙", "姒傝堪"]):
        return 0.8
    if any(k in s for k in ["鏂规硶", "瀹炵幇", "璁捐", "鏋舵瀯", "鏂规"]):
        return 1.2
    if any(k in s for k in ["缁撹", "鎬荤粨", "灞曟湜"]):
        return 0.8
    return 1.0


def _max_chars_for_section(section: str) -> int:
    return 0


def _compute_section_targets(*, sections: list[str], base_min_paras: int, total_chars: int) -> dict[str, SectionTargets]:
    from writing_agent.v2.graph_runner_runtime import _compute_section_targets as _impl

    return _impl(sections=sections, base_min_paras=base_min_paras, total_chars=total_chars)


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
    return [s.strip() for s in (raw or "").split(",") if s and s.strip()]


def _require_json_response(
    *,
    client: OllamaClient,
    system: str,
    user: str,
    stage: str,
    temperature: float,
    max_retries: int = 2,
) -> dict:
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            raw = client.chat(system=system, user=user, temperature=temperature)
            raw_json = _extract_json_block(raw)
            if not raw_json:
                raise ValueError(f"{stage}: empty json block")
            data = json.loads(raw_json)
            if not isinstance(data, dict):
                raise ValueError(f"{stage}: json is not object")
            return data
        except Exception as exc:
            last_err = exc
            system = (
                system
                + "\n\nYour previous output was not valid JSON. Return exactly one JSON object with no markdown."
            )
            user = "Return only a JSON object."
            time.sleep(0.4 * attempt)
            continue
    raise ValueError(f"{stage}: json parse failed: {last_err}")


def _plan_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_PLAN_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(5.0, float(raw))
        except Exception:
            pass
    return 40.0  # 20s鈫?0s 缈诲€?


def _analysis_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_ANALYSIS_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(3.0, float(raw))
        except Exception:
            pass
    return 24.0  # 12s鈫?4s 缈诲€?


def _section_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_SECTION_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(10.0, float(raw))
        except Exception:
            pass
    return 120.0  # 60s鈫?20s 缈诲€嶏紝缁欐ā鍨嬫洿鍏呰冻鐨勬椂闂?


def _is_evidence_enabled() -> bool:
    # Evidence/RAG is expensive and can stall on offline setups.
    # Default to disabled unless explicitly turned on.
    raw = os.environ.get("WRITING_AGENT_EVIDENCE_ENABLED", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _truncate_text(text: str, *, max_chars: int = 1200) -> str:
    s = (text or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max(0, max_chars - 3)].rstrip() + "..."

_DISALLOWED_SECTIONS = {"\u6458\u8981", "\u5173\u952e\u8bcd", "\u76ee\u5f55", "Abstract", "Keywords"}
_ACK_SECTIONS = {"\u81f4\u8c22", "\u9e23\u8c22"}

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
    s = (text or "").lower()
    if "weekly" in s or "week report" in s or "周报" in str(text or ""):
        return ["This Week Work", "Issues and Risks", "Next Week Plan", "Support Needed"]
    return []


def _pick_draft_models(worker_models: list[str], *, agg_model: str, fallback: str) -> tuple[str, str]:
    return draft_model_domain.pick_draft_models(
        worker_models=worker_models,
        agg_model=agg_model,
        fallback=fallback,
        env_main=os.environ.get("WRITING_AGENT_DRAFT_MAIN_MODEL", "").strip(),
        env_support=os.environ.get("WRITING_AGENT_DRAFT_SUPPORT_MODEL", "").strip(),
        installed=_ollama_installed_models(),
        sizes=_ollama_model_sizes_gb(),
        is_embedding_model=_looks_like_embedding_model,
    )




def _extract_json_block(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    s = s.replace("```json", "").replace("```", "").strip()
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return s[start : end + 1]


def _compute_section_weights(sections: list[str]) -> dict[str, float]:
    weights = _load_section_weights()
    out: dict[str, float] = {}
    for s in sections:
        title = _section_title(s) or s
        w = weights.get(title)
        if w is None:
            w = _guess_section_weight(title)
        out[s] = float(max(0.3, min(3.0, w)))
    return out


def _classify_section_type(title: str) -> str:
    """Classify section type for target length scaling."""
    t = (title or "").strip().lower()
    if any(k in t for k in ["introduction", "background", "overview", "综述", "引言"]):
        return "intro"
    if any(k in t for k in ["method", "design", "implementation", "architecture", "analysis", "方法", "设计", "实现", "架构"]):
        return "method"
    if any(k in t for k in ["conclusion", "summary", "结论", "总结", "展望"]):
        return "conclusion"
    return "default"


def _default_plan_map(
    *,
    sections: list[str],
    base_targets: dict[str, SectionTargets],
    total_chars: int,
) -> dict[str, PlanSection]:
    return graph_reference_domain.default_plan_map(
        sections=sections,
        base_targets=base_targets,
        total_chars=total_chars,
        compute_section_weights=_compute_section_weights,
        section_title=_section_title,
        is_reference_section=_is_reference_section,
        classify_section_type=_classify_section_type,
        plan_section_cls=PlanSection,
    )


def _plan_sections_with_model(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    sections: list[str],
    total_chars: int,
) -> dict:
    if not sections:
        return {}
    client = OllamaClient(base_url=base_url, model=model, timeout_s=_plan_timeout_s())
    config = get_prompt_config("planner")
    system, user = PromptBuilder.build_planner_prompt(
        title=title,
        total_chars=total_chars,
        sections=sections,
        instruction=instruction
    )
    return _require_json_response(
        client=client,
        system=system,
        user=user,
        stage="plan",
        temperature=config.temperature,
        max_retries=max(2, int(os.environ.get("WRITING_AGENT_JSON_RETRIES", "2"))),
    )


def _sanitize_planned_sections(sections: list[str]) -> list[str]:
    banned = {"\u6458\u8981", "\u5173\u952e\u8bcd", "\u76ee\u5f55", "Abstract", "Keywords", "\u5efa\u8bae", "\u9644\u5f55"}
    out: list[str] = []
    seen: set[str] = set()
    for s in sections or []:
        title = _clean_section_title(str(s or ""))
        if not title:
            continue
        if title in banned:
            continue
        if title in _ACK_SECTIONS:
            continue
        if title in _DISALLOWED_SECTIONS:
            continue
        if title in seen:
            continue
        seen.add(title)
        out.append(title)
    # ensure references last
    refs = [t for t in out if _is_reference_section(t)]
    out = [t for t in out if not _is_reference_section(t)]
    if refs:
        out.append("\u53c2\u8003\u6587\u732e")
    else:
        out.append("\u53c2\u8003\u6587\u732e")
    return out


def _clean_section_title(title: str) -> str:
    return graph_plan_domain.clean_section_title(
        title,
        strip_chapter_prefix_local=_strip_chapter_prefix_local,
    )




def _clean_outline_title(title: str) -> str:
    s = _strip_chapter_prefix_local(str(title or "")).strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
    s = re.sub(r"\s*#+\s*$", "", s).strip()
    return s

def _strip_chapter_prefix_local(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^\u7b2c\s*\d+\s*\u7ae0\s*", "", s)
    s = re.sub(r"^\d+(?:\.\d+)*\s*", "", s)
    return s.strip()


def _sanitize_section_tokens(sections: list[str], *, keep_full_titles: bool = False) -> list[str]:
    banned = {"\u6458\u8981", "\u5173\u952e\u8bcd", "\u76ee\u5f55", "Abstract", "Keywords", "\u5efa\u8bae", "\u9644\u5f55"}
    out: list[str] = []
    refs: list[str] = []
    seen: set[tuple[int, str]] = set()
    for sec in sections or []:
        lvl, title = _split_section_token(sec)
        clean = _clean_outline_title(title) if keep_full_titles else _clean_section_title(title)
        if not clean:
            continue
        if clean in banned or clean in _ACK_SECTIONS or clean in _DISALLOWED_SECTIONS:
            continue
        key = (lvl if lvl >= 3 else 2, clean)
        if key in seen:
            continue
        seen.add(key)
        token = _encode_section(lvl, clean) if lvl >= 3 else clean
        if _is_reference_section(clean):
            refs.append(token)
        else:
            out.append(token)
    if refs:
        out.append("\u53c2\u8003\u6587\u732e")
    else:
        out.append("\u53c2\u8003\u6587\u732e")
    return out


def _sanitize_outline(outline: list[tuple[int, str]]) -> list[tuple[int, str]]:
    if not outline:
        return []
    out: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    refs = False
    numbered_re = re.compile(r"^\s*(?:\u7b2c\s*\d+\s*\u7ae0|\d+[\s.])")
    has_numbered = any(numbered_re.match(str(txt or "")) for _, txt in outline)
    for lvl, txt in outline:
        try:
            lvl_i = int(lvl)
        except Exception:
            lvl_i = 1
        lvl_i = 1 if lvl_i <= 1 else (2 if lvl_i == 2 else 3)
        clean = _clean_outline_title(txt)
        if not clean:
            continue
        if has_numbered and not numbered_re.match(str(txt or "")):
            lvl_i = 2
        if clean in _DISALLOWED_SECTIONS or clean in _ACK_SECTIONS:
            continue
        key = (lvl_i, clean)
        if key in seen:
            continue
        seen.add(key)
        if _is_reference_section(clean):
            refs = True
            continue
        out.append((lvl_i, clean))
    if refs:
        out.append((1, "\u53c2\u8003\u6587\u732e"))
    return out


def _plan_sections_list_with_model(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
) -> list[str]:
    client = OllamaClient(base_url=base_url, model=model, timeout_s=_plan_timeout_s())
    catalog = section_catalog_text()
    system = """????????????Agent????JSON???Markdown?
Schema: {sections:[string]}.
??????????????????????16??????????????????????????/???/??/??/????????????????????????????????4-12???
???????{"sections":["??","????","????","???????","??","????"]}
"""
    user = (
        f"\u62a5\u544a\u6807\u9898\uff1a{title}\n"
        f"\u7528\u6237\u9700\u6c42\uff1a\n{instruction}\n\n"
        f"\u53ef\u9009\u7ae0\u8282\u5e93\uff08\u6309\u9700\u6311\u9009\uff0c\u4e0d\u5fc5\u5168\u90e8\u4f7f\u7528\uff09\uff1a\n{catalog}\n\n"
        "\u8bf7\u7ed9\u51fa\u7ae0\u8282\u5217\u8868JSON\u3002"
    )
    data = _require_json_response(
        client=client,
        system=system,
        user=user,
        stage="plan_sections",
        temperature=0.2,
        max_retries=max(2, int(os.environ.get("WRITING_AGENT_JSON_RETRIES", "2"))),
    )
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, list):
        raise ValueError("plan_sections: sections must be list")
    cleaned = _sanitize_planned_sections([str(x) for x in sections])
    return cleaned or ["\u5f15\u8a00", "\u7ed3\u8bba", "\u53c2\u8003\u6587\u732e"]


def _predict_num_tokens(*, min_chars: int, max_chars: int, is_reference: bool) -> int:
    # 浼樺寲: 榛樿鍚敤杞檺鍒舵ā寮忥紝璁╂ā鍨嬭嚜鐒剁粨鏉?
    # 璁剧疆鐜鍙橀噺 WRITING_AGENT_HARD_MAX=1 鍙垏鍥炵‖闄愬埗妯″紡
    hard_max_mode = os.environ.get("WRITING_AGENT_HARD_MAX", "0").strip() in {"1", "true", "yes"}
    
    base = max(1200, int(round(min_chars * 4.0)))
    
    if max_chars > 0 and hard_max_mode:
        # 纭檺鍒舵ā寮忥細涓ユ牸闄愬埗鏈€澶у瓧鏁?
        base = min(base, int(round(max_chars * 3.0)))
    # 杞檺鍒舵ā寮忥紙榛樿锛夛細蹇界暐max_chars锛岃妯″瀷鑷敱鍙戞尌
    
    if is_reference:
        base = min(base, 2400)
    
    return max(800, min(8192, base))


def _normalize_plan_map(
    *,
    plan_raw: dict,
    sections: list[str],
    base_targets: dict[str, SectionTargets],
    total_chars: int,
) -> dict[str, PlanSection]:
    return graph_plan_domain.normalize_plan_map(
        plan_raw=plan_raw,
        sections=sections,
        base_targets=base_targets,
        total_chars=total_chars,
        default_plan_map=lambda s, b, t: _default_plan_map(sections=s, base_targets=b, total_chars=t),
        section_title=_section_title,
        classify_section_type=_classify_section_type,
        is_reference_section=_is_reference_section,
        plan_section_cls=PlanSection,
    )


def _analyze_instruction(
    *,
    base_url: str,
    model: str,
    instruction: str,
    current_text: str,
) -> dict:
    fast_raw = os.environ.get("WRITING_AGENT_ANALYSIS_FAST", "").strip().lower()
    force_fast = fast_raw in {"force", "always"}
    if force_fast or fast_raw in {"1", "true", "yes", "on"}:
        if force_fast or (len((instruction or "").strip()) <= 120 and not (current_text or "").strip()):
            return {"topic": (instruction or "").strip(), "doc_type": "report"}
    client = OllamaClient(base_url=base_url, model=model, timeout_s=_analysis_timeout_s())
    config = get_prompt_config("analysis")
    excerpt = _truncate_text(current_text or "", max_chars=800)
    system, user = PromptBuilder.build_analysis_prompt(
        instruction=instruction,
        excerpt=excerpt
    )
    return _require_json_response(
        client=client,
        system=system,
        user=user,
        stage="analysis",
        temperature=config.temperature,
        max_retries=max(2, int(os.environ.get("WRITING_AGENT_JSON_RETRIES", "2"))),
    )


def _format_analysis_summary(analysis: dict, *, fallback: str) -> str:
    if not isinstance(analysis, dict) or not analysis:
        return (fallback or "").strip()

    lines: list[str] = []

    def _add(label: str, value: object) -> None:
        val = str(value or "").strip()
        if val:
            lines.append(f"{label}: {val}")

    def _add_list(label: str, values: list[str], limit: int = 10) -> None:
        items = [str(x).strip() for x in values if str(x).strip()]
        if items:
            lines.append(f"{label}: " + "、".join(items[:limit]))

    _add("topic", analysis.get("topic"))
    _add("doc_type", analysis.get("doc_type"))
    _add("audience", analysis.get("audience"))
    _add("style", analysis.get("style"))
    _add_list("keywords", list(analysis.get("keywords") or []))
    _add_list("must_include", list(analysis.get("must_include") or []))
    _add_list("avoid_sections", list(analysis.get("avoid_sections") or []))
    _add_list("constraints", list(analysis.get("constraints") or []))
    _add_list("questions", list(analysis.get("questions") or []), limit=6)

    return "\n".join(lines).strip() or (fallback or "").strip()


def _build_evidence_queries(*, section_title: str, plan: PlanSection | None, analysis: dict | None) -> list[str]:
    items: list[str] = []
    if section_title:
        items.append(section_title)
    if plan:
        items.extend([str(x).strip() for x in (plan.evidence_queries or []) if str(x).strip()])
        items.extend([str(x).strip() for x in (plan.key_points or []) if str(x).strip()])
    if isinstance(analysis, dict):
        items.extend([str(x).strip() for x in (analysis.get("keywords") or []) if str(x).strip()])
        topic = str(analysis.get("topic") or "").strip()
        if topic:
            items.append(topic)
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        if not it or it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


def _extract_sources_from_context(context: str) -> list[dict]:
    blocks = [b for b in (context or "").split("\n\n") if b.strip()]
    out: list[dict] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        head = lines[0]
        url = ""
        if len(lines) > 1 and lines[1].startswith("http"):
            url = lines[1]
        m = re.match(r"^\[(.+?)\]\s+(.+?)(?:\s+\((.+)\))?$", head)
        if m:
            paper_id = m.group(1).strip()
            title = m.group(2).strip()
            kind = (m.group(3) or "").strip()
            out.append({"id": paper_id, "title": title, "kind": kind, "url": url})
        else:
            out.append({"id": "", "title": head.strip(), "kind": "", "url": url})
    return out


def _extract_year(text: str) -> str:
    return graph_reference_domain.extract_year(text)


def _format_authors(authors: list[str]) -> str:
    return graph_reference_domain.format_authors(authors)


def _enrich_sources_with_rag(sources: list[dict]) -> list[dict]:
    return graph_reference_domain.enrich_sources_with_rag(sources)


def _collect_reference_sources(evidence_map: dict[str, dict]) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()
    for data in (evidence_map or {}).values():
        items = data.get("sources") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        for s in items:
            if not isinstance(s, dict):
                continue
            url = str(s.get("url") or "").strip()
            title = str(s.get("title") or "").strip()
            key = url or title or str(s.get("id") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "url": url,
                    "title": title,
                    "id": str(s.get("id") or "").strip(),
                    "kind": str(s.get("kind") or "").strip(),
                    "authors": s.get("authors") or [],
                    "published": s.get("published") or "",
                    "updated": s.get("updated") or "",
                    "source": s.get("source") or "",
                }
            )
    return _enrich_sources_with_rag(sources)


def _format_reference_items(sources: list[dict]) -> list[str]:
    return graph_reference_domain.format_reference_items(
        sources,
        extract_year_fn=_extract_year,
        format_authors_fn=_format_authors,
    )


def _fallback_reference_sources(*, instruction: str) -> list[dict]:
    return graph_reference_domain.fallback_reference_sources(
        instruction=instruction,
        mcp_rag_retrieve=lambda query, top_k, per_paper, max_chars: _mcp_rag_retrieve(
            query=query,
            top_k=top_k,
            per_paper=per_paper,
            max_chars=max_chars,
        ),
        extract_sources_from_context=_extract_sources_from_context,
        enrich_sources_with_rag_fn=_enrich_sources_with_rag,
        extract_year_fn=_extract_year,
    )


def _summarize_evidence(
    *,
    base_url: str,
    model: str,
    section: str,
    analysis_summary: str,
    context: str,
    sources: list[dict],
) -> dict:
    return graph_reference_domain.summarize_evidence(
        base_url=base_url,
        model=model,
        section=section,
        analysis_summary=analysis_summary,
        context=context,
        sources=sources,
        require_json_response=_require_json_response,
        ollama_client_cls=OllamaClient,
    )


def _format_evidence_summary(facts: list[dict], sources: list[dict]) -> tuple[str, list[str]]:
    return graph_reference_domain.format_evidence_summary(facts, sources)


def _build_evidence_pack(
    *,
    instruction: str,
    section: str,
    analysis: dict | None,
    plan: PlanSection | None,
    base_url: str,
    model: str,
) -> dict:
    enabled_raw = os.environ.get("WRITING_AGENT_EVIDENCE_ENABLED", "1").strip().lower()
    if enabled_raw not in {"1", "true", "yes", "on"}:
        return {"summary": "", "sources": [], "allowed_urls": []}
    try:
        from writing_agent.v2.rag.retrieve import retrieve_context
    except Exception:
        return {"summary": "", "sources": [], "allowed_urls": []}
    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    rag_dir = data_dir / "rag"
    queries = _build_evidence_queries(section_title=_section_title(section) or section, plan=plan, analysis=analysis)
    q = " ".join([instruction] + queries).strip()
    top_k = int(os.environ.get("WRITING_AGENT_RAG_TOP_K", "6"))
    max_chars = int(os.environ.get("WRITING_AGENT_RAG_MAX_CHARS", "2800"))
    per_paper = int(os.environ.get("WRITING_AGENT_RAG_PER_PAPER", "2"))
    res = retrieve_context(rag_dir=rag_dir, query=q, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    context = res.context or ""
    sources = _extract_sources_from_context(context)
    summary_data = _summarize_evidence(
        base_url=base_url,
        model=model,
        section=section,
        analysis_summary=_format_analysis_summary(analysis or {}, fallback=instruction),
        context=context,
        sources=sources,
    )
    summary_text, allowed_urls = _format_evidence_summary(summary_data.get("facts") or [], sources)
    return {"summary": summary_text, "sources": sources, "allowed_urls": allowed_urls}


def _format_plan_hint(plan: PlanSection | None) -> str:
    if not plan:
        return ""
    lines: list[str] = []
    desc = find_section_description(plan.title or "")
    if desc:
        lines.append(f"section role: {desc}")
    lines.append(f"target chars: {plan.target_chars} (allow +/-30%)")
    if plan.key_points:
        lines.append("key points: " + "、".join(plan.key_points))
    if plan.evidence_queries:
        lines.append("suggested evidence queries: " + "、".join(plan.evidence_queries[:6]))
    if plan.figures:
        fig_items = []
        for f in plan.figures:
            f_type = str(f.get("type") or "").strip()
            cap = str(f.get("caption") or "").strip()
            if f_type or cap:
                fig_items.append(f"{f_type or 'figure'}:{cap}" if cap else f_type)
        if fig_items:
            lines.append("suggested figures: " + "、".join(fig_items))
    if plan.tables:
        tab_items = []
        for t in plan.tables:
            cap = str(t.get("caption") or "").strip()
            if cap:
                tab_items.append(cap)
        if tab_items:
            lines.append("suggested tables: " + "、".join(tab_items))
    return "\n".join(lines)


def _sync_plan_media(plan_map: dict[str, PlanSection], targets: dict[str, SectionTargets]) -> dict[str, PlanSection]:
    out: dict[str, PlanSection] = {}
    for sec, plan in plan_map.items():
        t = targets.get(sec)
        if not t:
            out[sec] = plan
            continue
        min_tables = max(plan.min_tables, int(t.min_tables))
        min_figures = max(plan.min_figures, int(t.min_figures))
        if min_tables == plan.min_tables and min_figures == plan.min_figures:
            out[sec] = plan
            continue
        out[sec] = PlanSection(
            title=plan.title,
            target_chars=plan.target_chars,
            min_chars=plan.min_chars,
            max_chars=plan.max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
            key_points=plan.key_points,
            figures=plan.figures,
            tables=plan.tables,
            evidence_queries=plan.evidence_queries,
        )
    return out


def _section_body_len(text: str) -> int:
    if not text:
        return 0
    body = re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", text, flags=re.IGNORECASE)
    return len(body.strip())


def _doc_body_len(text: str) -> int:
    if not text:
        return 0
    body = re.sub(r"(?m)^#{1,6}\s+.+$", "", text or "")
    return _section_body_len(body)


def _count_text_chars(text: str) -> int:
    if not text:
        return 0
    return len(str(text).strip())


def _truncate_to_chars(text: str, max_chars: int) -> str:
    if not text or max_chars <= 0:
        return ""
    s = str(text).strip()
    if len(s) <= max_chars:
        return s
    clipped = s[:max_chars]
    # Prefer cutting at a sentence boundary if possible.
    for sep in ["。", "！", "？", ".", "!", "?", ";"]:
        idx = clipped.rfind(sep)
        if idx >= max(0, int(max_chars * 0.5)):
            return clipped[: idx + 1].strip()
    return clipped.strip()


def _blocks_to_doc_text(blocks: list[DocBlock]) -> str:
    if not blocks:
        return ""
    out: list[str] = []
    for b in blocks:
        if b.type == "heading":
            level = b.level or 1
            out.append(f"{'#' * level} {(b.text or '').strip()}")
        elif b.type == "paragraph":
            out.append((b.text or "").strip())
        elif b.type == "table":
            out.append("[[TABLE:{}]]".format(json.dumps(b.table or {}, ensure_ascii=False)))
        elif b.type == "figure":
            out.append("[[FIGURE:{}]]".format(json.dumps(b.figure or {}, ensure_ascii=False)))
    return "\n\n".join([s for s in out if s])


def _validate_plan_results(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    sections: list[str],
    plan_map: dict[str, PlanSection],
    section_text: dict[str, str],
) -> list[dict]:
    _ = (base_url, model, title, instruction)
    if not sections:
        return []

    issues: list[dict] = []
    for sec in sections:
        plan = plan_map.get(sec)
        if not plan:
            continue
        chars = _section_body_len(section_text.get(sec) or "")
        if chars < int(plan.min_chars):
            issues.append({"title": plan.title or sec, "issue": "short", "action": "expand"})
        elif int(plan.max_chars) > 0 and chars > int(plan.max_chars):
            issues.append({"title": plan.title or sec, "issue": "long", "action": "trim"})
    return issues


def _load_support_section_keywords() -> list[str]:
    raw = os.environ.get("WRITING_AGENT_SUPPORT_SECTIONS", "").strip()
    if raw:
        return _split_csv_env(raw)
    return ["引言", "背景", "相关", "综述", "文献", "参考", "绪论", "概述"]


def _is_support_section(section: str, keywords: list[str]) -> bool:
    s = (_section_title(section) or "").strip()
    if not s:
        return False
    for k in keywords:
        if k and k in s:
            return True
    return False


def run_generate_graph(
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str],
    required_outline: list[tuple[int, str]] | list[str] | None,
    expand_outline: bool = False,
    config: GenerateConfig = GenerateConfig(),
):
    from writing_agent.v2.graph_runner_runtime import run_generate_graph as _run_generate_graph_impl

    return _run_generate_graph_impl(
        instruction=instruction,
        current_text=current_text,
        required_h2=required_h2,
        required_outline=required_outline,
        expand_outline=expand_outline,
        config=config,
    )


def run_generate_graph_dual_engine(
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str],
    required_outline: list[tuple[int, str]] | list[str] | None,
    expand_outline: bool = False,
    config: GenerateConfig = GenerateConfig(),
    compose_mode: str = "auto",
    resume_sections: list[str] | None = None,
    format_only: bool = False,
):
    """
    Dual-engine orchestration entry.
    Native graph remains default. LangGraph can be enabled via WRITING_AGENT_GRAPH_ENGINE=langgraph|dual|auto.
    """
    from writing_agent.state_engine import DualGraphEngine, should_use_langgraph

    def _planner(payload: dict) -> dict:
        return {
            "required_h2": list(required_h2 or []),
            "required_outline": list(required_outline or []),
            "plan": {"compose_mode": compose_mode, "resume_sections": list(resume_sections or [])},
        }

    def _writer(payload: dict) -> dict:
        generator = run_generate_graph(
            instruction=instruction,
            current_text=current_text,
            required_h2=list(payload.get("required_h2") or required_h2 or []),
            required_outline=list(payload.get("required_outline") or required_outline or []),
            expand_outline=expand_outline,
            config=config,
        )
        final_text = ""
        problems: list[str] = []
        for event in generator:
            if isinstance(event, dict) and event.get("event") == "final":
                final_text = str(event.get("text") or "")
                problems = list(event.get("problems") or [])
                break
        return {"draft": final_text, "problems": problems}

    def _reviewer(payload: dict) -> dict:
        draft = str(payload.get("draft") or "")
        issues = _light_self_check(
            text=draft,
            sections=list(required_h2 or []),
            target_chars=_target_total_chars(config),
            evidence_enabled=_is_evidence_enabled(),
            reference_sources=[],
        )
        return {"review": {"issues": issues}, "fixups": []}

    def _qa(payload: dict) -> dict:
        return {
            "final_text": str(payload.get("draft") or ""),
            "problems": list((payload.get("review") or {}).get("issues") or payload.get("problems") or []),
        }

    engine = DualGraphEngine(use_langgraph=should_use_langgraph())
    run_id = f"graph_{int(time.time() * 1000)}"
    state, _events = engine.run(
        run_id=run_id,
        payload={
            "instruction": instruction,
            "current_text": current_text,
            "compose_mode": compose_mode,
            "resume_sections": list(resume_sections or []),
            "format_only": bool(format_only),
        },
        handlers={
            "planner": _planner,
            "writer": _writer,
            "reviewer": _reviewer,
            "qa": _qa,
        },
    )
    return {
        "ok": 1,
        "text": str(state.get("final_text") or ""),
        "problems": list(state.get("problems") or []),
        "trace_id": str(state.get("trace_id") or ""),
        "engine": "langgraph" if should_use_langgraph() else "native",
    }

from writing_agent.v2 import graph_runner_post_domain as post_domain

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
