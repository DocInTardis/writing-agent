from __future__ import annotations
import io
import json
import traceback
from pathlib import Path
import logging
import os
import shutil
import subprocess
import re
import tempfile
import threading
import queue
import time
import uuid
import traceback
import sqlite3
from datetime import datetime
from dataclasses import dataclass
from typing import Iterable
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
from writing_agent.document import ExportPrefs, V2ReportDocxExporter
from writing_agent.document.html_docx import HtmlDocxBuilder
from writing_agent.agents.citations import CitationAgent
from writing_agent.models import Citation, CitationStyle
from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings
from writing_agent.storage import InMemoryStore, VersionNode
from writing_agent.mcp_client import fetch_mcp_resource
from writing_agent.web.html_sanitize import sanitize_html
from writing_agent.web.block_edit import apply_block_edit
from writing_agent.v2.doc_format import parse_report_text, _split_heading_glue as _split_heading_glue_v2
from writing_agent.v2.doc_ir import (
    from_dict as doc_ir_from_dict,
    from_text as doc_ir_from_text,
    to_dict as doc_ir_to_dict,
    to_parsed as doc_ir_to_parsed,
    to_text as doc_ir_to_text,
    apply_ops as doc_ir_apply_ops,
    Operation as DocIROperation,
    diff_blocks as doc_ir_diff,
)
from writing_agent.v2.figure_render import render_figure_svg
from writing_agent.v2.graph_runner import (
    GenerateConfig,
    run_generate_graph,
    _sanitize_output_text,
    _merge_sections_text,
    _generic_fill_paragraph,
    _format_reference_items,
    _is_reference_section,
    _plan_title,
)
from writing_agent.v2.rust_bridge import try_rust_docx_export, try_rust_import
from writing_agent.v2.rag.arxiv import download_arxiv_pdf, search_arxiv
from writing_agent.v2.rag.openalex import search_openalex
def _start_ollama_serve() -> None:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
def _wait_until(predicate, timeout_s: float, interval_s: float = 0.2) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        if predicate():
            return True
        time.sleep(interval_s)
    return False
def _iter_with_timeout(gen, per_event: float = 0.0, overall: float = 0.0):
    """
    Iterate generator with optional per-event / overall timeout.
    Used to detect stalled generation and allow fallback.
    """
    if per_event <= 0 and overall <= 0:
        for item in gen:
            yield item
        return
    start = time.time()
    q: queue.Queue = queue.Queue()
    done = object()
    def _worker() -> None:
        try:
            for item in gen:
                q.put(("item", item))
            q.put(("done", done))
        except Exception as e:
            q.put(("err", e))
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    while True:
        timeout = per_event if per_event and per_event > 0 else None
        if overall and overall > 0:
            remaining = overall - (time.time() - start)
            if remaining <= 0:
                raise TimeoutError("generation timeout")
            timeout = remaining if timeout is None else min(timeout, remaining)
        try:
            kind, payload = q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("generation stalled")
        if kind == "item":
            yield payload
        elif kind == "done":
            break
        elif kind == "err":
            raise payload
def _run_with_timeout(fn, timeout_s: float, fallback):
    if timeout_s <= 0:
        return fn()
    q: queue.Queue = queue.Queue()
    def _worker() -> None:
        try:
            q.put(("ok", fn()))
        except Exception as e:
            q.put(("err", e))
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    try:
        kind, payload = q.get(timeout=timeout_s)
    except queue.Empty:
        return fallback
    if kind == "ok":
        return payload
    return fallback
_STREAM_METRICS_PATH = Path(".data/metrics/stream_timing.json")
_MCP_CITATIONS_CACHE: dict = {"ts": 0.0, "items": {}}
def _load_stream_metrics() -> dict:
    if not _STREAM_METRICS_PATH.exists():
        return {"runs": []}
    try:
        raw = _STREAM_METRICS_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("runs"), list):
            return data
    except Exception:
        pass
    return {"runs": []}
def _save_stream_metrics(data: dict) -> None:
    _STREAM_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STREAM_METRICS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    if len(vals) == 1:
        return float(vals[0])
    idx = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * q))))
    return float(vals[idx])
def _record_stream_timing(*, total_s: float, max_gap_s: float) -> None:
    data = _load_stream_metrics()
    runs = data.get("runs") if isinstance(data.get("runs"), list) else []
    runs.append({"total_s": float(total_s), "max_gap_s": float(max_gap_s), "ts": time.time()})
    data["runs"] = runs[-30:]
    _save_stream_metrics(data)
def _load_mcp_citations_cached() -> dict[str, Citation]:
    cache = _MCP_CITATIONS_CACHE
    now = time.time()
    if cache.get("items") and (now - float(cache.get("ts") or 0)) < 3600:
        return cache.get("items") or {}
    uri = os.environ.get("WRITING_AGENT_MCP_REF_URI", "mcp://references/default")
    result = fetch_mcp_resource(uri)
    items: dict[str, Citation] = {}
    try:
        contents = result.get("contents") if isinstance(result, dict) else None
        if isinstance(contents, list) and contents:
            payload = contents[0].get("text") if isinstance(contents[0], dict) else None
            data = json.loads(payload) if payload else None
            if isinstance(data, list):
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    key = str(row.get("key") or "").strip()
                    title = str(row.get("title") or "").strip()
                    if not key or not title:
                        continue
                    items[key] = Citation(
                        key=key,
                        title=title,
                        url=str(row.get("url") or "") or None,
                        authors=str(row.get("authors") or "") or None,
                        year=str(row.get("year") or "") or None,
                        venue=str(row.get("venue") or "") or None,
                    )
    except Exception:
        items = {}
    cache["ts"] = now
    cache["items"] = items
    return items
def _ensure_mcp_citations(session) -> None:
    if session.citations:
        return
    items = _load_mcp_citations_cached()
    if not items:
        return
    session.citations = items
    try:
        doc_ir = None
        if session.doc_ir:
            doc_ir = doc_ir_from_dict(session.doc_ir)
        elif session.doc_text:
            doc_ir = doc_ir_from_text(session.doc_text)
        if doc_ir is not None:
            style = _citation_style_from_session(session)
            doc_ir = _apply_citations_to_doc_ir(doc_ir, session.citations, style)
            session.doc_ir = doc_ir_to_dict(doc_ir)
            session.doc_text = doc_ir_to_text(doc_ir)
    except Exception:
        pass
def _mcp_rag_enabled() -> bool:
    raw = os.environ.get("WRITING_AGENT_RAG_MCP", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}
def _mcp_first_json(result: dict | None):
    if not isinstance(result, dict):
        return None
    contents = result.get("contents")
    if not isinstance(contents, list) or not contents:
        return None
    item = contents[0] if isinstance(contents[0], dict) else None
    if not isinstance(item, dict):
        return None
    text = str(item.get("text") or "")
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None
def _mcp_rag_retrieve(query: str, *, top_k: int, per_paper: int, max_chars: int):
    if not _mcp_rag_enabled():
        return None
    q = (query or "").strip()
    if not q:
        return None
    uri = (
        "mcp://rag/retrieve?query="
        + quote(q)
        + f"&top_k={int(top_k)}&per_paper={int(per_paper)}&max_chars={int(max_chars)}"
    )
    result = fetch_mcp_resource(uri)
    return _mcp_first_json(result)
def _mcp_rag_search(query: str, *, top_k: int, sources=None, max_results: int | None = None, mode: str = ""):
    if not _mcp_rag_enabled():
        return None
    q = (query or "").strip()
    if not q:
        return None
    uri = "mcp://rag/search?query=" + quote(q) + f"&top_k={int(top_k)}"
    if isinstance(sources, list) and sources:
        src = ",".join([str(s).strip() for s in sources if str(s).strip()])
        if src:
            uri += "&sources=" + quote(src)
    if max_results:
        uri += f"&max_results={int(max_results)}"
    if mode:
        uri += "&mode=" + quote(mode)
    result = fetch_mcp_resource(uri)
    return _mcp_first_json(result)
def _mcp_rag_search_chunks(query: str, *, top_k: int, per_paper: int, alpha: float, use_embeddings: bool):
    if not _mcp_rag_enabled():
        return None
    q = (query or "").strip()
    if not q:
        return None
    use_flag = "1" if use_embeddings else "0"
    uri = (
        "mcp://rag/search/chunks?query="
        + quote(q)
        + f"&top_k={int(top_k)}&per_paper={int(per_paper)}&alpha={float(alpha)}&use_embeddings={use_flag}"
    )
    result = fetch_mcp_resource(uri)
    return _mcp_first_json(result)
def _recommended_stream_timeouts() -> tuple[float, float]:
    data = _load_stream_metrics()
    runs = data.get("runs") if isinstance(data.get("runs"), list) else []
    totals = [float(r.get("total_s", 0)) for r in runs if r.get("total_s")]
    gaps = [float(r.get("max_gap_s", 0)) for r in runs if r.get("max_gap_s")]
    p95_total = _percentile(totals, 0.95)
    p95_gap = _percentile(gaps, 0.95)
    default_total = 600.0
    default_gap = 180.0
    probe_path = Path(".data/out/ui_timeout_probe.json")
    if probe_path.exists():
        try:
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            max_total_ms = float(probe.get("max_total_ms") or 0)
            max_gap_ms = float(probe.get("max_gap_ms") or 0)
            if max_total_ms > 0:
                default_total = max(default_total, (max_total_ms / 1000.0) * 1.2)
            if max_gap_ms > 0:
                default_gap = max(default_gap, (max_gap_ms / 1000.0) * 3.0)
        except Exception:
            pass
    overall_s = max(default_total, p95_total * 1.3 if p95_total > 0 else 0.0)
    stall_s = max(default_gap, p95_gap * 3 if p95_gap > 0 else 0.0)
    return overall_s, stall_s
def _run_with_heartbeat(fn, timeout_s: float, fallback, *, label: str, heartbeat_s: float = 3.0):
    if timeout_s <= 0:
        return fn()
    q: queue.Queue = queue.Queue()
    def _worker() -> None:
        try:
            q.put(("ok", fn()))
        except Exception as e:
            q.put(("err", e))
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    start_ts = time.time()
    last_emit = time.time()
    while True:
        try:
            kind, payload = q.get(timeout=1.0)
            if kind == "ok":
                return payload
            return fallback
        except queue.Empty:
            if time.time() - start_ts > timeout_s:
                return fallback
            if time.time() - last_emit > heartbeat_s:
                yield f"{label}…"
                last_emit = time.time()
def _default_outline_from_instruction(text: str) -> list[str]:
    """Heuristic outline placeholder (disabled to avoid special-case formats)."""
    return []
def _fallback_prompt_sections(session) -> list[str]:
    if getattr(session, "template_outline", None):
        out: list[str] = []
        for item in (session.template_outline or []):
            try:
                _, title = item
            except Exception:
                continue
            t = str(title or "").strip()
            if t:
                out.append(t)
        return out
    if getattr(session, "template_required_h2", None):
        return [str(t or "").strip() for t in (session.template_required_h2 or []) if str(t or "").strip()]
    return []
def _build_fallback_prompt(session, *, instruction: str, length_hint: str) -> tuple[str, str]:
    sections = _fallback_prompt_sections(session)
    section_hint = ""
    if sections:
        section_hint = "必须按顺序使用以下二级标题（##）：\n" + "、".join(sections) + "\n"
    prompt = (
        "你是文档写作助手，请根据用户需求生成一份中文正式文档，Markdown 输出。\n"
        "必须包含一级标题（#），结构清晰、表达正式，避免模板口吻或提示语。\n"
        f"{section_hint}"
        f"{length_hint}"
        "用户需求：\n"
        f"{instruction}\n"
    )
    system = "你是专业文档写手，只输出Markdown正文。"
    return system, prompt
def _single_pass_generate(session, *, instruction: str, current_text: str, target_chars: int = 0) -> str:
    """Single-pass fallback generation."""
    settings = get_ollama_settings()
    if not settings.enabled:
        raise OllamaError("\u6a21\u578b\u672a\u542f\u7528")
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise OllamaError("\u6a21\u578b\u672a\u5c31\u7eea")
    length_hint = ""
    options = None
    if target_chars and 100 <= target_chars <= 20000:
        # Improved length control with more explicit instructions
        length_hint = f"\u91cd\u8981\uff1a\u76ee\u6807\u5b57\u6570\u4e3a {target_chars} \u5b57\uff0c\u8bf7\u4e25\u683c\u63a7\u5236\u5728 {int(target_chars * 0.9)}-{int(target_chars * 1.1)} \u5b57\u4e4b\u95f4\u3002\n"
        # Adjust num_predict to be closer to target (1.1x instead of 1.2x)
        num_predict = min(2000, max(200, int(target_chars * 1.1)))
        options = {"num_predict": num_predict}
    system, prompt = _build_fallback_prompt(session, instruction=instruction, length_hint=length_hint)
    raw = client.chat(system=system, user=prompt, temperature=0.5, options=options)
    return _sanitize_output_text(raw)
def _single_pass_generate_with_heartbeat(session, *, instruction: str, current_text: str, target_chars: int = 0, heartbeat_callback=None):
    """Single-pass generation with heartbeat support for progress feedback.
    Args:
        session: Document session
        instruction: User instruction
        current_text: Current document text
        target_chars: Target character count
        heartbeat_callback: Optional callback function called periodically during generation
    Returns:
        Generated text
    """
    settings = get_ollama_settings()
    if not settings.enabled:
        raise OllamaError("\u6a21\u578b\u672a\u542f\u7528")
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise OllamaError("\u6a21\u578b\u672a\u5c31\u7eea")
    length_hint = ""
    options = None
    if target_chars and 100 <= target_chars <= 20000:
        # Improved length control with more explicit instructions
        length_hint = f"\u91cd\u8981\uff1a\u76ee\u6807\u5b57\u6570\u4e3a {target_chars} \u5b57\uff0c\u8bf7\u4e25\u683c\u63a7\u5236\u5728 {int(target_chars * 0.9)}-{int(target_chars * 1.1)} \u5b57\u4e4b\u95f4\u3002\n"
        # Adjust num_predict to be closer to target (1.1x instead of 1.2x)
        num_predict = min(2000, max(200, int(target_chars * 1.1)))
        options = {"num_predict": num_predict}
    system, prompt = _build_fallback_prompt(session, instruction=instruction, length_hint=length_hint)
    # Run generation in a thread with heartbeat
    result_queue: queue.Queue = queue.Queue()
    def _generate_worker():
        try:
            raw = client.chat(system=system, user=prompt, temperature=0.5, options=options)
            result_queue.put(("ok", _sanitize_output_text(raw)))
        except Exception as e:
            result_queue.put(("error", e))
    thread = threading.Thread(target=_generate_worker, daemon=True)
    thread.start()
    # Send heartbeat while waiting
    heartbeat_interval = 5.0  # Send heartbeat every 5 seconds
    last_heartbeat = time.time()
    heartbeat_messages = [
        "\u6b63\u5728\u751f\u6210\u5185\u5bb9...",
        "\u6b63\u5728\u7ec4\u7ec7\u8bed\u8a00...",
        "\u6b63\u5728\u4f18\u5316\u8868\u8fbe...",
        "\u5373\u5c06\u5b8c\u6210...",
    ]
    heartbeat_index = 0
    while thread.is_alive():
        try:
            kind, payload = result_queue.get(timeout=0.5)
            if kind == "ok":
                return payload
            else:
                raise payload
        except queue.Empty:
            # Check if we need to send heartbeat
            now = time.time()
            if heartbeat_callback and (now - last_heartbeat) >= heartbeat_interval:
                heartbeat_callback()
                last_heartbeat = now
                heartbeat_index = (heartbeat_index + 1) % len(heartbeat_messages)
    # Thread finished, get result
    try:
        kind, payload = result_queue.get(timeout=1.0)
        if kind == "ok":
            return payload
        else:
            raise payload
    except queue.Empty:
        raise OllamaError("\u751f\u6210\u8d85\u65f6")
def _single_pass_generate_stream(session, *, instruction: str, current_text: str, target_chars: int = 0):
    """Single-pass generation that yields streaming deltas."""
    settings = get_ollama_settings()
    if not settings.enabled:
        raise OllamaError("\u6a21\u578b\u672a\u542f\u7528")
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise OllamaError("\u6a21\u578b\u672a\u5c31\u7eea")
    length_hint = ""
    options = None
    if target_chars and 100 <= target_chars <= 20000:
        # Improved length control with more explicit instructions
        length_hint = f"\u91cd\u8981\uff1a\u76ee\u6807\u5b57\u6570\u4e3a {target_chars} \u5b57\uff0c\u8bf7\u4e25\u683c\u63a7\u5236\u5728 {int(target_chars * 0.9)}-{int(target_chars * 1.1)} \u5b57\u4e4b\u95f4\u3002\n"
        # Adjust num_predict to be closer to target (1.1x instead of 1.2x)
        num_predict = min(2000, max(200, int(target_chars * 1.1)))
        options = {"num_predict": num_predict}
    system, prompt = _build_fallback_prompt(session, instruction=instruction, length_hint=length_hint)
    buf = ""
    emit_buf = ""
    last_emit = time.time()
    chunk_min = int(os.environ.get("WRITING_AGENT_STREAM_CHUNK", "60"))
    chunk_min = max(20, min(400, chunk_min))
    for delta in client.chat_stream(system=system, user=prompt, temperature=0.5, options=options):
        buf += delta
        emit_buf += delta
        now = time.time()
        if len(emit_buf) >= chunk_min or (now - last_emit) > 1.2:
            yield {"event": "section", "phase": "delta", "section": "", "delta": emit_buf}
            emit_buf = ""
            last_emit = now
    if emit_buf:
        yield {"event": "section", "phase": "delta", "section": "", "delta": emit_buf}
    if buf.strip():
        yield {"event": "result", "text": _sanitize_output_text(buf)}
    else:
        raise OllamaError("\u751f\u6210\u8d85\u65f6")
def _check_generation_quality(text: str, target_chars: int = 0) -> list[str]:
    """Check the quality of generated text and return a list of issues.
    Args:
        text: Generated text to check
        target_chars: Target character count (0 means no target)
    Returns:
        List of quality issues found
    """
    issues = []
    # Check if text is too short
    if len(text.strip()) < 50:
        issues.append("\u751f\u6210\u5185\u5bb9\u8fc7\u77ed\uff0c\u5c11\u4e8e50\u5b57\u7b26")
    # Check if text is empty
    if not text.strip():
        issues.append("\u751f\u6210\u5185\u5bb9\u4e3a\u7a7a")
    # Check for repeated content (simple check for repeated lines)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if len(lines) != len(set(lines)):
        # Count duplicates
        from collections import Counter
        line_counts = Counter(lines)
        duplicates = [line for line, count in line_counts.items() if count > 1]
        if duplicates:
            issues.append(f"\u68c0\u6d4b\u5230\u91cd\u590d\u5185\u5bb9\uff1a{len(duplicates)}\u884c\u91cd\u590d")
    # Check for proper heading structure
    if '##' not in text and '#' not in text:
        issues.append("\u7f3a\u5c11\u6807\u9898\u7ed3\u6784")
    # Check length deviation if target is specified
    if target_chars > 0:
        actual_chars = len(text)
        deviation = abs(actual_chars - target_chars) / target_chars
        if deviation > 0.3:  # More than 30% deviation
            issues.append(f"\u5b57\u6570\u504f\u5dee\u8f83\u5927\uff1a\u76ee\u6807{target_chars}\u5b57\uff0c\u5b9e\u9645{actual_chars}\u5b57\uff08\u504f\u5dee{deviation*100:.1f}%\uff09")
    # Check for incomplete sentences (ends with comma or incomplete punctuation)
    if text.strip() and text.strip()[-1] in [',', '\uff0c', '...', '\u2026']:
        issues.append("\u6587\u6863\u7ed3\u5c3e\u4e0d\u5b8c\u6574")
    return issues
def _looks_like_prompt_echo(text: str, instruction: str) -> bool:
    src = (text or "").strip()
    if not src:
        return True
    lower = src.lower()
    # common prompt fragments
    phrases = [
        "你是文档写作助手",
        "只输出markdown正文",
        "markdown 输出",
        "用户需求",
        "必须包含",
        "按顺序使用以下二级标题",
        "用用户需求",
        "请生成",
        "请输出",
    ]
    hit = sum(1 for p in phrases if p in src)
    if hit >= 2:
        return True
    if src.startswith("你是") and ("助手" in src or "模型" in src or "写作" in src):
        return True
    if "用户需求" in src and (instruction.strip()[:12] in src):
        return True
    # prompt echoes are usually short and instruction-heavy
    if len(src) < 200 and ("用户需求" in src or "markdown" in lower):
        return True
    return False
def _system_pressure_high() -> bool:
    raw_cpu = os.environ.get("WRITING_AGENT_FAST_CPU", "").strip()
    raw_mem = os.environ.get("WRITING_AGENT_FAST_MEM", "").strip()
    try:
        cpu_th = float(raw_cpu) if raw_cpu else 85.0
    except Exception:
        cpu_th = 85.0
    try:
        mem_th = float(raw_mem) if raw_mem else 85.0
    except Exception:
        mem_th = 85.0
    try:
        import psutil  # type: ignore
    except Exception:
        return False
    try:
        cpu = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory().percent
    except Exception:
        return False
    return cpu >= cpu_th or mem >= mem_th
