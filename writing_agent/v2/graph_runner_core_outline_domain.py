"""Section weighting and outline sanitization helpers for graph runner core."""

from __future__ import annotations

import re


def _base():
    from writing_agent.v2 import graph_runner_core_domain as base
    return base


def _load_section_weights():
    return _base()._load_section_weights()


def _guess_section_weight(title: str) -> float:
    return _base()._guess_section_weight(title)


def _section_title(token: str) -> str:
    return _base()._section_title(token)


def _is_reference_section(title: str) -> bool:
    return _base()._is_reference_section(title)


def _split_section_token(token: str):
    return _base()._split_section_token(token)


def _encode_section(level: int, title: str) -> str:
    return _base()._encode_section(level, title)


def _compute_section_weights(sections: list[str]) -> dict[str, float]:
    weights = _load_section_weights()
    out: dict[str, float] = {}
    for s in sections:
        title = _section_title(s) or s
        w = weights.get(title)
        if w is None:
            w = _guess_section_weight(title)
        out[s] = float(max(0.3, min(3.0, w)))
    return out


def _classify_section_type(title: str) -> str:
    """Classify section type for target length scaling."""
    t = (title or "").strip().lower()
    if any(k in t for k in ["introduction", "background", "overview", "综述", "引言"]):
        return "intro"
    if any(k in t for k in ["method", "design", "implementation", "architecture", "analysis", "方法", "设计", "实现", "架构"]):
        return "method"
    if any(k in t for k in ["conclusion", "summary", "结论", "总结", "展望"]):
        return "conclusion"
    return "default"


def _default_plan_map(
    *,
    sections: list[str],
    base_targets: dict[str, SectionTargets],
    total_chars: int,
) -> dict[str, PlanSection]:
    return _base().graph_reference_domain.default_plan_map(
        sections=sections,
        base_targets=base_targets,
        total_chars=total_chars,
        compute_section_weights=_compute_section_weights,
        section_title=_section_title,
        is_reference_section=_is_reference_section,
        classify_section_type=_classify_section_type,
        plan_section_cls=_base().PlanSection,
    )



def _sanitize_planned_sections(sections: list[str]) -> list[str]:
    banned = {"\u76ee\u5f55", "Table of Contents", "Contents", "\u5efa\u8bae", "\u9644\u5f55"}
    out: list[str] = []
    seen: set[str] = set()
    for item in sections or []:
        title_obj = item
        if isinstance(item, dict):
            title_obj = item.get("title") or item.get("name") or ""
        title = str(title_obj or "").strip()
        if title.startswith("{") and "title" in title:
            m = re.search(r"""['"]title['"]\s*:\s*['"](.+?)['"]""", title)
            if m:
                title = m.group(1).strip()
        title = _clean_section_title(title)
        if not title:
            continue
        if title in banned:
            continue
        if title in _base()._ACK_SECTIONS:
            continue
        if title in _base()._DISALLOWED_SECTIONS:
            continue
        if title in seen:
            continue
        seen.add(title)
        out.append(title)
    # ensure references last
    refs = [t for t in out if _is_reference_section(t)]
    out = [t for t in out if not _is_reference_section(t)]
    if refs:
        out.append("\u53c2\u8003\u6587\u732e")
    else:
        out.append("\u53c2\u8003\u6587\u732e")
    return out


def _clean_section_title(title: str) -> str:
    return _base().graph_plan_domain.clean_section_title(
        title,
        strip_chapter_prefix_local=_strip_chapter_prefix_local,
    )




def _clean_outline_title(title: str) -> str:
    s = _strip_chapter_prefix_local(str(title or "")).strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
    s = re.sub(r"\s*#+\s*$", "", s).strip()
    return s

def _strip_chapter_prefix_local(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^\u7b2c\s*\d+\s*\u7ae0\s*", "", s)
    s = re.sub(r"^\d+(?:\.\d+)*\s*", "", s)
    return s.strip()


def _sanitize_section_tokens(sections: list[str], *, keep_full_titles: bool = False) -> list[str]:
    banned = {"\u76ee\u5f55", "Table of Contents", "Contents", "\u5efa\u8bae", "\u9644\u5f55"}
    out: list[str] = []
    refs: list[str] = []
    seen: set[tuple[int, str]] = set()
    for sec in sections or []:
        lvl, title = _split_section_token(sec)
        clean = _clean_outline_title(title) if keep_full_titles else _clean_section_title(title)
        if not clean:
            continue
        if clean in banned or clean in _base()._ACK_SECTIONS or clean in _base()._DISALLOWED_SECTIONS:
            continue
        key = (lvl if lvl >= 3 else 2, clean)
        if key in seen:
            continue
        seen.add(key)
        token = _encode_section(lvl, clean) if lvl >= 3 else clean
        if _is_reference_section(clean):
            refs.append(token)
        else:
            out.append(token)
    if refs:
        out.append("\u53c2\u8003\u6587\u732e")
    else:
        out.append("\u53c2\u8003\u6587\u732e")
    return out


def _sanitize_outline(outline: list[tuple[int, str]]) -> list[tuple[int, str]]:
    if not outline:
        return []
    out: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    refs = False
    numbered_re = re.compile(r"^\s*(?:\u7b2c\s*\d+\s*\u7ae0|\d+[\s.])")
    has_numbered = any(numbered_re.match(str(txt or "")) for _, txt in outline)
    for lvl, txt in outline:
        try:
            lvl_i = int(lvl)
        except Exception:
            lvl_i = 1
        lvl_i = 1 if lvl_i <= 1 else (2 if lvl_i == 2 else 3)
        clean = _clean_outline_title(txt)
        if not clean:
            continue
        if has_numbered and not numbered_re.match(str(txt or "")):
            lvl_i = 2
        if clean in _base()._DISALLOWED_SECTIONS or clean in _base()._ACK_SECTIONS:
            continue
        key = (lvl_i, clean)
        if key in seen:
            continue
        seen.add(key)
        if _is_reference_section(clean):
            refs = True
            continue
        out.append((lvl_i, clean))
    if refs:
        out.append((1, "\u53c2\u8003\u6587\u732e"))
    return out



__all__ = [name for name in globals() if not name.startswith("__")]
