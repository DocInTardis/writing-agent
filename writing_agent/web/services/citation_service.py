"""Citation Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import Request

from .base import app_v2_module


class CitationService:
    def get_citations(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        items: list[dict] = []
        for key, cite in (session.citations or {}).items():
            items.append(
                {
                    "id": key,
                    "author": cite.authors or "",
                    "title": cite.title or "",
                    "year": cite.year or "",
                    "source": cite.venue or cite.url or "",
                }
            )
        return {"items": items}

    async def save_citations(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        data = await request.json()
        items = data.get("items") if isinstance(data, dict) else None
        session.citations = app_v2._normalize_citation_items(items)
        app_v2.store.put(session)
        return {"ok": 1, "count": len(session.citations or {})}

    async def verify_citations(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        req_started = app_v2.time.perf_counter()
        cache_before = app_v2._citation_verify_cache_metrics_snapshot()
        try:
            data = await request.json()
        except Exception:
            data = {}

        items = data.get("items") if isinstance(data, dict) else None
        persist = bool(data.get("persist", True)) if isinstance(data, dict) else True
        debug_enabled = bool(data.get("debug", False)) if isinstance(data, dict) else False
        if not debug_enabled:
            debug_enabled = str(app_v2.os.environ.get("WRITING_AGENT_CITATION_VERIFY_DEBUG", "")).strip() == "1"
        requested_debug_level = app_v2._normalize_verify_debug_level(data.get("debug_level") if isinstance(data, dict) else "")
        debug_level = requested_debug_level
        rate_limited_full = False
        if debug_enabled and debug_level == "full":
            if not app_v2._allow_full_debug(doc_id):
                debug_level = "safe"
                rate_limited_full = True
        source_citations = app_v2._normalize_citation_items(items) if isinstance(items, list) else dict(session.citations or {})
        worker_count = 0
        if not source_citations:
            empty = {
                "ok": 1,
                "items": [],
                "updated_items": [],
                "summary": {"total": 0, "verified": 0, "possible": 0, "not_found": 0, "error": 0},
            }
            elapsed_ms = round((app_v2.time.perf_counter() - req_started) * 1000.0, 2)
            cache_after = app_v2._citation_verify_cache_metrics_snapshot()
            request_observe = app_v2._citation_verify_observe_record(
                elapsed_ms=elapsed_ms,
                item_count=0,
                worker_count=0,
                error_count=0,
                cache_before=cache_before,
                cache_after=cache_after,
            )
            observe_snapshot = app_v2._citation_verify_observe_snapshot()
            if debug_enabled:
                empty["debug"] = app_v2._build_citation_verify_debug_payload(
                    persist=persist,
                    input_count=0,
                    worker_count=0,
                    elapsed_ms=elapsed_ms,
                    requested_level=requested_debug_level,
                    debug_level=debug_level,
                    rate_limited_full=rate_limited_full,
                    debug_items=[],
                    request_observe=request_observe,
                    observe_snapshot=observe_snapshot,
                )
            return empty

        results, updated, debug_items, worker_count = app_v2._verify_citation_batch(source_citations, debug_enabled=debug_enabled)

        summary = {"total": len(results), "verified": 0, "possible": 0, "not_found": 0, "error": 0}
        for item in results:
            status = str(item.get("status") or "")
            if status == "verified":
                summary["verified"] += 1
            elif status == "possible":
                summary["possible"] += 1
            elif status == "error":
                summary["error"] += 1
            else:
                summary["not_found"] += 1

        if persist:
            session.citations = updated
            app_v2._set_internal_pref(
                session,
                app_v2._CITATION_VERIFY_KEY,
                {
                    "updated_at": app_v2.time.time(),
                    "items": {str(item.get("id") or ""): item for item in results if str(item.get("id") or "")},
                    "summary": summary,
                },
            )
            app_v2.store.put(session)

        elapsed_ms = round((app_v2.time.perf_counter() - req_started) * 1000.0, 2)
        cache_after = app_v2._citation_verify_cache_metrics_snapshot()
        request_observe = app_v2._citation_verify_observe_record(
            elapsed_ms=elapsed_ms,
            item_count=len(results),
            worker_count=worker_count,
            error_count=int(summary.get("error") or 0),
            cache_before=cache_before,
            cache_after=cache_after,
        )
        observe_snapshot = app_v2._citation_verify_observe_snapshot()

        updated_items = [app_v2._citation_payload(cite) for cite in updated.values()]
        response = {"ok": 1, "items": results, "updated_items": updated_items, "summary": summary}
        if debug_enabled:
            response["debug"] = app_v2._build_citation_verify_debug_payload(
                persist=persist,
                input_count=len(source_citations),
                worker_count=worker_count,
                elapsed_ms=elapsed_ms,
                requested_level=requested_debug_level,
                debug_level=debug_level,
                rate_limited_full=rate_limited_full,
                debug_items=debug_items,
                request_observe=request_observe,
                observe_snapshot=observe_snapshot,
            )
        return response

    def metrics_citation_verify(self) -> dict:
        app_v2 = app_v2_module()

        return app_v2._safe_citation_verify_metrics_payload()

    def metrics_citation_verify_alerts_config(self, request: Request) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        config = app_v2._citation_verify_alerts_config_effective()
        return {"ok": 1, "config": config, "source": app_v2._citation_verify_alerts_config_source()}

    async def metrics_citation_verify_alerts_config_save(self, request: Request) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.write")
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            raise app_v2.HTTPException(status_code=400, detail="body must be object")
        if bool(data.get("reset")):
            config = app_v2._citation_verify_alerts_config_reset()
            return {"ok": 1, "config": config, "source": "env", "reset": True}
        payload = data.get("config") if isinstance(data.get("config"), dict) else data
        config = app_v2._citation_verify_alerts_config_save(payload)
        return {"ok": 1, "config": config, "source": "file", "reset": False}

    def metrics_citation_verify_alerts_events(self, request: Request, limit: int = 50) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        snapshot = app_v2._citation_verify_alert_events_snapshot(limit=limit)
        return {"ok": 1, **snapshot}

    def metrics_citation_verify_alerts_event_detail(self, request: Request, event_id: str, context: int = 12) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        event = app_v2._citation_verify_alert_event_get(event_id)
        if not isinstance(event, dict):
            raise app_v2.HTTPException(status_code=404, detail="event not found")
        trend_context = app_v2._citation_verify_metrics_trend_context(ts=float(event.get("ts") or 0.0), limit=context)
        return {"ok": 1, "event": event, "trend_context": trend_context}

    def metrics_citation_verify_trends(self, limit: int = 120) -> dict:
        app_v2 = app_v2_module()

        snapshot = app_v2._citation_verify_metrics_trends_snapshot(limit=limit)
        return {"ok": 1, **snapshot}

