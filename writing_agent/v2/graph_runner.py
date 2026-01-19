from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import ctypes
import subprocess
from pathlib import Path

from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings
from writing_agent.v2.doc_format import parse_report_text, validate_doc


@dataclass(frozen=True)
class GenerateConfig:
    workers: int = 4
    worker_models: list[str] | None = None
    aggregator_model: str | None = None
    min_section_paragraphs: int = 4
    min_total_chars: int = 1800


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
    min_tables: int
    min_figures: int


def run_generate_graph(
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str] | None,
    config: GenerateConfig,
):
    """
    Yields dict events suitable for SSE:
      - {"event":"state","name":...,"phase":"start"|"end"}
      - {"event":"plan","title":...,"sections":[...]}
      - {"event":"section","phase":"start"|"delta"|"end","section":...,"delta":...}
      - {"event":"final","text":...,"problems":[...]}
    """
    settings = get_ollama_settings()
    if not settings.enabled:
        raise OllamaError("未启用Ollama（WRITING_AGENT_USE_OLLAMA=0）")
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise OllamaError("Ollama 未运行")

    agg_model = config.aggregator_model or os.environ.get("WRITING_AGENT_AGG_MODEL", "").strip() or "qwen:7b"
    installed = _ollama_installed_models()
    if installed and agg_model not in installed:
        agg_model = settings.model

    worker_models = (config.worker_models or [])[:]
    if not worker_models:
        models_raw = os.environ.get("WRITING_AGENT_WORKER_MODELS", "").strip()
        if models_raw:
            worker_models = [m.strip() for m in models_raw.split(",") if m.strip()]
        else:
            worker_models = _default_worker_models(preferred=settings.model)

    # Prefer using smaller models for drafting; avoid using the aggregator model for drafts if possible.
    worker_models = _select_models_by_memory(worker_models, fallback=settings.model)
    if len(worker_models) > 1:
        worker_models = [m for m in worker_models if m != agg_model] or worker_models

    # Keep 1 draft model resident by default to avoid swapping/loading thrash.
    draft_max = int(os.environ.get("WRITING_AGENT_DRAFT_MAX_MODELS", "1"))
    draft_max = max(1, min(4, draft_max))
    worker_models = worker_models[:draft_max] or [settings.model]

    pool = ModelPool(worker_models or [settings.model])

    yield {"event": "state", "name": "PLAN", "phase": "start"}
    title, sections = _plan_title_sections(current_text=current_text, instruction=instruction, required_h2=required_h2)
    targets = _compute_section_targets(sections=sections, base_min_paras=config.min_section_paragraphs, total_chars=_target_total_chars(config))
    yield {"event": "plan", "title": title, "sections": sections}
    yield {"event": "targets", "targets": {k: targets[k].__dict__ for k in sections if k in targets}}
    yield {"event": "delta", "delta": f"草稿模型：{', '.join(worker_models)}；合并模型：{agg_model}"}
    yield {"event": "state", "name": "PLAN", "phase": "end"}

    yield {"event": "state", "name": "DRAFT_SECTIONS", "phase": "start"}
    q: queue.Queue[dict] = queue.Queue()
    section_text: dict[str, str] = {s: "" for s in sections}

    def worker(section: str, model: str) -> None:
        q.put({"event": "section", "phase": "start", "section": section})
        attempts = max(1, int(os.environ.get("WRITING_AGENT_SECTION_RETRIES", "2")))
        last_err: Exception | None = None
        sec_t = targets.get(section) or SectionTargets(weight=1.0, min_paras=config.min_section_paragraphs, min_chars=800, min_tables=0, min_figures=0)
        for attempt in range(1, attempts + 1):
            try:
                if attempt > 1:
                    q.put({"event": "section", "phase": "delta", "section": section, "delta": f"\n\n[重试 {attempt}/{attempts}] …"})
                    time.sleep(0.8 * attempt)
                txt = _generate_section_stream(
                    base_url=settings.base_url,
                    model=model,
                    title=title,
                    section=section,
                    instruction=instruction,
                    min_paras=sec_t.min_paras,
                    min_chars=sec_t.min_chars,
                    min_tables=sec_t.min_tables,
                    min_figures=sec_t.min_figures,
                    out_queue=q,
                )
                txt2 = _ensure_section_minimums_stream(
                    base_url=settings.base_url,
                    model=model,
                    title=title,
                    section=section,
                    instruction=instruction,
                    draft=txt,
                    min_paras=sec_t.min_paras,
                    min_chars=sec_t.min_chars,
                    min_tables=sec_t.min_tables,
                    min_figures=sec_t.min_figures,
                    out_queue=q,
                )
                section_text[section] = txt2
                q.put({"event": "section", "phase": "end", "section": section})
                return
            except Exception as e:
                last_err = e
                continue
        fallback = f"[待补充]（章节生成失败：{last_err}）"
        section_text[section] = fallback
        q.put({"event": "section", "phase": "delta", "section": section, "delta": fallback})
        q.put({"event": "section", "phase": "end", "section": section})

    unique_models = sorted({m for m in worker_models if m})
    per_model = max(1, int(os.environ.get("WRITING_AGENT_PER_MODEL_CONCURRENCY", "1")))
    cap = max(1, per_model * max(1, len(unique_models)))
    requested = max(1, int(config.workers))
    max_workers = max(1, min(8, min(requested, cap)))

    # Default behavior: rotate models sequentially to keep Ollama stable on limited RAM.
    parallel_raw = os.environ.get("WRITING_AGENT_DRAFT_PARALLEL", "0").strip().lower()
    parallel = parallel_raw in {"1", "true", "yes", "on"}
    if not parallel or len(unique_models) <= 1:
        max_workers = 1

    # Keep one draft model "sticky" across all sections to reduce reload thrash.
    draft_model = (worker_models[0] if worker_models else settings.model) or settings.model

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = []
        for sec in sections:
            futs.append(ex.submit(worker, sec, draft_model))

        while True:
            try:
                ev = q.get(timeout=0.2)
                yield ev
                continue
            except queue.Empty:
                pass
            done_count = sum(1 for f in futs if f.done())
            if done_count == len(futs) and q.empty():
                break

    yield {"event": "state", "name": "DRAFT_SECTIONS", "phase": "end"}

    yield {"event": "state", "name": "AGGREGATE", "phase": "start"}
    merged_draft = _merge_sections_text(title, sections, section_text)
    merged = _aggregate_fix_stream(
        base_url=settings.base_url,
        model=agg_model,
        title=title,
        instruction=instruction,
        draft=merged_draft,
        required_h2=required_h2,
        targets=targets,
    )
    if _doc_body_len(merged) < int(_doc_body_len(merged_draft) * 0.75):
        yield {"event": "delta", "delta": "合并稿明显偏短，已回退为章节草稿并进入校验/修复流程。"}
        merged = merged_draft
    yield {"event": "state", "name": "AGGREGATE", "phase": "end"}

    yield {"event": "state", "name": "VALIDATE", "phase": "start"}
    parsed = parse_report_text(merged)
    problems = validate_doc(
        parsed,
        required_h2=required_h2,
        min_paragraphs_per_section={k: v.min_paras for k, v in targets.items()},
        min_chars_per_section={k: v.min_chars for k, v in targets.items()},
        min_tables_per_section={k: v.min_tables for k, v in targets.items()},
        min_figures_per_section={k: v.min_figures for k, v in targets.items()},
        min_total_chars=config.min_total_chars,
    )
    yield {"event": "state", "name": "VALIDATE", "phase": "end"}

    if problems:
        yield {"event": "state", "name": "REPAIR", "phase": "start"}
        merged2 = _repair_stream(
            base_url=settings.base_url,
            model=agg_model,
            title=title,
            instruction=instruction,
            draft=merged,
            problems=problems,
            required_h2=required_h2,
            targets=targets,
        )
        yield {"event": "state", "name": "REPAIR", "phase": "end"}
        parsed2 = parse_report_text(merged2)
        problems2 = validate_doc(
            parsed2,
            required_h2=required_h2,
            min_paragraphs_per_section={k: v.min_paras for k, v in targets.items()},
            min_chars_per_section={k: v.min_chars for k, v in targets.items()},
            min_tables_per_section={k: v.min_tables for k, v in targets.items()},
            min_figures_per_section={k: v.min_figures for k, v in targets.items()},
            min_total_chars=config.min_total_chars,
        )
        yield {"event": "final", "text": merged2, "problems": problems2}
        return

    yield {"event": "final", "text": merged, "problems": problems}


