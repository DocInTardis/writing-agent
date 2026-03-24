"""Content and packaging helpers for DOCX export."""

from __future__ import annotations

import io
import os
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from docx import Document
from docx.oxml.text.paragraph import CT_P
from docx.text.paragraph import Paragraph

from writing_agent.v2.doc_format import DocBlock


def _sanitize_heading_text(text: str) -> str:
    token = str(text or "").strip()
    token = re.sub(r"^\s*#{1,}\s+", "", token)
    token = token.replace("`", "")
    token = re.sub(r"^\s*[*\-•]\s+", "", token)
    return token.strip()


def _normalize_section_title(text: str) -> str:
    token = _sanitize_heading_text(text)
    token = re.sub(r"^\d+(?:\.\d+)*\s*", "", token)
    token = re.sub(r"^[一二三四五六七八九十]+、\s*", "", token)
    token = re.sub(r"^第[\d一二三四五六七八九十百]+[章节]\s*", "", token)
    return token.strip()


def _is_reference_title(title: str) -> bool:
    token = str(title or "").strip().lower()
    if not token:
        return False
    return any(
        key in token
        for key in (
            "参考文献",
            "参考资料",
            "references",
            "reference",
            "bibliography",
        )
    )


def _clear_doc_body(doc: Document) -> None:
    body = doc.element.body  # type: ignore[attr-defined]
    sects = [child for child in list(body) if child.tag.endswith("}sectPr")]
    keep_sect = sects[-1] if sects else None
    for child in list(body):
        if child is keep_sect:
            continue
        body.remove(child)


def _truncate_template_body(doc: Document) -> None:
    _clear_doc_body(doc)


def _ensure_min_figures(blocks: list[DocBlock]) -> list[DocBlock]:
    raw = os.environ.get("WRITING_AGENT_EXPORT_MIN_FIGURES", "2").strip()
    try:
        min_figs = int(raw)
    except Exception:
        min_figs = 1
    if min_figs <= 0:
        return blocks
    count = sum(1 for b in blocks if b.type == "figure")
    if count >= min_figs:
        return blocks

    specs = [
        {
            "type": "flow",
            "caption": "\u7cfb\u7edf\u5f00\u53d1\u6d41\u7a0b",
            "data": {"nodes": ["\u9700\u6c42\u8c03\u7814", "\u6982\u8981\u8bbe\u8ba1", "\u8be6\u7ec6\u8bbe\u8ba1", "\u7f16\u7801\u6d4b\u8bd5", "\u90e8\u7f72\u8fd0\u7ef4"]},
        },
        {
            "type": "bar",
            "caption": "\u6a21\u5757\u5de5\u4f5c\u91cf\u5206\u5e03",
            "data": {"labels": ["\u6838\u5fc3\u529f\u80fd", "\u6570\u636e\u5c42", "\u63a5\u53e3\u5c42", "\u754c\u9762\u5c42"], "values": [4, 3, 2, 1]},
        },
        {
            "type": "line",
            "caption": "\u5173\u952e\u6307\u6807\u8d8b\u52bf",
            "data": {"labels": ["\u9636\u6bb51", "\u9636\u6bb52", "\u9636\u6bb53", "\u9636\u6bb54"], "series": {"name": "\u54cd\u5e94\u65f6\u95f4(ms)", "values": [220, 180, 150, 130]}},
        },
    ]

    insert_points = [i + 1 for i, b in enumerate(blocks) if b.type == "heading"]
    if not insert_points:
        return blocks

    out = list(blocks)
    offset = 0
    spec_idx = 0
    for idx in insert_points:
        if count >= min_figs:
            break
        out.insert(idx + offset, DocBlock(type="figure", figure=specs[spec_idx % len(specs)]))
        count += 1
        offset += 1
        spec_idx += 1
    while count < min_figs:
        out.append(DocBlock(type="figure", figure=specs[spec_idx % len(specs)]))
        count += 1
        spec_idx += 1
    return out


