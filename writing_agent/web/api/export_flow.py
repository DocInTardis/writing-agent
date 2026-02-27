"""Export Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse

from writing_agent.web.services.export_service import ExportService

router = APIRouter()
service = ExportService()


def export_check(doc_id: str, format: str = "docx", auto_fix: int = 1) -> dict:
    return service.export_check(doc_id, format=format, auto_fix=auto_fix)


@router.get("/api/doc/{doc_id}/export/check")
def export_check_flow(doc_id: str, format: str = "docx", auto_fix: int = 1) -> dict:
    return export_check(doc_id, format=format, auto_fix=auto_fix)


@router.get("/download/{doc_id}.docx")
def download_docx_flow(doc_id: str) -> StreamingResponse:
    return service.download_docx(doc_id)


@router.get("/download/{doc_id}.pdf")
def download_pdf_flow(doc_id: str) -> StreamingResponse:
    return service.download_pdf(doc_id)


@router.get("/export/{doc_id}/{format}")
def export_multi_format_flow(doc_id: str, format: str) -> Response:
    return service.export_multi_format(doc_id, format)
