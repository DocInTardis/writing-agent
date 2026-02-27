"""Feedback Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import Request

from .base import app_v2_module


class FeedbackService:
    def get_chat(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        meta = app_v2._load_meta(doc_id)
        return {"items": meta.get("chat", [])}

    async def save_chat(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        data = await request.json()
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise app_v2.HTTPException(status_code=400, detail="items must be list")
        cleaned: list[dict] = []
        for item in items[-200:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            text = str(item.get("text") or "").strip()
            if not role or not text:
                continue
            cleaned.append({"role": role, "text": text})
        session.chat_log = cleaned
        app_v2.store.put(session)
        app_v2._save_meta(doc_id, chat=cleaned)
        return {"ok": 1}

    def get_thoughts(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        meta = app_v2._load_meta(doc_id)
        return {"items": meta.get("thoughts", [])}

    async def save_thoughts(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        data = await request.json()
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise app_v2.HTTPException(status_code=400, detail="items must be list")
        cleaned: list[dict] = []
        for item in items[-200:]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            detail = str(item.get("detail") or "").strip()
            time_str = str(item.get("time") or "").strip()
            if not label:
                continue
            cleaned.append({"label": label, "detail": detail, "time": time_str})
        session.thought_log = cleaned
        app_v2.store.put(session)
        app_v2._save_meta(doc_id, thoughts=cleaned)
        return {"ok": 1}

    def get_feedback(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        meta = app_v2._load_meta(doc_id)
        return {"items": meta.get("feedback", [])}

    async def save_feedback(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        data = await request.json()
        if not isinstance(data, dict):
            raise app_v2.HTTPException(status_code=400, detail="body must be object")
        items = data.get("items")
        if items is None and isinstance(data.get("item"), dict):
            items = [data.get("item")]
        if not isinstance(items, list):
            raise app_v2.HTTPException(status_code=400, detail="items must be list")
        normalized: list[dict] = []
        for raw in items:
            one = app_v2._normalize_feedback_item(raw)
            if one:
                normalized.append(one)
        if not normalized:
            raise app_v2.HTTPException(status_code=400, detail="no valid feedback item")
        existing = app_v2._load_meta(doc_id)
        merged = [x for x in (existing.get("feedback") or []) if isinstance(x, dict)]
        merged.extend(normalized)
        merged = merged[-500:]
        app_v2._save_meta(doc_id, feedback=merged)
        low_threshold = app_v2._low_satisfaction_threshold()
        low_recorded = 0
        context = data.get("context") if isinstance(data.get("context"), dict) else {}
        for item in normalized:
            if int(item.get("rating") or 0) <= low_threshold:
                ok = app_v2._append_low_satisfaction_event(
                    doc_id,
                    item,
                    context=context,
                    doc_text=str(session.doc_text or ""),
                )
                if ok:
                    low_recorded += 1
        return {
            "ok": 1,
            "saved": len(normalized),
            "low_recorded": low_recorded,
            "low_threshold": low_threshold,
            "items": merged[-50:],
        }

    def get_low_feedback(self, limit: int = 200) -> dict:
        app_v2 = app_v2_module()

        return {"items": app_v2._load_low_satisfaction_events(limit=limit)}

