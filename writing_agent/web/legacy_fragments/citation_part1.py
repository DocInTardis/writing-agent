"""Citation verify/runtime compatibility shims for app_v2."""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from collections import OrderedDict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from writing_agent.models import Citation
from writing_agent.web.domains import citation_alert_domain


def _clean(value: object) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _year(value: object) -> str:
    m = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return m.group(0) if m else ""


def _doi(value: object) -> str:
    raw = _clean(value).lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    m = re.search(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+\b", raw)
    return str(m.group(0)).rstrip(").,;:") if m else ""


def _work_title(work: object) -> str:
    return _clean(getattr(work, "title", ""))


def _work_authors(work: object) -> list[str]:
    rows = getattr(work, "authors", []) or []
    return [_clean(row) for row in rows if _clean(row)][:5]


def _work_year(work: object) -> str:
    return _year(getattr(work, "published", ""))


def _work_source(work: object) -> str:
    source = _clean(getattr(work, "primary_category", ""))
    if source:
        return source
    rows = getattr(work, "categories", []) or []
    if isinstance(rows, list):
        for row in rows:
            clean = _clean(row)
            if clean:
                return clean
    return ""


def _work_url(work: object) -> str:
    return _clean(getattr(work, "abs_url", ""))


def _work_doi(work: object) -> str:
    return _doi(getattr(work, "doi", "")) or _doi(_work_url(work))


def _norm_title(value: object) -> str:
    return re.sub(r"[^0-9a-z]+", " ", str(value or "").lower()).strip()


def _author_key(value: object) -> str:
    raw = _clean(value).lower()
    first = re.split(r"[,;]| and ", raw, flags=re.IGNORECASE)[0].strip()
    tokens = [tok for tok in re.split(r"[^a-z0-9]+", first) if tok]
    return tokens[-1] if tokens else ""


def _score_candidate(cite: Citation, work: object) -> tuple[float, dict]:
    cite_title = _norm_title(cite.title)
    work_title = _norm_title(_work_title(work))
    title_score = SequenceMatcher(None, cite_title, work_title).ratio() if cite_title and work_title else 0.0
    cite_year = _year(cite.year)
    work_year = _work_year(work)
    year_score = 1.0 if cite_year and work_year and cite_year == work_year else (0.5 if not cite_year or not work_year else 0.0)
    cite_author = _author_key(cite.authors)
    work_author = _author_key(";".join(_work_authors(work)))
    author_score = 1.0 if cite_author and work_author and cite_author == work_author else (0.5 if not cite_author or not work_author else 0.0)
    total = 0.72 * title_score + 0.18 * year_score + 0.10 * author_score
    return total, {
        "title_score": round(title_score, 4),
        "year_score": round(year_score, 4),
        "author_score": round(author_score, 4),
        "total_score": round(total, 4),
    }


def _int_env(name: str, default: int, *, low: int = 0, high: int = 1_000_000) -> int:
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except Exception:
        value = default
    return max(low, min(high, value))


def _float_env(name: str, default: float, *, low: float = 0.0, high: float = 1_000_000.0) -> float:
    try:
        value = float(str(os.environ.get(name, default)).strip())
    except Exception:
        value = default
    return max(low, min(high, value))


def _bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _read_json(path: Path, default: object) -> object:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _percentile(values: list[float], q: float) -> float:
    vals = sorted([float(v) for v in values if math.isfinite(float(v))])
    if not vals:
        return 0.0
    idx = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * q))))
    return vals[idx]


