#!/usr/bin/env python3
"""
Unified frontend (Playwright) content validation runner.

It executes:
- 70 single-round content cases
- 24 multi-round scenarios (round-by-round input + acceptance checks)

All generation is triggered through the web UI, not direct generation API calls.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
from scripts import ui_content_validation_export as export_domain
from scripts import ui_content_validation_multiround_adapter as multiround_adapter
from scripts import ui_content_validation_runmeta as runmeta_domain
from scripts import ui_content_validation_text_eval as text_eval_domain
from scripts.ui_content_validation_constants import (
    FORMAT_SENSITIVE_HINTS,
    STATUS_BUSY_HINTS,
    STATUS_FAILURE_HINTS,
    STATUS_RUNNING_HINTS,
    TERM_ALIASES,
)


DEFAULT_BASE_URL = os.environ.get("WA_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_DATASET = "tests/fixtures/content_validation/content_cases_70.json"
DEFAULT_MULTISET = "tests/fixtures/content_validation/multiround_cases_24.json"
DEFAULT_OUT_ROOT = Path(".data") / "out"

APP_SELECTOR = ".app"
EDITOR_SELECTOR = ".editable"
TEXTAREA_SELECTOR = ".assistant-dock .composer textarea"
SEND_SELECTOR = ".assistant-dock .send-btn"
THOUGHT_ITEM_SELECTOR = ".assistant-dock .thought-item"


@dataclass
class RunnerConfig:
    base_url: str
    start_server: bool
    disable_ollama: bool
    headless: bool
    timeout_s: int
    poll_interval_s: float
    group_smoke: bool
    run_all: bool
    max_single: int
    max_multi: int
    single_start: int
    single_end: int
    multi_start: int
    multi_end: int
    export_docx_all: bool
    export_docx_for_format: bool
    checkpoint: Optional[Path]
    resume: bool
    out_root: Path


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


_normalize_for_match = text_eval_domain.normalize_for_match
_squash_for_match = text_eval_domain.squash_for_match


def _status_contains_any(text: str, hints: Iterable[str]) -> bool:
    src = _normalize_for_match(text)
    for hint in hints:
        h = _normalize_for_match(str(hint or ""))
        if h and h in src:
            return True
    return False


def _status_indicates_failure(status_text: str) -> bool:
    return _status_contains_any(status_text, STATUS_FAILURE_HINTS)


def _status_indicates_busy(status_text: str) -> bool:
    return _status_contains_any(status_text, STATUS_BUSY_HINTS)


def _looks_like_connection_error(exc: Exception) -> bool:
    msg = _normalize_for_match(str(exc or ""))
    return (
        "err_connection_refused" in msg
        or "connection refused" in msg
        or "net::err" in msg
        or "failed to fetch" in msg
    )


def _status_indicates_transport_issue(status_text: str) -> bool:
    msg = _normalize_for_match(status_text)
    return (
        "failed to fetch" in msg
        or "networkerror" in msg
        or "network error" in msg
        or "connection refused" in msg
        or "err_connection_refused" in msg
    )


def pick_first_per_group(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for case in cases:
        group = str(case.get("group", "")).strip()
        if not group:
            group = "__ungrouped__"
        if group in seen:
            continue
        seen.add(group)
        out.append(case)
    return out


def filter_by_index(cases: List[Dict[str, Any]], start: int, end: int) -> List[Dict[str, Any]]:
    if start <= 1 and end >= len(cases):
        return list(cases)
    out: List[Dict[str, Any]] = []
    for idx, case in enumerate(cases, start=1):
        if idx < start or idx > end:
            continue
        out.append(case)
    return out


def normalize_base_url(raw: str) -> str:
    u = raw.rstrip("/")
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "http://" + u
    return u


def _http_get_json(url: str, timeout_s: float = 20.0) -> Dict[str, Any]:
    req = urllib.request.Request(url=url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def url_ready(base_url: str, timeout_s: float = 2.0) -> bool:
    test_url = base_url.rstrip("/") + "/favicon.ico"
    try:
        with urllib.request.urlopen(test_url, timeout=timeout_s) as resp:
            return 200 <= resp.status < 500
    except Exception:
        return False


def wait_url_ready(base_url: str, timeout_s: float = 45.0) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        if url_ready(base_url, timeout_s=2.0):
            return True
        time.sleep(0.3)
    return False


def start_local_server(base_url: str, disable_ollama: bool) -> subprocess.Popen[bytes]:
    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8000

    env = os.environ.copy()
    env["WRITING_AGENT_USE_SVELTE"] = "1"
    env["WRITING_AGENT_HOST"] = host
    env["WRITING_AGENT_PORT"] = str(port)
    if disable_ollama:
        env["WRITING_AGENT_USE_OLLAMA"] = "0"
    repo_root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(repo_root)

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "writing_agent.web.app_v2:app",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_url_ready(base_url, timeout_s=60):
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise RuntimeError(f"server failed to start at {base_url}")
    return proc


def ensure_server_available(
    base_url: str,
    cfg: RunnerConfig,
    server_proc: Optional[subprocess.Popen[bytes]],
) -> Optional[subprocess.Popen[bytes]]:
    if url_ready(base_url, timeout_s=2.0):
        return server_proc
    if not cfg.start_server:
        return server_proc
    if server_proc is not None:
        try:
            if server_proc.poll() is None:
                server_proc.terminate()
                server_proc.wait(timeout=5)
        except Exception:
            try:
                server_proc.kill()
            except Exception:
                pass
        server_proc = None
    return start_local_server(base_url, cfg.disable_ollama)


def ensure_assistant_open(page: Page) -> None:
    if page.locator(TEXTAREA_SELECTOR).count() > 0:
        return
    toggle = page.locator(".assistant-dock .assistant-toggle")
    if toggle.count() > 0:
        toggle.first.click()
        page.wait_for_selector(TEXTAREA_SELECTOR, timeout=5000)


def open_new_case_page(page: Page, base_url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector(APP_SELECTOR, timeout=60000)
            page.wait_for_selector(EDITOR_SELECTOR, timeout=60000)
            ensure_assistant_open(page)
            page.wait_for_selector(TEXTAREA_SELECTOR, timeout=60000)
            page.wait_for_function("window.__waGetStore && window.__waGetStore('docId')", timeout=60000)
            doc_id = page.evaluate("window.__waGetStore('docId')")
            return str(doc_id or "")
        except PlaywrightTimeoutError as exc:
            last_error = exc
            if attempt == 0:
                page.wait_for_timeout(1500)
                continue
            raise
    if last_error:
        raise last_error
    return ""


def get_ui_state(page: Page) -> Dict[str, Any]:
    state = page.evaluate(
        """
        () => {
          const pick = (name, fallback='') => {
            try {
              if (window.__waGetStore) {
                const v = window.__waGetStore(name);
                return v == null ? fallback : v;
              }
            } catch {}
            return fallback;
          };
          return {
            docId: String(pick('docId', '')),
            docStatus: String(pick('docStatus', '')),
            flowStatus: String(pick('flowStatus', '')),
            generating: Boolean(pick('generating', false)),
            sourceText: String(pick('sourceText', '')),
            wordCount: Number(pick('wordCount', 0)) || 0
          };
        }
        """
    )
    thoughts = page.locator(THOUGHT_ITEM_SELECTOR).count()
    state["thoughtCount"] = thoughts
    return state


def wait_until_generation_idle(page: Page, timeout_s: float = 45.0, poll_interval_s: float = 0.5) -> bool:
    start = time.monotonic()
    while True:
        state = get_ui_state(page)
        if not _state_generation_active(state):
            return True
        if time.monotonic() - start >= max(1.0, timeout_s):
            return False
        time.sleep(max(0.1, poll_interval_s))


def send_instruction(page: Page, instruction: str) -> None:
    wait_until_generation_idle(page, timeout_s=30.0, poll_interval_s=0.4)
    page.fill(TEXTAREA_SELECTOR, instruction)
    btn = page.locator(SEND_SELECTOR).first
    end = time.monotonic() + 20.0
    while time.monotonic() < end:
        disabled = btn.get_attribute("disabled")
        if disabled is None:
            break
        page.wait_for_timeout(200)
    btn.click()


def wait_generation_cycle(page: Page, timeout_s: int, poll_interval_s: float) -> Dict[str, Any]:
    start = time.monotonic()
    trace: List[Dict[str, Any]] = []
    last_trace = 0.0
    started = False
    finished = False
    timeout = False
    end_state: Dict[str, Any] = {}
    idle_streak = 0
    non_generating_streak = 0
    stable_chars_streak = 0
    last_chars = -1

    while True:
        state = get_ui_state(page)
        end_state = state
        is_active = _state_generation_active(state)
        char_count = compact_len(str(state.get("sourceText", "")))

        if is_active:
            started = True
        elif not started:
            doc_status = str(state.get("docStatus", ""))
            flow_status = str(state.get("flowStatus", ""))
            if _status_contains_any(doc_status, ("生成中", "解析中", "检查模型服务")) or _status_contains_any(
                flow_status, ("分析", "规划", "生成")
            ):
                started = True

        if started:
            if not is_active:
                idle_streak += 1
                if idle_streak >= 2:
                    finished = True
                    break
            else:
                idle_streak = 0
                if not bool(state.get("generating")):
                    non_generating_streak += 1
                    if char_count == last_chars:
                        stable_chars_streak += 1
                    else:
                        stable_chars_streak = 0
                    # Some front-end states linger at "解析中/规划" even when stream already stopped.
                    # If char count is stable for multiple polls and generating flag stays false, accept completion.
                    if non_generating_streak >= 6 and stable_chars_streak >= 4:
                        finished = True
                        break
                else:
                    non_generating_streak = 0
                    stable_chars_streak = 0
                last_chars = char_count

        elapsed = time.monotonic() - start
        if elapsed - last_trace >= 2.0:
            trace.append(
                {
                    "t_s": round(elapsed, 1),
                    "generating": bool(state.get("generating")),
                    "doc_status": str(state.get("docStatus", "")),
                    "flow_status": str(state.get("flowStatus", "")),
                    "chars": compact_len(str(state.get("sourceText", ""))),
                    "thought_count": int(state.get("thoughtCount", 0)),
                }
            )
            if len(trace) > 180:
                trace = trace[-180:]
            last_trace = elapsed

        if elapsed >= timeout_s:
            timeout = True
            break
        time.sleep(poll_interval_s)

    return {
        "started": started,
        "finished": finished,
        "timed_out": timeout,
        "duration_s": round(time.monotonic() - start, 2),
        "trace": trace,
        "end_state": end_state,
    }


def _state_generation_active(state: Dict[str, Any]) -> bool:
    if bool(state.get("generating")):
        return True
    doc_status = str(state.get("docStatus", "")).strip()
    flow_status = str(state.get("flowStatus", "")).strip()
    merged = f"{doc_status}\n{flow_status}"
    return _status_contains_any(merged, STATUS_RUNNING_HINTS)


def _merge_cycles(base: Dict[str, Any], extra: Dict[str, Any], merged_trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "started": bool(base.get("started")) or bool(extra.get("started")),
        "finished": bool(extra.get("finished")) or bool(base.get("finished")),
        "timed_out": bool(extra.get("timed_out")),
        "duration_s": round(float(base.get("duration_s") or 0.0) + float(extra.get("duration_s") or 0.0), 2),
        "trace": merged_trace[-240:],
        "end_state": extra.get("end_state") or base.get("end_state") or {},
    }

def run_generation_with_retry(page: Page, instruction: str, cfg: RunnerConfig, retries: int = 1) -> Dict[str, Any]:
    merged_trace: List[Dict[str, Any]] = []
    final_cycle: Dict[str, Any] = {}
    final_post: Dict[str, Any] = {}
    attempts = 0
    for attempt in range(retries + 1):
        attempts += 1
        send_instruction(page, instruction)
        cycle = wait_generation_cycle(page, timeout_s=cfg.timeout_s, poll_interval_s=cfg.poll_interval_s)
        post = cycle.get("end_state", {}) or get_ui_state(page)
        trace = cycle.get("trace", []) or []
        for row in trace:
            row2 = dict(row)
            row2["attempt"] = attempt + 1
            merged_trace.append(row2)

        if cycle.get("timed_out") and _state_generation_active(post):
            settle_timeout = max(45, min(180, int(cfg.timeout_s * 0.4)))
            settle = wait_generation_cycle(page, timeout_s=settle_timeout, poll_interval_s=cfg.poll_interval_s)
            settle_trace = settle.get("trace", []) or []
            for row in settle_trace:
                row2 = dict(row)
                row2["attempt"] = attempt + 1
                row2["phase"] = "settle"
                merged_trace.append(row2)
            cycle = _merge_cycles(cycle, settle, merged_trace)
            post = cycle.get("end_state", {}) or get_ui_state(page)

        status_text = str(post.get("docStatus", ""))
        generation_failed = _status_indicates_failure(status_text)
        busy_conflict = _status_indicates_busy(status_text)
        if busy_conflict:
            wait_until_generation_idle(page, timeout_s=20.0, poll_interval_s=cfg.poll_interval_s)
            post = get_ui_state(page)
            status_text = str(post.get("docStatus", ""))
            generation_failed = _status_indicates_failure(status_text)
            busy_conflict = _status_indicates_busy(status_text)
        active = _state_generation_active(post)
        retryable = (
            busy_conflict
            or generation_failed
            or (bool(cycle.get("timed_out")) and active)
            or (not bool(cycle.get("finished")) and not active)
        )

        final_cycle = cycle
        final_post = post
        if retryable and attempt < retries:
            if _status_indicates_transport_issue(status_text):
                try:
                    page.reload(wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_selector(APP_SELECTOR, timeout=60000)
                    page.wait_for_selector(EDITOR_SELECTOR, timeout=60000)
                    ensure_assistant_open(page)
                    page.wait_for_selector(TEXTAREA_SELECTOR, timeout=60000)
                except Exception:
                    pass
            time.sleep(1.0)
            continue
        break

    final_cycle["trace"] = merged_trace[-240:]
    return {"cycle": final_cycle, "post": final_post, "attempts": attempts}

alias_candidates = text_eval_domain.alias_candidates
token_present = text_eval_domain.token_present
heading_present = text_eval_domain.heading_present
is_format_sensitive_case = text_eval_domain.is_format_sensitive_case
_extract_heading_text = text_eval_domain.extract_heading_text
_looks_like_numbered_list_item_heading = text_eval_domain.looks_like_numbered_list_item_heading
_parse_heading_line = text_eval_domain.parse_heading_line
_is_heading_line = text_eval_domain.is_heading_line
_split_sections_by_headings = text_eval_domain.split_sections_by_headings
_looks_like_bilingual_case = text_eval_domain.looks_like_bilingual_case
_evaluate_section_richness = text_eval_domain.evaluate_section_richness
evaluate_acceptance = text_eval_domain.evaluate_acceptance
build_instruction_with_acceptance = text_eval_domain.build_instruction_with_acceptance
build_round_instruction = text_eval_domain.build_round_instruction
should_try_round_length_repair = text_eval_domain.should_try_round_length_repair
should_try_round_acceptance_repair = text_eval_domain.should_try_round_acceptance_repair
build_round_length_repair_prompt = text_eval_domain.build_round_length_repair_prompt
build_round_acceptance_repair_prompt = text_eval_domain.build_round_acceptance_repair_prompt
check_keep_and_change = text_eval_domain.check_keep_and_change


def case_artifact_dir(root: Path, case_id: str) -> Path:
    path = root / case_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_failure_screenshot(page: Page, path: Path) -> None:
    try:
        page.screenshot(path=str(path), full_page=True, timeout=120000)
    except Exception:
        pass


def save_text_snapshot(
    artifact_dir: Path,
    file_name: str,
    title: str,
    text: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    result = {"attempted": True, "ok": False, "path": "", "error": ""}
    out_path = artifact_dir / file_name
    try:
        lines: List[str] = [f"# {title}", ""]
        if meta:
            for k, v in meta.items():
                lines.append(f"- {k}: {v}")
            lines.append("")
        lines.append("## Content")
        lines.append("")
        lines.append(str(text or ""))
        out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        result["ok"] = out_path.exists()
        result["path"] = str(out_path)
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result


should_export_docx = export_domain.should_export_docx
_extract_issue_codes = export_domain.extract_issue_codes
classify_precheck_warnings = export_domain.classify_precheck_warnings
fetch_export_precheck = export_domain.fetch_export_precheck
probe_docx_download_headers = export_domain.probe_docx_download_headers
validate_docx_style_conformance = export_domain.validate_docx_style_conformance
export_docx_if_requested = export_domain.export_docx_if_requested


def run_single_case(
    page: Page,
    base_url: str,
    case: Dict[str, Any],
    cfg: RunnerConfig,
    artifacts_root: Path,
) -> Dict[str, Any]:
    case_id = str(case.get("id", "single-unknown"))
    artifact_dir = case_artifact_dir(artifacts_root, case_id)
    started_at = time.time()
    errors: List[str] = []
    warnings: List[str] = []

    doc_id = open_new_case_page(page, base_url)
    pre = get_ui_state(page)
    pre_text = str(pre.get("sourceText", ""))
    pre_thought = int(pre.get("thoughtCount", 0))

    prompt = str(case.get("prompt", "")).strip()
    prompt_with_constraints = build_instruction_with_acceptance(prompt, case.get("acceptance", {}) or {})
    generation = run_generation_with_retry(page, prompt_with_constraints, cfg, retries=1)
    cycle = generation["cycle"]
    post = generation["post"]
    post_text = str(post.get("sourceText", ""))
    post_thought = int(post.get("thoughtCount", 0))
    thought_delta = post_thought - pre_thought
    content_changed = post_text.strip() != pre_text.strip()

    acceptance = evaluate_acceptance(post_text, case.get("acceptance", {}) or {})
    status_text = str(post.get("docStatus", ""))
    generation_failed = _status_indicates_failure(status_text)
    conflict_409 = _status_indicates_busy(status_text)
    soft_success = bool(acceptance.get("passed")) and content_changed
    if generation_failed and not (conflict_409 and content_changed) and not soft_success:
        errors.append(f"generation_status={status_text}")
    if cycle.get("timed_out") and not (conflict_409 and content_changed) and not soft_success:
        errors.append("generation_timeout")
    if not cycle.get("started"):
        errors.append("generation_not_started")
    if not cycle.get("finished") and not (conflict_409 and content_changed) and not soft_success:
        errors.append("generation_not_finished")
    if not content_changed:
        errors.append("content_not_changed")

    if not acceptance.get("passed"):
        errors.extend([f"acceptance:{x}" for x in acceptance.get("failures", [])])

    text_snapshot = save_text_snapshot(
        artifact_dir=artifact_dir,
        file_name=f"{case_id}.md",
        title=case_id,
        text=post_text,
        meta={
            "mode": "single",
            "group": str(case.get("group", "")),
            "doc_id": doc_id,
            "char_count": compact_len(post_text),
        },
    )
    if not text_snapshot.get("ok"):
        warnings.append(f"text_snapshot_failed:{text_snapshot.get('error')}")

    export_result = None
    export_precheck = None
    export_provenance = None
    docx_style_check = None
    if should_export_docx(case, cfg):
        format_sensitive = is_format_sensitive_case(case)
        export_precheck = fetch_export_precheck(base_url, doc_id)
        if not export_precheck.get("ok"):
            errors.append(f"docx_precheck_failed:{export_precheck.get('error') or 'precheck_not_ok'}")
        else:
            if export_precheck.get("can_export") is False:
                issues = ",".join(export_precheck.get("issues") or []) or "blocked"
                errors.append(f"docx_precheck_blocked:{issues}")
            pre_warn = export_precheck.get("warnings") or []
            if pre_warn:
                classified = classify_precheck_warnings([str(x) for x in pre_warn])
                blocking_warn = classified.get("blocking") or []
                non_blocking_warn = classified.get("non_blocking") or []
                if blocking_warn:
                    errors.append("docx_precheck_warning:" + ",".join([str(x) for x in blocking_warn[:6]]))
                if non_blocking_warn:
                    warnings.append("docx_precheck_warning_non_blocking:" + ",".join([str(x) for x in non_blocking_warn[:6]]))
        export_result = export_docx_if_requested(page, artifact_dir, case_id, fallback_text=post_text)
        if not export_result.get("ok"):
            errors.append(f"docx_export_failed:{export_result.get('error')}")
        else:
            if format_sensitive and str(export_result.get("method") or "") == "local_text_fallback":
                errors.append("docx_export_method_not_allowed:local_text_fallback")
            export_provenance = probe_docx_download_headers(base_url, doc_id)
            if export_provenance.get("ok"):
                export_result["provenance"] = export_provenance
                backend = str(export_provenance.get("export_backend") or "").strip()
                if backend:
                    export_result["backend"] = backend
                warn = str(export_provenance.get("warn") or "").strip()
                if warn:
                    errors.append(f"docx_compat_warning:{warn}")
            else:
                warnings.append(f"docx_provenance_probe_failed:{export_provenance.get('error')}")
            docx_path_raw = str(export_result.get("path") or "").strip()
            if docx_path_raw:
                docx_style_check = validate_docx_style_conformance(Path(docx_path_raw), format_sensitive=format_sensitive)
                export_result["style_check"] = docx_style_check
                if not docx_style_check.get("passed"):
                    errors.extend([f"docx_style:{x}" for x in (docx_style_check.get("failures") or [])])

    passed = len(errors) == 0
    if not passed:
        save_failure_screenshot(page, artifact_dir / "failure.png")

    return {
        "id": case_id,
        "group": case.get("group", ""),
        "group_label": case.get("group_label", ""),
        "mode": "single",
        "doc_id": doc_id,
        "prompt_preview": prompt[:220],
        "duration_s": round(time.time() - started_at, 2),
        "attempts": int(generation.get("attempts", 1)),
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "stage_checks": {
            "generation_started": bool(cycle.get("started")),
            "generation_finished": bool(cycle.get("finished")),
            "generation_timed_out": bool(cycle.get("timed_out")),
            "thought_chain_delta": thought_delta,
            "content_changed": content_changed,
        },
        "status": {
            "doc_status": str(post.get("docStatus", "")),
            "flow_status": str(post.get("flowStatus", "")),
            "word_count": int(post.get("wordCount", 0)),
            "char_count": compact_len(post_text),
        },
        "text_preview": post_text[:300],
        "acceptance": acceptance,
        "trace": cycle.get("trace", []),
        "artifact_dir": str(artifact_dir),
        "text_snapshot": text_snapshot,
        "docx_export": export_result,
        "export_precheck": export_precheck,
        "docx_provenance": export_provenance,
        "docx_style_check": docx_style_check,
    }


run_multiround_case = multiround_adapter.run_multiround_case


load_checkpoint = runmeta_domain.load_checkpoint
save_checkpoint = runmeta_domain.save_checkpoint
build_summary = runmeta_domain.build_summary
write_summary_md = runmeta_domain.write_summary_md
print_progress = runmeta_domain.print_progress


def parse_args() -> argparse.Namespace:
    return runmeta_domain.parse_args(DEFAULT_DATASET, DEFAULT_MULTISET, str(DEFAULT_OUT_ROOT))


def load_and_select_cases(args: argparse.Namespace) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    return runmeta_domain.load_and_select_cases(
        args,
        read_json_fn=read_json,
        filter_by_index_fn=filter_by_index,
        pick_first_per_group_fn=pick_first_per_group,
    )


def main() -> int:
    args = parse_args()
    base_url = normalize_base_url(args.base_url)
    out_root = Path(args.out_root)
    run_ts = now_stamp()
    run_dir = out_root / f"content_validation_{run_ts}"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    cfg = RunnerConfig(
        base_url=base_url,
        start_server=bool(args.start_server),
        disable_ollama=bool(args.disable_ollama),
        headless=not bool(args.headed),
        timeout_s=max(30, int(args.timeout_s)),
        poll_interval_s=max(0.2, float(args.poll_interval_s)),
        group_smoke=bool(args.group_smoke),
        run_all=bool(args.run_all),
        max_single=int(args.max_single or 0),
        max_multi=int(args.max_multi or 0),
        single_start=max(1, int(args.single_start or 1)),
        single_end=max(1, int(args.single_end or 1)),
        multi_start=max(1, int(args.multi_start or 1)),
        multi_end=max(1, int(args.multi_end or 1)),
        export_docx_all=bool(args.export_docx_all),
        export_docx_for_format=bool(args.export_docx_for_format),
        checkpoint=Path(args.checkpoint) if str(args.checkpoint).strip() else None,
        resume=bool(args.resume),
        out_root=out_root,
    )

    single_cases, multi_cases = load_and_select_cases(args)
    print(f"selected single={len(single_cases)} multiround={len(multi_cases)}")
    if not single_cases and not multi_cases:
        print("no cases selected")
        return 2

    single_done: List[str] = []
    multi_done: List[str] = []
    if cfg.resume and cfg.checkpoint:
        ckpt = load_checkpoint(cfg.checkpoint)
        single_done = [str(x) for x in ckpt.get("single_done", [])]
        multi_done = [str(x) for x in ckpt.get("multi_done", [])]
        if single_done or multi_done:
            print(f"resume loaded: single_done={len(single_done)} multi_done={len(multi_done)}")

    server_proc: Optional[subprocess.Popen[bytes]] = None
    if not url_ready(base_url, timeout_s=2.0):
        if not cfg.start_server:
            print(
                f"base url not reachable: {base_url}; pass --start-server or start app manually",
                file=sys.stderr,
            )
            return 3
        server_proc = start_local_server(base_url, cfg.disable_ollama)
        print(f"server started at {base_url}")

    run_data: Dict[str, Any] = {
        "timestamp": run_ts,
        "config": {
            "base_url": base_url,
            "group_smoke": cfg.group_smoke,
            "run_all": cfg.run_all,
            "timeout_s": cfg.timeout_s,
            "poll_interval_s": cfg.poll_interval_s,
            "start_server": cfg.start_server,
            "disable_ollama": cfg.disable_ollama,
            "export_docx_all": cfg.export_docx_all,
            "export_docx_for_format": cfg.export_docx_for_format,
        },
        "results": {"single": [], "multiround": []},
        "paths": {},
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=cfg.headless)
            context = browser.new_context(
                accept_downloads=True,
                locale="zh-CN",
                viewport={"width": 1440, "height": 900},
            )
            page = context.new_page()

            total_single = len(single_cases)
            for idx, case in enumerate(single_cases, start=1):
                case_id = str(case.get("id", f"single-{idx}"))
                if case_id in single_done:
                    continue
                print_progress("single", idx, total_single, case_id, str(case.get("group", "")))
                try:
                    result = None
                    for _attempt in range(3):
                        try:
                            server_proc = ensure_server_available(base_url, cfg, server_proc)
                            result = run_single_case(page, base_url, case, cfg, artifacts_dir)
                            break
                        except PlaywrightTimeoutError:
                            if _attempt >= 2:
                                raise
                            page.wait_for_timeout(1500)
                            continue
                        except Exception as exc:
                            if _looks_like_connection_error(exc) and _attempt < 2:
                                server_proc = ensure_server_available(base_url, cfg, server_proc)
                                page.wait_for_timeout(800)
                                continue
                            raise
                    if result is None:
                        raise RuntimeError("single_case_result_missing")
                except PlaywrightTimeoutError as exc:
                    artifact_dir = case_artifact_dir(artifacts_dir, case_id)
                    save_failure_screenshot(page, artifact_dir / "exception_timeout.png")
                    result = {
                        "id": case_id,
                        "group": case.get("group", ""),
                        "mode": "single",
                        "passed": False,
                        "errors": [f"playwright_timeout:{exc}"],
                        "artifact_dir": str(artifact_dir),
                    }
                except Exception as exc:
                    artifact_dir = case_artifact_dir(artifacts_dir, case_id)
                    save_failure_screenshot(page, artifact_dir / "exception_error.png")
                    result = {
                        "id": case_id,
                        "group": case.get("group", ""),
                        "mode": "single",
                        "passed": False,
                        "errors": [f"exception:{exc}"],
                        "artifact_dir": str(artifact_dir),
                    }
                run_data["results"]["single"].append(result)
                single_done.append(case_id)
                if cfg.checkpoint:
                    save_checkpoint(cfg.checkpoint, single_done, multi_done)

            total_multi = len(multi_cases)
            for idx, case in enumerate(multi_cases, start=1):
                case_id = str(case.get("id", f"multi-{idx}"))
                if case_id in multi_done:
                    continue
                print_progress("multi", idx, total_multi, case_id, str(case.get("group", "")))
                try:
                    result = None
                    for _attempt in range(3):
                        try:
                            server_proc = ensure_server_available(base_url, cfg, server_proc)
                            result = run_multiround_case(page, base_url, case, cfg, artifacts_dir)
                            break
                        except PlaywrightTimeoutError:
                            if _attempt >= 2:
                                raise
                            page.wait_for_timeout(1500)
                            continue
                        except Exception as exc:
                            if _looks_like_connection_error(exc) and _attempt < 2:
                                server_proc = ensure_server_available(base_url, cfg, server_proc)
                                page.wait_for_timeout(800)
                                continue
                            raise
                    if result is None:
                        raise RuntimeError("multiround_case_result_missing")
                except PlaywrightTimeoutError as exc:
                    artifact_dir = case_artifact_dir(artifacts_dir, case_id)
                    save_failure_screenshot(page, artifact_dir / "exception_timeout.png")
                    result = {
                        "id": case_id,
                        "group": case.get("group", ""),
                        "mode": "multiround",
                        "passed": False,
                        "errors": [f"playwright_timeout:{exc}"],
                        "artifact_dir": str(artifact_dir),
                    }
                except Exception as exc:
                    artifact_dir = case_artifact_dir(artifacts_dir, case_id)
                    save_failure_screenshot(page, artifact_dir / "exception_error.png")
                    result = {
                        "id": case_id,
                        "group": case.get("group", ""),
                        "mode": "multiround",
                        "passed": False,
                        "errors": [f"exception:{exc}"],
                        "artifact_dir": str(artifact_dir),
                    }
                run_data["results"]["multiround"].append(result)
                multi_done.append(case_id)
                if cfg.checkpoint:
                    save_checkpoint(cfg.checkpoint, single_done, multi_done)

            context.close()
            browser.close()
    finally:
        if server_proc is not None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()

    summary = build_summary(run_data)
    run_json = run_dir / f"content_validation_run_{run_ts}.json"
    summary_md = run_dir / f"content_validation_summary_{run_ts}.md"
    run_data["summary"] = summary
    run_data["paths"] = {
        "run_json": str(run_json),
        "summary_md": str(summary_md),
        "artifacts_dir": str(artifacts_dir),
    }
    write_json(run_json, run_data)
    write_summary_md(summary_md, run_data, summary)

    print("run finished")
    print(
        "single: total={total} passed={passed} failed={failed}".format(
            total=summary["single"]["total"],
            passed=summary["single"]["passed"],
            failed=summary["single"]["failed"],
        )
    )
    print(
        "multiround: total={total} passed={passed} failed={failed}".format(
            total=summary["multiround"]["total"],
            passed=summary["multiround"]["passed"],
            failed=summary["multiround"]["failed"],
        )
    )
    print(
        "overall: total={total} passed={passed} failed={failed} pass_rate={rate}%".format(
            total=summary["overall"]["total"],
            passed=summary["overall"]["passed"],
            failed=summary["overall"]["failed"],
            rate=summary["overall"]["pass_rate"],
        )
    )
    print(f"json={run_json}")
    print(f"summary={summary_md}")

    return 0 if summary["overall"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
