"""Doc State Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from typing import Any, Callable


def normalize_doc_ir_for_export(
    doc_ir: Any,
    session: Any,
    *,
    ensure_mcp_citations: Callable[[Any], None],
    doc_ir_from_dict: Callable[[dict], Any],
    doc_ir_to_text: Callable[[Any], str],
    doc_ir_from_text: Callable[[str], Any],
    doc_ir_has_styles: Callable[[Any], bool],
    normalize_export_text: Callable[..., str],
) -> Any:
    ensure_mcp_citations(session)
    if getattr(session, "doc_ir", None):
        try:
            doc_ir = doc_ir_from_dict(session.doc_ir)
        except Exception:
            pass
    if doc_ir is None:
        return doc_ir
    try:
        if doc_ir_has_styles(doc_ir):
            return doc_ir
    except Exception:
        pass
    try:
        text = doc_ir_to_text(doc_ir)
    except Exception:
        return doc_ir
    text = normalize_export_text(text, session=session)
    text = re.sub(r"(?m)^(#{1,6})([^#\s])", r"\1 \2", text)
    try:
        return doc_ir_from_text(text)
    except Exception:
        return doc_ir


def safe_doc_text(
    session: Any,
    *,
    plan_title: Callable[..., str],
    fallback_sections_from_session: Callable[[Any], list[str]],
    build_fallback_text: Callable[..., str],
    store_put: Callable[[Any], None],
    doc_ir_to_text: Callable[[Any], str],
    doc_ir_from_dict: Callable[[dict], Any],
    set_doc_text: Callable[[Any, str], None],
) -> str:
    text = str(getattr(session, "doc_text", "") or "")
    if text.strip() and not getattr(session, "template_outline", None) and not getattr(session, "template_required_h2", None):
        try:
            title = plan_title(
                current_text="",
                instruction=str((getattr(session, "generation_prefs", {}) or {}).get("extra_requirements") or ""),
            )
            fallback_sections = fallback_sections_from_session(session)
            fallback = build_fallback_text(title, fallback_sections, session)
            if text.strip() == fallback.strip():
                session.doc_text = ""
                session.doc_ir = {}
                store_put(session)
                return ""
        except Exception:
            pass
    if not text.strip() and getattr(session, "doc_ir", None):
        try:
            text = doc_ir_to_text(doc_ir_from_dict(session.doc_ir))
        except Exception:
            text = ""
    if not text.strip():
        session.doc_text = ""
        session.doc_ir = {}
        store_put(session)
        return ""
    set_doc_text(session, text)
    store_put(session)
    return text


def validate_docx_bytes(docx_bytes: bytes) -> list[str]:
    from zipfile import BadZipFile, ZipFile
    import io
    import xml.etree.ElementTree as ET

    issues: list[str] = []
    try:
        with ZipFile(io.BytesIO(docx_bytes), "r") as zin:
            names = zin.namelist()
            required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
            missing = [n for n in required if n not in names]
            if missing:
                issues.append(f"missing:{','.join(missing)}")
            for name in names:
                if not name.lower().endswith(".xml"):
                    continue
                try:
                    ET.fromstring(zin.read(name))
                except Exception:
                    issues.append(f"xml:{name}")
    except BadZipFile:
        issues.append("badzip")
    except Exception:
        issues.append("unknown")
    return issues


def set_doc_text(
    session: Any,
    text: str,
    *,
    doc_ir_to_dict: Callable[[Any], dict],
    doc_ir_from_text: Callable[[str], Any],
) -> None:
    session.doc_text = text
    if not str(text or "").strip():
        session.doc_ir = {}
        return
    try:
        session.doc_ir = doc_ir_to_dict(doc_ir_from_text(text))
    except Exception:
        session.doc_ir = {}


def safe_doc_ir_payload(
    text: str,
    *,
    doc_ir_to_dict: Callable[[Any], dict],
    doc_ir_from_text: Callable[[str], Any],
) -> dict:
    if not str(text or "").strip():
        return {}
    try:
        return doc_ir_to_dict(doc_ir_from_text(str(text)))
    except Exception:
        return {}


def doc_ir_has_styles(
    doc_ir: Any,
    *,
    doc_ir_to_dict: Callable[[Any], dict],
) -> bool:
    try:
        data = doc_ir_to_dict(doc_ir) if not isinstance(doc_ir, dict) else doc_ir
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    if isinstance(data.get("style"), dict) and data.get("style"):
        return True

    def block_has_style(block: dict) -> bool:
        if isinstance(block.get("style"), dict) and block.get("style"):
            return True
        runs = block.get("runs")
        if isinstance(runs, list):
            for run in runs:
                if not isinstance(run, dict):
                    continue
                for key in ("bold", "italic", "underline", "strike", "color", "background", "font", "size", "link"):
                    if run.get(key):
                        return True
        return False

    def walk_sections(sections: list[dict]) -> bool:
        for sec in sections:
            if isinstance(sec.get("style"), dict) and sec.get("style"):
                return True
            blocks = sec.get("blocks")
            if isinstance(blocks, list):
                for block in blocks:
                    if isinstance(block, dict) and block_has_style(block):
                        return True
            children = sec.get("children")
            if isinstance(children, list) and walk_sections(children):
                return True
        return False

    sections = data.get("sections")
    if isinstance(sections, list):
        return walk_sections(sections)
    return False
