"""Arxiv module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from http.client import IncompleteRead, RemoteDisconnected
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"


@dataclass(frozen=True)
class ArxivPaper:
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
class ArxivSearchResult:
    query: str
    max_results: int
    papers: list[ArxivPaper]


def search_arxiv(*, query: str, max_results: int = 5, timeout_s: float = 30.0) -> ArxivSearchResult:
    q = (query or "").strip()
    if not q:
        raise ValueError("query required")
    max_results = int(max(1, min(50, max_results)))

    base = "https://export.arxiv.org/api/query"
    params = {"search_query": f"all:{q}", "start": "0", "max_results": str(max_results)}
    url = f"{base}?{urlencode(params)}"
    headers = {"User-Agent": "writing-agent-studio/2.0 (+local rag builder)"}

    req = Request(url=url, headers=headers, method="GET")
    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urlopen(req, timeout=timeout_s) as resp:
                xml_text = resp.read().decode("utf-8", errors="replace")
            last_err = None
            break
        except (RemoteDisconnected, IncompleteRead, URLError, HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(0.6 * attempt)
    if last_err is not None:
        raise last_err

    papers = list(_parse_arxiv_atom(xml_text))
    return ArxivSearchResult(query=q, max_results=max_results, papers=papers)


def download_arxiv_pdf(*, paper_id: str, timeout_s: float = 60.0) -> bytes:
    pid = (paper_id or "").strip()
    if not pid:
        raise ValueError("paper_id required")
    url = f"https://arxiv.org/pdf/{pid}.pdf"
    headers = {"User-Agent": "writing-agent-studio/2.0 (+local rag builder)"}
    req = Request(url=url, headers=headers, method="GET")
    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urlopen(req, timeout=timeout_s) as resp:
                return resp.read()
        except (RemoteDisconnected, IncompleteRead, URLError, HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(0.9 * attempt)
    raise last_err or RuntimeError("download failed")


def _parse_arxiv_atom(xml_text: str) -> Iterable[ArxivPaper]:
    ns = {"a": ATOM_NS, "ar": ARXIV_NS}
    root = ET.fromstring(xml_text)
    for entry in root.findall("a:entry", namespaces=ns):
        abs_url = _clean_text(entry.findtext("a:id", default="", namespaces=ns))
        paper_id = _paper_id_from_abs_url(abs_url)

        title = _clean_text(entry.findtext("a:title", default="", namespaces=ns))
        summary = _clean_text(entry.findtext("a:summary", default="", namespaces=ns))
        authors = [_clean_text(a.findtext("a:name", default="", namespaces=ns)) for a in entry.findall("a:author", namespaces=ns)]
        authors = [a for a in authors if a]

        published = _clean_iso_datetime(_clean_text(entry.findtext("a:published", default="", namespaces=ns)))
        updated = _clean_iso_datetime(_clean_text(entry.findtext("a:updated", default="", namespaces=ns)))

        categories = [c.attrib.get("term", "") for c in entry.findall("a:category", namespaces=ns)]
        categories = [c for c in categories if c]
        primary_el = entry.find("ar:primary_category", namespaces=ns)
        primary_category = (primary_el.attrib.get("term", "") if primary_el is not None else "") or (categories[0] if categories else "")

        pdf_url = ""
        for link in entry.findall("a:link", namespaces=ns):
            href = link.attrib.get("href", "") or ""
            typ = link.attrib.get("type", "") or ""
            title_attr = (link.attrib.get("title", "") or "").lower()
            if typ == "application/pdf" or title_attr == "pdf" or "/pdf/" in href:
                pdf_url = href
                break
        if not pdf_url and paper_id:
            pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"

        if not paper_id:
            continue
        yield ArxivPaper(
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


def _paper_id_from_abs_url(abs_url: str) -> str:
    s = (abs_url or "").strip()
    if not s:
        return ""
    # Typical: http(s)://arxiv.org/abs/2501.12345v2 or .../abs/hep-th/9901001v1
    m = re.search(r"/abs/(?P<pid>[^?#]+)", s)
    if m:
        return m.group("pid")
    return s.rsplit("/", 1)[-1]


def _clean_text(s: str) -> str:
    return " ".join((s or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _clean_iso_datetime(s: str) -> str:
    if not s:
        return ""
    try:
        # arXiv uses ISO8601 with Z; keep normalized.
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.isoformat()
    except Exception:
        return s
