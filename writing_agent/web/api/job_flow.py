"""Job Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from writing_agent.web.contracts import JobPollResponse, JobSubmitRequest, JobSubmitResponse
from writing_agent.web.services.audit_service import AuditService
from writing_agent.web.services.job_service import JobService
from writing_agent.web.services.rbac_service import RBACService

router = APIRouter()
service = JobService()
rbac = RBACService()
audit = AuditService()


def _role(request: Request) -> str:
    return str(request.headers.get("x-role") or "viewer").strip().lower() or "viewer"


def _tenant(request: Request) -> str:
    return str(request.headers.get("x-tenant-id") or "default").strip() or "default"


@router.post("/api/v1/jobs/submit")
async def job_submit(request: Request) -> JobSubmitResponse:
    role = _role(request)
    if not rbac.allow(role=role, action="job:write"):
        raise HTTPException(status_code=403, detail="forbidden")
    body = await request.json()
    payload = JobSubmitRequest.model_validate(body if isinstance(body, dict) else {})
    row = service.submit(job_type=payload.type, payload=payload.payload, callback_url=payload.callback_url)
    audit.append(actor=role, action="job_submit", tenant_id=_tenant(request), payload={"job_id": row.job_id, "type": row.type})
    return JobSubmitResponse(ok=1, job_id=row.job_id, status=row.status)


@router.get("/api/v1/jobs/{job_id}")
def job_poll(job_id: str, request: Request) -> JobPollResponse:
    role = _role(request)
    if not rbac.allow(role=role, action="job:read"):
        raise HTTPException(status_code=403, detail="forbidden")
    row = service.get(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobPollResponse(ok=1, job_id=row.job_id, status=row.status, result=row.result)


@router.get("/api/v1/jobs")
def job_list(request: Request, limit: int = 50) -> dict:
    role = _role(request)
    if not rbac.allow(role=role, action="job:read"):
        raise HTTPException(status_code=403, detail="forbidden")
    rows = service.list(limit=limit)
    return {
        "ok": 1,
        "items": [
            {
                "job_id": row.job_id,
                "type": row.type,
                "status": row.status,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ],
    }