def _plan_title_sections(*, current_text: str, instruction: str, required_h2: list[str] | None) -> tuple[str, list[str]]:
    text = (current_text or "").strip()
    m = None
    for line in text.splitlines():
        if line.startswith("# "):
            m = line[2:].strip()
            break
    title = m or _guess_title(instruction) or "未命名报告"

    if required_h2:
        secs = [s.strip() for s in required_h2 if s and s.strip()]
        if secs:
            return title, secs
    # default
    return title, ["摘要", "引言", "方法", "结果", "结论", "参考文献"]


def _guess_title(instruction: str) -> str:
    s = (instruction or "").strip().replace("\r", "").replace("\n", " ")
    if not s:
        return ""
    # take first sentence-ish fragment
    for sep in ["。", ".", "！", "!", "？", "?"]:
        if sep in s:
            s = s.split(sep, 1)[0]
            break
    s = s.strip()
    return s[:40]


def _generate_section_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    section: str,
    instruction: str,
    min_paras: int,
    min_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
) -> str:
    # When Ollama queues requests, the first token can take a while; keep timeout generous.
    client = OllamaClient(base_url=base_url, model=model, timeout_s=300.0)

    table_hint = ""
    fig_hint = ""
    if min_tables > 0 or section in {"结果"}:
        table_hint = "本章节必须包含至少 1 个表格标记 [[TABLE:{...}]]，用于呈现关键指标/对比/实验结果。"
    if min_figures > 0:
        fig_hint = "本章节必须包含至少 1 个图标记 [[FIGURE:{...}]]（按内容选择 bar/line/pie/timeline/sequence/flow/er）。"
    elif section in {"结果"}:
        fig_hint = "本章节必须包含至少 1 个图标记 [[FIGURE:{...}]]（优先 bar/line/pie）。"
    elif section in {"方法"}:
        fig_hint = "本章节尽量包含 1 个图标记 [[FIGURE:{...}]]（优先 flow/sequence）。"
    elif section in {"引言"}:
        fig_hint = "如涉及发展脉络/阶段，可加入 [[FIGURE:{...}]]（timeline）。"

    system = (
        "你是一个严谨的报告写作Agent，只负责输出“一个章节”的正文内容。\n"
        "输出规则（必须遵守）：\n"
        "1) 只输出纯文本，不要HTML，不要Markdown，不要列表符号渲染（允许自然语言编号）。\n"
        f"2) 至少输出 {max(2, int(min_paras))} 段，段与段之间用空行分隔；每段要具体、可执行、包含定义/步骤/约束/边界条件。\n"
        f"3) 目标长度约 {max(220, int(min_chars))} 字符（可略超，但不要明显不足）。\n"
        "4) 不要编造真实数据/引用；未知信息用 [待补充]。\n"
        "5) 需要结构化呈现时可插入标记（单行、JSON必须合法）：\n"
        "   - 表格：[[TABLE:{\"caption\":\"...\",\"columns\":[\"...\"],\"rows\":[[\"...\"],[\"...\"]]}]]\n"
        "   - 图：[[FIGURE:{\"type\":\"bar|line|pie|timeline|sequence|flow|er\",\"caption\":\"...\",\"data\":{...}}]]\n"
        f"6) {table_hint} {fig_hint}\n"
    )

    rag_context = _maybe_rag_context(instruction=instruction, section=section)
    if rag_context:
        system = system + "6) 可参考给定的论文/摘要材料，但不要捏造具体数值或真实引用。\n"

    user = (
        f"文档标题：{title}\n"
        f"你负责章节：{section}\n\n"
        f"用户整体要求：\n{instruction}\n\n"
    )
    if rag_context:
        user += f"可用参考材料（摘要/元数据，仅供辅助）：\n{rag_context}\n\n"
    user += "请直接输出该章节正文内容。"

    buf: list[str] = []
    for delta in client.chat_stream(system=system, user=user, temperature=0.35):
        buf.append(delta)
        out_queue.put({"event": "section", "phase": "delta", "section": section, "delta": delta})
    txt = "".join(buf)
    return _postprocess_section(section, txt, min_paras=min_paras, min_chars=min_chars, min_tables=min_tables, min_figures=min_figures)


