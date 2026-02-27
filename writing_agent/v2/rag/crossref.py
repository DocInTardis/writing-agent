"""Crossref module.

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
class CrossrefWork:
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
    doi: str


@dataclass(frozen=True)
class CrossrefSearchResult:
    query: str
    max_results: int
    works: list[CrossrefWork]


def search_crossref(*, query: str, max_results: int = 10, timeout_s: float = 20.0) -> CrossrefSearchResult:
    q = (query or "").strip()
    if not q:
        raise ValueError("query required")
    max_results = int(max(1, min(50, max_results)))
    works = _fetch(query=q, max_results=max_results, timeout_s=timeout_s)
    return CrossrefSearchResult(query=q, max_results=max_results, works=works)


def _fetch(*, query: str, max_results: int, timeout_s: float) -> list[CrossrefWork]:
    params = {
        "query.bibliographic": query,
        "rows": str(max_results),
        "sort": "relevance",
        "order": "desc",
    }
    url = f"https://api.crossref.org/works?{urlencode(params)}"
    req = Request(
        url=url,
        headers={"User-Agent": "writing-agent-studio/2.0 (+local citation verify)"},
        method="GET",
    )

    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = _safe_json(raw)
            message = data.get("message") if isinstance(data, dict) else {}
            items = message.get("items") if isinstance(message, dict) else None
            if not isinstance(items, list):
                return []
            out: list[CrossrefWork] = []
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                out.append(_parse_work(item, idx))
            return out
        except (RemoteDisconnected, IncompleteRead, URLError, HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(0.6 * attempt)
    if last_err:
        raise last_err
    return []


def _parse_work(item: dict, idx: int) -> CrossrefWork:
    doi = _clean_text(str(item.get("DOI") or ""))
    paper_id = f"crossref:{doi}" if doi else f"crossref:item-{idx}"
    title = _first_text(item.get("title"))
    container = _first_text(item.get("container-title"))
    authors = _extract_authors(item.get("author"))
    published = (
        _date_from_parts(item.get("issued"))
        or _date_from_parts(item.get("published-print"))
        or _date_from_parts(item.get("published-online"))
    )
    created = item.get("created") if isinstance(item.get("created"), dict) else {}
    updated = _clean_text(str(created.get("date-time") or ""))

    abs_url = _clean_text(str(item.get("URL") or ""))
    if not abs_url and doi:
        abs_url = f"https://doi.org/{doi}"
    pdf_url = _pick_pdf_url(item.get("link"))

    categories = [container] if container else []
    primary_category = container

    return CrossrefWork(
        paper_id=paper_id,
        title=title,
        summary="",
        authors=authors,
        published=published,
        updated=updated,
        abs_url=abs_url,
        pdf_url=pdf_url,
        categories=categories,
        primary_category=primary_category,
        doi=doi,
    )


def _extract_authors(authors) -> list[str]:
    out: list[str] = []
    if not isinstance(authors, list):
        return out
    for a in authors:
        if not isinstance(a, dict):
            continue
        name = _clean_text(str(a.get("name") or ""))
        if not name:
            given = _clean_text(str(a.get("given") or ""))
            family = _clean_text(str(a.get("family") or ""))
            name = " ".join([x for x in (given, family) if x]).strip()
        if name:
            out.append(name)
    return out


def _date_from_parts(raw) -> str:
    obj = raw if isinstance(raw, dict) else {}
    parts = obj.get("date-parts") if isinstance(obj.get("date-parts"), list) else []
    if not parts or not isinstance(parts[0], list):
        return ""
    first = parts[0]
    if not first:
        return ""
    nums: list[int] = []
    for x in first[:3]:
        try:
            nums.append(int(x))
        except Exception:
            break
    if not nums:
        return ""
    if len(nums) == 1:
        return f"{nums[0]:04d}"
    if len(nums) == 2:
        return f"{nums[0]:04d}-{nums[1]:02d}"
    return f"{nums[0]:04d}-{nums[1]:02d}-{nums[2]:02d}"


def _pick_pdf_url(raw_links) -> str:
    if not isinstance(raw_links, list):
        return ""
    for link in raw_links:
        if not isinstance(link, dict):
            continue
        content_type = _clean_text(str(link.get("content-type") or "")).lower()
        href = _clean_text(str(link.get("URL") or ""))
        if href and ("pdf" in content_type or href.lower().endswith(".pdf")):
            return href
    return ""


def _first_text(value) -> str:
    if isinstance(value, list):
        for item in value:
            text = _clean_text(str(item or ""))
            if text:
                return text
        return ""
    return _clean_text(str(value or ""))


def _clean_text(s: str) -> str:
    return " ".join((s or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _safe_json(raw: str) -> dict:
    try:
        import json

        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
