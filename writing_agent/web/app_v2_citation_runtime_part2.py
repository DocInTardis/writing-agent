"""App V2 Citation Runtime Part2 module.

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
    "_STATE_PREFIXES",
    "bind",
    "install",
    "_proxy_factory",
    "_sync_state_from_namespace",
    "_sync_state_to_namespace",
    "_is_state_key",
}
_STATE_PREFIXES = ("_CITATION_VERIFY_", "_DEBUG_")
_ORIGINAL_FUNCS: dict[str, object] = {}


def _is_state_key(name: object) -> bool:
    key = str(name or "")
    return any(key.startswith(prefix) for prefix in _STATE_PREFIXES)


def _sync_state_from_namespace(namespace: dict) -> None:
    for key, value in namespace.items():
        if _is_state_key(key):
            globals()[key] = value
    for key, value in list(globals().items()):
        if _is_state_key(key):
            namespace.setdefault(key, value)


def _sync_state_to_namespace(namespace: dict) -> None:
    for key, value in list(globals().items()):
        # Avoid overwriting state produced by other citation runtime modules.
        if _is_state_key(key) and key not in namespace:
            namespace[key] = value


def bind(namespace: dict) -> None:
    for key, value in namespace.items():
        if key in _BIND_SKIP_NAMES:
            continue
        if callable(value) and bool(getattr(value, "_wa_runtime_proxy", False)):
            if str(getattr(value, "_wa_runtime_proxy_target_module", "")) == __name__:
                # Restore original implementation when namespace holds this module's proxy.
                original = _ORIGINAL_FUNCS.get(key)
                if callable(original):
                    globals()[key] = original
                continue
        local = globals().get(key)
        if key in globals() and local is value:
            continue
        globals()[key] = value
    _sync_state_from_namespace(namespace)


def _proxy_factory(fn_name: str, namespace: dict):
    fn = globals()[fn_name]

    @wraps(fn)
    def _proxy(*args, **kwargs):
        bind(namespace)
        try:
            return fn(*args, **kwargs)
        finally:
            _sync_state_to_namespace(namespace)

    _proxy._wa_runtime_proxy = True
    _proxy._wa_runtime_proxy_target_module = __name__
    _proxy._wa_runtime_proxy_target_name = fn_name
    return _proxy

def _normalize_verify_debug_level(raw: object) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        value = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_DEBUG_LEVEL", "safe")).strip().lower()
    if value in {"full", "unsafe", "internal", "raw"}:
        return "full"
    if value in {"strict", "minimal", "meta"}:
        return "strict"
    return "safe"


def _debug_full_limit_per_min() -> int:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_DEBUG_FULL_MAX_PER_MIN", "8")).strip()
    try:
        return max(0, int(raw))
    except Exception:
        return 8


def _debug_item_sample_limit() -> int:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_DEBUG_ITEM_SAMPLE_LIMIT", "24")).strip()
    try:
        return max(1, int(raw))
    except Exception:
        return 24


def _citation_verify_max_workers(item_count: int) -> int:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", "4")).strip()
    try:
        configured = int(raw)
    except Exception:
        configured = 4
    configured = max(1, min(12, configured))
    size = max(1, int(item_count or 0))
    return min(configured, size)


def _citation_verify_adaptive_workers_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_WORKERS", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _citation_verify_worker_boost_step() -> int:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_BOOST_STEP", "2")).strip()
    try:
        return max(1, min(4, int(raw)))
    except Exception:
        return 2


def _citation_verify_worker_reduce_step() -> int:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_REDUCE_STEP", "2")).strip()
    try:
        return max(1, min(6, int(raw)))
    except Exception:
        return 2


def _citation_verify_effective_workers(item_count: int) -> int:
    base = _citation_verify_max_workers(item_count)
    size = max(1, int(item_count or 0))
    workers = min(base, size)
    if workers <= 1 or not _citation_verify_adaptive_workers_enabled():
        return workers

    observe = _citation_verify_observe_snapshot(include_recent=False)
    runs = int(observe.get("runs") or 0) if isinstance(observe, dict) else 0
    if runs < 6:
        return workers

    elapsed = observe.get("elapsed_ms") if isinstance(observe.get("elapsed_ms"), dict) else {}
    errors = observe.get("errors") if isinstance(observe.get("errors"), dict) else {}
    items = observe.get("items") if isinstance(observe.get("items"), dict) else {}
    p95 = float(elapsed.get("p95") or 0.0)
    error_rate = float(errors.get("rate_per_run") or 0.0)
    avg_items = float(items.get("avg") or 0.0)

    if p95 >= 4500.0 or error_rate >= 0.30:
        workers = max(1, workers - _citation_verify_worker_reduce_step())
    elif p95 <= 1600.0 and error_rate <= 0.08 and size >= max(8, int(round(avg_items or 0.0))):
        workers = min(size, workers + _citation_verify_worker_boost_step())
    return max(1, min(size, workers))


def _debug_full_bucket_max_keys() -> int:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_DEBUG_FULL_MAX_KEYS", "1024")).strip()
    try:
        return max(1, int(raw))
    except Exception:
        return 1024


def _prune_debug_full_rate_buckets(*, floor: float, keep_key: str) -> None:
    # Drop stale timestamps first to avoid unbounded growth on long-running processes.
    for key in list(_DEBUG_FULL_RATE_BUCKETS.keys()):
        rows = [ts for ts in _DEBUG_FULL_RATE_BUCKETS.get(key, []) if ts >= floor]
        if rows:
            _DEBUG_FULL_RATE_BUCKETS[key] = rows
        else:
            _DEBUG_FULL_RATE_BUCKETS.pop(key, None)

    max_keys = _debug_full_bucket_max_keys()
    if len(_DEBUG_FULL_RATE_BUCKETS) <= max_keys:
        return

    # Keep the active key and most recently used buckets; evict older buckets.
    ranked: list[tuple[str, float]] = []
    for key, rows in _DEBUG_FULL_RATE_BUCKETS.items():
        last_ts = max(rows) if rows else 0.0
        ranked.append((key, float(last_ts)))
    ranked.sort(key=lambda x: x[1], reverse=True)
    keep: set[str] = {keep_key}
    for key, _ in ranked:
        if len(keep) >= max_keys:
            break
        keep.add(key)
    for key in list(_DEBUG_FULL_RATE_BUCKETS.keys()):
        if key not in keep:
            _DEBUG_FULL_RATE_BUCKETS.pop(key, None)


def _allow_full_debug(doc_id: str) -> bool:
    limit = _debug_full_limit_per_min()
    if limit <= 0:
        return False
    key = str(doc_id or "").strip() or "_global"
    now = time.time()
    floor = now - 60.0
    with _DEBUG_FULL_RATE_LOCK:
        _prune_debug_full_rate_buckets(floor=floor, keep_key=key)
        rows = list(_DEBUG_FULL_RATE_BUCKETS.get(key, []))
        if len(rows) >= limit:
            _DEBUG_FULL_RATE_BUCKETS[key] = rows
            return False
        rows.append(now)
        _DEBUG_FULL_RATE_BUCKETS[key] = rows
        return True


def _sample_debug_items(rows: list[dict], *, limit: int) -> list[dict]:
    data = list(rows or [])
    if limit <= 0 or len(data) <= limit:
        return data
    if limit == 1:
        return [data[0]]
    # Deterministic stride sampling to keep timeline coverage without randomness.
    stride = (len(data) - 1) / float(limit - 1)
    picked: list[dict] = []
    seen: set[int] = set()
    for i in range(limit):
        idx = int(round(i * stride))
        idx = max(0, min(len(data) - 1, idx))
        if idx in seen:
            continue
        seen.add(idx)
        picked.append(data[idx])
    if len(picked) < limit:
        for i, row in enumerate(data):
            if i in seen:
                continue
            picked.append(row)
            if len(picked) >= limit:
                break
    return picked[:limit]


def _mask_middle(value: str, head: int = 2, tail: int = 2) -> str:
    src = str(value or "")
    if not src:
        return ""
    if len(src) <= (head + tail + 1):
        return "*" * max(3, len(src))
    return f"{src[:head]}***{src[-tail:]}"


def _sanitize_debug_url(value: str) -> str:
    try:
        parsed = urlsplit(str(value or ""))
    except Exception:
        return _mask_middle(str(value or ""), head=6, tail=4)
    path = str(parsed.path or "")
    if len(path) > 80:
        path = path[:40] + ".../" + path[-20:]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _sanitize_debug_text(value: object, *, max_len: int = 220) -> str:
    text = _normalize_citation_text(value)
    if not text:
        return ""

    def _mask_email(m: re.Match) -> str:
        local = str(m.group(1) or "")
        domain = str(m.group(2) or "")
        return f"{_mask_middle(local, head=1, tail=1)}@{domain}"

    text = _DEBUG_EMAIL_RE.sub(_mask_email, text)
    text = _DEBUG_URL_RE.sub(lambda m: _sanitize_debug_url(m.group(0)), text)
    text = _DEBUG_SECRET_TOKEN_RE.sub(lambda m: _mask_middle(m.group(0), head=3, tail=2), text)
    text = _DEBUG_LONG_TOKEN_RE.sub(lambda m: _mask_middle(m.group(0), head=3, tail=2), text)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def _sanitize_verify_debug_item(item: dict, *, level: str) -> dict:
    row = dict(item or {})
    providers_raw = row.get("providers")
    providers = providers_raw if isinstance(providers_raw, dict) else {}
    clean_providers = {str(k): int(v or 0) for k, v in providers.items()}
    out = {
        "id": str(row.get("id") or ""),
        "cache_hit": bool(row.get("cache_hit", False)),
        "query": "",
        "providers": clean_providers,
        "errors": [],
        "picked_provider": str(row.get("picked_provider") or ""),
        "picked_title_score": float(row.get("picked_title_score") or 0.0),
        "picked_year_score": float(row.get("picked_year_score") or 0.0),
        "picked_total_score": float(row.get("picked_total_score") or 0.0),
        "elapsed_ms": float(row.get("elapsed_ms") or 0.0),
    }
    errors_raw = row.get("errors")
    error_items = errors_raw if isinstance(errors_raw, list) else []
    if level == "full":
        out["query"] = _normalize_citation_text(row.get("query"))
        out["errors"] = [_normalize_citation_text(x) for x in error_items[:4] if _normalize_citation_text(x)]
        return out
    if level == "safe":
        out["query"] = _sanitize_debug_text(row.get("query"), max_len=200)
        out["errors"] = [
            _sanitize_debug_text(x, max_len=180) for x in error_items[:4] if _sanitize_debug_text(x, max_len=180)
        ]
        return out
    # strict/minimal: only return coarse metrics.
    out["query"] = ""
    out["errors"] = []
    return out


def _build_citation_verify_debug_payload(
    *,
    persist: bool,
    input_count: int,
    worker_count: int,
    elapsed_ms: float,
    requested_level: str,
    debug_level: str,
    rate_limited_full: bool,
    debug_items: list[dict],
    request_observe: dict | None = None,
    observe_snapshot: dict | None = None,
) -> dict:
    sample_limit = _debug_item_sample_limit()
    sampled = _sample_debug_items(debug_items, limit=sample_limit)
    sanitized_items = [_sanitize_verify_debug_item(row, level=debug_level) for row in sampled]
    out = {
        "request": {"persist": persist, "debug": True, "input_count": input_count, "workers": max(0, int(worker_count or 0))},
        "requested_level": requested_level,
        "level": debug_level,
        "sanitized": debug_level != "full",
        "rate_limited_full": rate_limited_full,
        "cache": _citation_verify_cache_snapshot(),
        "sampling": {
            "input_items": len(debug_items),
            "output_items": len(sampled),
            "limit": sample_limit,
            "truncated": len(sampled) < len(debug_items),
        },
        "elapsed_ms": round(max(0.0, float(elapsed_ms or 0.0)), 2),
        "items": sanitized_items,
    }
    if isinstance(request_observe, dict) or isinstance(observe_snapshot, dict):
        out["observe"] = {
            "request": dict(request_observe or {}),
            "window": dict(observe_snapshot or {}),
        }
    return out


def _verify_one_citation_for_api(key: str, cite: Citation, *, debug_enabled: bool) -> tuple[dict, Citation, dict | None]:
    try:
        if debug_enabled:
            item, next_cite, dbg = _verify_one_citation_detail(cite)
            row = dict(dbg or {})
            row["id"] = key
            item["id"] = key
            return item, next_cite, row
        item, next_cite = _verify_one_citation(cite)
        item["id"] = key
        return item, next_cite, None
    except Exception as exc:
        item = {
            "id": key,
            "author": cite.authors or "",
            "title": cite.title or "",
            "year": cite.year or "",
            "source": cite.venue or cite.url or "",
            "status": "error",
            "provider": "",
            "score": 0.0,
            "matched_title": "",
            "matched_year": "",
            "matched_source": "",
            "doi": "",
            "url": "",
            "reason": f"exception:{exc.__class__.__name__}",
        }
        if not debug_enabled:
            return item, cite, None
        return (
            item,
            cite,
            {
                "id": key,
                "cache_hit": False,
                "query": _build_citation_verify_query(cite),
                "providers": {},
                "errors": [f"exception:{exc.__class__.__name__}"],
                "picked_provider": "",
                "picked_title_score": 0.0,
                "picked_year_score": 0.0,
                "picked_total_score": 0.0,
                "elapsed_ms": 0.0,
            },
        )


def _verify_citation_batch(
    source_citations: dict[str, Citation], *, debug_enabled: bool
) -> tuple[list[dict], dict[str, Citation], list[dict], int]:
    ordered = list(source_citations.items())[:60]
    if not ordered:
        return [], {}, [], 0

    workers = _citation_verify_effective_workers(len(ordered))
    if workers <= 1 or len(ordered) <= 1:
        rows = [_verify_one_citation_for_api(key, cite, debug_enabled=debug_enabled) for key, cite in ordered]
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="citation-verify") as pool:
            rows = list(
                pool.map(
                    lambda kv: _verify_one_citation_for_api(kv[0], kv[1], debug_enabled=debug_enabled),
                    ordered,
                )
            )

    results: list[dict] = []
    updated: dict[str, Citation] = {}
    debug_items: list[dict] = []
    for (key, _), (item, next_cite, row) in zip(ordered, rows):
        item["id"] = key
        results.append(item)
        updated[key] = next_cite
        if debug_enabled and isinstance(row, dict):
            row["id"] = key
            debug_items.append(row)
    return results, updated, debug_items, workers


def _build_citation_verify_query(cite: Citation) -> str:
    title = _normalize_citation_text(cite.title)
    if not title:
        return ""
    query_parts: list[str] = [title]
    raw_authors = _normalize_citation_text(cite.authors or "")
    if raw_authors:
        people = re.split(r"[,;锛岋紱/&]+|\band\b", raw_authors, flags=re.IGNORECASE)
        for person in people:
            words = [w for w in person.split() if w]
            if words:
                query_parts.append(words[-1])
                break
    year = _extract_citation_year(cite.year)
    if year:
        query_parts.append(year)
    return " ".join(query_parts).strip()[:256]


def _score_openalex_match(cite: Citation, work) -> tuple[float, float, float, float]:
    cite_title = _normalize_citation_title(cite.title)
    work_title = _normalize_citation_title(getattr(work, "title", ""))
    title_score = SequenceMatcher(None, cite_title, work_title).ratio() if (cite_title and work_title) else 0.0

    cite_year = _extract_citation_year(cite.year)
    work_year = _extract_citation_year(getattr(work, "published", ""))
    year_score = 0.0
    if cite_year and work_year:
        try:
            gap = abs(int(cite_year) - int(work_year))
        except Exception:
            gap = 9
        if gap == 0:
            year_score = 1.0
        elif gap == 1:
            year_score = 0.65
        elif gap == 2:
            year_score = 0.35
    elif not cite_year:
        year_score = 0.5

    cite_authors = _citation_author_tokens(cite.authors or "")
    work_authors = _citation_author_tokens(" ".join(getattr(work, "authors", []) or []))
    if cite_authors and work_authors:
        author_score = len(cite_authors & work_authors) / max(1, len(cite_authors))
    elif not cite_authors:
        author_score = 0.5
    else:
        author_score = 0.0

    title_weight = 0.82
    year_weight = 0.12 if cite_year else 0.0
    author_weight = 0.06 if cite_authors else 0.0
    total_weight = title_weight + year_weight + author_weight
    score = (
        title_score * title_weight + year_score * year_weight + author_score * author_weight
    ) / (total_weight or 1.0)
    return float(score), float(title_score), float(year_score), float(author_score)


def _citation_work_source(work) -> str:
    return _normalize_citation_text(
        getattr(work, "primary_category", "")
        or ((getattr(work, "categories", []) or [""])[0])
    )


def _collect_citation_candidates(query: str) -> tuple[list[tuple[str, object]], list[str]]:
    candidates: list[tuple[str, object]] = []
    errors: list[str] = []

    try:
        oa = search_openalex(query=query, max_results=8, timeout_s=12.0)
        for w in list(getattr(oa, "works", []) or []):
            candidates.append(("openalex", w))
    except Exception as exc:
        errors.append(f"openalex:{exc.__class__.__name__}")

    try:
        cr = search_crossref(query=query, max_results=8, timeout_s=12.0)
        for w in list(getattr(cr, "works", []) or []):
            candidates.append(("crossref", w))
    except Exception as exc:
        errors.append(f"crossref:{exc.__class__.__name__}")

    return candidates, errors


def _pick_best_citation_candidate(cite: Citation, candidates: list[tuple[str, object]]) -> tuple[str, object | None, float, float, float]:
    best_provider = ""
    best_work = None
    best_score = -1.0
    best_title_score = 0.0
    best_year_score = 0.0
    for provider, work in candidates:
        score, title_score, year_score, _ = _score_openalex_match(cite, work)
        if score > best_score:
            best_provider = provider
            best_work = work
            best_score = score
            best_title_score = title_score
            best_year_score = year_score
    return best_provider, best_work, best_score, best_title_score, best_year_score


def _new_citation_verify_item(cite: Citation) -> dict:
    return {
        "id": cite.key,
        "author": cite.authors or "",
        "title": cite.title or "",
        "year": cite.year or "",
        "source": cite.venue or cite.url or "",
        "status": "not_found",
        "provider": "",
        "score": 0.0,
        "matched_title": "",
        "matched_year": "",
        "matched_source": "",
        "doi": "",
        "url": "",
        "reason": "no_match",
    }


def _verify_one_citation_detail(cite: Citation) -> tuple[dict, Citation, dict]:
    started = time.perf_counter()
    debug_info = {
        "cache_hit": False,
        "query": "",
        "providers": {"openalex": 0, "crossref": 0},
        "errors": [],
        "picked_provider": "",
        "picked_title_score": 0.0,
        "picked_year_score": 0.0,
        "picked_total_score": 0.0,
        "elapsed_ms": 0.0,
    }
    item = _new_citation_verify_item(cite)

    cached = _citation_verify_cache_get(cite)
    if cached is not None:
        cached_item, next_cite = cached
        debug_info["cache_hit"] = True
        debug_info["picked_provider"] = str(cached_item.get("provider") or "")
        debug_info["picked_total_score"] = float(cached_item.get("score") or 0.0)
        debug_info["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
        return cached_item, next_cite, debug_info

    query = _build_citation_verify_query(cite)
    debug_info["query"] = query
    if not query:
        item["reason"] = "missing_title"
        _citation_verify_cache_set(cite, item, cite)
        debug_info["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
        return item, cite, debug_info

    candidates, errors = _collect_citation_candidates(query)
    if errors:
        debug_info["errors"] = list(errors[:4])
    for provider, _ in candidates:
        if provider in debug_info["providers"]:
            debug_info["providers"][provider] += 1
        else:
            debug_info["providers"][provider] = 1

    if not candidates:
        if errors:
            item["provider"] = "openalex+crossref"
            item["status"] = "error"
            item["reason"] = f"search_error:{'|'.join(errors[:2])}"
            debug_info["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
            return item, cite, debug_info
        item["provider"] = "openalex+crossref"
        item["reason"] = "no_result"
        _citation_verify_cache_set(cite, item, cite)
        debug_info["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
        return item, cite, debug_info

    provider, best_work, best_score, best_title_score, best_year_score = _pick_best_citation_candidate(cite, candidates)
    debug_info["picked_provider"] = provider or ""
    debug_info["picked_title_score"] = round(float(best_title_score), 4)
    debug_info["picked_year_score"] = round(float(best_year_score), 4)
    debug_info["picked_total_score"] = round(float(best_score), 4)
    if best_work is None:
        if errors:
            item["provider"] = "openalex+crossref"
            item["status"] = "error"
            item["reason"] = f"search_error:{'|'.join(errors[:2])}"
            debug_info["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
            return item, cite, debug_info
        item["provider"] = "openalex+crossref"
        item["reason"] = "no_result"
        _citation_verify_cache_set(cite, item, cite)
        debug_info["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
        return item, cite, debug_info

    matched_title = _normalize_citation_text(getattr(best_work, "title", ""))
    matched_year = _extract_citation_year(getattr(best_work, "published", ""))
    matched_source = _citation_work_source(best_work)
    matched_url = _normalize_citation_text(getattr(best_work, "abs_url", ""))
    matched_doi = _normalize_citation_text(getattr(best_work, "doi", ""))

    status = "not_found"
    reason = "low_confidence_match"
    if best_title_score >= 0.88 and best_score >= 0.82 and (not cite.year or best_year_score >= 0.35):
        status = "verified"
        reason = "high_confidence_match"
    elif best_title_score >= 0.72 and best_score >= 0.60:
        status = "possible"
        reason = "partial_match"

    item.update(
        {
            "status": status,
            "provider": provider or "openalex+crossref",
            "score": round(max(0.0, best_score), 3),
            "reason": reason,
            "matched_title": matched_title if best_score >= 0.50 else "",
            "matched_year": matched_year if best_score >= 0.50 else "",
            "matched_source": matched_source if best_score >= 0.50 else "",
            "doi": matched_doi if best_score >= 0.50 else "",
            "url": matched_url if best_score >= 0.50 else "",
        }
    )

    if status not in {"verified", "possible"}:
        _citation_verify_cache_set(cite, item, cite)
        debug_info["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
        return item, cite, debug_info

    next_cite = Citation(
        key=cite.key,
        title=matched_title if (status == "verified" and matched_title) else (cite.title or matched_title or ""),
        url=cite.url or (matched_url or None),
        authors=cite.authors
        or (", ".join([a for a in (getattr(best_work, "authors", []) or [])[:5]]) or None),
        year=cite.year or (matched_year or None),
        venue=cite.venue or (matched_source or None),
    )
    _citation_verify_cache_set(cite, item, next_cite)
    debug_info["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
    return item, next_cite, debug_info



def install(namespace: dict) -> None:
    bind(namespace)
    _sync_state_to_namespace(namespace)
    for fn_name, fn in list(globals().items()):
        if fn_name in {
            "bind",
            "install",
            "_proxy_factory",
            "_sync_state_from_namespace",
            "_sync_state_to_namespace",
            "_is_state_key",
        }:
            continue
        if fn_name.startswith("_") and callable(fn) and str(getattr(fn, "__module__", "")) == __name__:
            _ORIGINAL_FUNCS.setdefault(fn_name, fn)
            namespace[fn_name] = _proxy_factory(fn_name, namespace)