def _should_use_fast_generate(raw_instruction: str, target_chars: int, prefs: dict | None) -> bool:
    prefs = prefs or {}
    if str(os.environ.get("WRITING_AGENT_FAST_GENERATE", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if prefs.get("fast_generate") is True:
        return True
    return _system_pressure_high()
def _pull_model_stream_iter(base_url: str, name: str, *, timeout_s: float) -> Iterable[str] | tuple[bool, str]:
    url = f"{base_url}/api/pull"
    payload = json.dumps({"name": name, "stream": True}).encode("utf-8")
    req = UrlRequest(url=url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    started = time.time()
    last_status = ""
    try:
        with urlopen(req, timeout=min(10.0, max(2.0, timeout_s))) as resp:
            for raw in resp:
                if time.time() - started > timeout_s:
                    return False, f"pull timeout: {name}"
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                status = str(data.get("status") or "")
                completed = data.get("completed")
                total = data.get("total")
                if status and status != last_status:
                    last_status = status
                if status and isinstance(completed, (int, float)) and isinstance(total, (int, float)) and total > 0:
                    pct = int((completed / total) * 100)
                    last_status = f"{status} {pct}%"
                if last_status:
                    yield f"{name}: {last_status}"
                if status.lower() == "success":
                    return True, ""
    except Exception as e:
        return False, f"pull failed: {e}"
    return True, ""
def _pull_model_stream(base_url: str, name: str, *, timeout_s: float) -> tuple[bool, str]:
    it = _pull_model_stream_iter(base_url, name, timeout_s=timeout_s)
    if isinstance(it, tuple):
        return it
    ok = True
    msg = ""
    try:
        for _ in it:
            pass
    except StopIteration as e:
        ok, msg = e.value or (True, "")
    return ok, msg
def _ensure_ollama_ready_iter() -> Iterable[str] | tuple[bool, str]:
    settings = get_ollama_settings()
    if not settings.enabled:
        return False, "未启用模型服务"
    base_url = settings.base_url
    timeout_s = float(os.environ.get("WRITING_AGENT_OLLAMA_PREP_TIMEOUT_S", "120"))
    probe = OllamaClient(base_url=base_url, model=settings.model, timeout_s=min(5.0, settings.timeout_s))
    client = OllamaClient(base_url=base_url, model=settings.model, timeout_s=settings.timeout_s)
    yield f"检查模型服务：{base_url}"
    if not probe.is_running():
        yield "启动模型服务…"
        try:
            _start_ollama_serve()
        except FileNotFoundError:
            return False, "未找到 ollama，可执行文件不在 PATH"
        if not _wait_until(probe.is_running, timeout_s=12):
            return False, f"Ollama 未就绪：{settings.base_url}"
    models: set[str] = set()
    def _add(name: str | None) -> None:
        n = str(name or "").strip()
        if n:
            models.add(n)
    _add(settings.model)
    _add(os.environ.get("WRITING_AGENT_AGG_MODEL", "").strip())
    _add(os.environ.get("WRITING_AGENT_ANALYSIS_MODEL", "").strip())
    _add(os.environ.get("WRITING_AGENT_EXTRACT_MODEL", "").strip())
    _add(os.environ.get("WRITING_AGENT_DRAFT_MAIN_MODEL", "").strip())
    _add(os.environ.get("WRITING_AGENT_DRAFT_SUPPORT_MODEL", "").strip())
    workers_raw = os.environ.get("WRITING_AGENT_WORKER_MODELS", "").strip()
    if workers_raw:
        for item in workers_raw.split(","):
            _add(item)
    try:
        for name in sorted(models):
            c = OllamaClient(base_url=base_url, model=name, timeout_s=settings.timeout_s)
            c_probe = OllamaClient(base_url=base_url, model=name, timeout_s=min(5.0, settings.timeout_s))
            if not c_probe.has_model():
                yield f"拉取模型：{name}"
                pull_iter = _pull_model_stream_iter(base_url, name, timeout_s=timeout_s)
                if isinstance(pull_iter, tuple):
                    ok, msg = pull_iter
                else:
                    ok, msg = True, ""
                    try:
                        while True:
                            note = next(pull_iter)
                            if note:
                                yield str(note)
                    except StopIteration as e:
                        ok, msg = e.value or (True, "")
                if not ok:
                    return False, msg or f"模型准备超时：{name}"
            if not c_probe.has_model():
                return False, f"模型未就绪：{name}"
    except Exception:
        return False, "模型准备失败"
    return True, ""
def _ensure_ollama_ready() -> tuple[bool, str]:
    settings = get_ollama_settings()
    if not settings.enabled:
        return False, "未启用模型服务"
    base_url = settings.base_url
    timeout_s = settings.timeout_s
    probe = OllamaClient(base_url=base_url, model=settings.model, timeout_s=min(5.0, timeout_s))
    client = OllamaClient(base_url=base_url, model=settings.model, timeout_s=timeout_s)
    if not probe.is_running():
        try:
            _start_ollama_serve()
        except FileNotFoundError:
            return False, "未找到 ollama，可执行文件不在 PATH"
        if not _wait_until(probe.is_running, timeout_s=12):
            return False, f"Ollama 未就绪：{settings.base_url}"
    models: set[str] = set()
    def _add(name: str | None) -> None:
        n = str(name or "").strip()
        if n:
            models.add(n)
    _add(settings.model)
    _add(os.environ.get("WRITING_AGENT_AGG_MODEL", "").strip())
    _add(os.environ.get("WRITING_AGENT_ANALYSIS_MODEL", "").strip())
    _add(os.environ.get("WRITING_AGENT_EXTRACT_MODEL", "").strip())
    _add(os.environ.get("WRITING_AGENT_DRAFT_MAIN_MODEL", "").strip())
    _add(os.environ.get("WRITING_AGENT_DRAFT_SUPPORT_MODEL", "").strip())
    workers_raw = os.environ.get("WRITING_AGENT_WORKER_MODELS", "").strip()
    if workers_raw:
        for item in workers_raw.split(","):
            _add(item)
    try:
        prep_timeout = float(os.environ.get("WRITING_AGENT_OLLAMA_PREP_TIMEOUT_S", "120"))
        for name in sorted(models):
            c = OllamaClient(base_url=base_url, model=name, timeout_s=timeout_s)
            c_probe = OllamaClient(base_url=base_url, model=name, timeout_s=min(5.0, timeout_s))
            if not c_probe.has_model():
                ok, msg = _pull_model_stream(base_url, name, timeout_s=prep_timeout)
                if not ok:
                    return False, msg or f"模型准备超时：{name}"
            if not c_probe.has_model():
                return False, f"模型未就绪：{name}"
    except Exception:
        return False, "模型准备失败"
    return True, ""
def _summarize_analysis(raw: str, analysis: dict) -> dict:
    if not isinstance(analysis, dict):
        return {"summary": "", "missing": [], "steps": []}
    intent = analysis.get("intent") or {}
    entities = analysis.get("entities") or {}
    missing = analysis.get("missing") or []
    constraints = analysis.get("constraints") or []
    decomp = analysis.get("decomposition") or analysis.get("steps") or []
    parts = []
    if raw:
        parts.append(f"需求：{raw}")
    name = str(intent.get("name") or "").strip()
    if name:
        parts.append(f"意图：{name}")
    label_map = {
        "title": "标题",
        "purpose": "用途",
        "length": "长度",
        "formatting": "格式",
        "audience": "受众",
        "output_form": "输出",
        "voice": "语气",
        "avoid": "避免",
        "scope": "范围",
    }
    for key, label in label_map.items():
        val = str(entities.get(key) or "").strip()
        if val:
            parts.append(f"{label}：{val}")
    if constraints:
        parts.append("约束：" + "；".join([str(x) for x in constraints if str(x).strip()]))
    steps = []
    if isinstance(decomp, list):
        steps.extend([str(x).strip() for x in decomp if str(x).strip()])
    if not steps and constraints:
        steps.extend([f"约束：{str(x).strip()}" for x in constraints if str(x).strip()])
    return {
        "summary": " | ".join([p for p in parts if p]),
        "missing": missing,
        "steps": steps[:6],
    }
from writing_agent.v2.rag.index import RagIndex
from writing_agent.v2.rag.search import search_papers
from writing_agent.v2.rag.retrieve import retrieve_context
from writing_agent.v2.rag.search import build_rag_context, search_papers
from writing_agent.v2.rag.store import RagStore
from writing_agent.v2.rag.user_library import UserLibrary, _extract_text
from writing_agent.v2.rag import search_arxiv
from writing_agent.v2.template_parse import prepare_template_file, parse_template_file
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
def _static_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0
STATIC_VERSION = int(
    max(
        _static_mtime(BASE_DIR / "static" / "v2.css"),
        _static_mtime(BASE_DIR / "static" / "v2.js"),
        _static_mtime(BASE_DIR / "static" / "v2_svelte" / "main.js"),
        _static_mtime(BASE_DIR / "static" / "v2_svelte" / "style.css"),
    )
)
PERF_MODE = os.environ.get("WRITING_AGENT_PERF_MODE", "").strip() == "1"
app = FastAPI(title="Writing Agent Studio (v2)")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
@app.get("/wa_bridge_bg.wasm")
def wa_bridge_wasm() -> Response:
    wasm_path = BASE_DIR / "static" / "v2_svelte" / "wa_bridge_bg.wasm"
    if not wasm_path.exists():
        raise HTTPException(status_code=404, detail="wa_bridge_bg.wasm not found")
    return FileResponse(wasm_path, media_type="application/wasm")
store = InMemoryStore()
docx_exporter = V2ReportDocxExporter()
html_docx_exporter = HtmlDocxBuilder()
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(REPO_ROOT / ".data"))).resolve()
USER_TEMPLATES_DIR = DATA_DIR / "templates"
RAG_DIR = DATA_DIR / "rag"
USER_LIBRARY_DIR = DATA_DIR / "library"
TEMPLATE_DIR = REPO_ROOT / "templates"
META_DB_PATH = DATA_DIR / "session_meta.db"
rag_store = RagStore(RAG_DIR)
rag_index = RagIndex(RAG_DIR)
user_library = UserLibrary(USER_LIBRARY_DIR, rag_index)
def _ensure_meta_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(META_DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS doc_meta (
                doc_id TEXT PRIMARY KEY,
                chat_json TEXT,
                thought_json TEXT,
                updated_at REAL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
def _load_meta(doc_id: str) -> dict:
    _ensure_meta_db()
    conn = sqlite3.connect(META_DB_PATH)
    try:
        cur = conn.execute(
            "SELECT chat_json, thought_json FROM doc_meta WHERE doc_id = ?",
            (doc_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"chat": [], "thoughts": []}
        chat_raw, thought_raw = row
        chat = json.loads(chat_raw) if chat_raw else []
        thoughts = json.loads(thought_raw) if thought_raw else []
        return {"chat": chat, "thoughts": thoughts}
    except Exception:
        return {"chat": [], "thoughts": []}
    finally:
        conn.close()
def _save_meta(doc_id: str, *, chat: list | None = None, thoughts: list | None = None) -> None:
    _ensure_meta_db()
    existing = _load_meta(doc_id)
    chat_items = chat if chat is not None else existing.get("chat", [])
    thought_items = thoughts if thoughts is not None else existing.get("thoughts", [])
    conn = sqlite3.connect(META_DB_PATH)
    try:
        conn.execute(
            "INSERT INTO doc_meta(doc_id, chat_json, thought_json, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(doc_id) DO UPDATE SET chat_json=excluded.chat_json, thought_json=excluded.thought_json, updated_at=excluded.updated_at",
            (
                doc_id,
                json.dumps(chat_items, ensure_ascii=False),
                json.dumps(thought_items, ensure_ascii=False),
                time.time(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
def _warm_ollama_model(model: str) -> None:
    settings = get_ollama_settings()
    if not settings.enabled:
        return
    client = OllamaClient(base_url=settings.base_url, model=model, timeout_s=12.0)
    if not client.is_running():
        return
    try:
        client.chat(system="回复OK即可。", user="OK", temperature=0.0)
    except Exception:
        return
@app.on_event("startup")
async def _startup_warm_models() -> None:
    """启动时预热模型，减少首次生成延迟"""
    model = os.environ.get("WRITING_AGENT_EXTRACT_MODEL", "").strip() or get_ollama_settings().model
    thread = threading.Thread(target=_warm_ollama_model, args=(model,), daemon=True)
    thread.start()
@app.get("/", response_class=HTMLResponse)
def root() -> RedirectResponse:
    session = store.create()
    _set_doc_text(session, "")
    # Defaults: graduation design / report settings (user can override in UI).
    session.formatting = {
        "font_name": "宋体",
        "font_name_east_asia": "宋体",
        "font_size_name": "小四",
        "font_size_pt": 12,
        "line_spacing": 28,
        "heading1_font_name": "黑体",
        "heading1_font_name_east_asia": "黑体",
        "heading1_size_pt": 22,
        "heading2_font_name": "黑体",
        "heading2_font_name_east_asia": "黑体",
        "heading2_size_pt": 16,
        "heading3_font_name": "黑体",
        "heading3_font_name_east_asia": "黑体",
        "heading3_size_pt": 16,
    }
    session.generation_prefs = {
        "purpose": "毕业设计/课程设计报告",
        "figure_types": ["flow", "er", "sequence", "bar", "line"],
        "table_types": ["summary", "metrics", "compare"],
        "include_cover": True,
        "include_toc": True,
        "toc_levels": 3,
        "page_numbers": True,
        "include_header": True,
        "header_text": "",
        "footer_text": "",
        "page_margins_cm": 2.8,
        "page_margin_top_cm": 3.7,
        "page_margin_bottom_cm": 3.5,
        "page_margin_left_cm": 2.8,
        "page_margin_right_cm": 2.6,
        "page_size": "A4",
        "expand_outline": False,
        "target_length_mode": "",
        "target_length_value": 0,
        "target_char_count": 0,
        "target_word_count": 0,
        "target_page_count": 0,
        "target_length_confirmed": False,
        "extra_requirements": "",
    }
    store.put(session)
    return RedirectResponse(url=f"/workbench/{session.id}", status_code=303)
@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)
@app.get("/workbench/{doc_id}", response_class=HTMLResponse)
def workbench_page(request: Request, doc_id: str) -> HTMLResponse:
    session = store.get(doc_id)
    if session is None:
        resp = templates.TemplateResponse(
            "v2_error2.html",
            {
                "request": request,
                "message": "文档不存在或已过期",
                "static_version": STATIC_VERSION,
                "perf_mode": PERF_MODE,
            },
        )
        resp.headers["Cache-Control"] = "no-store"
        return resp
    svelte_entry = os.path.join(os.path.dirname(__file__), "static", "v2_svelte", "main.js")
    use_svelte_raw = os.environ.get("WRITING_AGENT_USE_SVELTE", "1").strip().lower()
    use_svelte = use_svelte_raw not in {"0", "false", "no", "off"}
    template_name = "v2_workbench_svelte.html" if use_svelte and os.path.exists(svelte_entry) else "v2_workbench2.html"
    resp = templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "doc_id": doc_id,
            "static_version": STATIC_VERSION,
            "perf_mode": PERF_MODE,
        },
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp
@app.get("/api/doc/{doc_id}")
def api_get_doc(doc_id: str) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    _ensure_mcp_citations(session)
    store.put(session)
    meta = _load_meta(doc_id)
    return {
        "id": session.id,
        "text": _safe_doc_text(session),
        "doc_ir": session.doc_ir or {},
        "template_name": session.template_source_name or "",
        "required_h2": session.template_required_h2 or [],
        "template_outline": session.template_outline or [],
        "template_type": session.template_source_type or "",
        "formatting": session.formatting or {},
        "generation_prefs": session.generation_prefs or {},
        "chat_log": meta.get("chat", []),
        "thought_log": meta.get("thoughts", []),
    }
@app.get("/api/doc/{doc_id}/chat")
def api_get_chat(doc_id: str) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    meta = _load_meta(doc_id)
    return {"items": meta.get("chat", [])}
@app.post("/api/doc/{doc_id}/chat")
async def api_save_chat(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items must be list")
    cleaned: list[dict] = []
    for item in items[-200:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        text = str(item.get("text") or "").strip()
        if not role or not text:
            continue
        cleaned.append({"role": role, "text": text})
    session.chat_log = cleaned
    store.put(session)
    _save_meta(doc_id, chat=cleaned)
    return {"ok": 1}
@app.get("/api/doc/{doc_id}/thoughts")
def api_get_thoughts(doc_id: str) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    meta = _load_meta(doc_id)
    return {"items": meta.get("thoughts", [])}
@app.get("/api/text/{block_id}")
def api_get_text_block(block_id: str) -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    store_dir = data_dir / "text_store"
    block_id = str(block_id or "").strip()
    if not block_id:
        raise HTTPException(status_code=400, detail="block_id required")
    txt_path = store_dir / f"{block_id}.txt"
    json_path = store_dir / f"{block_id}.json"
    if txt_path.exists():
        return {"id": block_id, "format": "text", "kind": _guess_block_kind(block_id), "text": txt_path.read_text(encoding="utf-8")}
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        return {"id": block_id, "format": "json", "kind": _guess_block_kind(block_id), "data": payload}
    raise HTTPException(status_code=404, detail="block not found")
def _guess_block_kind(block_id: str) -> str:
    low = (block_id or "").lower()
    if low.startswith("t_"):
        return "table"
    if low.startswith("f_"):
        return "figure"
    if low.startswith("l_"):
        return "list"
    if low.startswith("p_"):
        return "paragraph"
    return "unknown"
@app.post("/api/doc/{doc_id}/thoughts")
async def api_save_thoughts(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items must be list")
    cleaned: list[dict] = []
    for item in items[-200:]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        detail = str(item.get("detail") or "").strip()
        time_str = str(item.get("time") or "").strip()
        if not label:
            continue
        cleaned.append({"label": label, "detail": detail, "time": time_str})
    session.thought_log = cleaned
    store.put(session)
    _save_meta(doc_id, thoughts=cleaned)
    return {"ok": 1}
def _normalize_citation_items(items: object) -> dict[str, Citation]:
    citations: dict[str, Citation] = {}
    if not isinstance(items, list):
        return citations
    for raw in items:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("id") or raw.get("key") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not key or not title:
            continue
        authors = str(raw.get("author") or raw.get("authors") or "").strip() or None
        year = str(raw.get("year") or "").strip() or None
        source = str(raw.get("source") or raw.get("venue") or "").strip() or None
        url = str(raw.get("url") or "").strip() or None
        if source and not url and re.match(r"^https?://", source):
            url = source
            source = None
        citations[key] = Citation(
            key=key,
            title=title,
            url=url,
            authors=authors,
            year=year,
            venue=source,
        )
    return citations
@app.get("/api/doc/{doc_id}/citations")
def api_get_citations(doc_id: str) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    items: list[dict] = []
    for key, cite in (session.citations or {}).items():
        items.append(
            {
                "id": key,
                "author": cite.authors or "",
                "title": cite.title or "",
                "year": cite.year or "",
                "source": cite.venue or cite.url or "",
            }
        )
    return {"items": items}
@app.post("/api/doc/{doc_id}/citations")
async def api_save_citations(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    items = data.get("items") if isinstance(data, dict) else None
    session.citations = _normalize_citation_items(items)
    store.put(session)
    return {"ok": 1, "count": len(session.citations or {})}
@app.post("/api/doc/{doc_id}/save")
async def api_save_doc(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    incoming_ir = data.get("doc_ir")
    saved_from_ir = False
    if isinstance(incoming_ir, dict) and incoming_ir.get("sections") is not None:
        try:
            session.doc_ir = incoming_ir
            text = doc_ir_to_text(doc_ir_from_dict(session.doc_ir))
            saved_from_ir = True
        except Exception:
            text = str(data.get("text") or "")
    else:
        text = str(data.get("text") or "")
    incoming = text.strip()
    existing = (session.doc_text or "").strip()
    # Prevent overwriting rich content with a near-empty title-only draft.
    if existing and (len(existing) > len(incoming)) and (not re.search(r"(?m)^##\\s+.+$", incoming)) and re.search(r"(?m)^##\\s+.+$", existing):
        text = session.doc_text
    if saved_from_ir:
        session.doc_text = text
    else:
        _set_doc_text(session, text)
    if isinstance(data.get("formatting"), dict):
        session.formatting = data.get("formatting") or {}
    if isinstance(data.get("generation_prefs"), dict):
        session.generation_prefs = data.get("generation_prefs") or {}
    store.put(session)
    return {"ok": 1}
@app.post("/api/doc/{doc_id}/import")
async def api_import_doc(doc_id: str, file: UploadFile = File(...)) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="document not found")
    if file is None or not (file.filename or "").strip():
        raise HTTPException(status_code=400, detail="file required")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large (max 50MB)")
    temp_dir = DATA_DIR / "imports"
    temp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix.lower() or ".txt"
    tmp_path = temp_dir / f"{doc_id}_{uuid.uuid4().hex}{suffix}"
    tmp_path.write_bytes(raw)
    try:
        text = _try_rust_import(tmp_path) or _extract_text(tmp_path)
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty document")
    _set_doc_text(session, text)
    store.put(session)
    return {"ok": 1, "text": text}
@app.post("/api/doc/{doc_id}/settings")
async def api_save_settings(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    if isinstance(data.get("formatting"), dict):
        session.formatting = data.get("formatting") or {}
    if isinstance(data.get("generation_prefs"), dict):
        session.generation_prefs = data.get("generation_prefs") or {}
    store.put(session)
    return {"ok": 1}
@app.post("/api/doc/{doc_id}/analyze")
async def api_analyze_message(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    text = str(data.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    analysis = _run_message_analysis(
        session,
        text,
        force=bool(data.get("force")),
        quick=bool(data.get("quick")) or str(data.get("mode") or "").lower() == "quick",
    )
    return {"ok": 1, "analysis": analysis}
@app.post("/api/doc/{doc_id}/extract_prefs")
async def api_extract_prefs(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在或已过期")
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    text = str(data.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    settings = get_ollama_settings()
    if not settings.enabled:
        raise HTTPException(status_code=400, detail="未启用Ollama")
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise HTTPException(status_code=400, detail="Ollama 未运行")
    model = os.environ.get("WRITING_AGENT_EXTRACT_MODEL", "").strip() or settings.model
    quick_extract = os.environ.get("WRITING_AGENT_EXTRACT_QUICK", "").strip() != "0"
    analysis = _run_message_analysis(session, text, quick=False)
    analysis_text = _compose_analysis_input(text, analysis)
    extract_timeout = _extract_timeout_s()
    parsed = _fast_extract_prefs(text)
    refined = {}
    has_fast = bool(parsed)
    force_ai = os.environ.get("WRITING_AGENT_EXTRACT_FAST_ONLY", "").strip() == "0"
    if force_ai:
        try:
            ai_parsed = _extract_prefs_with_model(
                base_url=settings.base_url,
                model=model,
                text=analysis_text,
                timeout_s=extract_timeout,
            )
            if isinstance(ai_parsed, dict):
                parsed.update(ai_parsed)
            if os.environ.get("WRITING_AGENT_EXTRACT_REFINE", "").strip() == "1":
                refined = _extract_prefs_refine_with_model(
                    base_url=settings.base_url,
                    model=model,
                    text=analysis_text,
                    initial=parsed or {},
                    timeout_s=extract_timeout,
                )
        except Exception:
            if not has_fast:
                parsed = {}
            refined = {}
    merged: dict = {}
    if isinstance(parsed, dict):
        merged.update(parsed)
    if isinstance(refined, dict):
        merged.update(refined)
    fmt = _normalize_ai_formatting(merged.get("formatting") if isinstance(merged, dict) else None)
    prefs = _normalize_ai_prefs(merged.get("generation_prefs") if isinstance(merged, dict) else None)
    prefs = _infer_role_defaults(text, prefs, analysis)
    title = str(merged.get("title") or "").strip() if isinstance(merged, dict) else ""
    questions = [str(x).strip() for x in (merged.get("questions") or []) if str(x).strip()] if isinstance(merged, dict) else []
    if text and questions:
        questions = [q for q in questions if not re.search(r"(输入|内容).{0,6}为空", q)]
    summary = str(merged.get("summary") or "").strip() if isinstance(merged, dict) else ""
    auto_summary = _build_pref_summary(text, analysis, title, fmt, prefs)
    history = _analysis_history_context(session)
    dynamic = {}
    if settings.enabled and client.is_running():
        dynamic = _generate_dynamic_questions_with_model(
            base_url=settings.base_url,
            model=_analysis_model_name(settings),
            raw=text,
            analysis=analysis,
            history=history,
            merged={"title": title, "formatting": fmt, "generation_prefs": prefs, "summary": summary},
        )
    dyn_summary = str(dynamic.get("summary") or "").strip() if isinstance(dynamic, dict) else ""
    if dyn_summary:
        summary = dyn_summary
    elif (not summary or re.search(r"(\u5df2\u8bc6\u522b|\u672a\u63d0\u4f9b|\u4e0d\u8db3|\u7f3a\u5931|\u4e0d\u660e\u786e|\u4e0d\u5b8c\u6574)", summary)):
        summary = auto_summary or summary
    dyn_qs = dynamic.get("questions") if isinstance(dynamic, dict) else None
    if isinstance(dyn_qs, list):
        questions = [str(x).strip() for x in dyn_qs if str(x).strip()]
    # rules only as boundaries / fallback
    if not questions:
        questions = _build_missing_questions(title, fmt, prefs, analysis)
    conflicts = _detect_extract_conflicts(analysis=analysis, title=title, prefs=prefs)
    if conflicts:
        questions = conflicts + questions
    multi = _detect_multi_intent(text)
    if multi:
        questions = multi + questions
    conf = _field_confidence(text, analysis, title, prefs, fmt)
    low_conf = _low_conf_questions(conf)
    if low_conf:
        questions = low_conf + questions
    # adaptive limit only
    score = _info_score(title, fmt, prefs, analysis)
    max_q = 3
    if score >= 5:
        max_q = 1
    elif score >= 3:
        max_q = 2
    if len(questions) > max_q:
        questions = questions[:max_q]
    target_chars = _resolve_target_chars(fmt, prefs)
    if target_chars <= 0:
        has_length_q = any(re.search(r"(\u5b57\u6570|\u9875\u6570|\u9875\u7801|\u7bc7\u5e45|\u957f\u5ea6)", q) for q in questions)
        if not has_length_q:
            questions.append("\u8bf7\u544a\u77e5\u76ee\u6807\u5b57\u6570\u6216\u9875\u6570\uff08\u4efb\u9009\u5176\u4e00\uff09\u3002")
    resp = {
        "ok": 1,
        "title": title,
        "formatting": fmt,
        "generation_prefs": prefs,
        "questions": questions,
        "summary": summary,
    }
    if os.environ.get("WRITING_AGENT_EXTRACT_DEBUG", "").strip() == "1":
        resp["debug_text"] = text
        resp["debug_fast"] = parsed
    return resp
@app.post("/api/doc/{doc_id}/template")
async def api_upload_template(doc_id: str, file: UploadFile = File(...)) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if file is None or not (file.filename or "").strip():
        raise HTTPException(status_code=400, detail="file required")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large (max 50MB)")
    USER_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    tid = uuid.uuid4().hex
    suffix = Path(file.filename).suffix.lower() or ".bin"
    path = (USER_TEMPLATES_DIR / f"{doc_id}_{tid}{suffix}")
    path.write_bytes(raw)
    resolved = prepare_template_file(path)
    text = _extract_text(resolved)
    settings = get_ollama_settings()
    if not settings.enabled:
        raise HTTPException(status_code=400, detail="未启用Ollama")
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise HTTPException(status_code=400, detail="Ollama 未运行")
    first = _extract_template_with_model(
        base_url=settings.base_url,
        model=settings.model,
        filename=file.filename,
        text=text,
    )
    refined = _extract_template_refine_with_model(
        base_url=settings.base_url,
        model=settings.model,
        filename=file.filename,
        text=text,
        initial=first or {},
    )
    info: dict = {}
    if isinstance(first, dict):
        info.update(first)
    if isinstance(refined, dict):
        info.update(refined)
    parsed = parse_template_file(Path(resolved), Path(file.filename).stem)
    if parsed.outline:
        info["outline"] = list(parsed.outline)
        info["required_h2"] = list(parsed.required_h2)
        if not info.get("name"):
            info["name"] = parsed.name
    session.template_source_name = str(info.get("name") or Path(file.filename).stem)
    session.template_required_h2 = list(info.get("required_h2") or [])
    session.template_outline = list(info.get("outline") or [])
    session.template_source_path = str(resolved)
    session.template_source_type = resolved.suffix.lower()
    store.put(session)
    questions = [str(x).strip() for x in (info.get("questions") or []) if str(x).strip()] if isinstance(info, dict) else []
    if not session.template_outline and not questions:
        questions = ["未能识别模板章节结构，请粘贴或描述章节与层级。"]
    return {
        "ok": 1,
        "template_name": session.template_source_name,
        "required_h2": session.template_required_h2,
        "template_outline": session.template_outline or [],
        "questions": questions,
    }
@app.post("/api/doc/{doc_id}/template/clear")
async def api_clear_template(doc_id: str) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="æ–‡æ¡£ä¸å­˜åœ¨æˆ–å·²è¿‡æœ?")
    session.template_source_name = ""
    session.template_required_h2 = []
    session.template_outline = []
    session.template_source_path = ""
    session.template_source_type = ""
    store.put(session)
    return {"ok": 1}
@app.post("/api/doc/{doc_id}/upload")
async def api_doc_upload(doc_id: str, file: UploadFile = File(...)) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在或已过期")
    if file is None or not (file.filename or "").strip():
        raise HTTPException(status_code=400, detail="file required")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large (max 50MB)")
    rec = user_library.put_upload(filename=file.filename, file_bytes=raw)
    kind = "library"
    info = None
    resolved_path = ""
    try:
        src_path = Path(rec.source_path)
        suffix = src_path.suffix.lower()
        text = user_library.get_text(rec.doc_id)
        ai_kind = "unknown"
        ai_conf = 0.0
        settings = get_ollama_settings()
        running = False
        if settings.enabled:
            client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
            running = client.is_running()
            if running:
                result = _classify_upload_with_model(
                    base_url=settings.base_url,
                    model=settings.model,
                    filename=file.filename,
                    text=text,
                )
                ai_kind = str(result.get("kind") or "unknown")
                try:
                    ai_conf = float(result.get("confidence") or 0.0)
                except Exception:
                    ai_conf = 0.0
        if ai_kind == "template" and suffix in {".doc", ".docx", ".txt", ".md", ".html", ".htm"}:
            resolved = prepare_template_file(src_path)
            if resolved.suffix.lower() != ".doc":
                resolved_path = str(resolved)
                first = _extract_template_with_model(
                    base_url=settings.base_url,
                    model=settings.model,
                    filename=file.filename,
                    text=text,
                )
                refined = _extract_template_refine_with_model(
                    base_url=settings.base_url,
                    model=settings.model,
                    filename=file.filename,
                    text=text,
                    initial=first or {},
                )
                info = {}
                if isinstance(first, dict):
                    info.update(first)
                if isinstance(refined, dict):
                    info.update(refined)
                kind = "template"
        elif suffix in {".doc", ".docx", ".txt", ".md", ".html", ".htm"} and running and ai_kind in {"unknown", "other", ""}:
            resolved = prepare_template_file(src_path)
            if resolved.suffix.lower() != ".doc":
                resolved_path = str(resolved)
                quick = _extract_template_titles_with_model(
                    base_url=settings.base_url,
                    model=settings.model,
                    filename=file.filename,
                    text=text,
                )
                titles = _normalize_string_list(quick.get("titles"), ("title", "text", "name"))
                questions = _normalize_string_list(quick.get("questions"), ("question", "text", "q"))
                if len(titles) >= 3:
                    kind = "template"
                    info = {
                        "name": Path(file.filename).stem,
                        "outline": [(1, t) for t in titles],
                        "required_h2": [],
                        "questions": questions,
                    }
                else:
                    info = None
                    kind = "library"
        elif ai_kind in {"reference", "other"}:
            kind = "library"
        else:
            kind = "library"
        if kind == "template" and info is not None and resolved_path:
            parsed = parse_template_file(Path(resolved_path), Path(file.filename).stem)
            if parsed.outline:
                info["outline"] = list(parsed.outline)
                info["required_h2"] = list(parsed.required_h2)
                if not info.get("name"):
                    info["name"] = parsed.name
        if kind == "template" and info is not None:
            session.template_source_name = str(info.get("name") or Path(file.filename).stem)
            session.template_required_h2 = list(info.get("required_h2") or [])
            session.template_outline = list(info.get("outline") or [])
            session.template_source_path = resolved_path
            session.template_source_type = Path(resolved_path).suffix.lower() if resolved_path else ""
            store.put(session)
    except Exception:
        info = None
    questions = []
    if isinstance(info, dict):
        questions = [str(x).strip() for x in (info.get("questions") or []) if str(x).strip()]
        if kind == "template" and not info.get("outline") and not questions:
            questions = ["未能识别模板章节结构，请粘贴或描述章节与层级。"]
    payload = {"ok": 1, "kind": kind, "item": _library_item_payload(rec), "questions": questions}
    if kind == "template" and info is not None:
        payload.update(
            {
                "template_name": str(info.get("name") or ""),
                "required_h2": list(info.get("required_h2") or []),
                "template_outline": list(info.get("outline") or []),
            }
        )
    return payload
@app.post("/api/doc/{doc_id}/upload/clarify")
async def api_doc_upload_clarify(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在或已过期")
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    text = str(data.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    template_path = str(session.template_source_path or "").strip()
    if not template_path:
        raise HTTPException(status_code=400, detail="未找到可复核的模板")
    path = Path(template_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="模板文件不存在")
    settings = get_ollama_settings()
    if not settings.enabled:
        raise HTTPException(status_code=400, detail="未启用Ollama")
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise HTTPException(status_code=400, detail="Ollama 未运行")
    raw_text = _extract_text(path)
    combined = (raw_text + "\n\n补充说明：\n" + text).strip()
    first = _extract_template_with_model(
        base_url=settings.base_url,
        model=settings.model,
        filename=path.name,
        text=combined,
    )
    refined = _extract_template_refine_with_model(
        base_url=settings.base_url,
        model=settings.model,
        filename=path.name,
        text=combined,
        initial=first or {},
    )
    info: dict = {}
    if isinstance(first, dict):
        info.update(first)
    if isinstance(refined, dict):
        info.update(refined)
    parsed = parse_template_file(path, Path(path.name).stem)
    if parsed.outline:
        info["outline"] = list(parsed.outline)
        info["required_h2"] = list(parsed.required_h2)
        if not info.get("name"):
            info["name"] = parsed.name
    session.template_source_name = str(info.get("name") or session.template_source_name or Path(path.name).stem)
    new_required = list(info.get("required_h2") or [])
    new_outline = list(info.get("outline") or [])
    if not new_outline and session.template_outline:
        new_outline = list(session.template_outline or [])
    if not new_required and session.template_required_h2:
        new_required = list(session.template_required_h2 or [])
    session.template_required_h2 = new_required
    session.template_outline = new_outline
    store.put(session)
    questions = [str(x).strip() for x in (info.get("questions") or []) if str(x).strip()] if isinstance(info, dict) else []
    if not session.template_outline and not questions:
        questions = ["未能识别模板章节结构，请粘贴或描述章节与层级。"]
    return {
        "ok": 1,
        "template_name": session.template_source_name,
        "required_h2": session.template_required_h2,
        "template_outline": session.template_outline or [],
        "questions": questions,
    }
@app.post("/api/doc/{doc_id}/generate/stream")
async def api_generate_stream(doc_id: str, request: Request) -> StreamingResponse:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="document not found")
    data = await request.json()
    raw_instruction = str(data.get("instruction") or "").strip()
    current_text = str(data.get("text") or "")
    selection = str(data.get("selection") or "")
    if not raw_instruction:
        raise HTTPException(status_code=400, detail="instruction required")
    def emit(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    def iter_events():
        yield emit("delta", {"delta": "model preparing..."})
        prep_queue: queue.Queue[str] = queue.Queue()
        result: dict[str, object] = {"ok": True, "msg": ""}
        def _prep_worker() -> None:
            nonlocal result
            try:
                ready_iter = _ensure_ollama_ready_iter()
                if isinstance(ready_iter, tuple):
                    ok, msg = ready_iter
                    result = {"ok": ok, "msg": msg}
                    return
                for note in ready_iter:
                    if note:
                        prep_queue.put(str(note))
                result = {"ok": True, "msg": ""}
            except Exception as e:
                result = {"ok": False, "msg": str(e)}
        prep_thread = threading.Thread(target=_prep_worker, daemon=True)
        prep_thread.start()
        last_emit = time.time()
        while prep_thread.is_alive() or not prep_queue.empty():
            try:
                note = prep_queue.get(timeout=1.0)
                if note:
                    yield emit("delta", {"delta": note})
                    last_emit = time.time()
            except queue.Empty:
                if time.time() - last_emit > 3:
                    yield emit("delta", {"delta": "model preparing..."})
                    last_emit = time.time()
        ok = bool(result.get("ok"))
        msg = str(result.get("msg") or "")
        if not ok:
            yield emit("error", {"message": msg or "模型准备失败"})
            return
        prefs = session.generation_prefs or {}
        fmt = session.formatting or {}
        target_chars = _resolve_target_chars(fmt, prefs)
        if target_chars <= 0:
            target_chars = _extract_target_chars_from_instruction(raw_instruction)
        base_text = current_text or session.doc_text or ""
        if base_text.strip():
            if base_text != session.doc_text:
                _set_doc_text(session, base_text)
            _auto_commit_version(session, "auto: before update")
        quick_edit = _try_quick_edit(base_text, raw_instruction)
        if quick_edit:
            updated_text, note = quick_edit
            updated_text = _postprocess_output_text(
                session,
                updated_text,
                raw_instruction,
                current_text=base_text,
                base_text=base_text,
            )
            _set_doc_text(session, updated_text)
            _auto_commit_version(session, "auto: after update")
            store.put(session)
            yield emit("delta", {"delta": note})
            yield emit("final", {"text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)})
            return
        analysis_quick = _run_message_analysis(session, raw_instruction, quick=True)
        ai_edit = _try_ai_intent_edit(base_text, raw_instruction, analysis_quick)
        if ai_edit:
            updated_text, note = ai_edit
            updated_text = _postprocess_output_text(
                session,
                updated_text,
                raw_instruction,
                current_text=base_text,
                base_text=base_text,
            )
            _set_doc_text(session, updated_text)
            _auto_commit_version(session, "auto: after update")
            store.put(session)
            yield emit("delta", {"delta": note})
            yield emit("final", {"text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)})
            return
        if _should_route_to_revision(raw_instruction, base_text, analysis_quick):
            summary = "检测到修改指令，进入快速修订流程"
            yield emit("analysis", {"summary": summary, "steps": ["定位修改目标", "执行改写", "校对结构"], "missing": []})
            revised = _try_revision_edit(
                session=session,
                instruction=raw_instruction,
                text=base_text,
                selection=selection,
                analysis=analysis_quick,
            )
            if revised:
                updated_text, note = revised
                updated_text = _postprocess_output_text(
                    session,
                    updated_text,
                    raw_instruction,
                    current_text=base_text,
                    base_text=base_text,
                )
                _set_doc_text(session, updated_text)
                _auto_commit_version(session, "auto: after update")
                store.put(session)
                yield emit("delta", {"delta": note})
                yield emit("final", {"text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)})
                return
            yield emit("delta", {"delta": "快速修订未成功，转入完整生成…"})
        if _should_use_fast_generate(raw_instruction, target_chars, session.generation_prefs or {}):
            fast_done = False
            try:
                instruction = _augment_instruction(
                    raw_instruction,
                    formatting=session.formatting or {},
                    generation_prefs=session.generation_prefs or {},
                )
                # Use streaming version with heartbeat for better UX
                final_text = ""
                saw_stream_delta = False
                for event in _single_pass_generate_stream(
                    session,
                    instruction=instruction,
                    current_text=current_text,
                    target_chars=target_chars,
                ):
                    if event.get("event") == "heartbeat":
                        yield emit("delta", {"delta": event.get("message", "")})
                    elif event.get("event") == "section":
                        saw_stream_delta = True
                        yield emit("section", event)
                    elif event.get("event") == "result":
                        final_text = event.get("text", "")
                if final_text:
                    final_text = _postprocess_output_text(
                        session,
                        final_text,
                        raw_instruction,
                        current_text=current_text,
                    )
                    if not _looks_like_prompt_echo(final_text, raw_instruction):
                        # Check generation quality
                        quality_issues = _check_generation_quality(final_text, target_chars)
                        if not saw_stream_delta:
                            yield emit("section", {"section": "fast", "phase": "delta", "delta": final_text})
                        yield emit(
                            "final",
                            {"text": final_text, "problems": quality_issues, "doc_ir": _safe_doc_ir_payload(final_text)},
                        )
                        _set_doc_text(session, final_text)
                        _auto_commit_version(session, "auto: after update")
                        store.put(session)
                        fast_done = True
                    else:
                        yield emit("delta", {"delta": "快速生成结果异常，转入完整生成…"})
            except Exception:
                yield emit("delta", {"delta": "快速生成失败，转入完整生成…"})
            if fast_done:
                return
        analysis_timeout = float(os.environ.get("WRITING_AGENT_ANALYSIS_MAX_S", "20"))
        analysis_iter = _run_with_heartbeat(
            lambda: _run_message_analysis(session, raw_instruction),
            analysis_timeout,
            _normalize_analysis({}, raw_instruction),
            label="解析中",
        )
        if isinstance(analysis_iter, tuple):
            analysis = analysis_iter
        else:
            analysis = None
            try:
                while True:
                    note = next(analysis_iter)
                    if note:
                        yield emit("delta", {"delta": str(note)})
            except StopIteration as e:
                analysis = e.value
        if analysis is None:
            analysis = _normalize_analysis({}, raw_instruction)
        analysis_instruction = _compose_analysis_input(raw_instruction, analysis)
        instruction = _augment_instruction(
            analysis_instruction,
            formatting=session.formatting or {},
            generation_prefs=session.generation_prefs or {},
        )
        # auto-outline for common doc types when没有模板/必选H2
        if not session.template_required_h2 and not session.template_outline:
            auto_outline = _default_outline_from_instruction(raw_instruction)
            if auto_outline:
                session.template_required_h2 = auto_outline
                store.put(session)
        summary = _summarize_analysis(raw_instruction, analysis)
        if isinstance(summary, dict):
            summary["raw"] = analysis
        yield emit("analysis", summary)
        prefs = session.generation_prefs or {}
        fmt = session.formatting or {}
        target_chars = _resolve_target_chars(fmt, prefs)
        if target_chars <= 0:
            target_chars = _extract_target_chars_from_instruction(raw_instruction)
        if target_chars > 0:
            raw_margin = os.environ.get("WRITING_AGENT_TARGET_MARGIN", "").strip()
            try:
                margin = float(raw_margin) if raw_margin else 0.15
            except Exception:
                margin = 0.15
            margin = max(0.0, min(0.3, margin))
            internal_target = int(round(target_chars * (1.0 + margin)))
            cfg = GenerateConfig(
                workers=int(os.environ.get("WRITING_AGENT_WORKERS", "12")),  # 优化: 10->12充分利用12核
                min_total_chars=internal_target,
                max_total_chars=internal_target,
            )
        else:
            cfg = GenerateConfig(
                workers=int(os.environ.get("WRITING_AGENT_WORKERS", "12")),  # 优化: 10->12充分利用12核
            )
        final_text: str | None = None
        problems: list[str] = []
        overall_default_s, stall_default_s = _recommended_stream_timeouts()
        stall_s = float(os.environ.get("WRITING_AGENT_STREAM_EVENT_TIMEOUT_S", str(int(stall_default_s))))
        stall_s = max(stall_s, stall_default_s)
        overall_s = float(os.environ.get("WRITING_AGENT_STREAM_MAX_S", str(int(overall_default_s))))
        overall_s = max(overall_s, overall_default_s)
        section_raw = os.environ.get("WRITING_AGENT_STREAM_SECTION_TIMEOUT_S", "").strip()
        section_stall_s = float(section_raw) if section_raw else 0.0
        if section_stall_s > 0 and section_stall_s < stall_s:
            section_stall_s = stall_s
        start_ts = time.time()
        max_gap_s = 0.0
        try:
            expand_outline = bool((session.generation_prefs or {}).get("expand_outline", False))
            gen = run_generate_graph(
                instruction=instruction,
                current_text=current_text,
                required_h2=list(session.template_required_h2 or []),
                required_outline=list(session.template_outline or []),
                expand_outline=expand_outline,
                config=cfg,
            )
            last_section_at: float | None = None
            last_event_at = start_ts
            for ev in _iter_with_timeout(gen, per_event=stall_s, overall=overall_s):
                now = time.time()
                gap = now - last_event_at
                if gap > max_gap_s:
                    max_gap_s = gap
                last_event_at = now
                if ev.get("event") == "final":
                    final_text = _postprocess_output_text(
                        session,
                        str(ev.get("text") or ""),
                        raw_instruction,
                        current_text=current_text,
                    )
                    problems = list(ev.get("problems") or [])
                    payload = dict(ev)
                    payload["text"] = final_text
                    payload["doc_ir"] = _safe_doc_ir_payload(final_text)
                    yield emit(payload.get("event", "message"), payload)
                    _record_stream_timing(total_s=time.time() - start_ts, max_gap_s=max_gap_s)
                    break
                yield emit(ev.get("event", "message"), ev)
                if ev.get("event") == "section" and ev.get("phase") == "delta":
                    last_section_at = time.time()
                if section_stall_s > 0:
                    if last_section_at is not None and time.time() - last_section_at > section_stall_s:
                        raise TimeoutError("section stalled")
        except Exception as e:
            try:
                log_path = Path(".data/logs/graph_error.log")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} graph_error: {e}\n{traceback.format_exc()}\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            # fallback to single-pass generation if streaming pipeline stalls
            try:
                # Use streaming version with heartbeat
                final_text = None
                saw_stream_delta = False
                for event in _single_pass_generate_stream(
                    session,
                    instruction=instruction,
                    current_text=current_text,
                    target_chars=target_chars,
                ):
                    if event.get("event") == "heartbeat":
                        yield emit("delta", {"delta": event.get("message", "")})
                    elif event.get("event") == "section":
                        saw_stream_delta = True
                        yield emit("section", event)
                    elif event.get("event") == "result":
                        final_text = event.get("text", "")
                if final_text:
                    final_text = _postprocess_output_text(
                        session,
                        final_text,
                        raw_instruction,
                        current_text=current_text,
                    )
                    # Check generation quality
                    quality_issues = _check_generation_quality(final_text, target_chars)
                    if not saw_stream_delta:
                        yield emit("section", {"section": "fallback", "phase": "delta", "delta": final_text})
                    yield emit(
                        "final",
                        {"text": final_text, "problems": quality_issues, "doc_ir": _safe_doc_ir_payload(final_text)},
                    )
                    _record_stream_timing(total_s=time.time() - start_ts, max_gap_s=max_gap_s)
            except Exception as ee:
                yield emit("error", {"message": f"generation failed: {e}; fallback failed: {ee}"})
        if final_text is None or len(final_text.strip()) < 20:
            # 兜底：单轮生成，避免空结果/过度超时
            try:
                final_text = None
                saw_stream_delta = False
                for event in _single_pass_generate_stream(
                    session,
                    instruction=instruction,
                    current_text=current_text,
                    target_chars=target_chars,
                ):
                    if event.get("event") == "heartbeat":
                        yield emit("delta", {"delta": event.get("message", "")})
                    elif event.get("event") == "section":
                        saw_stream_delta = True
                        yield emit("section", event)
                    elif event.get("event") == "result":
                        final_text = event.get("text", "")
                if final_text:
                    final_text = _postprocess_output_text(
                        session,
                        final_text,
                        raw_instruction,
                        current_text=current_text,
                    )
                    # Check generation quality
                    quality_issues = _check_generation_quality(final_text, target_chars)
                    if not saw_stream_delta:
                        yield emit(
                            "section",
                            {"section": "fallback", "phase": "delta", "delta": final_text},
                        )
                    yield emit(
                        "final",
                        {"text": final_text, "problems": quality_issues, "doc_ir": _safe_doc_ir_payload(final_text)},
                    )
                    _record_stream_timing(total_s=time.time() - start_ts, max_gap_s=max_gap_s)
            except Exception as e:
                yield emit("error", {"message": f"生成失败：未得到正文且兜底失败：{e}"})
                return
        # 持久化最终文稿，刷新后不丢失
        if final_text is not None:
            _set_doc_text(session, final_text)
            _auto_commit_version(session, "auto: after update")
            store.put(session)
    return StreamingResponse(
        iter_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
@app.post("/api/doc/{doc_id}/generate")
async def api_generate(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    raw_instruction = str(data.get("instruction") or "").strip()
    current_text = str(data.get("text") or "")
    selection = str(data.get("selection") or "")
    if not raw_instruction:
        raise HTTPException(status_code=400, detail="instruction 不能为空")
    ok, msg = _ensure_ollama_ready()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    prefs = session.generation_prefs or {}
    fmt = session.formatting or {}
    target_chars = _resolve_target_chars(fmt, prefs)
    if target_chars <= 0:
        target_chars = _extract_target_chars_from_instruction(raw_instruction)
    base_text = current_text or session.doc_text or ""
    if base_text.strip():
        if base_text != session.doc_text:
            _set_doc_text(session, base_text)
        _auto_commit_version(session, "auto: before update")
    quick_edit = _try_quick_edit(base_text, raw_instruction)
    if quick_edit:
        updated_text, _ = quick_edit
        updated_text = _postprocess_output_text(
            session,
            updated_text,
            raw_instruction,
            current_text=base_text,
            base_text=base_text,
        )
        _set_doc_text(session, updated_text)
        _auto_commit_version(session, "auto: after update")
        store.put(session)
        return {"ok": 1, "text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)}
    analysis_quick = _run_message_analysis(session, raw_instruction, quick=True)
    ai_edit = _try_ai_intent_edit(base_text, raw_instruction, analysis_quick)
    if ai_edit:
        updated_text, note = ai_edit
        updated_text = _postprocess_output_text(
            session,
            updated_text,
            raw_instruction,
            current_text=base_text,
            base_text=base_text,
        )
        _set_doc_text(session, updated_text)
        _auto_commit_version(session, "auto: after update")
        store.put(session)
        return {"ok": 1, "text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text), "note": note}
    if _should_route_to_revision(raw_instruction, base_text, analysis_quick):
        revised = _try_revision_edit(
            session=session,
            instruction=raw_instruction,
            text=base_text,
            selection=selection,
            analysis=analysis_quick,
        )
        if revised:
            updated_text, _ = revised
            updated_text = _postprocess_output_text(
                session,
                updated_text,
                raw_instruction,
            current_text=base_text,
            base_text=base_text,
        )
        _set_doc_text(session, updated_text)
        _auto_commit_version(session, "auto: after update")
        store.put(session)
        return {"ok": 1, "text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)}
    if _should_use_fast_generate(raw_instruction, target_chars, session.generation_prefs or {}):
        try:
            instruction = _augment_instruction(
                raw_instruction,
                formatting=session.formatting or {},
                generation_prefs=session.generation_prefs or {},
            )
            final_text = _single_pass_generate(
                session,
                instruction=instruction,
                current_text=current_text,
                target_chars=target_chars,
            )
            final_text = _postprocess_output_text(
                session,
                final_text,
                raw_instruction,
                current_text=current_text,
            )
            if final_text and not _looks_like_prompt_echo(final_text, raw_instruction):
                _set_doc_text(session, final_text)
                _auto_commit_version(session, "auto: after update")
                store.put(session)
                return {"ok": 1, "text": final_text, "problems": [], "doc_ir": _safe_doc_ir_payload(final_text)}
        except Exception:
            pass
    analysis_timeout = float(os.environ.get("WRITING_AGENT_ANALYSIS_MAX_S", "20"))
    analysis = _run_with_timeout(
        lambda: _run_message_analysis(session, raw_instruction),
        analysis_timeout,
        _normalize_analysis({}, raw_instruction),
    )
    analysis_instruction = _compose_analysis_input(raw_instruction, analysis)
    instruction = _augment_instruction(
        analysis_instruction,
        formatting=session.formatting or {},
        generation_prefs=session.generation_prefs or {},
    )
    if not session.template_required_h2 and not session.template_outline:
        auto_outline = _default_outline_from_instruction(raw_instruction)
        if auto_outline:
            session.template_required_h2 = auto_outline
            store.put(session)
    prefs = session.generation_prefs or {}
    fmt = session.formatting or {}
    target_chars = _resolve_target_chars(fmt, prefs)
    if target_chars <= 0:
        target_chars = _extract_target_chars_from_instruction(raw_instruction)
    if target_chars > 0:
        raw_margin = os.environ.get("WRITING_AGENT_TARGET_MARGIN", "").strip()
        try:
            margin = float(raw_margin) if raw_margin else 0.15
        except Exception:
            margin = 0.15
        margin = max(0.0, min(0.3, margin))
        internal_target = int(round(target_chars * (1.0 + margin)))
        cfg = GenerateConfig(
            workers=int(os.environ.get("WRITING_AGENT_WORKERS", "12")),  # 优化: 10->12充分利用12核
            min_total_chars=internal_target,
            max_total_chars=internal_target,
        )
    else:
        cfg = GenerateConfig(
            workers=int(os.environ.get("WRITING_AGENT_WORKERS", "12")),  # 优化: 10->12充分利用12核
        )
    final_text: str | None = None
    problems: list[str] = []
    try:
        expand_outline = bool((session.generation_prefs or {}).get("expand_outline", False))
        gen = run_generate_graph(
            instruction=instruction,
            current_text=current_text,
            required_h2=list(session.template_required_h2 or []),
            required_outline=list(session.template_outline or []),
            expand_outline=expand_outline,
            config=cfg,
        )
        stall_s = float(os.environ.get("WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S", os.environ.get("WRITING_AGENT_STREAM_EVENT_TIMEOUT_S", "90")))
        overall_s = float(os.environ.get("WRITING_AGENT_NONSTREAM_MAX_S", os.environ.get("WRITING_AGENT_STREAM_MAX_S", "180")))
        for ev in _iter_with_timeout(gen, per_event=stall_s, overall=overall_s):
            if ev.get("event") == "final":
                final_text = str(ev.get("text") or "")
                problems = list(ev.get("problems") or [])
                break
    except Exception as e:
        # fallback to单轮生成以保证有内容
        try:
            final_text = _single_pass_generate(session, instruction=instruction, current_text=current_text, target_chars=target_chars)
        except Exception as ee:
            raise HTTPException(status_code=500, detail=f"生成失败：{e}; 兜底失败：{ee}") from ee
    if not final_text or len(str(final_text).strip()) < 20:
        try:
            final_text = _single_pass_generate(session, instruction=instruction, current_text=current_text, target_chars=target_chars)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成失败：未得到结果且兜底失败：{e}") from e
    final_text = _postprocess_output_text(
        session,
        final_text,
        raw_instruction,
        current_text=current_text,
    )
    _set_doc_text(session, final_text)
    _auto_commit_version(session, "auto: after update")
    store.put(session)
    return {"ok": 1, "text": final_text, "problems": problems, "doc_ir": _safe_doc_ir_payload(final_text)}
@app.post("/api/doc/{doc_id}/generate/section")
async def api_generate_section(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="???????")
    data = await request.json()
    section = str(data.get("section") or "").strip()
    if not section:
        raise HTTPException(status_code=400, detail="section ????")
    instruction = str(data.get("instruction") or "").strip() or (session.last_instruction or "")
    current_text = session.text or ""
    cfg = GenerateConfig(workers=1, min_total_chars=0, max_total_chars=0)
    final_text: str | None = None
    try:
        gen = run_generate_graph(
            instruction=instruction,
            current_text=current_text,
            required_h2=[section],
            required_outline=[],
            expand_outline=False,
            config=cfg,
        )
        for ev in gen:
            if ev.get("event") == "final":
                final_text = str(ev.get("text") or "")
                break
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"section generation failed: {e}")
    if not final_text:
        raise HTTPException(status_code=500, detail="section generation produced no text")
    try:
        from writing_agent.v2.graph_runner import _apply_section_updates  # type: ignore
        updated = _apply_section_updates(current_text, final_text, [section])
    except Exception:
        updated = final_text
    session.text = updated
    store.put(session)
    return {"ok": 1, "text": updated}
@app.post("/api/doc/{doc_id}/revise")
async def api_revise_doc(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    instruction = str(data.get("instruction") or "").strip()
    selection = str(data.get("selection") or "").strip()
    incoming_ir = data.get("doc_ir")
    if isinstance(incoming_ir, dict) and incoming_ir.get("sections") is not None:
        try:
            session.doc_ir = incoming_ir
            text = doc_ir_to_text(doc_ir_from_dict(session.doc_ir))
        except Exception:
            text = str(data.get("text") or session.doc_text or "")
    else:
        text = str(data.get("text") or session.doc_text or "")
    base_text = text
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction 不能为空")
    if not text.strip():
        raise HTTPException(status_code=400, detail="文档为空")
    settings = get_ollama_settings()
    if not settings.enabled:
        raise HTTPException(status_code=400, detail="未启用Ollama")
    if not OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s).is_running():
        raise HTTPException(status_code=400, detail="Ollama 未运行")
    analysis = _run_message_analysis(session, instruction)
    analysis_instruction = str(analysis.get("rewritten_query") or instruction).strip() or instruction
    model = os.environ.get("WRITING_AGENT_REVISE_MODEL", "").strip() or settings.model
    client = OllamaClient(base_url=settings.base_url, model=model, timeout_s=settings.timeout_s)
    decision = _revision_decision_with_model(
        base_url=settings.base_url,
        model=model,
        instruction=analysis_instruction,
        selection=selection,
        text=text,
    )
    if isinstance(decision, dict) and decision.get("should_apply") is False:
        return {"ok": 1, "text": text}
    plan_steps = []
    if isinstance(decision, dict):
        plan_steps = [str(x).strip() for x in (decision.get("plan") or []) if str(x).strip()]
    plan_hint = ""
    if plan_steps:
        plan_hint = "修改计划：\n- " + "\n- ".join(plan_steps) + "\n\n"
    if selection:
        system = (
            "你是文档润色编辑，只需要改写“选中段落”。\n"
            "要求：必须遵循“思考 -> 判断 -> 进行修改”的内部流程，但只输出最终改写文本。\n"
            "规则：\n"
            "1) 只输出改写后的段落内容，不要输出标题、不加多余说明。\n"
            "2) 保持原意与结构，语言更准确、学术、连贯。\n"
            "3) 不新增事实/数据/出处；禁止占位、提示或自我指涉用语。\n"
        )
        user = f"选中段落：\n{selection}\n\n修改要求：\n{analysis_instruction}\n\n{plan_hint}请输出改写后的段落。"
        buf: list[str] = []
        for delta in client.chat_stream(system=system, user=user, temperature=0.25):
            buf.append(delta)
        rewritten = _sanitize_output_text("".join(buf).strip())
        if rewritten and selection in text:
            text = text.replace(selection, rewritten, 1)
        text = _replace_question_headings(text)
    else:
        system = (
            "你是文档编辑，需要按要求改写全文，但必须保持章节结构与顺序。\n"
            "要求：必须遵循“思考 -> 判断 -> 进行修改”的内部流程，但只输出最终文本。\n"
            "规则：\n"
            "1) 只输出纯文本，保留“# / ## / ###”标题行。\n"
            "2) 不删除正文段落（除非明显重复/乱码）；不改变章节顺序。\n"
            "3) 不编造具体事实/数据/出处；禁止占位、提示或自我指涉用语。\n"
            "4) 保留 [[TABLE:...]] / [[FIGURE:...]] 标记。\n"
        )
        user = f"修改要求：\n{analysis_instruction}\n\n{plan_hint}原文：\n{text}\n\n请输出修改后的全文。"
        buf: list[str] = []
        for delta in client.chat_stream(system=system, user=user, temperature=0.25):
            buf.append(delta)
        text = _sanitize_output_text("".join(buf).strip() or text)
        text = _replace_question_headings(text)
    if not text.strip():
        raise HTTPException(status_code=500, detail="改写结果为空")
    text = _postprocess_output_text(
        session,
        text,
        instruction,
        current_text=base_text,
        base_text=base_text,
    )
    _set_doc_text(session, text)
    store.put(session)
    return {"ok": 1, "text": text, "doc_ir": session.doc_ir or {}}
@app.post("/api/doc/{doc_id}/doc_ir/ops")
async def api_doc_ir_ops(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    ops_raw = data.get("ops") or []
    ops: list[DocIROperation] = []
    for item in ops_raw:
        if isinstance(item, dict):
            try:
                ops.append(DocIROperation.parse_obj(item))
            except Exception:
                continue
    if not ops:
        raise HTTPException(status_code=400, detail="ops 参数无效")
    doc_ir = doc_ir_from_dict(session.doc_ir or {})
    doc_ir = doc_ir_apply_ops(doc_ir, ops)
    session.doc_ir = doc_ir_to_dict(doc_ir)
    session.doc_text = doc_ir_to_text(doc_ir)
    store.put(session)
    return {"ok": 1, "doc_ir": session.doc_ir, "text": session.doc_text}
@app.post("/api/doc/{doc_id}/doc_ir/diff")
async def api_doc_ir_diff(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    other = data.get("doc_ir")
    if not isinstance(other, dict):
        raise HTTPException(status_code=400, detail="doc_ir 参数无效")
    cur = doc_ir_from_dict(session.doc_ir or {})
    nxt = doc_ir_from_dict(other)
    diff = doc_ir_diff(cur, nxt)
    return {"ok": 1, "diff": diff}
@app.post("/api/figure/render")
async def api_render_figure(request: Request) -> dict:
    data = await request.json()
    spec = data.get("spec") if isinstance(data, dict) else {}
    if not isinstance(spec, dict):
        raise HTTPException(status_code=400, detail="spec must be object")
    svg, caption = render_figure_svg(spec)
    safe_svg = sanitize_html(svg)
    return {"svg": safe_svg, "caption": caption}
def _extract_json_payload(raw: str):
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9_-]*", "", raw).strip()
        raw = raw.strip("`")
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None
def _diagram_spec_from_llm(prompt: str, kind: str) -> dict | None:
    settings = get_ollama_settings()
    if not settings.enabled:
        return None
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        return None
    kind = kind or "flow"
    sys = "You are a diagram JSON generator. Output JSON only."
    user = (
        "Convert the user request to JSON.\n"
        "Output format: {\"type\":...,\"caption\":...,\"data\":...}.\n"
        "type must be flow/er/sequence.\n"
        "flow.data: nodes[{id,text}], edges[{src,dst,label}]\n"
        "er.data: entities[{name,attributes}], relations[{left,right,label,cardinality}]\n"
        "sequence.data: participants[], messages[{from,to,text}]\n"
        f"User type: {kind}\n"
        f"User request: {prompt}\n"
    )
    try:
        raw = client.chat(system=sys, user=user, temperature=0.2)
    except Exception:
        return None
    data = _extract_json_payload(raw)
    if not data:
        return None
    return data
def _diagram_spec_fallback(prompt: str, kind: str) -> dict:
    kind = (kind or "flow").strip().lower()
    caption = (prompt or "").strip()[:20] or "diagram"
    sep_pattern = r"[,.;\n]+"
    if kind in {"flow", "flowchart"}:
        pairs = re.findall(r"([A-Za-z0-9一-鿿]{1,12})\s*(?:->|=>|?|?)\s*([A-Za-z0-9一-鿿]{1,12})", prompt or "")
        nodes = []
        edges = []
        seen = set()
        for src, dst in pairs:
            if src not in seen:
                nodes.append({"id": src, "text": src})
                seen.add(src)
            if dst not in seen:
                nodes.append({"id": dst, "text": dst})
                seen.add(dst)
            edges.append({"src": src, "dst": dst, "label": ""})
        if not nodes:
            parts = [p.strip() for p in re.split(sep_pattern, prompt or "") if p.strip()]
            if len(parts) < 2:
                parts = ["Start", "Process", "End"]
            nodes = [{"id": f"n{i+1}", "text": p[:12]} for i, p in enumerate(parts[:8])]
            edges = [{"src": f"n{i+1}", "dst": f"n{i+2}", "label": ""} for i in range(len(nodes) - 1)]
        return {"type": "flow", "caption": caption or "flow", "data": {"nodes": nodes, "edges": edges}}
    if kind == "er":
        entities = []
        relations = []
        for line in (prompt or "").splitlines():
            if ":" in line or "?" in line:
                left, right = re.split(r"[:?]", line, maxsplit=1)
                name = left.strip()
                attrs = [a.strip() for a in re.split(r"[,??]", right) if a.strip()]
                if name:
                    entities.append({"name": name[:16], "attributes": attrs[:8] or ["attr"]})
        if len(entities) < 2:
            entities = [
                {"name": "EntityA", "attributes": ["field1", "field2"]},
                {"name": "EntityB", "attributes": ["field1", "field2"]}
            ]
        relations.append({"left": entities[0]["name"], "right": entities[1]["name"], "label": "rel", "cardinality": ""})
        return {"type": "er", "caption": caption or "er", "data": {"entities": entities, "relations": relations}}
    if kind == "sequence":
        parts = [p.strip() for p in re.split(sep_pattern, prompt or "") if p.strip()]
        actors = parts[:4] or ["Client", "Server", "DB"]
        messages = []
        for i in range(len(actors) - 1):
            messages.append({"from": actors[i], "to": actors[i+1], "text": "message"})
        if not messages:
            messages = [
                {"from": "Client", "to": "Server", "text": "request"},
                {"from": "Server", "to": "DB", "text": "query"},
                {"from": "DB", "to": "Server", "text": "result"}
            ]
        return {"type": "sequence", "caption": caption or "sequence", "data": {"participants": actors, "messages": messages}}
    return {"type": "flow", "caption": caption or "flow", "data": {"nodes": [], "edges": []}}
def _diagram_spec_from_prompt(prompt: str, kind: str) -> dict:
    prompt = str(prompt or "").strip()
    kind = str(kind or "flow").strip().lower()
    spec = _diagram_spec_from_llm(prompt, kind)
    if not spec:
        return _diagram_spec_fallback(prompt, kind)
    if "type" not in spec:
        spec["type"] = kind
    if "caption" not in spec:
        spec["caption"] = (prompt[:20] if prompt else "???")
    if "data" not in spec:
        spec["data"] = {}
    return spec
@app.post("/api/doc/{doc_id}/diagram/generate")
async def api_diagram_generate(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="?????")
    data = await request.json()
    prompt = str(data.get("prompt") or "").strip()
    kind = str(data.get("kind") or "flow").strip().lower()
    if not prompt:
        raise HTTPException(status_code=400, detail="??????")
    spec = _diagram_spec_from_prompt(prompt, kind)
    return {"ok": 1, "spec": spec}
@app.post("/api/doc/{doc_id}/inline-ai")
async def api_inline_ai(doc_id: str, request: Request) -> dict:
    """
    Perform inline AI operations on document text
    Operations:
    - continue: Continue writing from cursor position
    - improve: Improve selected text
    - summarize: Summarize selected text
    - expand: Expand text with more details
    - change_tone: Change writing tone/style
    - simplify: Simplify complex text
    - elaborate: Add detailed explanation
    - rephrase: Rephrase with different wording
    """
    from writing_agent.v2.inline_ai import InlineAIEngine, InlineOperation, InlineContext, ToneStyle
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="\u6587\u6863\u4e0d\u5b58\u5728")
    data = await request.json()
    operation = data.get("operation")
    selected_text = data.get("selected_text", "")
    before_text = data.get("before_text", "")
    after_text = data.get("after_text", "")
    # Validate operation
    try:
        op = InlineOperation(operation)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"\u65e0\u6548\u7684\u64cd\u4f5c: {operation}")
    # Build context
    context = InlineContext(
        selected_text=selected_text,
        before_text=before_text,
        after_text=after_text,
        document_title=data.get("document_title", ""),
        section_title=data.get("section_title"),
        document_type=data.get("document_type")
    )
    # Execute operation
    engine = InlineAIEngine()
    # Get operation-specific parameters
    kwargs = {}
    if op == InlineOperation.CONTINUE:
        kwargs["target_words"] = data.get("target_words", 200)
    elif op == InlineOperation.IMPROVE:
        kwargs["focus"] = data.get("focus", "general")
    elif op == InlineOperation.SUMMARIZE:
        kwargs["max_sentences"] = data.get("max_sentences", 3)
    elif op == InlineOperation.EXPAND:
        kwargs["expansion_ratio"] = data.get("expansion_ratio", 2.0)
    elif op == InlineOperation.CHANGE_TONE:
        tone_str = data.get("target_tone", "professional")
        try:
            kwargs["target_tone"] = ToneStyle(tone_str)
        except ValueError:
            kwargs["target_tone"] = ToneStyle.PROFESSIONAL
    result = await engine.execute_operation(op, context, **kwargs)
    if result.success:
        return {
            "ok": 1,
            "generated_text": result.generated_text,
            "operation": result.operation.value
        }
    else:
        raise HTTPException(status_code=500, detail=result.error or "\u64cd\u4f5c\u5931\u8d25")
@app.post("/api/doc/{doc_id}/inline-ai/stream")
async def api_inline_ai_stream(doc_id: str, request: Request) -> StreamingResponse:
    """
    Perform inline AI operations with streaming output
    This endpoint returns Server-Sent Events (SSE) for real-time streaming.
    Operations:
    - ask_ai: Ask AI a question about selected text
    - explain: Explain selected text
    - improve: Improve selected text
    - continue: Continue writing
    - summarize: Summarize text
    - translate: Translate text
    - All other inline operations
    Events:
    - start: Operation started
    - delta: Incremental content update
    - done: Operation completed
    - error: Error occurred
    """
    from writing_agent.v2.inline_ai import InlineAIEngine, InlineOperation, InlineContext, ToneStyle
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="\u6587\u6863\u4e0d\u5b58\u5728")
    data = await request.json()
    operation = data.get("operation")
    selected_text = data.get("selected_text", "")
    before_text = data.get("before_text", "")
    after_text = data.get("after_text", "")
    # Validate operation
    try:
        op = InlineOperation(operation)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"\u65e0\u6548\u7684\u64cd\u4f5c: {operation}")
    # Build context
    context = InlineContext(
        selected_text=selected_text,
        before_text=before_text,
        after_text=after_text,
        document_title=data.get("document_title", ""),
        section_title=data.get("section_title"),
        document_type=data.get("document_type")
    )
    # Get operation-specific parameters
    kwargs = {}
    if op == InlineOperation.CONTINUE:
        kwargs["target_words"] = data.get("target_words", 200)
    elif op == InlineOperation.IMPROVE:
        kwargs["focus"] = data.get("focus", "general")
    elif op == InlineOperation.SUMMARIZE:
        kwargs["max_sentences"] = data.get("max_sentences", 3)
    elif op == InlineOperation.EXPAND:
        kwargs["expansion_ratio"] = data.get("expansion_ratio", 2.0)
    elif op == InlineOperation.CHANGE_TONE:
        tone_str = data.get("target_tone", "professional")
        try:
            kwargs["target_tone"] = ToneStyle(tone_str)
        except ValueError:
            kwargs["target_tone"] = ToneStyle.PROFESSIONAL
    elif op == InlineOperation.ASK_AI:
        kwargs["question"] = data.get("question", "")
    elif op == InlineOperation.EXPLAIN:
        kwargs["detail_level"] = data.get("detail_level", "medium")
    elif op == InlineOperation.TRANSLATE:
        kwargs["target_language"] = data.get("target_language", "en")
    # Execute streaming operation
    engine = InlineAIEngine()
    def emit(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    async def event_generator():
        try:
            async for event in engine.execute_operation_stream(op, context, **kwargs):
                event_type = event.get("type", "message")
                yield emit(event_type, event)
        except Exception as e:
            logger.error(f"Streaming inline AI failed: {e}", exc_info=True)
            yield emit("error", {"error": str(e)})
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
@app.post("/api/doc/{doc_id}/block-edit")
async def api_block_edit(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="document not found")
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    block_id = str(data.get("block_id") or "").strip()
    instruction = str(data.get("instruction") or "").strip()
    if not block_id or not instruction:
        raise HTTPException(status_code=400, detail="block_id and instruction required")
    incoming_ir = data.get("doc_ir")
    if isinstance(incoming_ir, dict) and incoming_ir.get("sections") is not None:
        doc_ir = doc_ir_from_dict(incoming_ir)
    else:
        doc_ir = doc_ir_from_dict(session.doc_ir or {})
    try:
        base_text = doc_ir_to_text(doc_ir)
    except Exception:
        base_text = ""
    if base_text.strip():
        session.doc_text = base_text
        session.doc_ir = doc_ir_to_dict(doc_ir)
        _auto_commit_version(session, "auto: before update")
    try:
        updated_ir, meta = await apply_block_edit(doc_ir, block_id, instruction)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    session.doc_ir = doc_ir_to_dict(updated_ir)
    text = doc_ir_to_text(updated_ir)
    session.doc_text = text
    _auto_commit_version(session, "auto: after update")
    store.put(session)
    return {"ok": 1, "doc_ir": session.doc_ir, "text": session.doc_text, "meta": meta}
@app.post("/api/rag/arxiv/ingest")
async def api_rag_arxiv_ingest(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    max_results = int(data.get("max_results") or 5)
    download_pdf = bool(data.get("download_pdf", True))
    keep_existing = bool(data.get("keep_existing", True))
    index_after = bool(data.get("index", True))
    embed = bool(data.get("embed", True))
    existing = {p.paper_id for p in rag_store.list_papers()} if keep_existing else set()
    res = search_arxiv(query=query, max_results=max_results)
    saved: list[dict] = []
    errors: list[dict] = []
    for paper in res.papers:
        if keep_existing and paper.paper_id in existing:
            continue
        try:
            pdf_bytes = download_arxiv_pdf(paper_id=paper.paper_id) if download_pdf else None
            rec = rag_store.put_arxiv_paper(paper, pdf_bytes=pdf_bytes)
            if index_after:
                try:
                    rag_index.upsert_from_paper(rec, embed=embed)
                except Exception:
                    pass
            saved.append(
                {
                    "paper_id": rec.paper_id,
                    "title": rec.title,
                    "published": rec.published,
                    "abs_url": rec.abs_url,
                    "pdf_url": rec.pdf_url,
                    "pdf_path": rec.pdf_path if (pdf_bytes is not None) else "",
                }
            )
        except Exception as e:
            errors.append({"paper_id": paper.paper_id, "title": paper.title, "error": str(e)})
    return {"ok": 1, "saved": saved, "errors": errors}
@app.get("/api/rag/papers")
def api_rag_list_papers() -> dict:
    papers = rag_store.list_papers()
    return {
        "papers": [
            {
                "paper_id": p.paper_id,
                "title": p.title,
                "published": p.published,
                "abs_url": p.abs_url,
                "pdf_path": p.pdf_path if Path(p.pdf_path).exists() else "",
            }
            for p in papers
        ]
    }
@app.post("/api/rag/search")
async def api_rag_search(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    top_k = int(data.get("top_k") or 5)
    max_results = int(data.get("max_results") or 10)
    sources = data.get("sources")
    mode = str(data.get("mode") or "").strip().lower()
    is_remote = ("sources" in data) or ("max_results" in data) or mode == "remote"
    if is_remote and not isinstance(sources, list):
        sources = ["openalex", "arxiv"]
    mcp_payload = _mcp_rag_search(
        query,
        top_k=top_k,
        sources=sources if is_remote else None,
        max_results=max_results if is_remote else None,
        mode="remote" if is_remote else "local",
    )
    if isinstance(mcp_payload, dict):
        results = mcp_payload.get("results")
        mcp_mode = str(mcp_payload.get("mode") or "").strip().lower()
        if mcp_mode == "remote":
            is_remote = True
        if isinstance(results, list):
            if is_remote:
                items = []
                for r in results:
                    if not isinstance(r, dict):
                        continue
                    items.append(
                        {
                            "source": str(r.get("source") or ""),
                            "paper_id": str(r.get("id") or ""),
                            "title": str(r.get("title") or ""),
                            "summary": str(r.get("summary") or ""),
                            "authors": r.get("authors") or [],
                            "published": str(r.get("published") or ""),
                            "updated": str(r.get("updated") or ""),
                            "abs_url": str(r.get("url") or ""),
                            "pdf_url": str(r.get("pdf_url") or ""),
                            "categories": r.get("categories") or [],
                            "primary_category": str(r.get("primary_category") or ""),
                        }
                    )
                return {"ok": 1, "items": items}
            hits = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                hits.append(
                    {
                        "paper_id": str(r.get("id") or ""),
                        "title": str(r.get("title") or ""),
                        "summary": str(r.get("summary") or ""),
                        "snippet": str(r.get("snippet") or ""),
                        "score": float(r.get("score") or 0.0),
                        "published": str(r.get("published") or ""),
                        "abs_url": str(r.get("url") or ""),
                        "pdf_path": "",
                    }
                )
            return {"hits": hits}
    if is_remote:
        srcs = sources if isinstance(sources, list) else ["openalex", "arxiv"]
        items: list[dict] = []
        if "openalex" in srcs:
            try:
                res = search_openalex(query=query, max_results=max_results)
                for w in res.works:
                    items.append(
                        {
                            "source": "openalex",
                            "paper_id": w.paper_id,
                            "title": w.title,
                            "summary": w.summary,
                            "authors": w.authors,
                            "published": w.published,
                            "updated": w.updated,
                            "abs_url": w.abs_url,
                            "pdf_url": w.pdf_url,
                            "categories": w.categories,
                            "primary_category": w.primary_category,
                        }
                    )
            except Exception:
                pass
        if "arxiv" in srcs:
            try:
                res = search_arxiv(query=query, max_results=max_results)
                for p in res.papers:
                    items.append(
                        {
                            "source": "arxiv",
                            "paper_id": p.paper_id,
                            "title": p.title,
                            "summary": p.summary,
                            "authors": p.authors,
                            "published": p.published,
                            "updated": p.updated,
                            "abs_url": p.abs_url,
                            "pdf_url": p.pdf_url,
                            "categories": p.categories,
                            "primary_category": p.primary_category,
                        }
                    )
            except Exception:
                pass
        return {"ok": 1, "items": items}
    hits = search_papers(papers=rag_store.list_papers(), query=query, top_k=top_k)
    return {
        "hits": [
            {
                "paper_id": h.paper_id,
                "title": h.title,
                "summary": h.summary,
                "snippet": h.snippet,
                "score": h.score,
                "published": h.published,
                "abs_url": h.abs_url,
                "pdf_path": h.pdf_path if Path(h.pdf_path).exists() else "",
            }
            for h in hits
        ]
    }
@app.post("/api/rag/retrieve")
async def api_rag_retrieve(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    top_k = int(data.get("top_k") or 5)
    max_chars = int(data.get("max_chars") or 2500)
    per_paper = int(data.get("per_paper") or 2)
    mcp_payload = _mcp_rag_retrieve(query, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    if isinstance(mcp_payload, dict):
        context = str(mcp_payload.get("context") or "")
        sources = mcp_payload.get("sources")
        hits: list[dict] = []
        if isinstance(sources, list):
            for s in sources:
                if not isinstance(s, dict):
                    continue
                hits.append(
                    {
                        "paper_id": str(s.get("id") or ""),
                        "title": str(s.get("title") or ""),
                        "abs_url": str(s.get("url") or ""),
                        "kind": str(s.get("kind") or ""),
                        "published": str(s.get("published") or ""),
                    }
                )
        return {"context": context, "mode": "mcp", "hits": hits}
    res = retrieve_context(rag_dir=RAG_DIR, query=query, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    if res.chunk_hits:
        return {
            "context": res.context,
            "mode": "chunks",
            "hits": [
                {"chunk_id": h.chunk_id, "paper_id": h.paper_id, "title": h.title, "score": h.score, "kind": h.kind, "abs_url": h.abs_url}
                for h in res.chunk_hits
            ],
        }
    return {
        "context": res.context,
        "mode": "papers",
        "hits": [{"paper_id": h.paper_id, "title": h.title, "score": h.score} for h in res.paper_hits],
    }
@app.post("/api/rag/index/rebuild")
async def api_rag_index_rebuild(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    embed = bool(data.get("embed", True))
    total = rag_index.rebuild(embed=embed)
    return {"ok": 1, "chunks": total}
@app.post("/api/rag/search/chunks")
async def api_rag_search_chunks(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    top_k = int(data.get("top_k") or 6)
    per_paper = int(data.get("per_paper") or 2)
    alpha = float(data.get("alpha") or 0.75)
    use_embeddings = bool(data.get("use_embeddings", True))
    mcp_payload = _mcp_rag_search_chunks(
        query,
        top_k=top_k,
        per_paper=per_paper,
        alpha=alpha,
        use_embeddings=use_embeddings,
    )
    if isinstance(mcp_payload, dict):
        hits = mcp_payload.get("hits")
        if isinstance(hits, list):
            return {
                "mode": "mcp",
                "hits": [
                    {
                        "chunk_id": str(h.get("chunk_id") or ""),
                        "paper_id": str(h.get("paper_id") or ""),
                        "title": str(h.get("title") or ""),
                        "abs_url": str(h.get("abs_url") or ""),
                        "kind": str(h.get("kind") or ""),
                        "score": float(h.get("score") or 0.0),
                        "text": str(h.get("text") or ""),
                    }
                    for h in hits
                    if isinstance(h, dict)
                ]
            }
    hits = rag_index.search(query=query, top_k=top_k, per_paper=per_paper, use_embeddings=use_embeddings, alpha=alpha)
    return {
        "hits": [
            {
                "chunk_id": h.chunk_id,
                "paper_id": h.paper_id,
                "title": h.title,
                "abs_url": h.abs_url,
                "kind": h.kind,
                "score": h.score,
                "text": h.text,
            }
            for h in hits
        ]
    }
@app.get("/api/rag/paper/{paper_id:path}/pdf")
def api_rag_get_pdf(paper_id: str) -> FileResponse:
    path = rag_store.find_pdf_path(paper_id)
    if path is None:
        raise HTTPException(status_code=404, detail="pdf not found")
    return FileResponse(str(path), media_type="application/pdf", filename=path.name)
@app.post("/api/library/upload")
async def api_library_upload(file: UploadFile = File(...)) -> dict:
    if file is None or not (file.filename or "").strip():
        raise HTTPException(status_code=400, detail="file required")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large (max 50MB)")
    rec = user_library.put_upload(filename=file.filename, file_bytes=raw)
    return {"ok": 1, "item": _library_item_payload(rec)}
@app.get("/api/library/items")
def api_library_items(status: str = "") -> dict:
    st = (status or "").strip().lower()
    if st in {"", "all"}:
        st = ""
    items = user_library.list_items(status=st or None)
    return {"items": [_library_item_payload(i) for i in items]}
@app.get("/api/library/item/{doc_id}")
def api_library_item(doc_id: str) -> dict:
    rec = user_library.get_item(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="item not found")
    text = user_library.get_text(doc_id)
    return {"item": _library_item_payload(rec), "text": text}
@app.post("/api/library/item/{doc_id}/approve")
def api_library_approve(doc_id: str) -> dict:
    rec = user_library.approve(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="item not found")
    return {"ok": 1, "item": _library_item_payload(rec)}
@app.post("/api/library/item/{doc_id}/restore")
def api_library_restore(doc_id: str) -> dict:
    rec = user_library.restore(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="item not found")
    return {"ok": 1, "item": _library_item_payload(rec)}
@app.post("/api/library/item/{doc_id}/trash")
def api_library_trash(doc_id: str) -> dict:
    rec = user_library.trash(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="item not found")
    return {"ok": 1, "item": _library_item_payload(rec)}
@app.post("/api/library/item/{doc_id}/update")
async def api_library_update(doc_id: str, request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    text = str(data.get("text") or "")
    rec = user_library.update_text(doc_id, text=text)
    if rec is None:
        raise HTTPException(status_code=404, detail="item not found")
    return {"ok": 1, "item": _library_item_payload(rec)}
@app.delete("/api/library/item/{doc_id}")
def api_library_delete(doc_id: str) -> dict:
    if not user_library.delete(doc_id):
        raise HTTPException(status_code=404, detail="item not found")
    return {"ok": 1}
@app.post("/api/library/from_doc")
async def api_library_from_doc(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    text = str(data.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    title = str(data.get("title") or "").strip() or _default_title()
    status = str(data.get("status") or "trashed").strip().lower() or "trashed"
    source_id = str(data.get("source_id") or "").strip()
    rec = user_library.put_text(text=text, title=title, source="generated", status=status, source_id=source_id)
    return {"ok": 1, "item": _library_item_payload(rec)}
def _download_url(url: str, *, timeout_s: float = 40.0) -> bytes | None:
    u = (url or "").strip()
    if not u:
        return None
    headers = {"User-Agent": "writing-agent-studio/2.0 (+rag ingest)"}
    req = UrlRequest(url=u, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            return resp.read()
    except Exception:
        return None
@app.post("/api/rag/ingest")
async def api_rag_ingest(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    items = data.get("items") or []
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items required")
    download_pdf = bool(data.get("download_pdf", True))
    embed = bool(data.get("embed", True))
    ingested: list[dict] = []
    for item in items[:50]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip().lower()
        paper_id = str(item.get("paper_id") or "").strip()
        if not paper_id:
            continue
        pdf_bytes = None
        try:
            if source == "arxiv":
                if download_pdf:
                    pdf_bytes = download_arxiv_pdf(paper_id=paper_id)
                paper = type(
                    "ArxivPaperShim",
                    (),
                    {
                        "paper_id": paper_id,
                        "title": str(item.get("title") or ""),
                        "summary": str(item.get("summary") or ""),
                        "authors": item.get("authors") or [],
                        "published": str(item.get("published") or ""),
                        "updated": str(item.get("updated") or ""),
                        "abs_url": str(item.get("abs_url") or ""),
                        "pdf_url": str(item.get("pdf_url") or ""),
                        "categories": item.get("categories") or [],
                        "primary_category": str(item.get("primary_category") or ""),
                    },
                )()
                rec = rag_store.put_arxiv_paper(paper, pdf_bytes=pdf_bytes)
            else:
                if download_pdf:
                    pdf_bytes = _download_url(str(item.get("pdf_url") or ""))
                work = type(
                    "OpenAlexWorkShim",
                    (),
                    {
                        "paper_id": paper_id,
                        "title": str(item.get("title") or ""),
                        "summary": str(item.get("summary") or ""),
                        "authors": item.get("authors") or [],
                        "published": str(item.get("published") or ""),
                        "updated": str(item.get("updated") or ""),
                        "abs_url": str(item.get("abs_url") or ""),
                        "pdf_url": str(item.get("pdf_url") or ""),
                        "categories": item.get("categories") or [],
                        "primary_category": str(item.get("primary_category") or ""),
                    },
                )()
                rec = rag_store.put_openalex_work(work, pdf_bytes=pdf_bytes)
            rag_index.upsert_from_paper(rec, embed=embed)
            ingested.append({"paper_id": paper_id, "title": rec.title, "source": rec.source})
        except Exception:
            continue
    return {"ok": 1, "count": len(ingested), "items": ingested}
@app.get("/api/rag/stats")
def api_rag_stats() -> dict:
    papers = rag_store.list_papers()
    return {
        "ok": 1,
        "paper_count": len(papers),
        "pdf_count": len([p for p in papers if p.pdf_path and Path(p.pdf_path).exists()]),
        "chunks": rag_index.index_path.exists(),
    }
@app.get("/api/docs/list")
def api_docs_list() -> dict:
    """获取文档列表"""
    docs = []
    for doc_id, session in store.items():
        text = _safe_doc_text(session)
        title = session.title or ""
        if not title:
            # 从文本中提取标题
            lines = text.split('\n')
            for line in lines:
                if line.strip().startswith('#'):
                    title = line.strip().lstrip('#').strip()
                    break
        docs.append({
            "doc_id": doc_id,
            "title": title or _default_title(),
            "text": text[:200],
            "updated_at": getattr(session, "updated_at", ""),
            "char_count": len(text)
        })
    # 按更新时间排序
    docs.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"ok": 1, "docs": docs}
@app.post("/api/doc/{doc_id}/delete")
def api_doc_delete(doc_id: str) -> dict:
    """删除文档"""
    if doc_id in store._sessions:
        del store._sessions[doc_id]
    return {"ok": 1}
@app.get("/download/{doc_id}.docx")
def download_docx(doc_id: str) -> StreamingResponse:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="?????")
    base_text = _safe_doc_text(session)
    doc_ir = None
    if session.doc_ir:
        try:
            doc_ir = doc_ir_from_dict(session.doc_ir)
        except Exception:
            doc_ir = None
    if doc_ir is None:
        if not (base_text or "").strip():
            raise HTTPException(status_code=400, detail="????")
        text = _clean_export_text(base_text)
        text = _fix_section_heading_glue(text, _collect_heading_candidates(session))
        doc_ir = doc_ir_from_text(text)
    doc_ir = _normalize_doc_ir_for_export(doc_ir, session)
    style = _citation_style_from_session(session)
    doc_ir = _apply_citations_to_doc_ir(doc_ir, session.citations or {}, style)
    parsed = doc_ir_to_parsed(doc_ir)
    fmt = _formatting_from_session(session)
    prefs = _export_prefs_from_session(session)
    use_html = _doc_ir_has_styles(doc_ir)
    if use_html:
        html = _doc_ir_to_html(doc_ir)
        payload = html_docx_exporter.build(html, fmt)
    else:
        template_path = str(session.template_source_path or "").strip()
        if template_path and Path(template_path).suffix.lower() != ".docx":
            template_path = ""
        if not template_path:
            try:
                for name in os.listdir(REPO_ROOT):
                    if name.lower().endswith(".docx") and "converted" in name.lower():
                        template_path = str(REPO_ROOT / name)
                        break
                if not template_path:
                    for name in os.listdir(TEMPLATE_DIR):
                        if re.search(r"\(1\)\.docx$", name):
                            template_path = str(TEMPLATE_DIR / name)
                            break
                if not template_path:
                    for name in os.listdir(TEMPLATE_DIR):
                        if name.lower().endswith(".docx") and "??????" in name:
                            template_path = str(TEMPLATE_DIR / name)
                            break
            except Exception:
                template_path = ""
        try:
            text = doc_ir_to_text(doc_ir)
        except Exception:
            text = base_text
        text = _clean_export_text(text)
        rust_payload = _try_rust_docx_export(text)
        if rust_payload:
            payload = rust_payload
        else:
            payload = docx_exporter.build_from_parsed(parsed, fmt, prefs, template_path=template_path or None)
    issues = _validate_docx_bytes(payload)
    if issues:
        logger.warning(f"[docx-validate] {doc_id}: " + ";".join(issues))
    filename = f"{parsed.title or 'document'}.docx"
    filename = re.sub(r'[\r\n"]+', "", filename)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename) or "document.docx"
    quoted = quote(filename, safe="")
    headers = {"Content-Disposition": f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{quoted}'}
    if issues:
        headers["X-Docx-Warn"] = ",".join(issues)[:256]
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )
def _resolve_soffice_path() -> str | None:
    env = (
        os.environ.get("WRITING_AGENT_SOFFICE")
        or os.environ.get("SOFFICE_PATH")
        or os.environ.get("LIBREOFFICE_PATH")
    )
    if env:
        p = Path(env)
        if p.is_dir():
            cand = p / ("soffice.exe" if os.name == "nt" else "soffice")
            if cand.exists():
                return str(cand)
        if p.exists():
            return str(p)
    for name in ("soffice", "soffice.exe"):
        found = shutil.which(name)
        if found:
            return found
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:\Program Files")) / "LibreOffice" / "program" / "soffice.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\Program Files (x86)")) / "LibreOffice" / "program" / "soffice.exe",
        ]
        for cand in candidates:
            if cand.exists():
                return str(cand)
    return None
def _convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> None:
    errors: list[str] = []
    if os.name == "nt":
        try:
            from docx2pdf import convert  # type: ignore
            convert(str(docx_path), str(pdf_path))
            if pdf_path.exists():
                return
        except Exception as e:
            errors.append(f"docx2pdf: {e}")
    soffice = _resolve_soffice_path()
    if not soffice:
        detail = "PDF????????LibreOffice"
        if errors:
            detail += "?" + "; ".join(errors)[:200]
        raise HTTPException(status_code=500, detail=detail)
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf_path.parent), str(docx_path)],
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0 or not pdf_path.exists():
        stderr = result.stderr.decode("utf-8", errors="ignore").strip()
        stdout = result.stdout.decode("utf-8", errors="ignore").strip()
        msg = stderr or stdout or "LibreOffice ????"
        raise HTTPException(status_code=500, detail=f"PDF?????{msg}")
@app.get("/download/{doc_id}.pdf")
def download_pdf(doc_id: str) -> StreamingResponse:
    """??PDF???docx???"""
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="?????")
    base_text = _safe_doc_text(session)
    doc_ir = None
    if session.doc_ir:
        try:
            doc_ir = doc_ir_from_dict(session.doc_ir)
        except Exception:
            doc_ir = None
    if doc_ir is None:
        if not (base_text or "").strip():
            raise HTTPException(status_code=400, detail="????")
        text = _clean_export_text(base_text)
        text = _fix_section_heading_glue(text, _collect_heading_candidates(session))
        doc_ir = doc_ir_from_text(text)
    doc_ir = _normalize_doc_ir_for_export(doc_ir, session)
    style = _citation_style_from_session(session)
    doc_ir = _apply_citations_to_doc_ir(doc_ir, session.citations or {}, style)
    parsed = doc_ir_to_parsed(doc_ir)
    fmt = _formatting_from_session(session)
    prefs = _export_prefs_from_session(session)
    use_html = _doc_ir_has_styles(doc_ir)
    if use_html:
        html = _doc_ir_to_html(doc_ir)
        docx_bytes = html_docx_exporter.build(html, fmt)
    else:
        template_path = str(session.template_source_path or "").strip()
        if template_path and Path(template_path).suffix.lower() != ".docx":
            template_path = ""
        try:
            text = doc_ir_to_text(doc_ir)
        except Exception:
            text = base_text
        text = _clean_export_text(text)
        rust_payload = _try_rust_docx_export(text)
        if rust_payload:
            docx_bytes = rust_payload
        else:
            docx_bytes = docx_exporter.build_from_parsed(parsed, fmt, prefs, template_path=template_path or None)
    # ???docx
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
        tmp_docx.write(docx_bytes)
        tmp_docx_path = Path(tmp_docx.name)
    tmp_pdf_path = tmp_docx_path.with_suffix(".pdf")
    try:
        _convert_docx_to_pdf(tmp_docx_path, tmp_pdf_path)
        with open(tmp_pdf_path, "rb") as f:
            pdf_bytes = f.read()
        filename = f"{parsed.title or 'document'}.pdf"
        filename = re.sub(r'[\r\n"]+', "", filename)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename) or "document.pdf"
        quoted = quote(filename, safe="")
        headers = {"Content-Disposition": f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{quoted}'}
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers=headers,
        )
    finally:
        # ??????
        try:
            tmp_docx_path.unlink(missing_ok=True)
            tmp_pdf_path.unlink(missing_ok=True)
        except Exception:
            pass
@app.get("/export/{doc_id}/{format}")
def export_multi_format(doc_id: str, format: str) -> Response:
    """多格式导出：md/html/tex/txt"""
    session = store.get(doc_id)
    if not session:
        raise HTTPException(404, "文档不存在")
    
    text = session.doc_text or ""
    if not text.strip():
        raise HTTPException(400, "文档为空")
    
    title = _extract_title(text)
    
    if format == "md":
        # Markdown导出（带元数据）
        metadata = f"""---
title: {title}
author: user
date: {datetime.now().strftime('%Y-%m-%d')}
version: {session.current_version_id or 'draft'}
---
"""
        content = metadata + text
        return Response(
            content=content.encode("utf-8"),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{quote(title)}.md"'}
        )
    
    elif format == "html":
        # HTML导出（带样式）
        parsed = parse_report_text(text)
        html_body = _render_blocks_to_html(parsed.blocks)
        full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: 'Times New Roman', '宋体', serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 20px; }}
        h1 {{ text-align: center; font-size: 24pt; margin-bottom: 20px; }}
        h2 {{ font-size: 18pt; margin-top: 20px; }}
        h3 {{ font-size: 14pt; margin-top: 16px; }}
        p {{ text-align: justify; text-indent: 2em; margin-bottom: 12px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        .citation-ref {{ color: #0066cc; font-size: 0.85em; font-weight: 600; vertical-align: super; }}
    </style>
</head>
<body>
{html_body}
</body>
</html>"""
        return Response(
            content=full_html.encode("utf-8"),
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{quote(title)}.html"'}
        )
    
    elif format == "tex":
        # LaTeX导出
        latex_content = _convert_to_latex(text, title)
        return Response(
            content=latex_content.encode("utf-8"),
            media_type="application/x-latex",
            headers={"Content-Disposition": f'attachment; filename="{quote(title)}.tex"'}
        )
    
    elif format == "txt":
        # 纯文本导出（去除Markdown标记）
        plain = re.sub(r'#{1,3}\s+', '', text)
        plain = re.sub(r'\*\*(.+?)\*\*', r'\1', plain)
        plain = re.sub(r'\*(.+?)\*', r'\1', plain)
        plain = re.sub(r'\[@([a-zA-Z0-9_-]+)\]', '', plain)
        return Response(
            content=plain.encode("utf-8"),
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{quote(title)}.txt"'}
        )
    
    else:
        raise HTTPException(400, f"不支持的格式：{format}，支持md/html/tex/txt")
def _try_rust_docx_export(text: str) -> bytes | None:
    return try_rust_docx_export(text)
def _try_rust_import(path: Path) -> str | None:
    return try_rust_import(path)
def _library_item_payload(rec) -> dict:
    return {
        "doc_id": rec.doc_id,
        "title": rec.title,
        "status": rec.status,
        "source": rec.source,
        "source_id": rec.source_id,
        "source_name": rec.source_name,
        "char_count": rec.char_count,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
        "trash_until": rec.trash_until,
    }
def _extract_json_block(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return ""
    return m.group(0).strip()
_ANALYSIS_INFLIGHT: dict[str, float] = {}
_ANALYSIS_LOCK = threading.Lock()
def _quick_intent_guess(raw: str) -> dict:
    s = (raw or "").strip()
    if not s:
        return {"name": "other", "confidence": 0.1, "reason": ""}
    compact = re.sub(r"\s+", "", s)
    if re.search(r"(下载|导出|导出文档|docx|pdf|word)", compact, re.I):
        return {"name": "export", "confidence": 0.6, "reason": "命中导出/下载关键词"}
    if re.search(r"(修改|润色|改写|优化|调整|替换|改为|改成|删减|删除|去掉|补充|扩写|简化|校对|纠错|统一|合并|拆分|分拆|分成|新增|添加|插入|移动|移到|放到|重排|排序|顺序|交换|互换|对调)", compact):
        return {"name": "modify", "confidence": 0.6, "reason": "命中修改关键词"}
    if re.search(r"(模板|格式|样式|排版|字号|字体|行距|页边距|页眉|页脚)", compact):
        return {"name": "template", "confidence": 0.55, "reason": "命中模板/格式关键词"}
    if re.search(r"(上传|导入|附件|资料)", compact):
        return {"name": "upload", "confidence": 0.55, "reason": "命中上传关键词"}
    if re.search(r"(目录|章节|大纲|结构|提纲|框架)", compact):
        return {"name": "outline", "confidence": 0.55, "reason": "命中结构关键词"}
    if re.search(r"(生成|撰写|起草|写一份|写一篇|写个|输出|制作|形成)", compact):
        return {"name": "generate", "confidence": 0.55, "reason": "命中生成关键词"}
    if re.search(r"[?？]", s):
        return {"name": "question", "confidence": 0.4, "reason": "疑问句"}
    return {"name": "other", "confidence": 0.2, "reason": "未命中规则"}
def _clean_title_candidate(text: str) -> str:
    t = str(text or "").strip()
    if not t:
        return ""
    m = re.search(r"《([^》]{1,80})》", t)
    if m:
        t = m.group(1)
    t = t.strip().strip("“”\"'‘’《》【】（）()[]{}<>「」『』")
    t = re.sub(r"[。！？!?；;，,、]+$", "", t).strip()
    return t
def _extract_title_change(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    patterns = [
        r"(?:修改|更改|调整|设置)\s*(?:文档)?(?:标题|题目)\s*(?:为|成)?\s*(.+)",
        r"(?:标题|题目)\s*(?:改为|改成|调整为|设置为)\s*(.+)",
        r"把\s*(?:文档)?(?:标题|题目)\s*(?:改为|改成|调整为|设置为)\s*(.+)",
        r"将\s*(?:文档)?(?:标题|题目)\s*(?:改为|改成|调整为|设置为)\s*(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            cand = _clean_title_candidate(m.group(1))
            if cand:
                return cand
    return None
def _extract_replace_pair(raw: str) -> tuple[str, str] | None:
    s = (raw or "").strip()
    if not s:
        return None
    quoted = re.search(
        r"[把将]?\s*[\"“‘《【](.{1,80}?)[\"”’》】]\s*(?:改为|改成|替换为|换成)\s*[\"“‘《【](.{1,80}?)[\"”’》】]\s*$",
        s,
    )
    if quoted:
        old = quoted.group(1).strip()
        new = quoted.group(2).strip()
        if old and new and old != new:
            return old, new
    m = re.search(r"(.{1,80}?)\s*(?:改为|改成|替换为|换成)\s*(.{1,80})", s)
    if m:
        old = m.group(1).strip().strip("“”\"'‘’《》【】")
        new = m.group(2).strip().strip("“”\"'‘’《》【】")
        if old and new and old != new:
            return old, new
    return None
def _normalize_heading_text(text: str) -> str:
    t = re.sub(r"^#{1,6}\s*", "", str(text or "")).strip()
    t = re.sub(r"^第[一二三四五六七八九十0-9]+[章节部分]\s*", "", t)
    t = re.sub(r"^(?:[0-9]+(?:\.[0-9]+){0,2}|[一二三四五六七八九十]+)[、.）)]\s*", "", t)
    return re.sub(r"\s+", "", t)
def _apply_title_change(text: str, title: str) -> str:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i, line in enumerate(lines):
        if re.match(r"^#\s+", line):
            lines[i] = f"# {title}"
            return "\n".join(lines).strip()
    if lines and lines[0].strip():
        return f"# {title}\n\n" + "\n".join(lines).strip()
    return f"# {title}\n" + "\n".join(lines).strip()
@dataclass
class EditOp:
    op: str
    args: dict
@dataclass
class RuleSpec:
    name: str
    op: str
    regex: re.Pattern
    args: dict
    priority: int
    clean: list[str]
    clean_title: bool
    strip_quotes: list[str]
    types: dict
    detect_all: bool
@dataclass
class SectionSpan:
    level: int
    title: str
    start: int
    end: int
def _split_lines(text: str) -> list[str]:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
_EDIT_RULES_CACHE: dict = {"mtime": 0.0, "rules": []}
def _compile_rule_flags(flag_list: list[str]) -> int:
    flags = 0
    for f in flag_list or []:
        f = str(f).upper()
        if f == "I":
            flags |= re.IGNORECASE
        elif f == "M":
            flags |= re.MULTILINE
        elif f == "S":
            flags |= re.DOTALL
        elif f == "X":
            flags |= re.VERBOSE
    return flags
def _load_edit_rules() -> list[RuleSpec]:
    path = Path("writing_agent/web/edit_rules.json")
    try:
        mtime = path.stat().st_mtime
    except Exception:
        return []
    cache = _EDIT_RULES_CACHE
    if cache.get("mtime") == mtime and cache.get("rules"):
        return cache.get("rules") or []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rules: list[RuleSpec] = []
    for item in data.get("rules", []):
        pattern = str(item.get("pattern") or "").strip()
        if not pattern:
            continue
        flags = _compile_rule_flags(item.get("flags") or [])
        try:
            regex = re.compile(pattern, flags)
        except re.error:
            continue
        rules.append(
            RuleSpec(
                name=str(item.get("name") or ""),
                op=str(item.get("op") or ""),
                regex=regex,
                args=dict(item.get("args") or {}),
                priority=int(item.get("priority") or 100),
                clean=list(item.get("clean") or []),
                clean_title=bool(item.get("clean_title") or False),
                strip_quotes=list(item.get("strip_quotes") or []),
                types=dict(item.get("types") or {}),
                detect_all=bool(item.get("detect_all") or False),
            )
        )
    rules.sort(key=lambda r: r.priority)
    _EDIT_RULES_CACHE["mtime"] = mtime
    _EDIT_RULES_CACHE["rules"] = rules
    return rules
def _split_instruction_clauses(raw: str) -> list[str]:
    s = str(raw or "").strip()
    if not s:
        return []
    token = "||"
    for sep in ["并且", "同时", "然后", "以及", "并"]:
        s = s.replace(sep, token)
    s = re.sub(r"[，,;；。]+", token, s)
    parts = [p.strip() for p in s.split(token) if p.strip()]
    return parts or [str(raw or "").strip()]
def _strip_quotes(text: str) -> str:
    return str(text or "").strip().strip("“”\"'‘’《》【】")
def _build_rule_args(rule: RuleSpec, match: re.Match, clause: str) -> dict | None:
    args: dict = {}
    for key, val in (rule.args or {}).items():
        if isinstance(val, str) and val.startswith("$"):
            group = val[1:]
            try:
                args[key] = match.group(group)
            except IndexError:
                args[key] = ""
        else:
            args[key] = val
    if rule.detect_all:
        args["all"] = bool(re.search(r"(全部|所有|全文)", clause))
    for key in rule.strip_quotes or []:
        if key in args:
            args[key] = _strip_quotes(args.get(key))
    if rule.clean_title and "title" in args:
        args["title"] = _clean_title_candidate(args.get("title"))
    for key in rule.clean or []:
        if key in args:
            args[key] = _clean_section_title(args.get(key))
    for key, kind in (rule.types or {}).items():
        if key not in args:
            continue
        if kind == "int_chinese":
            args[key] = _parse_chinese_number(str(args.get(key)))
        elif kind == "list_titles":
            args[key] = _split_title_list(str(args.get(key)))
    # remove empty string args
    for key in list(args.keys()):
        if isinstance(args[key], str) and not args[key].strip():
            args[key] = ""
    return args
def _extract_sections(text: str, *, prefer_levels: tuple[int, ...] = (2, 3)) -> list[SectionSpan]:
    lines = _split_lines(text)
    raw: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        if not title:
            continue
        raw.append((i, level, title))
    use = [h for h in raw if h[1] in prefer_levels]
    if not use:
        use = raw
    out: list[SectionSpan] = []
    for idx, (start, level, title) in enumerate(use):
        end = use[idx + 1][0] if idx + 1 < len(use) else len(lines)
        out.append(SectionSpan(level=level, title=title, start=start, end=end))
    return out
def _find_section(sections: list[SectionSpan], title: str) -> SectionSpan | None:
    target = _normalize_heading_text(title)
    if not target:
        return None
    for sec in sections:
        if _normalize_heading_text(sec.title) == target:
            return sec
    for sec in sections:
        norm = _normalize_heading_text(sec.title)
        if target in norm or norm in target:
            return sec
    return None
def _find_section_by_index(text: str, index: int) -> SectionSpan | None:
    if index <= 0:
        return None
    sections = _extract_sections(text, prefer_levels=(2,))
    if not sections:
        sections = _extract_sections(text, prefer_levels=(1, 2, 3))
    if 0 < index <= len(sections):
        return sections[index - 1]
    return None
def _insert_block(lines: list[str], idx: int, block: list[str]) -> None:
    if idx < 0:
        idx = 0
    if idx > len(lines):
        idx = len(lines)
    insert_block = list(block)
    if idx > 0 and lines[idx - 1].strip() and insert_block and insert_block[0].strip():
        insert_block = [""] + insert_block
    lines[idx:idx] = insert_block
def _apply_set_title(text: str, title: str) -> str:
    return _apply_title_change(text, title)
def _apply_replace_text(text: str, old: str, new: str, *, replace_all: bool = False) -> str:
    if not old:
        return text
    return (text or "").replace(old, new) if replace_all else (text or "").replace(old, new, 1)
def _apply_rename_section(text: str, old_title: str, new_title: str) -> str:
    lines = _split_lines(text)
    sections = _extract_sections(text)
    sec = _find_section(sections, old_title)
    if not sec:
        return text
    line = lines[sec.start]
    m = re.match(r"^(#+)\s+", line)
    prefix = m.group(1) if m else "##"
    lines[sec.start] = f"{prefix} {new_title}"
    return "\n".join(lines).strip()
def _apply_add_section_op(
    text: str,
    title: str,
    *,
    anchor: str | None = None,
    position: str = "after",
    level: int | None = None,
) -> str:
    lines = _split_lines(text)
    sections = _extract_sections(text)
    anchor_sec = _find_section(sections, anchor) if anchor else None
    if anchor_sec:
        insert_idx = anchor_sec.end if position == "after" else anchor_sec.start
        level = level or max(2, anchor_sec.level)
    else:
        ref_sec = _find_section(sections, "参考文献") or _find_section(sections, "参考资料")
        insert_idx = ref_sec.start if ref_sec else len(lines)
        level = level or 2
    heading = f"{'#' * level} {title}"
    block = [heading, ""]
    _insert_block(lines, insert_idx, block)
    return "\n".join(lines).strip()
def _apply_delete_section_op(text: str, title: str | None = None, index: int | None = None) -> str:
    lines = _split_lines(text)
    sec = None
    if index:
        sec = _find_section_by_index(text, index)
    if sec is None and title:
        sections = _extract_sections(text)
        sec = _find_section(sections, title)
    if not sec:
        return text
    del lines[sec.start:sec.end]
    if sec.start > 0 and sec.start < len(lines):
        if not lines[sec.start - 1].strip() and not lines[sec.start].strip():
            del lines[sec.start]
    return "\n".join(lines).strip()
def _apply_move_section_op(text: str, title: str, anchor: str, *, position: str = "after") -> str:
    lines = _split_lines(text)
    sections = _extract_sections(text)
    src = _find_section(sections, title)
    if not src:
        return text
    block = lines[src.start:src.end]
    del lines[src.start:src.end]
    rebuilt = "\n".join(lines)
    sections = _extract_sections(rebuilt)
    anchor_sec = _find_section(sections, anchor)
    insert_idx = len(lines)
    if anchor_sec:
        insert_idx = anchor_sec.end if position == "after" else anchor_sec.start
    _insert_block(lines, insert_idx, block)
    return "\n".join(lines).strip()
def _apply_replace_section_content_op(text: str, title: str, content: str) -> str:
    lines = _split_lines(text)
    sections = _extract_sections(text)
    sec = _find_section(sections, title)
    if not sec:
        return text
    content_lines = _split_lines(str(content or ""))
    while content_lines and not content_lines[0].strip():
        content_lines.pop(0)
    while content_lines and not content_lines[-1].strip():
        content_lines.pop()
    block: list[str] = []
    if content_lines:
        if content_lines[0].strip():
            block.append("")
        block.extend(content_lines)
        block.append("")
    rebuilt = lines[: sec.start + 1] + block + lines[sec.end :]
    return "\n".join(rebuilt).strip()
def _apply_append_section_content_op(text: str, title: str, content: str) -> str:
    content_lines = _split_lines(str(content or ""))
    while content_lines and not content_lines[0].strip():
        content_lines.pop(0)
    while content_lines and not content_lines[-1].strip():
        content_lines.pop()
    if not content_lines:
        return text
    lines = _split_lines(text)
    sections = _extract_sections(text)
    sec = _find_section(sections, title)
    if not sec:
        return text
    insert_idx = sec.end
    _insert_block(lines, insert_idx, content_lines)
    return "\n".join(lines).strip()
def _apply_merge_sections_op(text: str, first: str, second: str) -> str:
    lines = _split_lines(text)
    sections = _extract_sections(text)
    sec_second = _find_section(sections, second)
    sec_first = _find_section(sections, first)
    if not sec_first or not sec_second or sec_first.start == sec_second.start:
        return text
    content_second = lines[sec_second.start + 1:sec_second.end]
    del lines[sec_second.start:sec_second.end]
    rebuilt = "\n".join(lines)
    sections = _extract_sections(rebuilt)
    sec_first = _find_section(sections, first)
    if not sec_first:
        return text
    insert_at = sec_first.end
    block: list[str] = []
    if insert_at > 0 and lines[insert_at - 1].strip():
        block.append("")
    block.extend(content_second)
    lines[insert_at:insert_at] = block
    return "\n".join(lines).strip()
def _apply_swap_sections_op(text: str, first: str, second: str) -> str:
    lines = _split_lines(text)
    sections = _extract_sections(text)
    sec_a = _find_section(sections, first)
    sec_b = _find_section(sections, second)
    if not sec_a or not sec_b or sec_a.start == sec_b.start:
        return text
    if sec_a.start > sec_b.start:
        sec_a, sec_b = sec_b, sec_a
    block_a = lines[sec_a.start:sec_a.end]
    block_b = lines[sec_b.start:sec_b.end]
    middle = lines[sec_a.end:sec_b.start]
    rebuilt = lines[:sec_a.start] + block_b + middle + block_a + lines[sec_b.end:]
    return "\n".join(rebuilt).strip()
def _split_paragraphs(lines: list[str]) -> list[list[str]]:
    paras: list[list[str]] = []
    buf: list[str] = []
    for line in lines:
        if line.strip():
            buf.append(line)
        else:
            if buf:
                paras.append(buf)
                buf = []
    if buf:
        paras.append(buf)
    return paras
def _apply_split_section_op(text: str, title: str, new_titles: list[str]) -> str:
    if not new_titles:
        return text
    lines = _split_lines(text)
    sections = _extract_sections(text)
    sec = _find_section(sections, title)
    if not sec:
        return text
    level = sec.level
    content_lines = lines[sec.start + 1:sec.end]
    paragraphs = _split_paragraphs(content_lines)
    n = len(new_titles)
    groups: list[list[str]] = [[] for _ in range(n)]
    if paragraphs:
        import math
        chunk = max(1, int(math.ceil(len(paragraphs) / n)))
        for i in range(n):
            chunk_paras = paragraphs[i * chunk:(i + 1) * chunk]
            block: list[str] = []
            for p in chunk_paras:
                if block:
                    block.append("")
                block.extend(p)
            groups[i] = block
    new_blocks: list[str] = []
    for i, t in enumerate(new_titles):
        heading = f"{'#' * level} {t}"
        new_blocks.append(heading)
        if groups[i]:
            new_blocks.extend(groups[i])
        new_blocks.append("")
    # remove trailing empty line
    while new_blocks and not new_blocks[-1].strip():
        new_blocks.pop()
    rebuilt = lines[:sec.start] + new_blocks + lines[sec.end:]
    return "\n".join(rebuilt).strip()
def _match_section_index(sections: list[SectionSpan], title: str, used: set[int]) -> int | None:
    target = _normalize_heading_text(title)
    for idx, sec in enumerate(sections):
        if idx in used:
            continue
        if _normalize_heading_text(sec.title) == target:
            return idx
    for idx, sec in enumerate(sections):
        if idx in used:
            continue
        norm = _normalize_heading_text(sec.title)
        if target in norm or norm in target:
            return idx
    return None
def _apply_reorder_sections_op(text: str, order: list[str]) -> str:
    if not order:
        return text
    lines = _split_lines(text)
    sections = _extract_sections(text, prefer_levels=(2,))
    if not sections:
        sections = _extract_sections(text, prefer_levels=(1, 2, 3))
    if not sections:
        return text
    blocks = [lines[s.start:s.end] for s in sections]
    used: set[int] = set()
    order_idx: list[int] = []
    for title in order:
        idx = _match_section_index(sections, title, used)
        if idx is not None:
            used.add(idx)
            order_idx.append(idx)
    remaining = [i for i in range(len(sections)) if i not in used]
    new_blocks = [blocks[i] for i in order_idx] + [blocks[i] for i in remaining]
    prefix = lines[:sections[0].start]
    suffix = lines[sections[-1].end:]
    merged: list[str] = []
    for block in new_blocks:
        if merged and merged[-1].strip() and block and block[0].strip():
            merged.append("")
        merged.extend(block)
    rebuilt = prefix + merged + suffix
    return "\n".join(rebuilt).strip()
def _apply_edit_op(text: str, op: EditOp) -> str:
    kind = op.op
    args = op.args or {}
    if kind == "set_title":
        return _apply_set_title(text, str(args.get("title") or ""))
    if kind == "replace_text":
        return _apply_replace_text(
            text,
            str(args.get("old") or ""),
            str(args.get("new") or ""),
            replace_all=bool(args.get("all")),
        )
    if kind == "rename_section":
        return _apply_rename_section(text, str(args.get("old") or ""), str(args.get("new") or ""))
    if kind == "add_section":
        return _apply_add_section_op(
            text,
            str(args.get("title") or ""),
            anchor=str(args.get("anchor") or "") or None,
            position=str(args.get("position") or "after"),
            level=args.get("level"),
        )
    if kind == "delete_section":
        return _apply_delete_section_op(
            text,
            title=str(args.get("title") or "") or None,
            index=int(args.get("index") or 0) or None,
        )
    if kind == "move_section":
        return _apply_move_section_op(
            text,
            str(args.get("title") or ""),
            str(args.get("anchor") or ""),
            position=str(args.get("position") or "after"),
        )
    if kind == "replace_section_content":
        return _apply_replace_section_content_op(
            text,
            str(args.get("title") or ""),
            str(args.get("content") or ""),
        )
    if kind == "append_section_content":
        return _apply_append_section_content_op(
            text,
            str(args.get("title") or ""),
            str(args.get("content") or ""),
        )
    if kind == "merge_sections":
        return _apply_merge_sections_op(
            text,
            str(args.get("first") or ""),
            str(args.get("second") or ""),
        )
    if kind == "swap_sections":
        return _apply_swap_sections_op(
            text,
            str(args.get("first") or ""),
            str(args.get("second") or ""),
        )
    if kind == "split_section":
        titles = args.get("new_titles")
        if not isinstance(titles, list):
            titles = []
        return _apply_split_section_op(
            text,
            str(args.get("title") or ""),
            [str(t) for t in titles if str(t).strip()],
        )
    if kind == "reorder_sections":
        order = args.get("order")
        if not isinstance(order, list):
            order = []
        return _apply_reorder_sections_op(
            text,
            [str(t) for t in order if str(t).strip()],
        )
    return text
def _apply_edit_ops(text: str, ops: list[EditOp]) -> str:
    cur = text or ""
    for op in ops:
        cur = _apply_edit_op(cur, op)
    return cur
def _parse_chinese_number(token: str) -> int | None:
    token = str(token or "").strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    mapping = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    total = 0
    if token == "十":
        return 10
    if "十" in token:
        parts = token.split("十")
        if parts[0]:
            total += mapping.get(parts[0], 0) * 10
        else:
            total += 10
        if len(parts) > 1 and parts[1]:
            total += mapping.get(parts[1], 0)
        return total if total > 0 else None
    if token in mapping:
        return mapping[token]
    return None
def _clean_section_title(text: str) -> str:
    t = _clean_title_candidate(text)
    t = re.sub(r"(章节|小节|部分|标题|题目)$", "", t).strip()
    return t
def _split_title_list(raw: str) -> list[str]:
    s = str(raw or "").strip()
    if not s:
        return []
    for sep in ["并且", "同时", "以及", "并", "及", "和", "与"]:
        s = s.replace(sep, "、")
    s = re.sub(r"[，,;；/]+", "、", s)
    parts = [p.strip() for p in s.split("、") if p.strip()]
    cleaned = [_clean_section_title(p) for p in parts]
    return [p for p in cleaned if p]
def _parse_edit_ops(raw: str) -> list[EditOp]:
    s = (raw or "").strip()
    if not s:
        return []
    s = re.sub(r"^(请|麻烦|帮我|请帮我|帮忙)", "", s).strip()
    clauses = _split_instruction_clauses(s)
    rules = _load_edit_rules()
    ops: list[EditOp] = []
    if rules:
        for clause in clauses:
            matched = False
            for rule in rules:
                if not rule.op:
                    continue
                m = rule.regex.search(clause)
                if not m:
                    continue
                args = _build_rule_args(rule, m, clause)
                if args is None:
                    continue
                ops.append(EditOp(rule.op, args))
                matched = True
                break
            if not matched and len(clauses) == 1:
                break
    if ops:
        return ops
    # Fallback heuristics if rules are missing or no match
    title = _extract_title_change(s)
    if title:
        return [EditOp("set_title", {"title": title})]
    pair = _extract_replace_pair(s)
    if pair:
        old, new = pair
        replace_all = bool(re.search(r"(全部|所有|全文)", s))
        return [EditOp("replace_text", {"old": old, "new": new, "all": replace_all})]
    m = re.search(r"在(.{1,40}?)(之后|后面|后)\s*(?:新增|添加|插入)(?:一|1)?(?:个)?(?:章节|小节|部分)?\s*(.+)", s)
    if m:
        anchor = _clean_section_title(m.group(1))
        title = _clean_section_title(m.group(3))
        if anchor and title:
            return [EditOp("add_section", {"title": title, "anchor": anchor, "position": "after"})]
    m = re.search(r"在(.{1,40}?)(之前|前面|前)\s*(?:新增|添加|插入)(?:一|1)?(?:个)?(?:章节|小节|部分)?\s*(.+)", s)
    if m:
        anchor = _clean_section_title(m.group(1))
        title = _clean_section_title(m.group(3))
        if anchor and title:
            return [EditOp("add_section", {"title": title, "anchor": anchor, "position": "before"})]
    m = re.search(r"(?:新增|添加|插入)(?:一|1)?(?:个)?(?:章节|小节|部分)?\s*(.+)", s)
    if m:
        title = _clean_section_title(m.group(1))
        if title:
            return [EditOp("add_section", {"title": title})]
    m = re.search(r"(?:删除|移除|去掉)第?([0-9一二三四五六七八九十]+)(?:章|节|部分)", s)
    if m:
        idx = _parse_chinese_number(m.group(1))
        if idx:
            return [EditOp("delete_section", {"index": idx})]
    m = re.search(r"(?:删除|移除|去掉)(?:章节|小节|部分)?\s*(.+)", s)
    if m:
        title = _clean_section_title(m.group(1))
        if title:
            return [EditOp("delete_section", {"title": title})]
    m = re.search(r"(?:把|将)?(.{1,40}?)(?:章节|小节|部分)?(?:移到|移动到|放到|放在|调整到)\s*(.{1,40}?)(之后|后面|后)", s)
    if m:
        title = _clean_section_title(m.group(1))
        anchor = _clean_section_title(m.group(2))
        if title and anchor:
            return [EditOp("move_section", {"title": title, "anchor": anchor, "position": "after"})]
    m = re.search(r"(?:把|将)?(.{1,40}?)(?:章节|小节|部分)?(?:移到|移动到|放到|放在|调整到)\s*(.{1,40}?)(之前|前面|前)", s)
    if m:
        title = _clean_section_title(m.group(1))
        anchor = _clean_section_title(m.group(2))
        if title and anchor:
            return [EditOp("move_section", {"title": title, "anchor": anchor, "position": "before"})]
    m = re.search(r"(?:合并|整合|并入)\s*(.{1,40}?)\s*(?:和|与|、)\s*(.{1,40})", s)
    if m:
        first = _clean_section_title(m.group(1))
        second = _clean_section_title(m.group(2))
        if first and second:
            return [EditOp("merge_sections", {"first": first, "second": second})]
    m = re.search(r"(?:交换|互换|调换|对调)\s*(.{1,40}?)\s*(?:和|与|、)\s*(.{1,40})", s)
    if m:
        first = _clean_section_title(m.group(1))
        second = _clean_section_title(m.group(2))
        if first and second:
            return [EditOp("swap_sections", {"first": first, "second": second})]
    m = re.search(r"(?:拆分|拆成|分拆|分成)\s*(.{1,40}?)(?:章节|小节|部分)?\s*(?:为|成)\s*(.+)", s)
    if m:
        title = _clean_section_title(m.group(1))
        new_titles = _split_title_list(m.group(2))
        if title and new_titles:
            return [EditOp("split_section", {"title": title, "new_titles": new_titles})]
    m = re.search(r"(?:章节顺序|顺序|章节顺序调整|顺序调整|重排|排序|排列).{0,6}(?:为|改为|调整为|变为)\s*(.+)", s)
    if m:
        order = _split_title_list(m.group(1))
        if order:
            return [EditOp("reorder_sections", {"order": order})]
    m = re.search(r"按(.+?)顺序(?:重排|排序|排列)", s)
    if m:
        order = _split_title_list(m.group(1))
        if order:
            return [EditOp("reorder_sections", {"order": order})]
    return []
def _build_quick_edit_note(ops: list[EditOp]) -> str:
    if not ops:
        return "已完成快速修改"
    if len(ops) > 1:
        return f"已完成{len(ops)}项修改"
    op = ops[0]
    args = op.args or {}
    if op.op == "set_title":
        return f"已更新标题为「{args.get('title', '')}」"
    if op.op == "replace_text":
        return f"已将“{args.get('old', '')}”替换为“{args.get('new', '')}”"
    if op.op == "rename_section":
        return f"已将章节“{args.get('old', '')}”改为“{args.get('new', '')}”"
    if op.op == "add_section":
        return f"已新增章节「{args.get('title', '')}」"
    if op.op == "delete_section":
        if args.get('index'):
            return f"已删除第{args.get('index')}章"
        return f"已删除章节「{args.get('title', '')}」"
    if op.op == "move_section":
        return f"已调整章节「{args.get('title', '')}」位置"
    if op.op == "replace_section_content":
        return f"已更新章节内容「{args.get('title', '')}」"
    if op.op == "append_section_content":
        return f"已追加章节内容「{args.get('title', '')}」"
    if op.op == "merge_sections":
        return f"已合并章节「{args.get('first', '')}」与「{args.get('second', '')}」"
    if op.op == "swap_sections":
        return f"已交换章节「{args.get('first', '')}」与「{args.get('second', '')}」"
    if op.op == "split_section":
        titles = args.get('new_titles') if isinstance(args.get('new_titles'), list) else []
        name = " / ".join([str(t) for t in titles if str(t).strip()])
        return f"已拆分章节「{args.get('title', '')}」为「{name}」" if name else "已拆分章节"
    if op.op == "reorder_sections":
        return "已按指定顺序重排章节"
    return "已完成快速修改"
def _build_outline_hint(text: str, *, limit: int = 20) -> str:
    sections = _extract_sections(text, prefer_levels=(1, 2))
    titles = [s.title for s in sections[:limit] if str(s.title or '').strip()]
    if not titles:
        return ""
    return "\n".join([f"- {t}" for t in titles])
def _parse_edit_ops_with_model(raw: str, text: str) -> list[EditOp]:
    base_text = str(text or "")
    if not base_text.strip():
        return []
    settings = get_ollama_settings()
    if not settings.enabled:
        return []
    model = os.environ.get("WRITING_AGENT_EDIT_PARSE_MODEL", "").strip() or os.environ.get("WRITING_AGENT_REVISE_MODEL", "").strip() or settings.model
    timeout_raw = os.environ.get("WRITING_AGENT_EDIT_PARSE_TIMEOUT_S", "").strip()
    try:
        timeout_s = max(4.0, float(timeout_raw)) if timeout_raw else 12.0
    except Exception:
        timeout_s = 12.0
    client = OllamaClient(base_url=settings.base_url, model=model, timeout_s=timeout_s)
    if not client.is_running():
        return []
    outline_hint = _build_outline_hint(base_text)
    system = """你是文档修改指令解析器，只输出JSON，不要Markdown。
Schema: {ops:[{op:string,args:object}]}
允许的op: set_title, replace_text, rename_section, add_section, delete_section, move_section, replace_section_content, append_section_content, merge_sections, swap_sections, split_section, reorder_sections。
规则：
1) 如果无法解析为结构化操作，返回 {ops: []}。
2) 不要虚构章节名；尽量匹配已知章节。
3) args字段只包含必要键。
4) 不输出解释文字。"""
    user = f"""修改指令：{raw}
已知章节：
{outline_hint or '（无）'}
请输出JSON。"""
    try:
        out = client.chat(system=system, user=user, temperature=0.0).strip()
    except Exception:
        return []
    raw_json = _extract_json_block(out)
    if not raw_json:
        return []
    try:
        data = json.loads(raw_json)
    except Exception:
        return []
    ops_raw = data.get("ops") if isinstance(data, dict) else None
    if not isinstance(ops_raw, list):
        return []
    allowed = {
        "set_title",
        "replace_text",
        "rename_section",
        "add_section",
        "delete_section",
        "move_section",
        "replace_section_content",
        "append_section_content",
        "merge_sections",
        "swap_sections",
        "split_section",
        "reorder_sections",
    }
    ops: list[EditOp] = []
    for item in ops_raw[:5]:
        if not isinstance(item, dict):
            continue
        op = str(item.get("op") or "").strip()
        if op not in allowed:
            continue
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        args = dict(args)
        if op in {
            "rename_section",
            "add_section",
            "delete_section",
            "move_section",
            "replace_section_content",
            "append_section_content",
            "merge_sections",
            "swap_sections",
        }:
            for key in list(args.keys()):
                if key in {"title", "anchor", "old", "new", "first", "second"}:
                    args[key] = _clean_section_title(args.get(key))
        if op == "set_title" and "title" in args:
            args["title"] = _clean_title_candidate(args.get("title"))
        if op == "replace_text":
            if "old" in args:
                args["old"] = _strip_quotes(args.get("old"))
            if "new" in args:
                args["new"] = _strip_quotes(args.get("new"))
            if "all" in args:
                args["all"] = bool(args.get("all"))
        if op in {"replace_section_content", "append_section_content"}:
            if "title" in args:
                args["title"] = _clean_section_title(args.get("title"))
            if "content" in args:
                args["content"] = _strip_quotes(args.get("content"))
        if op == "delete_section" and "index" in args:
            try:
                args["index"] = int(args.get("index"))
            except Exception:
                args["index"] = _parse_chinese_number(str(args.get("index")))
        if op == "split_section":
            args["title"] = _clean_section_title(args.get("title"))
            new_titles = args.get("new_titles")
            if isinstance(new_titles, str):
                new_titles = _split_title_list(new_titles)
            if not isinstance(new_titles, list):
                new_titles = []
            args["new_titles"] = [_clean_section_title(t) for t in new_titles if str(t).strip()]
        if op == "reorder_sections":
            order = args.get("order")
            if isinstance(order, str):
                order = _split_title_list(order)
            if not isinstance(order, list):
                order = []
            args["order"] = [_clean_section_title(t) for t in order if str(t).strip()]
        if op == "swap_sections":
            args["first"] = _clean_section_title(args.get("first"))
            args["second"] = _clean_section_title(args.get("second"))
        # basic validation
        if op == "set_title" and not str(args.get("title") or "").strip():
            continue
        if op == "replace_text" and (not str(args.get("old") or "").strip() or not str(args.get("new") or "").strip()):
            continue
        if op == "rename_section" and (not str(args.get("old") or "").strip() or not str(args.get("new") or "").strip()):
            continue
        if op == "add_section" and not str(args.get("title") or "").strip():
            continue
        if op == "delete_section" and not (args.get("index") or str(args.get("title") or "").strip()):
            continue
        if op == "move_section" and (not str(args.get("title") or "").strip() or not str(args.get("anchor") or "").strip()):
            continue
        if op in {"replace_section_content", "append_section_content"} and (
            not str(args.get("title") or "").strip() or not str(args.get("content") or "").strip()
        ):
            continue
        if op == "merge_sections" and (not str(args.get("first") or "").strip() or not str(args.get("second") or "").strip()):
            continue
        if op == "swap_sections" and (not str(args.get("first") or "").strip() or not str(args.get("second") or "").strip()):
            continue
        if op == "split_section" and (not str(args.get("title") or "").strip() or len(args.get("new_titles") or []) < 2):
            continue
        if op == "reorder_sections" and len(args.get("order") or []) < 2:
            continue
        ops.append(EditOp(op, args))
    return ops
def _try_quick_edit(text: str, instruction: str) -> tuple[str, str] | None:
    raw = (instruction or "").strip()
    if not raw:
        return None
    ops = _parse_edit_ops(raw)
    if not ops and _looks_like_modify_instruction(raw):
        ops = _parse_edit_ops_with_model(raw, text)
    if not ops:
        return None
    updated = _apply_edit_ops(text or "", ops)
    if updated.strip() != (text or "").strip():
        return updated, _build_quick_edit_note(ops)
    return None
def _should_try_ai_edit(raw: str, text: str, analysis: dict | None = None) -> bool:
    if not str(text or "").strip():
        return False
    compact = re.sub(r"\s+", "", str(raw or ""))
    if not compact:
        return False
    if re.search(r"(生成|撰写|起草|写一|输出|制作|形成|写作)", compact) and not _looks_like_modify_instruction(raw):
        return False
    if _looks_like_modify_instruction(raw):
        return True
    if re.search(r"(加上|补上|统一|整理|调整|格式|样式|字体|编号|数字符号|标号|小标题|段落|标题)", compact):
        return True
    if isinstance(analysis, dict):
        intent = analysis.get("intent")
        if isinstance(intent, dict):
            name = str(intent.get("name") or "").strip().lower()
            try:
                conf = float(intent.get("confidence") or 0)
            except Exception:
                conf = 0.0
            if name in {"modify", "format", "outline"} and conf >= 0.3:
                return True
            if name == "generate" and conf >= 0.6:
                return False
    return False
def _try_ai_intent_edit(text: str, instruction: str, analysis: dict | None = None) -> tuple[str, str] | None:
    if not _should_try_ai_edit(instruction, text, analysis):
        return None
    ops = _parse_edit_ops_with_model(instruction, text)
    if not ops:
        return None
    updated = _apply_edit_ops(text or "", ops)
    if updated.strip() != (text or "").strip():
        return updated, _build_quick_edit_note(ops)
    return None
def _looks_like_modify_instruction(raw: str) -> bool:
    s = (raw or "").strip()
    if not s:
        return False
    compact = re.sub(r"\s+", "", s)
    if re.search(
        r"(修改|润色|改写|优化|调整|替换|改为|改成|删减|删除|去掉|补充|扩写|简化|校对|纠错|统一|合并|拆分|分拆|分成|新增|添加|插入|移动|移到|放到|重排|排序|顺序|交换|互换|对调)",
        compact,
    ):
        return True
    if re.search(r"(把|将).{1,80}(改为|改成|替换为|换成|移到|放到).{1,80}", compact):
        return True
    if re.search(r"(标题|题目).{0,6}(改为|改成|调整|设置)", compact):
        return True
    if re.search(r"(删除|移除|去掉).{0,8}(章节|小节|部分|标题)", compact):
        return True
    if re.search(r"(合并|拆分|分拆|分成|交换|互换|对调).{1,20}(章节|小节|部分)", compact):
        return True
    return False
def _should_route_to_revision(raw: str, text: str, analysis: dict | None = None) -> bool:
    if not str(text or "").strip():
        return False
    compact = re.sub(r"\s+", "", str(raw or ""))
    if not compact:
        return False
    if _looks_like_modify_instruction(raw):
        return True
    if re.search(r"(生成|撰写|起草|写一份|写一篇|写个|输出|制作|形成)", compact):
        return False
    if isinstance(analysis, dict):
        intent = analysis.get("intent")
        if isinstance(intent, dict):
            name = str(intent.get("name") or "").strip().lower()
            try:
                conf = float(intent.get("confidence") or 0)
            except Exception:
                conf = 0.0
            if name == "modify" and conf >= 0.45:
                return True
            if name == "generate" and conf >= 0.6:
                return False
    return False
def _try_revision_edit(
    *,
    session,
    instruction: str,
    text: str,
    selection: str = "",
    analysis: dict | None = None,
) -> tuple[str, str] | None:
    raw = str(instruction or "").strip()
    base_text = str(text or "")
    if not raw or not base_text.strip():
        return None
    settings = get_ollama_settings()
    if not settings.enabled:
        return None
    model = os.environ.get("WRITING_AGENT_REVISE_MODEL", "").strip() or settings.model
    client = OllamaClient(base_url=settings.base_url, model=model, timeout_s=settings.timeout_s)
    if not client.is_running():
        return None
    analysis_instruction = raw
    if isinstance(analysis, dict):
        analysis_instruction = str(analysis.get("rewritten_query") or raw).strip() or raw
    selection_text = str(selection or "").strip()
    if selection_text:
        system = (
            "你是文档修改助手，只改写“选中段落”。\n"
            "要求：\n"
            "1) 仅输出改写后的段落文本，不要输出标题或额外说明。\n"
            "2) 保持原意与结构，语言更清晰专业。\n"
            "3) 不新增事实/数据/引用；禁止占位符或自我指涉。\n"
        )
        user = (
            f"选中段落：\n{selection_text}\n\n"
            f"修改要求：\n{analysis_instruction}\n\n"
            "请输出改写后的段落。"
        )
    else:
        system = (
            "你是文档修改助手，需要按要求改写全文，但必须保持章节结构与顺序。\n"
            "要求：\n"
            "1) 仅输出纯文本，保留 # / ## / ### 标题行。\n"
            "2) 不删除正文段落（除非明显重复/乱码）；不改变章节顺序。\n"
            "3) 不编造事实/数据/引用；禁止占位符或自我指涉。\n"
            "4) 保留 [[TABLE:...]] / [[FIGURE:...]] 标记。\n"
        )
        user = (
            f"修改要求：\n{analysis_instruction}\n\n"
            f"原文：\n{base_text}\n\n"
            "请输出修改后的全文。"
        )
    buf: list[str] = []
    try:
        for delta in client.chat_stream(system=system, user=user, temperature=0.25):
            buf.append(delta)
    except Exception:
        return None
    rewritten = _sanitize_output_text("".join(buf).strip())
    if not rewritten:
        return None
    if selection_text and selection_text in base_text:
        updated = base_text.replace(selection_text, rewritten, 1)
    else:
        updated = rewritten if not selection_text else base_text
    updated = _replace_question_headings(updated)
    updated = _sanitize_output_text(updated)
    if not updated.strip():
        return None
    return updated, "已按修改指令更新内容"
def _analysis_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_ANALYSIS_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(2.0, float(raw))
        except Exception:
            pass
    return 45.0
def _revision_decision_with_model(
    *,
    base_url: str,
    model: str,
    instruction: str,
    selection: str,
    text: str,
) -> dict:
    snippet = (selection or "").strip()
    if not snippet:
        snippet = (text or "")[:2000]
    client = OllamaClient(base_url=base_url, model=model, timeout_s=30.0)
    system = (
        "你是文档修改决策Agent，只输出JSON，不要Markdown，不要多余文字。\n"
        "Schema: {should_apply:boolean,reason:string,plan:[string]}。\n"
        "规则：先思考修改要点，再判断是否需要修改；若不需要修改，should_apply=false并说明原因；"
        "若需要修改，plan写出2-5条可执行步骤。\n"
        "示例：{\"should_apply\":true,\"reason\":\"用户要求调整语气\",\"plan\":[\"保留原意\",\"替换口语表达\",\"检查衔接\"]}\n"
    )
    user = (
        f"修改要求：{instruction}\n"
        f"选中内容：{selection or '（无）'}\n"
        f"文档片段：\n{snippet}\n\n"
        "请输出决策JSON。"
    )
    try:
        raw = client.chat(system=system, user=user, temperature=0.1).strip()
    except Exception:
        return {"should_apply": True, "reason": "", "plan": []}
    raw_json = _extract_json_block(raw)
    if not raw_json:
        return {"should_apply": True, "reason": "", "plan": []}
    try:
        data = json.loads(raw_json)
    except Exception:
        return {"should_apply": True, "reason": "", "plan": []}
    return data if isinstance(data, dict) else {"should_apply": True, "reason": "", "plan": []}
def _extract_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_EXTRACT_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(4.0, float(raw))
        except Exception:
            pass
    return 20.0
def _analysis_model_name(settings) -> str:
    cand = os.environ.get("WRITING_AGENT_ANALYSIS_MODEL", "").strip()
    if cand:
        return cand
    cand = os.environ.get("WRITING_AGENT_AGG_MODEL", "").strip()
    if cand:
        return cand
    return settings.model
def _build_analysis_context(session) -> str:
    parts: list[str] = []
    prefs = session.generation_prefs or {}
    fmt = session.formatting or {}
    if session.template_source_name:
        parts.append(f"模板:{session.template_source_name}")
    if prefs.get("purpose"):
        parts.append(f"用途:{prefs.get('purpose')}")
    mode = str(prefs.get("target_length_mode") or "").strip().lower()
    val = prefs.get("target_length_value")
    if mode in {"chars", "pages"} and val:
        unit = "字" if mode == "chars" else "页"
        parts.append(f"长度:{val}{unit}")
    if "expand_outline" in prefs:
        parts.append(f"层级展开:{'是' if prefs.get('expand_outline') else '否'}")
    if fmt.get("font_name_east_asia") or fmt.get("font_size_name") or fmt.get("font_size_pt"):
        size = fmt.get("font_size_name") or (f"{fmt.get('font_size_pt')}pt" if fmt.get("font_size_pt") else "")
        parts.append(f"正文:{fmt.get('font_name_east_asia') or ''} {size}".strip())
    if fmt.get("heading1_font_name_east_asia") or fmt.get("heading1_size_pt"):
        parts.append(f"标题:{fmt.get('heading1_font_name_east_asia') or ''} {fmt.get('heading1_size_pt') or ''}pt".strip())
    return "；".join([p for p in parts if p])
def _normalize_analysis(data: object, raw_text: str) -> dict:
    base = {
        "intent": {"name": "other", "confidence": 0.1, "reason": ""},
        "rewritten_query": raw_text.strip(),
        "decomposition": [],
        "constraints": [],
        "missing": [],
        "entities": {},
    }
    if not isinstance(data, dict):
        return base
    intent = data.get("intent")
    if isinstance(intent, dict):
        name = str(intent.get("name") or "").strip() or "other"
        conf = intent.get("confidence")
        try:
            conf_val = float(conf)
        except Exception:
            conf_val = 0.1
        base["intent"] = {"name": name, "confidence": max(0.0, min(1.0, conf_val)), "reason": str(intent.get("reason") or "")}
    rewritten = str(data.get("rewritten_query") or "").strip()
    if rewritten:
        base["rewritten_query"] = rewritten
    decomp = data.get("decomposition")
    if isinstance(decomp, list):
        base["decomposition"] = [str(x).strip() for x in decomp if str(x).strip()][:12]
    constraints = data.get("constraints")
    if isinstance(constraints, list):
        base["constraints"] = [str(x).strip() for x in constraints if str(x).strip()][:12]
    missing = data.get("missing")
    if isinstance(missing, list):
        base["missing"] = [str(x).strip() for x in missing if str(x).strip()][:12]
    entities = data.get("entities")
    if isinstance(entities, dict):
        base["entities"] = {k: str(v).strip() for k, v in entities.items() if str(v).strip()}
    return base
def _compose_analysis_input(text: str, analysis: dict) -> str:
    base = str(analysis.get("rewritten_query") or "").strip() or str(text or "").strip()
    parts = [base]
    decomp = analysis.get("decomposition") if isinstance(analysis, dict) else None
    if isinstance(decomp, list) and decomp:
        parts.append("拆解要点：\n- " + "\n- ".join([str(x).strip() for x in decomp if str(x).strip()][:8]))
    intent = analysis.get("intent") if isinstance(analysis, dict) else None
    if isinstance(intent, dict) and intent.get("name"):
        parts.append(f"意图:{str(intent.get('name')).strip()}")
    constraints = analysis.get("constraints") if isinstance(analysis, dict) else None
    if isinstance(constraints, list) and constraints:
        parts.append("硬性约束：" + "；".join([str(x).strip() for x in constraints if str(x).strip()][:8]))
    missing = analysis.get("missing") if isinstance(analysis, dict) else None
    if isinstance(missing, list) and missing:
        parts.append("待确认：" + "；".join([str(x).strip() for x in missing if str(x).strip()][:8]))
    merged = "\n\n".join([p for p in parts if p])
    return merged.strip()
def _build_pref_summary(raw: str, analysis: dict, title: str, fmt: dict, prefs: dict) -> str:
    parts: list[str] = []
    clean_title = str(title or "").strip()
    if clean_title:
        parts.append(f"\u4e3b\u9898\uff1a{clean_title}")
    purpose = str(prefs.get("purpose") or "").strip() if isinstance(prefs, dict) else ""
    if purpose:
        parts.append(f"\u7528\u9014\uff1a{purpose}")
    mode = str(prefs.get("target_length_mode") or "").strip().lower() if isinstance(prefs, dict) else ""
    val = prefs.get("target_length_value") if isinstance(prefs, dict) else None
    if mode in {"chars", "pages"} and val:
        unit = "\u5b57" if mode == "chars" else "\u9875"
        parts.append(f"\u957f\u5ea6\uff1a\u7ea6{val}{unit}")
    if isinstance(fmt, dict):
        font = str(fmt.get("font_name_east_asia") or fmt.get("font_name") or "").strip()
        size = fmt.get("font_size_name") or (f"{fmt.get('font_size_pt')}pt" if fmt.get("font_size_pt") else "")
        if font or size:
            parts.append(f"\u6b63\u6587\uff1a{font} {size}".strip())
        h1 = fmt.get("heading1_size_pt")
        if h1:
            parts.append(f"\u6807\u9898\u5b57\u53f7\uff1a{h1}pt")
    decomp = analysis.get("decomposition") if isinstance(analysis, dict) else None
    if isinstance(decomp, list) and decomp:
        items = [str(x).strip() for x in decomp if str(x).strip()][:5]
        if items:
            parts.append("\u5185\u5bb9\u8981\u70b9\uff1a" + "\u3001".join(items))
    constraints = analysis.get("constraints") if isinstance(analysis, dict) else None
    if isinstance(constraints, list) and constraints:
        items = [str(x).strip() for x in constraints if str(x).strip()][:4]
        if items:
            parts.append("\u7ea6\u675f\uff1a" + "\u3001".join(items))
    entities = analysis.get("entities") if isinstance(analysis, dict) else None
    if isinstance(entities, dict):
        audience = str(entities.get("audience") or "").strip()
        if audience:
            parts.append(f"\u53d7\u4f17\uff1a{audience}")
        output_form = str(entities.get("output_form") or "").strip()
        if output_form:
            parts.append(f"\u8f93\u51fa\u5f62\u5f0f\uff1a{output_form}")
        voice = str(entities.get("voice") or "").strip()
        if voice:
            parts.append(f"\u8bed\u6c14/\u98ce\u683c\uff1a{voice}")
        scope = str(entities.get("scope") or "").strip()
        if scope:
            parts.append(f"\u5185\u5bb9\u8303\u56f4\uff1a{scope}")
        avoid = str(entities.get("avoid") or "").strip()
        if avoid:
            parts.append(f"\u907f\u514d/\u4e0d\u8981\uff1a{avoid}")
    if not parts:
        base = str(analysis.get("rewritten_query") or raw or "").strip()
        if base:
            return f"\u6211\u7406\u89e3\u4f60\u7684\u9700\u6c42\u662f\uff1a{base}"
        return ""
    return "\u6211\u7406\u89e3\u4f60\u7684\u9700\u6c42\u5982\u4e0b\uff1a\n" + "\n".join(parts)
def _field_confidence(raw: str, analysis: dict, title: str, prefs: dict, fmt: dict) -> dict:
    raw_s = (raw or "").strip()
    ent = analysis.get("entities") if isinstance(analysis, dict) else None
    ent = ent if isinstance(ent, dict) else {}
    conf: dict[str, float] = {}
    # title
    if title and (title in raw_s or title in str(ent.get("title") or "")):
        conf["title"] = 0.8
    elif title:
        conf["title"] = 0.5
    # purpose
    purpose = str(prefs.get("purpose") or "").strip() if isinstance(prefs, dict) else ""
    if purpose and (purpose in raw_s or purpose in str(ent.get("purpose") or "")):
        conf["purpose"] = 0.8
    elif purpose:
        conf["purpose"] = 0.5
    # length
    mode = str(prefs.get("target_length_mode") or "").strip().lower() if isinstance(prefs, dict) else ""
    val = prefs.get("target_length_value") if isinstance(prefs, dict) else None
    if mode in {"chars", "pages"} and val:
        if re.search(r"\d+\s*(?:\u5b57|\u5b57\u7b26|\u9875|\u9762|\u4e07\u5b57)", raw_s):
            conf["length"] = 0.8
        else:
            conf["length"] = 0.5
    # formatting
    if isinstance(fmt, dict) and fmt:
        if re.search(r"\u5b57\u53f7|\u5b57\u4f53|\u884c\u8ddd|\u6392\u7248", raw_s):
            conf["format"] = 0.7
        else:
            conf["format"] = 0.45
    return conf
def _low_conf_questions(conf: dict) -> list[str]:
    out: list[str] = []
    if conf.get("title", 1.0) < 0.6:
        out.append("\u6807\u9898\u53ef\u80fd\u7406\u89e3\u4e0d\u51c6\uff0c\u8bf7\u786e\u8ba4\u6807\u9898\u3002")
    if conf.get("purpose", 1.0) < 0.6:
        out.append("\u7528\u9014/\u573a\u666f\u53ef\u80fd\u4e0d\u660e\u786e\uff0c\u8bf7\u8865\u5145\u3002")
    if conf.get("length", 1.0) < 0.6:
        out.append("\u957f\u5ea6\u53ef\u80fd\u4e0d\u51c6\uff0c\u8bf7\u786e\u8ba4\u5b57\u6570/\u9875\u6570\u3002")
    if conf.get("format", 1.0) < 0.5:
        out.append("\u683c\u5f0f/\u6392\u7248\u8981\u6c42\u4e0d\u660e\u786e\uff0c\u6709\u7684\u8bdd\u8bf7\u8865\u5145\uff0c\u6ca1\u6709\u5199\u201c\u9ed8\u8ba4\u201d\u3002")
    return out
def _prioritize_missing(raw: str, analysis: dict, items: list[str]) -> list[str]:
    if not items:
        return []
    s = (raw or "") + " " + str(analysis.get("rewritten_query") or "")
    s = s.replace(" ", "")
    priority = [
        "标题/用途",
        "格式/版式",
        "长度/字数",
        "章节结构/提纲/范围",
        "受众",
        "交付/输出要求",
        "语气/风格",
        "资料/引用/数据来源",
        "特殊约束",
    ]
    # keep only items that exist in missing list
    ordered = []
    seen = set()
    for p in priority:
        for it in items:
            if it in seen:
                continue
            if p == it:
                ordered.append(it)
                seen.add(it)
    # append any remaining
    for it in items:
        if it not in seen:
            ordered.append(it)
            seen.add(it)
    return ordered
def _build_missing_questions(title: str, fmt: dict, prefs: dict, analysis: dict) -> list[str]:
    missing: list[str] = []
    clean_title = str(title or "").strip()
    if not clean_title:
        missing.append("\u4e3b\u9898/\u9898\u76ee")
    purpose = str(prefs.get("purpose") or "").strip() if isinstance(prefs, dict) else ""
    if not purpose:
        missing.append("\u7528\u9014/\u573a\u666f")
    mode = str(prefs.get("target_length_mode") or "").strip().lower() if isinstance(prefs, dict) else ""
    val = prefs.get("target_length_value") if isinstance(prefs, dict) else None
    if not (mode in {"chars", "pages"} and val):
        missing.append("\u76ee\u6807\u5b57\u6570\u6216\u9875\u6570")
    if not (isinstance(fmt, dict) and fmt):
        missing.append("\u683c\u5f0f/\u6392\u7248\u8981\u6c42\uff08\u6709\u5c31\u8bf4\uff0c\u6ca1\u6709\u5199\u201c\u9ed8\u8ba4\u201d\uff09")
    entities = analysis.get("entities") if isinstance(analysis, dict) else None
    if isinstance(entities, dict):
        audience = str(entities.get("audience") or "").strip()
        if not audience:
            missing.append("\u53d7\u4f17/\u5bf9\u8c61")
        output_form = str(entities.get("output_form") or "").strip()
        if not output_form:
            missing.append("\u8f93\u51fa\u5f62\u5f0f\uff08\u62a5\u544a/\u65b9\u6848/\u603b\u7ed3/\u6c47\u62a5\uff09")
        voice = str(entities.get("voice") or "").strip()
        if not voice:
            missing.append("\u8bed\u6c14/\u98ce\u683c")
        scope = str(entities.get("scope") or "").strip()
        if not scope:
            missing.append("\u5185\u5bb9\u8303\u56f4")
        avoid = str(entities.get("avoid") or "").strip()
        if not avoid:
            missing.append("\u4e0d\u5e0c\u671b\u51fa\u73b0\u7684\u5185\u5bb9")
    extra = analysis.get("missing") if isinstance(analysis, dict) else None
    if isinstance(extra, list):
        for item in extra:
            s = str(item).strip()
            if s and s not in missing:
                missing.append(s)
    missing = [m for m in missing if m][:4]
    if not missing:
        return []
    return ["\u8fd8\u7f3a\u8fd9\u4e9b\u5173\u952e\u4fe1\u606f\uff0c\u8bf7\u4e00\u6b21\u8865\u5145\uff1a" + "\u3001".join(missing)]
def _length_from_text(raw: str) -> tuple[str, int] | None:
    s = (raw or "").strip()
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*\u4e07\u5b57", s)
    if m:
        return ("chars", int(float(m.group(1)) * 10000))
    m = re.search(r"(\d+)\s*(?:\u5b57|\u5b57\u7b26)", s)
    if m:
        return ("chars", int(m.group(1)))
    m = re.search(r"(\d+)\s*(?:\u9875|\u9762)", s)
    if m:
        return ("pages", int(m.group(1)))
    return None
def _analysis_history_context(session, limit: int = 3) -> str:
    log = list(getattr(session, "analysis_log", []) or [])
    items = []
    for entry in log[-limit:]:
        raw = str(entry.get("raw") or "").strip()
        analysis = entry.get("analysis") if isinstance(entry, dict) else None
        summary = str((analysis or {}).get("rewritten_query") or "").strip() if isinstance(analysis, dict) else ""
        if raw:
            items.append(f"??: {raw}")
        if summary and summary != raw:
            items.append(f"????: {summary}")
    return "\n".join(items)
def _generate_dynamic_questions_with_model(
    *,
    base_url: str,
    model: str,
    raw: str,
    analysis: dict,
    history: str,
    merged: dict,
) -> dict:
    client = OllamaClient(base_url=base_url, model=model, timeout_s=_analysis_timeout_s())
    system = (
        "你是需求解析助手，只输出JSON，不要markdown。\n"
        "Schema: {summary:string, questions:[string], confidence:{title:number,purpose:number,length:number,format:number,scope:number,voice:number}}\n"
        "要求：先给summary，再给<=3条高价值澄清问题questions，并给出字段置信度confidence。\n"
        "若信息已足够，questions可以为空。\n"
    )
    payload = {"raw": raw, "analysis": analysis, "history": history, "merged": merged}
    user = (
        f"历史：{history or '空'}\n"
        f"本次输入：{raw}\n"
        f"解析中间结果：{json.dumps(payload, ensure_ascii=False)}\n"
        "请按Schema输出JSON。"
    )
    try:
        raw_out = client.chat(system=system, user=user, temperature=0.2)
    except Exception:
        return {}
    raw_json = _extract_json_block(raw_out)
    if not raw_json:
        return {}
    try:
        data = json.loads(raw_json)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
def _detect_extract_conflicts(*, analysis: dict, title: str, prefs: dict) -> list[str]:
    conflicts: list[str] = []
    entities = analysis.get("entities") if isinstance(analysis, dict) else None
    if not isinstance(entities, dict):
        return conflicts
    a_title = str(entities.get("title") or "").strip()
    if a_title and title and a_title not in title and title not in a_title:
        conflicts.append("\u6807\u9898\u7406\u89e3\u4e0d\u4e00\u81f4\uff0c\u8bf7\u786e\u8ba4\u6807\u9898\u3002")
    a_purpose = str(entities.get("purpose") or "").strip()
    p_purpose = str(prefs.get("purpose") or "").strip() if isinstance(prefs, dict) else ""
    if a_purpose and p_purpose and a_purpose not in p_purpose and p_purpose not in a_purpose:
        conflicts.append("\u7528\u9014/\u573a\u666f\u53ef\u80fd\u6709\u51fa\u5165\uff0c\u8bf7\u786e\u8ba4\u3002")
    a_len = _length_from_text(str(entities.get("length") or "")) if isinstance(entities, dict) else None
    mode = str(prefs.get("target_length_mode") or "").strip().lower() if isinstance(prefs, dict) else ""
    val = prefs.get("target_length_value") if isinstance(prefs, dict) else None
    if a_len and mode in {"chars", "pages"} and val:
        a_mode, a_val = a_len
        try:
            v = int(val)
        except Exception:
            v = 0
        if a_mode == mode and v and abs(a_val - v) > max(80, int(0.2 * a_val)):
            conflicts.append("\u957f\u5ea6\u4fe1\u606f\u524d\u540e\u4e0d\u4e00\u81f4\uff0c\u8bf7\u786e\u8ba4\u5b57\u6570/\u9875\u6570\u3002")
    return conflicts
def _infer_role_defaults(raw: str, prefs: dict, analysis: dict) -> dict:
    p = dict(prefs or {})
    s = (raw or "") + " " + str(analysis.get("rewritten_query") or "")
    s = s.replace(" ", "")
    def _set_if_empty(key: str, val: str) -> None:
        if not p.get(key) and val:
            p[key] = val
    if any(k in s for k in ["学术", "论文", "研究", "综述"]):
        _set_if_empty("audience", "学术读者")
        _set_if_empty("voice", "学术/客观")
        _set_if_empty("output_form", "论文")
    if any(k in s for k in ["商业", "市场", "方案", "路演", "投资"]):
        _set_if_empty("audience", "业务/管理层")
        _set_if_empty("voice", "专业/说服")
        _set_if_empty("output_form", "方案")
    if any(k in s for k in ["新闻", "报道", "舆情", "播报", "简讯"]):
        _set_if_empty("audience", "大众读者")
        _set_if_empty("voice", "新闻/客观")
        _set_if_empty("output_form", "简报")
    return p
def _detect_multi_intent(text: str) -> list[str]:
    s = (text or "").replace(" ", "")
    if not s:
        return []
    # 两种及以上输出类型混杂
    if re.search(r"(报告|方案|文档).+(报告|方案|文档)", s):
        return ["检测到可能包含多个输出意图，请明确只需哪一种。"]
    # multiple deliverable keywords
    deliverables = ["报告", "方案", "PPT", "简报", "PRD", "周报", "总结"]
    hit = [d for d in deliverables if d in s]
    if len(hit) >= 2:
        return [f"同时提到：{', '.join(hit[:4])}，请确认要输出哪一种。"]
    return []
def _info_score(title: str, fmt: dict, prefs: dict, analysis: dict) -> int:
    score = 0
    if str(title or "").strip():
        score += 1
    if isinstance(prefs, dict):
        if prefs.get("purpose"):
            score += 1
        if prefs.get("target_length_mode") and prefs.get("target_length_value"):
            score += 1
        if prefs.get("output_form"):
            score += 1
        if prefs.get("audience"):
            score += 1
        if prefs.get("voice"):
            score += 1
        if prefs.get("scope"):
            score += 1
    if isinstance(fmt, dict) and fmt:
        score += 1
    return score
def _run_message_analysis(session, text: str, *, force: bool = False, quick: bool = False) -> dict:
    raw = str(text or "").strip()
    if not raw:
        return {}
    last = session.last_analysis if isinstance(session.last_analysis, dict) else {}
    last_mode = str(last.get("mode") or "")
    if not force and last.get("raw") == raw and isinstance(last.get("analysis"), dict):
        if quick or last_mode == "full":
            return last.get("analysis") or {}
    if quick:
        analysis = _normalize_analysis({}, raw)
        analysis["intent"] = _quick_intent_guess(raw)
        entry = {"time": datetime.now().isoformat(timespec="seconds"), "raw": raw, "analysis": analysis, "mode": "quick"}
        log = list(session.analysis_log or [])
        log.append(entry)
        session.analysis_log = log[-200:]
        session.last_analysis = entry
        store.put(session)
        return analysis
    inflight_key = f"{session.id}:{hash(raw)}"
    with _ANALYSIS_LOCK:
        if _ANALYSIS_INFLIGHT.get(inflight_key):
            return last.get("analysis") or _normalize_analysis({}, raw)
        _ANALYSIS_INFLIGHT[inflight_key] = time.time()
    settings = get_ollama_settings()
    try:
        if not settings.enabled:
            analysis = _normalize_analysis({}, raw)
        else:
            model = _analysis_model_name(settings)
            client = OllamaClient(base_url=settings.base_url, model=model, timeout_s=_analysis_timeout_s())
            if not client.is_running():
                analysis = _normalize_analysis({}, raw)
            else:
                context = _build_analysis_context(session)
                system = (
                    "你是对话理解引擎，只输出JSON，不要Markdown。\n"
                    "任务：Intent Detection、Query Rewriting、Query Decomposition。\n"
                    "Schema: {intent:{name:string,confidence:number,reason:string}, rewritten_query:string, decomposition:[string], "
                    "constraints:[string], missing:[string], entities:{title:string,purpose:string,length:string,formatting:string,template:string,audience:string,output_form:string,voice:string,avoid:string,scope:string}}。\n"
                    "规则：不编造；信息缺失就留空；重写需明确且不增加新需求；拆解为有序原子项。\n"
                    "intent.name 可选: generate/modify/format/outline/template/upload/export/clarify/question/other。\n"
                )
                user = f"已知上下文：{context or '无'}\n用户输入：{raw}\n请输出JSON。"
                try:
                    out = client.chat(system=system, user=user, temperature=0.1).strip()
                    raw_json = _extract_json_block(out)
                    data = json.loads(raw_json) if raw_json else {}
                    analysis = _normalize_analysis(data, raw)
                except Exception:
                    analysis = _normalize_analysis({}, raw)
    finally:
        with _ANALYSIS_LOCK:
            _ANALYSIS_INFLIGHT.pop(inflight_key, None)
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "raw": raw, "analysis": analysis, "mode": "full"}
    log = list(session.analysis_log or [])
    log.append(entry)
    session.analysis_log = log[-200:]
    session.last_analysis = entry
    store.put(session)
    return analysis
def _normalize_string_list(items: object, keys: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    if not isinstance(items, list):
        return out
    for item in items:
        val = ""
        if isinstance(item, str):
            val = item.strip()
        elif isinstance(item, dict):
            for key in keys:
                raw = item.get(key)
                if raw is None:
                    continue
                val = str(raw).strip()
                if val:
                    break
        else:
            val = str(item).strip()
        if val:
            out.append(val)
    return out
def _normalize_outline(outline_raw: object) -> list[tuple[int, str]]:
    outline: list[tuple[int, str]] = []
    if not isinstance(outline_raw, list):
        return outline
    for item in outline_raw:
        level = None
        title = None
        if isinstance(item, dict):
            level = item.get("level")
            title = item.get("title") or item.get("h2") or item.get("name") or item.get("question")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            level, title = item[0], item[1]
        elif isinstance(item, str):
            title = item
        else:
            title = str(item)
        txt = str(title or "").strip()
        if not txt:
            continue
        if re.search(r"[。！？；]", txt):
            continue
        lvl = None
        if level is not None:
            try:
                lvl = int(level)
            except Exception:
                lvl = None
        if lvl is None:
            if re.match(r"^\s*\d+(?:\.\d+){2,}\b", txt):
                lvl = 3
            elif re.match(r"^\s*\d+\.\d+\b", txt):
                lvl = 2
            else:
                lvl = 1
        if lvl < 1 or lvl > 3:
            continue
        outline.append((lvl, txt))
    return outline
def _classify_upload_with_model(
    *,
    base_url: str,
    model: str,
    filename: str,
    text: str,
) -> dict:
    snippet = (text or "").strip()
    if not snippet:
        return {"kind": "unknown", "confidence": 0.0, "reason": "empty"}
    if len(snippet) > 2800:
        snippet = snippet[:2800] + "…"
    client = OllamaClient(base_url=base_url, model=model, timeout_s=_extract_timeout_s())
    system = (
        "你是文档类型识别Agent，只输出JSON，不要Markdown，不要多余文字。\n"
        "Schema: {kind:string,confidence:number,reason:string}.\n"
        "kind 只能是 template/reference/other。\n"
        "template: 主要是章节结构、目录式标题、模板框架、章节占位。\n"
        "reference: 实际内容文档/资料/论文/报告正文。\n"
        "other: 非文档或无法判断。\n"
        "如果内容主要是章节标题/目录/结构列表，或出现“XXX：描述”这样的章节提示，应判为 template。\n"
        "如果内容以叙述性段落为主（方法、结果、分析、结论等），应判为 reference。\n"
    )
    user = f"文件名：{filename}\n内容节选：\n{snippet}\n\n请输出识别JSON。"
    try:
        raw = client.chat(system=system, user=user, temperature=0.1)
    except Exception:
        return {"kind": "unknown", "confidence": 0.0, "reason": "model_error"}
    raw_json = _extract_json_block(raw)
    if not raw_json:
        return {"kind": "unknown", "confidence": 0.0, "reason": "no_json"}
    try:
        data = json.loads(raw_json)
    except Exception:
        return {"kind": "unknown", "confidence": 0.0, "reason": "bad_json"}
    kind = str(data.get("kind") or "").strip().lower()
    conf = data.get("confidence")
    try:
        conf_val = float(conf)
    except Exception:
        conf_val = 0.0
    reason = str(data.get("reason") or "").strip()
    if kind not in {"template", "reference", "other"}:
        kind = "unknown"
    return {"kind": kind, "confidence": conf_val, "reason": reason}
def _extract_template_with_model(
    *,
    base_url: str,
    model: str,
    filename: str,
    text: str,
) -> dict:
    snippet = (text or "").strip()
    if not snippet:
        return {"name": Path(filename).stem, "outline": [], "required_h2": []}
    if len(snippet) > 4000:
        snippet = snippet[:4000] + "…"
    client = OllamaClient(base_url=base_url, model=model, timeout_s=_extract_timeout_s())
    system = (
        "你是模板结构提取Agent，只输出JSON，不要Markdown，不要多余文字。\n"
        "Schema: {name:string,outline:[{level:int,title:string}],required_h2:[string],questions:[string]}.\n"
        "规则：outline 按出现顺序输出；level 仅 1-3；不要自行新增不存在的章节。\n"
        "若模板信息不完整或含糊，给出 questions。\n"
        "如果看到“论文一般包含/章节包括/目录”等列表，或“标题：描述”的结构，请抽取标题部分为 outline。\n"
        "如果无法识别任何章节，请在 questions 中要求用户粘贴或描述章节结构。\n"
    )
    user = f"文件名：{filename}\n模板内容：\n{snippet}\n\n请输出模板结构JSON。"
    try:
        raw = client.chat(system=system, user=user, temperature=0.1)
    except Exception:
        return {"name": Path(filename).stem, "outline": [], "required_h2": []}
    raw_json = _extract_json_block(raw)
    if not raw_json:
        return {"name": Path(filename).stem, "outline": [], "required_h2": []}
    try:
        data = json.loads(raw_json)
    except Exception:
        return {"name": Path(filename).stem, "outline": [], "required_h2": []}
    outline_raw = data.get("outline") if isinstance(data, dict) else None
    outline = _normalize_outline(outline_raw)
    required_raw = data.get("required_h2") if isinstance(data, dict) else None
    required_h2 = _normalize_string_list(required_raw, ("title", "h2", "name", "text"))
    if not outline and required_h2:
        outline = [(1, txt) for txt in required_h2]
    name = str(data.get("name") or "").strip() if isinstance(data, dict) else ""
    questions = _normalize_string_list(data.get("questions") if isinstance(data, dict) else None, ("question", "text", "q"))
    if not outline and not required_h2:
        fallback = _extract_template_titles_with_model(
            base_url=base_url,
            model=model,
            filename=filename,
            text=snippet,
        )
        titles = _normalize_string_list(fallback.get("titles"), ("title", "text", "name"))
        if titles:
            outline = [(1, txt) for txt in titles]
        if not questions:
            questions = _normalize_string_list(fallback.get("questions"), ("question", "text", "q"))
    return {"name": name or Path(filename).stem, "outline": outline, "required_h2": required_h2, "questions": questions}
def _extract_template_refine_with_model(
    *,
    base_url: str,
    model: str,
    filename: str,
    text: str,
    initial: dict,
) -> dict:
    snippet = (text or "").strip()
    if not snippet:
        return {"outline": [], "required_h2": [], "questions": []}
    if len(snippet) > 4000:
        snippet = snippet[:4000] + "…"
    client = OllamaClient(base_url=base_url, model=model, timeout_s=_extract_timeout_s())
    system = (
        "你是模板结构复核Agent，只输出JSON，不要Markdown，不要多余文字。\n"
        "Schema: {outline:[{level:int,title:string}],required_h2:[string],questions:[string]}.\n"
        "规则：对初始抽取进行纠错与补全，不得凭空新增；不确定的列入 questions。\n"
        "若 outline 为空，必须在 questions 中提示用户粘贴/确认结构，不要直接返回空。\n"
        "如果 outline 为空但 required_h2 不为空，可以将 required_h2 按顺序作为 level=1 的 outline 输出。\n"
        "仅保留能作为章节/小节标题的短语，删除说明性句子或带句号的长句。\n"
    )
    user = (
        f"文件名：{filename}\n模板内容：\n{snippet}\n\n"
        f"初始抽取：\n{json.dumps(initial, ensure_ascii=False)}\n\n"
        "请输出复核后的结构JSON。"
    )
    try:
        raw = client.chat(system=system, user=user, temperature=0.1)
    except Exception:
        return {"outline": [], "required_h2": [], "questions": []}
    raw_json = _extract_json_block(raw)
    if not raw_json:
        return {"outline": [], "required_h2": [], "questions": []}
    try:
        data = json.loads(raw_json)
    except Exception:
        return {"outline": [], "required_h2": [], "questions": []}
    outline_raw = data.get("outline") if isinstance(data, dict) else None
    outline = _normalize_outline(outline_raw)
    required_raw = data.get("required_h2") if isinstance(data, dict) else None
    required_h2 = _normalize_string_list(required_raw, ("title", "h2", "name", "text"))
    if not outline and required_h2:
        outline = [(1, txt) for txt in required_h2]
    questions = _normalize_string_list(data.get("questions") if isinstance(data, dict) else None, ("question", "text", "q"))
    if not outline and not required_h2:
        fallback = _extract_template_titles_with_model(
            base_url=base_url,
            model=model,
            filename=filename,
            text=snippet,
        )
        titles = _normalize_string_list(fallback.get("titles"), ("title", "text", "name"))
        if titles:
            outline = [(1, txt) for txt in titles]
        if not questions:
            questions = _normalize_string_list(fallback.get("questions"), ("question", "text", "q"))
    return {"outline": outline, "required_h2": required_h2, "questions": questions}
def _extract_prefs_with_model(
    *,
    base_url: str,
    model: str,
    text: str,
    timeout_s: float | None = None,
) -> dict:
    snippet = (text or "").strip()
    if not snippet:
        return {}
    if len(snippet) > 800:
        snippet = snippet[:800] + "…"
    client = OllamaClient(base_url=base_url, model=model, timeout_s=timeout_s or 20.0)
    system = (
        "你是需求参数提取Agent，只输出JSON。\n"
        "Schema: {title:string,formatting:{font_name:string,font_name_east_asia:string,font_size_name:string,font_size_pt:number,line_spacing:number,"
        "heading1_font_name:string,heading1_font_name_east_asia:string,heading1_size_pt:number,"
        "heading2_font_name:string,heading2_font_name_east_asia:string,heading2_size_pt:number,"
        "heading3_font_name:string,heading3_font_name_east_asia:string,heading3_size_pt:number},"
        "generation_prefs:{purpose:string,target_length_mode:string,target_length_value:number,expand_outline:boolean},"
        "summary:string,questions:[string]}.\n"
        "规则：只填确定项；target_length_mode 只能是 chars/pages；target_length_value 必须为数字。\n"
        "字号映射：五号=10.5pt，小四=12pt，四号=14pt，小三=15pt，三号=16pt，小二=18pt，二号=22pt。\n"
        "出现“标题/一级标题/章节”+字号/字体 -> 填 heading1_*；“正文”+字号/字体 -> 填 font_*。\n"
        "summary 复述理解；缺失项写入 questions；不要编造。\n"
    )
    user = f"用户输入：\n{snippet}\n\n请输出提取JSON。"
    try:
        raw = client.chat(system=system, user=user, temperature=0.1)
    except Exception:
        return {}
    raw_json = _extract_json_block(raw)
    if not raw_json:
        return {}
    try:
        return json.loads(raw_json)
    except Exception:
        return {}
def _extract_template_titles_with_model(
    *,
    base_url: str,
    model: str,
    filename: str,
    text: str,
) -> dict:
    snippet = (text or "").strip()
    if not snippet:
        return {"titles": [], "questions": []}
    if len(snippet) > 5000:
        snippet = snippet[:5000] + "…"
    client = OllamaClient(base_url=base_url, model=model, timeout_s=_extract_timeout_s())
    system = (
        "你是模板目录/章节标题抽取Agent，只输出JSON，不要Markdown，不要多余文字。\n"
        "Schema: {titles:[string],questions:[string]}.\n"
        "规则：从文本中提取章节/目录/结构标题，保持出现顺序；不要编造不存在的标题。\n"
        "只输出可作为标题的短语，剔除说明性长句或带句号的内容。\n"
        "若无法识别任何标题，请给出 questions 让用户粘贴或描述结构。\n"
    )
    user = f"文件名：{filename}\n模板内容：\n{snippet}\n\n请输出标题列表JSON。"
    try:
        raw = client.chat(system=system, user=user, temperature=0.1)
    except Exception:
        return {"titles": [], "questions": []}
    raw_json = _extract_json_block(raw)
    if not raw_json:
        return {"titles": [], "questions": []}
    try:
        data = json.loads(raw_json)
    except Exception:
        return {"titles": [], "questions": []}
    titles = _normalize_string_list(data.get("titles") if isinstance(data, dict) else None, ("title", "text", "name"))
    questions = _normalize_string_list(data.get("questions") if isinstance(data, dict) else None, ("question", "text", "q"))
    return {"titles": titles, "questions": questions}
def _extract_prefs_refine_with_model(
    *,
    base_url: str,
    model: str,
    text: str,
    initial: dict,
    timeout_s: float | None = None,
) -> dict:
    snippet = (text or "").strip()
    if not snippet:
        return {}
    if len(snippet) > 800:
        snippet = snippet[:800] + "…"
    client = OllamaClient(base_url=base_url, model=model, timeout_s=timeout_s or 20.0)
    system = (
        "你是需求参数复核Agent，只输出JSON，不要Markdown，不要多余文字。\n"
        "Schema: {title:string,formatting:{...},generation_prefs:{...},summary:string,questions:[string]}.\n"
        "规则：在初始抽取基础上纠错与补全；summary 用于复述你理解的需求；"
        "不确定的列入 questions；不要臆造信息。\n"
        "如用户输入已包含标题/字数/用途/字体，请补齐对应字段，并遵循字号映射（小四=12pt、四号=14pt、小三=15pt、三号=16pt、小二=18pt、二号=22pt）。\n"
        "示例：\n"
        "“标题黑体三号，二级标题黑体四号，正文宋体小四” -> heading1_size_pt=16, heading2_size_pt=14, font_size_pt=12。\n"
    )
    user = (
        f"用户输入：\n{snippet}\n\n"
        f"初始抽取：\n{json.dumps(initial, ensure_ascii=False)}\n\n"
        "请输出复核后的JSON。"
    )
    try:
        raw = client.chat(system=system, user=user, temperature=0.1)
    except Exception:
        return {}
    raw_json = _extract_json_block(raw)
    if not raw_json:
        return {}
    try:
        return json.loads(raw_json)
    except Exception:
        return {}
def _fast_extract_prefs(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    trans_map = {
        ord("\uFF10"): "0",
        ord("\uFF11"): "1",
        ord("\uFF12"): "2",
        ord("\uFF13"): "3",
        ord("\uFF14"): "4",
        ord("\uFF15"): "5",
        ord("\uFF16"): "6",
        ord("\uFF17"): "7",
        ord("\uFF18"): "8",
        ord("\uFF19"): "9",
        ord("\uFF0C"): ",",
        ord("\u3002"): ".",
        ord("\uFF1A"): ":",
        ord("\uFF1B"): ";",
        ord("\uFF08"): "(",
        ord("\uFF09"): ")",
        ord("\uFF1C"): "<",
        ord("\uFF1E"): ">",
        ord("\u3010"): "[",
        ord("\u3011"): "]",
    }
    norm = raw.translate(trans_map)
    def _cn_num_to_int(val: str) -> int | None:
        s = (val or "").strip()
        if not s:
            return None
        if re.search(r"\d", s):
            try:
                return int(float(s))
            except Exception:
                return None
        s = s.replace("\u4e24", "\u4e8c")
        units = {"\u5341": 10, "\u767e": 100, "\u5343": 1000, "\u4e07": 10000}
        digits = {
            "\u96f6": 0,
            "\u4e00": 1,
            "\u4e8c": 2,
            "\u4e09": 3,
            "\u56db": 4,
            "\u4e94": 5,
            "\u516d": 6,
            "\u4e03": 7,
            "\u516b": 8,
            "\u4e5d": 9,
        }
        total = 0
        unit = 1
        num = 0
        has = False
        for ch in reversed(s):
            if ch in digits:
                num += digits[ch] * unit
                has = True
            elif ch in units:
                unit = units[ch]
                if unit >= 10000:
                    total += num
                    num = 0
                    unit = 1
                has = True
            else:
                return None
        total += num
        return total if has else None
    size_name_map = {
        "\u521d\u53f7": 42,
        "\u5c0f\u521d": 36,
        "\u4e00\u53f7": 26,
        "\u5c0f\u4e00": 24,
        "\u4e8c\u53f7": 22,
        "\u5c0f\u4e8c": 18,
        "\u4e09\u53f7": 16,
        "\u5c0f\u4e09": 15,
        "\u56db\u53f7": 14,
        "\u5c0f\u56db": 12,
        "\u4e94\u53f7": 10.5,
        "\u5c0f\u4e94": 9,
        "\u516d\u53f7": 7.5,
        "\u5c0f\u516d": 6.5,
    }
    def _clean_title(val: str) -> str:
        t = (val or "").strip()
        if not t:
            return ""
        t = re.sub(
            r"(\u9ed8\u8ba4\u683c\u5f0f|\u6309\u9ed8\u8ba4|\u5e2e\u6211|\u751f\u6210|\u64b0\u5199|\u5199\u4e00\u4efd|\u505a\u4e00\u4efd|\u51c6\u5907\u4e00\u4efd|\u6765\u4e00\u4efd)",
            "",
            t,
        )
        t = re.sub(r"(\u62a5\u544a|\u8bba\u6587|\u65b9\u6848|\u8bbe\u8ba1|\u8bf4\u660e\u4e66?)$", "", t)
        t = re.sub(r"^\u4e00(\u4efd|\u7bc7|\u79cd)", "", t)
        t = re.sub(r"\u7684", "", t).strip()
        return t
    title = ""
    suffix = (
        "\u7ba1\u7406\u7cfb\u7edf|\u7cfb\u7edf|\u5e73\u53f0|\u5e94\u7528|\u9879\u76ee|\u65b9\u6848|\u8bbe\u8ba1|\u8f6f\u4ef6|\u7f51\u7ad9"
    )
    base = r"[\u4e00-\u9fffA-Za-z0-9]{2,30}"
    patterns = [
        rf"(?:\u751f\u6210|\u64b0\u5199|\u5e2e\u6211\u5199|\u5199\u4e00\u4efd|\u505a\u4e00\u4efd|\u51c6\u5907\u4e00\u4efd|\u6765\u4e00\u4efd)\s*({base}(?:{suffix}))",
        rf"({base}(?:{suffix}))\s*(?:\u62a5\u544a|\u8bba\u6587|\u65b9\u6848|\u8bbe\u8ba1|\u8bf4\u660e\u4e66?)",
        rf"(?:\u5173\u4e8e|\u56f4\u7ed5)\s*({base}(?:{suffix}))",
        r"[\u201c\"\u300a<]\s*([^\u201d\"\u300b>]{2,30})\s*[\u201d\"\u300b>]",
    ]
    for pat in patterns:
        m = re.search(pat, norm)
        if m:
            title = _clean_title(m.group(1))
            if title:
                break
    if not title:
        m = re.search(
            r"(?:\u5199\u4e00\u4efd|\u751f\u6210|\u505a\u4e00\u4efd|\u51c6\u5907\u4e00\u4efd|\u6765\u4e00\u4efd)\s*<?([^>]{2,40})>?\s*(?:\u62a5\u544a|\u8bba\u6587|\u65b9\u6848|\u8bbe\u8ba1)",
            norm,
        )
        if m:
            title = _clean_title(m.group(1))
    if title:
        title = re.split(r"[,.?!;:\s]", title)[0].strip()
    mode = ""
    value = 0
    questions: list[str] = []
    m = re.search(r"(\d+(?:\.\d+)?)\s*\u4e07\u5b57", norm)
    if m:
        mode = "chars"
        value = int(float(m.group(1)) * 10000)
    if not mode:
        m = re.search(r"\u5b57\u6570\s*(?:\u4e3a|\u662f|\u7ea6|\u5927\u6982)?\s*(\d+)", norm)
        if m:
            mode = "chars"
            value = int(m.group(1))
    if not mode:
        m = re.search(r"(?:\u7ea6|\u5927\u6982)\s*(\d+)\s*(?:\u5b57|\u5b57\u7b26)", norm)
        if m:
            mode = "chars"
            value = int(m.group(1))
    if not mode:
        m = re.search(r"(\d+)\s*(?:\u9875|\u9762)", norm)
        if m:
            mode = "pages"
            value = int(m.group(1))
    if not mode:
        m = re.search(r"([\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u4e24\u767e\u5343\u4e07]+)\s*(?:\u9875|\u9762)", norm)
        if m:
            cn_val = _cn_num_to_int(m.group(1))
            if cn_val:
                mode = "pages"
                value = cn_val
    if not mode:
        m = re.search(r"([\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u4e24\u767e\u5343\u4e07]+)\s*(?:\u5b57|\u5b57\u7b26)", norm)
        if m:
            cn_val = _cn_num_to_int(m.group(1))
            if cn_val:
                mode = "chars"
                value = cn_val
    range_match = re.search(
        r"(\d+(?:\.\d+)?)\s*[-~\u2013\u2014\u2015\u81f3]\s*(\d+(?:\.\d+)?)\s*(?:\u5b57|\u5b57\u7b26|\u9875|\u9762)",
        norm,
    )
    if range_match and not mode:
        left = range_match.group(1)
        right = range_match.group(2)
        unit = range_match.group(0)
        questions.append(
            f"\u4f60\u7ed9\u4e86\u957f\u5ea6\u8303\u56f4\uff08{unit}\uff09\uff0c\u8bf7\u786e\u8ba4\u76ee\u6807\u957f\u5ea6\u3002"
        )
        try:
            avg_val = int(round((float(left) + float(right)) / 2))
            if "\u9875" in unit or "\u9762" in unit:
                mode = "pages"
                value = avg_val
            else:
                mode = "chars"
                value = avg_val
        except Exception:
            pass
    purpose = ""
    for key in (
        "\u8bfe\u7a0b\u62a5\u544a",
        "\u8bfe\u7a0b\u8bbe\u8ba1",
        "\u6bd5\u4e1a\u8bbe\u8ba1",
        "\u9879\u76ee\u603b\u7ed3",
        "\u8c03\u7814\u62a5\u544a",
        "\u53ef\u884c\u6027\u62a5\u544a",
        "\u53c2\u8003\u4f5c\u4e1a",
        "\u8bfe\u7a0b\u6c47\u62a5",
        "\u9636\u6bb5\u603b\u7ed3",
        "\u9879\u76ee\u590d\u76d8",
    ):
        if key in raw:
            purpose = key
            break
    formatting: dict = {}
    prefs: dict = {}
    m = re.search(
        r"(?:\u6b63\u6587\u5b57\u4f53|\u6b63\u6587|\u5b57\u4f53)\s*[:\uff1a]?\s*([A-Za-z ]{3,20}|[\u4e00-\u9fff]{2,6})",
        norm,
    )
    if m:
        font = m.group(1).strip()
        if font:
            formatting["font_name_east_asia"] = font
    m = re.search(
        r"(?:\u5b57\u53f7|\u5b57\u4f53\u5927\u5c0f|\u6b63\u6587)\s*[:\uff1a]?\s*(\u521d\u53f7|\u5c0f\u521d|\u4e00\u53f7|\u5c0f\u4e00|\u4e8c\u53f7|\u5c0f\u4e8c|\u4e09\u53f7|\u5c0f\u4e09|\u56db\u53f7|\u5c0f\u56db|\u4e94\u53f7|\u5c0f\u4e94|\u516d\u53f7|\u5c0f\u516d)",
        norm,
    )
    if m and m.group(1) in size_name_map:
        formatting["font_size_pt"] = size_name_map[m.group(1)]
        formatting["font_size_name"] = m.group(1)
    m = re.search(
        r"(?:\u5b57\u53f7|\u5b57\u4f53\u5927\u5c0f|\u6b63\u6587)\s*[:\uff1a]?\s*(\d+(?:\.\d+)?)\s*pt",
        norm,
        flags=re.IGNORECASE,
    )
    if m:
        formatting["font_size_pt"] = float(m.group(1))
    m = re.search(r"(?:\u884c\u8ddd|\u884c\u95f4\u8ddd)\s*[:\uff1a]?\s*(\d+(?:\.\d+)?)\s*\u500d", norm)
    if m:
        formatting["line_spacing"] = float(m.group(1))
    h1 = re.search(
        r"(?:\u4e00\u7ea7\u6807\u9898|\u4e00\u7ea7\u6807\u9898\u5b57\u53f7|\u6807\u9898)\s*[:\uff1a]?\s*(\u521d\u53f7|\u5c0f\u521d|\u4e00\u53f7|\u5c0f\u4e00|\u4e8c\u53f7|\u5c0f\u4e8c|\u4e09\u53f7|\u5c0f\u4e09|\u56db\u53f7|\u5c0f\u56db|\u4e94\u53f7|\u5c0f\u4e94)",
        norm,
    )
    if h1 and h1.group(1) in size_name_map:
        formatting["heading1_size_pt"] = size_name_map[h1.group(1)]
    h2 = re.search(
        r"(?:\u4e8c\u7ea7\u6807\u9898)\s*[:\uff1a]?\s*(\u521d\u53f7|\u5c0f\u521d|\u4e00\u53f7|\u5c0f\u4e00|\u4e8c\u53f7|\u5c0f\u4e8c|\u4e09\u53f7|\u5c0f\u4e09|\u56db\u53f7|\u5c0f\u56db|\u4e94\u53f7|\u5c0f\u4e94)",
        norm,
    )
    if h2 and h2.group(1) in size_name_map:
        formatting["heading2_size_pt"] = size_name_map[h2.group(1)]
    h3 = re.search(
        r"(?:\u4e09\u7ea7\u6807\u9898)\s*[:\uff1a]?\s*(\u521d\u53f7|\u5c0f\u521d|\u4e00\u53f7|\u5c0f\u4e00|\u4e8c\u53f7|\u5c0f\u4e8c|\u4e09\u53f7|\u5c0f\u4e09|\u56db\u53f7|\u5c0f\u56db|\u4e94\u53f7|\u5c0f\u4e94)",
        norm,
    )
    if h3 and h3.group(1) in size_name_map:
        formatting["heading3_size_pt"] = size_name_map[h3.group(1)]
    if re.search(r"\bA5\b", norm, flags=re.IGNORECASE):
        prefs["page_size"] = "A5"
    elif re.search(r"\bA4\b", norm, flags=re.IGNORECASE):
        prefs["page_size"] = "A4"
    elif re.search(r"\bLETTER\b", norm, flags=re.IGNORECASE):
        prefs["page_size"] = "LETTER"
    m = re.search(
        r"(?:\u9875\u8fb9\u8ddd|\u9875\u9762\u8fb9\u8ddd)\s*[:\uff1a]?\s*(\d+(?:\.\d+)?)\s*cm",
        norm,
        flags=re.IGNORECASE,
    )
    if m:
        prefs["page_margins_cm"] = float(m.group(1))
    if re.search(r"(?:\u4e0d\u8981|\u65e0\u9700|\u53d6\u6d88)\s*\u5c01\u9762", norm):
        prefs["include_cover"] = False
    if re.search(r"(?:\u9700\u8981|\u5305\u542b|\u6709)\s*\u5c01\u9762", norm):
        prefs["include_cover"] = True
    if re.search(r"(?:\u4e0d\u8981|\u65e0\u9700|\u53d6\u6d88)\s*\u76ee\u5f55", norm):
        prefs["include_toc"] = False
    if re.search(r"(?:\u9700\u8981|\u5305\u542b|\u6709)\s*\u76ee\u5f55", norm):
        prefs["include_toc"] = True
    if re.search(r"(?:\u4e0d\u8981|\u65e0\u9700|\u53d6\u6d88)\s*(\u9875\u7801|\u9875\u6570)", norm):
        prefs["page_numbers"] = False
    if re.search(r"(?:\u9700\u8981|\u5305\u542b|\u6709)\s*(\u9875\u7801|\u9875\u6570)", norm):
        prefs["page_numbers"] = True
    header_text = ""
    footer_text = ""
    m = re.search(r"\u9875\u7709\s*[:\uff1a]\s*([^\n,;\uff0c\uff1b]{1,30})", norm)
    if m:
        header_text = m.group(1).strip()
        if header_text:
            prefs["include_header"] = True
    m = re.search(r"\u9875\u811a\s*[:\uff1a]\s*([^\n,;\uff0c\uff1b]{1,30})", norm)
    if m:
        footer_text = m.group(1).strip()
    if header_text:
        prefs["header_text"] = header_text
    if footer_text:
        prefs["footer_text"] = footer_text
    if purpose:
        prefs["purpose"] = purpose
    if mode and value:
        prefs["target_length_mode"] = mode
        prefs["target_length_value"] = value
    result = {}
    if title:
        result["title"] = title
    if formatting:
        result["formatting"] = formatting
    if prefs:
        result["generation_prefs"] = prefs
    if questions:
        result["questions"] = questions
    if result:
        result["summary"] = "\u5df2\u8bc6\u522b\u6807\u9898/\u7528\u9014/\u957f\u5ea6/\u683c\u5f0f\u7ebf\u7d22\u3002"
    return result
def _coerce_float(value: object) -> float | None:
    try:
        return float(value)
    except Exception:
        return None
def _coerce_int(value: object) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None
def _normalize_ai_formatting(data: object) -> dict:
    if not isinstance(data, dict):
        return {}
    out: dict = {}
    def _set_str(key: str) -> None:
        val = str(data.get(key) or "").strip()
        if val:
            out[key] = val
    _set_str("font_name")
    _set_str("font_name_east_asia")
    _set_str("font_size_name")
    _set_str("heading1_font_name")
    _set_str("heading1_font_name_east_asia")
    _set_str("heading2_font_name")
    _set_str("heading2_font_name_east_asia")
    _set_str("heading3_font_name")
    _set_str("heading3_font_name_east_asia")
    fs_pt = _coerce_float(data.get("font_size_pt"))
    if fs_pt:
        out["font_size_pt"] = fs_pt
    if "font_size_pt" not in out:
        size_name = str(out.get("font_size_name") or "").strip()
        name_map = {
            "五号": 10.5,
            "小四": 12,
            "四号": 14,
            "小三": 15,
            "三号": 16,
            "小二": 18,
            "二号": 22,
        }
        if size_name in name_map:
            out["font_size_pt"] = name_map[size_name]
    ls = _coerce_float(data.get("line_spacing"))
    if ls:
        out["line_spacing"] = ls
    h1_pt = _coerce_float(data.get("heading1_size_pt"))
    if h1_pt:
        out["heading1_size_pt"] = h1_pt
    h2_pt = _coerce_float(data.get("heading2_size_pt"))
    if h2_pt:
        out["heading2_size_pt"] = h2_pt
    h3_pt = _coerce_float(data.get("heading3_size_pt"))
    if h3_pt:
        out["heading3_size_pt"] = h3_pt
    return out
def _replace_question_headings(text: str) -> str:
    if not text:
        return text
    lines = []
    for line in str(text).replace("\r", "").split("\n"):
        if re.match(r"^#{1,3}\s*[?？]{2,}\s*$", line):
            line = "## 参考文献"
        elif re.match(r"^[?？]{2,}\s*$", line):
            line = "参考文献"
        lines.append(line)
    return "\n".join(lines)
def _normalize_ai_prefs(data: object) -> dict:
    if not isinstance(data, dict):
        return {}
    out: dict = {}
    purpose = str(data.get("purpose") or "").strip()
    if purpose:
        out["purpose"] = purpose
    mode = str(data.get("target_length_mode") or "").strip().lower()
    if mode in {"chars", "pages"}:
        out["target_length_mode"] = mode
        val = _coerce_int(data.get("target_length_value"))
        if val and val > 0:
            out["target_length_value"] = val
    if isinstance(data.get("expand_outline"), bool):
        out["expand_outline"] = bool(data.get("expand_outline"))
    for key in ("include_cover", "include_toc", "include_header", "page_numbers"):
        if isinstance(data.get(key), bool):
            out[key] = bool(data.get(key))
    page_size = str(data.get("page_size") or "").strip().upper()
    if page_size in {"A4", "A5", "LETTER"}:
        out["page_size"] = page_size
    margin = _coerce_float(data.get("page_margins_cm"))
    if margin and margin > 0:
        out["page_margins_cm"] = margin
    header_text = str(data.get("header_text") or "").strip()
    if header_text:
        out["header_text"] = header_text
    footer_text = str(data.get("footer_text") or "").strip()
    if footer_text:
        out["footer_text"] = footer_text
    audience = str(data.get("audience") or "").strip()
    if audience:
        out["audience"] = audience
    output_form = str(data.get("output_form") or "").strip()
    if output_form:
        out["output_form"] = output_form
    voice = str(data.get("voice") or "").strip()
    if voice:
        out["voice"] = voice
    avoid = str(data.get("avoid") or "").strip()
    if avoid:
        out["avoid"] = avoid
    scope = str(data.get("scope") or "").strip()
    if scope:
        out["scope"] = scope
    return out
def _formatting_from_session(session) -> object:
    from writing_agent.models import FormattingRequirements
    f = getattr(session, "formatting", None)
    if not isinstance(f, dict):
        return FormattingRequirements()
    try:
        font_size_pt = float(f.get("font_size_pt") or 10.5)
    except Exception:
        font_size_pt = 10.5
    try:
        line_spacing = float(f.get("line_spacing") or 1.5)
    except Exception:
        line_spacing = 1.5
    def _normalize_font_name(raw: object, fallback: str) -> str:
        name = str(raw or "").strip()
        if not name:
            return fallback
        fixes = {
            "å®‹ä½“": "宋体",
            "瀹嬩綋": "宋体",
            "é»‘ä½“": "黑体",
            "榛戜綋": "黑体",
            "SimSun": "宋体",
            "SimHei": "黑体",
        }
        return fixes.get(name, name)
    font_name = _normalize_font_name(f.get("font_name"), "宋体")
    font_name_ea = _normalize_font_name(f.get("font_name_east_asia"), "宋体")
    def _read_float(key: str) -> float | None:
        raw = f.get(key)
        if raw is None:
            return None
        try:
            return float(raw)
        except Exception:
            return None
    return FormattingRequirements(
        font_name=font_name,
        font_name_east_asia=font_name_ea,
        font_size_pt=font_size_pt,
        line_spacing=line_spacing,
        heading1_font_name=_normalize_font_name(f.get("heading1_font_name"), "黑体") or None,
        heading1_font_name_east_asia=_normalize_font_name(f.get("heading1_font_name_east_asia"), "黑体") or None,
        heading1_size_pt=_read_float("heading1_size_pt"),
        heading2_font_name=_normalize_font_name(f.get("heading2_font_name"), "黑体") or None,
        heading2_font_name_east_asia=_normalize_font_name(f.get("heading2_font_name_east_asia"), "黑体") or None,
        heading2_size_pt=_read_float("heading2_size_pt"),
        heading3_font_name=_normalize_font_name(f.get("heading3_font_name"), "黑体") or None,
        heading3_font_name_east_asia=_normalize_font_name(f.get("heading3_font_name_east_asia"), "黑体") or None,
        heading3_size_pt=_read_float("heading3_size_pt"),
    )
def _export_prefs_from_session(session) -> ExportPrefs:
    prefs = getattr(session, "generation_prefs", None)
    if not isinstance(prefs, dict):
        return ExportPrefs()
    base_margin = float(prefs.get("page_margins_cm") or 2.8)
    return ExportPrefs(
        include_cover=bool(prefs.get("include_cover", True)),
        include_toc=bool(prefs.get("include_toc", True)),
        toc_levels=int(prefs.get("toc_levels") or 3),
        include_header=bool(prefs.get("include_header", True)),
        page_numbers=bool(prefs.get("page_numbers", True)),
        header_text=str(prefs.get("header_text") or ""),
        footer_text=str(prefs.get("footer_text") or ""),
        page_margins_cm=base_margin,
        page_margin_top_cm=float(prefs.get("page_margin_top_cm") or 3.7),
        page_margin_bottom_cm=float(prefs.get("page_margin_bottom_cm") or 3.5),
        page_margin_left_cm=float(prefs.get("page_margin_left_cm") or 2.8),
        page_margin_right_cm=float(prefs.get("page_margin_right_cm") or 2.6),
        page_size=str(prefs.get("page_size") or "A4"),
    )
def _estimate_chars_per_page(formatting: dict, prefs: dict) -> int:
    font_size = float(formatting.get("font_size_pt") or 12)
    line_spacing = float(formatting.get("line_spacing") or 1.5)
    margins = float(prefs.get("page_margins_cm") or 2.5)
    size = str(prefs.get("page_size") or "A4").upper()
    if size == "A5":
        width, height = 14.8, 21.0
    elif size == "LETTER":
        width, height = 21.59, 27.94
    else:
        width, height = 21.0, 29.7
    page_width = width - 2 * margins
    page_height = height - 2 * margins
    line_height_pt = line_spacing if line_spacing >= 4 else font_size * line_spacing
    line_height_cm = line_height_pt * 0.0352778
    lines_per_page = max(1, int(page_height / max(0.35, line_height_cm)))
    base_chars_per_line = 38
    chars_per_line = max(10, int(base_chars_per_line * (12 / max(8, font_size))))
    return max(120, int(lines_per_page * chars_per_line))
def _resolve_target_chars(formatting: dict, prefs: dict) -> int:
    if not isinstance(prefs, dict):
        return 0
    def _safe_int(val) -> int:
        try:
            return int(float(val))
        except Exception:
            return 0
    target_chars = _safe_int(prefs.get("target_char_count") or 0)
    if target_chars > 0:
        return target_chars
    mode = str(prefs.get("target_length_mode") or "").strip().lower()
    if mode == "chars":
        return _safe_int(prefs.get("target_word_count") or prefs.get("target_length_value") or 0)
    if mode == "pages":
        pages = _safe_int(prefs.get("target_page_count") or prefs.get("target_length_value") or 0)
        if pages > 0:
            return int(pages * _estimate_chars_per_page(formatting or {}, prefs))
    return 0
def _extract_target_chars_from_instruction(instruction: str) -> int:
    s = (instruction or "").strip()
    if not s:
        return 0
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s*\u4e07\s*\u5b57", s)
    if m:
        try:
            val = int(float(m.group(1)) * 10000)
        except Exception:
            val = 0
        if 100 <= val <= 200000:
            return val
    m = re.search(r"(\d{1,3})\s*\u5343\s*\u5b57", s)
    if m:
        try:
            val = int(float(m.group(1)) * 1000)
        except Exception:
            val = 0
        if 100 <= val <= 200000:
            return val
    patterns = [
        (r"(?:\u5b57\u6570|\u5b57\u7b26\u6570)\s*[:\uff1a]?\s*(\d{2,6})", 1),
        (r"(\d{2,6})\s*(?:\u5b57|\u5b57\u7b26)", 1),
        (r"(\d{1,3})\s*(?:k|K)\s*(?:\u5b57|\u5b57\u7b26)?", 1000),
    ]
    for pat, multi in patterns:
        m = re.search(pat, s)
        if not m:
            continue
        try:
            val = int(float(m.group(1)) * multi)
        except Exception:
            val = 0
        if 100 <= val <= 200000:
            return val
    return 0
def _clean_export_text(text: str) -> str:
    s = (text or "").replace("\r", "")
    converted = _maybe_convert_json_doc(s)
    if converted:
        s = converted
    # Normalize heading markers: "##标题" -> "## 标题"
    s = re.sub(r"(?m)^(#{1,6})([^#\s])", r"\1 \2", s)
    # Strip XML-illegal control characters to avoid DOCX corruption.
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    s = s.replace("\uFFFE", "").replace("\uFFFF", "")
    lines = s.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        t = raw.strip()
        if not t:
            out.append("")
            i += 1
            continue
        if re.match(r"^\s*#{4,}\s+", raw):
            raw = re.sub(r"^\s*#{4,}\s+", "", raw)
            t = raw.strip()
        if t in {"#", "##", "###"}:
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt:
                    out.append(f"{t} {nxt}")
                    i += 2
                    continue
            i += 1
            continue
        if out and len(t) <= 4 and re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]+", t):
            prev = out[-1].strip()
            if prev and not re.search(r"[。！？!?;；:：]$", prev) and re.search(r"[\u4e00-\u9fff]$", prev):
                out[-1] = out[-1].rstrip() + t
                i += 1
                continue
        out.append(raw)
        i += 1
    s = "\n".join(out)
    s = s.replace("```", "")
    s = re.sub(r"(?<!\*)\*(?!\*)", "", s)
    s = re.sub(r"(?m)^\s*[*\-\u2013]\s+", "", s)
    s = _compact_list_spacing_for_export(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
def _compact_list_spacing_for_export(text: str) -> str:
    lines = (text or "").splitlines()
    def is_list_line(line: str) -> bool:
        t = (line or "").strip()
        if not t:
            return False
        if re.match(r"^\d+[.\uFF0E\u3001\)]\s+", t):
            return True
        if re.match(r"^[一二三四五六七八九十]+[.\u3001\)]\s+", t):
            return True
        if re.match(r"^[\u2022\u00B7]\s+", t):
            return True
        return False
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip():
            out.append(line)
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        prev = ""
        for k in range(len(out) - 1, -1, -1):
            if out[k].strip():
                prev = out[k]
                break
        next_line = lines[j] if j < len(lines) else ""
        if prev and next_line and is_list_line(prev) and is_list_line(next_line):
            i = j
            continue
        out.append("")
        i = j
    return "\n".join(out)
def _json_sections_to_text(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    title = str(data.get("title") or "").strip() or _default_title()
    sections = data.get("sections")
    if not isinstance(sections, list):
        return None
    lines: list[str] = [f"# {title}"]
    for sec in sections:
        if isinstance(sec, dict):
            sec_title = str(sec.get("title") or sec.get("name") or sec.get("section") or "").strip()
            if not sec_title:
                continue
            lines.append(f"## {sec_title}")
            content = sec.get("content")
            if content is None:
                content = sec.get("text")
            if content is None:
                content = sec.get("body")
            if isinstance(content, list):
                content = "\n\n".join([str(x).strip() for x in content if str(x).strip()])
            content = str(content or "").strip()
            if content:
                lines.append(content)
        elif isinstance(sec, str):
            sec_title = sec.strip()
            if sec_title:
                lines.append(f"## {sec_title}")
    return "\n\n".join(lines).strip()
def _maybe_convert_json_doc(text: str) -> str | None:
    s = str(text or "").strip()
    if not s:
        return None
    if re.search(r"(?m)^#{1,3}\s+", s):
        return None
    if not (s.startswith("{") or "```json" in s):
        return None
    raw_json = _extract_json_block(s)
    if not raw_json and s.startswith("{") and s.endswith("}"):
        raw_json = s
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
    except Exception:
        return None
    if isinstance(data, dict) and isinstance(data.get("doc_ir"), dict):
        try:
            return doc_ir_to_text(doc_ir_from_dict(data["doc_ir"]))
        except Exception:
            return None
    if isinstance(data, dict) and "title" in data and isinstance(data.get("sections"), list):
        return _json_sections_to_text(data)
    return None
def _normalize_generated_text(text: str, instruction: str, current_text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return s
    converted = _maybe_convert_json_doc(s)
    if converted:
        s = converted
    # Normalize heading markers like "##标题" -> "## 标题"
    s = re.sub(r"(?m)^(#{1,6})([^#\s])", r"\1 \2", s)
    if not re.search(r"(?m)^#\s+", s):
        title = _plan_title(current_text=current_text or s, instruction=instruction)
        if not title:
            title = _extract_title(s)
        s = f"# {title}\n\n" + s.lstrip()
    return s.strip()
_FAST_REPORT_SECTIONS = ["背景", "本周工作", "下周计划", "风险与需协助", "风险与协助", "风险与需支持"]
def _collect_heading_candidates(session) -> list[str]:
    titles: list[str] = []
    for item in (session.template_required_h2 or []):
        t = str(item or "").strip()
        if t:
            titles.append(t)
    for item in (session.template_outline or []):
        try:
            lvl, title = item
        except Exception:
            continue
        t = str(title or "").strip()
        if t:
            titles.append(t)
    titles.extend(_FAST_REPORT_SECTIONS)
    seen = set()
    out: list[str] = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
def _extract_heading_candidates_from_text(text: str) -> list[str]:
    if not text:
        return []
    try:
        parsed = parse_report_text(text)
    except Exception:
        return []
    titles: list[str] = []
    for b in (parsed.blocks or []):
        if getattr(b, "type", "") == "heading":
            t = str(getattr(b, "text", "") or "").strip()
            if t:
                titles.append(t)
    seen: set[str] = set()
    out: list[str] = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
def _heading_candidates_for_revision(session, base_text: str) -> list[str]:
    titles = _collect_heading_candidates(session)
    titles.extend(_extract_heading_candidates_from_text(base_text))
    seen: set[str] = set()
    out: list[str] = []
    for t in titles:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out
def _postprocess_output_text(
    session,
    text: str,
    instruction: str,
    *,
    current_text: str,
    base_text: str | None = None,
) -> str:
    s = _sanitize_output_text(text)
    base = base_text if base_text is not None else current_text
    s = _normalize_generated_text(s, instruction, current_text or base)
    titles = _heading_candidates_for_revision(session, base or "")
    if titles:
        s = _fix_section_heading_glue(s, titles)
    return s
def _fix_section_heading_glue(text: str, titles: list[str]) -> str:
    if not text or not titles:
        return text
    lines = (text or "").splitlines()
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            out.append(raw)
            continue
        heading_prefix = ""
        content = line
        if line.startswith("#"):
            m = re.match(r"^(#{1,6})\s*(.+)$", line)
            if not m:
                out.append(raw)
                continue
            heading_prefix = m.group(1)
            content = m.group(2).strip()
            split = _split_heading_glue_v2(content)
            if split:
                out.append(f"{heading_prefix} {split[0]}")
                if split[1]:
                    out.append(split[1])
                continue
        matched = ""
        for t in titles:
            if content.startswith(t):
                matched = t
                break
        if matched:
            rest = content[len(matched):].lstrip("：:、-— \t")
            level = heading_prefix or "##"
            out.append(f"{level} {matched}")
            if rest:
                out.append(rest)
            continue
        out.append(raw)
    return "\n".join(out).strip()
_CITATION_MARK_RE = re.compile(r"\[@([a-zA-Z0-9_-]+)\]")
_REFERENCE_HEADING_RE = re.compile(r"^(#{1,3})\s*(参考文献|参考资料|references)\s*$", re.IGNORECASE)
def _citation_style_from_session(session) -> CitationStyle:
    raw = str((session.formatting or {}).get("citation_style") or "").strip()
    if not raw:
        return CitationStyle.GBT
    key = raw.replace(" ", "").replace("-", "").replace("_", "").upper()
    if key in {"APA"}:
        return CitationStyle.APA
    if key in {"IEEE"}:
        return CitationStyle.IEEE
    if key in {"GBT", "GB", "GBT7714", "GB/T", "GB/T7714"}:
        return CitationStyle.GBT
    return CitationStyle.GBT
def _insert_reference_section(text: str, ref_lines: list[str]) -> str:
    if not ref_lines:
        return text
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    heading_idx = None
    for idx, line in enumerate(lines):
        if _REFERENCE_HEADING_RE.match(line.strip()):
            heading_idx = idx
            break
    if heading_idx is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("## 参考文献")
        lines.append("")
        lines.extend(ref_lines)
        return "\n".join(lines).strip() + "\n"
    existing_nums: set[int] = set()
    for i in range(heading_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        if re.match(r"^#{1,3}\s+", line):
            break
        m = re.match(r"^\[(\d+)\]\s*", line)
        if m:
            try:
                existing_nums.add(int(m.group(1)))
            except Exception:
                pass
    to_add: list[str] = []
    for line in ref_lines:
        m = re.match(r"^\[(\d+)\]\s*", line)
        if m:
            try:
                if int(m.group(1)) in existing_nums:
                    continue
            except Exception:
                pass
        to_add.append(line)
    if not to_add:
        return text
    insert_idx = heading_idx + 1
    for i in range(heading_idx + 1, len(lines)):
        if re.match(r"^#{1,3}\s+", lines[i].strip()):
            insert_idx = i
            break
        insert_idx = i + 1
    if insert_idx > 0 and lines[insert_idx - 1].strip():
        to_add = [""] + to_add
    lines[insert_idx:insert_idx] = to_add
    return "\n".join(lines)
def _apply_citations_for_export(text: str, citations: dict[str, Citation], style: CitationStyle) -> str:
    if not text:
        return text
    key_to_num: dict[str, int] = {}
    ordered_keys: list[str] = []
    def _assign_key(key: str) -> int:
        if key not in key_to_num:
            key_to_num[key] = len(key_to_num) + 1
            ordered_keys.append(key)
        return key_to_num[key]
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        num = _assign_key(key)
        return f"[{num}]"
    replaced = _CITATION_MARK_RE.sub(_replace, text)
    if not ordered_keys and citations:
        for key in citations.keys():
            _assign_key(key)
    if not ordered_keys:
        return replaced
    citer = CitationAgent()
    ref_lines: list[str] = []
    for key in ordered_keys:
        cite = citations.get(key)
        if cite:
            ref = citer.format_reference(cite, style)
        else:
            ref = f"{key}（未找到引用详情）"
        ref_lines.append(f"[{key_to_num[key]}] {ref}")
    return _insert_reference_section(replaced, ref_lines)
def _apply_citations_to_doc_ir(doc_ir, citations: dict[str, Citation], style: CitationStyle):
    if not doc_ir or not citations:
        return doc_ir
    try:
        data = doc_ir_to_dict(doc_ir)
    except Exception:
        return doc_ir
    key_to_num: dict[str, int] = {}
    ordered_keys: list[str] = []
    def _assign_key(key: str) -> int:
        if key not in key_to_num:
            key_to_num[key] = len(key_to_num) + 1
            ordered_keys.append(key)
        return key_to_num[key]
    def _replace_text(text: str) -> str:
        if not text:
            return text
        return _CITATION_MARK_RE.sub(lambda m: f"[{_assign_key(m.group(1))}]", text)
    def _replace_caption(container: dict, field: str) -> None:
        if not isinstance(container, dict):
            return
        val = container.get(field)
        if isinstance(val, str) and val:
            container[field] = _replace_text(val)
    def _process_blocks(blocks: list[dict]) -> None:
        for block in blocks:
            if not isinstance(block, dict):
                continue
            t = str(block.get("type") or "").lower()
            if t in {"paragraph", "text", "p"}:
                block["text"] = _replace_text(str(block.get("text") or ""))
                continue
            if t == "list":
                items = block.get("items")
                if isinstance(items, list):
                    block["items"] = [_replace_text(str(i)) for i in items]
                elif isinstance(block.get("text"), str):
                    block["text"] = _replace_text(str(block.get("text") or ""))
                continue
            if t == "table":
                table = block.get("table") or block.get("data")
                if isinstance(table, dict):
                    _replace_caption(table, "caption")
                continue
            if t == "figure":
                fig = block.get("figure") or block.get("data")
                if isinstance(fig, dict):
                    _replace_caption(fig, "caption")
                continue
    def _walk_sections(sections: list[dict]) -> None:
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            blocks = sec.get("blocks")
            if isinstance(blocks, list):
                _process_blocks(blocks)
            children = sec.get("children")
            if isinstance(children, list):
                _walk_sections(children)
    sections = data.get("sections")
    if isinstance(sections, list):
        _walk_sections(sections)
    if not ordered_keys and citations:
        for key in citations.keys():
            _assign_key(key)
    if not ordered_keys:
        return doc_ir_from_dict(data)
    citer = CitationAgent()
    ref_lines: list[str] = []
    for key in ordered_keys:
        cite = citations.get(key)
        if cite:
            ref = citer.format_reference(cite, style)
        else:
            ref = f"{key}（未找到引用详情）"
        ref_lines.append(f"[{key_to_num[key]}] {ref}")
    def _find_reference_section(sections: list[dict]) -> dict | None:
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            title = str(sec.get("title") or "").strip()
            if title and re.search(r"(参考文献|参考资料|references)", title, re.I):
                return sec
            children = sec.get("children")
            if isinstance(children, list):
                found = _find_reference_section(children)
                if found:
                    return found
        return None
    ref_section = None
    if isinstance(sections, list):
        ref_section = _find_reference_section(sections)
        if ref_section is None:
            ref_section = {"title": "参考文献", "level": 2, "blocks": [], "children": []}
            sections.append(ref_section)
    if ref_section is not None:
        ref_section["blocks"] = [{"type": "paragraph", "text": line} for line in ref_lines]
    return doc_ir_from_dict(data)
def _normalize_doc_ir_for_export(doc_ir, session):
    _ensure_mcp_citations(session)
    if session.doc_ir:
        try:
            doc_ir = doc_ir_from_dict(session.doc_ir)
        except Exception:
            pass
    if doc_ir is None:
        return doc_ir
    try:
        if _doc_ir_has_styles(doc_ir):
            return doc_ir
    except Exception:
        pass
    try:
        text = doc_ir_to_text(doc_ir)
    except Exception:
        return doc_ir
    text = _fix_section_heading_glue(text, _collect_heading_candidates(session))
    text = re.sub(r"(?m)^(#{1,6})([^#\\s])", r"\\1 \\2", text)
    try:
        return doc_ir_from_text(text)
    except Exception:
        return doc_ir
def _safe_doc_text(session) -> str:
    text = str(session.doc_text or "")
    if text.strip() and not session.template_outline and not session.template_required_h2:
        try:
            title = _plan_title(
                current_text="",
                instruction=str((session.generation_prefs or {}).get("extra_requirements") or ""),
            )
            fallback_sections = _fallback_sections_from_session(session)
            fallback = _build_fallback_text(title, fallback_sections, session)
            if text.strip() == fallback.strip():
                session.doc_text = ""
                session.doc_ir = {}
                store.put(session)
                return ""
        except Exception:
            pass
    if not text.strip() and session.doc_ir:
        try:
            text = doc_ir_to_text(doc_ir_from_dict(session.doc_ir))
        except Exception:
            text = ""
    if not text.strip():
        session.doc_text = ""
        session.doc_ir = {}
        store.put(session)
        return ""
    _set_doc_text(session, text)
    store.put(session)
    return text
def _validate_docx_bytes(docx_bytes: bytes) -> list[str]:
    from zipfile import ZipFile, BadZipFile
    import xml.etree.ElementTree as ET
    import io
    issues: list[str] = []
    try:
        with ZipFile(io.BytesIO(docx_bytes), "r") as zin:
            names = zin.namelist()
            required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
            missing = [n for n in required if n not in names]
            if missing:
                issues.append(f"missing:{','.join(missing)}")
            # Parse critical XML parts to ensure well-formedness.
            for name in names:
                if not name.lower().endswith(".xml"):
                    continue
                try:
                    ET.fromstring(zin.read(name))
                except Exception:
                    issues.append(f"xml:{name}")
    except BadZipFile:
        issues.append("badzip")
    except Exception:
        issues.append("unknown")
    return issues
def _set_doc_text(session, text: str) -> None:
    session.doc_text = text
    if not str(text or "").strip():
        session.doc_ir = {}
        return
    try:
        session.doc_ir = doc_ir_to_dict(doc_ir_from_text(text))
    except Exception:
        session.doc_ir = {}
def _safe_doc_ir_payload(text: str) -> dict:
    if not str(text or "").strip():
        return {}
    try:
        return doc_ir_to_dict(doc_ir_from_text(str(text)))
    except Exception:
        return {}
def _fallback_sections_from_session(session) -> list[str]:
    if session.template_outline:
        return [str(t or "").strip() for _, t in session.template_outline if str(t or "").strip()]
    if session.template_required_h2:
        return [str(t or "").strip() for t in session.template_required_h2 if str(t or "").strip()]
    return ["引言", "需求分析", "总体设计", "数据库设计", "测试与结果", "结论", "参考文献"]
def _fallback_reference_items(session, query: str) -> list[str]:
    q = (query or "").strip()
    if not q:
        q = str((session.generation_prefs or {}).get("extra_requirements") or "").strip()
    if not q:
        q = title = str(session.doc_text or "").strip()
    papers = rag_store.list_papers()
    hits = search_papers(papers=papers, query=q, top_k=8)
    sources: list[dict] = []
    for h in hits:
        # map to reference item schema used by _format_reference_items
        sources.append(
            {
                "title": h.title,
                "url": h.abs_url,
                "authors": [],
                "published": h.published,
                "updated": h.published,
                "source": "openalex" if "openalex" in h.abs_url else "arxiv" if "arxiv" in h.abs_url else "",
            }
        )
    return _format_reference_items(sources)
def _build_fallback_text(title: str, sections: list[str], session=None) -> str:
    fallback_text: dict[str, str] = {}
    ref_lines: list[str] = []
    if session is not None:
        query = str((session.generation_prefs or {}).get("extra_requirements") or "").strip() or title
        ref_lines = _fallback_reference_items(session, query)
    for sec in sections:
        if _is_reference_section(sec):
            fallback_text[sec] = "\n".join(ref_lines).strip()
        else:
            body = _generic_fill_paragraph(sec, idx=1)
            if ref_lines:
                body = (body + " [1]").strip()
            fallback_text[sec] = body
    return _merge_sections_text(title or _default_title(), sections, fallback_text)
def _augment_instruction(instruction: str, *, formatting: dict, generation_prefs: dict) -> str:
    inst = (instruction or "").strip()
    if not inst:
        return ""
    fmt = formatting if isinstance(formatting, dict) else {}
    prefs = generation_prefs if isinstance(generation_prefs, dict) else {}
    purpose = str(prefs.get("purpose") or "").strip()
    figure_types = prefs.get("figure_types")
    table_types = prefs.get("table_types")
    extra_req = str(prefs.get("extra_requirements") or "").strip()
    lines: list[str] = [inst, "", "【格式与输出约束（系统设置）】"]
    if purpose:
        lines.append(f"- 用途：{purpose}")
    mode = str(prefs.get("target_length_mode") or "").strip().lower()
    target_chars = int(prefs.get("target_char_count") or 0)
    target_pages = int(prefs.get("target_page_count") or 0)
    if mode == "pages" and target_pages > 0:
        lines.append(f"- 目标长度：约{target_pages}页（折合≈{target_chars}字）")
    elif mode == "chars" and target_chars > 0:
        lines.append(f"- 目标长度：约{target_chars}字（折合≈{target_pages}页）")
    if extra_req:
        lines.append(f"- 补充要求：{extra_req}")
    if fmt:
        name = str(fmt.get("font_size_name") or "").strip()
        pt = str(fmt.get("font_size_pt") or "").strip()
        ls = str(fmt.get("line_spacing") or "").strip()
        if name or pt:
            lines.append(f"- 字号：{name or '[默认]'}（{pt or '[默认]'}pt）")
        if ls:
            lines.append(f"- 行距：{ls}")
        h1_pt = str(fmt.get("heading1_size_pt") or "").strip()
        h2_pt = str(fmt.get("heading2_size_pt") or "").strip()
        h3_pt = str(fmt.get("heading3_size_pt") or "").strip()
        h1_font = str(fmt.get("heading1_font_name_east_asia") or fmt.get("heading1_font_name") or "").strip()
        h2_font = str(fmt.get("heading2_font_name_east_asia") or fmt.get("heading2_font_name") or "").strip()
        h3_font = str(fmt.get("heading3_font_name_east_asia") or fmt.get("heading3_font_name") or "").strip()
        if h1_pt or h1_font:
            lines.append(f"- 一级标题：{h1_font or '[默认字体]'} {h1_pt or '[默认字号]'}pt")
        if h2_pt or h2_font:
            lines.append(f"- 二级标题：{h2_font or '[默认字体]'} {h2_pt or '[默认字号]'}pt")
        if h3_pt or h3_font:
            lines.append(f"- 三级标题：{h3_font or '[默认字体]'} {h3_pt or '[默认字号]'}pt")
    if isinstance(table_types, list) and table_types:
        lines.append("- 建议表格类型：" + ", ".join([str(x) for x in table_types]))
    if isinstance(figure_types, list) and figure_types:
        lines.append("- 建议图类型：" + ", ".join([str(x) for x in figure_types]))
    lines.append("- 若缺少具体数据，用保守表述或范围描述补足，不要出现占位提示。")
    lines.append("- 输出为可直接提交的正式专项设计/毕业设计风格，不要出现提示语、草稿说明或AI痕迹。")
    lines.append("- 正文避免出现无关符号或标记（标题行除外）。")
    return "\n".join([x for x in lines if x is not None]).strip()
def _render_blocks_to_html(blocks) -> str:
    out: list[str] = []
    for b in blocks:
        if b.type == "heading":
            level = max(1, min(3, int(b.level or 1)))
            txt = _esc(b.text or "")
            if level == 1:
                out.append(f'<h1 style="text-align:center;margin-bottom:12pt">{txt}</h1>')
            elif level == 2:
                out.append(f'<h2 style="margin-top:12pt;margin-bottom:6pt">{txt}</h2>')
            else:
                out.append(f'<h3 style="margin-top:10pt;margin-bottom:4pt">{txt}</h3>')
        elif b.type == "paragraph":
            body = _esc(b.text or "").replace("\n", "<br/>")
            out.append('<p style="text-align:justify;text-indent:2em;margin-bottom:6pt">' + body + "</p>")
        elif b.type == "table":
            t = b.table or {}
            caption = _esc(str(t.get("caption") or "").strip() or "表格")
            cols = t.get("columns") if isinstance(t, dict) else None
            rows = t.get("rows") if isinstance(t, dict) else None
            columns = [str(c) for c in cols] if isinstance(cols, list) else ["列1", "列2"]
            body = rows if isinstance(rows, list) else [["[待补充]", "[待补充]"]]
            out.append(f'<p style="margin-top:6pt;margin-bottom:4pt"><strong>{caption}</strong></p>')
            out.append('<table class="tbl"><thead><tr>' + "".join(f"<th>{_esc(c)}</th>" for c in columns) + "</tr></thead><tbody>")
            for r in body[:20]:
                rr = r if isinstance(r, list) else [str(r)]
                out.append("<tr>" + "".join(f"<td>{_esc(str(rr[i]) if i < len(rr) else '')}</td>" for i in range(len(columns))) + "</tr>")
            out.append("</tbody></table>")
        elif b.type == "figure":
            f = b.figure or {}
            caption = _esc(str(f.get("caption") or "图"))
            out.append(f'<p style="margin-top:6pt;margin-bottom:4pt"><strong>图：</strong>{caption}（导出docx时为占位）</p>')
            out.append(f'<p style="text-indent:2em;margin-bottom:6pt">[图占位] {caption}</p>')
    return "".join(out)
def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _doc_ir_has_styles(doc_ir) -> bool:
    try:
        data = doc_ir_to_dict(doc_ir) if not isinstance(doc_ir, dict) else doc_ir
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    if isinstance(data.get("style"), dict) and data.get("style"):
        return True
    def block_has_style(block: dict) -> bool:
        if isinstance(block.get("style"), dict) and block.get("style"):
            return True
        runs = block.get("runs")
        if isinstance(runs, list):
            for r in runs:
                if not isinstance(r, dict):
                    continue
                for k in ("bold", "italic", "underline", "strike", "color", "background", "font", "size", "link"):
                    if r.get(k):
                        return True
        return False
    def walk_sections(sections: list[dict]) -> bool:
        for sec in sections:
            if isinstance(sec.get("style"), dict) and sec.get("style"):
                return True
            blocks = sec.get("blocks")
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict) and block_has_style(b):
                        return True
            children = sec.get("children")
            if isinstance(children, list) and walk_sections(children):
                return True
        return False
    sections = data.get("sections")
    if isinstance(sections, list):
        return walk_sections(sections)
    return False
def _style_dict_to_css(style: dict | None) -> str:
    if not isinstance(style, dict):
        return ""
    css = []
    align = str(style.get("align") or style.get("textAlign") or "").strip()
    if align in {"left", "center", "right", "justify"}:
        css.append(f"text-align:{align}")
    line_height = str(style.get("lineHeight") or "").strip()
    if re.match(r"^\d+(\.\d+)?$", line_height):
        css.append(f"line-height:{line_height}")
    indent = str(style.get("indent") or style.get("textIndent") or "").strip()
    if re.match(r"^\d+(\.\d+)?(px|pt|em|rem)?$", indent):
        css.append(f"text-indent:{indent}")
    margin_top = str(style.get("marginTop") or "").strip()
    if re.match(r"^\d+(\.\d+)?(px|pt|em|rem)?$", margin_top):
        css.append(f"margin-top:{margin_top}")
    margin_bottom = str(style.get("marginBottom") or "").strip()
    if re.match(r"^\d+(\.\d+)?(px|pt|em|rem)?$", margin_bottom):
        css.append(f"margin-bottom:{margin_bottom}")
    font_family = str(style.get("fontFamily") or "").strip()
    if font_family:
        css.append(f"font-family:{_esc(font_family)}")
    font_size = str(style.get("fontSize") or "").strip()
    if re.match(r"^\d+(\.\d+)?(px|pt|em|rem)?$", font_size):
        css.append(f"font-size:{font_size}")
    color = str(style.get("color") or "").strip()
    if re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", color) or color.startswith("rgb("):
        css.append(f"color:{_esc(color)}")
    background = str(style.get("background") or style.get("backgroundColor") or "").strip()
    if re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", background) or background.startswith("rgb("):
        css.append(f"background-color:{_esc(background)}")
    return f' style="{";".join(css)}"' if css else ""
def _run_to_html(run: dict) -> str:
    txt = _esc(str(run.get("text") or "")).replace("\n", "<br/>")
    if not txt:
        return ""
    inner = txt
    if run.get("bold"):
        inner = f"<strong>{inner}</strong>"
    if run.get("italic"):
        inner = f"<em>{inner}</em>"
    if run.get("underline"):
        inner = f"<u>{inner}</u>"
    if run.get("strike"):
        inner = f"<del>{inner}</del>"
    link = str(run.get("link") or "").strip()
    if link:
        inner = f'<a href="{_esc(link)}" target="_blank" rel="noopener">{inner}</a>'
    css = []
    color = str(run.get("color") or "").strip()
    if re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", color) or color.startswith("rgb("):
        css.append(f"color:{_esc(color)}")
    background = str(run.get("background") or "").strip()
    if re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", background) or background.startswith("rgb("):
        css.append(f"background-color:{_esc(background)}")
    font = str(run.get("font") or "").strip()
    if font:
        css.append(f"font-family:{_esc(font)}")
    size = str(run.get("size") or "").strip()
    if re.match(r"^\d+(\.\d+)?(px|pt|em|rem)?$", size):
        css.append(f"font-size:{size}")
    if css:
        inner = f'<span style="{";".join(css)}">{inner}</span>'
    return inner
def _runs_to_html(runs: list[dict]) -> str:
    parts = [_run_to_html(r) for r in runs if isinstance(r, dict)]
    return "".join([p for p in parts if p])
def _doc_ir_to_html(doc_ir) -> str:
    data = doc_ir_to_dict(doc_ir) if not isinstance(doc_ir, dict) else doc_ir
    if not isinstance(data, dict):
        return ""
    title = str(data.get("title") or "").strip()
    parts: list[str] = []
    if title:
        parts.append(f'<h1 style="text-align:center;margin-bottom:12pt">{_esc(title)}</h1>')
    def render_block(block: dict) -> str:
        t = str(block.get("type") or "paragraph").lower()
        style = _style_dict_to_css(block.get("style") if isinstance(block.get("style"), dict) else None)
        runs = block.get("runs") if isinstance(block.get("runs"), list) else None
        if t == "heading":
            level = max(1, min(6, int(block.get("level") or 1)))
            if runs:
                inner = _runs_to_html(runs)
            else:
                inner = _esc(str(block.get("text") or ""))
            return f"<h{level}{style}>{inner}</h{level}>"
        if t in {"paragraph", "text", "p"}:
            if runs:
                inner = _runs_to_html(runs)
            else:
                inner = _esc(str(block.get("text") or "")).replace("\n", "<br/>")
            return f"<p{style}>{inner}</p>"
        if t == "list":
            ordered = bool(block.get("ordered"))
            items = block.get("items") if isinstance(block.get("items"), list) else []
            li = "".join([f"<li{style}>{_esc(str(it))}</li>" for it in items if str(it).strip()])
            tag = "ol" if ordered else "ul"
            return f"<{tag}{style}>{li}</{tag}>"
        if t == "table":
            tdata = block.get("table") if isinstance(block.get("table"), dict) else {}
            caption = _esc(str(tdata.get("caption") or "").strip() or "表格")
            cols = tdata.get("columns") if isinstance(tdata.get("columns"), list) else []
            rows = tdata.get("rows") if isinstance(tdata.get("rows"), list) else []
            if not cols:
                cols = ["列1", "列2"]
            head = "".join([f"<th>{_esc(str(c))}</th>" for c in cols])
            body_rows = []
            for r in rows[:20]:
                rlist = r if isinstance(r, list) else [r]
                row_html = "".join(
                    [f"<td>{_esc(str(rlist[i]) if i < len(rlist) else '')}</td>" for i in range(len(cols))]
                )
                body_rows.append(f"<tr>{row_html}</tr>")
            body = "".join(body_rows)
            return (
                f"<p style=\"margin-top:6pt;margin-bottom:4pt\"><strong>{caption}</strong></p>"
                f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
            )
        if t == "figure":
            fdata = block.get("figure") if isinstance(block.get("figure"), dict) else {}
            caption = _esc(str(fdata.get("caption") or "图"))
            return f'<p style="margin-top:6pt;margin-bottom:4pt"><strong>图：</strong>{caption}</p>'
        return ""
    def walk_sections(sections: list[dict]) -> None:
        for sec in sections:
            sec_title = str(sec.get("title") or "").strip()
            level = max(1, min(6, int(sec.get("level") or 2)))
            sec_style = _style_dict_to_css(sec.get("style") if isinstance(sec.get("style"), dict) else None)
            if sec_title:
                parts.append(f"<h{level}{sec_style}>{_esc(sec_title)}</h{level}>")
            blocks = sec.get("blocks")
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict):
                        html = render_block(b)
                        if html:
                            parts.append(html)
            children = sec.get("children")
            if isinstance(children, list):
                walk_sections(children)
    sections = data.get("sections")
    if isinstance(sections, list):
        walk_sections(sections)
    return "".join(parts)
# === 版本树API ===
@app.post("/api/doc/{doc_id}/version/commit")
async def api_version_commit(doc_id: str, request: Request) -> dict:
    """提交新版本（类似git commit）"""
    session = store.get(doc_id)
    if not session:
        raise HTTPException(404, "文档不存在")
    
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        payload = {}
    
    message = payload.get("message", "保存版本")
    author = payload.get("author", "user")
    tags = payload.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    kind = str(payload.get("kind") or "").strip().lower()
    if not tags and not kind:
        kind = "major"
    if kind == "major" and "major" not in tags:
        tags.append("major")
    elif kind == "minor" and "minor" not in tags:
        tags.append("minor")
    
    # 生成新版本ID
    version_id = uuid.uuid4().hex[:12]
    
    # 创建版本节点
    version = VersionNode(
        version_id=version_id,
        parent_id=session.current_version_id,
        timestamp=time.time(),
        message=message,
        author=author,
        doc_text=session.doc_text,
        doc_ir=session.doc_ir.copy() if session.doc_ir else {},
        tags=tags,
        branch_name=_get_current_branch(session)
    )
    
    # 保存版本
    session.versions[version_id] = version
    session.current_version_id = version_id
    
    # 更新分支指针
    branch = _get_current_branch(session)
    session.branches[branch] = version_id
    
    store.put(session)
    
    return {
        "ok": 1,
        "version_id": version_id,
        "message": message,
        "timestamp": version.timestamp,
        "kind": kind or ""
    }
@app.get("/api/doc/{doc_id}/version/log")
def _version_kind_from_tags(tags) -> str:
    if not isinstance(tags, list):
        return ""
    if "major" in tags:
        return "major"
    if "minor" in tags:
        return "minor"
    return ""
def _version_diff_summary(prev_doc_ir: dict, next_doc_ir: dict) -> dict:
    try:
        old_doc = doc_ir_from_dict(prev_doc_ir or {})
        new_doc = doc_ir_from_dict(next_doc_ir or {})
        diff = doc_ir_diff(old_doc, new_doc)
    except Exception:
        return {}
    counts = {"insert": 0, "delete": 0, "replace": 0}
    for op, _, _ in diff:
        if op in counts:
            counts[op] += 1
    return counts
def api_version_log(doc_id: str, branch: str = "main", limit: int = 50) -> dict:
    """获取版本历史（类似git log）"""
    session = store.get(doc_id)
    if not session:
        raise HTTPException(404, "文档不存在")
    
    # 从分支HEAD开始回溯
    head_id = session.branches.get(branch)
    if not head_id:
        return {"ok": 1, "versions": [], "branch": branch}
    
    versions = []
    current_id = head_id
    count = 0
    
    while current_id and count < limit:
        version = session.versions.get(current_id)
        if not version:
            break
        
        summary = {}
        if version.parent_id and version.parent_id in session.versions:
            parent = session.versions.get(version.parent_id)
            if parent:
                summary = _version_diff_summary(parent.doc_ir, version.doc_ir)
        versions.append({
            "version_id": version.version_id,
            "parent_id": version.parent_id,
            "timestamp": version.timestamp,
            "message": version.message,
            "author": version.author,
            "tags": version.tags,
            "kind": _version_kind_from_tags(version.tags),
            "summary": summary,
            "branch_name": version.branch_name,
            "is_current": current_id == session.current_version_id
        })
        
        current_id = version.parent_id
        count += 1
    
    return {"ok": 1, "versions": versions, "branch": branch}
@app.get("/api/doc/{doc_id}/version/tree")
def api_version_tree(doc_id: str) -> dict:
    """获取完整版本树（可视化用）"""
    session = store.get(doc_id)
    if not session:
        raise HTTPException(404, "文档不存在")
    
    # 构建邻接表
    nodes = []
    edges = []
    
    for vid, version in session.versions.items():
        nodes.append({
            "id": vid,
            "message": version.message,
            "author": version.author,
            "timestamp": version.timestamp,
            "tags": version.tags,
            "branch": version.branch_name,
            "is_current": vid == session.current_version_id
        })
        
        if version.parent_id:
            edges.append({
                "from": version.parent_id,
                "to": vid
            })
    
    return {
        "ok": 1,
        "nodes": nodes,
        "edges": edges,
        "branches": session.branches,
        "current": session.current_version_id
    }
@app.post("/api/doc/{doc_id}/version/checkout")
async def api_version_checkout(doc_id: str, request: Request) -> dict:
    """切换到指定版本（类似git checkout）"""
    session = store.get(doc_id)
    if not session:
        raise HTTPException(404, "文档不存在")
    
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        raise HTTPException(400, "参数错误")
    
    version_id = payload.get("version_id")
    if not version_id:
        raise HTTPException(400, "缺少version_id")
    
    version = session.versions.get(version_id)
    if not version:
        raise HTTPException(404, "版本不存在")
    
    # 恢复版本快照
    session.doc_text = version.doc_text
    session.doc_ir = version.doc_ir.copy() if version.doc_ir else {}
    session.current_version_id = version_id
    
    store.put(session)
    
    return {
        "ok": 1,
        "version_id": version_id,
        "message": version.message,
        "doc_text": version.doc_text
    }
@app.post("/api/doc/{doc_id}/version/branch")
async def api_version_branch(doc_id: str, request: Request) -> dict:
    """创建新分支（类似git branch）"""
    session = store.get(doc_id)
    if not session:
        raise HTTPException(404, "文档不存在")
    
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        raise HTTPException(400, "参数错误")
    
    branch_name = payload.get("branch_name", "").strip()
    if not branch_name:
        raise HTTPException(400, "分支名不能为空")
    
    if branch_name in session.branches:
        raise HTTPException(400, f"分支'{branch_name}'已存在")
    
    # 从当前HEAD创建分支
    base_version_id = payload.get("base_version_id") or session.current_version_id
    if base_version_id and base_version_id not in session.versions:
        raise HTTPException(404, "基础版本不存在")
    
    session.branches[branch_name] = base_version_id or ""
    store.put(session)
    
    return {
        "ok": 1,
        "branch_name": branch_name,
        "base_version_id": base_version_id
    }
@app.get("/api/doc/{doc_id}/version/diff")
def api_version_diff(doc_id: str, from_version: str, to_version: str) -> dict:
    """对比两个版本差异（类似git diff）"""
    session = store.get(doc_id)
    if not session:
        raise HTTPException(404, "文档不存在")
    
    v1 = session.versions.get(from_version)
    v2 = session.versions.get(to_version)
    
    if not v1 or not v2:
        raise HTTPException(404, "版本不存在")
    
    # 简单文本diff（按行）
    lines1 = v1.doc_text.split('\n')
    lines2 = v2.doc_text.split('\n')
    
    import difflib
    diff = list(difflib.unified_diff(
        lines1, lines2,
        fromfile=f'version {from_version}',
        tofile=f'version {to_version}',
        lineterm=''
    ))
    
    return {
        "ok": 1,
        "from_version": from_version,
        "to_version": to_version,
        "diff": diff,
        "from_message": v1.message,
        "to_message": v2.message
    }
@app.post("/api/doc/{doc_id}/version/tag")
async def api_version_tag(doc_id: str, request: Request) -> dict:
    """给版本打标签（类似git tag）"""
    session = store.get(doc_id)
    if not session:
        raise HTTPException(404, "文档不存在")
    
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        raise HTTPException(400, "参数错误")
    
    version_id = payload.get("version_id")
    tag = payload.get("tag", "").strip()
    
    if not version_id or not tag:
        raise HTTPException(400, "缺少参数")
    
    version = session.versions.get(version_id)
    if not version:
        raise HTTPException(404, "版本不存在")
    
    if tag not in version.tags:
        version.tags.append(tag)
        store.put(session)
    
    return {"ok": 1, "version_id": version_id, "tag": tag}
def _get_current_branch(session) -> str:
    """获取当前所在分支"""
    if not session.current_version_id:
        return "main"
    
    current = session.versions.get(session.current_version_id)
    return current.branch_name if current else "main"
def _auto_commit_version(session, message: str, *, author: str = "system", tags: list[str] | None = None) -> str | None:
    if session is None:
        return None
    text = str(session.doc_text or "").strip()
    if not text:
        return None
    doc_ir = session.doc_ir.copy() if session.doc_ir else {}
    tag_list = list(tags or [])
    if "minor" not in tag_list:
        tag_list.append("minor")
    if "auto" not in tag_list:
        tag_list.append("auto")
    cur_id = session.current_version_id
    if cur_id and cur_id in session.versions:
        cur = session.versions.get(cur_id)
        if cur and str(cur.doc_text or "").strip() == text and (cur.doc_ir or {}) == (doc_ir or {}):
            return None
    version_id = uuid.uuid4().hex[:12]
    branch = _get_current_branch(session)
    version = VersionNode(
        version_id=version_id,
        parent_id=session.current_version_id,
        timestamp=time.time(),
        message=message or "auto commit",
        author=author,
        doc_text=session.doc_text,
        doc_ir=session.doc_ir.copy() if session.doc_ir else {},
        tags=tag_list,
        branch_name=branch,
    )
    session.versions[version_id] = version
    session.current_version_id = version_id
    session.branches[branch] = version_id
    return version_id
def _convert_to_latex(text: str, title: str) -> str:
    """转换Markdown到LaTeX"""
    lines = text.split('\n')
    latex_lines = [
        r'\documentclass[12pt,a4paper]{article}',
        r'\usepackage[UTF8]{ctex}',
        r'\usepackage{amsmath}',
        r'\usepackage{graphicx}',
        r'\usepackage{hyperref}',
        r'\title{' + title + r'}',
        r'\author{user}',
        r'\date{\today}',
        r'\begin{document}',
        r'\maketitle',
        ''
    ]
    
    for line in lines:
        # 标题
        if line.startswith('### '):
            latex_lines.append(r'\subsubsection{' + line[4:].strip() + r'}')
        elif line.startswith('## '):
            latex_lines.append(r'\subsection{' + line[3:].strip() + r'}')
        elif line.startswith('# '):
            latex_lines.append(r'\section{' + line[2:].strip() + r'}')
        # 加粗/斜体
        elif line.strip():
            processed = line
            processed = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', processed)
            processed = re.sub(r'\*(.+?)\*', r'\\textit{\1}', processed)
            processed = re.sub(r'\[@([a-zA-Z0-9_-]+)\]', r'\\cite{\1}', processed)
            latex_lines.append(processed)
            latex_lines.append('')
    
    latex_lines.extend([
        '',
        r'\end{document}'
    ])
    
    return '\n'.join(latex_lines)
def _render_blocks_to_html(blocks) -> str:
    """将解析后的blocks转为HTML"""
    html_parts = []
    
    for block in blocks:
        if block.type == "heading":
            level = min(3, max(1, block.level))
            html_parts.append(f'<h{level}>{block.text}</h{level}>')
        elif block.type == "paragraph":
            text = block.text.replace('\n', '<br/>')
            # 处理引用标记
            text = re.sub(r'\[@([a-zA-Z0-9_-]+)\]', r'<sup class="citation-ref">[\1]</sup>', text)
            html_parts.append(f'<p>{text}</p>')
        elif block.type == "table":
            html_parts.append('<table>')
            html_parts.append('<thead><tr>')
            for col in (block.table.columns if hasattr(block.table, 'columns') else []):
                html_parts.append(f'<th>{col}</th>')
            html_parts.append('</tr></thead><tbody>')
            for row in (block.table.rows if hasattr(block.table, 'rows') else []):
                html_parts.append('<tr>')
                for cell in row:
                    html_parts.append(f'<td>{cell}</td>')
                html_parts.append('</tr>')
            html_parts.append('</tbody></table>')
    
    return '\n'.join(html_parts)
def _default_title() -> str:
    stamp = time.strftime("%Y%m%d-%H%M")
    return "自动生成文档-" + stamp
def _extract_title(text: str) -> str:
    '''Extract document title.'''
    if not text:
        return _default_title()
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    for line in lines:
        line = re.sub(r"[#*_`]+", "", line or "").strip()
        if line:
            return line[:24].rstrip()
    return _default_title()
