"""Reference planning and query normalization helpers."""

from __future__ import annotations

import re
from collections.abc import Callable

_REFERENCE_QUERY_META_PATTERNS = (
    r"\u4e2d\u6587\u5b66\u672f\u8bba\u6587\u5199\u4f5c\u9700\u6c42",
    r"\u5b66\u672f\u8bba\u6587\u5199\u4f5c\u9700\u6c42",
    r"\u5b8c\u6574\u4e2d\u6587\u5b66\u672f\u8bba\u6587\u6b63\u6587",
    r"\u5b8c\u6574\u5b66\u672f\u8bba\u6587\u6b63\u6587",
    r"\u8f93\u51fa\u6b63\u6587",
    r"\u8bba\u6587\u6b63\u6587",
    r"\u8bf7\u56f4\u7ed5",
    r"\u8bf7\u751f\u6210",
    r"\u8bf7\u64b0\u5199",
    r"\u751f\u6210\u4e00\u7bc7",
    r"\u64b0\u5199\u4e00\u7bc7",
    r"\[\[\s*(?:figure|table)\s*:\s*\{.*?\}\s*\]\]",
    r"\[\[\s*(?:figure|table)\s*:[^\]]+\]\]",
    r"<[^>]+>",
    r"[\u300a\u300b\"\u201c\u201d\u2018\u2019]",
)

_REFERENCE_QUERY_STOPWORDS = {
    "\u4e2d\u6587",
    "\u5b66\u672f",
    "\u8bba\u6587",
    "\u5b66\u672f\u8bba\u6587",
    "\u6b63\u6587",
    "\u5199\u4f5c\u9700\u6c42",
    "\u8981\u6c42",
    "\u8f93\u51fa",
    "\u5b8c\u6574",
    "\u751f\u6210",
    "\u64b0\u5199",
    "\u5199",
    "\u4e00\u7bc7",
    "\u5173\u4e8e",
    "\u56f4\u7ed5",
    "\u9898\u76ee",
    "\u6807\u9898",
    "\u7ae0\u8282",
    "\u6bb5\u843d",
    "\u56fe",
    "\u56fe\u8868",
    "\u56fe\u7247",
    "\u63d2\u56fe",
    "\u56fe\u793a",
    "\u6d41\u7a0b\u56fe",
    "\u7ed3\u6784\u56fe",
    "\u8868",
    "\u8868\u683c",
    "\u8bf4\u660e",
    "\u5b57\u6bb5",
    "\u6a21\u5f0f",
    "\u6807\u8bb0",
    "\u6e32\u67d3",
    "\u5bfc\u51fa",
    "academic",
    "paper",
    "papers",
    "report",
    "reports",
    "article",
    "articles",
    "thesis",
    "essay",
    "write",
    "writing",
    "generate",
    "generated",
    "draft",
    "final",
    "full",
    "complete",
    "chinese",
    "english",
    "topic",
    "title",
    "section",
    "sections",
    "paragraph",
    "paragraphs",
    "instruction",
    "instructions",
    "requirement",
    "requirements",
    "outline",
    "figure",
    "figures",
    "caption",
    "captions",
    "kind",
    "data",
    "json",
    "type",
    "types",
    "schema",
    "marker",
    "markers",
    "table",
    "tables",
    "block",
    "blocks",
    "markdown",
    "docx",
    "xml",
    "svg",
    "png",
    "mermaid",
    "prompt",
    "prompts",
    "render",
    "rendered",
    "renderable",
    "asset",
    "assets",
    "inline",
    "about",
}


