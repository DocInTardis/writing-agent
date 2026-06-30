"""Internal python-docx compatibility helpers.

Centralizes accesses to undocumented python-docx internals so that
# type: ignore annotations are needed in only one place.
"""

from __future__ import annotations

from typing import Any

from docx import Document
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph
from docx.text.run import Run


def paragraph_p(paragraph: Paragraph) -> Any:
    """Return the underlying ``<w:p>`` element."""
    return paragraph._p  # type: ignore[attr-defined]


def run_rPr(run: Run) -> Any:
    """Return (or create) the ``<w:rPr>`` element for a run."""
    return run._element.get_or_add_rPr()  # type: ignore[attr-defined]


def remove_paragraph(paragraph: Paragraph) -> None:
    """Remove *paragraph* from its parent body."""
    paragraph._element.getparent().remove(paragraph._element)  # type: ignore[attr-defined]


def section_sectPr(section: Any) -> Any:
    """Return the ``<w:sectPr>`` element for a section."""
    return section._sectPr  # type: ignore[attr-defined]


def doc_body(doc: Document) -> Any:
    """Return the document body element."""
    return doc.element.body  # type: ignore[attr-defined]


def doc_element(doc: Document) -> Any:
    """Return the document root element."""
    return doc.element  # type: ignore[attr-defined]


def style_rPr(style: Any) -> Any:
    """Return (or create) the ``<w:rPr>`` element for a style."""
    return style._element.get_or_add_rPr()  # type: ignore[attr-defined]
