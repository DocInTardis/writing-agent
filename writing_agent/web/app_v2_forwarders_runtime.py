"""App V2 Forwarders Runtime module.

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
    "api_get_doc",
    "api_get_chat",
    "api_save_chat",
    "api_get_thoughts",
    "api_get_text_block",
    "api_save_thoughts",
    "api_get_feedback",
    "api_save_feedback",
    "api_get_low_feedback",
    "api_doc_plagiarism_check",
    "api_doc_ai_rate_check",
    "api_doc_ai_rate_latest",
    "api_doc_plagiarism_library_scan",
    "api_doc_plagiarism_library_scan_latest",
    "api_doc_plagiarism_library_scan_download",
    "api_get_citations",
    "api_save_citations",
    "_verify_one_citation",
    "_citation_payload",
    "api_verify_citations",
    "api_metrics_citation_verify",
    "api_metrics_citation_verify_alerts_config",
    "api_metrics_citation_verify_alerts_config_save",
    "api_metrics_citation_verify_alerts_events",
    "api_metrics_citation_verify_alerts_event_detail",
    "api_metrics_citation_verify_trends",
    "api_save_doc",
    "api_import_doc",
    "api_save_settings",
    "api_analyze_message",
    "api_extract_prefs",
    "api_upload_template",
    "api_clear_template",
    "api_doc_upload",
    "api_doc_upload_clarify",
    "api_generate_stream",
    "api_generate",
    "api_generate_section",
    "api_revise_doc",
    "api_doc_ir_ops",
    "api_doc_ir_diff",
    "api_render_figure",
    "api_diagram_generate",
    "api_inline_ai",
    "api_inline_ai_stream",
    "api_block_edit",
    "api_block_edit_preview",
    "api_rag_arxiv_ingest",
    "api_rag_list_papers",
    "api_rag_search",
    "api_rag_retrieve",
    "api_rag_index_rebuild",
    "api_rag_search_chunks",
    "api_rag_get_pdf",
    "api_library_upload",
    "api_library_items",
    "api_library_item",
    "api_library_approve",
    "api_library_restore",
    "api_library_trash",
    "api_library_update",
    "api_library_delete",
    "api_library_from_doc",
    "api_rag_ingest",
    "api_rag_stats",
    "api_docs_list",
]


def api_get_doc(doc_id: str) -> dict:
    from writing_agent.web.api.document_flow import get_doc

    return get_doc(doc_id)

def api_get_chat(doc_id: str) -> dict:
    from writing_agent.web.api.feedback_flow import get_chat

    return get_chat(doc_id)

async def api_save_chat(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.feedback_flow import save_chat

    return await save_chat(doc_id, request)

def api_get_thoughts(doc_id: str) -> dict:
    from writing_agent.web.api.feedback_flow import get_thoughts

    return get_thoughts(doc_id)

def api_get_text_block(block_id: str) -> dict:
    from writing_agent.web.api.document_flow import get_text_block

    return get_text_block(block_id)

async def api_save_thoughts(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.feedback_flow import save_thoughts

    return await save_thoughts(doc_id, request)

def api_get_feedback(doc_id: str) -> dict:
    from writing_agent.web.api.feedback_flow import get_feedback

    return get_feedback(doc_id)

async def api_save_feedback(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.feedback_flow import save_feedback

    return await save_feedback(doc_id, request)

def api_get_low_feedback(limit: int = 200) -> dict:
    from writing_agent.web.api.feedback_flow import get_low_feedback

    return get_low_feedback(limit=limit)

async def api_doc_plagiarism_check(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.quality_flow import plagiarism_check

    return await plagiarism_check(doc_id, request)

async def api_doc_ai_rate_check(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.quality_flow import ai_rate_check

    return await ai_rate_check(doc_id, request)

def api_doc_ai_rate_latest(doc_id: str) -> dict:
    from writing_agent.web.api.quality_flow import ai_rate_latest

    return ai_rate_latest(doc_id)

async def api_doc_plagiarism_library_scan(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.quality_flow import plagiarism_library_scan

    return await plagiarism_library_scan(doc_id, request)

def api_doc_plagiarism_library_scan_latest(doc_id: str) -> dict:
    from writing_agent.web.api.quality_flow import plagiarism_library_scan_latest

    return plagiarism_library_scan_latest(doc_id)

def api_doc_plagiarism_library_scan_download(doc_id: str, report_id: str, format: str = "json") -> FileResponse:
    from writing_agent.web.api.quality_flow import plagiarism_library_scan_download

    return plagiarism_library_scan_download(doc_id, report_id=report_id, format=format)

def api_get_citations(doc_id: str) -> dict:
    from writing_agent.web.api.citation_flow import get_citations

    return get_citations(doc_id)

async def api_save_citations(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.citation_flow import save_citations

    return await save_citations(doc_id, request)

def _verify_one_citation(cite: Citation) -> tuple[dict, Citation]:
    item, next_cite, _ = _verify_one_citation_detail(cite)
    return item, next_cite

def _citation_payload(cite: Citation) -> dict:
    return {
        "id": cite.key,
        "author": cite.authors or "",
        "title": cite.title or "",
        "year": cite.year or "",
        "source": cite.venue or cite.url or "",
    }

async def api_verify_citations(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.citation_flow import verify_citations

    return await verify_citations(doc_id, request)

def api_metrics_citation_verify() -> dict:
    from writing_agent.web.api.citation_flow import metrics_citation_verify

    return metrics_citation_verify()

def api_metrics_citation_verify_alerts_config(request: Request) -> dict:
    from writing_agent.web.api.citation_flow import metrics_citation_verify_alerts_config

    return metrics_citation_verify_alerts_config(request)

async def api_metrics_citation_verify_alerts_config_save(request: Request) -> dict:
    from writing_agent.web.api.citation_flow import metrics_citation_verify_alerts_config_save

    return await metrics_citation_verify_alerts_config_save(request)

def api_metrics_citation_verify_alerts_events(request: Request, limit: int = 50) -> dict:
    from writing_agent.web.api.citation_flow import metrics_citation_verify_alerts_events

    return metrics_citation_verify_alerts_events(request, limit=limit)

def api_metrics_citation_verify_alerts_event_detail(request: Request, event_id: str, context: int = 12) -> dict:
    from writing_agent.web.api.citation_flow import metrics_citation_verify_alerts_event_detail

    return metrics_citation_verify_alerts_event_detail(request, event_id=event_id, context=context)

def api_metrics_citation_verify_trends(limit: int = 120) -> dict:
    from writing_agent.web.api.citation_flow import metrics_citation_verify_trends

    return metrics_citation_verify_trends(limit=limit)

async def api_save_doc(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.template_flow import save_doc

    return await save_doc(doc_id, request)

async def api_import_doc(doc_id: str, file: UploadFile = File(...)) -> dict:
    from writing_agent.web.api.template_flow import import_doc

    return await import_doc(doc_id, file)

async def api_save_settings(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.template_flow import save_settings

    return await save_settings(doc_id, request)

async def api_analyze_message(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.template_flow import analyze_message

    return await analyze_message(doc_id, request)

async def api_extract_prefs(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.template_flow import extract_prefs

    return await extract_prefs(doc_id, request)

async def api_upload_template(doc_id: str, file: UploadFile = File(...)) -> dict:
    from writing_agent.web.api.template_flow import upload_template

    return await upload_template(doc_id, file)

async def api_clear_template(doc_id: str) -> dict:
    from writing_agent.web.api.template_flow import clear_template

    return await clear_template(doc_id)

async def api_doc_upload(doc_id: str, file: UploadFile = File(...)) -> dict:
    from writing_agent.web.api.template_flow import doc_upload

    return await doc_upload(doc_id, file)

async def api_doc_upload_clarify(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.template_flow import doc_upload_clarify

    return await doc_upload_clarify(doc_id, request)

async def api_generate_stream(doc_id: str, request: Request) -> StreamingResponse:
    from writing_agent.web import app_v2_generate_stream_runtime as _generate_stream_runtime

    _generate_stream_runtime.bind(globals())
    return await _generate_stream_runtime.api_generate_stream(doc_id, request)

async def api_generate(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.generation_flow import generate

    return await generate(doc_id, request)

async def api_generate_section(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.generation_flow import generate_section

    return await generate_section(doc_id, request)

async def api_revise_doc(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.generation_flow import revise_doc

    return await revise_doc(doc_id, request)

async def api_doc_ir_ops(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.editing_flow import doc_ir_ops

    return await doc_ir_ops(doc_id, request)

async def api_doc_ir_diff(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.editing_flow import doc_ir_diff

    return await doc_ir_diff(doc_id, request)

async def api_render_figure(request: Request) -> dict:
    from writing_agent.web.api.editing_flow import render_figure

    return await render_figure(request)

async def api_diagram_generate(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.editing_flow import diagram_generate

    return await diagram_generate(doc_id, request)

async def api_inline_ai(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.editing_flow import inline_ai

    return await inline_ai(doc_id, request)

async def api_inline_ai_stream(doc_id: str, request: Request) -> StreamingResponse:
    from writing_agent.web.api.editing_flow import inline_ai_stream

    return await inline_ai_stream(doc_id, request)

async def api_block_edit(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.editing_flow import block_edit

    return await block_edit(doc_id, request)

async def api_block_edit_preview(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.editing_flow import block_edit_preview

    return await block_edit_preview(doc_id, request)

async def api_rag_arxiv_ingest(request: Request) -> dict:
    from writing_agent.web.api.rag_flow import rag_arxiv_ingest

    return await rag_arxiv_ingest(request)

def api_rag_list_papers() -> dict:
    from writing_agent.web.api.rag_flow import rag_list_papers

    return rag_list_papers()

async def api_rag_search(request: Request) -> dict:
    from writing_agent.web.api.rag_flow import rag_search

    return await rag_search(request)

async def api_rag_retrieve(request: Request) -> dict:
    from writing_agent.web.api.rag_flow import rag_retrieve

    return await rag_retrieve(request)

async def api_rag_index_rebuild(request: Request) -> dict:
    from writing_agent.web.api.rag_flow import rag_index_rebuild

    return await rag_index_rebuild(request)

async def api_rag_search_chunks(request: Request) -> dict:
    from writing_agent.web.api.rag_flow import rag_search_chunks

    return await rag_search_chunks(request)

def api_rag_get_pdf(paper_id: str) -> FileResponse:
    from writing_agent.web.api.rag_flow import rag_get_pdf

    return rag_get_pdf(paper_id)

async def api_library_upload(file: UploadFile = File(...)) -> dict:
    from writing_agent.web.api.rag_flow import library_upload

    return await library_upload(file)

def api_library_items(status: str = "") -> dict:
    from writing_agent.web.api.rag_flow import library_items

    return library_items(status=status)

def api_library_item(doc_id: str) -> dict:
    from writing_agent.web.api.rag_flow import library_item

    return library_item(doc_id)

def api_library_approve(doc_id: str) -> dict:
    from writing_agent.web.api.rag_flow import library_approve

    return library_approve(doc_id)

def api_library_restore(doc_id: str) -> dict:
    from writing_agent.web.api.rag_flow import library_restore

    return library_restore(doc_id)

def api_library_trash(doc_id: str) -> dict:
    from writing_agent.web.api.rag_flow import library_trash

    return library_trash(doc_id)

async def api_library_update(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.rag_flow import library_update

    return await library_update(doc_id, request)

def api_library_delete(doc_id: str) -> dict:
    from writing_agent.web.api.rag_flow import library_delete

    return library_delete(doc_id)

async def api_library_from_doc(request: Request) -> dict:
    from writing_agent.web.api.rag_flow import library_from_doc

    return await library_from_doc(request)

async def api_rag_ingest(request: Request) -> dict:
    from writing_agent.web.api.rag_flow import rag_ingest

    return await rag_ingest(request)

def api_rag_stats() -> dict:
    from writing_agent.web.api.rag_flow import rag_stats

    return rag_stats()

def api_docs_list() -> dict:
    from writing_agent.web.api.document_flow import docs_list

    return docs_list()
