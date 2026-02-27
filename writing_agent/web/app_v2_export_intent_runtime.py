"""App V2 Export Intent Runtime module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

from functools import wraps

from fastapi import File, Request, UploadFile


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
    "_proxy_factory",
    "bind",
    "install",
}


def bind(namespace: dict) -> None:
    for key, value in namespace.items():
        if key in _BIND_SKIP_NAMES:
            continue
        globals()[key] = value


def _proxy_factory(fn_name: str, namespace: dict):
    fn = globals()[fn_name]

    @wraps(fn)
    def _proxy(*args, **kwargs):
        bind(namespace)
        return fn(*args, **kwargs)

    _proxy._wa_runtime_proxy = True
    _proxy._wa_runtime_proxy_target_module = __name__
    _proxy._wa_runtime_proxy_target_name = fn_name
    return _proxy


def install(namespace: dict) -> None:
    bind(namespace)
    for fn_name in EXPORTED_FUNCTIONS:
        namespace[fn_name] = _proxy_factory(fn_name, namespace)

EXPORTED_FUNCTIONS = [
    "api_export_check",
    "_raise_export_blocking_error",
    "_auto_export_template_enabled",
    "_persist_export_autofix_enabled",
    "_resolve_export_template_path",
    "download_docx",
    "_resolve_soffice_path",
    "_convert_docx_to_pdf",
    "download_pdf",
    "export_multi_format",
    "_try_rust_docx_export",
    "_try_rust_import",
    "_library_item_payload",
    "_extract_json_block",
    "_quick_intent_guess",
]


def api_export_check(doc_id: str, format: str = "docx", auto_fix: int = 1) -> dict:
    from writing_agent.web.api.export_flow import export_check

    return export_check(doc_id, format=format, auto_fix=auto_fix)

def _raise_export_blocking_error(report: dict) -> None:
    if not isinstance(report, dict):
        return
    policy = str(report.get("policy") or "strict").strip().lower()
    if policy != "strict":
        return
    issues = report.get("issues")
    if not isinstance(issues, list):
        return
    blocking = [x for x in issues if isinstance(x, dict) and bool(x.get("blocking", True))]
    if not blocking:
        return
    summary = "; ".join(str(x.get("message") or x.get("code") or "unknown issue") for x in blocking[:4]).strip()
    raise HTTPException(
        status_code=400,
        detail=f"\u5bfc\u51fa\u524d\u6821\u9a8c\u672a\u901a\u8fc7\uff1a{summary or 'unknown issue'}",
    )

def _auto_export_template_enabled() -> bool:
    return export_settings_domain.auto_export_template_enabled()

def _persist_export_autofix_enabled() -> bool:
    return export_settings_domain.persist_export_autofix_enabled()

def _resolve_export_template_path(session) -> str:
    return export_settings_domain.resolve_export_template_path(
        session,
        repo_root=REPO_ROOT,
        template_dir=TEMPLATE_DIR,
        auto_export_template_enabled_fn=_auto_export_template_enabled,
    )

def download_docx(doc_id: str) -> StreamingResponse:
    from writing_agent.web.api.export_flow import download_docx as _download_docx

    return _download_docx(doc_id)

def _resolve_soffice_path() -> str | None:
    env = (
        os.environ.get("WRITING_AGENT_SOFFICE")
        or os.environ.get("SOFFICE_PATH")
        or os.environ.get("LIBREOFFICE_PATH")
    )
    if env:
        p = Path(env)
        if p.is_dir():
            cand = p / ("soffice.exe" if os.name == "nt" else "soffice")
            if cand.exists():
                return str(cand)
        if p.exists():
            return str(p)
    for name in ("soffice", "soffice.exe"):
        found = shutil.which(name)
        if found:
            return found
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "LibreOffice" / "program" / "soffice.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "LibreOffice" / "program" / "soffice.exe",
        ]
        for cand in candidates:
            if cand.exists():
                return str(cand)
    return None

def _convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> None:
    errors: list[str] = []
    if os.name == "nt":
        try:
            from docx2pdf import convert  # type: ignore
            convert(str(docx_path), str(pdf_path))
            if pdf_path.exists():
                return
        except Exception as e:
            errors.append(f"docx2pdf: {e}")
    soffice = _resolve_soffice_path()
    if not soffice:
        detail = "PDF 瀵煎嚭澶辫触锛氭湭鎵惧埌 LibreOffice"
        if errors:
            detail += "; " + "; ".join(errors)[:200]
        raise HTTPException(status_code=500, detail=detail)
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf_path.parent), str(docx_path)],
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0 or not pdf_path.exists():
        stderr = result.stderr.decode("utf-8", errors="ignore").strip()
        stdout = result.stdout.decode("utf-8", errors="ignore").strip()
        msg = stderr or stdout or "LibreOffice 杞崲澶辫触"
        raise HTTPException(status_code=500, detail=f"PDF 导出失败：{msg}")

def download_pdf(doc_id: str) -> StreamingResponse:
    from writing_agent.web.api.export_flow import download_pdf as _download_pdf

    return _download_pdf(doc_id)

def export_multi_format(doc_id: str, format: str) -> Response:
    from writing_agent.web.api.export_flow import export_multi_format as _export_multi_format

    return _export_multi_format(doc_id, format)

def _try_rust_docx_export(text: str) -> bytes | None:
    return try_rust_docx_export(text)

def _try_rust_import(path: Path) -> str | None:
    return try_rust_import(path)

def _library_item_payload(rec) -> dict:
    return {
        "doc_id": rec.doc_id,
        "title": rec.title,
        "status": rec.status,
        "source": rec.source,
        "source_id": rec.source_id,
        "source_name": rec.source_name,
        "char_count": rec.char_count,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
        "trash_until": rec.trash_until,
    }

def _extract_json_block(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return ""
    return m.group(0).strip()

def _quick_intent_guess(raw: str) -> dict:
    text = str(raw or "").strip()
    if not text:
        return {"name": "other", "confidence": 0.1, "reason": ""}
    compact = re.sub(r"\s+", "", text).lower()
    if re.search(r"(??|??|docx|pdf|word|export)", compact):
        return {"name": "export", "confidence": 0.6, "reason": "keyword: export"}
    if re.search(r"(??|??|??|??|??|??|??|??|??|??|??|??|??|??|??|??|modify|revise|edit)", compact):
        return {"name": "modify", "confidence": 0.6, "reason": "keyword: modify"}
    if re.search(r"(??|??|??|??|??|??|??|???|header|footer|template|format|style)", compact):
        return {"name": "template", "confidence": 0.55, "reason": "keyword: template"}
    if re.search(r"(??|??|??|??|upload|import)", compact):
        return {"name": "upload", "confidence": 0.55, "reason": "keyword: upload"}
    if re.search(r"(??|??|??|??|??|outline|section)", compact):
        return {"name": "outline", "confidence": 0.55, "reason": "keyword: outline"}
    if re.search(r"(??|??|??|??|??|generate|write|draft)", compact):
        return {"name": "generate", "confidence": 0.55, "reason": "keyword: generate"}
    if re.search(r"[??]", text):
        return {"name": "question", "confidence": 0.4, "reason": "contains question mark"}
    return {"name": "other", "confidence": 0.2, "reason": "fallback"}
