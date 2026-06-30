"""Document Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter

from writing_agent.web.services.document_service import DocumentService

router = APIRouter()
service = DocumentService()


def get_doc(doc_id: str) -> dict:
    return service.get_doc(doc_id)


def get_text_block(block_id: str) -> dict:
    return service.get_text_block(block_id)


def _guess_block_kind(block_id: str) -> str:
    return service._guess_block_kind(block_id)


def docs_list(
    status: str = "active",
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
    return service.docs_list(status=status, query=q, label=label, owner=owner, priority=priority, due_soon=due_soon, unassigned=unassigned, no_due_date=no_due_date, no_priority=no_priority, overdue=overdue, sort=sort)


def doc_delete(doc_id: str) -> dict:
    return service.doc_delete(doc_id)


@router.get("/api/doc/{doc_id}")
def get_doc_flow(doc_id: str) -> dict:
    return get_doc(doc_id)


@router.get("/api/text/{block_id}")
def get_text_block_flow(block_id: str) -> dict:
    return get_text_block(block_id)


@router.get("/api/docs/list")
def docs_list_flow(
    status: str = "active",
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
    return docs_list(status=status, q=q, label=label, owner=owner, priority=priority, due_soon=due_soon, unassigned=unassigned, no_due_date=no_due_date, no_priority=no_priority, overdue=overdue, sort=sort)


@router.post("/api/doc/{doc_id}/delete")
def doc_delete_flow(doc_id: str) -> dict:
    return doc_delete(doc_id)
