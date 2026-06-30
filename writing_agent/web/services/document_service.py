"""Document Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

from writing_agent.web import meta_db as _meta_db
from .base import app_v2_module
from .workspace_service import WorkspaceService


class DocumentService:
    def get_doc(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        app_v2._ensure_mcp_citations(session)
        app_v2.store.put(session)
        meta = _meta_db.load_meta(doc_id)
        workspace = WorkspaceService().summarize_session(session)
        return {
            "id": session.id,
            "title": str(workspace.get("title") or getattr(session, "title", "") or app_v2._extract_title(app_v2._safe_doc_text(session)) or app_v2._default_title()),
            "labels": list(workspace.get("labels", [])),
            "owner": str(workspace.get("owner") or ""),
            "priority": str(workspace.get("priority") or ""),
            "due_at": float(workspace.get("due_at", 0.0) or 0.0),
            "due_soon": bool(workspace.get("due_soon", False)),
            "unassigned": bool(workspace.get("unassigned", False)),
            "no_due_date": bool(workspace.get("no_due_date", False)),
            "no_priority": bool(workspace.get("no_priority", False)),
            "overdue": bool(workspace.get("overdue", False)),
            "text": app_v2._safe_doc_text(session),
            "doc_ir": session.doc_ir or {},
            "template_name": session.template_source_name or "",
            "required_h2": session.template_required_h2 or [],
            "template_outline": session.template_outline or [],
            "template_type": session.template_source_type or "",
            "formatting": session.formatting or {},
            "generation_prefs": session.generation_prefs or {},
            "resume_state": app_v2._get_resume_state_payload(session),
            "status": str(workspace.get("status") or getattr(session, "status", "draft") or "draft"),
            "archived": bool(workspace.get("archived", False)),
            "trashed": bool(workspace.get("trashed", False)),
            "trash_until": float(workspace.get("trash_until", 0.0) or 0.0),
            "created_at": float(getattr(session, "created_at", 0.0) or 0.0),
            "updated_at": float(getattr(session, "updated_at", 0.0) or 0.0),
            "chat_log": meta.get("chat", []),
            "thought_log": meta.get("thoughts", []),
            "feedback_log": meta.get("feedback", []),
        }

    def get_text_block(self, block_id: str) -> dict:
        app_v2 = app_v2_module()

        repo_root = app_v2.Path(__file__).resolve().parents[3]
        data_dir = app_v2.Path(app_v2.os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
        store_dir = data_dir / "text_store"
        block_id = str(block_id or "").strip()
        if not block_id:
            raise app_v2.HTTPException(status_code=400, detail="block_id required")
        txt_path = store_dir / f"{block_id}.txt"
        json_path = store_dir / f"{block_id}.json"
        if txt_path.exists():
            return {
                "id": block_id,
                "format": "text",
                "kind": self._guess_block_kind(block_id),
                "text": txt_path.read_text(encoding="utf-8"),
            }
        if json_path.exists():
            try:
                payload = app_v2.json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            return {"id": block_id, "format": "json", "kind": self._guess_block_kind(block_id), "data": payload}
        raise app_v2.HTTPException(status_code=404, detail="block not found")

    def docs_list(
        self,
        status: str = "active",
        query: str = "",
        label: str = "",
        owner: str = "",
        priority: str = "",
        due_soon: object = False,
        unassigned: object = False,
        no_due_date: object = False,
        no_priority: object = False,
        overdue: object = False,
        sort: str = "updated",
    ) -> dict:
        payload = WorkspaceService().list_workspaces(
            status=status or "active",
            limit=200,
            query=query,
            label=label,
            owner=owner,
            priority=priority,
            due_soon=due_soon,
            unassigned=unassigned,
            no_due_date=no_due_date,
            no_priority=no_priority,
            overdue=overdue,
            sort=sort,
        )
        docs = [
            {
                "doc_id": item.get("doc_id"),
                "title": item.get("title"),
                "labels": item.get("labels", []),
                "owner": item.get("owner", ""),
                "priority": item.get("priority", ""),
                "due_at": item.get("due_at", 0.0),
                "due_soon": bool(item.get("due_soon", False)),
                "unassigned": bool(item.get("unassigned", False)),
                "no_due_date": bool(item.get("no_due_date", False)),
                "no_priority": bool(item.get("no_priority", False)),
                "overdue": bool(item.get("overdue", False)),
                "text": item.get("preview"),
                "updated_at": item.get("updated_at"),
                "char_count": item.get("char_count"),
                "status": item.get("status"),
                "archived": item.get("archived"),
                "trashed": item.get("trashed"),
                "trash_until": item.get("trash_until"),
                "template_name": item.get("template_name"),
                "version_count": item.get("version_count"),
                "citation_count": item.get("citation_count"),
            }
            for item in payload.get("items", [])
        ]
        return {
            "ok": 1,
            "docs": docs,
            "status": payload.get("status"),
            "query": payload.get("query", ""),
            "label": payload.get("label", ""),
            "owner": payload.get("owner", ""),
            "priority": payload.get("priority", ""),
            "due_soon": bool(payload.get("due_soon", False)),
            "unassigned": bool(payload.get("unassigned", False)),
            "no_due_date": bool(payload.get("no_due_date", False)),
            "no_priority": bool(payload.get("no_priority", False)),
            "overdue": bool(payload.get("overdue", False)),
            "sort": payload.get("sort", "updated"),
            "total": payload.get("total", len(docs)),
        }

    def doc_delete(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        app_v2.store.delete(doc_id)
        return {"ok": 1}

    @staticmethod
    def _guess_block_kind(block_id: str) -> str:
        low = (block_id or "").lower()
        if low.startswith("t_"):
            return "table"
        if low.startswith("f_"):
            return "figure"
        if low.startswith("l_"):
            return "list"
        if low.startswith("p_"):
            return "paragraph"
        return "unknown"

