"""Citation Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from writing_agent.web.services.citation_service import CitationService

router = APIRouter()
service = CitationService()


def get_citations(doc_id: str) -> dict:
    return service.get_citations(doc_id)


async def save_citations(doc_id: str, request: Request) -> dict:
    return await service.save_citations(doc_id, request)


async def verify_citations(doc_id: str, request: Request) -> dict:
    return await service.verify_citations(doc_id, request)


def metrics_citation_verify() -> dict:
    return service.metrics_citation_verify()


def metrics_citation_verify_alerts_config(request: Request) -> dict:
    return service.metrics_citation_verify_alerts_config(request)


async def metrics_citation_verify_alerts_config_save(request: Request) -> dict:
    return await service.metrics_citation_verify_alerts_config_save(request)


def metrics_citation_verify_alerts_events(request: Request, limit: int = 50) -> dict:
    return service.metrics_citation_verify_alerts_events(request, limit=limit)


def metrics_citation_verify_alerts_event_detail(request: Request, event_id: str, context: int = 12) -> dict:
    return service.metrics_citation_verify_alerts_event_detail(request, event_id=event_id, context=context)


def metrics_citation_verify_trends(limit: int = 120) -> dict:
    return service.metrics_citation_verify_trends(limit=limit)


@router.get("/api/doc/{doc_id}/citations")
def get_citations_flow(doc_id: str) -> dict:
    return get_citations(doc_id)


@router.post("/api/doc/{doc_id}/citations")
async def save_citations_flow(doc_id: str, request: Request) -> dict:
    return await save_citations(doc_id, request)


@router.post("/api/doc/{doc_id}/citations/verify")
async def verify_citations_flow(doc_id: str, request: Request) -> dict:
    return await verify_citations(doc_id, request)


@router.get("/api/metrics/citation_verify")
def metrics_citation_verify_flow() -> dict:
    return metrics_citation_verify()


@router.get("/api/metrics/citation_verify/alerts/config")
def metrics_citation_verify_alerts_config_flow(request: Request) -> dict:
    return metrics_citation_verify_alerts_config(request)


@router.post("/api/metrics/citation_verify/alerts/config")
async def metrics_citation_verify_alerts_config_save_flow(request: Request) -> dict:
    return await metrics_citation_verify_alerts_config_save(request)


@router.get("/api/metrics/citation_verify/alerts/events")
def metrics_citation_verify_alerts_events_flow(request: Request, limit: int = 50) -> dict:
    return metrics_citation_verify_alerts_events(request, limit=limit)


@router.get("/api/metrics/citation_verify/alerts/event/{event_id}")
def metrics_citation_verify_alerts_event_detail_flow(request: Request, event_id: str, context: int = 12) -> dict:
    return metrics_citation_verify_alerts_event_detail(request, event_id=event_id, context=context)


@router.get("/api/metrics/citation_verify/trends")
def metrics_citation_verify_trends_flow(limit: int = 120) -> dict:
    return metrics_citation_verify_trends(limit=limit)
