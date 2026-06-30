"""Workspace View Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .base import app_v2_module
from .workspace_service import WorkspaceService, _flag_enabled, _workspace_sort_mode

_BUILTIN_VIEWS = [
    {"id": "all-workspaces", "name": "All Workspaces", "status": "all", "q": "", "label": "", "owner": "", "priority": "", "due_soon": False, "unassigned": False, "no_due_date": False, "no_priority": False, "overdue": False, "sort": "updated"},
    {"id": "review-queue", "name": "Review Queue", "status": "review", "q": "", "label": "", "owner": "", "priority": "", "due_soon": False, "unassigned": False, "no_due_date": False, "no_priority": False, "overdue": False, "sort": "updated"},
    {"id": "ready-queue", "name": "Ready Queue", "status": "ready", "q": "", "label": "", "owner": "", "priority": "", "due_soon": False, "unassigned": False, "no_due_date": False, "no_priority": False, "overdue": False, "sort": "updated"},
    {"id": "high-priority", "name": "High Priority", "status": "active", "q": "", "label": "", "owner": "", "priority": "high", "due_soon": False, "unassigned": False, "no_due_date": False, "no_priority": False, "overdue": False, "sort": "due"},
    {"id": "urgent", "name": "Urgent", "status": "active", "q": "", "label": "", "owner": "", "priority": "urgent", "due_soon": False, "unassigned": False, "no_due_date": False, "no_priority": False, "overdue": False, "sort": "due"},
    {"id": "due-soon", "name": "Due Soon", "status": "active", "q": "", "label": "", "owner": "", "priority": "", "due_soon": True, "unassigned": False, "no_due_date": False, "no_priority": False, "overdue": False, "sort": "due"},
    {"id": "unassigned", "name": "Unassigned", "status": "active", "q": "", "label": "", "owner": "", "priority": "", "due_soon": False, "unassigned": True, "no_due_date": False, "no_priority": False, "overdue": False, "sort": "updated"},
    {"id": "no-due-date", "name": "No Due Date", "status": "active", "q": "", "label": "", "owner": "", "priority": "", "due_soon": False, "unassigned": False, "no_due_date": True, "no_priority": False, "overdue": False, "sort": "updated"},
    {"id": "no-priority", "name": "No Priority", "status": "active", "q": "", "label": "", "owner": "", "priority": "", "due_soon": False, "unassigned": False, "no_due_date": False, "no_priority": True, "overdue": False, "sort": "updated"},
    {"id": "overdue", "name": "Overdue", "status": "active", "q": "", "label": "", "owner": "", "priority": "", "due_soon": False, "unassigned": False, "no_due_date": False, "no_priority": False, "overdue": True, "sort": "due"},
    {"id": "archived", "name": "Archived", "status": "archived", "q": "", "label": "", "owner": "", "priority": "", "due_soon": False, "unassigned": False, "no_due_date": False, "no_priority": False, "overdue": False, "sort": "updated"},
    {"id": "trash", "name": "Trash", "status": "trashed", "q": "", "label": "", "owner": "", "priority": "", "due_soon": False, "unassigned": False, "no_due_date": False, "no_priority": False, "overdue": False, "sort": "expires"},
]


def _normalize_view_payload(*, name: str, status: str, query: str, label: str, owner: str, priority: str, due_soon: object, unassigned: object, no_due_date: object, no_priority: object, overdue: object, sort: str) -> dict:
    normalized_name = " ".join(str(name or "").split()).strip()[:60]
    normalized_status = str(status or "all").strip().lower() or "all"
    normalized_query = " ".join(str(query or "").split()).strip()[:120]
    normalized_label = " ".join(str(label or "").split()).strip()[:32]
    normalized_owner = " ".join(str(owner or "").split()).strip()[:48]
    normalized_priority = str(priority or "").strip().lower()
    normalized_priority = normalized_priority if normalized_priority in {"", "low", "medium", "high", "urgent"} else ""
    normalized_due_soon = _flag_enabled(due_soon)
    normalized_unassigned = _flag_enabled(unassigned)
    normalized_no_due_date = _flag_enabled(no_due_date)
    normalized_no_priority = _flag_enabled(no_priority)
    normalized_overdue = _flag_enabled(overdue)
    normalized_sort = _workspace_sort_mode(sort)
    return {
        "name": normalized_name,
        "status": normalized_status,
        "q": normalized_query,
        "label": normalized_label,
        "owner": normalized_owner,
        "priority": normalized_priority,
        "due_soon": normalized_due_soon,
        "unassigned": normalized_unassigned,
        "no_due_date": normalized_no_due_date,
        "no_priority": normalized_no_priority,
        "overdue": normalized_overdue,
        "sort": normalized_sort,
    }


class WorkspaceViewService:
    @staticmethod
    def _storage_path() -> Path:
        app_v2 = app_v2_module()

        persistence_dir = getattr(app_v2.store, "_persistence_dir", None)
        root = Path(persistence_dir) if persistence_dir else Path(app_v2.DATA_DIR)
        if root.name == "workspaces":
            root = root.parent
        root.mkdir(parents=True, exist_ok=True)
        return root / "workspace_views.json"

    def _load_custom_views(self) -> list[dict]:
        path = self._storage_path()
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            import logging
            logging.getLogger(__name__).warning("_load_custom_views: failed to read %s", path, exc_info=True)
            return []
        items = payload.get("items") if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return []
        normalized: list[dict] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            view_id = str(raw.get("id") or "").strip()
            fields = _normalize_view_payload(
                name=str(raw.get("name") or ""),
                status=str(raw.get("status") or "all"),
                query=str(raw.get("q") or ""),
                label=str(raw.get("label") or ""),
                owner=str(raw.get("owner") or ""),
                priority=str(raw.get("priority") or ""),
                due_soon=raw.get("due_soon"),
                unassigned=raw.get("unassigned"),
                no_due_date=raw.get("no_due_date"),
                no_priority=raw.get("no_priority"),
                overdue=raw.get("overdue"),
                sort=str(raw.get("sort") or "updated"),
            )
            if not view_id or not fields["name"]:
                continue
            normalized.append({"id": view_id, **fields, "builtin": False})
        return normalized[:12]

    def _persist_custom_views(self, items: list[dict]) -> None:
        path = self._storage_path()
        payload = {
            "schema_version": 1,
            "items": [
                {
                    "id": str(item.get("id") or "").strip(),
                    "name": str(item.get("name") or "").strip(),
                    "status": str(item.get("status") or "all").strip().lower(),
                    "q": str(item.get("q") or "").strip(),
                    "label": str(item.get("label") or "").strip(),
                    "owner": str(item.get("owner") or "").strip(),
                    "priority": str(item.get("priority") or "").strip().lower(),
                    "due_soon": bool(item.get("due_soon", False)),
                    "unassigned": bool(item.get("unassigned", False)),
                    "no_due_date": bool(item.get("no_due_date", False)),
                    "no_priority": bool(item.get("no_priority", False)),
                    "overdue": bool(item.get("overdue", False)),
                    "sort": _workspace_sort_mode(str(item.get("sort") or "updated")),
                }
                for item in items
                if str(item.get("id") or "").strip() and str(item.get("name") or "").strip()
            ],
        }
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def list_views(
        self,
        *,
        status: str = "all",
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
    ) -> list[dict]:
        current = _normalize_view_payload(name="current", status=status, query=query, label=label, owner=owner, priority=priority, due_soon=due_soon, unassigned=unassigned, no_due_date=no_due_date, no_priority=no_priority, overdue=overdue, sort=sort)
        workspace_service = WorkspaceService()
        views = [{**item, "builtin": True} for item in _BUILTIN_VIEWS] + self._load_custom_views()
        decorated: list[dict] = []
        for view in views:
            payload = workspace_service.list_workspaces(
                status=str(view.get("status") or "all"),
                limit=1,
                query=str(view.get("q") or ""),
                label=str(view.get("label") or ""),
                owner=str(view.get("owner") or ""),
                priority=str(view.get("priority") or ""),
                due_soon=bool(view.get("due_soon", False)),
                unassigned=bool(view.get("unassigned", False)),
                no_due_date=bool(view.get("no_due_date", False)),
                no_priority=bool(view.get("no_priority", False)),
                overdue=bool(view.get("overdue", False)),
                sort=str(view.get("sort") or "updated"),
            )
            decorated.append(
                {
                    **view,
                    "count": int(payload.get("total", 0) or 0),
                    "active": (
                        str(view.get("status") or "all").casefold() == current["status"].casefold()
                        and str(view.get("q") or "") == current["q"]
                        and str(view.get("label") or "").casefold() == current["label"].casefold()
                        and str(view.get("owner") or "").casefold() == current["owner"].casefold()
                        and str(view.get("priority") or "").casefold() == current["priority"].casefold()
                        and bool(view.get("due_soon", False)) == bool(current["due_soon"])
                        and bool(view.get("unassigned", False)) == bool(current["unassigned"])
                        and bool(view.get("no_due_date", False)) == bool(current["no_due_date"])
                        and bool(view.get("no_priority", False)) == bool(current["no_priority"])
                        and bool(view.get("overdue", False)) == bool(current["overdue"])
                        and str(view.get("sort") or "updated").casefold() == current["sort"].casefold()
                    ),
                }
            )
        return decorated

    def create_view(
        self,
        *,
        name: str,
        status: str = "all",
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
        fields = _normalize_view_payload(name=name, status=status, query=query, label=label, owner=owner, priority=priority, due_soon=due_soon, unassigned=unassigned, no_due_date=no_due_date, no_priority=no_priority, overdue=overdue, sort=sort)
        if not fields["name"]:
            raise app_v2_module().HTTPException(status_code=400, detail="view name required")
        views = self._load_custom_views()
        views = [view for view in views if str(view.get("name") or "").casefold() != fields["name"].casefold()]
        views.insert(0, {"id": uuid.uuid4().hex, **fields, "builtin": False})
        self._persist_custom_views(views[:12])
        return {
            "ok": 1,
            "items": self.list_views(
                status=fields["status"],
                query=fields["q"],
                label=fields["label"],
                owner=fields["owner"],
                priority=fields["priority"],
                due_soon=fields["due_soon"],
                unassigned=fields["unassigned"],
                no_due_date=fields["no_due_date"],
                no_priority=fields["no_priority"],
                overdue=fields["overdue"],
                sort=fields["sort"],
            ),
        }

    def delete_view(self, view_id: str) -> dict:
        normalized_id = str(view_id or "").strip()
        if not normalized_id:
            raise app_v2_module().HTTPException(status_code=400, detail="view_id required")
        views = self._load_custom_views()
        next_views = [view for view in views if str(view.get("id") or "") != normalized_id]
        if len(next_views) == len(views):
            raise app_v2_module().HTTPException(status_code=404, detail="view not found")
        self._persist_custom_views(next_views)
        return {"ok": 1, "deleted": normalized_id}
