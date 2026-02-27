"""Generation Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from writing_agent.web.services.generation_service import GenerationService

router = APIRouter()
service = GenerationService()


@router.post("/api/doc/{doc_id}/generate/stream")
async def generate_stream_flow(doc_id: str, request: Request) -> StreamingResponse:
    return await service.generate_stream(doc_id, request)


@router.post("/api/doc/{doc_id}/generate")
async def generate_flow(doc_id: str, request: Request) -> dict:
    return await generate(doc_id, request)


async def generate(doc_id: str, request: Request) -> dict:
    return await service.generate(doc_id, request)


async def generate_section(doc_id: str, request: Request) -> dict:
    return await service.generate_section(doc_id, request)


async def revise_doc(doc_id: str, request: Request) -> dict:
    return await service.revise_doc(doc_id, request)


@router.post("/api/doc/{doc_id}/generate/section")
async def generate_section_flow(doc_id: str, request: Request) -> dict:
    return await generate_section(doc_id, request)


@router.post("/api/doc/{doc_id}/revise")
async def revise_flow(doc_id: str, request: Request) -> dict:
    return await revise_doc(doc_id, request)

