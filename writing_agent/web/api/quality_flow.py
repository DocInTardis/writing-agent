"""Quality Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from writing_agent.web.services.quality_service import QualityService

router = APIRouter()
service = QualityService()


async def plagiarism_check(doc_id: str, request: Request) -> dict:
    return await service.plagiarism_check(doc_id, request)


async def ai_rate_check(doc_id: str, request: Request) -> dict:
    return await service.ai_rate_check(doc_id, request)


def ai_rate_latest(doc_id: str) -> dict:
    return service.ai_rate_latest(doc_id)


async def plagiarism_library_scan(doc_id: str, request: Request) -> dict:
    return await service.plagiarism_library_scan(doc_id, request)


def plagiarism_library_scan_latest(doc_id: str) -> dict:
    return service.plagiarism_library_scan_latest(doc_id)


def plagiarism_library_scan_download(doc_id: str, report_id: str, format: str = "json") -> FileResponse:
    return service.plagiarism_library_scan_download(doc_id, report_id=report_id, format=format)


@router.post("/api/doc/{doc_id}/plagiarism/check")
async def plagiarism_check_flow(doc_id: str, request: Request) -> dict:
    return await plagiarism_check(doc_id, request)


@router.post("/api/doc/{doc_id}/ai_rate/check")
async def ai_rate_check_flow(doc_id: str, request: Request) -> dict:
    return await ai_rate_check(doc_id, request)


@router.get("/api/doc/{doc_id}/ai_rate/latest")
def ai_rate_latest_flow(doc_id: str) -> dict:
    return ai_rate_latest(doc_id)


@router.post("/api/doc/{doc_id}/plagiarism/library_scan")
async def plagiarism_library_scan_flow(doc_id: str, request: Request) -> dict:
    return await plagiarism_library_scan(doc_id, request)


@router.get("/api/doc/{doc_id}/plagiarism/library_scan/latest")
def plagiarism_library_scan_latest_flow(doc_id: str) -> dict:
    return plagiarism_library_scan_latest(doc_id)


@router.get("/api/doc/{doc_id}/plagiarism/library_scan/download")
def plagiarism_library_scan_download_flow(doc_id: str, report_id: str, format: str = "json") -> FileResponse:
    return plagiarism_library_scan_download(doc_id, report_id=report_id, format=format)
