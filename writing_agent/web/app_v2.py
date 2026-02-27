"""App V2 module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations
import io
import json
import logging
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from difflib import SequenceMatcher
from dataclasses import dataclass
from typing import Iterable
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request as UrlRequest, urlopen
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
# 閰嶇疆鏃ュ織
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
from writing_agent.llm import OllamaClient, OllamaError, get_default_provider, get_ollama_settings
from writing_agent.storage import InMemoryStore, VersionNode
from writing_agent.mcp_client import fetch_mcp_resource
from writing_agent.web.html_sanitize import sanitize_html
from writing_agent.web.block_edit import apply_block_edit
from writing_agent.web.generation_lock import DocGenerationState
from writing_agent.web.domains import (
    citation_alert_domain,
    citation_render_domain,
    doc_state_domain,
    doc_ir_html_domain,
    export_settings_domain,
    export_quality_domain,
    export_structure_domain,
    fallback_content_domain,
    heading_candidates_domain,
    heading_equivalence_domain,
    heading_glue_domain,
    instruction_requirements_domain,
    length_target_domain,
    prefs_analysis_domain,
    prefs_extract_domain,
    plagiarism_domain,
    revision_edit_runtime_domain,
    section_edit_ops_domain,
    version_state_domain,
)
from writing_agent.web.generate_request import (
    apply_compose_mode_instruction as _apply_compose_mode_instruction,
    apply_resume_sections_instruction as _apply_resume_sections_instruction,
    decode_section_title_for_stream as _decode_section_title_for_stream,
    extract_format_only_updates as _extract_format_only_updates_base,
    looks_like_modify_instruction as _looks_like_modify_instruction_base,
    normalize_compose_mode as _normalize_compose_mode,
    normalize_resume_sections as _normalize_resume_sections,
    normalize_section_key_for_stream as _normalize_section_key_for_stream,
    should_route_to_revision as _should_route_to_revision_base,
    try_format_only_update as _try_format_only_update_base,
    try_handle_format_only_request as _try_handle_format_only_request_base,
)
from writing_agent.web.text_export import (
    convert_to_latex as _convert_to_latex_base,
    default_title as _default_title_base,
    esc_html as _esc_base,
    extract_title as _extract_title_base,
    render_blocks_to_html as _render_blocks_to_html_base,
)
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
    build_index as doc_ir_build_index,
    render_block_text as doc_ir_render_block_text,
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
from writing_agent.v2.rag.crossref import search_crossref
from writing_agent.v2.rag.openalex import search_openalex
from writing_agent.quality.plagiarism import compare_against_references
from writing_agent.quality.ai_rate import estimate_ai_rate
from writing_agent.observability import get_bridge
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
_DOC_GENERATION_STATE = DocGenerationState()

def _try_begin_doc_generation(doc_id: str, *, mode: str, target_ids: list[str] | None = None) -> str | None:
    return _DOC_GENERATION_STATE.try_begin(doc_id, mode=mode, target_ids=target_ids)

def _doc_lock_wait_seconds(mode: str) -> float:
    mode_key = str(mode or "").strip().lower()
    per_mode_key = f"WRITING_AGENT_DOC_LOCK_WAIT_{mode_key.upper()}_S"
    raw = str(os.environ.get(per_mode_key, "")).strip()
    if not raw:
        raw = str(os.environ.get("WRITING_AGENT_DOC_LOCK_WAIT_S", "6")).strip()
    try:
        wait_s = float(raw)
    except Exception:
        wait_s = 6.0
    return max(0.0, min(30.0, wait_s))

def _try_begin_doc_generation_with_wait(
    doc_id: str,
    *,
    mode: str,
    target_ids: list[str] | None = None,
) -> str | None:
    wait_s = _doc_lock_wait_seconds(mode)
    return _DOC_GENERATION_STATE.begin_with_wait(
        doc_id,
        mode=mode,
        target_ids=target_ids,
        wait_s=wait_s,
        poll_s=0.15,
    )

def _finish_doc_generation(doc_id: str, token: str | None) -> None:
    _DOC_GENERATION_STATE.finish(doc_id, token)

def _touch_doc_generation(doc_id: str, token: str | None = None) -> bool:
    return _DOC_GENERATION_STATE.touch(doc_id, token)

def _generation_busy_message(doc_id: str) -> str:
    return _DOC_GENERATION_STATE.busy_message(doc_id)

def _is_doc_generation_busy(doc_id: str) -> bool:
    return _DOC_GENERATION_STATE.is_busy(doc_id)

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
from writing_agent.web import app_v2_generation_helpers_runtime as _generation_helpers_runtime
_generation_helpers_runtime.install(globals())

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
        _static_mtime(BASE_DIR / "static" / "v2_legacy_runtime.js"),
        _static_mtime(BASE_DIR / "static" / "v2_svelte" / "main.js"),
        _static_mtime(BASE_DIR / "static" / "v2_svelte" / "style.css"),
    )
)
PERF_MODE = os.environ.get("WRITING_AGENT_PERF_MODE", "").strip() == "1"

@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    await _startup_warm_models()
    yield

app = FastAPI(title="Writing Agent Studio (v2)", lifespan=_app_lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
_OTEL_BRIDGE = get_bridge()

@app.middleware("http")
async def _security_and_request_id_middleware(request: Request, call_next):
    request_id = str(request.headers.get("x-request-id") or "").strip() or uuid.uuid4().hex
    correlation_id = str(request.headers.get("x-correlation-id") or "").strip() or request_id
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    with _OTEL_BRIDGE.span("http.request", correlation_id=correlation_id):
        response = await call_next(request)
    response.headers.setdefault("X-Request-ID", request_id)
    response.headers.setdefault("X-Correlation-ID", correlation_id)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response

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
LOW_SATISFACTION_PATH = DATA_DIR / "learning" / "low_satisfaction_feedback.jsonl"
_LOW_SATISFACTION_LOCK = threading.Lock()
PLAGIARISM_REPORT_DIR = DATA_DIR / "plagiarism_reports"
rag_store = RagStore(RAG_DIR)
rag_index = RagIndex(RAG_DIR)
user_library = UserLibrary(USER_LIBRARY_DIR, rag_index)
_INTERNAL_PREF_PREFIX = "_wa_"
_RESUME_STATE_KEY = "_wa_resume_state"
_CITATION_VERIFY_KEY = "_wa_citation_verify"
_PLAGIARISM_SCAN_KEY = "_wa_plagiarism_scan"
_AI_RATE_KEY = "_wa_ai_rate_latest"
_CITATION_VERIFY_ALERTS_CONFIG_PATH = DATA_DIR / "citation_verify_alerts_config.json"
_CITATION_VERIFY_ALERTS_CONFIG_LOCK = threading.Lock()
_CITATION_VERIFY_ALERTS_CONFIG_CACHE: dict | None = None
_CITATION_VERIFY_ALERTS_CONFIG_LOADED = False
_CITATION_VERIFY_ALERT_NOTIFY_LOCK = threading.Lock()
_CITATION_VERIFY_ALERT_EVENTS_PATH = DATA_DIR / "citation_verify_alert_events.json"
_CITATION_VERIFY_ALERT_EVENTS_LOCK = threading.Lock()
_CITATION_VERIFY_METRICS_TRENDS_PATH = DATA_DIR / "citation_verify_metrics_trends.json"
_CITATION_VERIFY_METRICS_TRENDS_LOCK = threading.Lock()
_CITATION_VERIFY_ALERT_NOTIFY_STATE: dict[str, object] = {
    "severity": "ok",
    "signature": "",
    "last_sent_at": 0.0,
    "suppressed": 0,
    "last_error": "",
    "last_event_type": "",
    "last_event_id": "",
}

def _merge_generation_prefs(existing: dict | None, incoming: dict | None) -> dict:
    out: dict = dict(incoming or {})
    for k, v in (existing or {}).items():
        key = str(k or "")
        if key.startswith(_INTERNAL_PREF_PREFIX) and key not in out:
            out[key] = v
    return out

def _set_internal_pref(session, key: str, value: object) -> None:
    prefs = dict(session.generation_prefs or {})
    if value is None:
        prefs.pop(key, None)
    else:
        prefs[key] = value
    session.generation_prefs = prefs

def _get_internal_pref(session, key: str, default: object = None) -> object:
    prefs = session.generation_prefs if isinstance(session.generation_prefs, dict) else {}
    if not isinstance(prefs, dict):
        return default
    return prefs.get(key, default)

def _update_resume_state(
    session,
    *,
    status: str,
    user_instruction: str | None = None,
    request_instruction: str | None = None,
    compose_mode: str | None = None,
    partial_text: str | None = None,
    plan_sections: list[str] | None = None,
    completed_sections: list[str] | None = None,
    completed_section: str | None = None,
    cursor_anchor: str | None = None,
    error: str | None = None,
) -> None:
    old = _get_internal_pref(session, _RESUME_STATE_KEY, {}) or {}
    state = dict(old if isinstance(old, dict) else {})
    state["status"] = str(status or "").strip().lower() or "unknown"
    state["updated_at"] = time.time()
    if user_instruction is not None:
        state["user_instruction"] = str(user_instruction or "")
    if request_instruction is not None:
        state["request_instruction"] = str(request_instruction or "")
    if compose_mode is not None:
        state["compose_mode"] = _normalize_compose_mode(compose_mode)
    if partial_text is not None:
        src = str(partial_text or "")
        clean = src.strip()
        state["partial_chars"] = len(clean)
        state["partial_preview"] = clean[-240:] if clean else ""
    if plan_sections is not None:
        state["plan_sections"] = _normalize_resume_sections(plan_sections)
    if completed_sections is not None:
        state["completed_sections"] = _normalize_resume_sections(completed_sections)
    if completed_section is not None:
        done = _normalize_resume_sections(state.get("completed_sections"))
        sec = str(completed_section or "").strip()
        if sec and sec not in done:
            done.append(sec)
        state["completed_sections"] = done
    if cursor_anchor is not None:
        state["cursor_anchor"] = str(cursor_anchor or "").strip()
    plan = _normalize_resume_sections(state.get("plan_sections"))
    done = _normalize_resume_sections(state.get("completed_sections"))
    if plan:
        state["pending_sections"] = [sec for sec in plan if sec not in set(done)]
    else:
        state["pending_sections"] = []
    if error is not None:
        state["error"] = str(error or "")
    _set_internal_pref(session, _RESUME_STATE_KEY, state)

def _get_resume_state_payload(session) -> dict:
    raw = _get_internal_pref(session, _RESUME_STATE_KEY, {}) or {}
    if not isinstance(raw, dict):
        return {}
    status = str(raw.get("status") or "").strip().lower()
    if status not in {"running", "interrupted"}:
        return {}
    return {
        "status": status,
        "updated_at": float(raw.get("updated_at") or 0.0),
        "user_instruction": str(raw.get("user_instruction") or ""),
        "request_instruction": str(raw.get("request_instruction") or ""),
        "compose_mode": _normalize_compose_mode(raw.get("compose_mode")),
        "partial_chars": int(raw.get("partial_chars") or 0),
        "partial_preview": str(raw.get("partial_preview") or ""),
        "plan_sections": _normalize_resume_sections(raw.get("plan_sections")),
        "completed_sections": _normalize_resume_sections(raw.get("completed_sections")),
        "pending_sections": _normalize_resume_sections(raw.get("pending_sections")),
        "cursor_anchor": str(raw.get("cursor_anchor") or ""),
        "error": str(raw.get("error") or ""),
    }

def _export_gate_policy(session) -> str:
    prefs = session.generation_prefs if isinstance(session.generation_prefs, dict) else {}
    raw = str((prefs or {}).get("export_gate_policy") or os.environ.get("WRITING_AGENT_EXPORT_GATE_POLICY", "strict")).strip().lower()
    if raw in {"off", "disabled", "none"}:
        return "off"
    if raw in {"warn", "warning", "warn-only", "warn_only"}:
        return "warn"
    return "strict"

_ALLOWED_UPLOAD_EXTS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".html",
    ".htm",
    ".pdf",
    ".doc",
    ".docx",
    ".odt",
    ".rtf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".svg",
}
_TEXT_UPLOAD_EXTS = {".txt", ".md", ".csv", ".json", ".html", ".htm"}
_IMAGE_UPLOAD_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}

def _normalize_upload_filename(name: str) -> str:
    base = Path(str(name or "").strip()).name
    base = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", base).strip(" .")
    if not base:
        base = "upload.bin"
    if len(base) > 120:
        stem = Path(base).stem[:80] or "upload"
        suffix = Path(base).suffix[:20]
        base = f"{stem}{suffix}"
    return base

def _looks_like_binary_payload(raw: bytes) -> bool:
    if not raw:
        return False
    sample = raw[:4096]
    if b"\x00" in sample:
        return True
    bad = sum(1 for b in sample if (b < 9 or (13 < b < 32)))
    return bad > max(8, len(sample) // 16)

def _detect_image_type(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return "gif"
    if raw.startswith(b"BM"):
        return "bmp"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    if raw[:256].lstrip().startswith(b"<svg") or b"<svg" in raw[:2048]:
        return "svg"
    return ""

def _validate_upload_payload(*, suffix: str, raw: bytes) -> None:
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large (max 50MB)")
    if suffix in _IMAGE_UPLOAD_EXTS:
        detected = _detect_image_type(raw)
        expected = suffix.lstrip(".")
        if expected == "jpg":
            expected = "jpeg"
        if not detected or detected != expected:
            raise HTTPException(
                status_code=400,
                detail="invalid image payload: content does not match extension",
            )
    if suffix in _TEXT_UPLOAD_EXTS and _looks_like_binary_payload(raw):
        raise HTTPException(status_code=400, detail="invalid text payload: appears to be binary data")

async def _read_upload_payload(file: UploadFile) -> tuple[str, str, bytes]:
    if file is None or not (file.filename or "").strip():
        raise HTTPException(status_code=400, detail="file required")
    source_name = _normalize_upload_filename(file.filename or "")
    suffix = Path(source_name).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_EXTS:
        raise HTTPException(status_code=400, detail=f"unsupported file type: {suffix or 'unknown'}")
    raw = await file.read()
    _validate_upload_payload(suffix=suffix, raw=raw)
    return source_name, suffix, raw

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
                feedback_json TEXT,
                updated_at REAL
            )
            """
        )
        cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(doc_meta)").fetchall()}
        if "feedback_json" not in cols:
            conn.execute("ALTER TABLE doc_meta ADD COLUMN feedback_json TEXT")
        conn.commit()
    finally:
        conn.close()
