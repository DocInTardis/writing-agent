"""LLM Config Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from writing_agent.web.services.llm_config_service import LLMConfigService

router = APIRouter()
service = LLMConfigService()


@router.get("/api/llm/presets")
def list_presets() -> dict:
    return {"ok": True, "presets": service.list_presets()}


@router.get("/api/llm/config")
def get_config() -> dict:
    return {"ok": True, "config": service.get_config()}


@router.post("/api/llm/config/active")
def set_active_provider(data: dict) -> dict:
    provider_id = str(data.get("provider_id", "")).strip()
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id is required")
    return {"ok": True, "config": service.set_active_provider(provider_id)}


@router.post("/api/llm/config/provider")
def add_or_update_provider(data: dict) -> dict:
    try:
        return {"ok": True, "config": service.add_or_update_provider(data)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/llm/config/provider/delete")
def remove_provider(data: dict) -> dict:
    provider_id = str(data.get("provider_id", "")).strip()
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id is required")
    return {"ok": True, "config": service.remove_provider(provider_id)}


@router.post("/api/llm/config/test")
def test_provider(data: dict) -> dict:
    result = service.test_provider(data)
    return {"ok": result.get("ok", False), **result}
