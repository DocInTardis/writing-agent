"""System Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter

from writing_agent.web.services.system_service import SystemService

router = APIRouter()
service = SystemService()


@router.get("/healthz")
def healthz_flow() -> dict:
    return service.healthz()


@router.get("/api/system/status")
def system_status_flow() -> dict:
    return service.system_status()
