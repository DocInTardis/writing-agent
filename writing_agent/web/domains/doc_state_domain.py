"""Doc State Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import re
import os
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
    canonicalize_ir = str(os.environ.get("WRITING_AGENT_EXPORT_DOC_IR_CANONICALIZE", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not canonicalize_ir:
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
    # Keep DocIR as single source-of-truth when it already exists.
    if getattr(session, "doc_ir", None):
        session.doc_text = text
        store_put(session)
        return text
    set_doc_text(session, text)
    store_put(session)
    return text


def validate_docx_bytes(docx_bytes: bytes) -> list[str]:
    from zipfile import BadZipFile, ZipFile
    import io
    import xml.etree.ElementTree as ET
    import posixpath

    issues: list[str] = []

    def add_issue(code: str) -> None:
        if code and code not in issues:
            issues.append(code)

    try:
        with ZipFile(io.BytesIO(docx_bytes), "r") as zin:
            names = zin.namelist()
            required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
            missing = [n for n in required if n not in names]
            if missing:
                add_issue(f"missing:{','.join(missing)}")
            xml_parts: dict[str, bytes] = {}
            for name in names:
                if not name.lower().endswith(".xml"):
                    continue
                try:
                    raw = zin.read(name)
                    ET.fromstring(raw)
                    xml_parts[name] = raw
                except Exception:
                    add_issue(f"xml:{name}")

            ns = {
                "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
                "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
                "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
            }
            rel_map: dict[str, str] = {}
            rels_raw = xml_parts.get("word/_rels/document.xml.rels")
            if rels_raw:
                try:
                    rels_root = ET.fromstring(rels_raw)
                    for rel in rels_root.findall(".//pr:Relationship", ns):
                        rid = str(rel.attrib.get("Id") or "")
                        target = str(rel.attrib.get("Target") or "")
                        if rid and target:
                            rel_map[rid] = target
                except Exception:
                    add_issue("xml:word/_rels/document.xml.rels")

            doc_raw = xml_parts.get("word/document.xml")
            if doc_raw:
                try:
                    doc_root = ET.fromstring(doc_raw)
                    non_default_footer_types: set[str] = set()
                    footer_rids: list[tuple[str, str]] = []
                    for sect in doc_root.findall(".//w:sectPr", ns):
                        seen_default_footer = False
                        for ref in sect.findall("w:footerReference", ns):
                            ref_type = str(ref.attrib.get(f"{{{ns['w']}}}type") or "default").lower()
                            rid = str(ref.attrib.get(f"{{{ns['r']}}}id") or "")
                            footer_rids.append((ref_type, rid))
                            if ref_type != "default":
                                non_default_footer_types.add(ref_type)
                            if ref_type == "default":
                                if seen_default_footer:
                                    add_issue("footer-ref:duplicate-default")
                                seen_default_footer = True
                    for ref_type in sorted(non_default_footer_types):
                        add_issue(f"footer-ref:nondefault:{ref_type}")

                    if rel_map:
                        for ref_type, rid in footer_rids:
                            if not rid:
                                add_issue("rels:footer-ref-missing-rid")
                                continue
                            target = rel_map.get(rid)
                            if not target:
                                add_issue(f"rels:missing-footer-target:{rid}")
                                continue
                            part_path = posixpath.normpath(posixpath.join("word", target)).lstrip("/")
                            if part_path not in names:
                                add_issue(f"rels:missing-footer-part:{ref_type}")
                except Exception:
                    add_issue("xml:word/document.xml")

            page_field_empty_re = re.compile(
                r"<(?:\w+:)?instrText[^>]*>\s*PAGE[^<]*</(?:\w+:)?instrText>[\s\S]{0,300}?fldCharType=\"separate\"[\s\S]{0,200}?(?:<(?:\w+:)?t[^>]*/>|<(?:\w+:)?t[^>]*>\s*</(?:\w+:)?t>)",
                re.IGNORECASE,
            )
            for name, raw in xml_parts.items():
                if not name.startswith("word/footer") or not name.endswith(".xml"):
                    continue
                xml_text = raw.decode("utf-8", errors="ignore")
                if page_field_empty_re.search(xml_text):
                    add_issue(f"page-field-empty:{name}")
    except BadZipFile:
        add_issue("badzip")
    except Exception:
        add_issue("unknown")
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
