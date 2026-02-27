"""Version Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import difflib

from fastapi import Request

from .base import app_v2_module


class VersionService:
    async def version_commit(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if not session:
            raise app_v2.HTTPException(404, "document not found")

        try:
            body = await request.body()
            payload = app_v2.json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        message = payload.get("message", "淇濆瓨鐗堟湰")
        author = payload.get("author", "user")
        tags = payload.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        kind = str(payload.get("kind") or "").strip().lower()
        if not tags and not kind:
            kind = "major"
        if kind == "major" and "major" not in tags:
            tags.append("major")
        elif kind == "minor" and "minor" not in tags:
            tags.append("minor")

        version_id = app_v2.uuid.uuid4().hex[:12]
        version = app_v2.VersionNode(
            version_id=version_id,
            parent_id=session.current_version_id,
            timestamp=app_v2.time.time(),
            message=message,
            author=author,
            doc_text=session.doc_text,
            doc_ir=session.doc_ir.copy() if session.doc_ir else {},
            tags=tags,
            branch_name=app_v2._get_current_branch(session),
        )

        session.versions[version_id] = version
        session.current_version_id = version_id
        branch = app_v2._get_current_branch(session)
        session.branches[branch] = version_id
        app_v2.store.put(session)

        return {
            "ok": 1,
            "version_id": version_id,
            "message": message,
            "timestamp": version.timestamp,
            "kind": kind or "",
        }

    def version_log(self, doc_id: str, branch: str = "main", limit: int = 50) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if not session:
            raise app_v2.HTTPException(404, "document not found")

        head_id = session.branches.get(branch)
        if not head_id:
            return {"ok": 1, "versions": [], "branch": branch}

        versions = []
        current_id = head_id
        count = 0
        while current_id and count < limit:
            version = session.versions.get(current_id)
            if not version:
                break
            summary = {}
            if version.parent_id and version.parent_id in session.versions:
                parent = session.versions.get(version.parent_id)
                if parent:
                    summary = app_v2._version_diff_summary(parent.doc_ir, version.doc_ir)
            versions.append(
                {
                    "version_id": version.version_id,
                    "parent_id": version.parent_id,
                    "timestamp": version.timestamp,
                    "message": version.message,
                    "author": version.author,
                    "tags": version.tags,
                    "kind": app_v2._version_kind_from_tags(version.tags),
                    "summary": summary,
                    "branch_name": version.branch_name,
                    "is_current": current_id == session.current_version_id,
                }
            )
            current_id = version.parent_id
            count += 1

        return {"ok": 1, "versions": versions, "branch": branch}

    def version_tree(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if not session:
            raise app_v2.HTTPException(404, "document not found")

        nodes = []
        edges = []
        for vid, version in session.versions.items():
            nodes.append(
                {
                    "id": vid,
                    "message": version.message,
                    "author": version.author,
                    "timestamp": version.timestamp,
                    "tags": version.tags,
                    "branch": version.branch_name,
                    "is_current": vid == session.current_version_id,
                }
            )
            if version.parent_id:
                edges.append({"from": version.parent_id, "to": vid})

        return {
            "ok": 1,
            "nodes": nodes,
            "edges": edges,
            "branches": session.branches,
            "current": session.current_version_id,
        }

    async def version_checkout(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if not session:
            raise app_v2.HTTPException(404, "document not found")
        try:
            body = await request.body()
            payload = app_v2.json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            raise app_v2.HTTPException(400, "invalid payload")

        version_id = payload.get("version_id")
        if not version_id:
            raise app_v2.HTTPException(400, "missing version_id")
        version = session.versions.get(version_id)
        if not version:
            raise app_v2.HTTPException(404, "version not found")

        session.doc_text = version.doc_text
        session.doc_ir = version.doc_ir.copy() if version.doc_ir else {}
        session.current_version_id = version_id
        app_v2.store.put(session)
        return {"ok": 1, "version_id": version_id, "message": version.message, "doc_text": version.doc_text}

    async def version_branch(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if not session:
            raise app_v2.HTTPException(404, "document not found")
        try:
            body = await request.body()
            payload = app_v2.json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            raise app_v2.HTTPException(400, "invalid payload")

        branch_name = payload.get("branch_name", "").strip()
        if not branch_name:
            raise app_v2.HTTPException(400, "branch_name required")
        if branch_name in session.branches:
            raise app_v2.HTTPException(400, f"branch '{branch_name}' already exists")
        base_version_id = payload.get("base_version_id") or session.current_version_id
        if base_version_id and base_version_id not in session.versions:
            raise app_v2.HTTPException(404, "base version not found")
        session.branches[branch_name] = base_version_id or ""
        app_v2.store.put(session)
        return {"ok": 1, "branch_name": branch_name, "base_version_id": base_version_id}

    def version_diff(self, doc_id: str, from_version: str, to_version: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if not session:
            raise app_v2.HTTPException(404, "document not found")
        v1 = session.versions.get(from_version)
        v2 = session.versions.get(to_version)
        if not v1 or not v2:
            raise app_v2.HTTPException(404, "version not found")
        diff = list(
            difflib.unified_diff(
                v1.doc_text.split("\n"),
                v2.doc_text.split("\n"),
                fromfile=f"version {from_version}",
                tofile=f"version {to_version}",
                lineterm="",
            )
        )
        return {
            "ok": 1,
            "from_version": from_version,
            "to_version": to_version,
            "diff": diff,
            "from_message": v1.message,
            "to_message": v2.message,
        }

    async def version_tag(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if not session:
            raise app_v2.HTTPException(404, "document not found")
        try:
            body = await request.body()
            payload = app_v2.json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            raise app_v2.HTTPException(400, "invalid payload")

        version_id = payload.get("version_id")
        tag = payload.get("tag", "").strip()
        if not version_id or not tag:
            raise app_v2.HTTPException(400, "missing params")
        version = session.versions.get(version_id)
        if not version:
            raise app_v2.HTTPException(404, "version not found")
        if tag not in version.tags:
            version.tags.append(tag)
            app_v2.store.put(session)
        return {"ok": 1, "version_id": version_id, "tag": tag}

