"""Graph Runner Post Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from writing_agent.llm import OllamaClient, get_ollama_settings
from writing_agent.sections_catalog import find_section_description
from writing_agent.v2 import (
    draft_model_domain,
    graph_aggregate_domain,
    graph_plan_domain,
    graph_reference_domain,
    graph_section_draft_domain,
    graph_text_sanitize_domain,
)
from writing_agent.v2.doc_format import DocBlock, parse_report_text
from writing_agent.v2.prompts import PromptBuilder, get_prompt_config
from writing_agent.v2.text_store import TextStore


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


_DISALLOWED_SECTIONS = {"??", "???", "??", "Abstract", "Keywords"}
_ACK_SECTIONS = {"??", "??"}
_META_PHRASES = [
    "\u4e0b\u9762\u662f",
    "\u4ee5\u4e0b\u662f",
    "\u6839\u636e\u4f60\u7684\u8981\u6c42",
    "\u6839\u636e\u60a8\u7684\u8981\u6c42",
    "\u751f\u6210\u7ed3\u679c\u5982\u4e0b",
    "\u8f93\u51fa\u5982\u4e0b",
]
_SECTION_TOKEN_RE = re.compile(r"^H([23])::(.*)$")


def _strip_chapter_prefix_local(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^\u7b2c\s*\d+\s*\u7ae0\s*", "", s)
    s = re.sub(r"^\d+(?:\.\d+)*\s*", "", s)
    return s.strip()

def _clean_section_title(title: str) -> str:
    return graph_plan_domain.clean_section_title(
        title,
        strip_chapter_prefix_local=_strip_chapter_prefix_local,
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


def _extract_h2_titles(text: str) -> list[str]:
    out: list[str] = []
    for line in (text or "").splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            title = _clean_section_title(m.group(1))
            if title:
                out.append(title)
    return out

def _count_citations(text: str) -> int:
    return len(re.findall(r"\[\d+\]", text or ""))

def _light_self_check(*, text: str, sections: list[str], target_chars: int, evidence_enabled: bool, reference_sources: list[dict]) -> list[str]:
    problems: list[str] = []
    body_len = _doc_body_len(text)
    if target_chars > 0:
        lower = int(target_chars * 0.9)
        upper = int(target_chars * 1.1)
        if body_len < lower or body_len > upper:
            problems.append(f"\u5b57\u6570\u4e0e\u76ee\u6807\u504f\u5dee\u8f83\u5927\uff08\u5b9e\u9645{body_len}\uff0c\u76ee\u6807\u7ea6{target_chars}\uff09\u3002")
    if sections:
        expected = [_clean_section_title(_section_title(s) or s) for s in sections]
        got = set(_extract_h2_titles(text))
        missing = [s for s in expected if s and s not in got]
        if missing:
            problems.append("\u7f3a\u5c11\u7ae0\u8282\uff1a" + "\u3001".join(missing[:6]))
    if evidence_enabled:
        if not reference_sources:
            problems.append("\u5f53\u524d\u65e0\u53ef\u7528\u8bc1\u636e\u6765\u6e90\uff0c\u5982\u9700\u4e25\u683c\u5f15\u7528\u8bf7\u4e0a\u4f20\u6216\u5f00\u542f\u68c0\u7d22\u3002")
        else:
            cites = _count_citations(text)
            if cites == 0:
                problems.append("\u5df2\u5f00\u542f\u8bc1\u636e\u9650\u5236\uff0c\u8bf7\u8865\u5145\u5f15\u7528\uff08\u5f62\u5982[1]\uff09\u3002")
    return problems

def _plan_title(current_text: str, instruction: str) -> str:
    text = (current_text or "").strip()
    m = None
    for line in text.splitlines():
        if line.startswith("# "):
            m = line[2:].strip()
            break
    raw = m or _guess_title(instruction) or _fallback_title_from_instruction(instruction) or _default_title()
    return _normalize_title_line(raw)

def _normalize_title_line(title: str) -> str:
    s = (title or "").replace("\r", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
    return s.strip()

def _default_title() -> str:
    stamp = time.strftime("%Y%m%d-%H%M")
    return f"\u81ea\u52a8\u751f\u6210\u6587\u6863-{stamp}"

def _fallback_title_from_instruction(instruction: str) -> str:
    s = (instruction or "").strip().replace("\r", " ").replace("\n", " ")
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    s = re.split(r"[銆?!?锛侊紵]", s)[0].strip()
    s = re.sub(
        r"^(?:\u751f\u6210|\u5199\u4e00\u4efd?|\u5199|\u5236\u4f5c|\u5e2e\u6211|\u8bf7|\u9700\u8981)\s*",
        "",
        s,
    ).strip()
    if not s:
        return ""
    if len(s) > 20:
        s = s[:20].rstrip()
    return s

def _plan_title_sections(*, current_text: str, instruction: str, required_h2: list[str] | None) -> tuple[str, list[str]]:
    title = _plan_title(current_text=current_text, instruction=instruction)

    if required_h2:
        secs = _sanitize_planned_sections([s.strip() for s in required_h2 if s and s.strip()])
        if secs:
            return title, secs
    return title, []

def _guess_title(instruction: str) -> str:
    s = (instruction or "").strip().replace("\r", "").replace("\n", " ")
    if not s:
        return ""

    quoted = re.search(r"[\"'“”‘’]([^\"'“”‘’]{2,80})[\"'“”‘’]", s)
    if quoted:
        return quoted.group(1).strip()[:40]

    report_like = re.search(r"([A-Za-z0-9\u4e00-\u9fff]{2,40})\s*(report|paper|proposal|方案|报告|论文)", s, flags=re.IGNORECASE)
    if report_like:
        return report_like.group(1).strip()[:40]

    first = s
    for sep in ["。", "！", "？", ".", "!", "?", ";", "；"]:
        if sep in first:
            first = first.split(sep, 1)[0]
            break
    first = re.sub(r"\s+", " ", first).strip()
    return first[:40]

def _wants_acknowledgement(instruction: str) -> bool:
    s = (instruction or "").replace(" ", "")
    if not s:
        return False
    return ("鑷磋阿" in s) or ("鎰熻阿" in s) or ("鑷磋緸" in s)

def _filter_ack_headings(headings: list[str], *, allow_ack: bool) -> list[str]:
    if allow_ack:
        return headings
    return [h for h in headings if "鑷磋阿" not in h and "鑷磋緸" not in h]

def _filter_ack_outline(outline: list[tuple[int, str]], *, allow_ack: bool) -> list[tuple[int, str]]:
    if allow_ack:
        return outline
    return [(lvl, txt) for lvl, txt in outline if ("鑷磋阿" not in txt and "鑷磋緸" not in txt)]

def _filter_disallowed_outline(outline: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return [(lvl, txt) for lvl, txt in outline if txt not in _DISALLOWED_SECTIONS]

def _is_engineering_instruction(instruction: str) -> bool:
    s = (instruction or "").replace(" ", "")
    if not s:
        return False
    keywords = ["系统", "平台", "工程", "设计", "实现", "架构", "开发", "数据库", "模块", "项目"]
    return any(k in s for k in keywords)

def _boost_media_targets(targets: dict[str, SectionTargets], sections: list[str]) -> None:
    for sec in sections:
        t = targets.get(sec)
        if not t:
            continue
        title = (_section_title(sec) or sec).strip()
        if _is_reference_section(title) or "闄勫綍" in title:
            continue
        min_tables = t.min_tables
        min_figures = t.min_figures
        if any(k in title for k in ["需求", "设计", "实现", "架构", "测试", "结果", "分析", "requirement", "design"]):
            min_figures = max(min_figures, 1)
            min_tables = max(min_tables, 1)
        else:
            min_figures = max(min_figures, 1)
        targets[sec] = SectionTargets(
            weight=t.weight,
            min_paras=t.min_paras,
            min_chars=t.min_chars,
            max_chars=t.max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
        )

def _generate_section_stream(
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
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
    reference_items: list[dict],
    text_store: TextStore | None,
) -> str:
    from writing_agent.v2.graph_runner_runtime import _generate_section_stream as _impl

    return _impl(
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
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
        out_queue=out_queue,
        reference_items=reference_items,
        text_store=text_store,
    )

def _maybe_rag_context(*, instruction: str, section: str) -> str:
    enabled_raw = os.environ.get("WRITING_AGENT_RAG_ENABLED", "1").strip().lower()
    if enabled_raw not in {"1", "true", "yes", "on"}:
        return ""

    q = (instruction or "").strip()
    if section:
        q = (q + " " + section).strip()
    top_k = int(os.environ.get("WRITING_AGENT_RAG_TOP_K", "4"))
    max_chars = int(os.environ.get("WRITING_AGENT_RAG_MAX_CHARS", "2500"))
    per_paper = int(os.environ.get("WRITING_AGENT_RAG_PER_PAPER", "2"))

    ctx, _ = _mcp_rag_retrieve(query=q, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    if ctx.strip():
        return ctx

    try:
        from writing_agent.v2.rag.retrieve import retrieve_context
    except Exception:
        return ""

    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    rag_dir = data_dir / "rag"

    res = retrieve_context(rag_dir=rag_dir, query=q, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    return res.context

def _mcp_rag_enabled() -> bool:
    raw = os.environ.get("WRITING_AGENT_RAG_MCP", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}

def _mcp_rag_retrieve(*, query: str, top_k: int, per_paper: int, max_chars: int) -> tuple[str, list[dict]]:
    if not _mcp_rag_enabled():
        return "", []
    q = (query or "").strip()
    if not q:
        return "", []
    try:
        from writing_agent.mcp_client import fetch_mcp_json
    except Exception:
        return "", []
    uri = (
        "mcp://rag/retrieve?query="
        + quote(q)
        + f"&top_k={int(top_k)}&per_paper={int(per_paper)}&max_chars={int(max_chars)}"
    )
    data = fetch_mcp_json(uri)
    if not isinstance(data, dict):
        return "", []
    context = str(data.get("context") or "")
    sources = data.get("sources")
    if not isinstance(sources, list):
        sources = []
    return context, sources

def _looks_like_rag_meta_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return True
    low = s.lower()
    if "http://" in low or "https://" in low:
        return True
    if "openalex" in low or "arxiv" in low or "doi" in low:
        return True
    if re.match(r"^\[[^\]]+\]", s):
        return True
    return False

def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))

def _is_mostly_ascii_line(text: str) -> bool:
    s = text or ""
    letters = sum(1 for ch in s if ch.isascii() and ch.isalpha())
    if letters < 12:
        return False
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    if cjk == 0:
        return True
    return letters > cjk * 2

def _strip_rag_meta_lines(text: str) -> str:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _looks_like_rag_meta_line(line):
            continue
        if _is_mostly_ascii_line(line) and not _has_cjk(line):
            continue
        lines.append(line)
    return " ".join(lines).strip()

def _plan_point_paragraph(section: str, plan: PlanSection | None, idx: int) -> str:
    if not plan or not plan.key_points:
        return ""
    sec = (_section_title(section) or section).strip() or "鏈妭"
    points = [p for p in plan.key_points if p]
    if not points:
        return ""
    point = points[(idx - 1) % len(points)]
    return f"{sec} should elaborate around {point}, describing approach, constraints, and verifiable outcomes."

def _expand_with_context(
    section: str,
    text: str,
    ctx: str,
    min_chars: int,
    min_paras: int,
    plan: PlanSection | None = None,
) -> str:
    base = (text or '').strip()
    if not ctx or min_chars <= 0:
        return base
    chunks = [p.strip() for p in re.split(r'\n\s*\n+', ctx) if p.strip()]
    added = 0
    for p in chunks:
        cleaned = _strip_rag_meta_lines(p)
        if len(cleaned) < 20:
            continue
        if cleaned in base:
            continue
        if re.match(r'^#{1,3}\s+', cleaned):
            continue
        base = (base + '\n\n' + cleaned) if base else cleaned
        added += 1
        if _section_body_len(base) >= min_chars and added >= max(0, min_paras - 1):
            break
    max_add = max(min_paras, min(50, max(12, int(min_chars / 40) or 12)))
    while _section_body_len(base) < min_chars and added < max_add:
        plan_para = _plan_point_paragraph(section, plan, added + 1)
        extra = plan_para or _generic_fill_paragraph(section, idx=added + 1)
        if not extra:
            break
        base = (base + '\n\n' + extra) if base else extra
        added += 1
    return base

def _select_models_by_memory(models: list[str], *, fallback: str) -> list[str]:
    return graph_reference_domain.select_models_by_memory(
        models,
        fallback=fallback,
        looks_like_embedding_model=_looks_like_embedding_model,
        ollama_installed_models=_ollama_installed_models,
        get_memory_bytes=_get_memory_bytes,
        ollama_model_sizes_gb=_ollama_model_sizes_gb,
    )

def _default_worker_models(*, preferred: str) -> list[str]:
    installed = _ollama_installed_models()
    if not installed:
        return [preferred]
    out: list[str] = []
    if preferred in installed and not _looks_like_embedding_model(preferred):
        out.append(preferred)
    # Add other non-embedding models as fallback candidates.
    for m in sorted(installed):
        if m == preferred:
            continue
        if _looks_like_embedding_model(m):
            continue
        out.append(m)
    return out or [preferred]

def _looks_like_embedding_model(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in ["embed", "embedding", "bge-", "e5-", "nomic-embed"])

def _ollama_installed_models() -> set[str]:
    try:
        p = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=8)
        if p.returncode != 0:
            return set()
        lines = (p.stdout or "").splitlines()
        out: set[str] = set()
        for line in lines[1:]:
            parts = line.split()
            if parts:
                out.add(parts[0].strip())
        return out
    except Exception:
        return set()

def _ollama_model_sizes_gb() -> dict[str, float]:
    # Parse `ollama list` SIZE column; best-effort.
    try:
        p = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=8)
        if p.returncode != 0:
            return {}
        out: dict[str, float] = {}
        for line in (p.stdout or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) < 3:
                continue
            name = parts[0].strip()
            # SIZE is usually the 3rd column, e.g. "4.1" "GB"
            try:
                num = float(parts[2])
                unit = parts[3].upper() if len(parts) > 3 else "GB"
                if unit.startswith("MB"):
                    gb = num / 1024.0
                elif unit.startswith("KB"):
                    gb = num / (1024.0 * 1024.0)
                else:
                    gb = num
                out[name] = max(0.1, gb)
            except Exception:
                continue
        return out
    except Exception:
        return {}

def _get_memory_bytes() -> tuple[int, int]:
    # Windows GlobalMemoryStatusEx; fallback returns (0,0)
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):  # type: ignore[attr-defined]
            return int(st.ullTotalPhys), int(st.ullAvailPhys)
    except Exception:
        pass
    return 0, 0

def _sanitize_output_text(text: str) -> str:
    banned = [
        "如果您有任何",
        "如有任何",
        "您有任何",
        "需要进一步的信息",
        "需要进一步信息",
        "随时回来询问",
        "欢迎随时",
        "祝您",
        "期待着未来",
        "期待未来",
        "继续交流",
        "非常感谢",
        "感谢您",
        "不客气",
        "很高兴能为您提供帮助",
    ]
    return graph_text_sanitize_domain.sanitize_output_text(
        text,
        meta_phrases=_META_PHRASES,
        has_cjk=_has_cjk,
        is_mostly_ascii_line=_is_mostly_ascii_line,
        banned_phrases=banned,
    )

def _strip_markdown_noise(text: str) -> str:
    return graph_text_sanitize_domain.strip_markdown_noise(text)

def _should_merge_tail(prev_line: str, line: str) -> bool:
    return graph_text_sanitize_domain.should_merge_tail(prev_line, line)

def _clean_generated_text(text: str) -> str:
    return graph_text_sanitize_domain.clean_generated_text(text, should_merge_tail_fn=_should_merge_tail)

def _normalize_final_output(text: str, *, expected_sections: list[str] | None = None) -> str:
    from writing_agent.v2.graph_runner_runtime import _normalize_final_output as _impl

    return _impl(text, expected_sections=expected_sections)

def _is_reference_section(title: str) -> bool:
    t = (title or "").strip().lower()
    if not t:
        return False
    return ("参考文献" in t) or ("参考资料" in t) or (t == "文献") or ("references" in t)

def _looks_like_heading_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if re.search(r"[\u3002\uFF01\uFF1F\uFF1B\uFF1A]", t):
        return False
    if re.match(r"^\u7b2c\s*\d+\s*\u7ae0", t):
        return True
    keywords = [
        "\u7eea\u8bba",
        "\u5f15\u8a00",
        "\u7efc\u8ff0",
        "\u80cc\u666f",
        "\u610f\u4e49",
        "\u65b9\u6cd5",
        "\u8bbe\u8ba1",
        "\u7cfb\u7edf",
        "\u5b9e\u73b0",
        "\u67b6\u6784",
        "\u6a21\u5757",
        "\u6d4b\u8bd5",
        "\u8bc4\u4f30",
        "\u5206\u6790",
        "\u7ed3\u679c",
        "\u7ed3\u8bba",
        "\u603b\u7ed3",
        "\u5c55\u671b",
        "\u9700\u6c42",
        "\u53c2\u8003\u6587\u732e",
        "\u9644\u5f55",
        "\u81f4\u8c22",
    ]
    return any(k in t for k in keywords)

def _strip_inline_headings(text: str, section_title: str) -> str:
    return graph_section_draft_domain.strip_inline_headings(
        text,
        section_title,
        looks_like_heading_text=_looks_like_heading_text,
    )

def _format_references(text: str) -> str:
    return graph_section_draft_domain.format_references(
        text,
        strip_markdown_noise=_strip_markdown_noise,
    )

def _ensure_media_markers(
    text: str,
    *,
    section_title: str,
    min_tables: int,
    min_figures: int,
) -> str:
    return graph_section_draft_domain.ensure_media_markers(
        text,
        section_title=section_title,
        min_tables=min_tables,
        min_figures=min_figures,
        is_reference_section=_is_reference_section,
    )

def _generic_fill_paragraph(section: str, *, idx: int = 1) -> str:
    return graph_section_draft_domain.generic_fill_paragraph(
        section,
        idx=idx,
        section_title=_section_title,
        is_reference_section=_is_reference_section,
        find_section_description=find_section_description,
    )

def _fast_fill_references(topic: str) -> str:
    return graph_section_draft_domain.fast_fill_references(topic)

def _fast_fill_section(
    section: str,
    *,
    min_paras: int,
    min_chars: int,
    min_tables: int,
    min_figures: int,
) -> str:
    return graph_section_draft_domain.fast_fill_section(
        section,
        min_paras=min_paras,
        min_chars=min_chars,
        min_tables=min_tables,
        min_figures=min_figures,
        section_title=_section_title,
        is_reference_section=_is_reference_section,
        generic_fill_paragraph=lambda sec, i: _generic_fill_paragraph(sec, idx=i),
    )

def _postprocess_section(
    section: str,
    txt: str,
    *,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
) -> str:
    return graph_section_draft_domain.postprocess_section(
        section,
        txt,
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
        section_title=_section_title,
        is_reference_section=_is_reference_section,
        format_references=_format_references,
        strip_reference_like_lines=_strip_reference_like_lines,
        strip_inline_headings=_strip_inline_headings,
        generic_fill_paragraph=lambda sec, i: _generic_fill_paragraph(sec, idx=i),
        sanitize_output_text=_sanitize_output_text,
        ensure_media_markers=lambda content, sec_title, tables, figures: _ensure_media_markers(
            content,
            section_title=sec_title,
            min_tables=tables,
            min_figures=figures,
        ),
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
    draft: str,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
) -> str:
    from writing_agent.v2.graph_runner_runtime import _ensure_section_minimums_stream as _impl

    return _impl(
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
        draft=draft,
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
        out_queue=out_queue,
    )

def _strip_reference_like_lines(text: str) -> str:
    return graph_section_draft_domain.strip_reference_like_lines(text)

def _normalize_section_id(section: str) -> str:
    return graph_section_draft_domain.normalize_section_id(
        section,
        section_token_re=_SECTION_TOKEN_RE,
        encode_section=_encode_section,
    )

def _stream_structured_blocks(
    *,
    client: OllamaClient,
    system: str,
    user: str,
    out_queue: queue.Queue[dict],
    section: str,
    section_id: str,
    is_reference: bool,
    num_predict: int,
    deadline: float,
    strict_json: bool = True,
    text_store: TextStore | None = None,
) -> str:
    return graph_section_draft_domain.stream_structured_blocks(
        client=client,
        system=system,
        user=user,
        out_queue=out_queue,
        section=section,
        section_id=section_id,
        is_reference=is_reference,
        num_predict=num_predict,
        deadline=deadline,
        strict_json=strict_json,
        text_store=text_store,
    )

def _trim_total_chars(text: str, max_chars: int) -> str:
    if max_chars <= 0 or not text:
        return text
    if _count_text_chars(text) <= max_chars:
        return text
    parsed = parse_report_text(text)
    used = 0
    out_blocks: list[DocBlock] = []
    for b in parsed.blocks:
        if b.type == "heading":
            out_blocks.append(b)
            continue
        if b.type == "paragraph":
            t = b.text or ""
            p_len = _count_text_chars(t)
            if used + p_len <= max_chars:
                out_blocks.append(b)
                used += p_len
                continue
            remaining = max_chars - used
            if remaining <= 0:
                break
            trimmed = _truncate_to_chars(t, remaining)
            if trimmed:
                out_blocks.append(DocBlock(type="paragraph", text=trimmed))
                used += _count_text_chars(trimmed)
            break
        else:
            out_blocks.append(b)
    while out_blocks and out_blocks[-1].type == "heading":
        out_blocks.pop()
    if not out_blocks:
        return text
    return _blocks_to_doc_text(out_blocks)

def _encode_section(level: int, title: str) -> str:
    lvl = 2 if int(level or 2) <= 2 else 3
    return f"H{lvl}::{(title or '').strip()}"

def _split_section_token(section: str) -> tuple[int, str]:
    m = _SECTION_TOKEN_RE.match((section or "").strip())
    if m:
        return int(m.group(1)), (m.group(2) or "").strip()
    return 2, (section or "").strip()

def _section_title(section: str) -> str:
    return _split_section_token(section)[1]

def _sections_from_outline(outline: list[tuple[int, str]], *, expand: bool) -> tuple[list[str], list[str]]:
    items = [(int(lvl), str(txt).strip()) for lvl, txt in (outline or []) if str(txt).strip()]
    if not items:
        return [], []
    has_h1 = any(lvl == 1 for lvl, _ in items)
    sections: list[str] = []
    chapters: list[str] = []
    seen: set[tuple[int, str]] = set()
    for lvl, txt in items:
        if lvl == 1:
            chapters.append(txt)
            key = (2, txt)
            if key not in seen:
                sections.append(_encode_section(2, txt))
                seen.add(key)
        elif lvl == 2:
            if has_h1:
                if expand:
                    key = (3, txt)
                    if key not in seen:
                        sections.append(_encode_section(3, txt))
                        seen.add(key)
                else:
                    continue
            else:
                chapters.append(txt)
                key = (2, txt)
                if key not in seen:
                    sections.append(_encode_section(2, txt))
                    seen.add(key)
    return sections, chapters

def _map_section_parents(sections: list[str]) -> dict[str, str]:
    parent_map: dict[str, str] = {}
    current_parent = ""
    for sec in sections:
        level, title = _split_section_token(sec)
        if not title:
            continue
        if level <= 2:
            current_parent = title
            continue
        if level >= 3 and current_parent:
            parent_map[sec] = current_parent
    return parent_map

def _merge_sections_text(title: str, sections: list[str], section_text: dict[str, str]) -> str:
    if not sections:
        sections = [
            "Introduction",
            "Requirement Analysis",
            "Overall Design",
            "Data Design",
            "Testing and Results",
            "Conclusion",
            "References",
        ]
    out = [f"# {title}"]
    for sec in sections:
        level, heading = _split_section_token(sec)
        prefix = "##" if level <= 2 else "###"
        out.append(f"{prefix} {heading}")
        content = (section_text.get(sec) or "").strip()
        out.append(content or _generic_fill_paragraph(sec, idx=1))
    return "\n\n".join(out).strip() + "\n"

def _apply_section_updates(base_text: str, updates, transitions) -> str:
    # compatibility: generation_service passes (current_text, final_text, [section])
    if isinstance(updates, str) and isinstance(transitions, list):
        return str(updates or "").strip() or base_text
    if not isinstance(updates, dict) or not isinstance(transitions, dict):
        return base_text
    return graph_aggregate_domain.apply_section_updates(base_text, updates, transitions)
