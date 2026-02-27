"""Doc Ir Html Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from typing import Callable


def style_dict_to_css(style: dict | None, *, esc: Callable[[str], str]) -> str:
    if not isinstance(style, dict):
        return ""
    css = []
    align = str(style.get("align") or style.get("textAlign") or "").strip()
    if align in {"left", "center", "right", "justify"}:
        css.append(f"text-align:{align}")
    line_height = str(style.get("lineHeight") or "").strip()
    if re.match(r"^\d+(\.\d+)?$", line_height):
        css.append(f"line-height:{line_height}")
    indent = str(style.get("indent") or style.get("textIndent") or "").strip()
    if re.match(r"^\d+(\.\d+)?(px|pt|em|rem)?$", indent):
        css.append(f"text-indent:{indent}")
    margin_top = str(style.get("marginTop") or "").strip()
    if re.match(r"^\d+(\.\d+)?(px|pt|em|rem)?$", margin_top):
        css.append(f"margin-top:{margin_top}")
    margin_bottom = str(style.get("marginBottom") or "").strip()
    if re.match(r"^\d+(\.\d+)?(px|pt|em|rem)?$", margin_bottom):
        css.append(f"margin-bottom:{margin_bottom}")
    font_family = str(style.get("fontFamily") or "").strip()
    if font_family:
        css.append(f"font-family:{esc(font_family)}")
    font_size = str(style.get("fontSize") or "").strip()
    if re.match(r"^\d+(\.\d+)?(px|pt|em|rem)?$", font_size):
        css.append(f"font-size:{font_size}")
    color = str(style.get("color") or "").strip()
    if re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", color) or color.startswith("rgb("):
        css.append(f"color:{esc(color)}")
    background = str(style.get("background") or style.get("backgroundColor") or "").strip()
    if re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", background) or background.startswith("rgb("):
        css.append(f"background-color:{esc(background)}")
    return f' style="{";".join(css)}"' if css else ""


def run_to_html(run: dict, *, esc: Callable[[str], str]) -> str:
    txt = esc(str(run.get("text") or "")).replace("\n", "<br/>")
    if not txt:
        return ""
    inner = txt
    if run.get("bold"):
        inner = f"<strong>{inner}</strong>"
    if run.get("italic"):
        inner = f"<em>{inner}</em>"
    if run.get("underline"):
        inner = f"<u>{inner}</u>"
    if run.get("strike"):
        inner = f"<del>{inner}</del>"
    link = str(run.get("link") or "").strip()
    if link:
        inner = f'<a href="{esc(link)}" target="_blank" rel="noopener">{inner}</a>'
    css = []
    color = str(run.get("color") or "").strip()
    if re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", color) or color.startswith("rgb("):
        css.append(f"color:{esc(color)}")
    background = str(run.get("background") or "").strip()
    if re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", background) or background.startswith("rgb("):
        css.append(f"background-color:{esc(background)}")
    font = str(run.get("font") or "").strip()
    if font:
        css.append(f"font-family:{esc(font)}")
    size = str(run.get("size") or "").strip()
    if re.match(r"^\d+(\.\d+)?(px|pt|em|rem)?$", size):
        css.append(f"font-size:{size}")
    if css:
        inner = f'<span style="{";".join(css)}">{inner}</span>'
    return inner


def runs_to_html(runs: list[dict], *, esc: Callable[[str], str]) -> str:
    parts = [run_to_html(r, esc=esc) for r in runs if isinstance(r, dict)]
    return "".join([p for p in parts if p])


def doc_ir_to_html(doc_ir, *, esc: Callable[[str], str], doc_ir_to_dict: Callable[[object], dict]) -> str:
    data = doc_ir_to_dict(doc_ir) if not isinstance(doc_ir, dict) else doc_ir
    if not isinstance(data, dict):
        return ""
    title = str(data.get("title") or "").strip()
    parts: list[str] = []
    if title:
        parts.append(f'<h1 style="text-align:center;margin-bottom:12pt">{esc(title)}</h1>')

    def render_block(block: dict) -> str:
        t = str(block.get("type") or "paragraph").lower()
        style = style_dict_to_css(block.get("style") if isinstance(block.get("style"), dict) else None, esc=esc)
        runs = block.get("runs") if isinstance(block.get("runs"), list) else None
        if t == "heading":
            level = max(1, min(6, int(block.get("level") or 1)))
            if runs:
                inner = runs_to_html(runs, esc=esc)
            else:
                inner = esc(str(block.get("text") or ""))
            return f"<h{level}{style}>{inner}</h{level}>"
        if t in {"paragraph", "text", "p"}:
            if runs:
                inner = runs_to_html(runs, esc=esc)
            else:
                inner = esc(str(block.get("text") or "")).replace("\n", "<br/>")
            return f"<p{style}>{inner}</p>"
        if t == "list":
            ordered = bool(block.get("ordered"))
            items = block.get("items") if isinstance(block.get("items"), list) else []
            li = "".join([f"<li{style}>{esc(str(it))}</li>" for it in items if str(it).strip()])
            tag = "ol" if ordered else "ul"
            return f"<{tag}{style}>{li}</{tag}>"
        if t == "table":
            tdata = block.get("table") if isinstance(block.get("table"), dict) else {}
            caption = esc(str(tdata.get("caption") or "").strip() or "表格")
            cols = tdata.get("columns") if isinstance(tdata.get("columns"), list) else []
            rows = tdata.get("rows") if isinstance(tdata.get("rows"), list) else []
            if not cols:
                cols = ["列1", "列2"]
            head = "".join([f"<th>{esc(str(c))}</th>" for c in cols])
            body_rows = []
            for r in rows[:20]:
                rlist = r if isinstance(r, list) else [r]
                row_html = "".join([f"<td>{esc(str(rlist[i]) if i < len(rlist) else '')}</td>" for i in range(len(cols))])
                body_rows.append(f"<tr>{row_html}</tr>")
            body = "".join(body_rows)
            return (
                f"<p style=\"margin-top:6pt;margin-bottom:4pt\"><strong>{caption}</strong></p>"
                f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
            )
        if t == "figure":
            fdata = block.get("figure") if isinstance(block.get("figure"), dict) else {}
            caption = esc(str(fdata.get("caption") or "图"))
            return f'<p style="margin-top:6pt;margin-bottom:4pt"><strong>图：</strong>{caption}</p>'
        return ""

    def walk_sections(sections: list[dict]) -> None:
        for sec in sections:
            sec_title = str(sec.get("title") or "").strip()
            level = max(1, min(6, int(sec.get("level") or 2)))
            sec_style = style_dict_to_css(sec.get("style") if isinstance(sec.get("style"), dict) else None, esc=esc)
            if sec_title:
                parts.append(f"<h{level}{sec_style}>{esc(sec_title)}</h{level}>")
            blocks = sec.get("blocks")
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict):
                        html = render_block(b)
                        if html:
                            parts.append(html)
            children = sec.get("children")
            if isinstance(children, list):
                walk_sections(children)

    sections = data.get("sections")
    if isinstance(sections, list):
        walk_sections(sections)
    return "".join(parts)

