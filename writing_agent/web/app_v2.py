from __future__ import annotations

import io
import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from writing_agent.document import ExportPrefs, V2ReportDocxExporter
from writing_agent.storage import InMemoryStore
from writing_agent.web.html_sanitize import sanitize_html
from writing_agent.v2.doc_format import parse_report_text
from writing_agent.v2.figure_render import render_figure_svg
from writing_agent.v2.graph_runner import GenerateConfig, run_generate_graph
from writing_agent.v2.rag.arxiv import download_arxiv_pdf
from writing_agent.v2.rag.index import RagIndex
from writing_agent.v2.rag.retrieve import retrieve_context
from writing_agent.v2.rag.search import build_rag_context, search_papers
from writing_agent.v2.rag.store import RagStore
from writing_agent.v2.rag import search_arxiv
from writing_agent.v2.template_parse import parse_template_file


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Writing Agent Studio (v2)")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

store = InMemoryStore()
docx_exporter = V2ReportDocxExporter()

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(REPO_ROOT / ".data"))).resolve()
USER_TEMPLATES_DIR = DATA_DIR / "templates"
RAG_DIR = DATA_DIR / "rag"

rag_store = RagStore(RAG_DIR)
rag_index = RagIndex(RAG_DIR)


@app.get("/", response_class=HTMLResponse)
def root() -> RedirectResponse:
    session = store.create()
    session.doc_text = ""
    # Defaults: graduation design / report settings (user can override in UI).
    session.formatting = {
        "font_name": "Times New Roman",
        "font_name_east_asia": "宋体",
        "font_size_name": "小四",
        "font_size_pt": 12,
        "line_spacing": 1.5,
    }
    session.generation_prefs = {
        "purpose": "毕业设计/课程设计报告",
        "figure_types": ["flow", "er", "sequence", "bar", "line"],
        "table_types": ["summary", "metrics", "compare"],
        "include_cover": True,
        "include_toc": True,
        "toc_levels": 3,
        "page_numbers": True,
        "include_header": True,
        "page_margins_cm": 2.54,
    }
    store.put(session)
    return RedirectResponse(url=f"/workbench/{session.id}", status_code=303)


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/workbench/{doc_id}", response_class=HTMLResponse)
def workbench_page(request: Request, doc_id: str) -> HTMLResponse:
    session = store.get(doc_id)
    if session is None:
        return templates.TemplateResponse("v2_error2.html", {"request": request, "message": "文档不存在或已过期"})
    return templates.TemplateResponse("v2_workbench2.html", {"request": request, "doc_id": doc_id})


@app.get("/api/doc/{doc_id}")
def api_get_doc(doc_id: str) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {
        "id": session.id,
        "text": session.doc_text or "",
        "template_name": session.template_source_name or "",
        "required_h2": session.template_required_h2 or [],
        "formatting": session.formatting or {},
        "generation_prefs": session.generation_prefs or {},
    }


