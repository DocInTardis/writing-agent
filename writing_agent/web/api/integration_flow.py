"""Integration Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from writing_agent.web.contracts import WebhookEvent
from writing_agent.web.services.audit_service import AuditService
from writing_agent.web.services.integration_service import IntegrationService
from writing_agent.web.services.rbac_service import RBACService

router = APIRouter()
service = IntegrationService()
rbac = RBACService()
audit = AuditService()


def _role(request: Request) -> str:
    return str(request.headers.get("x-role") or "viewer").strip().lower() or "viewer"


def _tenant(request: Request) -> str:
    return str(request.headers.get("x-tenant-id") or "default").strip() or "default"


@router.post("/api/v1/integration/events")
async def publish_event(request: Request) -> dict:
    role = _role(request)
    if not rbac.allow(role=role, action="event:write"):
        raise HTTPException(status_code=403, detail="forbidden")
    body = await request.json()
    event = WebhookEvent.model_validate(body if isinstance(body, dict) else {})
    payload = event.model_copy(update={"tenant_id": event.tenant_id or _tenant(request)})
    result = service.publish_event(payload)
    audit.append(actor=role, action="event_publish", tenant_id=payload.tenant_id, payload={"event_type": payload.event_type})
    return result


@router.get("/api/v1/integration/events")
def list_events(request: Request, limit: int = 50) -> dict:
    role = _role(request)
    if not rbac.allow(role=role, action="event:read"):
        raise HTTPException(status_code=403, detail="forbidden")
    return service.list_events(limit=limit, tenant_id=_tenant(request))
