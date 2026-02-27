"""App module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

import io
import json
import os
import re
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from writing_agent.agents.document_edit import DocumentEditAgent
from writing_agent.agents.report_policy import ReportPolicy, extract_template_headings
from writing_agent.agents.diagram_agent import DiagramAgent, DiagramRequest
from writing_agent.diagrams import render_er_svg, render_flowchart_svg
from writing_agent.diagrams.spec import DiagramSpec, ErEntity, ErRelation, ErSpec, FlowEdge, FlowNode, FlowchartSpec
from writing_agent.document import HtmlDocxBuilder
from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings
from writing_agent.models import FormattingRequirements, ReportRequest
from writing_agent.storage import InMemoryStore
from writing_agent.web.html_sanitize import sanitize_html


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="写作 Agent")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

store = InMemoryStore()
html_docx_builder = HtmlDocxBuilder()
edit_agent = DocumentEditAgent()
report_policy = ReportPolicy(min_section_paragraphs=2, min_total_chars=1200)
diagram_agent = DiagramAgent()

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "report_templates"
DATA_DIR = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(REPO_ROOT / ".data"))).resolve()
USER_TEMPLATES_DIR = DATA_DIR / "templates"
UPLOADS_DIR = DATA_DIR / "uploads"

_SAFE_FILE_ID = re.compile(r"^[a-f0-9]{32}\\.[a-zA-Z0-9]{1,8}$")


def _expand_media_markers(html: str) -> str:
    # Replace markers with rendered SVG (diagrams) or image placeholders.
    # Markers:
    # - [[FLOW: ...]]  -> flowchart diagram
    # - [[ER: ...]]    -> ER diagram
    # - [[IMG: ...]]   -> image placeholder (user can upload later)
    src = html or ""

    def _make_diagram_spec(dtype: str, instruction: str) -> DiagramSpec:
        ins = (instruction or "").strip()
        if dtype == "flowchart":
            parts = [p.strip() for p in re.split(r"\s*(?:->|→|=>|＞|›|»)\s*", ins) if p.strip()]
            if len(parts) < 2:
                parts = [ins] if ins else []
            nodes = [FlowNode(id=f"n{i+1}", text=txt[:26]) for i, txt in enumerate(parts[:10])]
            edges = [FlowEdge(src=f"n{i+1}", dst=f"n{i+2}") for i in range(len(nodes) - 1)]
            fc = FlowchartSpec(nodes=nodes, edges=edges) if nodes else None
            return DiagramSpec(type="flowchart", title="Flowchart", caption=ins or "流程图", flowchart=fc)

        # ER
        ent_a = ""
        ent_b = ""
        m2 = re.search(r"([\u4e00-\u9fffA-Za-z0-9_]{1,20})\s*[-–—>]\s*([\u4e00-\u9fffA-Za-z0-9_]{1,20})", ins)
        if m2:
            ent_a, ent_b = m2.group(1), m2.group(2)
        if not ent_a:
            ent_a = "EntityA"
        if not ent_b:
            ent_b = "EntityB"
        entities = [ErEntity(name=ent_a, attributes=["[待补充]"]), ErEntity(name=ent_b, attributes=["[待补充]"])]
        rel = ErRelation(left=ent_a, right=ent_b, label="[待补充]", cardinality="")
        return DiagramSpec(type="er", title="ER Diagram", caption=ins or "ER图", er=ErSpec(entities=entities, relations=[rel]))

    def repl_diagram(m: re.Match) -> str:
        kind = (m.group(1) or "").lower()
        instruction = (m.group(2) or "").strip()
        dtype = "flowchart" if kind == "flow" else "er"
        spec = _make_diagram_spec(dtype, instruction)
        svg = render_flowchart_svg(spec) if dtype == "flowchart" else render_er_svg(spec)
        caption = (spec.caption or "").strip() or instruction or ("流程图" if dtype == "flowchart" else "ER图")
        return (
            '<figure class="fig diagram">'
            f"{svg}"
            f'<figcaption class="muted">图：{caption}</figcaption>'
            "</figure>"
        )

    def repl_img(m: re.Match) -> str:
        caption = (m.group(1) or "").strip() or "图片（待补充）"
        return (
            '<figure class="fig">'
            f'<p class="img-ph">[图片占位] {caption}（请使用“插入图片”上传替换）</p>'
            f'<figcaption class="muted">图：{caption}</figcaption>'
            "</figure>"
        )

    src = re.sub(r"\[\[(FLOW|ER)\s*:\s*([\s\S]{1,400}?)\]\]", repl_diagram, src, flags=re.IGNORECASE)
    src = re.sub(r"\[\[IMG\s*:\s*([\s\S]{1,200}?)\]\]", repl_img, src, flags=re.IGNORECASE)
    return src


def _list_report_templates() -> list[str]:
    if not REPORT_TEMPLATES_DIR.exists():
        return []
    return [p.name for p in sorted(REPORT_TEMPLATES_DIR.glob("*.html"))]


def _read_report_template(name: str) -> str:
    p = REPORT_TEMPLATES_DIR / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="模板不存在")
    return p.read_text(encoding="utf-8")


@app.get("/files/{file_id}")
def get_file(file_id: str) -> FileResponse:
    if not _SAFE_FILE_ID.match(file_id):
        raise HTTPException(status_code=400, detail="invalid file id")
    path = (UPLOADS_DIR / file_id).resolve()
    if not str(path).startswith(str(UPLOADS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(path))


@app.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    # 直接进入工作台：自动创建新文档并跳转。
    formatting = FormattingRequirements()
    req = ReportRequest(
        topic="自动生成文档",
        report_type="",
        formatting=formatting,
        include_figures=False,
        writing_style="学术",
        manual_sources_text="",
    )
    session = store.create()
    session.request = req
    session.html = edit_agent.bootstrap(topic=req.topic, template_html=None)
    session.messages = []
    store.put(session)
    return RedirectResponse(url=f"/studio/{session.id}", status_code=303)


@app.get("/new", response_class=HTMLResponse)
def new_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request, "templates": _list_report_templates()})


@app.post("/start")
def start(
    topic: str = Form(""),
    instruction: str = Form(""),
    manual_sources_text: str = Form(""),
    template_name: str = Form(""),
    template_file: UploadFile | None = File(None),
) -> RedirectResponse:
    # 兼容：如果用户没填格式指标，给一个合理默认值。
    formatting = FormattingRequirements()
    req = ReportRequest(
        topic=(topic or "").strip() or "自动生成文档",
        report_type="",
        formatting=formatting,
        include_figures=False,
        writing_style="学术",
        manual_sources_text=manual_sources_text,
    )

    session = store.create()
    session.request = req
    template_html = ""
    template_label = ""

    if template_file is not None and (template_file.filename or "").strip():
        raw = template_file.file.read()
        try:
            template_html = raw.decode("utf-8")
        except Exception:
            template_html = raw.decode("utf-8", errors="replace")
        template_label = template_file.filename or "uploaded.html"
        USER_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        (USER_TEMPLATES_DIR / f"{session.id}.html").write_text(template_html, encoding="utf-8")
    elif template_name.strip():
        template_label = template_name.strip()
        template_html = _read_report_template(template_label)

    session.template_name = template_label
    session.template_html = template_html
    session.html = edit_agent.bootstrap(topic=req.topic, template_html=template_html or None)
    session.messages = []
    if instruction.strip():
        # 作为首次对话指令应用到文档
        session.messages.append({"role": "user", "content": instruction.strip()})
        try:
            res = edit_agent.apply_instruction(
                session.html,
                instruction.strip(),
                selection=None,
                template_html=template_html or None,
                title=req.topic,
            )
            required = extract_template_headings(template_html) if template_html.strip() else None
            expanded = _expand_media_markers(res.html)
            session.html = report_policy.enforce(sanitize_html(expanded), title=req.topic, required_headings=required).html
            session.messages.append({"role": "assistant", "content": res.assistant})
        except Exception as e:
            session.messages.append({"role": "assistant", "content": f"未能应用指令（可稍后重试）：{e}"})

    store.put(session)
    return RedirectResponse(url=f"/studio/{session.id}", status_code=303)


@app.get("/studio/{doc_id}", response_class=HTMLResponse)
def studio_page(request: Request, doc_id: str) -> HTMLResponse:
    session = store.get(doc_id)
    if session is None:
        return templates.TemplateResponse("error.html", {"request": request, "message": "文档不存在或已过期"})
    html = sanitize_html(session.html or "")
    return templates.TemplateResponse(
        "studio.html",
        {
            "request": request,
            "doc_id": doc_id,
            "html": html,
            "messages": session.messages,
            "template_name": session.template_name,
        },
    )


@app.post("/api/studio/{doc_id}/save")
async def studio_save(doc_id: str, request: Request) -> dict[str, str]:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    html = sanitize_html(str(data.get("html") or ""))
    required = extract_template_headings(session.template_html) if (session.template_html or "").strip() else None
    session.html = report_policy.enforce(html, title=session.request.topic if session.request else "报告", required_headings=required).html
    store.put(session)
    return {"ok": "1"}


@app.post("/api/studio/{doc_id}/chat")
async def studio_chat(doc_id: str, request: Request) -> dict[str, str]:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    instruction = str(data.get("instruction") or "").strip()
    html_in = str(data.get("html") or "")
    selection = str(data.get("selection") or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction 不能为空")

    safe_html = sanitize_html(html_in)
    session.messages.append({"role": "user", "content": instruction})
    try:
        res = edit_agent.apply_instruction(
            safe_html,
            instruction,
            selection=selection or None,
            template_html=session.template_html or None,
            title=session.request.topic if session.request else "报告",
        )
        required = extract_template_headings(session.template_html) if (session.template_html or "").strip() else None
        expanded = _expand_media_markers(res.html)
        session.html = report_policy.enforce(sanitize_html(expanded), title=session.request.topic if session.request else "报告", required_headings=required).html
        session.messages.append({"role": "assistant", "content": res.assistant})
        store.put(session)
        return {"html": session.html, "assistant": res.assistant}
    except Exception as e:
        msg = f"未能应用修改：{e}"
        session.messages.append({"role": "assistant", "content": msg})
        store.put(session)
        raise HTTPException(status_code=500, detail=msg) from e


@app.post("/api/studio/{doc_id}/chat/stream")
async def studio_chat_stream(doc_id: str, request: Request) -> StreamingResponse:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    instruction = str(data.get("instruction") or "").strip()
    html_in = str(data.get("html") or "")
    selection = str(data.get("selection") or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction 不能为空")

    safe_html = sanitize_html(html_in)
    session.messages.append({"role": "user", "content": instruction})
    store.put(session)

    settings = get_ollama_settings()
    if not settings.enabled:
        raise HTTPException(status_code=400, detail="未启用Ollama（WRITING_AGENT_USE_OLLAMA=0）")
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise HTTPException(status_code=500, detail="Ollama 未运行")

    title = session.request.topic if session.request else "报告"

    def iter_events():
        def emit(event: str, payload: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        def strip_tags(s: str) -> str:
            return re.sub(r"<[^>]+>", "", s or "")

        def split_by_h2(html: str):
            h2_re = re.compile(r"(?is)(<h2\\b[^>]*>.*?</h2>)")
            parts = h2_re.split(html or "")
            prefix = parts[0] if parts else ""
            sections: list[dict[str, str]] = []
            for i in range(1, len(parts), 2):
                heading = parts[i]
                content = parts[i + 1] if i + 1 < len(parts) else ""
                title_txt = strip_tags(heading).strip()
                sections.append({"title": title_txt, "heading": heading, "content": content})
            return prefix, sections

        def normalize_section_fragment(section_title: str, frag_html: str) -> str:
            def esc(s: str) -> str:
                return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            cleaned = sanitize_html(frag_html or "")
            if re.search(r"(?is)<h2\\b", cleaned):
                _, secs = split_by_h2(cleaned)
                if secs:
                    first = secs[0]
                    return (first.get("heading") or f"<h2>{esc(section_title)}</h2>") + (first.get("content") or "")
                return cleaned
            return f"<h2>{esc(section_title)}</h2>{cleaned}"

        def build_worker_prompts(section_title: str, section_html: str, headings: list[str]) -> tuple[str, str]:
            system = (
                "你是一个“章节写作Agent”。你只负责一个章节，不能改其他章节。\n"
                "输出要求：\n"
                "1) 只输出该章节的HTML片段，必须以对应的 <h2>章节标题</h2> 开头。\n"
                "2) 章节内容必须更具体、更长：至少 4 段 <p>（每段尽量包含具体步骤/定义/约束/示例占位）。\n"
                "3) 不要编造数据或引用；缺失信息用 [待补充]。\n"
                "4) 不要输出 <script> 或 on* 事件属性。\n"
                "5) 你需要自己判断何时插入表格/图片：\n"
                "   - 对比、指标、清单、实验结果等结构化信息：用 <table class=\"tbl\"> 展示。\n"
                "   - 需要可视化流程/架构/实体关系：在合适位置插入 [[FLOW: ...]] 或 [[ER: ...]]（系统会自动渲染为图）。\n"
                "   - 需要图片但无法给出真实图片：插入 [[IMG: 图注/用途]] 作为占位。\n"
            )
            user = (
                f"文档标题：{title}\n"
                f"文档章节：{', '.join([h for h in headings if h])}\n\n"
                f"你负责章节：《{section_title}》\n\n"
                f"用户整体要求：\n{instruction}\n\n"
                f"当前章节HTML（仅供参考，可重写扩写）：\n{section_html}\n\n"
                "请直接输出该章节的最终HTML片段。"
            )
            return system, user

        def merge_sections(prefix: str, sections: list[dict[str, str]], updates: dict[str, str]) -> str:
            out = [prefix]
            applied = set()
            for s in sections:
                t = s.get("title") or ""
                if t in updates:
                    out.append(updates[t])
                    applied.add(t)
                else:
                    out.append((s.get("heading") or "") + (s.get("content") or ""))
            for t, frag in updates.items():
                if t not in applied:
                    out.append(frag)
            return "".join(out)

        yield emit("start", {"ok": 1, "mode": "multi-agent"})

        required_headings = extract_template_headings(session.template_html) if (session.template_html or "").strip() else None
        base = report_policy.enforce(safe_html, title=title, required_headings=required_headings).html
        prefix, sections = split_by_h2(base)
        headings = [s.get("title") or "" for s in sections]

        # Decide target sections:
        # - if user selected text, focus the section containing it
        # - else if user explicitly mentions section titles, focus there
        # - otherwise expand all sections to increase completeness/detail.
        targets: list[str] = []
        if selection:
            sel = selection.strip()
            for s in sections:
                sec_html = (s.get("heading") or "") + (s.get("content") or "")
                if sel and sel in strip_tags(sec_html):
                    t = s.get("title") or ""
                    if t:
                        targets = [t]
                        break

        if not targets:
            targets = [t for t in headings if t and t in instruction]
        if not targets:
            targets = headings[:]

        worker_count = int(os.environ.get("WRITING_AGENT_WORKERS", "10"))  # 优化: 4->10
        worker_count = max(4, min(16, worker_count))  # 至少4个
        models_raw = os.environ.get("WRITING_AGENT_WORKER_MODELS", "").strip()
        worker_models = [m.strip() for m in models_raw.split(",") if m.strip()] if models_raw else [settings.model]
        if not worker_models:
            worker_models = [settings.model]

        yield emit("delta", {"delta": f"多Agent分工：{len(targets)}个章节，{worker_count}个worker…"})

        def run_section_worker(section_title: str, section_html: str, model: str) -> tuple[str, str]:
            worker_client = OllamaClient(base_url=settings.base_url, model=model, timeout_s=settings.timeout_s)
            system, user = build_worker_prompts(section_title, section_html, headings)
            out = worker_client.chat(system=system, user=user, temperature=0.25)
            frag = normalize_section_fragment(section_title, out)
            return section_title, frag

        updates: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=worker_count) as ex:
            futs = {}
            for i, t in enumerate(targets):
                sec = next((s for s in sections if (s.get("title") or "") == t), None)
                sec_html = ((sec.get("heading") or "") + (sec.get("content") or "")) if sec else f"<h2>{t}</h2>"
                model = worker_models[i % len(worker_models)]
                futs[ex.submit(run_section_worker, t, sec_html, model)] = t

            for fut in as_completed(futs):
                t = futs[fut]
                try:
                    section_title, frag = fut.result()
                    updates[section_title] = frag
                    yield emit("delta", {"delta": frag})
                except Exception as e:
                    yield emit("delta", {"delta": f"<h2>{t}</h2><p>[待补充]（章节Agent失败：{e}）</p>"})

        merged = merge_sections(prefix, sections, updates)

        # Aggregator: resolve cross-section consistency and conflicts (best-effort). Fallback to merged if bad.
        agg_model = os.environ.get("WRITING_AGENT_AGG_MODEL", "").strip() or settings.model
        agg_client = OllamaClient(base_url=settings.base_url, model=agg_model, timeout_s=settings.timeout_s)
        agg_system = (
            "你是一个“报告合并统筹Agent”。你会收到原始文档HTML与多个章节Agent生成的章节HTML。\n"
            "任务：把章节结果合并成一个完整HTML报告，替换对应章节内容，解决冲突并统一风格。\n"
            "要求：\n"
            "1) 只输出最终HTML（不要解释）。\n"
            "2) 不要缩短内容：尽量保留并整合所有章节Agent生成的细节。\n"
            "3) 保留H1标题与所有H2章节；每个章节至少2段<p>；缺失信息用[待补充]。\n"
            "4) 禁止<script>与on*事件属性。\n"
            "5) 你需要自己判断何时插入表格/图片：\n"
            "   - 对比、指标、清单、实验结果等结构化信息：用 <table class=\"tbl\"> 展示。\n"
            "   - 需要可视化流程/架构/实体关系：在合适位置插入 [[FLOW: ...]] 或 [[ER: ...]]。\n"
            "   - 需要图片但无法给出真实图片：插入 [[IMG: 图注/用途]]。\n"
        )
        agg_user = (
            f"用户要求：\n{instruction}\n\n"
            f"原始HTML：\n{base}\n\n"
            f"合并草稿（已按章节替换）：\n{merged}\n\n"
            f"章节候选（JSON，key为章节标题）：\n{json.dumps(updates, ensure_ascii=False)}\n\n"
            "请输出最终完整HTML。"
        )

        yield emit("delta", {"delta": "统筹合并中…"})
        agg_chunks: list[str] = []
        try:
            for delta in agg_client.chat_stream(system=agg_system, user=agg_user, temperature=0.2):
                agg_chunks.append(delta)
                yield emit("delta", {"delta": delta})
        except Exception as e:
            yield emit("delta", {"delta": f"统筹合并失败：{e}，将使用章节合并结果。"})
            agg_chunks = []

        raw = "".join(agg_chunks).strip() if agg_chunks else merged
        cleaned = sanitize_html(_expand_media_markers(raw))
        enforced = report_policy.enforce(cleaned, title=title, required_headings=required_headings)
        if not enforced.html.strip():
            enforced = report_policy.enforce(merged, title=title, required_headings=required_headings)

        session.html = enforced.html
        assistant = f"已由多Agent扩写并应用到左侧文档（章节数：{len(targets)}）。"
        if enforced.fixes:
            assistant += "（已自动补齐结构）"
        session.messages.append({"role": "assistant", "content": assistant})
        store.put(session)
        yield emit("final", {"assistant": assistant, "html": session.html})

    return StreamingResponse(
        iter_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/studio/{doc_id}/diagram")
async def studio_diagram(doc_id: str, request: Request) -> dict[str, str]:
    session = store.get(doc_id)
    if session is None or session.request is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    data = await request.json()
    dtype = str(data.get("type") or "").strip().lower()
    instruction = str(data.get("instruction") or "").strip()
    if dtype not in {"flowchart", "er"}:
        raise HTTPException(status_code=400, detail="type must be flowchart|er")
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction 不能为空")

    spec = diagram_agent.generate(DiagramRequest(type=dtype, instruction=instruction))
    if dtype == "er":
        svg = render_er_svg(spec)
        caption = spec.caption or "ER图"
    else:
        svg = render_flowchart_svg(spec)
        caption = spec.caption or "流程图"

    snippet = (
        '<div class="diagram">'
        f"{svg}"
        f'<p class="muted">图：{caption}</p>'
        "</div>"
    )
    safe = sanitize_html(snippet)
    return {"html": safe, "caption": caption}


@app.post("/api/studio/{doc_id}/upload-image")
async def studio_upload_image(doc_id: str, file: UploadFile = File(...)) -> dict[str, str]:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if file is None or not (file.filename or "").strip():
        raise HTTPException(status_code=400, detail="file required")
    if not (file.content_type or "").lower().startswith("image/"):
        raise HTTPException(status_code=400, detail="only image/* allowed")

    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large (max 5MB)")

    ext = Path(file.filename).suffix.lower().lstrip(".")
    if ext not in {"png", "jpg", "jpeg", "gif", "webp", "bmp"}:
        ext = "png"
    file_id = f"{uuid.uuid4().hex}.{ext}"

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    path = (UPLOADS_DIR / file_id)
    path.write_bytes(raw)
    session.uploads[file_id] = str(path.resolve())
    store.put(session)
    return {"url": f"/files/{file_id}", "file_id": file_id}


@app.get("/download/{doc_id}.docx")
def download_docx(doc_id: str) -> StreamingResponse:
    session = store.get(doc_id)
    if session is None or session.request is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not (session.html or "").strip():
        raise HTTPException(status_code=404, detail="文档为空")
    required = extract_template_headings(session.template_html) if (session.template_html or "").strip() else None
    enforced = report_policy.enforce(session.html, title=session.request.topic, required_headings=required)
    def resolve_image(src: str) -> str | None:
        if not src or not src.startswith("/files/"):
            return None
        file_id = src[len("/files/") :]
        if not _SAFE_FILE_ID.match(file_id):
            return None
        p = (UPLOADS_DIR / file_id)
        return str(p) if p.exists() else None

    payload = html_docx_builder.build(enforced.html, session.request.formatting, resolve_image_path=resolve_image)
    filename = f"{session.request.topic or 'document'}.docx"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