def _reference_query_tokens(query: str) -> list[str]:
    text = str(query or "").strip()
    if not text:
        return []
    quoted = re.search(r"\u300a([^\u300b]+)\u300b", text)
    if quoted:
        text = quoted.group(1).strip()
    for pattern in _REFERENCE_QUERY_META_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(
        r"\b(?:figure|figures|caption|captions|kind|data|json|type|types|schema|marker|markers|table|tables|block|blocks|markdown|docx|xml|svg|png|mermaid|prompt|prompts|render(?:ed|able)?|asset|assets|inline)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"[\[\]\{\}\(\)<>|=:_/#`]+", " ", text)
    text = re.sub(r"[\s,\uFF0C\u3001;\uFF1B:\uFF1A\u3002\uFF01\uFF1F!?\n\r\t]+", " ", text).strip()
    if not text:
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    for token in _topic_tokens(text):
        if token in _REFERENCE_QUERY_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def normalize_reference_query(query: str) -> str:
    return " ".join(_reference_query_tokens(query)).strip()

def _default_key_points_for_title(title: str, *, section_type: str, is_reference: bool) -> list[str]:
    if is_reference:
        return [
            "\u6765\u6e90\u53ef\u6838\u9a8c\u6027\u4e0e\u6761\u76ee\u5b8c\u6574\u6027",
            "\u5f15\u7528\u98ce\u683c\u4e00\u81f4\u6027\u4e0e\u7f16\u53f7\u89c4\u8303",
        ]
    t = str(title or "")
    if section_type == "intro":
        return [
            "\u7814\u7a76\u80cc\u666f\u4e0e\u95ee\u9898\u754c\u5b9a",
            "\u7814\u7a76\u8d21\u732e\u4e0e\u6587\u7ae0\u7ed3\u6784",
        ]
    if section_type == "method":
        return [
            "\u6280\u672f\u8def\u7ebf\u4e0e\u5173\u952e\u6b65\u9aa4",
            "\u53c2\u6570\u8bbe\u7f6e\u4e0e\u590d\u73b0\u6761\u4ef6",
        ]
    if section_type == "conclusion":
        return [
            "\u6838\u5fc3\u7ed3\u8bba\u4e0e\u5b9e\u8df5\u542f\u793a",
            "\u5c40\u9650\u6027\u4e0e\u540e\u7eed\u7814\u7a76\u65b9\u5411",
        ]
    if re.search(r"(\u5b9e\u9a8c|\u7ed3\u679c|\u8bc4\u4f30|ablation|benchmark)", t, flags=re.IGNORECASE):
        return [
            "\u5b9e\u9a8c\u8bbe\u8ba1\u4e0e\u8bc4\u4ef7\u6307\u6807",
            "\u7ed3\u679c\u5206\u6790\u4e0e\u8bef\u5dee\u8ba8\u8bba",
        ]
    return [
        "\u4e3b\u9898\u6982\u5ff5\u4e0e\u7814\u7a76\u8fb9\u754c",
        "\u8bba\u8bc1\u8def\u5f84\u4e0e\u8bc1\u636e\u652f\u6491",
    ]

def _default_evidence_queries_for_title(title: str, *, is_reference: bool) -> list[str]:
    if is_reference:
        return []
    t = str(title or "").strip()
    if not t:
        return ["\u4e3b\u9898 \u7814\u7a76\u7efc\u8ff0", "\u4e3b\u9898 \u5b9e\u8bc1\u7814\u7a76"]
    return [f"{t} \u7814\u7a76\u8fdb\u5c55", f"{t} \u5b9e\u8bc1\u8bc4\u4f30"]

def visual_value_score_for_section(title: str, *, is_reference: bool = False, section_type: str = "") -> float:
    if is_reference:
        return 0.0
    t = str(title or "").strip()
    if not t:
        return 0.0
    probe = t.lower()
    score = 0.18
    if section_type == "intro":
        score = max(score, 0.12)
    if section_type == "conclusion":
        score = max(score, 0.08)
    if re.search(r"(架构|框架|体系|模块|平台|系统总体|architecture|framework|module|topology)", t, flags=re.IGNORECASE):
        score = max(score, 0.92)
    if re.search(r"(流程|机制|路径|链路|方法|实现|过程|工作流|pipeline|workflow|process|method|implementation)", t, flags=re.IGNORECASE):
        score = max(score, 0.84)
    if re.search(r"(时序|阶段|演化|sequence|timeline|phase)", t, flags=re.IGNORECASE):
        score = max(score, 0.78)
    if re.search(r"(关系|交互|协同|角色|network|interaction|relation)", t, flags=re.IGNORECASE):
        score = max(score, 0.72)
    if re.search(r"(实验|结果|评估|数据|analysis|result|benchmark)", t, flags=re.IGNORECASE):
        score = max(score, 0.46)
    if re.search(r"(摘要|关键词|引言|讨论|结论|abstract|keywords|introduction|discussion|conclusion)", probe, flags=re.IGNORECASE):
        score = min(score, 0.4 if score > 0.4 else score)
    return max(0.0, min(1.0, round(score, 2)))


def _default_figure_suggestions_for_title(title: str, *, is_reference: bool) -> list[dict]:
    if is_reference:
        return []
    t = str(title or "").strip()
    if not t:
        return []
    if re.search(r"(\u67b6\u6784|\u6846\u67b6|\u4f53\u7cfb|\u6a21\u5757|\u5e73\u53f0|\u7cfb\u7edf\u603b\u4f53|architecture|framework|module|topology)", t, flags=re.IGNORECASE):
        return [{"type": "architecture", "caption": f"{t}\u67b6\u6784\u56fe"}]
    if re.search(r"(\u6d41\u7a0b|\u673a\u5236|\u8def\u5f84|\u94fe\u8def|\u65b9\u6cd5|\u5b9e\u73b0|\u8fc7\u7a0b|\u5de5\u4f5c\u6d41|pipeline|workflow|process|method|implementation)", t, flags=re.IGNORECASE):
        return [{"type": "flow", "caption": f"{t}\u6d41\u7a0b\u56fe"}]
    if re.search(r"(\u65f6\u5e8f|\u9636\u6bb5|\u6f14\u5316|sequence|timeline|phase)", t, flags=re.IGNORECASE):
        return [{"type": "timeline", "caption": f"{t}\u793a\u610f\u56fe"}]
    if re.search(r"(\u5173\u7cfb|\u4ea4\u4e92|\u534f\u540c|\u89d2\u8272|network|interaction|relation)", t, flags=re.IGNORECASE):
        return [{"type": "sequence", "caption": f"{t}\u5173\u7cfb\u56fe"}]
    return []

def default_plan_map(
    *,
    sections: list[str],
    base_targets: dict,
    total_chars: int,
    compute_section_weights: Callable[[list[str]], dict[str, float]],
    section_title: Callable[[str], str],
    is_reference_section: Callable[[str], bool],
    classify_section_type: Callable[[str], str],
    plan_section_cls,
) -> dict:
    weights = compute_section_weights(sections)
    denom = sum(weights.values()) or 1.0
    plan: dict = {}
    for sec in sections:
        title = section_title(sec) or sec
        share = int(round(float(total_chars) * (weights.get(sec, 1.0) / denom)))
        target = max(200, share)
        if is_reference_section(title):
            target = max(220, min(1200, target))
        section_type = classify_section_type(title)
        if section_type == "intro":
            min_chars = max(380, int(round(target * 0.95)))
            max_chars = max(min_chars + 320, int(round(target * 1.35)))
        elif section_type == "method":
            min_chars = max(760, int(round(target * 1.15)))
            max_chars = max(min_chars + 520, int(round(target * 1.65)))
        elif section_type == "conclusion":
            min_chars = max(460, int(round(target * 0.95)))
            max_chars = max(min_chars + 360, int(round(target * 1.35)))
        else:
            min_chars = max(520, int(round(target * 1.05)))
            max_chars = max(min_chars + 420, int(round(target * 1.45)))
        target_row = base_targets.get(sec)
        min_tables = int(target_row.min_tables) if target_row else 0
        min_figures = int(target_row.min_figures) if target_row else 0
        is_ref = is_reference_section(title)
        key_points = _default_key_points_for_title(title, section_type=section_type, is_reference=is_ref)
        evidence_queries = _default_evidence_queries_for_title(title, is_reference=is_ref)
        figures = _default_figure_suggestions_for_title(title, is_reference=is_ref)
        tables: list[dict] = []
        if re.search(r"(\u5b9e\u9a8c|\u7ed3\u679c|\u8bc4\u4f30|\u6570\u636e|analysis|result|benchmark)", title, flags=re.IGNORECASE):
            tables = [{"caption": f"{title}\u7ed3\u679c\u5bf9\u6bd4", "columns": ["\u6307\u6807", "\u6570\u503c"]}]
            min_tables = max(min_tables, 1)
        if is_ref:
            figures = []
            tables = []
            min_tables = 0
            min_figures = 0
        plan[sec] = plan_section_cls(
            title=title,
            target_chars=target,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
            key_points=key_points,
            figures=figures,
            tables=tables,
            evidence_queries=evidence_queries,
        )
    return plan


def extract_year(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    match = re.search(r"(19|20)\d{2}", value)
    return match.group(0) if match else ""


def format_authors(authors: list[str]) -> str:
    cleaned = [a.strip() for a in (authors or []) if str(a).strip()]
    if not cleaned:
        return ""
    if len(cleaned) <= 3:
        return ", ".join(cleaned)
    return f"{', '.join(cleaned[:3])} et al."


def _topic_tokens(text: str) -> list[str]:
    src = str(text or "").strip().lower()
    if not src:
        return []
    chunks = re.findall(r"[一-鿿]{2,}|[a-z][a-z0-9\-]{2,}", src)
    out: list[str] = []
    seen: set[str] = set()
    for token in chunks:
        t = token.strip().lower()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out