def _maybe_rag_context(*, instruction: str, section: str) -> str:
    enabled_raw = os.environ.get("WRITING_AGENT_RAG_ENABLED", "0").strip().lower()
    if enabled_raw not in {"1", "true", "yes", "on"}:
        return ""

    try:
        from writing_agent.v2.rag.retrieve import retrieve_context
    except Exception:
        return ""

    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    rag_dir = data_dir / "rag"

    q = (instruction or "").strip()
    if section:
        q = (q + " " + section).strip()
    top_k = int(os.environ.get("WRITING_AGENT_RAG_TOP_K", "4"))
    max_chars = int(os.environ.get("WRITING_AGENT_RAG_MAX_CHARS", "2500"))
    per_paper = int(os.environ.get("WRITING_AGENT_RAG_PER_PAPER", "2"))
    res = retrieve_context(rag_dir=rag_dir, query=q, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    return res.context

def _select_models_by_memory(models: list[str], *, fallback: str) -> list[str]:
    candidates = [m.strip() for m in (models or []) if m and m.strip()]
    if not candidates:
        return [fallback]

    # Drop embedding-only models; they are not useful for text generation.
    candidates = [m for m in candidates if not _looks_like_embedding_model(m)]
    if not candidates:
        return [fallback]

    installed = _ollama_installed_models()
    if installed:
        candidates = [m for m in candidates if m in installed]
    if not candidates:
        return [fallback]

    max_active = int(os.environ.get("WRITING_AGENT_MAX_ACTIVE_MODELS", "2"))
    max_active = max(1, min(8, max_active))

    reserve_gb = float(os.environ.get("WRITING_AGENT_RAM_RESERVE_GB", "4"))
    ratio = float(os.environ.get("WRITING_AGENT_MODEL_BUDGET_RATIO", "0.55"))
    ratio = min(0.95, max(0.2, ratio))

    total_b, avail_b = _get_memory_bytes()
    avail_gb = avail_b / (1024**3)
    budget_gb = max(0.0, (avail_gb - reserve_gb) * ratio)
    if budget_gb <= 0.2:
        return [candidates[0]]

    sizes = _ollama_model_sizes_gb()
    out: list[str] = []
    used = 0.0
    for m in candidates:
        est = float(sizes.get(m, 4.0))
        # empirical overhead factor
        est = est * 1.15
        if not out:
            out.append(m)
            used += est
            if len(out) >= max_active:
                break
            continue
        if used + est <= budget_gb and len(out) < max_active:
            out.append(m)
            used += est
    return out or [candidates[0]]


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


def _postprocess_section(section: str, txt: str, *, min_paras: int, min_chars: int, min_tables: int, min_figures: int) -> str:
    s = (txt or "").replace("\r", "").strip()
    # Normalize paragraphs (model sometimes emits single-newline wrapped text)
    paras = [p.strip() for p in re.split(r"\n\s*\n+", s) if p.strip()]
    if len(paras) <= 1 and "\n" in s:
        # treat each non-empty line as a paragraph when no blank lines are used
        lines = [ln.strip() for ln in re.split(r"\n+", s) if ln.strip()]
        if len(lines) >= 2:
            paras = lines
    if len(paras) <= 1 and len(s) >= 420:
        # CJK-friendly fallback: split long single paragraph by sentences into 3-6 paragraphs
        parts = [p.strip() for p in re.split(r"(?<=[。！？!?.])\s*", s) if p.strip()]
        if len(parts) >= 6:
            chunked: list[str] = []
            buf: list[str] = []
            for part in parts:
                buf.append(part)
                if len("".join(buf)) >= 180:
                    chunked.append("".join(buf).strip())
                    buf = []
            if buf:
                chunked.append("".join(buf).strip())
            paras = [p for p in chunked if p]
    if len(paras) < max(2, min_paras):
        need = max(2, min_paras) - len(paras)
        paras.extend([f"[待补充]：补充“{section}”的关键细节与可操作步骤。" for _ in range(need)])

    joined = "\n\n".join(paras)
    if min_tables > 0 and "[[TABLE:" not in joined:
        joined += (
            "\n\n[[TABLE:{\"caption\":\"关键结果汇总（待补充）\",\"columns\":[\"指标\",\"方法A\",\"方法B\",\"备注\"],"
            "\"rows\":[[\"[待补充]\",\"[待补充]\",\"[待补充]\",\"[待补充]\"]]}]]"
        )
    if min_figures > 0 and "[[FIGURE:" not in joined:
        ftype = "bar" if ("结果" in section or "实验" in section or "评估" in section) else ("flow" if ("方法" in section or "实现" in section or "设计" in section) else "timeline")
        joined += f'\n\n[[FIGURE:{{"type":"{ftype}","caption":"{section}图示（待补充）","data":{{}}}}]]'
    if min_chars > 0:
        body_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", joined).strip())
        if body_len < min_chars and len(paras) >= max(2, min_paras):
            joined += f"\n\n[待补充]：补齐“{section}”的论证细节、定义边界、步骤与可落地建议（目标补足至约 {min_chars} 字符）。"
    return joined.strip()


def _ensure_section_minimums_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    section: str,
    instruction: str,
    draft: str,
    min_paras: int,
    min_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
) -> str:
    txt = _postprocess_section(section, draft, min_paras=min_paras, min_chars=min_chars, min_tables=min_tables, min_figures=min_figures)
    body_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", txt).strip())
    paras = [p for p in re.split(r"\n\s*\n+", txt) if p.strip()]
    if (len(paras) >= min_paras) and (min_chars <= 0 or body_len >= min_chars):
        return txt

    rounds = max(0, min(2, int(os.environ.get("WRITING_AGENT_SECTION_CONTINUE_ROUNDS", "2"))))
    if rounds <= 0:
        return txt

    client = OllamaClient(base_url=base_url, model=model, timeout_s=240.0)
    for r in range(rounds):
        missing_chars = max(0, int(min_chars) - body_len) if min_chars > 0 else 0
        out_queue.put({"event": "section", "phase": "delta", "section": section, "delta": f"\n\n[补齐 {r+1}/{rounds}] …\n"})
        system = (
            "你是报告续写Agent，只负责在不改变风格的前提下补齐该章节。\n"
            "规则：只输出纯文本；不要重复已有内容；不要编造真实数据/引用；未知信息用[待补充]。\n"
            "尽量补充：定义边界、步骤、可执行方案、风险与对策、验收方式。\n"
        )
        user = (
            f"文档标题：{title}\n章节：{section}\n\n"
            f"用户整体要求：\n{instruction}\n\n"
            f"当前章节草稿：\n{txt}\n\n"
            f"请继续补充该章节，至少新增 {max(220, missing_chars)} 字符，并确保最终至少 {min_paras} 段。"
        )
        buf: list[str] = []
        for delta in client.chat_stream(system=system, user=user, temperature=0.25):
            buf.append(delta)
            out_queue.put({"event": "section", "phase": "delta", "section": section, "delta": delta})
        txt = (txt + "\n\n" + "".join(buf)).strip()
        txt = _postprocess_section(section, txt, min_paras=min_paras, min_chars=min_chars, min_tables=min_tables, min_figures=min_figures)
        body_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", txt).strip())
        paras = [p for p in re.split(r"\n\s*\n+", txt) if p.strip()]
        if (len(paras) >= min_paras) and (min_chars <= 0 or body_len >= min_chars):
            break

    return txt


