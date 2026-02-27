"""Text Export module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

import re
import time


def esc_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_blocks_to_html(blocks) -> str:
    out: list[str] = []
    for block in blocks:
        if block.type == "heading":
            level = max(1, min(3, int(block.level or 1)))
            txt = esc_html(block.text or "")
            if level == 1:
                out.append(f'<h1 style="text-align:center;margin-bottom:12pt">{txt}</h1>')
            elif level == 2:
                out.append(f'<h2 style="margin-top:12pt;margin-bottom:6pt">{txt}</h2>')
            else:
                out.append(f'<h3 style="margin-top:10pt;margin-bottom:4pt">{txt}</h3>')
        elif block.type == "paragraph":
            body = esc_html(block.text or "").replace("\n", "<br/>")
            body = re.sub(r"\[@([a-zA-Z0-9_-]+)\]", r'<sup class="citation-ref">[\1]</sup>', body)
            out.append('<p style="text-align:justify;text-indent:2em;margin-bottom:6pt">' + body + "</p>")
        elif block.type == "table":
            table = block.table or {}
            caption = esc_html(str(table.get("caption") or "").strip() or "表格")
            cols = table.get("columns") if isinstance(table, dict) else None
            rows = table.get("rows") if isinstance(table, dict) else None
            columns = [str(c) for c in cols] if isinstance(cols, list) else ["列1", "列2"]
            body = rows if isinstance(rows, list) else [["[待补充]", "[待补充]"]]
            out.append(f'<p style="margin-top:6pt;margin-bottom:4pt"><strong>{caption}</strong></p>')
            out.append('<table class="tbl"><thead><tr>' + "".join(f"<th>{esc_html(c)}</th>" for c in columns) + "</tr></thead><tbody>")
            for row in body[:20]:
                rr = row if isinstance(row, list) else [str(row)]
                out.append(
                    "<tr>" + "".join(
                        f"<td>{esc_html(str(rr[i]) if i < len(rr) else '')}</td>" for i in range(len(columns))
                    ) + "</tr>"
                )
            out.append("</tbody></table>")
        elif block.type == "figure":
            fig = block.figure or {}
            caption = esc_html(str(fig.get("caption") or "图"))
            out.append(f'<p style="margin-top:6pt;margin-bottom:4pt"><strong>图：</strong>{caption}（导出docx时为占位）</p>')
            out.append(f'<p style="text-indent:2em;margin-bottom:6pt">[图占位] {caption}</p>')
    return "".join(out)


def convert_to_latex(text: str, title: str) -> str:
    lines = text.split("\n")
    latex_lines = [
        r"\documentclass[12pt,a4paper]{article}",
        r"\usepackage[UTF8]{ctex}",
        r"\usepackage{amsmath}",
        r"\usepackage{graphicx}",
        r"\usepackage{hyperref}",
        r"\title{" + title + r"}",
        r"\author{user}",
        r"\date{\today}",
        r"\begin{document}",
        r"\maketitle",
        "",
    ]
    for line in lines:
        if line.startswith("### "):
            latex_lines.append(r"\subsubsection{" + line[4:].strip() + r"}")
        elif line.startswith("## "):
            latex_lines.append(r"\subsection{" + line[3:].strip() + r"}")
        elif line.startswith("# "):
            latex_lines.append(r"\section{" + line[2:].strip() + r"}")
        elif line.strip():
            processed = line
            processed = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", processed)
            processed = re.sub(r"\*(.+?)\*", r"\\textit{\1}", processed)
            processed = re.sub(r"\[@([a-zA-Z0-9_-]+)\]", r"\\cite{\1}", processed)
            latex_lines.append(processed)
            latex_lines.append("")
    latex_lines.extend(["", r"\end{document}"])
    return "\n".join(latex_lines)


def default_title() -> str:
    stamp = time.strftime("%Y%m%d-%H%M")
    return "自动生成文档-" + stamp


def extract_title(text: str) -> str:
    if not text:
        return default_title()
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    for line in lines:
        line = re.sub(r"[#*_`]+", "", line or "").strip()
        if line:
            return line[:24].rstrip()
    return default_title()