def _ensure_min_tables(blocks: list[DocBlock]) -> list[DocBlock]:
    raw = os.environ.get("WRITING_AGENT_EXPORT_MIN_TABLES", "2").strip()
    try:
        min_tables = int(raw)
    except Exception:
        min_tables = 1
    if min_tables <= 0:
        return blocks
    count = sum(1 for b in blocks if b.type == "table")
    if count >= min_tables:
        return blocks

    sample = {
        "caption": "\u6307\u6807\u6c47\u603b",
        "columns": ["\u6307\u6807", "\u8bf4\u660e", "\u53d6\u503c"],
        "rows": [
            ["\u53ef\u7528\u6027", "\u670d\u52a1\u7a33\u5b9a\u6027", "99.9%"],
            ["\u54cd\u5e94\u65f6\u95f4", "\u5e73\u5747\u54cd\u5e94", "<200ms"],
            ["\u5e76\u53d1\u80fd\u529b", "\u5cf0\u503c\u5e76\u53d1", "1000 QPS"],
        ],
    }

    insert_points = [i + 1 for i, b in enumerate(blocks) if b.type == "heading"]
    if not insert_points:
        return blocks

    out = list(blocks)
    offset = 0
    for idx in insert_points:
        if count >= min_tables:
            break
        out.insert(idx + offset, DocBlock(type="table", table=sample))
        count += 1
        offset += 1
    while count < min_tables:
        out.append(DocBlock(type="table", table=sample))
        count += 1
    return out


def _ensure_reference_section(blocks: list[DocBlock]) -> list[DocBlock]:
    def _looks_like_reference_item(text: str) -> bool:
        if re.search(r"(19|20)\d{2}", text):
            return True
        if re.search(r"(出版社|期刊|学报|杂志|Journal|Conference|Proceedings|Transactions|IEEE|ACM)", text, re.IGNORECASE):
            return True
        return False

    content: list[DocBlock] = []
    ref_lines: list[str] = []
    in_ref = False
    saw_reference_heading = False
    for b in blocks:
        if b.type == "heading":
            raw_text = (b.text or "").strip()
            if re.match(r"^\s*\[\d+\]\s*", raw_text):
                if raw_text:
                    ref_lines.append(raw_text)
                continue
            title = _normalize_section_title(_sanitize_heading_text(raw_text))
            if _is_reference_title(title):
                in_ref = True
                saw_reference_heading = True
                continue
            content.append(b)
            continue
        if b.type == "paragraph":
            text = (b.text or "").strip()
            if in_ref:
                if re.match(r"^\s*\[\d+\]\s*", text):
                    if text:
                        ref_lines.append(text)
                    continue
                if text and _looks_like_reference_item(text):
                    ref_lines.append(text)
                    continue
                content.append(b)
                continue
            if re.match(r"^\s*\[\d+\]\s*", text):
                if text:
                    ref_lines.append(text)
                continue
            content.append(b)
            continue
        # Preserve non-reference blocks that appear after a reference heading.
        # They are moved back into normal content instead of being dropped silently.
        content.append(b)

    refs: list[str] = []
    for line in ref_lines:
        m = re.match(r"^\s*\[(\d+)\]\s*(.+)$", line)
        if m:
            item = m.group(2).strip()
        else:
            item = line.strip()
        if item and _looks_like_reference_item(item):
            refs.append(item)

    seen: set[str] = set()
    deduped: list[str] = []
    for item in refs:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)

    if saw_reference_heading or deduped:
        content.append(DocBlock(type="heading", level=2, text="\u53c2\u8003\u6587\u732e"))
        for item in deduped:
            content.append(DocBlock(type="paragraph", text=item))
    return content

def _find_template_body_anchor(doc: Document):
    body = doc.element.body  # type: ignore[attr-defined]
    for child in body.iterchildren():
        if not isinstance(child, CT_P):
            continue
        p = Paragraph(child, doc)
        text = (p.text or "").strip()
        if not text:
            continue
        style = ""
        try:
            style = str(p.style.name or "")
        except Exception:
            style = ""
        if _is_toc_style(style) or _looks_like_toc_entry(text):
            continue
        if _is_heading_para(style, text):
            return child
    return None


def _is_heading_para(style: str, text: str) -> bool:
    style_lower = str(style or "").lower()
    if any(token in style_lower for token in ("heading 1", "heading 2", "heading 3", "toc heading")):
        return True
    style_text = str(style or "")
    if any(
        token in style_text
        for token in (
            "标题 1",
            "标题1",
            "标题 2",
            "标题2",
            "标题 3",
            "标题3",
            "自定义标题",
        )
    ):
        return True
    return _looks_like_heading_text(text)


def _looks_like_heading_text(text: str) -> bool:
    token = str(text or "").strip()
    if not token:
        return False
    patterns = (
        r"^\s*第[\d一二三四五六七八九十百]+[章节]\s*.+$",
        r"^\s*\d+(?:\.\d+)+\s+.+$",
        r"^\s*[一二三四五六七八九十]+、\s*.+$",
        r"^\s*[（(][一二三四五六七八九十]+[)）]\s*.+$",
    )
    return any(re.match(pattern, token) for pattern in patterns)


