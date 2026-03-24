"""Block rendering and persistence helpers extracted from graph_section_draft_domain."""

from __future__ import annotations

import json


def render_block_to_text(block: dict) -> str:
    block_type = str(block.get("type") or "paragraph").lower()
    if block_type in {"paragraph", "text", "p"}:
        return str(block.get("text") or "").strip()
    if block_type in {"list", "bullets", "bullet"}:
        items = block.get("items")
        if isinstance(items, list):
            return "\n".join([f"- {str(item).strip()}" for item in items if str(item).strip()]).strip()
        raw = str(block.get("text") or "").strip()
        if raw:
            lines = [line.strip() for line in raw.splitlines() if line.strip()]
            return "\n".join([line if line.startswith("-") else f"- {line}" for line in lines]).strip()
        return ""
    if block_type in {"table", "figure"}:
        marker = "TABLE" if block_type == "table" else "FIGURE"
        payload = {}
        for key in ("caption", "columns", "rows", "data"):
            if key in block and block.get(key) is not None:
                payload[key] = block.get(key)
        if block_type == "figure":
            figure_kind = str(block.get("kind") or block.get("figure_type") or payload.get("type") or "").strip().lower()
            if figure_kind:
                payload["type"] = figure_kind
        return f"[[{marker}:{json.dumps(payload, ensure_ascii=False)}]]"
    if block_type in {"reference", "ref"}:
        raw = str(block.get("text") or "").strip()
        if raw:
            return raw
        items = block.get("items")
        if isinstance(items, list):
            return "\n".join([str(item).strip() for item in items if str(item).strip()]).strip()
        return ""
    return str(block.get("text") or "").strip()


def persist_block_to_store(block: dict, text_store) -> str | None:
    if text_store is None or not isinstance(block, dict):
        return None
    block_type = str(block.get("type") or "paragraph").lower()
    block_id = str(block.get("block_id") or block.get("id") or "").strip() or None
    if block_type in {"paragraph", "text", "p"}:
        text = str(block.get("text") or "").strip()
        if not text:
            return block_id
        return text_store.put_text(text, block_id=block_id)
    if block_type in {"list", "bullets", "bullet"}:
        items = block.get("items")
        payload = {"items": items} if isinstance(items, list) else {"text": str(block.get("text") or "").strip()}
        return text_store.put_json(payload, block_id=block_id, prefix="l")
    if block_type == "table":
        payload = {}
        for key in ("caption", "columns", "rows", "data"):
            if key in block and block.get(key) is not None:
                payload[key] = block.get(key)
        return text_store.put_json(payload, block_id=block_id, prefix="t")
    if block_type == "figure":
        payload = {}
        for key in ("caption", "data"):
            if key in block and block.get(key) is not None:
                payload[key] = block.get(key)
        figure_kind = str(block.get("kind") or block.get("figure_type") or payload.get("type") or "").strip().lower()
        if figure_kind:
            payload["type"] = figure_kind
        return text_store.put_json(payload, block_id=block_id, prefix="f")
    if block_type in {"reference", "ref"}:
        text = str(block.get("text") or "").strip()
        if not text:
            items = block.get("items")
            if isinstance(items, list):
                text = "\n".join([str(item).strip() for item in items if str(item).strip()]).strip()
        if not text:
            return block_id
        return text_store.put_text(text, block_id=block_id)
    return block_id


def accept_block(block: dict, section_id: str, is_reference: bool) -> bool:
    sec = str(block.get("section_id") or "").strip()
    if sec != section_id:
        return False
    block_type = str(block.get("type") or "").lower()
    if not is_reference and block_type in {"reference", "ref"}:
        return False
    return True


__all__ = [name for name in globals() if not name.startswith("__")]
