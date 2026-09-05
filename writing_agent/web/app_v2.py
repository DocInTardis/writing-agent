"""App V2 module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from writing_agent.quality.ai_rate import estimate_ai_rate
from writing_agent.quality.plagiarism import compare_against_references
from writing_agent.models import Citation, CitationStyle, FormattingRequirements
from writing_agent.v2.doc_format import _split_heading_glue as _doc_format_split_heading_glue
from writing_agent.v2.doc_format import parse_report_text
from writing_agent.v2.figure_render import render_figure_svg
from writing_agent.v2.rag.crossref import search_crossref
from writing_agent.v2.rag.openalex import search_openalex
from writing_agent.web.block_edit import apply_block_edit
from writing_agent.web.html_sanitize import sanitize_html
from writing_agent.web import meta_db as _meta_db
from writing_agent.web.upload_utils import (
    ALLOWED_UPLOAD_EXTS as _ALLOWED_UPLOAD_EXTS,
    TEXT_UPLOAD_EXTS as _TEXT_UPLOAD_EXTS,
    IMAGE_UPLOAD_EXTS as _IMAGE_UPLOAD_EXTS,
    normalize_upload_filename as _normalize_upload_filename,
    looks_like_binary_payload as _looks_like_binary_payload,
    detect_image_type as _detect_image_type,
    validate_upload_payload as _validate_upload_payload,
    read_upload_payload as _read_upload_payload,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

from writing_agent.document import ExportPrefs, V2ReportDocxExporter
from writing_agent.diagnostics import diagnostic_path, enabled, write_compact_json
from writing_agent.llm import OllamaClient, get_default_provider, get_ollama_settings
from writing_agent.observability import get_bridge
from writing_agent.storage import InMemoryStore
from writing_agent.web.domains import (
    citation_alert_domain,
    citation_render_domain,
    doc_state_domain,
    export_quality_domain,
    export_settings_domain,
    export_structure_domain,
    fallback_content_domain,
    heading_candidates_domain,
    heading_equivalence_domain,
    heading_glue_domain,
    instruction_requirements_domain,
    length_target_domain,
    plagiarism_domain,
    prefs_analysis_domain,
    prefs_extract_domain,
    revision_edit_runtime_domain,
    route_graph_metrics_domain,
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
from writing_agent.web.generation_lock import DocGenerationState


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
_STREAM_METRICS_PATH = diagnostic_path("WRITING_AGENT_STREAM_TIMING_PATH", "stream_timing.json")
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
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("_load_stream_metrics: failed to read %s: %s", _STREAM_METRICS_PATH, exc)
    return {"runs": []}
def _save_stream_metrics(data: dict) -> None:
    write_compact_json(_STREAM_METRICS_PATH, data)
def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    if len(vals) == 1:
        return float(vals[0])
    idx = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * q))))
    return float(vals[idx])
def _record_stream_timing(*, total_s: float, max_gap_s: float) -> None:
    if not enabled("WRITING_AGENT_STREAM_TIMING_ENABLE"):
        return
    data = _load_stream_metrics()
    runs = data.get("runs") if isinstance(data.get("runs"), list) else []
    runs.append({"total_s": float(total_s), "max_gap_s": float(max_gap_s), "ts": time.time()})
    data["runs"] = runs[-30:]
    _save_stream_metrics(data)
from writing_agent.web.legacy_fragments import generation_helpers as _generation_helpers_runtime

_generation_helpers_runtime.install(globals())

from writing_agent.v2.graph_runner import (
    GenerateConfig,
    _format_reference_items,
    _generic_fill_paragraph,
    _is_reference_section,
    _merge_sections_text,
    _plan_title,
    _sanitize_output_text,
    run_generate_graph,
    run_generate_graph_dual_engine,
)
from writing_agent.v2.doc_ir import Operation as DocIROperation
from writing_agent.v2.doc_ir import apply_ops as doc_ir_apply_ops
from writing_agent.v2.doc_ir import build_index as doc_ir_build_index
from writing_agent.v2.doc_ir import diff_blocks as doc_ir_diff
from writing_agent.v2.doc_ir import from_dict as doc_ir_from_dict
from writing_agent.v2.doc_ir import from_text as doc_ir_from_text
from writing_agent.v2.doc_ir import render_block_text as doc_ir_render_block_text
from writing_agent.v2.doc_ir import to_dict as doc_ir_to_dict
from writing_agent.v2.doc_ir import to_parsed as doc_ir_to_parsed
from writing_agent.v2.doc_ir import to_text as doc_ir_to_text
from writing_agent.v2.rag.index import RagIndex
from writing_agent.v2.rag.search import search_papers
from writing_agent.v2.rag.store import RagStore
from writing_agent.v2.rag.user_library import UserLibrary

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
    _meta_db.init(
        meta_db_path=META_DB_PATH,
        low_satisfaction_path=LOW_SATISFACTION_PATH,
    )
    try:
        from writing_agent.web.services.workspace_service import WorkspaceService

        WorkspaceService().cleanup_expired_trash()
    except Exception as exc:
        logger.warning("startup: cleanup_expired_trash failed: %s", exc, exc_info=True)
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
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(REPO_ROOT / ".data"))).resolve()
WORKSPACE_DIR = DATA_DIR / "workspaces"
USER_TEMPLATES_DIR = DATA_DIR / "templates"
RAG_DIR = DATA_DIR / "rag"
USER_LIBRARY_DIR = DATA_DIR / "library"
TEMPLATE_DIR = REPO_ROOT / "templates"
META_DB_PATH = DATA_DIR / "session_meta.db"
LOW_SATISFACTION_PATH = DATA_DIR / "learning" / "low_satisfaction_feedback.jsonl"
_LOW_SATISFACTION_LOCK = threading.Lock()
PLAGIARISM_REPORT_DIR = DATA_DIR / "plagiarism_reports"
store = InMemoryStore(persistence_dir=WORKSPACE_DIR)
docx_exporter = V2ReportDocxExporter()
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
_CITATION_VERIFY_METRICS_TRENDS_CACHE_ROWS: list[dict] | None = None
_CITATION_VERIFY_METRICS_TRENDS_CACHE_PATH = ""
_CITATION_VERIFY_METRICS_TRENDS_CACHE_MTIME_NS = -1
_CITATION_VERIFY_METRICS_TRENDS_DIRTY = False
_CITATION_VERIFY_METRICS_TRENDS_LAST_WRITE_AT = 0.0
_CITATION_VERIFY_ALERT_NOTIFY_STATE: dict[str, object] = {
    "severity": "ok",
    "signature": "",
    "last_sent_at": 0.0,
    "suppressed": 0,
    "last_error": "",
    "last_event_type": "",
    "last_event_id": "",
}


def _extract_title(text: str) -> str:
    src = str(text or "")
    for line in src.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = re.sub(r"^#+\s*", "", stripped).strip()
            if title:
                return title[:120]
        cleaned = re.sub(r"[#*_`]+", "", stripped).strip()
        if cleaned:
            return cleaned[:80]
    return ""


def _set_doc_text(session, text: str) -> None:
    clean = str(text or "")
    doc_state_domain.set_doc_text(
        session,
        clean,
        doc_ir_to_dict=doc_ir_to_dict,
        doc_ir_from_text=doc_ir_from_text,
    )
    title = _extract_title(clean)
    if title and not str(getattr(session, "title", "") or "").strip():
        session.title = title
    try:
        session.branches["main"] = clean
    except Exception:
        pass


def _safe_doc_ir_payload(text: str) -> dict:
    return doc_state_domain.safe_doc_ir_payload(
        text,
        doc_ir_to_dict=doc_ir_to_dict,
        doc_ir_from_text=doc_ir_from_text,
    )


def _safe_doc_text(session) -> str:
    text = str(getattr(session, "doc_text", "") or "")
    if text.strip():
        return text
    raw_ir = getattr(session, "doc_ir", None)
    if raw_ir:
        try:
            text = doc_ir_to_text(doc_ir_from_dict(raw_ir))
        except Exception:
            text = ""
    if text.strip():
        session.doc_text = text
        return text
    session.doc_text = ""
    session.doc_ir = {}
    return ""


def _coerce_bool_pref(session, key: str, *, env_key: str = "", default: bool = False) -> bool:
    prefs = getattr(session, "generation_prefs", None)
    prefs = prefs if isinstance(prefs, dict) else {}
    parsed = export_quality_domain.coerce_optional_bool(prefs.get(key))
    if parsed is not None:
        return bool(parsed)
    if env_key:
        parsed = export_quality_domain.coerce_optional_bool(os.environ.get(env_key, ""))
        if parsed is not None:
            return bool(parsed)
    return bool(default)


def _strict_doc_format_enabled(session) -> bool:
    return _coerce_bool_pref(
        session,
        "strict_doc_format",
        env_key="WRITING_AGENT_STRICT_DOC_FORMAT_DEFAULT",
        default=False,
    )


def _strict_citation_verify_enabled(session) -> bool:
    return _coerce_bool_pref(
        session,
        "strict_citation_verify",
        env_key="WRITING_AGENT_STRICT_CITATION_VERIFY_DEFAULT",
        default=False,
    )


def _allow_possible_citation_status(session) -> bool:
    return _coerce_bool_pref(
        session,
        "allow_possible_citation_status",
        env_key="WRITING_AGENT_CITATION_VERIFY_ALLOW_POSSIBLE",
        default=False,
    )


def _clean_export_text(text: str) -> str:
    return export_quality_domain.clean_export_text(str(text or ""))


def _heading_num_prefix(title: str) -> tuple[str, str]:
    src = str(title or "").strip()
    match = re.match(r"^((?:\d+(?:\.\d+)*|[一二三四五六七八九十]+)[\.\uFF0E\u3001\)]?)\s*(.+)$", src)
    if not match:
        return "", src
    return str(match.group(1) or "").strip(), str(match.group(2) or "").strip()


def _equivalent_heading_key(title: str) -> str:
    return heading_equivalence_domain.equivalent_heading_key(
        title,
        normalize_heading_text=_normalize_heading_text,
        aliases=_HEADING_EQUIV_ALIASES,
    )


def _dedupe_toc_entries(text: str, prefer_chinese: bool) -> str:
    return heading_equivalence_domain.dedupe_toc_entries(
        text,
        prefer_chinese=bool(prefer_chinese),
        split_lines=section_edit_ops_domain.split_lines,
        extract_sections=lambda value: _extract_sections(value, prefer_levels=(1, 2, 3)),
        equivalent_heading_key=_equivalent_heading_key,
    )


def _dedupe_equivalent_headings(text: str) -> str:
    return heading_equivalence_domain.dedupe_equivalent_headings(
        text,
        split_lines=section_edit_ops_domain.split_lines,
        heading_num_prefix=_heading_num_prefix,
        equivalent_heading_key=_equivalent_heading_key,
        prefer_heading_language_is_chinese=heading_equivalence_domain.preferred_heading_language_is_chinese,
        choose_preferred_heading_title=lambda candidates, prefer: heading_equivalence_domain.choose_preferred_heading_title(
            candidates,
            prefer_chinese=prefer,
        ),
        dedupe_toc_entries=_dedupe_toc_entries,
    )


def _fix_section_heading_glue(text: str, titles: list[str]) -> str:
    return heading_glue_domain.fix_section_heading_glue(
        text,
        titles,
        split_heading_glue=_doc_format_split_heading_glue,
    )


def _normalize_export_text(text: str, *, session=None) -> str:
    cleaned = _clean_export_text(text)
    if not _strict_doc_format_enabled(session):
        return cleaned
    fixed = _dedupe_equivalent_headings(cleaned)
    titles: list[str] = []
    raw_outline = getattr(session, "template_outline", None) if session is not None else None
    if isinstance(raw_outline, list):
        for item in raw_outline:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                title = str(item[1] or "").strip()
            else:
                title = str(item or "").strip()
            if title:
                titles.append(title)
    if titles:
        fixed = _fix_section_heading_glue(fixed, titles)
    return fixed


def _citation_style_from_session(session) -> CitationStyle:
    formatting = getattr(session, "formatting", None)
    prefs = getattr(session, "generation_prefs", None)
    sources = []
    if isinstance(formatting, dict):
        sources.append(formatting.get("citation_style"))
    if isinstance(prefs, dict):
        sources.append(prefs.get("citation_style"))
    for raw in sources:
        value = str(raw or "").strip()
        if not value:
            continue
        try:
            return CitationStyle(value)
        except Exception:
            low = value.lower()
            if "apa" in low:
                return CitationStyle.APA
            if "ieee" in low:
                return CitationStyle.IEEE
            if "gb" in low or "7714" in low:
                return CitationStyle.GBT
    return CitationStyle.GBT


def _reference_lines_from_session(session) -> list[str]:
    from writing_agent.agents.citations import CitationAgent

    agent = CitationAgent()
    return export_structure_domain.reference_lines_from_session(
        session,
        citation_style_from_session=_citation_style_from_session,
        format_reference=agent.format_reference,
    )


def _ensure_toc_section(text: str) -> str:
    return export_structure_domain.ensure_toc_section(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
        split_lines=section_edit_ops_domain.split_lines,
    )


def _ensure_reference_section(text: str, session) -> str:
    return export_structure_domain.ensure_reference_section(
        text,
        session,
        has_reference_heading_fn=export_structure_domain.has_reference_heading,
        reference_lines_from_session_fn=_reference_lines_from_session,
        insert_reference_section=citation_render_domain.insert_reference_section,
    )


def _reference_section_last(text: str) -> bool:
    return export_structure_domain.reference_section_last(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
    )


def _move_reference_section_to_end(text: str) -> str:
    return export_structure_domain.move_reference_section_to_end(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
        apply_move_section_op=lambda source, title, anchor, **kwargs: section_edit_ops_domain.apply_move_section_op(
            source,
            title,
            anchor,
            normalize_heading_text=_normalize_heading_text,
            **kwargs,
        ),
    )


def _has_reference_requirement(session, text: str) -> bool:
    return export_structure_domain.has_reference_requirement(
        session,
        text,
        has_reference_heading_fn=export_structure_domain.has_reference_heading,
        reference_lines_from_session_fn=_reference_lines_from_session,
    )


def _citation_export_issues(session, text: str) -> list[dict]:
    return export_structure_domain.citation_export_issues(
        session,
        text,
        strict_citation_verify_enabled=_strict_citation_verify_enabled,
        get_internal_pref=_get_internal_pref,
        citation_verify_key=_CITATION_VERIFY_KEY,
        allow_possible_citation_status=_allow_possible_citation_status,
    )


def _export_quality_report(session, text: str, *, auto_fix: bool) -> dict:
    return export_structure_domain.export_quality_report(
        session,
        text,
        auto_fix=bool(auto_fix),
        export_gate_policy=_export_gate_policy,
        strict_doc_format_enabled=_strict_doc_format_enabled,
        has_reference_requirement_fn=_has_reference_requirement,
        normalize_export_text=_normalize_export_text,
        ensure_toc_section_fn=_ensure_toc_section,
        ensure_reference_section_fn=_ensure_reference_section,
        move_reference_section_to_end_fn=_move_reference_section_to_end,
        has_toc_heading_fn=export_structure_domain.has_toc_heading,
        has_reference_heading_fn=export_structure_domain.has_reference_heading,
        reference_section_last_fn=_reference_section_last,
        citation_export_issues_fn=_citation_export_issues,
    )


def _raise_export_blocking_error(quality: dict) -> None:
    if bool((quality or {}).get("can_export", True)):
        return
    issues = [x for x in (quality or {}).get("issues", []) if isinstance(x, dict)]
    blocking = [x for x in issues if bool(x.get("blocking", True))]
    rows = blocking or issues
    messages = [str(x.get("message") or x.get("code") or "export issue") for x in rows[:5]]
    detail = "导出前校验未通过"
    if messages:
        detail += "：" + "；".join(messages)
    raise HTTPException(status_code=400, detail=detail)


def _persist_export_autofix_enabled() -> bool:
    return export_settings_domain.persist_export_autofix_enabled()


def _resolve_export_template_path(session) -> str:
    return export_settings_domain.resolve_export_template_path(
        session,
        repo_root=REPO_ROOT,
        template_dir=TEMPLATE_DIR,
        auto_export_template_enabled_fn=export_settings_domain.auto_export_template_enabled,
    )


def _formatting_from_session(session) -> FormattingRequirements:
    return export_settings_domain.formatting_from_session(
        session,
        formatting_cls=FormattingRequirements,
    )


def _export_prefs_from_session(session) -> ExportPrefs:
    return export_settings_domain.export_prefs_from_session(
        session,
        export_prefs_cls=ExportPrefs,
    )


def _doc_ir_has_styles(doc_ir) -> bool:
    return doc_state_domain.doc_ir_has_styles(doc_ir, doc_ir_to_dict=doc_ir_to_dict)


def _normalize_doc_ir_for_export(doc_ir, session):
    return doc_state_domain.normalize_doc_ir_for_export(
        doc_ir,
        session,
        ensure_mcp_citations=_ensure_mcp_citations,
        doc_ir_from_dict=doc_ir_from_dict,
        doc_ir_to_text=doc_ir_to_text,
        doc_ir_from_text=doc_ir_from_text,
        doc_ir_has_styles=_doc_ir_has_styles,
        normalize_export_text=_normalize_export_text,
    )


def _apply_citations_to_doc_ir(doc_ir, citations: dict, style: CitationStyle):
    return citation_render_domain.apply_citations_to_doc_ir(doc_ir, citations, style)


def _validate_docx_bytes(docx_bytes: bytes) -> list[str]:
    return doc_state_domain.validate_docx_bytes(docx_bytes)


def _convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> None:
    import shutil

    src = Path(docx_path)
    dst = Path(pdf_path)
    exe = None
    for name in ("soffice", "soffice.exe", "libreoffice", "libreoffice.exe"):
        exe = shutil.which(name)
        if exe:
            break
    if not exe:
        raise RuntimeError("LibreOffice/soffice not available for PDF export")
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [exe, "--headless", "--convert-to", "pdf", "--outdir", str(dst.parent), str(src)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        check=False,
    )
    produced = src.with_suffix(".pdf")
    if result.returncode != 0 or not produced.exists():
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"PDF conversion failed: {err or result.returncode}")
    if produced.resolve() != dst.resolve():
        produced.replace(dst)


_MCP_CITATION_CACHE: dict[str, object] = {}


def _mcp_citation_sync_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_MCP_CITATIONS", "")).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(os.environ.get("WRITING_AGENT_MCP_REF_URI") or os.environ.get("WRITING_AGENT_MCP_REF_CMD"))


def _load_mcp_citations_cached() -> dict:
    if not _mcp_citation_sync_enabled():
        return {}
    try:
        from writing_agent.capabilities.mcp_retrieval import load_mcp_citations_cached
        from writing_agent.mcp_client import fetch_mcp_resource

        return load_mcp_citations_cached(
            cache=_MCP_CITATION_CACHE,
            os_module=os,
            time_module=time,
            json_module=json,
            fetch_mcp_resource_fn=fetch_mcp_resource,
            citation_cls=Citation,
        )
    except Exception as exc:
        logger.debug("Ignored MCP citation sync error: %s", exc, exc_info=True)
        return {}


def _ensure_mcp_citations(session) -> None:
    try:
        from writing_agent.capabilities.mcp_retrieval import ensure_mcp_citations

        ensure_mcp_citations(
            session=session,
            load_mcp_citations_cached_fn=_load_mcp_citations_cached,
            doc_ir_from_dict_fn=doc_ir_from_dict,
            doc_ir_from_text_fn=doc_ir_from_text,
            citation_style_from_session_fn=_citation_style_from_session,
            apply_citations_to_doc_ir_fn=_apply_citations_to_doc_ir,
            doc_ir_to_dict_fn=doc_ir_to_dict,
            doc_ir_to_text_fn=doc_ir_to_text,
        )
    except Exception as exc:
        logger.debug("Ignored MCP citation ensure error: %s", exc, exc_info=True)


def _extract_required_sections_from_instruction(instruction: str) -> list[str]:
    src = str(instruction or "")
    patterns = [
        r"必须包含以下(?:一级|二级)?章节[:：]\s*([^。\n]+)",
        r"必须包含(?:以下)?(?:一级|二级)?章节[:：]\s*([^。\n]+)",
        r"required sections?[:：]\s*([^\n]+)",
    ]
    raw = ""
    for pattern in patterns:
        match = re.search(pattern, src, flags=re.IGNORECASE)
        if match:
            raw = str(match.group(1) or "").strip()
            break
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in re.split(r"[、,，;；]+", raw):
        title = str(item or "").strip().strip(" .。:：\"'“”‘’")
        if not title:
            continue
        key = _normalize_heading_text(title)
        if key and key not in seen:
            seen.add(key)
            out.append(title)
    return out


def _append_new_h2_section(text: str, title: str, lines: list[str]) -> str:
    out = str(text or "").rstrip()
    block = [f"## {str(title or '').strip()}"]
    block.extend([str(line or "") for line in (lines or [])])
    if out:
        return out + "\n\n" + "\n".join(block).strip()
    return "\n".join(block).strip()


def _find_section_for_requirements(sections: list[object], title: str):
    found = section_edit_ops_domain.find_section(
        sections,
        title,
        normalize_heading_text=_normalize_heading_text,
    )
    if found is not None:
        return found
    target = _normalize_heading_text(title)
    for sec in sections or []:
        sec_title = str(getattr(sec, "title", "") or "")
        norm = _normalize_heading_text(sec_title)
        if target and norm and (target in norm or norm in target):
            return sec
    return None


def _insert_lines_into_section(text: str, title: str, lines: list[str]) -> str:
    src = str(text or "").strip()
    clean_lines = [str(line or "") for line in (lines or [])]
    if not clean_lines:
        return src
    sections = section_edit_ops_domain.extract_sections(src, prefer_levels=(2, 3))
    sec = _find_section_for_requirements(sections, title)
    if sec is None:
        return _append_new_h2_section(src, title, clean_lines)
    rows = section_edit_ops_domain.split_lines(src)
    insert_at = int(getattr(sec, "end", len(rows)) or len(rows))
    block = list(clean_lines)
    if insert_at > 0 and rows[insert_at - 1].strip() and block and block[0].strip():
        block = [""] + block
    if insert_at < len(rows) and rows[insert_at].strip() and block and block[-1].strip():
        block = block + [""]
    rows[insert_at:insert_at] = block
    return "\n".join(rows).strip()


def _enforce_instruction_requirements(text: str, instruction: str) -> str:
    return instruction_requirements_domain.enforce_instruction_requirements(
        text,
        instruction,
        extract_required_sections_from_instruction=_extract_required_sections_from_instruction,
        extract_sections=section_edit_ops_domain.extract_sections,
        normalize_heading_text=_normalize_heading_text,
        append_new_h2_section=_append_new_h2_section,
        find_section=_find_section_for_requirements,
        split_lines=section_edit_ops_domain.split_lines,
        insert_lines_into_section=_insert_lines_into_section,
    )


def _build_fallback_prompt(session, *, instruction: str, length_hint: str) -> tuple[str, str]:
    from writing_agent.capabilities.fallback_generation import build_fallback_prompt

    return build_fallback_prompt(session, instruction=instruction, length_hint=length_hint)


def _try_rust_import(path: Path) -> str:
    """Use the optional compiled Rust importer without building it at runtime."""
    try:
        from writing_agent.v2.rust_bridge import try_rust_import

        return str(try_rust_import(Path(path)) or "")
    except Exception:
        return ""


def _extract_text(path: Path) -> str:
    try:
        from writing_agent.v2.rag.user_library import _extract_text as _library_extract_text

        return str(_library_extract_text(Path(path)) or "")
    except Exception:
        p = Path(path)
        if not p.exists():
            return ""
        if p.suffix.lower() in {".txt", ".md", ".csv", ".json"}:
            return p.read_text(encoding="utf-8", errors="replace")
        if p.suffix.lower() in {".html", ".htm"}:
            html = p.read_text(encoding="utf-8", errors="replace")
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""


def _normalize_string_list(value: object, keys: tuple[str, ...] = ("text", "title", "name")) -> list[str]:
    raw_items = value if isinstance(value, list) else []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if isinstance(item, dict):
            text = ""
            for key in keys:
                text = str(item.get(key) or "").strip()
                if text:
                    break
        else:
            text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text[:160])
    return out


def _heuristic_template_info(filename: str, text: str) -> dict:
    src = str(text or "")
    name = Path(str(filename or "template")).stem or "template"
    outline: list[tuple[int, str]] = []
    for line in src.replace("\r", "").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        md = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)
        if md:
            outline.append((min(6, len(md.group(1))), md.group(2).strip()))
            continue
        numbered = re.match(r"^(?:\d+(?:\.\d+)*|[一二三四五六七八九十]+[、.．])\s*(.{2,80})$", stripped)
        if numbered and len(stripped) <= 90:
            level = 2 if "." in stripped else 1
            outline.append((level, numbered.group(1).strip()))
    if not outline:
        for line in [ln.strip() for ln in src.splitlines() if ln.strip()][:12]:
            if len(line) <= 80:
                outline.append((1 if not outline else 2, re.sub(r"^#+\s*", "", line).strip()))
            if len(outline) >= 6:
                break
    if outline:
        first_title = str(outline[0][1] or "").strip()
        if first_title and first_title != name:
            name = first_title[:80]
    required_h2 = [title for level, title in outline if int(level) == 2]
    if not required_h2 and len(outline) >= 2:
        required_h2 = [title for _level, title in outline[1:]]
    return {
        "name": name,
        "outline": outline,
        "required_h2": required_h2,
        "questions": [],
    }


def _extract_template_with_model(*, base_url: str, model: str, filename: str, text: str) -> dict:
    _ = base_url, model
    return _heuristic_template_info(filename, text)


def _extract_template_refine_with_model(
    *,
    base_url: str,
    model: str,
    filename: str,
    text: str,
    initial: dict | None = None,
) -> dict:
    _ = base_url, model, filename, text, initial
    return {}


def _extract_template_titles_with_model(*, base_url: str, model: str, filename: str, text: str) -> dict:
    _ = base_url, model
    info = _heuristic_template_info(filename, text)
    return {
        "titles": [title for _level, title in (info.get("outline") or [])],
        "questions": list(info.get("questions") or []),
    }


def _classify_upload_with_model(*, base_url: str, model: str, filename: str, text: str) -> dict:
    _ = base_url, model
    suffix = Path(str(filename or "")).suffix.lower()
    info = _heuristic_template_info(filename, text)
    if suffix in {".doc", ".docx", ".md", ".txt", ".html", ".htm"} and len(info.get("outline") or []) >= 3:
        return {"kind": "template"}
    if re.search(r"(?mi)^\s*(?:\[\d+\]|\d+\.)\s+.+", str(text or "")):
        return {"kind": "reference"}
    return {"kind": "library"}


def _extract_timeout_s() -> float:
    try:
        return max(1.0, float(os.environ.get("WRITING_AGENT_EXTRACT_TIMEOUT_S", "20")))
    except Exception:
        return 20.0


def _analysis_timeout_s() -> float:
    try:
        return max(1.0, float(os.environ.get("WRITING_AGENT_ANALYSIS_MAX_S", "20")))
    except Exception:
        return 20.0


def _analysis_model_name(settings) -> str:
    return str(os.environ.get("WRITING_AGENT_ANALYSIS_MODEL", "") or getattr(settings, "model", "") or "").strip()


def _analysis_history_context(session) -> str:
    prefs = getattr(session, "generation_prefs", None)
    if isinstance(prefs, dict):
        summary = str(prefs.get("_wa_last_analysis_summary") or "").strip()
        if summary:
            return summary[:1200]
    return ""


def _run_message_analysis(session, text: str, *, force: bool = False, quick: bool = False) -> dict:
    _ = session, force, quick
    raw = str(text or "").strip()
    if not raw:
        return prefs_analysis_domain.normalize_analysis({}, raw)
    intent = "modify" if _looks_like_modify_instruction_base(raw) else "generate"
    constraints: list[str] = []
    for marker in ("不要", "必须", "需要", "要求", "strict", "must"):
        if marker in raw:
            constraints.append(raw[:160])
            break
    data = {
        "intent": {"name": intent, "confidence": 0.65 if intent == "modify" else 0.55, "reason": "heuristic"},
        "rewritten_query": raw,
        "constraints": constraints,
        "missing": [],
        "entities": {},
    }
    return prefs_analysis_domain.normalize_analysis(data, raw)


def _compose_analysis_input(text: str, analysis: dict) -> str:
    if not isinstance(analysis, dict) or not analysis:
        return str(text or "")
    return (
        f"{str(text or '').strip()}\n\n"
        "<analysis_payload>\n"
        f"{json.dumps(analysis, ensure_ascii=False)}\n"
        "</analysis_payload>"
    ).strip()


def _extract_prefs_with_model(*, base_url: str, model: str, text: str, timeout_s: float | None = None) -> dict:
    _ = base_url, model, timeout_s
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("text required")
    parsed = prefs_extract_domain.fast_extract_prefs(raw)
    out = dict(parsed if isinstance(parsed, dict) else {})
    title = str(out.get("title") or "").strip()
    if not title:
        title_patterns = [
            r"(?:题目|标题|主题)\s*[:：]\s*([^\n，,。；;]{2,80})",
            r"(?:围绕|关于)\s*[“\"]?([^”\"\n，,。；;]{4,80})[”\"]?",
        ]
        for pattern in title_patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if match:
                title = str(match.group(1) or "").strip()
                break
    if not title:
        title = _extract_title(raw)
    if title:
        out["title"] = title
    prefs = dict(out.get("generation_prefs") if isinstance(out.get("generation_prefs"), dict) else {})
    length = prefs_analysis_domain.length_from_text(raw)
    if length:
        mode, value = length
        prefs["target_length_mode"] = mode
        prefs["target_length_value"] = value
        if mode == "chars":
            prefs["target_char_count"] = value
        elif mode == "pages":
            prefs["target_page_count"] = value
        prefs["target_length_confirmed"] = True
    if prefs:
        out["generation_prefs"] = prefs
    out.setdefault("summary", prefs_analysis_domain.build_pref_summary(raw, {}, title, {}, prefs))
    return out


def _extract_prefs_refine_with_model(
    *,
    base_url: str,
    model: str,
    text: str,
    initial: dict | None = None,
    timeout_s: float | None = None,
) -> dict:
    _ = base_url, model, text, initial, timeout_s
    return {}


_fast_extract_prefs = prefs_extract_domain.fast_extract_prefs
_normalize_ai_formatting = prefs_extract_domain.normalize_ai_formatting
_normalize_ai_prefs = prefs_extract_domain.normalize_ai_prefs
_replace_question_headings = prefs_extract_domain.replace_question_headings
_infer_role_defaults = prefs_analysis_domain.infer_role_defaults
_build_pref_summary = prefs_analysis_domain.build_pref_summary
_build_missing_questions = prefs_analysis_domain.build_missing_questions
_detect_extract_conflicts = prefs_analysis_domain.detect_extract_conflicts
_detect_multi_intent = prefs_analysis_domain.detect_multi_intent
_field_confidence = prefs_analysis_domain.field_confidence
_low_conf_questions = prefs_analysis_domain.low_conf_questions
_info_score = prefs_analysis_domain.info_score
_normalize_analysis = prefs_analysis_domain.normalize_analysis
_resolve_target_chars = length_target_domain.resolve_target_chars
_extract_target_chars_from_instruction = length_target_domain.extract_target_chars_from_instruction

from writing_agent.v2.template_parse import parse_template_file, prepare_template_file

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

# Upload helpers are now in writing_agent.web.upload_utils.
# The private aliases (_normalize_upload_filename, _read_upload_payload, etc.)
# are imported at the top of this file for backward-compat with callers that
# do `app_v2._read_upload_payload(...)` until those call sites are migrated.

# Meta DB helpers are now in writing_agent.web.meta_db.
# Backward-compat shims so existing callers (feedback_service, document_service)
# can continue using app_v2._load_meta / app_v2._save_meta until migrated.
_ensure_meta_db = _meta_db.ensure_meta_db
_load_meta = _meta_db.load_meta
_save_meta = _meta_db.save_meta

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

_append_low_satisfaction_event = _meta_db.append_low_satisfaction_event
_load_low_satisfaction_events = _meta_db.load_low_satisfaction_events

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

def _initialize_new_session(session) -> None:
    _set_doc_text(session, "")
    session.archived = False
    session.status = "draft"
    session.formatting = {
        "font_name": "SimSun",
        "font_name_east_asia": "SimSun",
        "font_size_name": "Small Four",
        "font_size_pt": 12,
        "line_spacing": 28,
        "heading1_font_name": "SimHei",
        "heading1_font_name_east_asia": "SimHei",
        "heading1_size_pt": 22,
        "heading2_font_name": "SimHei",
        "heading2_font_name_east_asia": "SimHei",
        "heading2_size_pt": 16,
        "heading3_font_name": "SimHei",
        "heading3_font_name_east_asia": "SimHei",
        "heading3_size_pt": 16,
    }
    session.generation_prefs = {
        "purpose": "graduation report / coursework report",
        "quality_profile": "academic_cnki_default",
        "figure_types": ["flow", "architecture", "er", "sequence", "bar", "line", "pie", "timeline"],
        "table_types": ["summary", "metrics", "compare"],
        "min_reference_count": 8,
        "min_h2_count": 3,
        "min_h3_count": 1,
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


def _create_new_session() -> RedirectResponse:
    session = store.create()
    _initialize_new_session(session)
    store.put(session)
    return RedirectResponse(url=f"/workbench/{session.id}", status_code=303)

@app.get("/", response_class=HTMLResponse)
def root(
    request: Request,
    status: str = "all",
    q: str = "",
    label: str = "",
    owner: str = "",
    priority: str = "",
    due_soon: str = "",
    unassigned: str = "",
    no_due_date: str = "",
    no_priority: str = "",
    overdue: str = "",
    sort: str = "updated",
) -> HTMLResponse:
    from writing_agent.web.services.system_service import SystemService
    from writing_agent.web.services.workspace_service import WorkspaceService
    from writing_agent.web.services.workspace_view_service import WorkspaceViewService

    workspace_service = WorkspaceService()
    overview = workspace_service.list_workspaces(
        status=status or "all",
        limit=200,
        query=q,
        label=label,
        owner=owner,
        priority=priority,
        due_soon=due_soon,
        unassigned=unassigned,
        no_due_date=no_due_date,
        no_priority=no_priority,
        overdue=overdue,
        sort=sort,
    )
    # Pagination
    page = max(1, int(request.query_params.get("page", 1)))
    per_page = 10
    all_items = overview.get("items", [])
    total_items = len(all_items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_items = all_items[start:end]
    activity = workspace_service.recent_activity(limit=12)
    summary = workspace_service.dashboard_summary()
    status_payload = SystemService().system_status()
    saved_views = WorkspaceViewService().list_views(
        status=status or "all",
        query=q,
        label=label,
        owner=owner,
        priority=priority,
        due_soon=due_soon,
        unassigned=unassigned,
        no_due_date=no_due_date,
        no_priority=no_priority,
        overdue=overdue,
        sort=sort,
    )
    resp = templates.TemplateResponse(
        request,
        "v2_home.html",
        {
            "static_version": STATIC_VERSION,
            "perf_mode": PERF_MODE,
            "workspaces": paginated_items,
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1,
            "next_page": page + 1,
            "workspace_total": summary.get("total", overview.get("total", 0)),
            "workspace_active": status_payload.get("workspaces", {}).get("active", 0),
            "workspace_archived": status_payload.get("workspaces", {}).get("archived", 0),
            "workspace_status_filter": overview.get("status", "all"),
            "workspace_query": overview.get("query", ""),
            "workspace_label_filter": overview.get("label", ""),
            "workspace_owner_filter": overview.get("owner", ""),
            "workspace_priority_filter": overview.get("priority", ""),
            "workspace_due_soon_filter": bool(overview.get("due_soon", False)),
            "workspace_unassigned_filter": bool(overview.get("unassigned", False)),
            "workspace_no_due_date_filter": bool(overview.get("no_due_date", False)),
            "workspace_no_priority_filter": bool(overview.get("no_priority", False)),
            "workspace_overdue_filter": bool(overview.get("overdue", False)),
            "workspace_sort_mode": overview.get("sort", "updated"),
            "saved_views": saved_views,
            "template_starters": workspace_service.built_in_templates(),
            "workspace_activity": activity.get("items", []),
            "workspace_summary": summary,
            "system_status": status_payload,
        },
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/new")
def new_workspace() -> RedirectResponse:
    return _create_new_session()


@app.get("/latest")
def latest_workspace() -> RedirectResponse:
    from writing_agent.web.services.workspace_service import WorkspaceService

    doc_id = WorkspaceService().latest_workspace_id()
    if doc_id:
        return RedirectResponse(url=f"/workbench/{doc_id}", status_code=303)
    return _create_new_session()
@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)
@app.get("/workbench/{doc_id}", response_class=HTMLResponse)
def workbench_page(request: Request, doc_id: str) -> HTMLResponse:
    session = store.get(doc_id)
    if session is None:
        resp = templates.TemplateResponse(
            request,
            "v2_error2.html",
            {
                "message": "document not found or expired",
                "static_version": STATIC_VERSION,
                "perf_mode": PERF_MODE,
            },
        )
        resp.headers["Cache-Control"] = "no-store"
        return resp
    store.touch(doc_id)
    svelte_entry = os.path.join(os.path.dirname(__file__), "static", "v2_svelte", "main.js")
    use_svelte_raw = os.environ.get("WRITING_AGENT_USE_SVELTE", "1").strip().lower()
    use_svelte = use_svelte_raw not in {"0", "false", "no", "off"}
    template_name = "v2_workbench_svelte.html" if use_svelte and os.path.exists(svelte_entry) else "v2_workbench2.html"
    resp = templates.TemplateResponse(
        request,
        template_name,
        {
            "doc_id": doc_id,
            "static_version": STATIC_VERSION,
            "perf_mode": PERF_MODE,
        },
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp
from writing_agent.web.legacy_fragments import forwarders as _forwarders_runtime

_forwarders_runtime.install(globals())

from writing_agent.web.legacy_fragments import (
    citation_part1 as _citation_runtime_part1,
    citation_part2 as _citation_runtime_part2,
)

_citation_runtime_part1.install(globals())
_citation_runtime_part2.install(globals())

def api_doc_delete(doc_id: str) -> dict:
    from writing_agent.web.api.document_flow import doc_delete

    return doc_delete(doc_id)
from writing_agent.web.legacy_fragments import export_intent as _export_intent_runtime

_export_intent_runtime.install(globals())

_ANALYSIS_INFLIGHT: dict[str, float] = {}
_ANALYSIS_LOCK = threading.Lock()

from writing_agent.web.legacy_fragments import (
    textops_part1 as _textops_runtime_part1,
    textops_part2 as _textops_runtime_part2,
    textops_part3 as _textops_runtime_part3,
)

_textops_runtime_part1.install(globals())
_textops_runtime_part2.install(globals())
_textops_runtime_part3.install(globals())

_HEADING_EQUIV_ALIASES: dict[str, set[str]] = heading_equivalence_domain.HEADING_EQUIV_ALIASES

_FAST_REPORT_SECTIONS = ["Background", "This Week", "Next Week", "Risks", "Support Needed"]

# === ??? API ===

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
    from writing_agent.web.api.system_flow import router as system_router
    from writing_agent.web.api.template_flow import router as template_router
    from writing_agent.web.api.version_flow import router as version_router
    from writing_agent.web.api.workspace_flow import router as workspace_router
    from writing_agent.web.api.workspace_view_flow import router as workspace_view_router
    from writing_agent.web.api.llm_config_flow import router as llm_config_router

    app.include_router(document_router)
    app.include_router(generation_router)
    app.include_router(job_router)
    app.include_router(integration_router)
    app.include_router(system_router)
    app.include_router(template_router)
    app.include_router(editing_router)
    app.include_router(export_router)
    app.include_router(feedback_router)
    app.include_router(quality_router)
    app.include_router(citation_router)
    app.include_router(rag_router)
    app.include_router(workspace_router)
    app.include_router(workspace_view_router)
    app.include_router(version_router)
    app.include_router(llm_config_router)
    _FLOW_ROUTERS_REGISTERED = True

_register_flow_routers()
