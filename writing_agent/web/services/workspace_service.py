"""Workspace Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import copy
import time
from pathlib import Path

from writing_agent.storage import _normalize_due_at, _normalize_labels, _normalize_owner, _normalize_priority
from writing_agent.v2.template_parse import parse_template_file

from .base import app_v2_module

WORKSPACE_STATUSES = {"draft", "writing", "review", "ready", "archived", "trashed"}
WORKSPACE_SORT_MODES = {"updated", "opened", "created", "title", "activity", "expires", "due"}
WORKSPACE_TRASH_RETENTION_S = 7 * 24 * 60 * 60
DUE_SOON_WINDOW_S = 7 * 24 * 60 * 60
WORKSPACE_BATCH_ACTIONS = {
    "pin",
    "unpin",
    "archive",
    "restore",
    "trash",
    "untrash",
    "purge",
    "status",
    "labels_add",
    "labels_remove",
    "labels_replace",
    "owner_set",
    "priority_set",
    "due_set",
    "due_clear",
}


def _text_preview(text: str, limit: int = 180) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def _format_ts(value: float) -> str:
    if not value:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(value))
    except Exception:
        return "-"


def _trash_deadline() -> float:
    return time.time() + WORKSPACE_TRASH_RETENTION_S


def _template_label(name: str) -> str:
    base = Path(name).stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in base.split()) or "Template"


def _build_outline_scaffold(title: str, outline: list[tuple[int, str]]) -> str:
    lines = [f"# {title}"]
    for level, heading in outline:
        clean_heading = str(heading or "").strip()
        if not clean_heading:
            continue
        depth = max(2, min(int(level or 2), 6))
        lines.extend(["", f"{'#' * depth} {clean_heading}", ""])
    return "\n".join(lines).strip() + "\n"


def _append_activity(session, *, event_type: str, message: str, details: dict | None = None) -> None:
    items = list(getattr(session, "activity_log", []) or [])
    items.append(
        {
            "ts": time.time(),
            "type": str(event_type or "event").strip() or "event",
            "message": str(message or "").strip()[:240],
            "details": dict(details or {}),
        }
    )
    session.activity_log = items[-80:]


def _workspace_status(session) -> str:
    if bool(getattr(session, "trashed", False)):
        return "trashed"
    archived = bool(getattr(session, "archived", False))
    if archived:
        return "archived"
    raw = str(getattr(session, "status", "draft") or "draft").strip().lower()
    return raw if raw in WORKSPACE_STATUSES else "draft"


def _workspace_labels(session) -> list[str]:
    return _normalize_labels(getattr(session, "labels", []))


def _workspace_owner(session) -> str:
    return _normalize_owner(getattr(session, "owner", ""))


def _workspace_priority(session) -> str:
    return _normalize_priority(getattr(session, "priority", ""))


def _workspace_due_at(session) -> float:
    return _normalize_due_at(getattr(session, "due_at", 0.0))


def _merge_workspace_labels(current: list[str], incoming: object) -> list[str]:
    merged = list(current or []) + list(_normalize_labels(incoming))
    return _normalize_labels(merged)


def _remove_workspace_labels(current: list[str], incoming: object) -> list[str]:
    current_labels = _normalize_labels(current)
    remove_keys = {item.casefold() for item in _normalize_labels(incoming)}
    if not remove_keys:
        return current_labels
    return [item for item in current_labels if item.casefold() not in remove_keys]


def _workspace_sort_mode(value: str) -> str:
    mode = str(value or "updated").strip().lower()
    return mode if mode in WORKSPACE_SORT_MODES else "updated"


def _flag_enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return float(value) > 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _date_input_value(value: float) -> str:
    if not value:
        return ""
    try:
        return time.strftime("%Y-%m-%d", time.localtime(value))
    except Exception:
        return ""


def _is_overdue(*, due_at: float, now: float | None = None) -> bool:
    current = float(now if now is not None else time.time())
    return bool(due_at and due_at < current)


def _is_due_soon(*, due_at: float, now: float | None = None, window_s: float = DUE_SOON_WINDOW_S) -> bool:
    current = float(now if now is not None else time.time())
    return bool(due_at and due_at >= current and due_at <= (current + float(window_s or 0.0)))


def _sort_workspaces(items: list[dict], *, mode: str) -> list[dict]:
    selected = _workspace_sort_mode(mode)
    if selected == "title":
        items.sort(
            key=lambda item: (
                str(item.get("title") or "").lower(),
                -(float(item.get("updated_at") or 0.0)),
                -(float(item.get("last_opened_at") or 0.0)),
            )
        )
    elif selected == "created":
        items.sort(
            key=lambda item: (
                float(item.get("created_at") or 0.0),
                float(item.get("updated_at") or 0.0),
                float(item.get("last_opened_at") or 0.0),
            ),
            reverse=True,
        )
    elif selected == "opened":
        items.sort(
            key=lambda item: (
                float(item.get("last_opened_at") or 0.0),
                float(item.get("updated_at") or 0.0),
                float(item.get("created_at") or 0.0),
            ),
            reverse=True,
        )
    elif selected == "activity":
        items.sort(
            key=lambda item: (
                int(item.get("activity_count") or 0),
                float(item.get("updated_at") or 0.0),
                float(item.get("last_opened_at") or 0.0),
            ),
            reverse=True,
        )
    elif selected == "expires":
        items.sort(
            key=lambda item: (
                0 if bool(item.get("trashed")) and float(item.get("trash_until") or 0.0) else 1,
                float(item.get("trash_until") or float("inf")),
                float(item.get("created_at") or 0.0),
                str(item.get("doc_id") or ""),
            )
        )
    elif selected == "due":
        items.sort(
            key=lambda item: (
                0 if float(item.get("due_at") or 0.0) > 0 else 1,
                float(item.get("due_at") or float("inf")),
                float(item.get("created_at") or 0.0) if float(item.get("due_at") or 0.0) > 0 else -(float(item.get("updated_at") or 0.0)),
                str(item.get("doc_id") or ""),
            )
        )
    else:
        items.sort(
            key=lambda item: (
                float(item.get("updated_at") or 0.0),
                float(item.get("last_opened_at") or 0.0),
                float(item.get("created_at") or 0.0),
            ),
            reverse=True,
        )
    if selected not in {"expires", "due"}:
        items.sort(key=lambda item: 1 if bool(item.get("pinned")) else 0, reverse=True)
    return items


def note_content_saved(session, *, source: str, text: str) -> None:
    content = str(text or "").strip()
    if not content:
        return
    current = _workspace_status(session)
    if current in {"draft", "review"}:
        session.status = "writing"
    _append_activity(
        session,
        event_type="content_saved",
        message=f"Saved content via {source}",
        details={"source": source, "char_count": len(content)},
    )


def note_settings_saved(session) -> None:
    _append_activity(session, event_type="settings_updated", message="Updated workspace settings")


class WorkspaceService:
    @staticmethod
    def cleanup_expired_trash() -> dict:
        app_v2 = app_v2_module()

        now = time.time()
        removed: list[str] = []
        for doc_id, session in list(app_v2.store.items()):
            if not bool(getattr(session, "trashed", False)):
                continue
            trash_until = float(getattr(session, "trash_until", 0.0) or 0.0)
            if not trash_until or trash_until > now:
                continue
            app_v2.store.delete(doc_id)
            removed.append(doc_id)
        return {"ok": 1, "deleted": len(removed), "doc_ids": removed}

    @staticmethod
    def built_in_templates() -> list[dict]:
        app_v2 = app_v2_module()

        templates: list[dict] = []
        root = Path(app_v2.REPO_ROOT) / "writing_agent" / "report_templates"
        if not root.exists():
            return templates
        for path in sorted(root.glob("*.html")):
            try:
                parsed = parse_template_file(path, path.stem)
            except Exception:
                import logging
                logging.getLogger(__name__).warning("built_in_templates: failed to parse %s", path, exc_info=True)
                parsed = None
            outline = list(parsed.outline) if parsed else []
            required_h2 = list(parsed.required_h2) if parsed else []
            templates.append(
                {
                    "id": path.name,
                    "name": _template_label(path.name),
                    "filename": path.name,
                    "required_h2": required_h2,
                    "outline": outline,
                    "outline_count": len(outline),
                    "summary": ", ".join(required_h2[:3]) if required_h2 else "Structured report scaffold",
                }
            )
        return templates

    @staticmethod
    def summarize_session(session) -> dict:
        app_v2 = app_v2_module()

        now = time.time()
        text = str(getattr(session, "doc_text", "") or "")
        if not text.strip() and getattr(session, "doc_ir", None):
            try:
                text = app_v2.doc_ir_to_text(app_v2.doc_ir_from_dict(session.doc_ir))
            except Exception:
                import logging
                logging.getLogger(__name__).debug("summarize_session: doc_ir render failed for %s", getattr(session, 'id', '?'), exc_info=True)
                text = ""
        title = str(getattr(session, "title", "") or "").strip() or app_v2._extract_title(text) or app_v2._default_title()
        due_at = _workspace_due_at(session)
        owner = _workspace_owner(session)
        return {
            "doc_id": session.id,
            "title": title,
            "pinned": bool(getattr(session, "pinned", False)),
            "labels": _workspace_labels(session),
            "owner": owner,
            "priority": _workspace_priority(session),
            "preview": _text_preview(text),
            "char_count": len(text),
            "citation_count": len(getattr(session, "citations", {}) or {}),
            "version_count": len(getattr(session, "versions", {}) or {}),
            "template_name": str(getattr(session, "template_source_name", "") or getattr(session, "template_name", "") or ""),
            "created_at": float(getattr(session, "created_at", 0.0) or 0.0),
            "updated_at": float(getattr(session, "updated_at", 0.0) or 0.0),
            "last_opened_at": float(getattr(session, "last_opened_at", 0.0) or 0.0),
            "due_at": due_at,
            "created_at_label": _format_ts(float(getattr(session, "created_at", 0.0) or 0.0)),
            "updated_at_label": _format_ts(float(getattr(session, "updated_at", 0.0) or 0.0)),
            "last_opened_at_label": _format_ts(float(getattr(session, "last_opened_at", 0.0) or 0.0)),
            "due_at_label": _format_ts(due_at),
            "due_date_input": _date_input_value(due_at),
            "status": _workspace_status(session),
            "archived": bool(getattr(session, "archived", False)),
            "trashed": bool(getattr(session, "trashed", False)),
            "trash_until": float(getattr(session, "trash_until", 0.0) or 0.0),
            "trash_until_label": _format_ts(float(getattr(session, "trash_until", 0.0) or 0.0)),
            "overdue": _is_overdue(due_at=due_at, now=now),
            "due_soon": _is_due_soon(due_at=due_at, now=now),
            "unassigned": not bool(owner),
            "no_due_date": not bool(due_at),
            "no_priority": not bool(_workspace_priority(session)),
            "activity_count": len(getattr(session, "activity_log", []) or []),
        }

    def list_workspaces(
        self,
        *,
        status: str = "active",
        limit: int = 50,
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
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        filter_status = str(status or "active").strip().lower()
        query_text = str(query or "").strip().lower()
        label_text = str(label or "").strip().lower()
        owner_text = str(owner or "").strip().lower()
        priority_text = _normalize_priority(priority)
        due_soon_only = _flag_enabled(due_soon)
        unassigned_only = _flag_enabled(unassigned)
        no_due_date_only = _flag_enabled(no_due_date)
        no_priority_only = _flag_enabled(no_priority)
        overdue_only = _flag_enabled(overdue)
        sort_mode = _workspace_sort_mode(sort)
        items: list[dict] = []
        for _, session in app_v2.store.items():
            archived = bool(getattr(session, "archived", False))
            trashed = bool(getattr(session, "trashed", False))
            if filter_status == "active" and (archived or trashed):
                continue
            if filter_status == "archived" and (not archived or trashed):
                continue
            if filter_status in {"trash", "trashed"} and not trashed:
                continue
            if filter_status in WORKSPACE_STATUSES and filter_status not in {"active", "archived", "all"}:
                if _workspace_status(session) != filter_status:
                    continue
            summary = self.summarize_session(session)
            if query_text:
                haystack = " ".join(
                    [
                        str(summary.get("title") or ""),
                        str(summary.get("preview") or ""),
                        str(summary.get("template_name") or ""),
                        " ".join(str(item or "") for item in summary.get("labels", [])),
                        str(summary.get("owner") or ""),
                        str(summary.get("priority") or ""),
                    ]
                ).lower()
                if query_text not in haystack:
                    continue
            if label_text:
                labels = [str(item or "").strip().lower() for item in summary.get("labels", [])]
                if label_text not in labels:
                    continue
            if owner_text and owner_text not in str(summary.get("owner") or "").lower():
                continue
            if priority_text and priority_text != str(summary.get("priority") or ""):
                continue
            if due_soon_only and not bool(summary.get("due_soon")):
                continue
            if unassigned_only and not bool(summary.get("unassigned")):
                continue
            if no_due_date_only and not bool(summary.get("no_due_date")):
                continue
            if no_priority_only and not bool(summary.get("no_priority")):
                continue
            if overdue_only and not bool(summary.get("overdue")):
                continue
            items.append(summary)
        _sort_workspaces(items, mode=sort_mode)
        limited = items[: max(1, min(int(limit or 50), 200))]
        active_count = (
            sum(1 for item in items if not bool(item.get("archived")) and not bool(item.get("trashed")))
            if filter_status == "all"
            else None
        )
        archived_count = (
            sum(1 for item in items if bool(item.get("archived")) and not bool(item.get("trashed")))
            if filter_status == "all"
            else None
        )
        trashed_count = sum(1 for item in items if bool(item.get("trashed"))) if filter_status == "all" else None
        return {
            "ok": 1,
            "status": filter_status,
            "query": query_text,
            "label": label_text,
            "owner": owner_text,
            "priority": priority_text,
            "due_soon": due_soon_only,
            "unassigned": unassigned_only,
            "no_due_date": no_due_date_only,
            "no_priority": no_priority_only,
            "overdue": overdue_only,
            "sort": sort_mode,
            "items": limited,
            "total": len(items),
            "active_count": active_count,
            "archived_count": archived_count,
            "trashed_count": trashed_count,
        }

    def dashboard_summary(self) -> dict:
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        now = time.time()
        sessions = [session for _, session in app_v2.store.items()]
        status_counts = {key: 0 for key in sorted(WORKSPACE_STATUSES)}
        pinned_count = 0
        template_bound_count = 0
        activity_total = 0
        active_last_24h = 0
        assigned_count = 0
        unassigned_count = 0
        no_due_date_count = 0
        no_priority_count = 0
        overdue_count = 0
        due_soon_count = 0
        high_priority_count = 0
        label_counts: dict[str, int] = {}
        for session in sessions:
            status = _workspace_status(session)
            status_counts[status] = int(status_counts.get(status, 0)) + 1
            if bool(getattr(session, "pinned", False)):
                pinned_count += 1
            if str(getattr(session, "template_source_name", "") or "").strip():
                template_bound_count += 1
            activity_total += len(getattr(session, "activity_log", []) or [])
            updated_at = float(getattr(session, "updated_at", 0.0) or 0.0)
            if updated_at and (now - updated_at) <= 86400:
                active_last_24h += 1
            if _workspace_owner(session):
                assigned_count += 1
            else:
                unassigned_count += 1
            if _workspace_priority(session) in {"high", "urgent"}:
                high_priority_count += 1
            elif not _workspace_priority(session):
                no_priority_count += 1
            due_at = _workspace_due_at(session)
            if not due_at:
                no_due_date_count += 1
            if _is_overdue(due_at=due_at, now=now):
                overdue_count += 1
            elif _is_due_soon(due_at=due_at, now=now):
                due_soon_count += 1
            for label in _workspace_labels(session):
                label_counts[label] = int(label_counts.get(label, 0)) + 1
        top_labels = [
            {"name": label, "count": count}
            for label, count in sorted(label_counts.items(), key=lambda item: (-item[1], item[0].lower()))[:8]
        ]
        return {
            "ok": 1,
            "total": len(sessions),
            "pinned": pinned_count,
            "template_bound": template_bound_count,
            "activity_total": activity_total,
            "active_last_24h": active_last_24h,
            "review_queue": int(status_counts.get("review", 0)),
            "ready_queue": int(status_counts.get("ready", 0)),
            "trashed": int(status_counts.get("trashed", 0)),
            "assigned": assigned_count,
            "unassigned": unassigned_count,
            "high_priority": high_priority_count,
            "no_priority": no_priority_count,
            "overdue": overdue_count,
            "due_soon": due_soon_count,
            "no_due_date": no_due_date_count,
            "label_count": len(label_counts),
            "top_labels": top_labels,
            "status_counts": status_counts,
        }

    def recent_activity(self, *, limit: int = 20, query: str = "") -> dict:
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        query_text = str(query or "").strip().lower()
        events: list[dict] = []
        for _, session in app_v2.store.items():
            title = self.summarize_session(session).get("title") or app_v2._default_title()
            for raw in list(getattr(session, "activity_log", []) or []):
                if not isinstance(raw, dict):
                    continue
                event = {
                    "doc_id": session.id,
                    "title": str(title),
                    "ts": float(raw.get("ts") or 0.0),
                    "ts_label": _format_ts(float(raw.get("ts") or 0.0)),
                    "type": str(raw.get("type") or "event"),
                    "message": str(raw.get("message") or "").strip(),
                    "details": dict(raw.get("details") or {}),
                }
                if query_text:
                    haystack = f"{event['title']} {event['type']} {event['message']}".lower()
                    if query_text not in haystack:
                        continue
                events.append(event)
        events.sort(key=lambda item: item.get("ts") or 0.0, reverse=True)
        limited = events[: max(1, min(int(limit or 20), 100))]
        return {"ok": 1, "items": limited, "total": len(events), "query": query_text}

    def latest_workspace_id(self) -> str | None:
        self.cleanup_expired_trash()
        payload = self.list_workspaces(status="active", limit=1)
        items = payload.get("items") or []
        if not items:
            return None
        return str((items[0] or {}).get("doc_id") or "") or None

    def create_workspace(self, *, template: str = "") -> dict:
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        session = app_v2.store.create()
        app_v2._initialize_new_session(session)
        _append_activity(session, event_type="workspace_created", message="Workspace created")
        template_name = str(template or "").strip()
        if template_name:
            root = Path(app_v2.REPO_ROOT) / "writing_agent" / "report_templates"
            path = root / template_name
            if path.exists() and path.is_file():
                parsed = parse_template_file(path, path.stem)
                session.template_source_name = _template_label(path.name)
                session.template_source_path = str(path)
                session.template_source_type = path.suffix.lower()
                session.template_required_h2 = list(parsed.required_h2 or [])
                session.template_outline = list(parsed.outline or [])
                scaffold_title = session.template_source_name or path.stem
                scaffold = _build_outline_scaffold(scaffold_title, session.template_outline)
                app_v2._set_doc_text(session, scaffold)
                _append_activity(
                    session,
                    event_type="template_applied",
                    message=f"Started from template: {session.template_source_name}",
                    details={"template": path.name},
                )
        app_v2.store.put(session)
        return {"ok": 1, "doc_id": session.id, "workspace": self.summarize_session(session)}

    def duplicate_workspace(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        duplicate = copy.deepcopy(session)
        now = time.time()
        duplicate.id = app_v2.uuid.uuid4().hex
        duplicate.created_at = now
        duplicate.updated_at = now
        duplicate.last_opened_at = now
        duplicate.archived = False
        duplicate.trashed = False
        duplicate.trash_until = 0.0
        duplicate.status = "draft"
        base_title = str(getattr(session, "title", "") or self.summarize_session(session).get("title") or app_v2._default_title()).strip()
        duplicate.title = f"{base_title} (Copy)"
        duplicate.title_locked = True
        _append_activity(duplicate, event_type="workspace_duplicated", message=f"Duplicated from {base_title}")
        app_v2.store.put(duplicate)
        return {"ok": 1, "doc_id": duplicate.id, "workspace": self.summarize_session(duplicate)}

    def update_workspace(
        self,
        doc_id: str,
        *,
        title: str,
        pinned: object = None,
        status: str = "",
        labels: object = None,
        owner: object = None,
        priority: object = None,
        due_at: object = None,
    ) -> dict:
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        normalized_title = str(title or "").strip()[:200]
        changed = False
        requested = False
        if normalized_title:
            requested = True
            current_title = str(getattr(session, "title", "") or "").strip()
            if normalized_title != current_title:
                session.title = normalized_title
                session.title_locked = True
                _append_activity(session, event_type="workspace_renamed", message=f"Renamed to {normalized_title}")
                changed = True
        if pinned is not None:
            requested = True
            next_pinned = bool(pinned)
            if next_pinned != bool(getattr(session, "pinned", False)):
                session.pinned = next_pinned
                _append_activity(
                    session,
                    event_type="workspace_pinned" if session.pinned else "workspace_unpinned",
                    message="Pinned workspace" if session.pinned else "Unpinned workspace",
                )
                changed = True
        next_status = str(status or "").strip().lower()
        if next_status:
            requested = True
            if next_status not in WORKSPACE_STATUSES - {"archived"}:
                raise app_v2.HTTPException(status_code=400, detail="invalid status")
            if next_status != str(getattr(session, "status", "draft") or "draft").strip().lower():
                session.status = next_status
                _append_activity(session, event_type="workspace_status", message=f"Status set to {next_status}")
                changed = True
        if labels is not None:
            requested = True
            next_labels = _normalize_labels(labels)
            current_labels = _workspace_labels(session)
            if next_labels != current_labels:
                session.labels = next_labels
                _append_activity(
                    session,
                    event_type="workspace_labels",
                    message=(
                        f"Updated labels: {', '.join(next_labels)}"
                        if next_labels
                        else "Cleared workspace labels"
                    ),
                    details={"labels": next_labels},
                )
                changed = True
        if owner is not None:
            requested = True
            next_owner = _normalize_owner(owner)
            current_owner = _workspace_owner(session)
            if next_owner != current_owner:
                session.owner = next_owner
                _append_activity(
                    session,
                    event_type="workspace_owner",
                    message=(f"Assigned owner: {next_owner}" if next_owner else "Cleared workspace owner"),
                    details={"owner": next_owner},
                )
                changed = True
        if priority is not None:
            requested = True
            next_priority = _normalize_priority(priority)
            current_priority = _workspace_priority(session)
            if next_priority != current_priority:
                session.priority = next_priority
                _append_activity(
                    session,
                    event_type="workspace_priority",
                    message=(f"Priority set to {next_priority}" if next_priority else "Cleared workspace priority"),
                    details={"priority": next_priority},
                )
                changed = True
        if due_at is not None:
            requested = True
            next_due_at = _normalize_due_at(due_at)
            current_due_at = _workspace_due_at(session)
            if next_due_at != current_due_at:
                session.due_at = next_due_at
                _append_activity(
                    session,
                    event_type="workspace_due_date",
                    message=(f"Due date set to {_format_ts(next_due_at)}" if next_due_at else "Cleared due date"),
                    details={"due_at": next_due_at},
                )
                changed = True
        if not requested:
            raise app_v2.HTTPException(status_code=400, detail="title, pinned, status, labels, owner, priority, or due date required")
        if changed:
            app_v2.store.put(session)
        return {"ok": 1, "workspace": self.summarize_session(session)}

    def pin_workspace(self, doc_id: str, *, pinned: bool) -> dict:
        return self.update_workspace(doc_id, title="", pinned=pinned)

    def archive_workspace(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        session.archived = True
        session.status = "archived"
        _append_activity(session, event_type="workspace_archived", message="Archived workspace")
        app_v2.store.put(session)
        return {"ok": 1, "workspace": self.summarize_session(session)}

    def trash_workspace(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        session.trashed = True
        session.trash_until = _trash_deadline()
        _append_activity(session, event_type="workspace_trashed", message="Moved workspace to trash")
        app_v2.store.put(session)
        return {"ok": 1, "workspace": self.summarize_session(session)}

    def untrash_workspace(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        session.trashed = False
        session.trash_until = 0.0
        _append_activity(session, event_type="workspace_restored_from_trash", message="Restored workspace from trash")
        app_v2.store.put(session)
        return {"ok": 1, "workspace": self.summarize_session(session)}

    def purge_workspace(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        if app_v2.store.get(doc_id) is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        app_v2.store.delete(doc_id)
        return {"ok": 1, "doc_id": doc_id}

    def restore_workspace(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()
        self.cleanup_expired_trash()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        session.archived = False
        session.status = "draft"
        _append_activity(session, event_type="workspace_restored", message="Restored workspace")
        app_v2.store.put(session)
        return {"ok": 1, "workspace": self.summarize_session(session)}

    def batch_update(
        self,
        doc_ids: list[str],
        *,
        action: str,
        status: str = "",
        labels: object = None,
        owner: object = None,
        priority: object = None,
        due_at: object = None,
    ) -> dict:
        app_v2 = app_v2_module()

        self.cleanup_expired_trash()
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for doc_id in doc_ids:
            normalized = str(doc_id or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_ids.append(normalized)
        if not normalized_ids:
            raise app_v2.HTTPException(status_code=400, detail="doc_ids required")
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in WORKSPACE_BATCH_ACTIONS:
            raise app_v2.HTTPException(status_code=400, detail="invalid batch action")
        results: list[dict] = []
        for doc_id in normalized_ids:
            if normalized_action == "pin":
                payload = self.pin_workspace(doc_id, pinned=True)
            elif normalized_action == "unpin":
                payload = self.pin_workspace(doc_id, pinned=False)
            elif normalized_action == "archive":
                payload = self.archive_workspace(doc_id)
            elif normalized_action == "restore":
                payload = self.restore_workspace(doc_id)
            elif normalized_action == "trash":
                payload = self.trash_workspace(doc_id)
            elif normalized_action == "untrash":
                payload = self.untrash_workspace(doc_id)
            elif normalized_action == "purge":
                payload = self.purge_workspace(doc_id)
            elif normalized_action == "labels_add":
                session = app_v2.store.get(doc_id)
                if session is None:
                    raise app_v2.HTTPException(status_code=404, detail="document not found")
                payload = self.update_workspace(doc_id, title="", labels=_merge_workspace_labels(_workspace_labels(session), labels))
            elif normalized_action == "labels_remove":
                session = app_v2.store.get(doc_id)
                if session is None:
                    raise app_v2.HTTPException(status_code=404, detail="document not found")
                payload = self.update_workspace(doc_id, title="", labels=_remove_workspace_labels(_workspace_labels(session), labels))
            elif normalized_action == "labels_replace":
                payload = self.update_workspace(doc_id, title="", labels=_normalize_labels(labels))
            elif normalized_action == "owner_set":
                payload = self.update_workspace(doc_id, title="", owner=owner)
            elif normalized_action == "priority_set":
                payload = self.update_workspace(doc_id, title="", priority=priority)
            elif normalized_action == "due_set":
                payload = self.update_workspace(doc_id, title="", due_at=due_at)
            elif normalized_action == "due_clear":
                payload = self.update_workspace(doc_id, title="", due_at="")
            else:
                payload = self.update_workspace(doc_id, title="", status=status)
            results.append({"doc_id": doc_id, **payload})
        return {"ok": 1, "action": normalized_action, "count": len(results), "items": results}