def _target_total_chars(config: GenerateConfig) -> int:
    raw = os.environ.get("WRITING_AGENT_TARGET_TOTAL_CHARS", "").strip()
    if raw.isdigit():
        return max(int(config.min_total_chars), int(raw))
    return max(int(config.min_total_chars), 4500)


def _compute_section_targets(*, sections: list[str], base_min_paras: int, total_chars: int) -> dict[str, SectionTargets]:
    weights = _load_section_weights()
    sec_weights: dict[str, float] = {}
    for s in sections:
        w = weights.get(s)
        if w is None:
            w = _guess_section_weight(s)
        sec_weights[s] = float(max(0.3, min(3.0, w)))

    denom = sum(sec_weights.values()) or 1.0
    out: dict[str, SectionTargets] = {}
    for sec in sections:
        w = sec_weights.get(sec, 1.0)
        min_paras = int(round(max(2.0, float(base_min_paras) * w)))
        min_paras = max(2, min(12, min_paras))

        share = int(round(float(total_chars) * (w / denom)))
        floor = 260 if "摘要" in sec else (180 if "参考" in sec else 420)
        min_chars = max(floor, min(9000, share))

        min_tables = 0
        min_figures = 0
        if any(k in sec for k in ["结果", "实验", "评估", "对比"]):
            min_tables = 1
            min_figures = 1
        elif any(k in sec for k in ["方法", "实现", "设计", "架构", "流程"]):
            min_figures = 1
        elif w >= 1.35 and "参考" not in sec and "附录" not in sec:
            min_figures = 1

        out[sec] = SectionTargets(weight=w, min_paras=min_paras, min_chars=min_chars, min_tables=min_tables, min_figures=min_figures)
    return out


