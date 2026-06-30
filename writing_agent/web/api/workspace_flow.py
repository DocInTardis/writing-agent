"""Workspace Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from writing_agent.web.services.workspace_service import WorkspaceService

router = APIRouter()
service = WorkspaceService()


@router.get("/api/workspaces")
def workspace_list_flow(
    status: str = "active",
    limit: int = 50,
    q: str = "",
    label: str = "",
    owner: str = "",
    priority: str = "",
    due_soon: str = "",
    unassigned: str = "",
    no_due_date: str = "",
    no_priority: str = "",
    overdue: str = "",
    sort: str = "updated",
) -> dict:
    return service.list_workspaces(status=status, limit=limit, query=q, label=label, owner=owner, priority=priority, due_soon=due_soon, unassigned=unassigned, no_due_date=no_due_date, no_priority=no_priority, overdue=overdue, sort=sort)


@router.get("/api/workspaces/activity")
def workspace_activity_flow(limit: int = 20, q: str = "") -> dict:
    return service.recent_activity(limit=limit, query=q)


@router.get("/api/workspaces/summary")
def workspace_summary_flow() -> dict:
    return service.dashboard_summary()


@router.post("/api/workspaces/batch")
async def workspace_batch_flow(request: Request) -> dict:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    raw_doc_ids = body.get("doc_ids")
    if not isinstance(raw_doc_ids, list):
        raise HTTPException(status_code=400, detail="doc_ids must be list")
    return service.batch_update(
        [str(item or "") for item in raw_doc_ids],
        action=str(body.get("action") or ""),
        status=str(body.get("status") or ""),
        labels=body.get("labels"),
        owner=body.get("owner"),
        priority=body.get("priority"),
        due_at=body.get("due_at", body.get("due_date")),
    )


@router.get("/api/workspaces/templates")
def workspace_template_list_flow() -> dict:
    return {"ok": 1, "items": service.built_in_templates()}


@router.post("/api/workspaces/create")
async def workspace_create_flow(request: Request) -> dict:
    template = ""
    try:
        body = await request.json()
    except Exception:
        import logging
        logging.getLogger(__name__).debug("workspace_create_flow: invalid JSON body, using empty payload", exc_info=True)
        body = {}
    if isinstance(body, dict):
        template = str(body.get("template") or "")
    return service.create_workspace(template=template)


@router.post("/api/workspaces/{doc_id}/duplicate")
def workspace_duplicate_flow(doc_id: str) -> dict:
    return service.duplicate_workspace(doc_id)


@router.post("/api/workspaces/{doc_id}/archive")
def workspace_archive_flow(doc_id: str) -> dict:
    return service.archive_workspace(doc_id)


@router.post("/api/workspaces/{doc_id}/trash")
def workspace_trash_flow(doc_id: str) -> dict:
    return service.trash_workspace(doc_id)


@router.post("/api/workspaces/{doc_id}/untrash")
def workspace_untrash_flow(doc_id: str) -> dict:
    return service.untrash_workspace(doc_id)


@router.post("/api/workspaces/{doc_id}/purge")
def workspace_purge_flow(doc_id: str) -> dict:
    return service.purge_workspace(doc_id)


@router.post("/api/workspaces/{doc_id}/restore")
def workspace_restore_flow(doc_id: str) -> dict:
    return service.restore_workspace(doc_id)


@router.post("/api/workspaces/{doc_id}/pin")
def workspace_pin_flow(doc_id: str) -> dict:
    return service.pin_workspace(doc_id, pinned=True)


@router.post("/api/workspaces/{doc_id}/unpin")
def workspace_unpin_flow(doc_id: str) -> dict:
    return service.pin_workspace(doc_id, pinned=False)


@router.post("/api/workspaces/{doc_id}/status")
async def workspace_status_flow(doc_id: str, request: Request) -> dict:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    return service.update_workspace(doc_id, title="", pinned=None, status=str(body.get("status") or ""))


@router.post("/api/workspaces/{doc_id}/update")
async def workspace_update_flow(doc_id: str, request: Request) -> dict:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    return service.update_workspace(
        doc_id,
        title=str(body.get("title") or ""),
        pinned=body.get("pinned"),
        status=str(body.get("status") or ""),
        labels=body["labels"] if "labels" in body else None,
        owner=body["owner"] if "owner" in body else None,
        priority=body["priority"] if "priority" in body else None,
        due_at=body.get("due_at", body.get("due_date")) if ("due_at" in body or "due_date" in body) else None,
    )
