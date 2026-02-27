"""Version Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from writing_agent.web.services.version_service import VersionService

router = APIRouter()
service = VersionService()


async def version_commit(doc_id: str, request: Request) -> dict:
    return await service.version_commit(doc_id, request)


def version_log(doc_id: str, branch: str = "main", limit: int = 50) -> dict:
    return service.version_log(doc_id, branch=branch, limit=limit)


def version_tree(doc_id: str) -> dict:
    return service.version_tree(doc_id)


async def version_checkout(doc_id: str, request: Request) -> dict:
    return await service.version_checkout(doc_id, request)


async def version_branch(doc_id: str, request: Request) -> dict:
    return await service.version_branch(doc_id, request)


def version_diff(doc_id: str, from_version: str, to_version: str) -> dict:
    return service.version_diff(doc_id, from_version=from_version, to_version=to_version)


async def version_tag(doc_id: str, request: Request) -> dict:
    return await service.version_tag(doc_id, request)


@router.post("/api/doc/{doc_id}/version/commit")
async def version_commit_flow(doc_id: str, request: Request) -> dict:
    return await version_commit(doc_id, request)


@router.get("/api/doc/{doc_id}/version/log")
def version_log_flow(doc_id: str, branch: str = "main", limit: int = 50) -> dict:
    return version_log(doc_id, branch=branch, limit=limit)


@router.get("/api/doc/{doc_id}/version/tree")
def version_tree_flow(doc_id: str) -> dict:
    return version_tree(doc_id)


@router.post("/api/doc/{doc_id}/version/checkout")
async def version_checkout_flow(doc_id: str, request: Request) -> dict:
    return await version_checkout(doc_id, request)


@router.post("/api/doc/{doc_id}/version/branch")
async def version_branch_flow(doc_id: str, request: Request) -> dict:
    return await version_branch(doc_id, request)


@router.get("/api/doc/{doc_id}/version/diff")
def version_diff_flow(doc_id: str, from_version: str, to_version: str) -> dict:
    return version_diff(doc_id, from_version=from_version, to_version=to_version)


@router.post("/api/doc/{doc_id}/version/tag")
async def version_tag_flow(doc_id: str, request: Request) -> dict:
    return await version_tag(doc_id, request)