def _guess_section_weight(section: str) -> float:
    s = (section or "").strip()
    if not s:
        return 1.0
    if "摘要" in s:
        return 0.7
    if "引言" in s or "背景" in s or "概述" in s:
        return 1.0
    if any(k in s for k in ["方法", "实现", "设计", "系统", "架构"]):
        return 1.35
    if any(k in s for k in ["实验", "结果", "评估", "分析", "讨论"]):
        return 1.45
    if "结论" in s or "总结" in s:
        return 0.9
    if "参考" in s:
        return 0.6
    if "附录" in s:
        return 0.55
    return 1.0


def _load_section_weights() -> dict[str, float]:
    raw = os.environ.get("WRITING_AGENT_SECTION_WEIGHTS", "").strip()
    if not raw:
        return {}
    try:
        if raw.lstrip().startswith("{"):
            obj = json.loads(raw)
            if isinstance(obj, dict):
                out: dict[str, float] = {}
                for k, v in obj.items():
                    if not isinstance(k, str):
                        continue
                    try:
                        out[k.strip()] = float(v)
                    except Exception:
                        continue
                return out
    except Exception:
        pass

    out2: dict[str, float] = {}
    for part in raw.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        try:
            out2[k] = float(v.strip())
        except Exception:
            continue
    return out2