def _load_meta(doc_id: str) -> dict:
    _ensure_meta_db()
    conn = sqlite3.connect(META_DB_PATH)
    try:
        cur = conn.execute(
            "SELECT chat_json, thought_json, feedback_json FROM doc_meta WHERE doc_id = ?",
            (doc_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"chat": [], "thoughts": [], "feedback": []}
        chat_raw, thought_raw, feedback_raw = row
        chat = json.loads(chat_raw) if chat_raw else []
        thoughts = json.loads(thought_raw) if thought_raw else []
        feedback = json.loads(feedback_raw) if feedback_raw else []
        if not isinstance(chat, list):
            chat = []
        if not isinstance(thoughts, list):
            thoughts = []
        if not isinstance(feedback, list):
            feedback = []
        return {"chat": chat, "thoughts": thoughts, "feedback": feedback}
    except Exception:
        return {"chat": [], "thoughts": [], "feedback": []}
    finally:
        conn.close()
def _save_meta(
    doc_id: str,
    *,
    chat: list | None = None,
    thoughts: list | None = None,
    feedback: list | None = None,
) -> None:
    _ensure_meta_db()
    existing = _load_meta(doc_id)
    chat_items = chat if chat is not None else existing.get("chat", [])
    thought_items = thoughts if thoughts is not None else existing.get("thoughts", [])
    feedback_items = feedback if feedback is not None else existing.get("feedback", [])
    conn = sqlite3.connect(META_DB_PATH)
    try:
        conn.execute(
            "INSERT INTO doc_meta(doc_id, chat_json, thought_json, feedback_json, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(doc_id) DO UPDATE SET "
            "chat_json=excluded.chat_json, thought_json=excluded.thought_json, "
            "feedback_json=excluded.feedback_json, updated_at=excluded.updated_at",
            (
                doc_id,
                json.dumps(chat_items, ensure_ascii=False),
                json.dumps(thought_items, ensure_ascii=False),
                json.dumps(feedback_items, ensure_ascii=False),
                time.time(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

def _low_satisfaction_threshold() -> int:
    raw = str(os.environ.get("WRITING_AGENT_LOW_SAT_THRESHOLD", "2")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 2
    return max(1, min(5, value))

def _normalize_feedback_item(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    rating_raw = raw.get("rating", raw.get("score"))
    try:
        rating = int(rating_raw)
    except Exception:
        return None
    if rating < 1 or rating > 5:
        return None
    note = str(raw.get("note") or raw.get("comment") or "").strip()[:600]
    stage = str(raw.get("stage") or "general").strip()[:80] or "general"
    tags_raw = raw.get("tags")
    tags: list[str] = []
    if isinstance(tags_raw, list):
        for tag in tags_raw[:20]:
            t = str(tag or "").strip()
            if t:
                tags.append(t[:40])
    created_raw = raw.get("created_at")
    try:
        created_at = float(created_raw) if created_raw is not None else time.time()
    except Exception:
        created_at = time.time()
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex),
        "rating": rating,
        "note": note,
        "stage": stage,
        "tags": tags,
        "created_at": created_at,
    }

def _append_low_satisfaction_event(
    doc_id: str,
    item: dict,
    *,
    context: dict | None = None,
    doc_text: str = "",
) -> bool:
    event = {
        "event_id": uuid.uuid4().hex,
        "doc_id": str(doc_id or "").strip(),
        "rating": int(item.get("rating") or 0),
        "stage": str(item.get("stage") or "general"),
        "note": str(item.get("note") or ""),
        "tags": list(item.get("tags") or []),
        "feedback_created_at": float(item.get("created_at") or time.time()),
        "recorded_at": time.time(),
        "context": dict(context or {}),
        "text_preview": str(doc_text or "").strip()[:1200],
    }
    try:
        LOW_SATISFACTION_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False)
        with _LOW_SATISFACTION_LOCK:
            with LOW_SATISFACTION_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return True
    except Exception:
        return False

def _load_low_satisfaction_events(limit: int = 200) -> list[dict]:
    cap = max(1, min(5000, int(limit or 200)))
    if not LOW_SATISFACTION_PATH.exists():
        return []
    try:
        lines = LOW_SATISFACTION_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    items: list[dict] = []
    for raw in lines[-cap:]:
        row = str(raw or "").strip()
        if not row:
            continue
        try:
            data = json.loads(row)
        except Exception:
            continue
        if isinstance(data, dict):
            items.append(data)
    return items

def _clamp_plagiarism_threshold(value: object, default: float = 0.35) -> float:
    return plagiarism_domain.clamp_plagiarism_threshold(value, default=default)

def _clamp_ai_rate_threshold(value: object, default: float = 0.65) -> float:
    return plagiarism_domain.clamp_ai_rate_threshold(value, default=default)

def _normalize_plagiarism_reference_texts(raw: object) -> list[dict]:
    return plagiarism_domain.normalize_plagiarism_reference_texts(raw)

def _collect_plagiarism_doc_references(
    raw_doc_ids: object,
    *,
    exclude_doc_id: str = "",
    max_count: int = 80,
    min_chars: int = 20,
) -> list[dict]:
    return plagiarism_domain.collect_plagiarism_doc_references(
        raw_doc_ids,
        store=store,
        safe_doc_text=_safe_doc_text,
        extract_title=_extract_title,
        exclude_doc_id=exclude_doc_id,
        max_count=max_count,
        min_chars=min_chars,
    )

def _dedupe_plagiarism_references(items: list[dict]) -> list[dict]:
    return plagiarism_domain.dedupe_plagiarism_references(items)

def _safe_plagiarism_report_id(raw: object) -> str:
    return plagiarism_domain.safe_plagiarism_report_id(raw)

def _new_plagiarism_report_id() -> str:
    return plagiarism_domain.new_plagiarism_report_id()

def _plagiarism_report_doc_dir(doc_id: str) -> Path:
    return plagiarism_domain.plagiarism_report_doc_dir(doc_id, report_root=PLAGIARISM_REPORT_DIR)

def _build_plagiarism_report_markdown(payload: dict) -> str:
    return plagiarism_domain.build_plagiarism_report_markdown(payload)

def _build_plagiarism_report_csv(payload: dict) -> str:
    return plagiarism_domain.build_plagiarism_report_csv(payload)

def _persist_plagiarism_report(doc_id: str, payload: dict) -> dict:
    return plagiarism_domain.persist_plagiarism_report(
        doc_id,
        payload,
        report_root=PLAGIARISM_REPORT_DIR,
    )

def _warm_ollama_model(model: str) -> None:
    settings = get_ollama_settings()
    if not settings.enabled:
        return
    client = OllamaClient(base_url=settings.base_url, model=model, timeout_s=12.0)
    if not client.is_running():
        return
    try:
        client.chat(system="Reply with OK only.", user="OK", temperature=0.0)
    except Exception:
        return
async def _startup_warm_models() -> None:
    """鍚姩鏃堕鐑ā鍨嬶紝鍑忓皯棣栨鐢熸垚寤惰繜"""
    model = os.environ.get("WRITING_AGENT_EXTRACT_MODEL", "").strip() or get_ollama_settings().model
    thread = threading.Thread(target=_warm_ollama_model, args=(model,), daemon=True)
    thread.start()
@app.get("/", response_class=HTMLResponse)
def root() -> RedirectResponse:
    session = store.create()
    _set_doc_text(session, "")
    # Defaults: graduation design / report settings (user can override in UI).
    session.formatting = {
        "font_name": "瀹嬩綋",
        "font_name_east_asia": "瀹嬩綋",
        "font_size_name": "灏忓洓",
        "font_size_pt": 12,
        "line_spacing": 28,
        "heading1_font_name": "榛戜綋",
        "heading1_font_name_east_asia": "榛戜綋",
        "heading1_size_pt": 22,
        "heading2_font_name": "榛戜綋",
        "heading2_font_name_east_asia": "榛戜綋",
        "heading2_size_pt": 16,
        "heading3_font_name": "榛戜綋",
        "heading3_font_name_east_asia": "榛戜綋",
        "heading3_size_pt": 16,
    }
    session.generation_prefs = {
        "purpose": "姣曚笟璁捐/璇剧▼璁捐鎶ュ憡",
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
                "message": "document not found or expired",
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
from writing_agent.web import app_v2_forwarders_runtime as _forwarders_runtime
_forwarders_runtime.install(globals())

from writing_agent.web import app_v2_citation_runtime_part1 as _citation_runtime_part1
from writing_agent.web import app_v2_citation_runtime_part2 as _citation_runtime_part2

_citation_runtime_part1.install(globals())
_citation_runtime_part2.install(globals())

def api_doc_delete(doc_id: str) -> dict:
    from writing_agent.web.api.document_flow import doc_delete

    return doc_delete(doc_id)
from writing_agent.web import app_v2_export_intent_runtime as _export_intent_runtime
_export_intent_runtime.install(globals())

_ANALYSIS_INFLIGHT: dict[str, float] = {}
_ANALYSIS_LOCK = threading.Lock()

from writing_agent.web import app_v2_textops_runtime_part1 as _textops_runtime_part1
from writing_agent.web import app_v2_textops_runtime_part2 as _textops_runtime_part2

_textops_runtime_part1.install(globals())
_textops_runtime_part2.install(globals())

_HEADING_EQUIV_ALIASES: dict[str, set[str]] = heading_equivalence_domain.HEADING_EQUIV_ALIASES

_FAST_REPORT_SECTIONS = ["背景", "本周工作", "下周计划", "风险与需协助", "风险与协助", "风险与需支持"]

# === 鐗堟湰鏍?API ===

_FLOW_ROUTERS_REGISTERED = False

def _register_flow_routers() -> None:
    global _FLOW_ROUTERS_REGISTERED
    if _FLOW_ROUTERS_REGISTERED:
        return
    from writing_agent.web.api.citation_flow import router as citation_router
    from writing_agent.web.api.document_flow import router as document_router
    from writing_agent.web.api.editing_flow import router as editing_router
    from writing_agent.web.api.export_flow import router as export_router
    from writing_agent.web.api.feedback_flow import router as feedback_router
    from writing_agent.web.api.generation_flow import router as generation_router
    from writing_agent.web.api.integration_flow import router as integration_router
    from writing_agent.web.api.job_flow import router as job_router
    from writing_agent.web.api.quality_flow import router as quality_router
    from writing_agent.web.api.rag_flow import router as rag_router
    from writing_agent.web.api.template_flow import router as template_router
    from writing_agent.web.api.version_flow import router as version_router

    app.include_router(document_router)
    app.include_router(generation_router)
    app.include_router(job_router)
    app.include_router(integration_router)
    app.include_router(template_router)
    app.include_router(editing_router)
    app.include_router(export_router)
    app.include_router(feedback_router)
    app.include_router(quality_router)
    app.include_router(citation_router)
    app.include_router(rag_router)
    app.include_router(version_router)
    _FLOW_ROUTERS_REGISTERED = True

_register_flow_routers()