def _is_toc_style(style: str) -> bool:
    style_text = str(style or "")
    return "toc" in style_text.lower() or "目录" in style_text


def _looks_like_toc_entry(text: str) -> bool:
    token = str(text or "").strip()
    if not token:
        return False
    return bool(re.search(r"[\.·…]{2,}\s*\d+$", token))


def _detect_template_heading_styles(doc: Document) -> dict[int, str]:
    names = {str(style.name) for style in doc.styles if getattr(style, "name", None)}
    lower_names = {name.lower(): name for name in names}
    styles: dict[int, str] = {}

    custom_candidates = {
        1: ["自定义标题 1", "自定义标题1", "自定义标题"],
        2: ["自定义标题 2", "自定义标题2", "自定义标题"],
        3: ["自定义标题 3", "自定义标题3", "自定义标题"],
    }
    heading_candidates = {
        1: ["heading 1", "标题 1", "标题1"],
        2: ["heading 2", "标题 2", "标题2"],
        3: ["heading 3", "标题 3", "标题3"],
    }

    for level, candidates in custom_candidates.items():
        for candidate in candidates:
            if candidate in names:
                styles[level] = candidate
                break
    for level, candidates in heading_candidates.items():
        for candidate in candidates:
            resolved = lower_names.get(candidate.lower())
            if resolved:
                styles[level] = resolved
                break
    return styles


def _save_doc(doc: Document) -> bytes:

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _postprocess_toc_footer_numbers(docx_bytes: bytes) -> bytes:
    import io

    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }

    with ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        try:
            doc_xml = zin.read("word/document.xml")
            rels_xml = zin.read("word/_rels/document.xml.rels")
        except Exception:
            return docx_bytes

        doc = ET.fromstring(doc_xml)
        rels = ET.fromstring(rels_xml)
        relmap = {
            rel.attrib.get("Id"): rel.attrib.get("Target")
            for rel in rels.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
        }
        footer_targets: set[str] = set()
        for sect in doc.findall(".//w:sectPr", ns):
            pg = sect.find("w:pgNumType", ns)
            if pg is None:
                continue
            fmt = pg.attrib.get(f"{{{ns['w']}}}fmt")
            if fmt != "upperRoman":
                continue
            for ref in sect.findall("w:footerReference", ns):
                if ref.attrib.get(f"{{{ns['w']}}}type") != "default":
                    continue
                rid = ref.attrib.get(f"{{{ns['r']}}}id")
                target = relmap.get(rid)
                if target:
                    footer_targets.add(f"word/{target}")

        if not footer_targets:
            return docx_bytes

        def rewrite_footer(xml_bytes: bytes, instr: str) -> bytes:
            root = ET.fromstring(xml_bytes)
            for child in list(root):
                root.remove(child)
            p = ET.Element(f"{{{ns['w']}}}p")
            ppr = ET.SubElement(p, f"{{{ns['w']}}}pPr")
            jc = ET.SubElement(ppr, f"{{{ns['w']}}}jc")
            jc.set(f"{{{ns['w']}}}val", "center")
            r1 = ET.SubElement(p, f"{{{ns['w']}}}r")
            fld_begin = ET.SubElement(r1, f"{{{ns['w']}}}fldChar")
            fld_begin.set(f"{{{ns['w']}}}fldCharType", "begin")
            r2 = ET.SubElement(p, f"{{{ns['w']}}}r")
            instr_el = ET.SubElement(r2, f"{{{ns['w']}}}instrText")
            instr_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            instr_el.text = instr
            r3 = ET.SubElement(p, f"{{{ns['w']}}}r")
            fld_sep = ET.SubElement(r3, f"{{{ns['w']}}}fldChar")
            fld_sep.set(f"{{{ns['w']}}}fldCharType", "separate")
            r4 = ET.SubElement(p, f"{{{ns['w']}}}r")
            t = ET.SubElement(r4, f"{{{ns['w']}}}t")
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = "I"
            r5 = ET.SubElement(p, f"{{{ns['w']}}}r")
            fld_end = ET.SubElement(r5, f"{{{ns['w']}}}fldChar")
            fld_end.set(f"{{{ns['w']}}}fldCharType", "end")
            root.append(p)
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)

        out = io.BytesIO()
        with ZipFile(out, "w") as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name in footer_targets:
                    data = rewrite_footer(data, "PAGE \\* ROMAN")
                zout.writestr(name, data)
        return out.getvalue()
