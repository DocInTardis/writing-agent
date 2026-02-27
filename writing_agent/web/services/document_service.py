"""Document Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

from .base import app_v2_module


class DocumentService:
    def get_doc(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        app_v2._ensure_mcp_citations(session)
        app_v2.store.put(session)
        meta = app_v2._load_meta(doc_id)
        return {
            "id": session.id,
            "text": app_v2._safe_doc_text(session),
            "doc_ir": session.doc_ir or {},
            "template_name": session.template_source_name or "",
            "required_h2": session.template_required_h2 or [],
            "template_outline": session.template_outline or [],
            "template_type": session.template_source_type or "",
            "formatting": session.formatting or {},
            "generation_prefs": session.generation_prefs or {},
            "resume_state": app_v2._get_resume_state_payload(session),
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

    def docs_list(self) -> dict:
        app_v2 = app_v2_module()

        docs = []
        for doc_id, session in app_v2.store.items():
            text = app_v2._safe_doc_text(session)
            title = session.title or ""
            if not title:
                lines = text.split("\n")
                for line in lines:
                    if line.strip().startswith("#"):
                        title = line.strip().lstrip("#").strip()
                        break
            docs.append(
                {
                    "doc_id": doc_id,
                    "title": title or app_v2._default_title(),
                    "text": text[:200],
                    "updated_at": getattr(session, "updated_at", ""),
                    "char_count": len(text),
                }
            )
        docs.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return {"ok": 1, "docs": docs}

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