@app.post("/api/doc/{doc_id}/save")
async def api_save_doc(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    text = str(data.get("text") or "")
    session.doc_text = text
    if isinstance(data.get("formatting"), dict):
        session.formatting = data.get("formatting") or {}
    if isinstance(data.get("generation_prefs"), dict):
        session.generation_prefs = data.get("generation_prefs") or {}
    store.put(session)
    return {"ok": 1}


@app.post("/api/doc/{doc_id}/settings")
async def api_save_settings(doc_id: str, request: Request) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    if isinstance(data.get("formatting"), dict):
        session.formatting = data.get("formatting") or {}
    if isinstance(data.get("generation_prefs"), dict):
        session.generation_prefs = data.get("generation_prefs") or {}
    store.put(session)
    return {"ok": 1}


@app.post("/api/doc/{doc_id}/template")
async def api_upload_template(doc_id: str, file: UploadFile = File(...)) -> dict:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if file is None or not (file.filename or "").strip():
        raise HTTPException(status_code=400, detail="file required")

    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large (max 15MB)")

    USER_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    tid = uuid.uuid4().hex
    suffix = Path(file.filename).suffix.lower() or ".bin"
    path = (USER_TEMPLATES_DIR / f"{doc_id}_{tid}{suffix}")
    path.write_bytes(raw)

    info = parse_template_file(path, name=file.filename)
    session.template_source_name = info.name
    session.template_required_h2 = info.required_h2
    store.put(session)
    return {"ok": 1, "template_name": info.name, "required_h2": info.required_h2}


@app.post("/api/doc/{doc_id}/generate/stream")
async def api_generate_stream(doc_id: str, request: Request) -> StreamingResponse:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    instruction = str(data.get("instruction") or "").strip()
    current_text = str(data.get("text") or "")
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction 不能为空")
    instruction = _augment_instruction(instruction, formatting=session.formatting or {}, generation_prefs=session.generation_prefs or {})

    def emit(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def iter_events():
        cfg = GenerateConfig(
            workers=int(os.environ.get("WRITING_AGENT_WORKERS", "4")),
        )
        try:
            for ev in run_generate_graph(
                instruction=instruction,
                current_text=current_text,
                required_h2=session.template_required_h2 or None,
                config=cfg,
            ):
                event = str(ev.get("event") or "message")
                payload = dict(ev)
                payload.pop("event", None)
                if event == "final":
                    session.doc_text = str(payload.get("text") or "")
                    store.put(session)
                yield emit(event, payload)
        except Exception as e:
            yield emit("error", {"message": f"生成失败：{e}"})

    return StreamingResponse(
        iter_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/figure/render")
async def api_render_figure(request: Request) -> dict:
    data = await request.json()
    spec = data.get("spec") if isinstance(data, dict) else {}
    if not isinstance(spec, dict):
        raise HTTPException(status_code=400, detail="spec must be object")
    svg, caption = render_figure_svg(spec)
    safe_svg = sanitize_html(svg)
    return {"svg": safe_svg, "caption": caption}


@app.post("/api/rag/arxiv/ingest")
async def api_rag_arxiv_ingest(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    max_results = int(data.get("max_results") or 5)
    download_pdf = bool(data.get("download_pdf", True))
    keep_existing = bool(data.get("keep_existing", True))
    index_after = bool(data.get("index", True))
    embed = bool(data.get("embed", True))

    existing = {p.paper_id for p in rag_store.list_papers()} if keep_existing else set()

    res = search_arxiv(query=query, max_results=max_results)
    saved: list[dict] = []
    errors: list[dict] = []
    for paper in res.papers:
        if keep_existing and paper.paper_id in existing:
            continue
        try:
            pdf_bytes = download_arxiv_pdf(paper_id=paper.paper_id) if download_pdf else None
            rec = rag_store.put_arxiv_paper(paper, pdf_bytes=pdf_bytes)
            if index_after:
                try:
                    rag_index.upsert_from_paper(rec, embed=embed)
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


@app.get("/api/rag/papers")
def api_rag_list_papers() -> dict:
    papers = rag_store.list_papers()
    return {
        "papers": [
            {
                "paper_id": p.paper_id,
                "title": p.title,
                "published": p.published,
                "abs_url": p.abs_url,
                "pdf_path": p.pdf_path if Path(p.pdf_path).exists() else "",
            }
            for p in papers
        ]
    }


@app.post("/api/rag/search")
async def api_rag_search(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    top_k = int(data.get("top_k") or 5)
    hits = search_papers(papers=rag_store.list_papers(), query=query, top_k=top_k)
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
                "pdf_path": h.pdf_path if Path(h.pdf_path).exists() else "",
            }
            for h in hits
        ]
    }


@app.post("/api/rag/retrieve")
async def api_rag_retrieve(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    top_k = int(data.get("top_k") or 5)
    max_chars = int(data.get("max_chars") or 2500)
    per_paper = int(data.get("per_paper") or 2)
    res = retrieve_context(rag_dir=RAG_DIR, query=query, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    if res.chunk_hits:
        return {
            "context": res.context,
            "mode": "chunks",
            "hits": [
                {"chunk_id": h.chunk_id, "paper_id": h.paper_id, "title": h.title, "score": h.score, "kind": h.kind, "abs_url": h.abs_url}
                for h in res.chunk_hits
            ],
        }
    return {
        "context": res.context,
        "mode": "papers",
        "hits": [{"paper_id": h.paper_id, "title": h.title, "score": h.score} for h in res.paper_hits],
    }


@app.post("/api/rag/index/rebuild")
async def api_rag_index_rebuild(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    embed = bool(data.get("embed", True))
    total = rag_index.rebuild(embed=embed)
    return {"ok": 1, "chunks": total}


@app.post("/api/rag/search/chunks")
async def api_rag_search_chunks(request: Request) -> dict:
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    query = str(data.get("query") or "").strip()
    top_k = int(data.get("top_k") or 6)
    per_paper = int(data.get("per_paper") or 2)
    alpha = float(data.get("alpha") or 0.75)
    use_embeddings = bool(data.get("use_embeddings", True))
    hits = rag_index.search(query=query, top_k=top_k, per_paper=per_paper, use_embeddings=use_embeddings, alpha=alpha)
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


@app.get("/api/rag/paper/{paper_id:path}/pdf")
def api_rag_get_pdf(paper_id: str) -> FileResponse:
    path = rag_store.find_pdf_path(paper_id)
    if path is None:
        raise HTTPException(status_code=404, detail="pdf not found")
    return FileResponse(str(path), media_type="application/pdf", filename=path.name)


@app.get("/download/{doc_id}.docx")
def download_docx(doc_id: str) -> StreamingResponse:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    text = session.doc_text or ""
    if not text.strip():
        raise HTTPException(status_code=400, detail="文档为空")

    parsed = parse_report_text(text)
    fmt = _formatting_from_session(session)
    prefs = _export_prefs_from_session(session)
    payload = docx_exporter.build_from_parsed(parsed, fmt, prefs)
    filename = f"{parsed.title or 'document'}.docx"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _formatting_from_session(session) -> object:
    from writing_agent.models import FormattingRequirements

    f = getattr(session, "formatting", None)
    if not isinstance(f, dict):
        return FormattingRequirements()

    try:
        font_size_pt = int(f.get("font_size_pt") or 12)
    except Exception:
        font_size_pt = 12
    try:
        line_spacing = float(f.get("line_spacing") or 1.5)
    except Exception:
        line_spacing = 1.5
    font_name = str(f.get("font_name") or "Times New Roman")
    font_name_ea = str(f.get("font_name_east_asia") or "宋体")
    return FormattingRequirements(font_name=font_name, font_name_east_asia=font_name_ea, font_size_pt=font_size_pt, line_spacing=line_spacing)


def _export_prefs_from_session(session) -> ExportPrefs:
    prefs = getattr(session, "generation_prefs", None)
    if not isinstance(prefs, dict):
        return ExportPrefs()
    return ExportPrefs(
        include_cover=bool(prefs.get("include_cover", True)),
        include_toc=bool(prefs.get("include_toc", True)),
        toc_levels=int(prefs.get("toc_levels") or 3),
        include_header=bool(prefs.get("include_header", True)),
        page_numbers=bool(prefs.get("page_numbers", True)),
        page_margins_cm=float(prefs.get("page_margins_cm") or 2.54),
    )


def _augment_instruction(instruction: str, *, formatting: dict, generation_prefs: dict) -> str:
    inst = (instruction or "").strip()
    if not inst:
        return ""
    fmt = formatting if isinstance(formatting, dict) else {}
    prefs = generation_prefs if isinstance(generation_prefs, dict) else {}
    purpose = str(prefs.get("purpose") or "").strip()
    figure_types = prefs.get("figure_types")
    table_types = prefs.get("table_types")

    lines: list[str] = [inst, "", "【格式与输出约束（系统设置）】"]
    if purpose:
        lines.append(f"- 用途：{purpose}")
    if fmt:
        name = str(fmt.get("font_size_name") or "").strip()
        pt = str(fmt.get("font_size_pt") or "").strip()
        ls = str(fmt.get("line_spacing") or "").strip()
        if name or pt:
            lines.append(f"- 字号：{name or '[默认]'}（{pt or '[默认]'}pt）")
        if ls:
            lines.append(f"- 行距：{ls}")
    if isinstance(table_types, list) and table_types:
        lines.append("- 建议表格类型：" + ", ".join([str(x) for x in table_types]))
    if isinstance(figure_types, list) and figure_types:
        lines.append("- 建议图类型：" + ", ".join([str(x) for x in figure_types]))
    lines.append("- 若缺少具体数据，用[待补充]占位，但正文必须充实、可执行。")
    return "\n".join([x for x in lines if x is not None]).strip()


def _render_blocks_to_html(blocks) -> str:
    out: list[str] = []
    for b in blocks:
        if b.type == "heading":
            level = max(1, min(3, int(b.level or 1)))
            txt = _esc(b.text or "")
            if level == 1:
                out.append(f'<h1 style="text-align:center;margin-bottom:12pt">{txt}</h1>')
            elif level == 2:
                out.append(f'<h2 style="margin-top:12pt;margin-bottom:6pt">{txt}</h2>')
            else:
                out.append(f'<h3 style="margin-top:10pt;margin-bottom:4pt">{txt}</h3>')
        elif b.type == "paragraph":
            body = _esc(b.text or "").replace("\n", "<br/>")
            out.append('<p style="text-align:justify;text-indent:2em;margin-bottom:6pt">' + body + "</p>")
        elif b.type == "table":
            t = b.table or {}
            caption = _esc(str(t.get("caption") or "").strip() or "表格")
            cols = t.get("columns") if isinstance(t, dict) else None
            rows = t.get("rows") if isinstance(t, dict) else None
            columns = [str(c) for c in cols] if isinstance(cols, list) else ["列1", "列2"]
            body = rows if isinstance(rows, list) else [["[待补充]", "[待补充]"]]
            out.append(f'<p style="margin-top:6pt;margin-bottom:4pt"><strong>{caption}</strong></p>')
            out.append('<table class="tbl"><thead><tr>' + "".join(f"<th>{_esc(c)}</th>" for c in columns) + "</tr></thead><tbody>")
            for r in body[:20]:
                rr = r if isinstance(r, list) else [str(r)]
                out.append("<tr>" + "".join(f"<td>{_esc(str(rr[i]) if i < len(rr) else '')}</td>" for i in range(len(columns))) + "</tr>")
            out.append("</tbody></table>")
        elif b.type == "figure":
            f = b.figure or {}
            caption = _esc(str(f.get("caption") or "图"))
            out.append(f'<p style="margin-top:6pt;margin-bottom:4pt"><strong>图：</strong>{caption}（导出docx时为占位）</p>')
            out.append(f'<p style="text-indent:2em;margin-bottom:6pt">[图占位] {caption}</p>')
    return "".join(out)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
