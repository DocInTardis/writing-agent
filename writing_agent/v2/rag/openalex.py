"""Openalex module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from http.client import IncompleteRead, RemoteDisconnected
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class OpenAlexWork:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    categories: list[str]
    primary_category: str


@dataclass(frozen=True)
class OpenAlexSearchResult:
    query: str
    max_results: int
    works: list[OpenAlexWork]


def search_openalex(*, query: str, max_results: int = 10, timeout_s: float = 30.0) -> OpenAlexSearchResult:
    q = (query or "").strip()
    if not q:
        raise ValueError("query required")
    max_results = int(max(1, min(50, max_results)))

    works: list[OpenAlexWork] = []
    per_page = min(50, max_results)
    page = 1
    while len(works) < max_results:
        batch = _fetch_page(query=q, per_page=per_page, page=page, timeout_s=timeout_s)
        if not batch:
            break
        for w in batch:
            works.append(w)
            if len(works) >= max_results:
                break
        if len(batch) < per_page:
            break
        page += 1
        time.sleep(0.2)

    return OpenAlexSearchResult(query=q, max_results=max_results, works=works)


def _fetch_page(*, query: str, per_page: int, page: int, timeout_s: float) -> list[OpenAlexWork]:
    base = "https://api.openalex.org/works"
    params = {"search": query, "per-page": str(per_page), "page": str(page)}
    url = f"{base}?{urlencode(params)}"
    headers = {"User-Agent": "writing-agent-studio/2.0 (+local rag builder)"}
    req = Request(url=url, headers=headers, method="GET")

    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = _safe_json(raw)
            results = data.get("results") if isinstance(data, dict) else None
            if not isinstance(results, list):
                return []
            return [_parse_work(w) for w in results if isinstance(w, dict)]
        except (RemoteDisconnected, IncompleteRead, URLError, HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(0.6 * attempt)
    if last_err:
        raise last_err
    return []


def _parse_work(obj: dict) -> OpenAlexWork:
    raw_id = str(obj.get("id") or "")
    ids = obj.get("ids") if isinstance(obj.get("ids"), dict) else {}
    if not raw_id:
        raw_id = str(ids.get("openalex") or "")
    work_id = _work_id_from_url(raw_id)
    paper_id = f"openalex:{work_id}" if work_id else f"openalex:{raw_id or 'work'}"

    title = _clean_text(str(obj.get("display_name") or ""))
    summary = _abstract_from_inverted_index(obj.get("abstract_inverted_index"))
    authors = _extract_authors(obj.get("authorships"))
    published = str(obj.get("publication_date") or "")
    updated = str(obj.get("updated_date") or "")
    abs_url = raw_id or (str(ids.get("openalex") or "") if isinstance(ids, dict) else "")

    categories = _extract_concepts(obj.get("concepts"))
    primary_category = categories[0] if categories else ""

    pdf_url = _pick_pdf_url(obj)

    return OpenAlexWork(
        paper_id=paper_id,
        title=title,
        summary=summary,
        authors=authors,
        published=published,
        updated=updated,
        abs_url=abs_url,
        pdf_url=pdf_url,
        categories=categories,
        primary_category=primary_category,
    )


def _pick_pdf_url(obj: dict) -> str:
    best = obj.get("best_oa_location") if isinstance(obj.get("best_oa_location"), dict) else {}
    primary = obj.get("primary_location") if isinstance(obj.get("primary_location"), dict) else {}

    for cand in (best.get("pdf_url"), primary.get("pdf_url")):
        if isinstance(cand, str) and cand.strip():
            return cand.strip()

    oa = obj.get("open_access") if isinstance(obj.get("open_access"), dict) else {}
    oa_url = oa.get("oa_url")
    if isinstance(oa_url, str) and oa_url.strip().lower().endswith(".pdf"):
        return oa_url.strip()

    return ""


def _extract_authors(authorships) -> list[str]:
    out: list[str] = []
    if isinstance(authorships, list):
        for a in authorships:
            if not isinstance(a, dict):
                continue
            auth = a.get("author") if isinstance(a.get("author"), dict) else {}
            name = _clean_text(str(auth.get("display_name") or ""))
            if name:
                out.append(name)
    return out


def _extract_concepts(concepts) -> list[str]:
    out: list[str] = []
    if isinstance(concepts, list):
        for c in concepts[:8]:
            if not isinstance(c, dict):
                continue
            name = _clean_text(str(c.get("display_name") or ""))
            if name:
                out.append(name)
    return out


def _abstract_from_inverted_index(inv) -> str:
    if not isinstance(inv, dict):
        return ""
    positions: dict[int, str] = {}
    for word, idxs in inv.items():
        if not isinstance(word, str) or not isinstance(idxs, list):
            continue
        for i in idxs:
            try:
                pos = int(i)
            except Exception:
                continue
            if pos not in positions:
                positions[pos] = word
    if not positions:
        return ""
    max_pos = max(positions.keys())
    words = [positions.get(i, "") for i in range(max_pos + 1)]
    return _clean_text(" ".join([w for w in words if w]))


def _work_id_from_url(url: str) -> str:
    s = (url or "").strip()
    if not s:
        return ""
    if "/" in s:
        return s.rsplit("/", 1)[-1]
    return s


def _clean_text(s: str) -> str:
    return " ".join((s or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _safe_json(raw: str) -> dict:
    try:
        import json

        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