def _sanitize_text(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[email]", text)
    text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-[redacted]", text)
    text = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[redacted]", text)
    text = re.sub(r"(token=)[^&\s]+", r"\1[redacted]", text, flags=re.IGNORECASE)
    return text


def install(g: dict) -> None:
    g.setdefault("_CITATION_VERIFY_CACHE", {})
    g.setdefault("_CITATION_VERIFY_CACHE_METRICS", {"hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0})
    g.setdefault("_CITATION_VERIFY_OBSERVE_RUNS", [])
    g.setdefault("_DEBUG_FULL_RATE_BUCKETS", {})
    g.setdefault("_CITATION_VERIFY_CACHE_CLOCK", 0)

    def _cache_metrics() -> dict:
        metrics = g.setdefault(
            "_CITATION_VERIFY_CACHE_METRICS",
            {"hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0},
        )
        for key in ("hit", "miss", "set", "expired", "evicted"):
            metrics.setdefault(key, 0)
        return metrics

    def _citation_verify_cache_key(cite: Citation) -> str:
        return "|".join([
            _norm_title(cite.title),
            _clean(cite.authors).lower(),
            _year(cite.year),
            _doi(cite.url),
        ])

    def _citation_verify_cache_max_entries() -> int:
        return _int_env("WRITING_AGENT_CITATION_VERIFY_CACHE_MAX_ENTRIES", 2048, low=1, high=100_000)

    def _citation_verify_cache_ttl_s() -> float:
        return _float_env("WRITING_AGENT_CITATION_VERIFY_CACHE_TTL_S", 3600.0, low=1.0, high=30 * 24 * 3600.0)

    def _citation_verify_cache_get(cite: Citation):
        cache = g.setdefault("_CITATION_VERIFY_CACHE", {})
        metrics = _cache_metrics()
        key = _citation_verify_cache_key(cite)
        row = cache.get(key)
        now = g["time"].time()
        if not isinstance(row, dict):
            metrics["miss"] += 1
            return None
        if now - float(row.get("ts") or 0.0) > _citation_verify_cache_ttl_s():
            cache.pop(key, None)
            metrics["miss"] += 1
            metrics["expired"] += 1
            return None
        g["_CITATION_VERIFY_CACHE_CLOCK"] = int(g.get("_CITATION_VERIFY_CACHE_CLOCK") or 0) + 1
        row["last_access"] = g["_CITATION_VERIFY_CACHE_CLOCK"]
        metrics["hit"] += 1
        return row.get("item"), row.get("updated")

    def _citation_verify_cache_set(cite: Citation, item: dict, updated: Citation) -> None:
        cache = g.setdefault("_CITATION_VERIFY_CACHE", {})
        metrics = _cache_metrics()
        key = _citation_verify_cache_key(cite)
        g["_CITATION_VERIFY_CACHE_CLOCK"] = int(g.get("_CITATION_VERIFY_CACHE_CLOCK") or 0) + 1
        cache[key] = {
            "ts": g["time"].time(),
            "last_access": g["_CITATION_VERIFY_CACHE_CLOCK"],
            "item": dict(item),
            "updated": updated,
        }
        metrics["set"] += 1
        max_entries = _citation_verify_cache_max_entries()
        while len(cache) > max_entries:
            oldest = min(cache.items(), key=lambda kv: float((kv[1] or {}).get("last_access") or 0.0))[0]
            cache.pop(oldest, None)
            metrics["evicted"] += 1

    def _citation_verify_cache_snapshot() -> dict:
        cache = g.setdefault("_CITATION_VERIFY_CACHE", {})
        metrics = _cache_metrics()
        return {
            "size": len(cache),
            "ttl_s": _citation_verify_cache_ttl_s(),
            "max_entries": _citation_verify_cache_max_entries(),
            **{key: int(metrics.get(key) or 0) for key in ("hit", "miss", "set", "expired", "evicted")},
        }

    def _citation_verify_cache_metrics_snapshot() -> dict:
        return {key: int(_cache_metrics().get(key) or 0) for key in ("hit", "miss", "set", "expired", "evicted")}

    def _citation_payload(cite: Citation) -> dict:
        return {
            "id": cite.key,
            "author": cite.authors or "",
            "title": cite.title or "",
            "year": cite.year or "",
            "source": cite.venue or cite.url or "",
            "url": cite.url or "",
        }

    def _normalize_citation_items(items: object) -> dict[str, Citation]:
        out: dict[str, Citation] = {}
        rows = items if isinstance(items, list) else []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            key = _clean(row.get("id") or row.get("key") or f"cite_{idx}")
            title = _clean(row.get("title"))
            if not key or not title:
                continue
            out[key] = Citation(
                key=key,
                title=title,
                authors=_clean(row.get("author") or row.get("authors")) or None,
                year=_year(row.get("year")) or None,
                venue=_clean(row.get("source") or row.get("venue")) or None,
                url=_clean(row.get("url")) or None,
            )
        return out

    def _collect_citation_candidates(query: str):
        rows: list[tuple[str, object]] = []
        errors: list[str] = []
        q = _clean(query)
        if not q:
            return rows, errors
        for provider, fn_name in (("openalex", "search_openalex"), ("crossref", "search_crossref")):
            try:
                result = g[fn_name](query=q, max_results=8, timeout_s=12.0)
                works = getattr(result, "works", []) or []
                rows.extend((provider, work) for work in works)
            except Exception as exc:
                errors.append(f"{provider}:{exc.__class__.__name__}")
        return rows, errors

    def _pick_best_citation_candidate(cite: Citation, candidates: list[tuple[str, object]]):
        best = ("", None, 0.0, {}, [])
        for provider, work in candidates:
            score, parts = _score_candidate(cite, work)
            if score > float(best[2] or 0.0):
                best = (provider, work, score, parts, [])
        return best

    def _query_for_cite(cite: Citation) -> str:
        return _clean(" ".join([cite.title or "", cite.authors or "", cite.year or ""]))

    def _item_from_match(cite: Citation, provider: str, work: object, score: float, reason: str = "") -> dict:
        return {
            "id": cite.key,
            "author": cite.authors or "",
            "title": cite.title or "",
            "year": cite.year or "",
            "source": cite.venue or cite.url or "",
            "status": "verified" if score >= 0.82 else ("possible" if score >= 0.65 else "not_found"),
            "provider": provider or "",
            "score": round(max(0.0, min(1.0, float(score or 0.0))), 4),
            "matched_title": _work_title(work),
            "matched_year": _work_year(work),
            "matched_source": _work_source(work),
            "doi": _work_doi(work),
            "url": _work_url(work),
            "reason": reason,
        }

    def _updated_citation(cite: Citation, item: dict) -> Citation:
        if str(item.get("status") or "") not in {"verified", "possible"}:
            return cite
        return Citation(
            key=cite.key,
            title=str(item.get("matched_title") or cite.title or ""),
            authors=cite.authors,
            year=str(item.get("matched_year") or cite.year or "") or None,
            venue=str(item.get("matched_source") or cite.venue or "") or None,
            url=str(item.get("url") or cite.url or "") or None,
        )

    def _verify_one_citation_detail(cite: Citation):
        started = g["time"].perf_counter()
        cached = _citation_verify_cache_get(cite)
        if cached is not None:
            item, updated = cached
            debug = {
                "cache_hit": True,
                "query": _query_for_cite(cite),
                "providers": {},
                "errors": [],
                "picked_provider": str((item or {}).get("provider") or ""),
                "picked_total_score": float((item or {}).get("score") or 0.0),
                "elapsed_ms": round((g["time"].perf_counter() - started) * 1000.0, 2),
            }
            return dict(item or {}), updated if isinstance(updated, Citation) else cite, debug

        query = _query_for_cite(cite)
        candidates, errors = _collect_citation_candidates(query)
        providers: dict[str, int] = {}
        for provider, _work in candidates:
            providers[provider] = providers.get(provider, 0) + 1
        provider, work, score, parts, _ = _pick_best_citation_candidate(cite, candidates)
        if work is not None and float(score) >= 0.65:
            item = _item_from_match(cite, provider, work, float(score))
            updated = _updated_citation(cite, item)
        elif errors:
            item = {
                **_citation_payload(cite),
                "status": "error",
                "provider": "openalex+crossref",
                "score": 0.0,
                "matched_title": "",
                "matched_year": "",
                "matched_source": "",
                "doi": "",
                "reason": f"search_error:{'|'.join(errors[:3])}",
            }
            updated = cite
        elif work is not None:
            item = _item_from_match(cite, provider, work, float(score), reason="low_confidence_match")
            item["status"] = "not_found"
            updated = cite
        else:
            item = {
                **_citation_payload(cite),
                "status": "not_found",
                "provider": "",
                "score": 0.0,
                "matched_title": "",
                "matched_year": "",
                "matched_source": "",
                "doi": "",
                "reason": "no_candidate",
            }
            updated = cite
        debug = {
            "cache_hit": False,
            "query": query,
            "providers": providers,
            "errors": errors,
            "picked_provider": provider,
            "picked_title_score": float((parts or {}).get("title_score") or 0.0),
            "picked_year_score": float((parts or {}).get("year_score") or 0.0),
            "picked_total_score": float((parts or {}).get("total_score") or score or 0.0),
            "elapsed_ms": round((g["time"].perf_counter() - started) * 1000.0, 2),
        }
        _citation_verify_cache_set(cite, item, updated)
        return item, updated, debug

    def _verify_one_citation(cite: Citation):
        item, updated, _debug = g["_verify_one_citation_detail"](cite)
        return item, updated

    def _citation_verify_max_workers(item_count: int) -> int:
        count = max(1, int(item_count or 1))
        raw = _int_env("WRITING_AGENT_CITATION_VERIFY_MAX_WORKERS", 4, low=1, high=64)
        return max(1, min(count, raw))

    def _citation_verify_effective_workers(item_count: int) -> int:
        count = max(1, int(item_count or 1))
        base = _citation_verify_max_workers(count)
        if not _bool_env("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_WORKERS", False):
            return base
        try:
            snap = g["_citation_verify_observe_snapshot"](include_recent=False)
        except Exception:
            return base
        if int((snap or {}).get("runs") or 0) < 5:
            return base
        elapsed = snap.get("elapsed_ms") if isinstance(snap.get("elapsed_ms"), dict) else {}
        errors = snap.get("errors") if isinstance(snap.get("errors"), dict) else {}
        p95 = float(elapsed.get("p95") or 0.0)
        err = float(errors.get("rate_per_run") or 0.0)
        if p95 >= 4000.0 or err >= 0.20:
            step = _int_env("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_REDUCE_STEP", 1, low=1, high=32)
            return max(1, min(count, base - step))
        if p95 <= 1800.0 and err <= 0.05:
            step = _int_env("WRITING_AGENT_CITATION_VERIFY_ADAPTIVE_BOOST_STEP", 1, low=1, high=32)
            return max(1, min(count, base + step))
        return base

    def _verify_citation_batch(source_citations: dict[str, Citation], *, debug_enabled: bool = False):
        results: list[dict] = []
        updated: dict[str, Citation] = {}
        debug_items: list[dict] = []
        items = list((source_citations or {}).items())
        workers = _citation_verify_effective_workers(len(items)) if items else 0
        for key, cite in items:
            try:
                if debug_enabled:
                    item, new_cite, debug = g["_verify_one_citation_detail"](cite)
                else:
                    item, new_cite = g["_verify_one_citation"](cite)
                    debug = {}
            except Exception as exc:
                item = {**_citation_payload(cite), "status": "error", "provider": "", "score": 0.0, "reason": exc.__class__.__name__}
                new_cite = cite
                debug = {"cache_hit": False, "query": _query_for_cite(cite), "providers": {}, "errors": [exc.__class__.__name__]}
            results.append(item)
            updated[str(key)] = new_cite
            if debug_enabled:
                debug_items.append(debug)
        return results, updated, debug_items, workers

    def _normalize_verify_debug_level(raw: object) -> str:
        value = str(raw or "safe").strip().lower()
        if value == "raw":
            return "full"
        if value in {"full", "safe", "strict"}:
            return value
        return "safe"

    def _allow_full_debug(doc_id: str) -> bool:
        buckets = g.setdefault("_DEBUG_FULL_RATE_BUCKETS", {})
        now = g["time"].time()
        floor = now - 60.0
        max_per_min = _int_env("WRITING_AGENT_CITATION_VERIFY_DEBUG_FULL_MAX_PER_MIN", 4, low=1, high=1000)
        max_keys = _int_env("WRITING_AGENT_CITATION_VERIFY_DEBUG_FULL_MAX_KEYS", 128, low=1, high=10000)
        for key in list(buckets.keys()):
            rows = [float(ts) for ts in (buckets.get(key) or []) if float(ts) >= floor]
            if rows:
                buckets[key] = rows
            else:
                buckets.pop(key, None)
        key = str(doc_id or "global")
        rows = [float(ts) for ts in (buckets.get(key) or []) if float(ts) >= floor]
        allowed = len(rows) < max_per_min
        if allowed:
            rows.append(now)
            buckets[key] = rows
        while len(buckets) > max_keys:
            candidates = [k for k in buckets.keys() if k != key] or list(buckets.keys())
            oldest = min(candidates, key=lambda k: min(buckets.get(k) or [now]))
            buckets.pop(oldest, None)
        return allowed

    def _debug_sample_limit() -> int:
        return _int_env("WRITING_AGENT_CITATION_VERIFY_DEBUG_ITEM_SAMPLE_LIMIT", 20, low=0, high=10000)

    def _debug_item_for_level(row: dict, level: str) -> dict:
        item = dict(row or {})
        if level == "full":
            return item
        if level == "strict":
            item["query"] = ""
            item["errors"] = []
            return item
        if "query" in item:
            item["query"] = _sanitize_text(item.get("query"))
        if isinstance(item.get("errors"), list):
            item["errors"] = [_sanitize_text(x) for x in item.get("errors")]
        return item

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
        request_observe: dict,
        observe_snapshot: dict,
    ) -> dict:
        limit = _debug_sample_limit()
        sampled = list(debug_items or [])[:limit]
        items = [_debug_item_for_level(row, debug_level) for row in sampled]
        return {
            "requested_level": requested_level,
            "level": debug_level,
            "sanitized": debug_level != "full",
            "rate_limited_full": bool(rate_limited_full),
            "persist": bool(persist),
            "elapsed_ms": float(elapsed_ms or 0.0),
            "items": items,
            "sampling": {
                "input_items": int(input_count or 0),
                "output_items": len(items),
                "limit": limit,
                "truncated": len(debug_items or []) > limit,
            },
            "request": {"items": int(input_count or 0), "workers": int(worker_count or 0)},
            "cache": _citation_verify_cache_snapshot(),
            "observe": {"request": request_observe or {}, "window": observe_snapshot or {}},
        }

    def _cache_delta(before: dict, after: dict) -> dict:
        out = {}
        for key in ("hit", "miss", "set", "expired", "evicted"):
            out[key] = max(0, int((after or {}).get(key) or 0) - int((before or {}).get(key) or 0))
        lookups = out["hit"] + out["miss"]
        out["hit_rate"] = round((out["hit"] / lookups), 4) if lookups else 0.0
        return out

    def _safe_nonneg_int(value: object) -> int:
        try:
            return max(0, int(float(value or 0)))
        except Exception:
            return 0

    def _citation_verify_observe_window_s() -> float:
        return _float_env("WRITING_AGENT_CITATION_VERIFY_OBSERVE_WINDOW_S", 1800.0, low=1.0, high=7 * 24 * 3600.0)

    def _citation_verify_observe_max_runs() -> int:
        return _int_env("WRITING_AGENT_CITATION_VERIFY_OBSERVE_MAX_RUNS", 240, low=1, high=100000)

    def _citation_verify_observe_prune_locked(*, now: float | None = None) -> None:
        rows = g.setdefault("_CITATION_VERIFY_OBSERVE_RUNS", [])
        now_value = g["time"].time() if now is None else float(now)
        floor = now_value - _citation_verify_observe_window_s()
        clean_rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                ts = float(row.get("ts"))
            except Exception:
                continue
            if ts >= floor:
                clean_rows.append(row)
        max_runs = _citation_verify_observe_max_runs()
        g["_CITATION_VERIFY_OBSERVE_RUNS"] = clean_rows[-max_runs:]

    def _citation_verify_observe_record(
        *,
        elapsed_ms: float,
        item_count: int,
        worker_count: int,
        error_count: int,
        cache_before: dict,
        cache_after: dict,
    ) -> dict:
        _citation_verify_observe_prune_locked()
        row = {
            "ts": g["time"].time(),
            "elapsed_ms": float(elapsed_ms or 0.0),
            "item_count": int(item_count or 0),
            "worker_count": int(worker_count or 0),
            "error_count": int(error_count or 0),
            "cache_delta": _cache_delta(cache_before, cache_after),
        }
        rows = g.setdefault("_CITATION_VERIFY_OBSERVE_RUNS", [])
        rows.append(row)
        g["_CITATION_VERIFY_OBSERVE_RUNS"] = rows[-_citation_verify_observe_max_runs():]
        return row

    def _citation_verify_observe_snapshot(*, include_recent: bool = True) -> dict:
        _citation_verify_observe_prune_locked()
        rows = [row for row in g.setdefault("_CITATION_VERIFY_OBSERVE_RUNS", []) if isinstance(row, dict)]
        elapsed: list[float] = []
        item_counts: list[float] = []
        workers: list[float] = []
        error_total = 0
        cache_total = {"hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0}
        recent: list[dict] = []
        for row in rows:
            try:
                elapsed.append(max(0.0, float(row.get("elapsed_ms") or 0.0)))
                item_counts.append(max(0.0, float(row.get("item_count") or 0.0)))
                workers.append(max(0.0, float(row.get("worker_count") or 0.0)))
                error_total += max(0, int(float(row.get("error_count") or 0.0)))
            except Exception:
                pass
            delta = row.get("cache_delta") if isinstance(row.get("cache_delta"), dict) else {}
            for key in cache_total:
                try:
                    cache_total[key] += max(0, int(float(delta.get(key) or 0.0)))
                except Exception:
                    pass
            if include_recent:
                recent_delta = dict(delta)
                for key in ("hit", "miss", "set", "expired", "evicted"):
                    recent_delta[key] = _safe_nonneg_int(recent_delta.get(key))
                lookups = int(recent_delta.get("hit") or 0) + int(recent_delta.get("miss") or 0)
                recent_delta["hit_rate"] = round((int(recent_delta.get("hit") or 0) / lookups), 4) if lookups else 0.0
                recent.append({**row, "cache_delta": recent_delta})
        lookups = cache_total["hit"] + cache_total["miss"]
        cache_total["hit_rate"] = round((cache_total["hit"] / lookups), 4) if lookups else 0.0
        runs = len(rows)
        return {
            "window_s": _citation_verify_observe_window_s(),
            "max_runs": _citation_verify_observe_max_runs(),
            "runs": runs,
            "elapsed_ms": {
                "avg": round(sum(elapsed) / runs, 4) if runs else 0.0,
                "p50": _percentile(elapsed, 0.50),
                "p95": _percentile(elapsed, 0.95),
                "max": max(elapsed) if elapsed else 0.0,
            },
            "items": {
                "total": int(sum(item_counts)),
                "avg": round(sum(item_counts) / runs, 4) if runs else 0.0,
                "p50": _percentile(item_counts, 0.50),
                "p95": _percentile(item_counts, 0.95),
                "max": int(max(item_counts)) if item_counts else 0,
            },
            "workers": {
                "avg": round(sum(workers) / runs, 4) if runs else 0.0,
                "max": int(max(workers)) if workers else 0,
            },
            "errors": {"total": error_total, "rate_per_run": round(error_total / runs, 4) if runs else 0.0},
            "cache_delta": cache_total,
            "recent": recent[-20:] if include_recent else [],
        }

    def _citation_verify_cache_snapshot_fallback() -> dict:
        return {"size": 0, "ttl_s": _citation_verify_cache_ttl_s(), "max_entries": _citation_verify_cache_max_entries(), "hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0}

    def _citation_verify_observe_snapshot_fallback() -> dict:
        return citation_alert_domain.citation_verify_observe_snapshot_fallback(
            window_s=_citation_verify_observe_window_s(),
            max_runs=_citation_verify_observe_max_runs(),
        )

    def _citation_verify_alerts_config_env() -> dict:
        return {
            "enabled": _bool_env("WRITING_AGENT_CITATION_VERIFY_ALERTS", False),
            "min_runs": _int_env("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", 5, low=1, high=100000),
            "p95_ms": _float_env("WRITING_AGENT_CITATION_VERIFY_ALERT_P95_MS", 4000.0, low=1.0),
            "error_rate_per_run": _float_env("WRITING_AGENT_CITATION_VERIFY_ALERT_ERROR_RATE", 0.25, low=0.0, high=1.0),
            "cache_delta_hit_rate": _float_env("WRITING_AGENT_CITATION_VERIFY_ALERT_HIT_RATE", 0.25, low=0.0, high=1.0),
            "notify_enabled": _bool_env("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY", False),
            "webhook_url": _clean(os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL", "")),
            "notify_cooldown_s": _float_env("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_COOLDOWN_S", 300.0, low=0.0),
            "notify_timeout_s": _float_env("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_TIMEOUT_S", 5.0, low=0.1, high=60.0),
        }

    def _normalize_alerts_config(raw: dict) -> dict:
        base = _citation_verify_alerts_config_env()
        src = raw if isinstance(raw, dict) else {}
        out = dict(base)
        for key in ("enabled", "notify_enabled"):
            if key in src:
                out[key] = bool(src.get(key))
        aliases = {"p95_ms": "p95_ms", "error_rate_per_run": "error_rate_per_run", "cache_delta_hit_rate": "cache_delta_hit_rate", "min_runs": "min_runs"}
        for key in aliases:
            if key in src:
                out[key] = src.get(key)
        for key in ("webhook_url",):
            if key in src:
                out[key] = _clean(src.get(key))
        for key in ("notify_cooldown_s", "notify_timeout_s"):
            if key in src:
                out[key] = src.get(key)
        out["min_runs"] = max(1, int(float(out.get("min_runs") or 1)))
        out["p95_ms"] = max(1.0, float(out.get("p95_ms") or 1.0))
        out["error_rate_per_run"] = max(0.0, min(1.0, float(out.get("error_rate_per_run") or 0.0)))
        out["cache_delta_hit_rate"] = max(0.0, min(1.0, float(out.get("cache_delta_hit_rate") or 0.0)))
        out["notify_cooldown_s"] = max(0.0, float(out.get("notify_cooldown_s") or 0.0))
        out["notify_timeout_s"] = max(0.1, float(out.get("notify_timeout_s") or 5.0))
        return out

    def _citation_verify_alerts_config_path() -> Path:
        return Path(g.get("_CITATION_VERIFY_ALERTS_CONFIG_PATH"))

    def _citation_verify_alerts_config_effective() -> dict:
        path = _citation_verify_alerts_config_path()
        raw = _read_json(path, None)
        if isinstance(raw, dict):
            return _normalize_alerts_config(raw)
        return _citation_verify_alerts_config_env()

    def _citation_verify_alerts_config_source() -> str:
        return "file" if _citation_verify_alerts_config_path().exists() else "env"

    def _citation_verify_alerts_config_save(payload: dict) -> dict:
        cfg = _normalize_alerts_config(payload if isinstance(payload, dict) else {})
        _write_json(_citation_verify_alerts_config_path(), cfg)
        return cfg

    def _citation_verify_alerts_config_reset() -> dict:
        try:
            _citation_verify_alerts_config_path().unlink(missing_ok=True)
        except Exception:
            pass
        return _citation_verify_alerts_config_env()

    def _event_path() -> Path:
        return Path(g.get("_CITATION_VERIFY_ALERT_EVENTS_PATH"))

    def _citation_verify_alert_events_append(row: dict) -> dict:
        events = _read_json(_event_path(), [])
        events = events if isinstance(events, list) else []
        event = dict(row or {})
        event.setdefault("id", uuid.uuid4().hex)
        event.setdefault("ts", g["time"].time())
        events.append(event)
        events = events[-1000:]
        _write_json(_event_path(), events)
        return event

    def _citation_verify_alert_events_snapshot(*, limit: int = 50) -> dict:
        events = _read_json(_event_path(), [])
        events = events if isinstance(events, list) else []
        lim = max(1, min(1000, int(limit or 50)))
        return {"limit": lim, "total": len(events), "events": events[-lim:]}

    def _citation_verify_alert_event_get(event_id: str) -> dict | None:
        target = str(event_id or "")
        for row in (_read_json(_event_path(), []) or []):
            if isinstance(row, dict) and str(row.get("id") or "") == target:
                return row
        return None

    def _citation_verify_alert_notify_state_reset() -> None:
        state = g.get("_CITATION_VERIFY_ALERT_NOTIFY_STATE")
        if isinstance(state, dict):
            state.clear()
            state.update({"severity": "ok", "signature": "", "last_sent_at": 0.0, "suppressed": 0, "last_error": "", "last_event_type": "", "last_event_id": ""})

    def _alert_notify_webhook(url: str, payload: dict, timeout_s: float):
        return False, "webhook_unavailable"

    def _trend_enabled() -> bool:
        return _bool_env("WRITING_AGENT_CITATION_VERIFY_TREND_ENABLED", False)

    def _trend_path() -> Path:
        return Path(g.get("_CITATION_VERIFY_METRICS_TRENDS_PATH"))

    def _trend_rows() -> list[dict]:
        cache_path = str(g.get("_CITATION_VERIFY_METRICS_TRENDS_CACHE_PATH") or "")
        path = _trend_path()
        rows = g.get("_CITATION_VERIFY_METRICS_TRENDS_CACHE_ROWS")
        if isinstance(rows, list) and cache_path == str(path):
            return rows
        raw = _read_json(path, {"points": []})
        loaded = raw.get("points") if isinstance(raw, dict) and isinstance(raw.get("points"), list) else []
        g["_CITATION_VERIFY_METRICS_TRENDS_CACHE_ROWS"] = loaded
        g["_CITATION_VERIFY_METRICS_TRENDS_CACHE_PATH"] = str(path)
        return loaded

    def _flush_trends(force: bool = False) -> None:
        rows = _trend_rows()
        if not _trend_enabled():
            return
        now = g["time"].time()
        interval = _float_env("WRITING_AGENT_CITATION_VERIFY_TREND_FLUSH_INTERVAL_S", 30.0, low=0.0)
        last = float(g.get("_CITATION_VERIFY_METRICS_TRENDS_LAST_WRITE_AT") or 0.0)
        if force or last <= 0.0 or (now - last) >= interval:
            _write_json(_trend_path(), {"points": rows})
            g["_CITATION_VERIFY_METRICS_TRENDS_LAST_WRITE_AT"] = now
            g["_CITATION_VERIFY_METRICS_TRENDS_DIRTY"] = False
        else:
            g["_CITATION_VERIFY_METRICS_TRENDS_DIRTY"] = True

    def _citation_verify_metrics_trend_append(point: dict) -> None:
        if not _trend_enabled():
            return
        rows = _trend_rows()
        row = dict(point or {})
        row.setdefault("id", uuid.uuid4().hex)
        row.setdefault("ts", g["time"].time())
        rows.append(row)
        g["_CITATION_VERIFY_METRICS_TRENDS_CACHE_ROWS"] = rows[-5000:]
        _flush_trends(force=False)

    def _citation_verify_metrics_trends_snapshot(*, limit: int = 120) -> dict:
        rows = _trend_rows() if _trend_enabled() else []
        lim = max(1, min(5000, int(limit or 120)))
        return {"enabled": _trend_enabled(), "total": len(rows), "limit": lim, "points": rows[-lim:]}

    def _citation_verify_metrics_trend_context(*, ts: float, limit: int = 12) -> dict:
        rows = _trend_rows() if _trend_enabled() else []
        lim = max(1, min(5000, int(limit or 12)))
        return {"enabled": _trend_enabled(), "total": len(rows), "limit": lim, "points": rows[-lim:]}

    def _build_citation_verify_alerts_payload(degraded: bool, errors: list[str], observe: dict) -> dict:
        cfg = _citation_verify_alerts_config_effective()
        return citation_alert_domain.build_citation_verify_alerts_payload(
            degraded=bool(degraded),
            errors=list(errors or []),
            observe=observe if isinstance(observe, dict) else {},
            alerts_enabled=bool(cfg.get("enabled")),
            min_runs=int(cfg.get("min_runs") or 1),
            threshold_p95=float(cfg.get("p95_ms") or 0.0),
            threshold_error_rate=float(cfg.get("error_rate_per_run") or 0.0),
            threshold_hit_rate=float(cfg.get("cache_delta_hit_rate") or 0.0),
            log_info=g["logger"].info,
        )

    def _citation_verify_alerts_fallback() -> dict:
        cfg = _citation_verify_alerts_config_effective()
        return citation_alert_domain.citation_verify_alerts_fallback(
            min_runs=int(cfg.get("min_runs") or 1),
            threshold_p95=float(cfg.get("p95_ms") or 0.0),
            threshold_error_rate=float(cfg.get("error_rate_per_run") or 0.0),
            threshold_hit_rate=float(cfg.get("cache_delta_hit_rate") or 0.0),
        )

    def _maybe_notify_citation_verify_alerts(alerts: dict, degraded: bool, errors: list[str]) -> dict:
        cfg = _citation_verify_alerts_config_effective()
        release_ctx = citation_alert_domain.citation_verify_release_context(
            correlation_id=str(os.environ.get("WRITING_AGENT_CORRELATION_ID", "")),
            release_candidate_id=str(os.environ.get("WRITING_AGENT_RELEASE_CANDIDATE_ID", "")),
        )
        hooks = citation_alert_domain.CitationAlertNotifyHooks(
            append_event=_citation_verify_alert_events_append,
            events_snapshot=_citation_verify_alert_events_snapshot,
            alert_notify_webhook=lambda url, payload, timeout_s: g["_alert_notify_webhook"](url, payload, timeout_s=timeout_s),
            log_info=g["logger"].info,
            log_warn=g["logger"].warning,
            log_error=g["logger"].error,
        )
        config = citation_alert_domain.CitationAlertNotifyConfig(
            notify_enabled=bool(cfg.get("notify_enabled")),
            webhook_url=str(cfg.get("webhook_url") or ""),
            cooldown_s=float(cfg.get("notify_cooldown_s") or 0.0),
            timeout_s=float(cfg.get("notify_timeout_s") or 5.0),
            release_ctx=release_ctx,
        )
        return citation_alert_domain.maybe_notify_citation_verify_alerts(
            alerts=alerts if isinstance(alerts, dict) else {},
            degraded=bool(degraded),
            errors=list(errors or []),
            config=config,
            hooks=hooks,
            notify_state=g["_CITATION_VERIFY_ALERT_NOTIFY_STATE"],
            notify_lock=g["_CITATION_VERIFY_ALERT_NOTIFY_LOCK"],
        )

    def _safe_citation_verify_metrics_payload() -> dict:
        return citation_alert_domain.safe_citation_verify_metrics_payload(
            cache_snapshot=lambda: g["_citation_verify_cache_snapshot"](),
            cache_snapshot_fallback=_citation_verify_cache_snapshot_fallback,
            observe_snapshot=lambda: g["_citation_verify_observe_snapshot"](),
            observe_snapshot_fallback_fn=_citation_verify_observe_snapshot_fallback,
            build_alerts_payload=lambda degraded, errors, observe: g["_build_citation_verify_alerts_payload"](degraded, errors, observe),
            alerts_fallback_fn=_citation_verify_alerts_fallback,
            maybe_notify_alerts=lambda alerts, degraded, errors: g["_maybe_notify_citation_verify_alerts"](alerts, degraded, errors),
            webhook_url=lambda: str(_citation_verify_alerts_config_effective().get("webhook_url") or ""),
            cooldown_s=lambda: float(_citation_verify_alerts_config_effective().get("notify_cooldown_s") or 0.0),
            append_trend_point=_citation_verify_metrics_trend_append,
            trend_snapshot=_citation_verify_metrics_trends_snapshot,
            log_warn=g["logger"].warning,
        )

    def _require_ops_permission(request, action: str) -> None:
        token = str(request.headers.get("X-Admin-Key") or request.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        admin_key = str(os.environ.get("WRITING_AGENT_ADMIN_API_KEY", "")).strip()
        if _bool_env("WRITING_AGENT_OPS_RBAC_ENABLED", False):
            if admin_key and token == admin_key:
                return
            policy_path = Path(os.environ.get("WRITING_AGENT_OPS_RBAC_POLICY", "security/ops_rbac_policy.json"))
            policy = _read_json(policy_path, {})
            roles = policy.get("roles") if isinstance(policy, dict) and isinstance(policy.get("roles"), dict) else {}
            principals = policy.get("principals") if isinstance(policy, dict) and isinstance(policy.get("principals"), list) else []
            role = ""
            for row in principals:
                if not isinstance(row, dict):
                    continue
                env_key = str(row.get("token_env") or "")
                if env_key and token and token == str(os.environ.get(env_key, "")):
                    role = str(row.get("role") or "")
                    break
            allowed = False
            raw_role = roles.get(role)
            perms = raw_role if isinstance(raw_role, list) else (raw_role.get("allow") if isinstance(raw_role, dict) else [])
            if isinstance(perms, list):
                allowed = "*" in perms or str(action) in [str(x) for x in perms]
            if not allowed:
                raise HTTPException(status_code=403, detail="forbidden")
            return
        if admin_key and token != admin_key:
            raise HTTPException(status_code=403, detail="forbidden")

    names = {
        "_citation_verify_cache_get": _citation_verify_cache_get,
        "_citation_verify_cache_set": _citation_verify_cache_set,
        "_citation_verify_cache_snapshot": _citation_verify_cache_snapshot,
        "_citation_verify_cache_metrics_snapshot": _citation_verify_cache_metrics_snapshot,
        "_citation_payload": _citation_payload,
        "_normalize_citation_items": _normalize_citation_items,
        "_collect_citation_candidates": _collect_citation_candidates,
        "_pick_best_citation_candidate": _pick_best_citation_candidate,
        "_verify_one_citation_detail": _verify_one_citation_detail,
        "_verify_one_citation": _verify_one_citation,
        "_verify_citation_batch": _verify_citation_batch,
        "_normalize_verify_debug_level": _normalize_verify_debug_level,
        "_allow_full_debug": _allow_full_debug,
        "_build_citation_verify_debug_payload": _build_citation_verify_debug_payload,
        "_citation_verify_max_workers": _citation_verify_max_workers,
        "_citation_verify_effective_workers": _citation_verify_effective_workers,
        "_citation_verify_observe_prune_locked": _citation_verify_observe_prune_locked,
        "_citation_verify_observe_record": _citation_verify_observe_record,
        "_citation_verify_observe_snapshot": _citation_verify_observe_snapshot,
        "_safe_citation_verify_metrics_payload": _safe_citation_verify_metrics_payload,
        "_citation_verify_alerts_config_effective": _citation_verify_alerts_config_effective,
        "_citation_verify_alerts_config_source": _citation_verify_alerts_config_source,
        "_citation_verify_alerts_config_save": _citation_verify_alerts_config_save,
        "_citation_verify_alerts_config_reset": _citation_verify_alerts_config_reset,
        "_citation_verify_alert_events_snapshot": _citation_verify_alert_events_snapshot,
        "_citation_verify_alert_event_get": _citation_verify_alert_event_get,
        "_citation_verify_alert_notify_state_reset": _citation_verify_alert_notify_state_reset,
        "_citation_verify_metrics_trends_snapshot": _citation_verify_metrics_trends_snapshot,
        "_citation_verify_metrics_trend_context": _citation_verify_metrics_trend_context,
        "_build_citation_verify_alerts_payload": _build_citation_verify_alerts_payload,
        "_maybe_notify_citation_verify_alerts": _maybe_notify_citation_verify_alerts,
        "_alert_notify_webhook": _alert_notify_webhook,
        "_require_ops_permission": _require_ops_permission,
    }
    g.update(names)
