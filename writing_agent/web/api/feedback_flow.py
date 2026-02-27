"""Feedback Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from writing_agent.web.services.feedback_service import FeedbackService

router = APIRouter()
service = FeedbackService()


def get_chat(doc_id: str) -> dict:
    return service.get_chat(doc_id)


async def save_chat(doc_id: str, request: Request) -> dict:
    return await service.save_chat(doc_id, request)


def get_thoughts(doc_id: str) -> dict:
    return service.get_thoughts(doc_id)


async def save_thoughts(doc_id: str, request: Request) -> dict:
    return await service.save_thoughts(doc_id, request)


def get_feedback(doc_id: str) -> dict:
    return service.get_feedback(doc_id)


async def save_feedback(doc_id: str, request: Request) -> dict:
    return await service.save_feedback(doc_id, request)


def get_low_feedback(limit: int = 200) -> dict:
    return service.get_low_feedback(limit=limit)


@router.get("/api/doc/{doc_id}/chat")
def get_chat_flow(doc_id: str) -> dict:
    return get_chat(doc_id)


@router.post("/api/doc/{doc_id}/chat")
async def save_chat_flow(doc_id: str, request: Request) -> dict:
    return await save_chat(doc_id, request)


@router.get("/api/doc/{doc_id}/thoughts")
def get_thoughts_flow(doc_id: str) -> dict:
    return get_thoughts(doc_id)


@router.post("/api/doc/{doc_id}/thoughts")
async def save_thoughts_flow(doc_id: str, request: Request) -> dict:
    return await save_thoughts(doc_id, request)


@router.get("/api/doc/{doc_id}/feedback")
def get_feedback_flow(doc_id: str) -> dict:
    return get_feedback(doc_id)


@router.post("/api/doc/{doc_id}/feedback")
async def save_feedback_flow(doc_id: str, request: Request) -> dict:
    return await save_feedback(doc_id, request)


@router.get("/api/feedback/low")
def get_low_feedback_flow(limit: int = 200) -> dict:
    return get_low_feedback(limit=limit)
