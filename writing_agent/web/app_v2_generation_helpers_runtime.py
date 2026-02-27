"""App V2 Generation Helpers Runtime module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

from functools import wraps

_BIND_SKIP_NAMES = {
    "__builtins__",
    "__cached__",
    "__doc__",
    "__file__",
    "__loader__",
    "__name__",
    "__package__",
    "__spec__",
    "_BIND_SKIP_NAMES",
    "_ORIGINAL_FUNCS",
    "bind",
    "install",
    "_proxy_factory",
}
_ORIGINAL_FUNCS: dict[str, object] = {}


def bind(namespace: dict) -> None:
    for key, value in namespace.items():
        if key in _BIND_SKIP_NAMES:
            continue
        if callable(value) and bool(getattr(value, "_wa_runtime_proxy", False)):
            if str(getattr(value, "_wa_runtime_proxy_target_module", "")) == __name__:
                original = _ORIGINAL_FUNCS.get(key)
                if callable(original):
                    globals()[key] = original
                continue
        local = globals().get(key)
        if key in globals() and local is value:
            continue
        globals()[key] = value


def _proxy_factory(fn_name: str, namespace: dict):
    fn = globals()[fn_name]

    @wraps(fn)
    def _proxy(*args, **kwargs):
        bind(namespace)
        return fn(*args, **kwargs)

    _proxy._wa_runtime_proxy = True
    _proxy._wa_runtime_proxy_target_module = __name__
    _proxy._wa_runtime_proxy_target_name = fn_name
    return _proxy


def install(namespace: dict) -> None:
    bind(namespace)
    for fn_name in EXPORTED_FUNCTIONS:
        _ORIGINAL_FUNCS.setdefault(fn_name, globals().get(fn_name))
    for fn_name in EXPORTED_FUNCTIONS:
        namespace[fn_name] = _proxy_factory(fn_name, namespace)


EXPORTED_FUNCTIONS = [
    "_load_mcp_citations_cached",
    "_ensure_mcp_citations",
    "_mcp_rag_enabled",
    "_mcp_first_json",
    "_mcp_rag_retrieve",
    "_mcp_rag_search",
    "_mcp_rag_search_chunks",
    "_recommended_stream_timeouts",
    "_run_with_heartbeat",
    "_default_outline_from_instruction",
    "_fallback_prompt_sections",
    "_build_fallback_prompt",
    "_default_llm_provider",
    "_single_pass_generate",
    "_single_pass_generate_with_heartbeat",
    "_single_pass_generate_stream",
    "_check_generation_quality",
    "_looks_like_prompt_echo",
    "_system_pressure_high",
    "_should_use_fast_generate",
    "_pull_model_stream_iter",
    "_pull_model_stream",
    "_ensure_ollama_ready_iter",
    "_ensure_ollama_ready",
    "_summarize_analysis",
]

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
                yield f"{label}..."
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
        section_hint = "Required H2 order (##):\n" + "\n".join(sections) + "\n"
    prompt = (
        "You are a writing assistant. Generate a formal Chinese Markdown document.\n"
        "Keep the structure clear and avoid placeholders or meta instructions.\n"
        f"{section_hint}"
        f"{length_hint}"
        "User requirement:\n"
        f"{instruction}\n"
    )
    system = "You are a professional writer. Output Markdown only."
    return system, prompt

def _default_llm_provider(settings):
    try:
        return get_default_provider(model=settings.model, timeout_s=settings.timeout_s)
    except Exception as exc:
        raise OllamaError(str(exc)) from exc

def _single_pass_generate(session, *, instruction: str, current_text: str, target_chars: int = 0) -> str:
    """Single-pass fallback generation."""
    settings = get_ollama_settings()
    if not settings.enabled:
        raise OllamaError("\u6a21\u578b\u672a\u542f\u7528")
    provider = _default_llm_provider(settings)
    if not provider.is_running():
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
    raw = provider.chat(system=system, user=prompt, temperature=0.5, options=options)
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
    provider = _default_llm_provider(settings)
    if not provider.is_running():
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
            raw = provider.chat(system=system, user=prompt, temperature=0.5, options=options)
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
    provider = _default_llm_provider(settings)
    if not provider.is_running():
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
    for delta in provider.chat_stream(system=system, user=prompt, temperature=0.5, options=options):
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
    phrases = [
        "you are a writing assistant",
        "output markdown only",
        "user requirement",
        "must include",
    ]
    hit = sum(1 for p in phrases if p in lower)
    if hit >= 2:
        return True
    if src.startswith("浣犳槸") and ("鍔╂墜" in src or "妯″瀷" in src or "鍐欎綔" in src):
        return True
    short_instruction = instruction.strip()[:12]
    if short_instruction and short_instruction in src and "requirement" in lower:
        return True
    if len(src) < 200 and ("requirement" in lower or "markdown" in lower):
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
        return False, "model service disabled"
    base_url = settings.base_url
    probe = OllamaClient(base_url=base_url, model=settings.model, timeout_s=min(5.0, settings.timeout_s))
    if not probe.is_running():
        yield f"checking model service: {base_url}"
        try:
            _start_ollama_serve()
        except FileNotFoundError:
            return False, "ollama executable not found in PATH"
        if not _wait_until(probe.is_running, timeout_s=12):
            return False, f"ollama not ready: {base_url}"
    return True, ""

def _ensure_ollama_ready() -> tuple[bool, str]:
    settings = get_ollama_settings()
    if not settings.enabled:
        return False, "model service disabled"
    base_url = settings.base_url
    probe = OllamaClient(base_url=base_url, model=settings.model, timeout_s=min(5.0, settings.timeout_s))
    if probe.is_running():
        return True, ""
    try:
        _start_ollama_serve()
    except FileNotFoundError:
        return False, "ollama executable not found in PATH"
    if not _wait_until(probe.is_running, timeout_s=12):
        return False, f"ollama not ready: {base_url}"
    return True, ""

def _summarize_analysis(raw: str, analysis: dict) -> dict:
    if not isinstance(analysis, dict):
        return {"summary": "", "missing": [], "steps": []}
    intent = analysis.get("intent") or {}
    entities = analysis.get("entities") or {}
    missing = analysis.get("missing") or []
    constraints = analysis.get("constraints") or []
    decomp = analysis.get("decomposition") or analysis.get("steps") or []
    parts: list[str] = []
    if raw:
        parts.append(f"requirement: {raw}")
    name = str(intent.get("name") or "").strip()
    if name:
        parts.append(f"intent: {name}")
    for key in ("title", "purpose", "length", "formatting", "audience", "output_form", "voice", "avoid", "scope"):
        val = str(entities.get(key) or "").strip()
        if val:
            parts.append(f"{key}: {val}")
    if constraints:
        parts.append("constraints: " + "; ".join([str(x) for x in constraints if str(x).strip()]))
    steps: list[str] = []
    if isinstance(decomp, list):
        steps.extend([str(x).strip() for x in decomp if str(x).strip()])
    if not steps and constraints:
        steps.extend([f"constraint: {str(x).strip()}" for x in constraints if str(x).strip()])
    return {
        "summary": " | ".join([p for p in parts if p]),
        "missing": missing,
        "steps": steps[:6],
    }
