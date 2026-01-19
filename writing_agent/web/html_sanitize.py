from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Final


_ALLOWED_TAGS: Final[set[str]] = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "br",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "ul",
    "ol",
    "li",
    "a",
    "span",
    "div",
    # Safe SVG subset for diagrams (no scripts, no external refs).
    "svg",
    "g",
    "rect",
    "circle",
    "line",
    "path",
    "text",
    "defs",
    "marker",
    "table",
    "tbody",
    "thead",
    "tr",
    "td",
    "th",
    "figure",
    "figcaption",
    "img",
}

_ALLOWED_ATTRS: Final[dict[str, set[str]]] = {
    "a": {"href"},
    "span": {"style", "class"},
    "div": {"style", "class"},
    "p": {"class", "style"},
    "li": {"style"},
    "h1": {"style"},
    "h2": {"style"},
    "h3": {"style"},
    "h4": {"style"},
    "h5": {"style"},
    "h6": {"style"},
    "svg": {"xmlns", "width", "height", "viewBox", "viewbox", "role", "aria-label"},
    "g": {"transform"},
    "rect": {"x", "y", "width", "height", "rx", "ry", "fill", "stroke", "stroke-width"},
    "circle": {"cx", "cy", "r", "fill", "stroke", "stroke-width"},
    "line": {"x1", "y1", "x2", "y2", "stroke", "stroke-width", "marker-end"},
    "path": {"d", "fill", "stroke", "stroke-width"},
    "text": {"x", "y", "fill", "font-size", "font-family", "text-anchor"},
    "marker": {"id", "markerwidth", "markerheight", "refx", "refy", "orient", "markerunits"},
    "defs": set(),
    "table": {"class"},
    "tbody": set(),
    "thead": set(),
    "tr": set(),
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "figure": {"class"},
    "figcaption": {"class"},
    "img": {"src", "alt", "width", "height"},
}

_ALLOWED_STYLE_PREFIXES: Final[tuple[str, ...]] = (
    "font-weight",
    "font-style",
    "font-size",
    "font-family",
    "color",
    "background-color",
    "line-height",
    "text-decoration",
    "text-align",
)


def sanitize_html(raw_html: str) -> str:
    parser = _Sanitizer()
    parser.feed(raw_html or "")
    parser.close()
    return "".join(parser.out)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in _ALLOWED_TAGS:
            self._stack.append("")
            return

        cleaned_attrs: list[str] = []
        allowed = _ALLOWED_ATTRS.get(tag, set())
        for k, v in attrs:
            k = (k or "").lower()
            if k not in allowed:
                continue
            if v is None:
                continue
            if k == "href":
                href = v.strip()
                if href.lower().startswith(("javascript:", "data:")):
                    continue
                cleaned_attrs.append(f' href="{html.escape(href, quote=True)}"')
            elif tag == "img" and k == "src":
                src = v.strip()
                # Only allow local served files
                if not src.startswith("/files/"):
                    continue
                cleaned_attrs.append(f' src="{html.escape(src, quote=True)}"')
            elif k == "style":
                style = _filter_style(v)
                if style:
                    cleaned_attrs.append(f' style="{html.escape(style, quote=True)}"')
            elif k in {"marker-end"}:
                # only allow local marker reference like url(#arrow)
                val = v.strip()
                if val.startswith("url(#") and val.endswith(")"):
                    cleaned_attrs.append(f' {k}="{html.escape(val, quote=True)}"')
            elif k == "class":
                cls = _filter_class(v)
                if cls:
                    cleaned_attrs.append(f' class="{html.escape(cls, quote=True)}"')
            else:
                cleaned_attrs.append(f' {k}="{html.escape(v.strip(), quote=True)}"')

        self.out.append(f"<{tag}{''.join(cleaned_attrs)}>")
        self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self._stack:
            return
        opened = self._stack.pop()
        if opened != tag:
            return
        if tag in _ALLOWED_TAGS and tag not in {"br"}:
            self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not data:
            return
        self.out.append(html.escape(data))

    def handle_entityref(self, name: str) -> None:
        self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.out.append(f"&#{name};")


def _filter_style(style: str) -> str:
    items = []
    for chunk in style.split(";"):
        if ":" not in chunk:
            continue
        k, v = chunk.split(":", 1)
        k = k.strip().lower()
        v = v.strip()
        if not k or not v:
            continue
        if any(k.startswith(p) for p in _ALLOWED_STYLE_PREFIXES):
            if k == "font-size":
                if not _is_safe_font_size(v):
                    continue
            if k in {"color", "background-color"}:
                if not _is_safe_color(v):
                    continue
            if k == "line-height":
                if not _is_safe_line_height(v):
                    continue
            if k == "text-align":
                if not _is_safe_text_align(v):
                    continue
            if k == "font-family":
                fam = _filter_font_family(v)
                if not fam:
                    continue
                v = fam
            items.append(f"{k}: {v}")
    return "; ".join(items)


def _is_safe_font_size(v: str) -> bool:
    # Allow only numeric pt/px to keep it deterministic.
    val = (v or "").strip().lower()
    if val.endswith("pt"):
        num = val[:-2].strip()
        return _is_num_in_range(num, 6, 72)
    if val.endswith("px"):
        num = val[:-2].strip()
        return _is_num_in_range(num, 8, 96)
    return False


def _is_num_in_range(num: str, lo: float, hi: float) -> bool:
    try:
        f = float(num)
        return lo <= f <= hi
    except Exception:
        return False


def _is_safe_color(v: str) -> bool:
    s = (v or "").strip().lower()
    if re.match(r"^#[0-9a-f]{6}$", s):
        return True
    return False


def _is_safe_line_height(v: str) -> bool:
    s = (v or "").strip().lower()
    # allow unitless numeric between 0.8 and 3
    try:
        f = float(s)
        return 0.8 <= f <= 3.0
    except Exception:
        return False


def _filter_font_family(v: str) -> str:
    raw = (v or "").strip()
    if not raw:
        return ""
    # Allow a short comma-separated list, keeping only safe tokens.
    out = []
    for part in raw.split(","):
        p = part.strip().strip("\"'")[:40]
        if not p:
            continue
        if any(ch in p for ch in ["<", ">", ";", "(", ")", "{", "}"]):
            continue
        out.append(p)
    return ", ".join(out)[:120]


def _is_safe_text_align(v: str) -> bool:
    s = (v or "").strip().lower()
    return s in {"left", "right", "center", "justify"}


def _filter_class(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    # Keep simple safe class list: letters/numbers/_- and spaces.
    cleaned = []
    for part in raw.split():
        p = "".join(ch for ch in part if ch.isalnum() or ch in {"_", "-"})
        if p:
            cleaned.append(p)
    out = " ".join(cleaned)[:80]
    return out
