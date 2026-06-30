"""Structure-aware section parsing and deterministic evidence extraction."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass

from writing_agent.v2.rag.pdf_text import PdfPageText
from writing_agent.v2.rag.structured_records import EvidenceRecord, SectionRecord, stable_id

PARSER_VERSION = "section-parser-1"
COMPRESSOR_VERSION = "deterministic-compressor-1"

_HEADING_RE = re.compile(
    r"^\s*(?:"
    r"#{1,6}\s+.+"
    r"|(?:第[一二三四五六七八九十百0-9]+[章节篇部])\s*.+"
    r"|(?:\d+(?:\.\d+){0,3})[.)、]?\s+[^\d].{0,100}"
    r"|(?:abstract|introduction|background|related work|literature review|method(?:ology)?|"
    r"materials and methods|results?|discussion|limitations?|conclusions?|references|"
    r"摘要|关键词|引言|研究背景|相关工作|文献综述|研究方法|实验方法|实验结果|"
    r"结果与讨论|讨论|局限性|结论|参考文献)"
    r")\s*$",
    re.IGNORECASE,
)
_NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,3})[.)、]?\s+")
_MARKDOWN_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+")
_SENTENCE_RE = re.compile(r"[^。！？!?\n]+[。！？!?]?")
_LIMITATION_RE = re.compile(
    r"\b(?:however|although|limitation|limited|may not|cannot|future work)\b|"
    r"(?:但是|然而|尽管|局限|限制|不足|尚不能|未来研究)",
    re.IGNORECASE,
)
_METHOD_RE = re.compile(
    r"\b(?:method|model|algorithm|dataset|sample|experiment|survey|regression)\b|"
    r"(?:方法|模型|算法|数据集|样本|实验|调查|回归)",
    re.IGNORECASE,
)
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were",
    "的", "了", "和", "与", "在", "是", "为", "对", "中", "及", "等", "本文",
}


@dataclass(frozen=True)
class _Line:
    text: str
    page: int | None
    start: int
    end: int


@dataclass(frozen=True)
class ParsedSection:
    title: str
    level: int
    order: int
    parent_order: int | None
    text: str
    page_start: int | None
    page_end: int | None
    source_start: int
    source_end: int


def parse_document_sections(
    *,
    text: str = "",
    pages: list[PdfPageText] | None = None,
    max_section_chars: int = 6000,
) -> list[ParsedSection]:
    lines = _build_lines(text=text, pages=pages or [])
    if not lines:
        return []

    heading_indices = [index for index, line in enumerate(lines) if _is_heading(line.text)]
    if not heading_indices:
        body = "\n".join(line.text for line in lines).strip()
        return _split_long_section(
            ParsedSection(
                title="Document",
                level=1,
                order=0,
                parent_order=None,
                text=body,
                page_start=lines[0].page,
                page_end=lines[-1].page,
                source_start=lines[0].start,
                source_end=lines[-1].end,
            ),
            max_section_chars=max_section_chars,
        )

    sections: list[ParsedSection] = []
    stack: list[tuple[int, int]] = []
    if heading_indices[0] > 0:
        prefix_lines = lines[: heading_indices[0]]
        prefix = "\n".join(line.text for line in prefix_lines).strip()
        if prefix:
            sections.append(
                ParsedSection(
                    title="Preamble",
                    level=1,
                    order=0,
                    parent_order=None,
                    text=prefix,
                    page_start=prefix_lines[0].page,
                    page_end=prefix_lines[-1].page,
                    source_start=prefix_lines[0].start,
                    source_end=prefix_lines[-1].end,
                )
            )

    for position, heading_index in enumerate(heading_indices):
        heading = lines[heading_index]
        next_index = heading_indices[position + 1] if position + 1 < len(heading_indices) else len(lines)
        body_lines = lines[heading_index + 1 : next_index]
        body = "\n".join(line.text for line in body_lines).strip()
        level = _heading_level(heading.text)
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_order = stack[-1][1] if stack else None
        order = len(sections)
        section = ParsedSection(
            title=_clean_heading(heading.text),
            level=level,
            order=order,
            parent_order=parent_order,
            text=body,
            page_start=(body_lines[0].page if body_lines else heading.page),
            page_end=(body_lines[-1].page if body_lines else heading.page),
            source_start=(body_lines[0].start if body_lines else heading.start),
            source_end=(body_lines[-1].end if body_lines else heading.end),
        )
        split = _split_long_section(section, max_section_chars=max_section_chars)
        sections.extend(split)
        stack.append((level, order))

    return [
        ParsedSection(
            title=row.title,
            level=row.level,
            order=index,
            parent_order=row.parent_order,
            text=row.text,
            page_start=row.page_start,
            page_end=row.page_end,
            source_start=row.source_start,
            source_end=row.source_end,
        )
        for index, row in enumerate(sections)
        if row.title or row.text
    ]


def build_structured_records(
    *,
    paper_id: str,
    sections: list[ParsedSection],
    keep_raw_chars: int = 1200,
    max_evidence_per_section: int = 6,
) -> tuple[list[SectionRecord], list[EvidenceRecord]]:
    section_ids = {
        row.order: stable_id("sec", paper_id, row.order, row.title, row.source_start)
        for row in sections
    }
    section_records: list[SectionRecord] = []
    evidence_records: list[EvidenceRecord] = []
    for row in sections:
        summary = _summarize(row.text)
        sentences = _sentences(row.text)
        claims = _select_claims(sentences)
        key_facts = [sentence for sentence in sentences if re.search(r"\d", sentence)][:4]
        limitations = [sentence for sentence in sentences if _LIMITATION_RE.search(sentence)][:3]
        methods = [sentence for sentence in sentences if _METHOD_RE.search(sentence)][:2]
        keywords = _keywords(f"{row.title}\n{row.text}")
        content_hash = hashlib.sha256(row.text.encode("utf-8")).hexdigest()
        section_id = section_ids[row.order]
        raw_text = row.text[: max(0, int(keep_raw_chars))].strip()
        section_records.append(
            SectionRecord(
                section_id=section_id,
                paper_id=paper_id,
                parent_section_id=section_ids.get(row.parent_order, "") if row.parent_order is not None else "",
                title=row.title,
                level=row.level,
                order=row.order,
                page_start=row.page_start,
                page_end=row.page_end,
                source_start=row.source_start,
                source_end=row.source_end,
                raw_text=raw_text,
                summary=summary,
                purpose=sentences[0] if sentences else "",
                method=methods[0] if methods else "",
                claims=claims,
                key_facts=key_facts,
                limitations=limitations,
                keywords=keywords,
                content_hash=content_hash,
                parser_version=PARSER_VERSION,
                compressor_version=COMPRESSOR_VERSION,
            )
        )
        evidence_records.extend(
            _extract_evidence(
                paper_id=paper_id,
                section_id=section_id,
                section=row,
                sentences=sentences,
                keywords=keywords,
                limit=max_evidence_per_section,
            )
        )
    return section_records, evidence_records


def _build_lines(*, text: str, pages: list[PdfPageText]) -> list[_Line]:
    out: list[_Line] = []
    offset = 0
    page_items = pages or ([PdfPageText(page=1, text=text)] if text.strip() else [])
    for page in page_items:
        for raw in page.text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
            value = raw.strip()
            start = offset + (raw.find(value) if value else 0)
            offset += len(raw) + 1
            if value:
                out.append(_Line(text=value, page=page.page, start=start, end=offset - 1))
        offset += 1
    return out


def _is_heading(text: str) -> bool:
    value = text.strip()
    if not value or len(value) > 120:
        return False
    if _HEADING_RE.match(value):
        return True
    if len(value) <= 45 and not re.search(r"[。！？!?;；]$", value):
        words = value.split()
        if 1 <= len(words) <= 8 and value.isupper() and any(ch.isalpha() for ch in value):
            return True
    return False


def _heading_level(text: str) -> int:
    markdown = _MARKDOWN_HEADING_RE.match(text)
    if markdown:
        return min(6, len(markdown.group(1)))
    numbered = _NUMBERED_HEADING_RE.match(text)
    if numbered:
        return min(6, numbered.group(1).count(".") + 1)
    if re.match(r"^\s*第.+章", text):
        return 1
    if re.match(r"^\s*第.+节", text):
        return 2
    return 1


def _clean_heading(text: str) -> str:
    return re.sub(r"^\s*#{1,6}\s+", "", text).strip()


def _split_long_section(section: ParsedSection, *, max_section_chars: int) -> list[ParsedSection]:
    limit = max(800, int(max_section_chars))
    if len(section.text) <= limit:
        return [section]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+|\n", section.text) if part.strip()]
    groups: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        if buffer and len(buffer) + len(paragraph) + 2 > limit:
            groups.append(buffer)
            buffer = paragraph
        else:
            buffer = f"{buffer}\n\n{paragraph}".strip()
    if buffer:
        groups.append(buffer)
    if len(groups) <= 1:
        groups = [section.text[index : index + limit] for index in range(0, len(section.text), limit)]
    return [
        ParsedSection(
            title=f"{section.title} (part {index})",
            level=section.level,
            order=section.order + index - 1,
            parent_order=section.parent_order,
            text=value,
            page_start=section.page_start,
            page_end=section.page_end,
            source_start=section.source_start,
            source_end=section.source_end,
        )
        for index, value in enumerate(groups, start=1)
    ]


def _sentences(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in _SENTENCE_RE.finditer(text.replace("\r", "\n"))
        if len(match.group(0).strip()) >= 15
    ]


def _summarize(text: str, *, max_chars: int = 700) -> str:
    sentences = _sentences(text)
    if not sentences:
        return text[:max_chars].strip()
    selected = sentences[:3]
    if len(sentences) > 3:
        selected.append(sentences[-1])
    summary = " ".join(dict.fromkeys(selected))
    return summary[:max_chars].strip()


def _select_claims(sentences: list[str]) -> list[str]:
    preferred = [
        sentence
        for sentence in sentences
        if re.search(
            r"\b(?:show|find|indicate|demonstrate|improve|reduce|increase|suggest|conclude)\w*\b|"
            r"(?:表明|发现|显示|证明|提高|降低|增加|结果|结论)",
            sentence,
            re.IGNORECASE,
        )
    ]
    return list(dict.fromkeys((preferred or sentences)[:4]))


def _keywords(text: str, *, limit: int = 12) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,8}", text.lower())
    counts = Counter(token for token in tokens if token not in _STOPWORDS)
    return [token for token, _count in counts.most_common(limit)]


def _extract_evidence(
    *,
    paper_id: str,
    section_id: str,
    section: ParsedSection,
    sentences: list[str],
    keywords: list[str],
    limit: int,
) -> list[EvidenceRecord]:
    candidates = _select_claims(sentences)
    fact_candidates = [sentence for sentence in sentences if re.search(r"\d", sentence)]
    structural_candidates = [
        sentence
        for sentence in sentences
        if re.match(r"^\s*(?:table|figure|fig\.?|表|图)\s*[A-Za-z0-9一二三四五六七八九十.-]*", sentence, re.IGNORECASE)
        or re.search(r"(?:=|≈|≤|≥|∑|√|[A-Za-z]\s*=\s*[-+0-9A-Za-z])", sentence)
    ]
    candidates = list(
        dict.fromkeys(structural_candidates + fact_candidates + candidates + sentences[:2])
    )[: max(1, int(limit))]
    out: list[EvidenceRecord] = []
    cursor = 0
    for index, sentence in enumerate(candidates):
        local_start = section.text.find(sentence, cursor)
        if local_start < 0:
            local_start = section.text.find(sentence)
        if local_start < 0:
            continue
        cursor = local_start + len(sentence)
        source_start = section.source_start + local_start
        source_end = source_start + len(sentence)
        evidence_type = _evidence_type(sentence)
        digest = hashlib.sha256(sentence.encode("utf-8")).hexdigest()
        out.append(
            EvidenceRecord(
                evidence_id=stable_id("ev", paper_id, section_id, index, digest),
                paper_id=paper_id,
                section_id=section_id,
                claim=sentence,
                evidence_text=sentence,
                evidence_type=evidence_type,
                page=section.page_start,
                paragraph=None,
                source_start=source_start,
                source_end=source_end,
                confidence=0.72 if evidence_type in {"data", "result", "method"} else 0.62,
                keywords=keywords[:8],
                content_hash=digest,
            )
        )
    return out


def _evidence_type(sentence: str) -> str:
    if re.match(r"^\s*(?:table|表)\s*[A-Za-z0-9一二三四五六七八九十.-]*", sentence, re.IGNORECASE):
        return "table"
    if re.match(r"^\s*(?:figure|fig\.?|图)\s*[A-Za-z0-9一二三四五六七八九十.-]*", sentence, re.IGNORECASE):
        return "figure"
    if re.search(r"(?:=|≈|≤|≥|∑|√|[A-Za-z]\s*=\s*[-+0-9A-Za-z])", sentence):
        return "formula"
    if re.search(r"\d", sentence):
        return "data"
    if _LIMITATION_RE.search(sentence):
        return "limitation"
    if _METHOD_RE.search(sentence):
        return "method"
    if re.search(r"\b(?:result|show|find|conclude)\w*\b|(?:结果|表明|发现|结论)", sentence, re.IGNORECASE):
        return "result"
    return "claim"
