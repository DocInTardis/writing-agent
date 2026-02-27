"""Quality Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import FileResponse

from writing_agent.web.domains import plagiarism_domain

from .base import app_v2_module


class QualityService:
    async def plagiarism_check(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        source_text = app_v2._safe_doc_text(session)
        if not str(source_text or "").strip():
            raise app_v2.HTTPException(status_code=400, detail="document is empty")

        data = await request.json()
        if not isinstance(data, dict):
            raise app_v2.HTTPException(status_code=400, detail="body must be object")

        threshold = plagiarism_domain.clamp_plagiarism_threshold(data.get("threshold"), default=0.35)
        top_k = max(1, min(100, int(data.get("top_k") or 10)))
        max_refs = max(1, min(80, int(data.get("max_references") or 40)))

        manual_refs = plagiarism_domain.normalize_plagiarism_reference_texts(data.get("reference_texts"))
        one_text = str(data.get("reference_text") or "").strip()
        if one_text:
            manual_refs.append({"id": "manual_text", "title": "manual_text", "text": one_text})
        doc_refs = plagiarism_domain.collect_plagiarism_doc_references(
            data.get("reference_doc_ids"),
            store=app_v2.store,
            safe_doc_text=app_v2._safe_doc_text,
            extract_title=app_v2._extract_title,
            exclude_doc_id=doc_id,
        )
        refs = plagiarism_domain.dedupe_plagiarism_references((manual_refs + doc_refs)[:max_refs])
        if not refs:
            raise app_v2.HTTPException(status_code=400, detail="no valid references provided")

        report = app_v2.compare_against_references(
            source_text,
            refs,
            threshold=threshold,
            top_k=top_k,
        )
        return {
            "ok": 1,
            "doc_id": doc_id,
            "checked_at": app_v2.time.time(),
            **report,
        }

    async def ai_rate_check(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        data = await request.json()
        if not isinstance(data, dict):
            raise app_v2.HTTPException(status_code=400, detail="body must be object")

        source_text = str(data.get("text") or "").strip() or app_v2._safe_doc_text(session)
        if not str(source_text or "").strip():
            raise app_v2.HTTPException(status_code=400, detail="document is empty")

        threshold = plagiarism_domain.clamp_ai_rate_threshold(data.get("threshold"), default=0.65)
        result = app_v2.estimate_ai_rate(source_text, threshold=threshold)
        payload = {
            "ok": 1,
            "doc_id": doc_id,
            "checked_at": app_v2.time.time(),
            **result,
        }
        app_v2._set_internal_pref(
            session,
            app_v2._AI_RATE_KEY,
            {
                "checked_at": payload.get("checked_at"),
                "ai_rate": payload.get("ai_rate"),
                "ai_rate_percent": payload.get("ai_rate_percent"),
                "threshold": payload.get("threshold"),
                "suspected_ai": payload.get("suspected_ai"),
                "risk_level": payload.get("risk_level"),
                "confidence": payload.get("confidence"),
                "signals": payload.get("signals", {}),
                "evidence": payload.get("evidence", []),
                "note": payload.get("note", ""),
            },
        )
        app_v2.store.put(session)
        return payload

    def ai_rate_latest(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        latest = app_v2._get_internal_pref(session, app_v2._AI_RATE_KEY, {}) or {}
        if not isinstance(latest, dict) or not latest:
            return {"ok": 1, "has_latest": False, "latest": {}}
        return {"ok": 1, "has_latest": True, "latest": latest}

    async def plagiarism_library_scan(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        source_text = app_v2._safe_doc_text(session)
        if not str(source_text or "").strip():
            raise app_v2.HTTPException(status_code=400, detail="document is empty")

        data = await request.json()
        if not isinstance(data, dict):
            raise app_v2.HTTPException(status_code=400, detail="body must be object")

        threshold = plagiarism_domain.clamp_plagiarism_threshold(data.get("threshold"), default=0.35)
        top_k = max(1, min(200, int(data.get("top_k") or 30)))
        max_docs = max(1, min(500, int(data.get("max_docs") or 120)))
        include_all_docs = bool(data.get("include_all_docs", True))

        manual_refs = plagiarism_domain.normalize_plagiarism_reference_texts(data.get("reference_texts"))
        one_text = str(data.get("reference_text") or "").strip()
        if one_text:
            manual_refs.append({"id": "manual_text", "title": "manual_text", "text": one_text})

        ref_doc_ids: list[str] = []
        if include_all_docs:
            ref_doc_ids = [sid for sid, _ in app_v2.store.items() if sid != doc_id]
        elif isinstance(data.get("reference_doc_ids"), list):
            ref_doc_ids = [str(x or "").strip() for x in data.get("reference_doc_ids") if str(x or "").strip()]

        doc_refs = plagiarism_domain.collect_plagiarism_doc_references(
            ref_doc_ids,
            store=app_v2.store,
            safe_doc_text=app_v2._safe_doc_text,
            extract_title=app_v2._extract_title,
            exclude_doc_id=doc_id,
            max_count=max_docs,
            min_chars=20,
        )
        refs = plagiarism_domain.dedupe_plagiarism_references((manual_refs + doc_refs)[: max_docs + 40])
        if not refs:
            raise app_v2.HTTPException(status_code=400, detail="no valid references provided")

        scan_report = app_v2.compare_against_references(
            source_text,
            refs,
            threshold=threshold,
            top_k=top_k,
        )

        payload = {
            "doc_id": doc_id,
            "report_id": plagiarism_domain.new_plagiarism_report_id(),
            "created_at": app_v2.time.time(),
            "threshold": threshold,
            "source_chars": scan_report.get("source_chars"),
            "total_references": scan_report.get("total_references"),
            "flagged_count": scan_report.get("flagged_count"),
            "max_score": scan_report.get("max_score"),
            "suspected": scan_report.get("suspected"),
            "results": scan_report.get("results", []),
            "config": scan_report.get("config", {}),
            "options": {
                "include_all_docs": include_all_docs,
                "requested_top_k": top_k,
                "requested_max_docs": max_docs,
                "manual_reference_count": len(manual_refs),
                "doc_reference_count": len(doc_refs),
            },
        }
        persisted = plagiarism_domain.persist_plagiarism_report(
            doc_id,
            payload,
            report_root=app_v2.PLAGIARISM_REPORT_DIR,
        )
        payload["report_id"] = persisted["report_id"]
        payload["paths"] = {
            "json": persisted["json_path"],
            "markdown": persisted["md_path"],
            "csv": persisted["csv_path"],
        }

        app_v2._set_internal_pref(
            session,
            app_v2._PLAGIARISM_SCAN_KEY,
            {
                "report_id": payload.get("report_id"),
                "created_at": payload.get("created_at"),
                "threshold": payload.get("threshold"),
                "source_chars": payload.get("source_chars"),
                "flagged_count": payload.get("flagged_count"),
                "max_score": payload.get("max_score"),
                "total_references": payload.get("total_references"),
                "suspected": payload.get("suspected"),
                "paths": payload.get("paths", {}),
            },
        )
        app_v2.store.put(session)

        return {"ok": 1, **payload}

    def plagiarism_library_scan_latest(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        latest = app_v2._get_internal_pref(session, app_v2._PLAGIARISM_SCAN_KEY, {}) or {}
        if not isinstance(latest, dict) or not latest:
            return {"ok": 1, "has_report": False, "latest": {}}
        return {"ok": 1, "has_report": True, "latest": latest}

    def plagiarism_library_scan_download(self, doc_id: str, report_id: str, format: str = "json") -> FileResponse:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        rid = plagiarism_domain.safe_plagiarism_report_id(report_id)
        if not rid:
            raise app_v2.HTTPException(status_code=400, detail="invalid report_id")
        fmt = str(format or "json").strip().lower()
        if fmt not in {"json", "md", "csv"}:
            raise app_v2.HTTPException(status_code=400, detail="format must be one of: json, md, csv")
        path = plagiarism_domain.plagiarism_report_doc_dir(doc_id, report_root=app_v2.PLAGIARISM_REPORT_DIR) / f"{rid}.{fmt}"
        if not path.exists():
            raise app_v2.HTTPException(status_code=404, detail="report file not found")
        media = "application/json"
        if fmt == "md":
            media = "text/markdown; charset=utf-8"
        elif fmt == "csv":
            media = "text/csv; charset=utf-8"
        return FileResponse(str(path), media_type=media, filename=path.name)
