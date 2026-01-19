from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class CitationStyle(str, Enum):
    APA = "APA"
    IEEE = "IEEE"
    GBT = "GB/T"


@dataclass(frozen=True)
class FormattingRequirements:
    word_count: int | None = None
    heading_levels: int = 3
    citation_style: CitationStyle = CitationStyle.GBT
    font_name: str = "Times New Roman"
    font_name_east_asia: str = "宋体"
    font_size_pt: int = 12
    line_spacing: float = 1.5


@dataclass(frozen=True)
class ReportRequest:
    topic: str
    report_type: str
    formatting: FormattingRequirements
    include_figures: bool = False
    writing_style: str = "学术"
    manual_sources_text: str = ""


@dataclass
class OutlineNode:
    title: str
    level: int
    notes: list[str] = field(default_factory=list)
    children: list["OutlineNode"] = field(default_factory=list)

    def walk(self) -> Iterable["OutlineNode"]:
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(frozen=True)
class Citation:
    key: str
    title: str
    url: str | None = None
    authors: str | None = None
    year: str | None = None
    venue: str | None = None


@dataclass
class Paragraph:
    text: str


@dataclass
class SectionDraft:
    title: str
    level: int
    paragraphs: list[Paragraph] = field(default_factory=list)


@dataclass
class DraftDocument:
    title: str
    sections: list[SectionDraft] = field(default_factory=list)


