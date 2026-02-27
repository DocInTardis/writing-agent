"""Rag Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse

router = APIRouter()


def _app_v2():
    from writing_agent.web import app_v2

    return app_v2


async def rag_arxiv_ingest(request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    if not query:
        raise app_v2.HTTPException(status_code=400, detail="query required")

    max_results = int(data.get("max_results") or 5)
    download_pdf = bool(data.get("download_pdf", True))
    keep_existing = bool(data.get("keep_existing", True))
    index_after = bool(data.get("index", True))
    embed = bool(data.get("embed", True))
    existing = {p.paper_id for p in app_v2.rag_store.list_papers()} if keep_existing else set()
    res = app_v2.search_arxiv(query=query, max_results=max_results)

    saved: list[dict] = []
    errors: list[dict] = []
    for paper in res.papers:
        if keep_existing and paper.paper_id in existing:
            continue
        try:
            pdf_bytes = app_v2.download_arxiv_pdf(paper_id=paper.paper_id) if download_pdf else None
            rec = app_v2.rag_store.put_arxiv_paper(paper, pdf_bytes=pdf_bytes)
            if index_after:
                try:
                    app_v2.rag_index.upsert_from_paper(rec, embed=embed)
                except Exception:
                    pass
            saved.append(
                {
                    "paper_id": rec.paper_id,
                    "title": rec.title,
                    "published": rec.published,
                    "abs_url": rec.abs_url,
                    "pdf_url": rec.pdf_url,
                    "pdf_path": rec.pdf_path if (pdf_bytes is not None) else "",
                }
            )
        except Exception as e:
            errors.append({"paper_id": paper.paper_id, "title": paper.title, "error": str(e)})
    return {"ok": 1, "saved": saved, "errors": errors}


def rag_list_papers() -> dict:
    app_v2 = _app_v2()
    papers = app_v2.rag_store.list_papers()
    return {
        "papers": [
            {
                "paper_id": p.paper_id,
                "title": p.title,
                "published": p.published,
                "abs_url": p.abs_url,
                "pdf_path": p.pdf_path if app_v2.Path(p.pdf_path).exists() else "",
            }
            for p in papers
        ]
    }


async def rag_search(request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    if not query:
        raise app_v2.HTTPException(status_code=400, detail="query required")

    top_k = int(data.get("top_k") or 5)
    max_results = int(data.get("max_results") or 10)
    sources = data.get("sources")
    mode = str(data.get("mode") or "").strip().lower()
    is_remote = ("sources" in data) or ("max_results" in data) or mode == "remote"
    if is_remote and not isinstance(sources, list):
        sources = ["openalex", "arxiv"]

    mcp_payload = app_v2._mcp_rag_search(
        query,
        top_k=top_k,
        sources=sources if is_remote else None,
        max_results=max_results if is_remote else None,
        mode="remote" if is_remote else "local",
    )
    if isinstance(mcp_payload, dict):
        results = mcp_payload.get("results")
        mcp_mode = str(mcp_payload.get("mode") or "").strip().lower()
        if mcp_mode == "remote":
            is_remote = True
        if isinstance(results, list):
            if is_remote:
                items = []
                for r in results:
                    if not isinstance(r, dict):
                        continue
                    items.append(
                        {
                            "source": str(r.get("source") or ""),
                            "paper_id": str(r.get("id") or ""),
                            "title": str(r.get("title") or ""),
                            "summary": str(r.get("summary") or ""),
                            "authors": r.get("authors") or [],
                            "published": str(r.get("published") or ""),
                            "updated": str(r.get("updated") or ""),
                            "abs_url": str(r.get("url") or ""),
                            "pdf_url": str(r.get("pdf_url") or ""),
                            "categories": r.get("categories") or [],
                            "primary_category": str(r.get("primary_category") or ""),
                        }
                    )
                return {"ok": 1, "items": items}

            hits = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                hits.append(
                    {
                        "paper_id": str(r.get("id") or ""),
                        "title": str(r.get("title") or ""),
                        "summary": str(r.get("summary") or ""),
                        "snippet": str(r.get("snippet") or ""),
                        "score": float(r.get("score") or 0.0),
                        "published": str(r.get("published") or ""),
                        "abs_url": str(r.get("url") or ""),
                        "pdf_path": "",
                    }
                )
            return {"hits": hits}

    if is_remote:
        srcs = sources if isinstance(sources, list) else ["openalex", "arxiv"]
        items: list[dict] = []
        if "openalex" in srcs:
            try:
                res = app_v2.search_openalex(query=query, max_results=max_results)
                for w in res.works:
                    items.append(
                        {
                            "source": "openalex",
                            "paper_id": w.paper_id,
                            "title": w.title,
                            "summary": w.summary,
                            "authors": w.authors,
                            "published": w.published,
                            "updated": w.updated,
                            "abs_url": w.abs_url,
                            "pdf_url": w.pdf_url,
                            "categories": w.categories,
                            "primary_category": w.primary_category,
                        }
                    )
            except Exception:
                pass
        if "arxiv" in srcs:
            try:
                res = app_v2.search_arxiv(query=query, max_results=max_results)
                for p in res.papers:
                    items.append(
                        {
                            "source": "arxiv",
                            "paper_id": p.paper_id,
                            "title": p.title,
                            "summary": p.summary,
                            "authors": p.authors,
                            "published": p.published,
                            "updated": p.updated,
                            "abs_url": p.abs_url,
                            "pdf_url": p.pdf_url,
                            "categories": p.categories,
                            "primary_category": p.primary_category,
                        }
                    )
            except Exception:
                pass
        return {"ok": 1, "items": items}

    hits = app_v2.search_papers(papers=app_v2.rag_store.list_papers(), query=query, top_k=top_k)
    return {
        "hits": [
            {
                "paper_id": h.paper_id,
                "title": h.title,
                "summary": h.summary,
                "snippet": h.snippet,
                "score": h.score,
                "published": h.published,
                "abs_url": h.abs_url,
                "pdf_path": h.pdf_path if app_v2.Path(h.pdf_path).exists() else "",
            }
            for h in hits
        ]
    }


async def rag_retrieve(request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    top_k = int(data.get("top_k") or 5)
    max_chars = int(data.get("max_chars") or 2500)
    per_paper = int(data.get("per_paper") or 2)

    mcp_payload = app_v2._mcp_rag_retrieve(query, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    if isinstance(mcp_payload, dict):
        context = str(mcp_payload.get("context") or "")
        sources = mcp_payload.get("sources")
        hits: list[dict] = []
        if isinstance(sources, list):
            for s in sources:
                if not isinstance(s, dict):
                    continue
                hits.append(
                    {
                        "paper_id": str(s.get("id") or ""),
                        "title": str(s.get("title") or ""),
                        "abs_url": str(s.get("url") or ""),
                        "kind": str(s.get("kind") or ""),
                        "published": str(s.get("published") or ""),
                    }
                )
        return {"context": context, "mode": "mcp", "hits": hits}

    res = app_v2.retrieve_context(rag_dir=app_v2.RAG_DIR, query=query, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    if res.chunk_hits:
        return {
            "context": res.context,
            "mode": "chunks",
            "hits": [
                {"chunk_id": h.chunk_id, "paper_id": h.paper_id, "title": h.title, "score": h.score, "kind": h.kind, "abs_url": h.abs_url}
                for h in res.chunk_hits
            ],
        }
    return {"context": res.context, "mode": "papers", "hits": [{"paper_id": h.paper_id, "title": h.title, "score": h.score} for h in res.paper_hits]}


async def rag_index_rebuild(request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    embed = bool(data.get("embed", True))
    total = app_v2.rag_index.rebuild(embed=embed)
    return {"ok": 1, "chunks": total}


async def rag_search_chunks(request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    top_k = int(data.get("top_k") or 6)
    per_paper = int(data.get("per_paper") or 2)
    alpha = float(data.get("alpha") or 0.75)
    use_embeddings = bool(data.get("use_embeddings", True))

    mcp_payload = app_v2._mcp_rag_search_chunks(
        query,
        top_k=top_k,
        per_paper=per_paper,
        alpha=alpha,
        use_embeddings=use_embeddings,
    )
    if isinstance(mcp_payload, dict):
        hits = mcp_payload.get("hits")
        if isinstance(hits, list):
            return {
                "mode": "mcp",
                "hits": [
                    {
                        "chunk_id": str(h.get("chunk_id") or ""),
                        "paper_id": str(h.get("paper_id") or ""),
                        "title": str(h.get("title") or ""),
                        "abs_url": str(h.get("abs_url") or ""),
                        "kind": str(h.get("kind") or ""),
                        "score": float(h.get("score") or 0.0),
                        "text": str(h.get("text") or ""),
                    }
                    for h in hits
                    if isinstance(h, dict)
                ],
            }

    hits = app_v2.rag_index.search(query=query, top_k=top_k, per_paper=per_paper, use_embeddings=use_embeddings, alpha=alpha)
    return {
        "hits": [
            {
                "chunk_id": h.chunk_id,
                "paper_id": h.paper_id,
                "title": h.title,
                "abs_url": h.abs_url,
                "kind": h.kind,
                "score": h.score,
                "text": h.text,
            }
            for h in hits
        ]
    }


def rag_get_pdf(paper_id: str) -> FileResponse:
    app_v2 = _app_v2()
    path = app_v2.rag_store.find_pdf_path(paper_id)
    if path is None:
        raise app_v2.HTTPException(status_code=404, detail="pdf not found")
    return FileResponse(str(path), media_type="application/pdf", filename=path.name)


async def library_upload(file: UploadFile = File(...)) -> dict:
    app_v2 = _app_v2()
    source_name, _, raw = await app_v2._read_upload_payload(file)
    rec = app_v2.user_library.put_upload(filename=source_name, file_bytes=raw)
    return {"ok": 1, "item": app_v2._library_item_payload(rec)}


def library_items(status: str = "") -> dict:
    app_v2 = _app_v2()
    st = (status or "").strip().lower()
    if st in {"", "all"}:
        st = ""
    items = app_v2.user_library.list_items(status=st or None)
    return {"items": [app_v2._library_item_payload(i) for i in items]}


def library_item(doc_id: str) -> dict:
    app_v2 = _app_v2()
    rec = app_v2.user_library.get_item(doc_id)
    if rec is None:
        raise app_v2.HTTPException(status_code=404, detail="item not found")
    text = app_v2.user_library.get_text(doc_id)
    return {"item": app_v2._library_item_payload(rec), "text": text}


def library_approve(doc_id: str) -> dict:
    app_v2 = _app_v2()
    rec = app_v2.user_library.approve(doc_id)
    if rec is None:
        raise app_v2.HTTPException(status_code=404, detail="item not found")
    return {"ok": 1, "item": app_v2._library_item_payload(rec)}


def library_restore(doc_id: str) -> dict:
    app_v2 = _app_v2()
    rec = app_v2.user_library.restore(doc_id)
    if rec is None:
        raise app_v2.HTTPException(status_code=404, detail="item not found")
    return {"ok": 1, "item": app_v2._library_item_payload(rec)}


def library_trash(doc_id: str) -> dict:
    app_v2 = _app_v2()
    rec = app_v2.user_library.trash(doc_id)
    if rec is None:
        raise app_v2.HTTPException(status_code=404, detail="item not found")
    return {"ok": 1, "item": app_v2._library_item_payload(rec)}


async def library_update(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    text = str(data.get("text") or "")
    rec = app_v2.user_library.update_text(doc_id, text=text)
    if rec is None:
        raise app_v2.HTTPException(status_code=404, detail="item not found")
    return {"ok": 1, "item": app_v2._library_item_payload(rec)}


def library_delete(doc_id: str) -> dict:
    app_v2 = _app_v2()
    if not app_v2.user_library.delete(doc_id):
        raise app_v2.HTTPException(status_code=404, detail="item not found")
    return {"ok": 1}


async def library_from_doc(request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    text = str(data.get("text") or "").strip()
    if not text:
        raise app_v2.HTTPException(status_code=400, detail="text required")
    title = str(data.get("title") or "").strip() or app_v2._default_title()
    status = str(data.get("status") or "trashed").strip().lower() or "trashed"
    source_id = str(data.get("source_id") or "").strip()
    rec = app_v2.user_library.put_text(text=text, title=title, source="generated", status=status, source_id=source_id)
    return {"ok": 1, "item": app_v2._library_item_payload(rec)}


def _download_url(url: str, *, timeout_s: float = 40.0) -> bytes | None:
    app_v2 = _app_v2()
    u = (url or "").strip()
    if not u:
        return None
    headers = {"User-Agent": "writing-agent-studio/2.0 (+rag ingest)"}
    req = app_v2.UrlRequest(url=u, headers=headers, method="GET")
    try:
        with app_v2.urlopen(req, timeout=timeout_s) as resp:
            return resp.read()
    except Exception:
        return None


async def rag_ingest(request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    items = data.get("items") or []
    if not isinstance(items, list):
        raise app_v2.HTTPException(status_code=400, detail="items required")

    download_pdf = bool(data.get("download_pdf", True))
    embed = bool(data.get("embed", True))
    ingested: list[dict] = []
    for item in items[:50]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip().lower()
        paper_id = str(item.get("paper_id") or "").strip()
        if not paper_id:
            continue
        pdf_bytes = None
        try:
            if source == "arxiv":
                if download_pdf:
                    pdf_bytes = app_v2.download_arxiv_pdf(paper_id=paper_id)
                paper = type(
                    "ArxivPaperShim",
                    (),
                    {
                        "paper_id": paper_id,
                        "title": str(item.get("title") or ""),
                        "summary": str(item.get("summary") or ""),
                        "authors": item.get("authors") or [],
                        "published": str(item.get("published") or ""),
                        "updated": str(item.get("updated") or ""),
                        "abs_url": str(item.get("abs_url") or ""),
                        "pdf_url": str(item.get("pdf_url") or ""),
                        "categories": item.get("categories") or [],
                        "primary_category": str(item.get("primary_category") or ""),
                    },
                )()
                rec = app_v2.rag_store.put_arxiv_paper(paper, pdf_bytes=pdf_bytes)
            else:
                if download_pdf:
                    pdf_bytes = _download_url(str(item.get("pdf_url") or ""))
                work = type(
                    "OpenAlexWorkShim",
                    (),
                    {
                        "paper_id": paper_id,
                        "title": str(item.get("title") or ""),
                        "summary": str(item.get("summary") or ""),
                        "authors": item.get("authors") or [],
                        "published": str(item.get("published") or ""),
                        "updated": str(item.get("updated") or ""),
                        "abs_url": str(item.get("abs_url") or ""),
                        "pdf_url": str(item.get("pdf_url") or ""),
                        "categories": item.get("categories") or [],
                        "primary_category": str(item.get("primary_category") or ""),
                    },
                )()
                rec = app_v2.rag_store.put_openalex_work(work, pdf_bytes=pdf_bytes)
            app_v2.rag_index.upsert_from_paper(rec, embed=embed)
            ingested.append({"paper_id": paper_id, "title": rec.title, "source": rec.source})
        except Exception:
            continue
    return {"ok": 1, "count": len(ingested), "items": ingested}


def rag_stats() -> dict:
    app_v2 = _app_v2()
    papers = app_v2.rag_store.list_papers()
    return {
        "ok": 1,
        "paper_count": len(papers),
        "pdf_count": len([p for p in papers if p.pdf_path and app_v2.Path(p.pdf_path).exists()]),
        "chunks": app_v2.rag_index.index_path.exists(),
    }


class RagService:
    async def rag_arxiv_ingest(self, request: Request) -> dict:
        return await rag_arxiv_ingest(request)

    def rag_list_papers(self) -> dict:
        return rag_list_papers()

    async def rag_search(self, request: Request) -> dict:
        return await rag_search(request)

    async def rag_retrieve(self, request: Request) -> dict:
        return await rag_retrieve(request)

    async def rag_index_rebuild(self, request: Request) -> dict:
        return await rag_index_rebuild(request)

    async def rag_search_chunks(self, request: Request) -> dict:
        return await rag_search_chunks(request)

    def rag_get_pdf(self, paper_id: str) -> FileResponse:
        return rag_get_pdf(paper_id)

    async def library_upload(self, file: UploadFile = File(...)) -> dict:
        return await library_upload(file)

    def library_items(self, status: str = "") -> dict:
        return library_items(status=status)

    def library_item(self, doc_id: str) -> dict:
        return library_item(doc_id)

    def library_approve(self, doc_id: str) -> dict:
        return library_approve(doc_id)

    def library_restore(self, doc_id: str) -> dict:
        return library_restore(doc_id)

    def library_trash(self, doc_id: str) -> dict:
        return library_trash(doc_id)

    async def library_update(self, doc_id: str, request: Request) -> dict:
        return await library_update(doc_id, request)

    def library_delete(self, doc_id: str) -> dict:
        return library_delete(doc_id)

    async def library_from_doc(self, request: Request) -> dict:
        return await library_from_doc(request)

    async def rag_ingest(self, request: Request) -> dict:
        return await rag_ingest(request)

    def rag_stats(self) -> dict:
        return rag_stats()


service = RagService()


@router.post("/api/rag/arxiv/ingest")
async def rag_arxiv_ingest_flow(request: Request) -> dict:
    return await service.rag_arxiv_ingest(request)


@router.get("/api/rag/papers")
def rag_list_papers_flow() -> dict:
    return service.rag_list_papers()


@router.post("/api/rag/search")
async def rag_search_flow(request: Request) -> dict:
    return await service.rag_search(request)


@router.post("/api/rag/retrieve")
async def rag_retrieve_flow(request: Request) -> dict:
    return await service.rag_retrieve(request)


@router.post("/api/rag/index/rebuild")
async def rag_index_rebuild_flow(request: Request) -> dict:
    return await service.rag_index_rebuild(request)


@router.post("/api/rag/search/chunks")
async def rag_search_chunks_flow(request: Request) -> dict:
    return await service.rag_search_chunks(request)


@router.get("/api/rag/paper/{paper_id:path}/pdf")
def rag_get_pdf_flow(paper_id: str) -> FileResponse:
    return service.rag_get_pdf(paper_id)


@router.post("/api/library/upload")
async def library_upload_flow(file: UploadFile = File(...)) -> dict:
    return await service.library_upload(file)


@router.get("/api/library/items")
def library_items_flow(status: str = "") -> dict:
    return service.library_items(status=status)


@router.get("/api/library/item/{doc_id}")
def library_item_flow(doc_id: str) -> dict:
    return service.library_item(doc_id)


@router.post("/api/library/item/{doc_id}/approve")
def library_approve_flow(doc_id: str) -> dict:
    return service.library_approve(doc_id)


@router.post("/api/library/item/{doc_id}/restore")
def library_restore_flow(doc_id: str) -> dict:
    return service.library_restore(doc_id)


@router.post("/api/library/item/{doc_id}/trash")
def library_trash_flow(doc_id: str) -> dict:
    return service.library_trash(doc_id)


@router.post("/api/library/item/{doc_id}/update")
async def library_update_flow(doc_id: str, request: Request) -> dict:
    return await service.library_update(doc_id, request)


@router.delete("/api/library/item/{doc_id}")
def library_delete_flow(doc_id: str) -> dict:
    return service.library_delete(doc_id)


@router.post("/api/library/from_doc")
async def library_from_doc_flow(request: Request) -> dict:
    return await service.library_from_doc(request)


@router.post("/api/rag/ingest")
async def rag_ingest_flow(request: Request) -> dict:
    return await service.rag_ingest(request)


@router.get("/api/rag/stats")
def rag_stats_flow() -> dict:
    return service.rag_stats()
