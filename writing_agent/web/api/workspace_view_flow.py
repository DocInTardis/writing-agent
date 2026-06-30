"""Workspace View Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from writing_agent.web.services.workspace_view_service import WorkspaceViewService

router = APIRouter()
service = WorkspaceViewService()


@router.get("/api/workspace-views")
def workspace_view_list_flow(
    status: str = "all",
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
    return {"ok": 1, "items": service.list_views(status=status, query=q, label=label, owner=owner, priority=priority, due_soon=due_soon, unassigned=unassigned, no_due_date=no_due_date, no_priority=no_priority, overdue=overdue, sort=sort)}


@router.post("/api/workspace-views/create")
async def workspace_view_create_flow(request: Request) -> dict:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be object")
    return service.create_view(
        name=str(body.get("name") or ""),
        status=str(body.get("status") or "all"),
        query=str(body.get("q") or ""),
        label=str(body.get("label") or ""),
        owner=str(body.get("owner") or ""),
        priority=str(body.get("priority") or ""),
        due_soon=body.get("due_soon"),
        unassigned=body.get("unassigned"),
        no_due_date=body.get("no_due_date"),
        no_priority=body.get("no_priority"),
        overdue=body.get("overdue"),
        sort=str(body.get("sort") or "updated"),
    )


@router.post("/api/workspace-views/{view_id}/delete")
def workspace_view_delete_flow(view_id: str) -> dict:
    return service.delete_view(view_id)