def _format_section_constraints(*, required: list[str], targets: dict[str, SectionTargets] | None) -> str:
    if not targets:
        return "- 每章：>=3段（空行分隔），内容具体。"
    lines: list[str] = []
    for sec in required[:18]:
        t = targets.get(sec)
        if t is None:
            continue
        extra: list[str] = []
        if t.min_tables > 0:
            extra.append(f"表>={t.min_tables}")
        if t.min_figures > 0:
            extra.append(f"图>={t.min_figures}")
        suffix = ("，" + "，".join(extra)) if extra else ""
        lines.append(f"- {sec}：段>={t.min_paras}，字>={t.min_chars}{suffix}")
    if len(required) > 18:
        lines.append("- 其余章节：按对应权重目标补齐。")
    return "\n".join(lines) if lines else "- 每章：>=3段（空行分隔），内容具体。"


def _doc_body_len(text: str) -> int:
    s = (text or "").replace("\r", "")
    # strip headings
    s = re.sub(r"(?m)^#{1,3}\s+.*?$", "", s)
    # strip markers
    s = re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", s, flags=re.IGNORECASE)
    return len(s.strip())


def _merge_sections_text(title: str, sections: list[str], section_text: dict[str, str]) -> str:
    out = [f"# {title}"]
    for sec in sections:
        out.append(f"## {sec}")
        out.append((section_text.get(sec) or "").strip() or "[待补充]")
    return "\n\n".join(out).strip() + "\n"


