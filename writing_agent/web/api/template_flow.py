"""Template Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile

router = APIRouter()


def _app_v2():
    from writing_agent.web import app_v2

    return app_v2


async def save_doc(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()

    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    incoming_ir = data.get("doc_ir")
    saved_from_ir = False
    if isinstance(incoming_ir, dict) and incoming_ir.get("sections") is not None:
        try:
            session.doc_ir = incoming_ir
            text = app_v2.doc_ir_to_text(app_v2.doc_ir_from_dict(session.doc_ir))
            saved_from_ir = True
        except Exception:
            text = str(data.get("text") or "")
    else:
        text = str(data.get("text") or "")

    incoming = text.strip()
    existing = (session.doc_text or "").strip()
    # Prevent overwriting a richer draft with a title-only short payload.
    if existing and (len(existing) > len(incoming)) and (not app_v2.re.search(r"(?m)^##\s+.+$", incoming)) and app_v2.re.search(
        r"(?m)^##\s+.+$",
        existing,
    ):
        text = session.doc_text

    if saved_from_ir:
        session.doc_text = text
    else:
        app_v2._set_doc_text(session, text)

    if isinstance(data.get("formatting"), dict):
        session.formatting = data.get("formatting") or {}
    if isinstance(data.get("generation_prefs"), dict):
        session.generation_prefs = app_v2._merge_generation_prefs(
            session.generation_prefs if isinstance(session.generation_prefs, dict) else {},
            data.get("generation_prefs") or {},
        )
    app_v2.store.put(session)
    return {"ok": 1}


async def import_doc(doc_id: str, file: UploadFile = File(...)) -> dict:
    app_v2 = _app_v2()

    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")
    if file is None or not (file.filename or "").strip():
        raise app_v2.HTTPException(status_code=400, detail="file required")

    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise app_v2.HTTPException(status_code=400, detail="file too large (max 50MB)")

    temp_dir = app_v2.DATA_DIR / "imports"
    temp_dir.mkdir(parents=True, exist_ok=True)
    suffix = app_v2.Path(file.filename).suffix.lower() or ".txt"
    tmp_path = temp_dir / f"{doc_id}_{app_v2.uuid.uuid4().hex}{suffix}"
    tmp_path.write_bytes(raw)
    try:
        text = app_v2._try_rust_import(tmp_path) or app_v2._extract_text(tmp_path)
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass

    text = (text or "").strip()
    if not text:
        raise app_v2.HTTPException(status_code=400, detail="empty document")

    app_v2._set_doc_text(session, text)
    app_v2.store.put(session)
    return {"ok": 1, "text": text}


async def save_settings(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()

    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")

    if isinstance(data.get("formatting"), dict):
        session.formatting = data.get("formatting") or {}
    if isinstance(data.get("generation_prefs"), dict):
        session.generation_prefs = app_v2._merge_generation_prefs(
            session.generation_prefs if isinstance(session.generation_prefs, dict) else {},
            data.get("generation_prefs") or {},
        )
    app_v2.store.put(session)
    return {"ok": 1}


async def analyze_message(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()

    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    text = str(data.get("text") or "").strip()
    if not text:
        raise app_v2.HTTPException(status_code=400, detail="text required")

    analysis = app_v2._run_message_analysis(
        session,
        text,
        force=bool(data.get("force")),
        quick=bool(data.get("quick")) or str(data.get("mode") or "").lower() == "quick",
    )
    return {"ok": 1, "analysis": analysis}


async def extract_prefs(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()

    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    text = str(data.get("text") or "").strip()
    if not text:
        raise app_v2.HTTPException(status_code=400, detail="text required")

    settings = app_v2.get_ollama_settings()
    if not settings.enabled:
        raise app_v2.HTTPException(status_code=400, detail="Ollama is not enabled")

    client = app_v2.OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise app_v2.HTTPException(status_code=400, detail="Ollama is not running")

    model = app_v2.os.environ.get("WRITING_AGENT_EXTRACT_MODEL", "").strip() or settings.model
    analysis = app_v2._run_message_analysis(session, text, quick=False)
    analysis_text = app_v2._compose_analysis_input(text, analysis)
    extract_timeout = app_v2._extract_timeout_s()

    parsed = app_v2._fast_extract_prefs(text)
    refined = {}
    has_fast = bool(parsed)
    force_ai = app_v2.os.environ.get("WRITING_AGENT_EXTRACT_FAST_ONLY", "").strip() == "0"
    if force_ai:
        try:
            ai_parsed = app_v2._extract_prefs_with_model(
                base_url=settings.base_url,
                model=model,
                text=analysis_text,
                timeout_s=extract_timeout,
            )
            if isinstance(ai_parsed, dict):
                parsed.update(ai_parsed)
            if app_v2.os.environ.get("WRITING_AGENT_EXTRACT_REFINE", "").strip() == "1":
                refined = app_v2._extract_prefs_refine_with_model(
                    base_url=settings.base_url,
                    model=model,
                    text=analysis_text,
                    initial=parsed or {},
                    timeout_s=extract_timeout,
                )
        except Exception:
            if not has_fast:
                parsed = {}
            refined = {}

    merged: dict = {}
    if isinstance(parsed, dict):
        merged.update(parsed)
    if isinstance(refined, dict):
        merged.update(refined)

    fmt = app_v2._normalize_ai_formatting(merged.get("formatting") if isinstance(merged, dict) else None)
    prefs = app_v2._normalize_ai_prefs(merged.get("generation_prefs") if isinstance(merged, dict) else None)
    prefs = app_v2._infer_role_defaults(text, prefs, analysis)
    title = str(merged.get("title") or "").strip() if isinstance(merged, dict) else ""
    questions = [str(x).strip() for x in (merged.get("questions") or []) if str(x).strip()] if isinstance(merged, dict) else []
    if text and questions:
        questions = [q for q in questions if not app_v2.re.search(r"(文本|内容).{0,6}粘贴", q)]
    summary = str(merged.get("summary") or "").strip() if isinstance(merged, dict) else ""

    auto_summary = app_v2._build_pref_summary(text, analysis, title, fmt, prefs)
    history = app_v2._analysis_history_context(session)
    dynamic = {}
    if settings.enabled and client.is_running():
        dynamic = app_v2._generate_dynamic_questions_with_model(
            base_url=settings.base_url,
            model=app_v2._analysis_model_name(settings),
            raw=text,
            analysis=analysis,
            history=history,
            merged={"title": title, "formatting": fmt, "generation_prefs": prefs, "summary": summary},
        )

    dyn_summary = str(dynamic.get("summary") or "").strip() if isinstance(dynamic, dict) else ""
    if dyn_summary:
        summary = dyn_summary
    elif (not summary or app_v2.re.search(r"(已识别|未提供|不足|缺失|不明确|不完整)", summary)):
        summary = auto_summary or summary

    dyn_qs = dynamic.get("questions") if isinstance(dynamic, dict) else None
    if isinstance(dyn_qs, list):
        questions = [str(x).strip() for x in dyn_qs if str(x).strip()]

    if not questions:
        questions = app_v2._build_missing_questions(title, fmt, prefs, analysis)
    conflicts = app_v2._detect_extract_conflicts(analysis=analysis, title=title, prefs=prefs)
    if conflicts:
        questions = conflicts + questions
    multi = app_v2._detect_multi_intent(text)
    if multi:
        questions = multi + questions
    conf = app_v2._field_confidence(text, analysis, title, prefs, fmt)
    low_conf = app_v2._low_conf_questions(conf)
    if low_conf:
        questions = low_conf + questions

    score = app_v2._info_score(title, fmt, prefs, analysis)
    max_q = 3
    if score >= 5:
        max_q = 1
    elif score >= 3:
        max_q = 2
    if len(questions) > max_q:
        questions = questions[:max_q]

    target_chars = app_v2._resolve_target_chars(fmt, prefs)
    if target_chars <= 0:
        has_length_q = any(app_v2.re.search(r"(字数|页数|页码|篇幅|长度)", q) for q in questions)
        if not has_length_q:
            questions.append("请告知目标字数或页数（任选其一）。")

    resp = {
        "ok": 1,
        "title": title,
        "formatting": fmt,
        "generation_prefs": prefs,
        "questions": questions,
        "summary": summary,
    }
    if app_v2.os.environ.get("WRITING_AGENT_EXTRACT_DEBUG", "").strip() == "1":
        resp["debug_text"] = text
        resp["debug_fast"] = parsed
    return resp


def _default_template_questions() -> list[str]:
    return ["未能自动识别模板结构，请补充章节目录或提供更清晰的模板内容。"]


async def upload_template(doc_id: str, file: UploadFile = File(...)) -> dict:
    app_v2 = _app_v2()

    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")
    if file is None or not (file.filename or "").strip():
        raise app_v2.HTTPException(status_code=400, detail="file required")

    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise app_v2.HTTPException(status_code=400, detail="file too large (max 50MB)")

    app_v2.USER_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    tid = app_v2.uuid.uuid4().hex
    suffix = app_v2.Path(file.filename).suffix.lower() or ".bin"
    path = app_v2.USER_TEMPLATES_DIR / f"{doc_id}_{tid}{suffix}"
    path.write_bytes(raw)

    resolved = app_v2.prepare_template_file(path)
    text = app_v2._extract_text(resolved)

    settings = app_v2.get_ollama_settings()
    if not settings.enabled:
        raise app_v2.HTTPException(status_code=400, detail="Ollama is not enabled")
    client = app_v2.OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise app_v2.HTTPException(status_code=400, detail="Ollama is not running")

    first = app_v2._extract_template_with_model(
        base_url=settings.base_url,
        model=settings.model,
        filename=file.filename,
        text=text,
    )
    refined = app_v2._extract_template_refine_with_model(
        base_url=settings.base_url,
        model=settings.model,
        filename=file.filename,
        text=text,
        initial=first or {},
    )

    info: dict = {}
    if isinstance(first, dict):
        info.update(first)
    if isinstance(refined, dict):
        info.update(refined)

    parsed = app_v2.parse_template_file(app_v2.Path(resolved), app_v2.Path(file.filename).stem)
    if parsed.outline:
        info["outline"] = list(parsed.outline)
        info["required_h2"] = list(parsed.required_h2)
        if not info.get("name"):
            info["name"] = parsed.name

    session.template_source_name = str(info.get("name") or app_v2.Path(file.filename).stem)
    session.template_required_h2 = list(info.get("required_h2") or [])
    session.template_outline = list(info.get("outline") or [])
    session.template_source_path = str(resolved)
    session.template_source_type = resolved.suffix.lower()
    app_v2.store.put(session)

    questions = [str(x).strip() for x in (info.get("questions") or []) if str(x).strip()] if isinstance(info, dict) else []
    if not session.template_outline and not questions:
        questions = _default_template_questions()

    return {
        "ok": 1,
        "template_name": session.template_source_name,
        "required_h2": session.template_required_h2,
        "template_outline": session.template_outline or [],
        "questions": questions,
    }


async def clear_template(doc_id: str) -> dict:
    app_v2 = _app_v2()

    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found or expired")
    session.template_source_name = ""
    session.template_required_h2 = []
    session.template_outline = []
    session.template_source_path = ""
    session.template_source_type = ""
    app_v2.store.put(session)
    return {"ok": 1}


async def doc_upload(doc_id: str, file: UploadFile = File(...)) -> dict:
    app_v2 = _app_v2()

    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    source_name, _, raw = await app_v2._read_upload_payload(file)
    rec = app_v2.user_library.put_upload(filename=source_name, file_bytes=raw)

    kind = "library"
    info = None
    resolved_path = ""
    try:
        src_path = app_v2.Path(rec.source_path)
        suffix = src_path.suffix.lower()
        text = app_v2.user_library.get_text(rec.doc_id)
        ai_kind = "unknown"
        settings = app_v2.get_ollama_settings()
        running = False
        if settings.enabled:
            client = app_v2.OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
            running = client.is_running()
            if running:
                result = app_v2._classify_upload_with_model(
                    base_url=settings.base_url,
                    model=settings.model,
                    filename=source_name,
                    text=text,
                )
                ai_kind = str(result.get("kind") or "unknown")

        if ai_kind == "template" and suffix in {".doc", ".docx", ".txt", ".md", ".html", ".htm"}:
            resolved = app_v2.prepare_template_file(src_path)
            if resolved.suffix.lower() != ".doc":
                resolved_path = str(resolved)
                first = app_v2._extract_template_with_model(
                    base_url=settings.base_url,
                    model=settings.model,
                    filename=source_name,
                    text=text,
                )
                refined = app_v2._extract_template_refine_with_model(
                    base_url=settings.base_url,
                    model=settings.model,
                    filename=source_name,
                    text=text,
                    initial=first or {},
                )
                info = {}
                if isinstance(first, dict):
                    info.update(first)
                if isinstance(refined, dict):
                    info.update(refined)
                kind = "template"
        elif suffix in {".doc", ".docx", ".txt", ".md", ".html", ".htm"} and running and ai_kind in {"unknown", "other", ""}:
            resolved = app_v2.prepare_template_file(src_path)
            if resolved.suffix.lower() != ".doc":
                resolved_path = str(resolved)
                quick = app_v2._extract_template_titles_with_model(
                    base_url=settings.base_url,
                    model=settings.model,
                    filename=source_name,
                    text=text,
                )
                titles = app_v2._normalize_string_list(quick.get("titles"), ("title", "text", "name"))
                questions = app_v2._normalize_string_list(quick.get("questions"), ("question", "text", "q"))
                if len(titles) >= 3:
                    kind = "template"
                    info = {
                        "name": app_v2.Path(source_name).stem,
                        "outline": [(1, t) for t in titles],
                        "required_h2": [],
                        "questions": questions,
                    }
                else:
                    info = None
                    kind = "library"
        elif ai_kind in {"reference", "other"}:
            kind = "library"
        else:
            kind = "library"

        if kind == "template" and info is not None and resolved_path:
            parsed = app_v2.parse_template_file(app_v2.Path(resolved_path), app_v2.Path(source_name).stem)
            if parsed.outline:
                info["outline"] = list(parsed.outline)
                info["required_h2"] = list(parsed.required_h2)
                if not info.get("name"):
                    info["name"] = parsed.name

        if kind == "template" and info is not None:
            session.template_source_name = str(info.get("name") or app_v2.Path(source_name).stem)
            session.template_required_h2 = list(info.get("required_h2") or [])
            session.template_outline = list(info.get("outline") or [])
            session.template_source_path = resolved_path
            session.template_source_type = app_v2.Path(resolved_path).suffix.lower() if resolved_path else ""
            app_v2.store.put(session)
    except Exception:
        info = None

    questions = []
    if isinstance(info, dict):
        questions = [str(x).strip() for x in (info.get("questions") or []) if str(x).strip()]
        if kind == "template" and not info.get("outline") and not questions:
            questions = _default_template_questions()

    payload = {"ok": 1, "kind": kind, "item": app_v2._library_item_payload(rec), "questions": questions}
    if kind == "template" and info is not None:
        payload.update(
            {
                "template_name": str(info.get("name") or ""),
                "required_h2": list(info.get("required_h2") or []),
                "template_outline": list(info.get("outline") or []),
            }
        )
    return payload


async def doc_upload_clarify(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()

    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")
    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    text = str(data.get("text") or "").strip()
    if not text:
        raise app_v2.HTTPException(status_code=400, detail="text required")

    template_path = str(session.template_source_path or "").strip()
    if not template_path:
        raise app_v2.HTTPException(status_code=400, detail="no active template")
    path = app_v2.Path(template_path)
    if not path.exists():
        raise app_v2.HTTPException(status_code=404, detail="template file not found")

    settings = app_v2.get_ollama_settings()
    if not settings.enabled:
        raise app_v2.HTTPException(status_code=400, detail="Ollama is not enabled")
    client = app_v2.OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise app_v2.HTTPException(status_code=400, detail="Ollama is not running")

    raw_text = app_v2._extract_text(path)
    combined = (raw_text + "\n\n用户补充说明:\n" + text).strip()
    first = app_v2._extract_template_with_model(
        base_url=settings.base_url,
        model=settings.model,
        filename=path.name,
        text=combined,
    )
    refined = app_v2._extract_template_refine_with_model(
        base_url=settings.base_url,
        model=settings.model,
        filename=path.name,
        text=combined,
        initial=first or {},
    )
    info: dict = {}
    if isinstance(first, dict):
        info.update(first)
    if isinstance(refined, dict):
        info.update(refined)

    parsed = app_v2.parse_template_file(path, app_v2.Path(path.name).stem)
    if parsed.outline:
        info["outline"] = list(parsed.outline)
        info["required_h2"] = list(parsed.required_h2)
        if not info.get("name"):
            info["name"] = parsed.name

    session.template_source_name = str(info.get("name") or session.template_source_name or app_v2.Path(path.name).stem)
    new_required = list(info.get("required_h2") or [])
    new_outline = list(info.get("outline") or [])
    if not new_outline and session.template_outline:
        new_outline = list(session.template_outline or [])
    if not new_required and session.template_required_h2:
        new_required = list(session.template_required_h2 or [])
    session.template_required_h2 = new_required
    session.template_outline = new_outline
    app_v2.store.put(session)

    questions = [str(x).strip() for x in (info.get("questions") or []) if str(x).strip()] if isinstance(info, dict) else []
    if not session.template_outline and not questions:
        questions = _default_template_questions()

    return {
        "ok": 1,
        "template_name": session.template_source_name,
        "required_h2": session.template_required_h2,
        "template_outline": session.template_outline or [],
        "questions": questions,
    }


class TemplateService:
    async def save_doc(self, doc_id: str, request: Request) -> dict:
        return await save_doc(doc_id, request)

    async def import_doc(self, doc_id: str, file: UploadFile = File(...)) -> dict:
        return await import_doc(doc_id, file)

    async def save_settings(self, doc_id: str, request: Request) -> dict:
        return await save_settings(doc_id, request)

    async def analyze_message(self, doc_id: str, request: Request) -> dict:
        return await analyze_message(doc_id, request)

    async def extract_prefs(self, doc_id: str, request: Request) -> dict:
        return await extract_prefs(doc_id, request)

    async def upload_template(self, doc_id: str, file: UploadFile = File(...)) -> dict:
        return await upload_template(doc_id, file)

    async def clear_template(self, doc_id: str) -> dict:
        return await clear_template(doc_id)

    async def doc_upload(self, doc_id: str, file: UploadFile = File(...)) -> dict:
        return await doc_upload(doc_id, file)

    async def doc_upload_clarify(self, doc_id: str, request: Request) -> dict:
        return await doc_upload_clarify(doc_id, request)


service = TemplateService()


@router.post("/api/doc/{doc_id}/save")
async def save_doc_flow(doc_id: str, request: Request) -> dict:
    return await service.save_doc(doc_id, request)


@router.post("/api/doc/{doc_id}/import")
async def import_doc_flow(doc_id: str, file: UploadFile = File(...)) -> dict:
    return await service.import_doc(doc_id, file)


@router.post("/api/doc/{doc_id}/settings")
async def save_settings_flow(doc_id: str, request: Request) -> dict:
    return await service.save_settings(doc_id, request)


@router.post("/api/doc/{doc_id}/analyze")
async def analyze_message_flow(doc_id: str, request: Request) -> dict:
    return await service.analyze_message(doc_id, request)


@router.post("/api/doc/{doc_id}/extract_prefs")
async def extract_prefs_flow(doc_id: str, request: Request) -> dict:
    return await service.extract_prefs(doc_id, request)


@router.post("/api/doc/{doc_id}/template")
async def upload_template_flow(doc_id: str, file: UploadFile = File(...)) -> dict:
    return await service.upload_template(doc_id, file)


@router.post("/api/doc/{doc_id}/template/clear")
async def clear_template_flow(doc_id: str) -> dict:
    return await service.clear_template(doc_id)


@router.post("/api/doc/{doc_id}/upload")
async def doc_upload_flow(doc_id: str, file: UploadFile = File(...)) -> dict:
    return await service.doc_upload(doc_id, file)


@router.post("/api/doc/{doc_id}/upload/clarify")
async def doc_upload_clarify_flow(doc_id: str, request: Request) -> dict:
    return await service.doc_upload_clarify(doc_id, request)
