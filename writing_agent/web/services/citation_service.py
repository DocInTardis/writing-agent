"""Citation Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request as UrlRequest, urlopen

from fastapi import Request

from writing_agent.models import Citation

from . import citation_resolve_alerts_domain as resolve_alerts_domain
from .base import app_v2_module

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", flags=re.IGNORECASE)
_ARXIV_RE = re.compile(r"\b(\d{4}\.\d{4,5}(?:v\d+)?)\b", flags=re.IGNORECASE)
_OPENALEX_WORK_RE = re.compile(r"\bW\d+\b", flags=re.IGNORECASE)
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", flags=re.IGNORECASE)
_META_ATTR_RE = re.compile(r"([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)")
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", flags=re.IGNORECASE | re.DOTALL)
_JSONLD_RE = re.compile(
    r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    flags=re.IGNORECASE | re.DOTALL,
)
_RESOLVE_METADATA_MAX_BYTES = 256 * 1024
_RESOLVE_TIMEOUT_S = 8.0
_RESOLVE_USER_AGENT = "writing-agent-studio/2.0 (+citation resolve-url)"
_as_bounded_int = resolve_alerts_domain._as_bounded_int
_as_bounded_float = resolve_alerts_domain._as_bounded_float
_coerce_bool = resolve_alerts_domain._coerce_bool
_resolve_alerts_config_path = resolve_alerts_domain._resolve_alerts_config_path
_resolve_alerts_env_defaults = resolve_alerts_domain._resolve_alerts_env_defaults
_normalize_resolve_alerts_config = resolve_alerts_domain._normalize_resolve_alerts_config
_resolve_alerts_config_reset_cache = resolve_alerts_domain._resolve_alerts_config_reset_cache
_resolve_alerts_config_load_from_disk_locked = resolve_alerts_domain._resolve_alerts_config_load_from_disk_locked
_resolve_alerts_config_effective = resolve_alerts_domain._resolve_alerts_config_effective
_resolve_alerts_config_source = resolve_alerts_domain._resolve_alerts_config_source
_resolve_alerts_config_save = resolve_alerts_domain._resolve_alerts_config_save
_resolve_alerts_config_reset = resolve_alerts_domain._resolve_alerts_config_reset
_resolve_observe_max_runs = resolve_alerts_domain._resolve_observe_max_runs
_resolve_observe_window_s = resolve_alerts_domain._resolve_observe_window_s
_resolve_alerts_enabled = resolve_alerts_domain._resolve_alerts_enabled
_resolve_alert_min_runs = resolve_alerts_domain._resolve_alert_min_runs
_resolve_alert_failure_rate_threshold = resolve_alerts_domain._resolve_alert_failure_rate_threshold
_resolve_alert_fallback_rate_threshold = resolve_alerts_domain._resolve_alert_fallback_rate_threshold
_resolve_alert_p95_ms_threshold = resolve_alerts_domain._resolve_alert_p95_ms_threshold
_resolve_alert_low_conf_rate_threshold = resolve_alerts_domain._resolve_alert_low_conf_rate_threshold
_resolve_alert_notify_enabled = resolve_alerts_domain._resolve_alert_notify_enabled
_resolve_alert_notify_webhook_url = resolve_alerts_domain._resolve_alert_notify_webhook_url
_resolve_alert_notify_cooldown_s = resolve_alerts_domain._resolve_alert_notify_cooldown_s
_resolve_alert_notify_timeout_s = resolve_alerts_domain._resolve_alert_notify_timeout_s
_resolve_alert_events_max_entries = resolve_alerts_domain._resolve_alert_events_max_entries
_resolve_alert_events_append = resolve_alerts_domain._resolve_alert_events_append
_resolve_alert_events_snapshot = resolve_alerts_domain._resolve_alert_events_snapshot
_resolve_alert_signature = resolve_alerts_domain._resolve_alert_signature
_percentile = resolve_alerts_domain._percentile
_resolve_observe_prune_locked = resolve_alerts_domain._resolve_observe_prune_locked
_resolve_observe_record = resolve_alerts_domain._resolve_observe_record
_resolve_alerts_payload = resolve_alerts_domain._resolve_alerts_payload
_resolve_observe_reset = resolve_alerts_domain._resolve_observe_reset


def _resolve_alert_notify_webhook(url: str, payload: dict, *, timeout_s: float) -> tuple[bool, str]:
    return resolve_alerts_domain._resolve_alert_notify_webhook(url, payload, timeout_s=timeout_s)


def _resolve_alert_notification_info(*, alerts: dict, snapshot: dict) -> dict:
    return resolve_alerts_domain._resolve_alert_notification_info(
        alerts=alerts,
        snapshot=snapshot,
        notify_webhook_fn=_resolve_alert_notify_webhook,
    )


def _resolve_observe_snapshot(*, limit: int = 60) -> dict:
    return resolve_alerts_domain._resolve_observe_snapshot(
        limit=limit,
        alert_notification_info_fn=_resolve_alert_notification_info,
    )

def _clean_text(value: object) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _extract_year(value: object) -> str:
    found = _YEAR_RE.search(str(value or ""))
    return found.group(0) if found else ""


def _normalize_doi(value: object) -> str:
    raw = _clean_text(value).lower()
    if not raw:
        return ""
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    raw = raw.lstrip("/")
    found = _DOI_RE.search(raw)
    if not found:
        return ""
    return str(found.group(0)).rstrip(").,;:")


def _normalize_public_url(raw_url: str) -> str:
    url = _clean_text(raw_url)
    if not url:
        raise ValueError("url required")
    parsed = urlsplit(url)
    scheme = str(parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError("url must be http or https")
    if not parsed.netloc:
        raise ValueError("url host required")
    if parsed.username or parsed.password:
        raise ValueError("url with credentials is not allowed")
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("url host required")
    if host == "localhost" or host.endswith(".local"):
        raise ValueError("url host is not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise ValueError("url host is not allowed")
    if parsed.port is not None and int(parsed.port) not in {80, 443}:
        raise ValueError("url port is not allowed")
    path = parsed.path or "/"
    return urlunsplit((scheme, parsed.netloc, path, parsed.query, ""))


def _extract_url_hints(url: str) -> dict[str, str]:
    parsed = urlsplit(url)
    host = str(parsed.hostname or "").strip().lower()
    path = str(parsed.path or "")
    hints = {"doi": "", "arxiv_id": "", "openalex_work": ""}

    if host in {"doi.org", "dx.doi.org"}:
        hints["doi"] = _normalize_doi(path.lstrip("/"))
    if not hints["doi"]:
        hints["doi"] = _normalize_doi(url)

    if "arxiv.org" in host:
        m = re.search(r"/(?:abs|pdf)/([^/?#]+)", path, flags=re.IGNORECASE)
        if m:
            arxiv_raw = str(m.group(1) or "").replace(".pdf", "")
            arxiv_match = _ARXIV_RE.search(arxiv_raw)
            if arxiv_match:
                hints["arxiv_id"] = str(arxiv_match.group(1))
    if not hints["arxiv_id"]:
        arxiv_match = _ARXIV_RE.search(url)
        if arxiv_match:
            hints["arxiv_id"] = str(arxiv_match.group(1))

    if "openalex.org" in host:
        work_match = _OPENALEX_WORK_RE.search(path.upper())
        if work_match:
            hints["openalex_work"] = str(work_match.group(0)).upper()

    return hints


def _decode_body(raw: bytes, content_type: str) -> str:
    charset = "utf-8"
    match = re.search(r"charset=([A-Za-z0-9._-]+)", str(content_type or ""), flags=re.IGNORECASE)
    if match:
        charset = str(match.group(1) or "utf-8").strip().lower()
    try:
        return raw.decode(charset, errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def _meta_value(meta_map: dict[str, list[str]], keys: list[str]) -> str:
    for key in keys:
        rows = meta_map.get(str(key).lower())
        if not rows:
            continue
        for row in rows:
            clean = _clean_text(row)
            if clean:
                return clean
    return ""


def _parse_meta_map(html_text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for tag in _META_TAG_RE.findall(html_text):
        attrs: dict[str, str] = {}
        for m in _META_ATTR_RE.finditer(tag):
            k = str(m.group(1) or "").strip().lower()
            v = str(m.group(2) or "").strip()
            if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
                v = v[1:-1]
            attrs[k] = _clean_text(html.unescape(v))
        key = attrs.get("name") or attrs.get("property") or attrs.get("itemprop") or ""
        value = attrs.get("content") or ""
        if not key or not value:
            continue
        out.setdefault(key.lower(), []).append(value)
    return out


def _jsonld_first_text(value: object) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        for key in ("name", "headline", "value"):
            text = _jsonld_first_text(value.get(key))
            if text:
                return text
        return ""
    if isinstance(value, list):
        for item in value:
            text = _jsonld_first_text(item)
            if text:
                return text
    return ""


def _jsonld_authors(value: object) -> list[str]:
    rows = value if isinstance(value, list) else [value]
    out: list[str] = []
    for row in rows:
        name = _jsonld_first_text(row)
        if not name:
            continue
        out.append(name)
    return out


def _jsonld_doi(value: object) -> str:
    if isinstance(value, str):
        return _normalize_doi(value)
    if isinstance(value, dict):
        property_id = _clean_text(value.get("propertyID") or value.get("propertyId")).lower()
        if "doi" in property_id:
            return _normalize_doi(value.get("value"))
        for key in ("value", "name", "url", "@id"):
            doi = _jsonld_doi(value.get(key))
            if doi:
                return doi
        return ""
    if isinstance(value, list):
        for row in value:
            doi = _jsonld_doi(row)
            if doi:
                return doi
    return ""


def _iter_jsonld_objects(html_text: str) -> list[dict]:
    objs: list[dict] = []
    for block in _JSONLD_RE.findall(html_text):
        raw = _clean_text(html.unescape(block))
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        queue: list[object] = [data]
        while queue:
            node = queue.pop(0)
            if isinstance(node, dict):
                objs.append(node)
                graph = node.get("@graph")
                if isinstance(graph, list):
                    queue.extend(graph)
            elif isinstance(node, list):
                queue.extend(node)
    return objs


def _fetch_page_metadata(
    url: str,
    *,
    timeout_s: float = _RESOLVE_TIMEOUT_S,
    max_bytes: int = _RESOLVE_METADATA_MAX_BYTES,
) -> dict:
    req = UrlRequest(
        url=str(url),
        headers={
            "User-Agent": _RESOLVE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.2",
        },
        method="GET",
    )
    with urlopen(req, timeout=timeout_s) as resp:  # nosec B310
        content_type = str(resp.headers.get("Content-Type") or "")
        raw = resp.read(max(1024, int(max_bytes) + 1))
    if len(raw) > int(max_bytes):
        raw = raw[: int(max_bytes)]
    text = _decode_body(raw, content_type)
    if not text:
        return {}

    meta_map = _parse_meta_map(text)
    title = ""
    m = _TITLE_RE.search(text)
    if m:
        title = _clean_text(html.unescape(str(m.group(1) or "")))
    title = _meta_value(meta_map, ["citation_title", "og:title", "dc.title"]) or title

    author_rows = meta_map.get("citation_author", []) + meta_map.get("author", []) + meta_map.get("dc.creator", [])
    authors = [_clean_text(row) for row in author_rows if _clean_text(row)]

    year = _extract_year(
        _meta_value(meta_map, ["citation_publication_date", "article:published_time", "dc.date", "citation_date"])
    )
    source = _meta_value(meta_map, ["citation_journal_title", "citation_conference_title", "og:site_name", "dc.source"])
    doi = _normalize_doi(_meta_value(meta_map, ["citation_doi", "dc.identifier"]))

    for obj in _iter_jsonld_objects(text):
        if not title:
            title = _jsonld_first_text(obj.get("headline") or obj.get("name"))
        if not authors:
            authors = _jsonld_authors(obj.get("author"))
        if not year:
            year = _extract_year(_jsonld_first_text(obj.get("datePublished") or obj.get("dateCreated")))
        if not source:
            source = _jsonld_first_text(obj.get("isPartOf") or obj.get("publisher"))
        if not doi:
            doi = _jsonld_doi(obj.get("identifier"))

    return {
        "title": _clean_text(title),
        "authors": [row for row in authors if row][:5],
        "year": _extract_year(year),
        "source": _clean_text(source),
        "doi": _normalize_doi(doi),
    }


def _work_title(work: object) -> str:
    return _clean_text(getattr(work, "title", ""))


def _work_authors(work: object) -> list[str]:
    rows = getattr(work, "authors", []) or []
    return [_clean_text(row) for row in rows if _clean_text(row)][:5]


def _work_year(work: object) -> str:
    return _extract_year(getattr(work, "published", ""))


def _work_source(work: object) -> str:
    source = _clean_text(getattr(work, "primary_category", ""))
    if source:
        return source
    categories = getattr(work, "categories", []) or []
    if isinstance(categories, list):
        for row in categories:
            clean = _clean_text(row)
            if clean:
                return clean
    return ""


def _work_url(work: object) -> str:
    return _clean_text(getattr(work, "abs_url", ""))


def _work_doi(work: object) -> str:
    return _normalize_doi(getattr(work, "doi", "")) or _normalize_doi(_work_url(work))


def _score_resolve_candidate(
    app_v2,
    *,
    hints: dict[str, str],
    cite_seed: Citation,
    query: str,
) -> tuple[str, object | None, float, str, list[str]]:
    warnings: list[str] = []
    candidates: list[tuple[str, object]] = []
    errors: list[str] = []

    query_value = _clean_text(query)
    if query_value:
        rows, row_errors = app_v2._collect_citation_candidates(query_value)
        candidates.extend(rows)
        errors.extend(row_errors)

    doi_hint = _normalize_doi(hints.get("doi"))
    if doi_hint and (not query_value or doi_hint not in query_value.lower()):
        rows, row_errors = app_v2._collect_citation_candidates(doi_hint)
        candidates.extend(rows)
        errors.extend(row_errors)

    if not candidates:
        if errors:
            warnings.append(f"search_error:{'|'.join(errors[:2])}")
        return "", None, 0.0, "metadata_only", warnings

    if doi_hint:
        for provider, work in candidates:
            work_doi = _work_doi(work)
            if work_doi and work_doi == doi_hint:
                return provider, work, 0.98, "doi_exact", warnings

    openalex_hint = str(hints.get("openalex_work") or "").upper()
    if openalex_hint:
        for provider, work in candidates:
            if openalex_hint in _work_url(work).upper():
                return provider, work, 0.96, "openalex_exact", warnings

    if _clean_text(cite_seed.title):
        provider, work, score, _, _ = app_v2._pick_best_citation_candidate(cite_seed, candidates)
        if work is not None:
            return provider, work, max(0.0, float(score)), "search_match", warnings

    provider, work = candidates[0]
    return provider, work, 0.58, "search_first", warnings


def _pick_first_surname(authors: str) -> str:
    raw = _clean_text(authors)
    if not raw:
        return ""
    first = re.split(r"[,;]| and ", raw, flags=re.IGNORECASE)[0].strip()
    tokens = [tok for tok in re.split(r"[^A-Za-z0-9]+", first) if tok]
    if not tokens:
        return ""
    return tokens[-1].lower()


def _pick_title_token(title: str) -> str:
    words = [tok.lower() for tok in re.split(r"[^A-Za-z0-9]+", _clean_text(title)) if len(tok) >= 3]
    if not words:
        words = [tok.lower() for tok in re.split(r"[^A-Za-z0-9]+", _clean_text(title)) if tok]
    return words[0] if words else ""


def _safe_citation_id(raw: str) -> str:
    value = re.sub(r"[^a-z0-9_]", "", str(raw or "").lower())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        return "cite"
    return value[:40]


def _suggest_citation_id(
    *,
    title: str,
    authors: str,
    year: str,
    doi: str,
    arxiv_id: str,
    existing_keys: set[str],
) -> str:
    surname = _pick_first_surname(authors)
    year_token = _extract_year(year)
    title_token = _pick_title_token(title)

    base = _safe_citation_id(f"{surname}{year_token}{title_token}")
    if base == "cite":
        if doi:
            base = _safe_citation_id(f"doi{re.sub(r'[^a-z0-9]+', '', doi.lower())[-12:]}")
        elif arxiv_id:
            base = _safe_citation_id(f"arxiv{re.sub(r'[^a-z0-9]+', '', arxiv_id.lower())}")

    candidate = base
    idx = 2
    while candidate.lower() in existing_keys:
        candidate = f"{base}_{idx}"
        idx += 1
    return candidate


class CitationService:
    def get_citations(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
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

    async def save_citations(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        data = await request.json()
        items = data.get("items") if isinstance(data, dict) else None
        session.citations = app_v2._normalize_citation_items(items)
        app_v2.store.put(session)
        return {"ok": 1, "count": len(session.citations or {})}

    async def resolve_url(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()
        started = app_v2.time.perf_counter()
        resolver_label = ""
        provider_label = ""
        confidence_value = 0.0
        warnings_value: list[str] = []

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        try:
            try:
                data = await request.json()
            except Exception:
                data = {}
            if not isinstance(data, dict):
                raise app_v2.HTTPException(status_code=400, detail="body must be object")
            raw_url = _clean_text(data.get("url"))
            if not raw_url:
                raise app_v2.HTTPException(status_code=400, detail="url required")
            try:
                url = _normalize_public_url(raw_url)
            except ValueError as exc:
                raise app_v2.HTTPException(status_code=400, detail=str(exc)) from exc

            warnings: list[str] = []
            hints = _extract_url_hints(url)
            metadata: dict = {}
            try:
                metadata = _fetch_page_metadata(url)
            except Exception as exc:
                warnings.append(f"metadata_fetch_failed:{exc.__class__.__name__}")

            if not metadata.get("doi") and hints.get("doi"):
                metadata["doi"] = hints.get("doi")

            metadata_title = _clean_text(metadata.get("title"))
            metadata_authors = metadata.get("authors") if isinstance(metadata.get("authors"), list) else []
            metadata_author_text = ", ".join([_clean_text(row) for row in metadata_authors if _clean_text(row)])
            metadata_year = _extract_year(metadata.get("year"))
            metadata_source = _clean_text(metadata.get("source"))

            query_parts: list[str] = []
            if metadata_title:
                query_parts.append(metadata_title)
            if metadata_author_text:
                query_parts.append(_pick_first_surname(metadata_author_text))
            if metadata_year:
                query_parts.append(metadata_year)
            query = _clean_text(" ".join([part for part in query_parts if part]))
            if not query:
                query = _clean_text(hints.get("doi") or hints.get("arxiv_id") or hints.get("openalex_work") or "")

            cite_seed = Citation(
                key="resolve_tmp",
                title=metadata_title or query,
                url=url,
                authors=metadata_author_text or None,
                year=metadata_year or None,
                venue=metadata_source or None,
            )
            provider, work, confidence, resolver, search_warnings = _score_resolve_candidate(
                app_v2,
                hints=hints,
                cite_seed=cite_seed,
                query=query,
            )
            warnings.extend(search_warnings)

            title = metadata_title
            author = metadata_author_text
            year = metadata_year
            source = metadata_source
            final_url = url
            doi = _normalize_doi(metadata.get("doi") or hints.get("doi"))

            if work is not None:
                title = _work_title(work) or title
                author = ", ".join(_work_authors(work)) or author
                year = _work_year(work) or year
                source = _work_source(work) or source
                final_url = _work_url(work) or final_url
                doi = _work_doi(work) or doi

            if not title:
                raise app_v2.HTTPException(status_code=422, detail="unable to resolve citation title")

            if resolver == "metadata_only":
                confidence = 0.45 if title else 0.0
                warnings.append("metadata_only")
            elif resolver in {"search_match", "search_first"} and confidence < 0.60:
                warnings.append("low_confidence_match")
            elif resolver == "search_match" and confidence < 0.82:
                warnings.append("medium_confidence_match")

            existing_keys = {str(k).strip().lower() for k in (session.citations or {}).keys() if str(k).strip()}
            citation_id = _suggest_citation_id(
                title=title,
                authors=author,
                year=year,
                doi=doi,
                arxiv_id=str(hints.get("arxiv_id") or ""),
                existing_keys=existing_keys,
            )

            resolver_label = str(resolver or "").strip().lower()
            provider_label = str(provider or "").strip().lower()
            confidence_value = max(0.0, min(1.0, float(confidence or 0.0)))
            warnings_value = [str(w).strip() for w in warnings if str(w).strip()]

            item = {
                "id": citation_id,
                "author": author,
                "title": title,
                "year": year,
                "source": source or final_url,
                "url": final_url,
            }
            response = {
                "ok": 1,
                "item": item,
                "confidence": round(confidence_value, 3),
                "warnings": sorted({str(w).strip() for w in warnings_value if str(w).strip()}),
                "debug": {
                    "resolver": resolver_label,
                    "provider": provider_label,
                    "score": round(confidence_value, 3),
                },
            }
            _resolve_observe_record(
                ok=True,
                elapsed_ms=round((app_v2.time.perf_counter() - started) * 1000.0, 2),
                resolver=resolver_label,
                provider=provider_label,
                confidence=confidence_value,
                warnings=warnings_value,
                error="",
            )
            return response
        except app_v2.HTTPException as exc:
            _resolve_observe_record(
                ok=False,
                elapsed_ms=round((app_v2.time.perf_counter() - started) * 1000.0, 2),
                resolver=resolver_label,
                provider=provider_label,
                confidence=confidence_value,
                warnings=warnings_value,
                error=f"http_{int(getattr(exc, 'status_code', 500) or 500)}",
            )
            raise
        except Exception as exc:
            _resolve_observe_record(
                ok=False,
                elapsed_ms=round((app_v2.time.perf_counter() - started) * 1000.0, 2),
                resolver=resolver_label,
                provider=provider_label,
                confidence=confidence_value,
                warnings=warnings_value,
                error=f"exception:{exc.__class__.__name__}",
            )
            raise

    async def verify_citations(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        req_started = app_v2.time.perf_counter()
        cache_before = app_v2._citation_verify_cache_metrics_snapshot()
        try:
            data = await request.json()
        except Exception:
            data = {}

        items = data.get("items") if isinstance(data, dict) else None
        persist = bool(data.get("persist", True)) if isinstance(data, dict) else True
        debug_enabled = bool(data.get("debug", False)) if isinstance(data, dict) else False
        if not debug_enabled:
            debug_enabled = str(app_v2.os.environ.get("WRITING_AGENT_CITATION_VERIFY_DEBUG", "")).strip() == "1"
        requested_debug_level = app_v2._normalize_verify_debug_level(data.get("debug_level") if isinstance(data, dict) else "")
        debug_level = requested_debug_level
        rate_limited_full = False
        if debug_enabled and debug_level == "full":
            if not app_v2._allow_full_debug(doc_id):
                debug_level = "safe"
                rate_limited_full = True
        source_citations = app_v2._normalize_citation_items(items) if isinstance(items, list) else dict(session.citations or {})
        worker_count = 0
        if not source_citations:
            empty = {
                "ok": 1,
                "items": [],
                "updated_items": [],
                "summary": {"total": 0, "verified": 0, "possible": 0, "not_found": 0, "error": 0},
            }
            elapsed_ms = round((app_v2.time.perf_counter() - req_started) * 1000.0, 2)
            cache_after = app_v2._citation_verify_cache_metrics_snapshot()
            request_observe = app_v2._citation_verify_observe_record(
                elapsed_ms=elapsed_ms,
                item_count=0,
                worker_count=0,
                error_count=0,
                cache_before=cache_before,
                cache_after=cache_after,
            )
            observe_snapshot = app_v2._citation_verify_observe_snapshot()
            if debug_enabled:
                empty["debug"] = app_v2._build_citation_verify_debug_payload(
                    persist=persist,
                    input_count=0,
                    worker_count=0,
                    elapsed_ms=elapsed_ms,
                    requested_level=requested_debug_level,
                    debug_level=debug_level,
                    rate_limited_full=rate_limited_full,
                    debug_items=[],
                    request_observe=request_observe,
                    observe_snapshot=observe_snapshot,
                )
            return empty

        results, updated, debug_items, worker_count = app_v2._verify_citation_batch(source_citations, debug_enabled=debug_enabled)

        summary = {"total": len(results), "verified": 0, "possible": 0, "not_found": 0, "error": 0}
        for item in results:
            status = str(item.get("status") or "")
            if status == "verified":
                summary["verified"] += 1
            elif status == "possible":
                summary["possible"] += 1
            elif status == "error":
                summary["error"] += 1
            else:
                summary["not_found"] += 1

        if persist:
            session.citations = updated
            app_v2._set_internal_pref(
                session,
                app_v2._CITATION_VERIFY_KEY,
                {
                    "updated_at": app_v2.time.time(),
                    "items": {str(item.get("id") or ""): item for item in results if str(item.get("id") or "")},
                    "summary": summary,
                },
            )
            app_v2.store.put(session)

        elapsed_ms = round((app_v2.time.perf_counter() - req_started) * 1000.0, 2)
        cache_after = app_v2._citation_verify_cache_metrics_snapshot()
        request_observe = app_v2._citation_verify_observe_record(
            elapsed_ms=elapsed_ms,
            item_count=len(results),
            worker_count=worker_count,
            error_count=int(summary.get("error") or 0),
            cache_before=cache_before,
            cache_after=cache_after,
        )
        observe_snapshot = app_v2._citation_verify_observe_snapshot()

        updated_items = [app_v2._citation_payload(cite) for cite in updated.values()]
        response = {"ok": 1, "items": results, "updated_items": updated_items, "summary": summary}
        if debug_enabled:
            response["debug"] = app_v2._build_citation_verify_debug_payload(
                persist=persist,
                input_count=len(source_citations),
                worker_count=worker_count,
                elapsed_ms=elapsed_ms,
                requested_level=requested_debug_level,
                debug_level=debug_level,
                rate_limited_full=rate_limited_full,
                debug_items=debug_items,
                request_observe=request_observe,
                observe_snapshot=observe_snapshot,
            )
        return response

    def metrics_citation_verify(self) -> dict:
        app_v2 = app_v2_module()

        return app_v2._safe_citation_verify_metrics_payload()

    def metrics_citation_resolve_url(self, limit: int = 60) -> dict:
        return {"ok": 1, **_resolve_observe_snapshot(limit=limit)}

    def metrics_citation_resolve_alerts_config(self, request: Request) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        return {"ok": 1, "config": _resolve_alerts_config_effective(), "source": _resolve_alerts_config_source()}

    async def metrics_citation_resolve_alerts_config_save(self, request: Request) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.write")
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            raise app_v2.HTTPException(status_code=400, detail="body must be object")
        if bool(data.get("reset")):
            config = _resolve_alerts_config_reset()
            return {"ok": 1, "config": config, "source": "env", "reset": True}
        payload = data.get("config") if isinstance(data.get("config"), dict) else data
        config = _resolve_alerts_config_save(payload)
        return {"ok": 1, "config": config, "source": "file", "reset": False}

    def metrics_citation_verify_alerts_config(self, request: Request) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        config = app_v2._citation_verify_alerts_config_effective()
        return {"ok": 1, "config": config, "source": app_v2._citation_verify_alerts_config_source()}

    async def metrics_citation_verify_alerts_config_save(self, request: Request) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.write")
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            raise app_v2.HTTPException(status_code=400, detail="body must be object")
        if bool(data.get("reset")):
            config = app_v2._citation_verify_alerts_config_reset()
            return {"ok": 1, "config": config, "source": "env", "reset": True}
        payload = data.get("config") if isinstance(data.get("config"), dict) else data
        config = app_v2._citation_verify_alerts_config_save(payload)
        return {"ok": 1, "config": config, "source": "file", "reset": False}

    def metrics_citation_verify_alerts_events(self, request: Request, limit: int = 50) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        snapshot = app_v2._citation_verify_alert_events_snapshot(limit=limit)
        return {"ok": 1, **snapshot}

    def metrics_citation_verify_alerts_event_detail(self, request: Request, event_id: str, context: int = 12) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        event = app_v2._citation_verify_alert_event_get(event_id)
        if not isinstance(event, dict):
            raise app_v2.HTTPException(status_code=404, detail="event not found")
        trend_context = app_v2._citation_verify_metrics_trend_context(ts=float(event.get("ts") or 0.0), limit=context)
        return {"ok": 1, "event": event, "trend_context": trend_context}

    def metrics_citation_verify_trends(self, limit: int = 120) -> dict:
        app_v2 = app_v2_module()

        snapshot = app_v2._citation_verify_metrics_trends_snapshot(limit=limit)
        return {"ok": 1, **snapshot}