def _aggregate_fix_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    draft: str,
    required_h2: list[str] | None,
    targets: dict[str, SectionTargets] | None,
) -> str:
    client = OllamaClient(base_url=base_url, model=model, timeout_s=180.0)
    required = [h.strip() for h in (required_h2 or []) if h and h.strip()]
    if not required:
        required = ["摘要", "引言", "方法", "结果", "结论", "参考文献"]

    constraints = _format_section_constraints(required=required, targets=targets)
    draft_len = _doc_body_len(draft)
    system = (
        "你是“报告统筹合并Agent”。你会收到一份草稿文本（含章节），需要把它改成更完整、更一致的最终稿。\n"
        "输出规则（必须遵守）：\n"
        "1) 只输出纯文本，不要HTML，不要Markdown（但可以保留以“# 标题 / ## 章节”形式的标题行）。\n"
        "2) 必须保留并输出这些章节（按顺序）："
        + "、".join(required)
        + "。\n"
        "3) 按章节最低要求补齐篇幅与结构（空行分隔，内容要具体；缺失信息用 [待补充]）：\n"
        + constraints
        + "\n"
        "4) 不要删除草稿中的任何正文段落（除非明显重复/乱码），不要把草稿浓缩成很短的摘要；输出长度应 >= 草稿长度的 85%（当前草稿约 "
        + str(draft_len)
        + " 字符）。\n"
        "5) 不要删除草稿中的 [[TABLE:...]] / [[FIGURE:...]] 标记；可以补充更多标记但必须是合法JSON。\n"
        "6) 不要编造真实数据/引用。\n"
    )
    user = f"文档标题：{title}\n用户要求：{instruction}\n\n草稿：\n{draft}\n\n请输出最终稿。"

    buf: list[str] = []
    for delta in client.chat_stream(system=system, user=user, temperature=0.2):
        buf.append(delta)
    return "".join(buf).strip() or draft


def _repair_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    draft: str,
    problems: list[str],
    required_h2: list[str] | None,
    targets: dict[str, SectionTargets] | None,
) -> str:
    client = OllamaClient(base_url=base_url, model=model, timeout_s=180.0)
    required = [h.strip() for h in (required_h2 or []) if h and h.strip()]
    if not required:
        required = ["摘要", "引言", "方法", "结果", "结论", "参考文献"]

    constraints = _format_section_constraints(required=required, targets=targets)
    draft_len = _doc_body_len(draft)
    system = (
        "你是“报告修复Agent”。你会收到一份报告草稿和一组校验问题，需要在不偷懒的前提下修复。\n"
        "输出规则：\n"
        "1) 只输出纯文本；保留“# 标题 / ## 章节”标题行。\n"
        "2) 必须包含并按顺序输出这些章节："
        + "、".join(required)
        + "。\n"
        "3) 修复段落不足/内容过短，按章节最低要求补齐：\n"
        + constraints
        + "\n"
        "4) 不要删除草稿中的任何正文段落（除非明显重复/乱码），不要把草稿浓缩成很短的摘要；输出长度应 >= 草稿长度的 85%（当前草稿约 "
        + str(draft_len)
        + " 字符）。\n"
        "5) 必须保留并可补充 [[TABLE:...]] / [[FIGURE:...]] 标记；JSON必须合法。\n"
        "6) 不要编造真实数据/引用。\n"
    )
    user = (
        f"文档标题：{title}\n用户要求：{instruction}\n\n"
        f"校验问题：\n- " + "\n- ".join(problems) + "\n\n"
        f"草稿：\n{draft}\n\n"
        "请输出修复后的最终稿。"
    )
    buf: list[str] = []
    for delta in client.chat_stream(system=system, user=user, temperature=0.2):
        buf.append(delta)
    return "".join(buf).strip() or draft
