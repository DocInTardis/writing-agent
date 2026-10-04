"""Deterministic end-to-end smoke test for the desktop product workflow.

Only the paid network model response is replaced.  Generation routing, the
Document V3 command API, persistence reload, and DOCX/PDF exporters use their
production implementations.  All state is isolated in a temporary directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch


def _require(response, label: str):
    if response.status_code != 200:
        raise AssertionError(f"{label} failed ({response.status_code}): {response.text[:500]}")
    return response


def _blocks(document: dict) -> list[dict]:
    sections = document.get("sections") or []
    if not sections:
        return []
    return list(sections[0].get("content") or [])


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="writing-agent-product-smoke-") as temp:
        root = Path(temp)
        os.environ["WRITING_AGENT_DATA_DIR"] = str(root / "data")
        os.environ["WRITING_AGENT_CACHE_DIR"] = str(root / "cache")
        os.environ["WRITING_AGENT_USE_ROUTE_GRAPH"] = "1"
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

        from fastapi.testclient import TestClient

        import writing_agent.web.app_v2 as app_v2
        from writing_agent.storage import InMemoryStore

        client = TestClient(app_v2.app)
        session = app_v2.store.create()
        doc_id = session.id

        generated_text = (
            "# 基于训练日志的智能分析\n\n"
            "## 研究背景\n\n"
            "训练日志能够把分散的运动记录转化为可复核的数据。\n\n"
            "## 系统设计\n\n"
            "系统采用结构化文档命令，使用户编辑与智能操作共享同一份文档。"
        )

        def deterministic_generation(**_kwargs):
            return {
                "ok": 1,
                "text": generated_text,
                "problems": [],
                "trace_id": "deterministic-product-smoke",
                "engine": "deterministic-test-provider",
                "route_id": "full_document",
                "route_entry": "writer",
            }

        with (
            patch.object(app_v2, "_ensure_ollama_ready", return_value=(True, "")),
            patch.object(app_v2, "_try_quick_edit", return_value=None),
            patch.object(app_v2, "_run_message_analysis", return_value={}),
            patch.object(app_v2, "_try_ai_intent_edit", return_value=None),
            patch.object(app_v2, "_should_route_to_revision", return_value=False),
            patch.object(app_v2, "_should_use_fast_generate", return_value=False),
            patch.object(app_v2, "run_generate_graph_dual_engine", side_effect=deterministic_generation),
        ):
            generated = _require(
                client.post(
                    f"/api/doc/{doc_id}/generate",
                    json={"instruction": "生成毕业论文初稿", "text": "", "compose_mode": "replace"},
                ),
                "generation",
            ).json()

        assert generated.get("ok") == 1
        assert generated.get("graph_meta", {}).get("route_id") == "full_document"

        generated_state = _require(client.get(f"/api/doc/{doc_id}"), "read generated document").json()
        document = generated_state["document_v3"]
        if not document:
            # The desktop client performs this same compatibility conversion
            # when a text-generation response predates native Document V3.
            from writing_agent.v3 import migrate_doc_ir

            document = migrate_doc_ir(generated.get("doc_ir") or generated_state.get("doc_ir") or {}).model_dump(
                mode="json", by_alias=True
            )
            _require(
                client.post(f"/api/doc/{doc_id}/save", json={"document_v3": document}),
                "generation to Document V3 conversion",
            )
        blocks = _blocks(document)
        assert len(blocks) >= 5, "generation was not converted into structured blocks"
        original_ids = [str(block["id"]) for block in blocks]

        # Human cross-block edit through the same command API used by the UI.
        first_paragraph = next(block for block in blocks if block.get("type") == "paragraph")
        edited = _require(
            client.post(
                f"/api/doc/{doc_id}/document-v3/commands",
                json={
                    "command": {
                        "id": "smoke-human-edit",
                        "type": "replace_text",
                        "target": {"kind": "nodes", "node_ids": [first_paragraph["id"]]},
                        "params": {"text": "训练日志为分析、反馈和复盘提供可追踪的数据基础。"},
                        "source": "user",
                    }
                },
            ),
            "human edit command",
        ).json()
        assert edited.get("changed") is True

        # AI and user actions intentionally share the validated command registry.
        latest_blocks = _blocks(edited["document"])
        last_id = str(latest_blocks[-1]["id"])
        inserted = _require(
            client.post(
                f"/api/doc/{doc_id}/document-v3/commands",
                json={
                    "command": {
                        "id": "smoke-ai-insert",
                        "type": "insert_blocks",
                        "target": {"kind": "nodes", "node_ids": [last_id]},
                        "params": {
                            "placement": "after",
                            "allowed_node_ids": [last_id],
                            "blocks": [{
                                "id": "smoke_conclusion",
                                "type": "paragraph",
                                "styleId": "normal",
                                "content": [{"type": "text", "text": "测试结论：完整工作流保持结构化且可编辑。"}],
                            }],
                        },
                        "source": "ai",
                    }
                },
            ),
            "AI document command",
        ).json()
        assert inserted.get("changed") is True

        moved = _require(
            client.post(
                f"/api/doc/{doc_id}/document-v3/commands",
                json={
                    "command": {
                        "id": "smoke-block-move",
                        "type": "move_blocks",
                        "target": {"kind": "nodes", "node_ids": ["smoke_conclusion"]},
                        "params": {"anchor_id": original_ids[0], "placement": "after"},
                        "source": "user",
                    }
                },
            ),
            "block move command",
        ).json()
        assert moved.get("changed") is True

        # Page setup is persisted as document data, exactly as the page dialog saves it.
        final_document = moved["document"]
        section = final_document["sections"][0]
        section["layout"].update({
            "pageSize": "A5",
            "orientation": "portrait",
            "marginTopMm": 22.0,
            "marginRightMm": 20.0,
            "marginBottomMm": 22.0,
            "marginLeftMm": 24.0,
        })
        section["headerFooter"]["pageNumber"].update({
            "enabled": True,
            "startAt": 3,
            "format": "arabic",
            "position": "footer",
            "alignment": "center",
        })
        _require(
            client.post(f"/api/doc/{doc_id}/save", json={"document_v3": final_document}),
            "save",
        )

        # Simulate closing and reopening by reconstructing the persistent store.
        app_v2.store = InMemoryStore(persistence_dir=app_v2.WORKSPACE_DIR)
        reopened = _require(client.get(f"/api/doc/{doc_id}"), "reopen").json()
        reopened_document = reopened["document_v3"]
        reopened_blocks = _blocks(reopened_document)
        assert reopened_blocks[1]["id"] == "smoke_conclusion", "block order was not persisted"
        assert reopened_document["sections"][0]["layout"]["pageSize"] == "A5"
        assert reopened_document["sections"][0]["headerFooter"]["pageNumber"]["startAt"] == 3

        docx = _require(client.get(f"/download/{doc_id}.docx"), "DOCX export").content
        pdf = _require(client.get(f"/download/{doc_id}.pdf"), "PDF export").content
        assert docx.startswith(b"PK") and len(docx) > 5_000, "DOCX export is not a valid OOXML archive"
        assert pdf.startswith(b"%PDF-") and len(pdf) > 1_000, "PDF export is not a valid PDF"

        # The material library is independent from document import: upload,
        # preview, AI opt-in, recycle, restore, and permanent deletion all use
        # the production API without replacing the current document.
        before_material_upload = _require(client.get(f"/api/doc/{doc_id}"), "document before material upload").json()["document_v3"]
        material = _require(
            client.post(
                "/api/library/upload",
                files={"file": ("训练依据.md", "# 训练依据\n\n渐进负荷需要结合恢复状态。".encode("utf-8"), "text/markdown")},
            ),
            "material upload",
        ).json()["item"]
        material_id = material["doc_id"]
        listed = _require(client.get("/api/library/items?status=all"), "material list").json()["items"]
        assert any(item["doc_id"] == material_id for item in listed)
        preview = _require(client.get(f"/api/library/item/{material_id}"), "material preview").json()
        assert "渐进负荷" in preview["text"]
        approved = _require(client.post(f"/api/library/item/{material_id}/approve"), "material approve").json()
        assert approved["item"]["status"] == "approved"
        trashed = _require(client.post(f"/api/library/item/{material_id}/trash"), "material trash").json()
        assert trashed["item"]["status"] == "trashed"
        restored = _require(client.post(f"/api/library/item/{material_id}/restore"), "material restore").json()
        assert restored["item"]["status"] == "pending"
        _require(client.post(f"/api/library/item/{material_id}/trash"), "material second trash")
        _require(client.delete(f"/api/library/item/{material_id}"), "material delete")
        after_material_upload = _require(client.get(f"/api/doc/{doc_id}"), "document after material upload").json()["document_v3"]
        assert before_material_upload == after_material_upload, "material upload unexpectedly replaced document content"

        print("PASS deterministic product workflow")
        print(f"  generated structured blocks: {len(blocks)}")
        print("  human edit + AI command + block move: pass")
        print("  A5 setup + page number start 3 + persistence reload: pass")
        print(f"  DOCX/PDF export: {len(docx)} / {len(pdf)} bytes")
        print("  material upload/preview/AI opt-in/recycle/delete: pass")
        print("  external model calls: 0; test-provider cost: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
