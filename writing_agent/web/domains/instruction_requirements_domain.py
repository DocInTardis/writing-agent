"""Instruction Requirements Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from typing import Any, Callable


def _extract_min_count(
    instruction: str,
    *,
    keyword_re: str,
    unit_re: str,
    default: int = 0,
    cap: int = 200,
) -> int:
    s = str(instruction or "")
    found: list[int] = []
    patterns = [
        rf"(?:{keyword_re}).{{0,40}}?(?:至少|不少于)\s*(\d{{1,3}})\s*(?:{unit_re})",
        rf"(?:至少|不少于)\s*(\d{{1,3}})\s*(?:{unit_re}).{{0,40}}?(?:{keyword_re})",
        rf"(?:{keyword_re}).{{0,20}}?(\d{{1,3}})\s*(?:{unit_re})",
    ]
    for pat in patterns:
        m = re.search(pat, s, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            n = int(m.group(1))
        except Exception:
            continue
        if n <= 0:
            continue
        found.append(min(cap, n))
    if found:
        return max(found)
    return max(0, int(default))


def _extract_exact_disclaimer(instruction: str) -> str:
    s = str(instruction or "").strip()
    if not s:
        return ""
    patterns = [
        r"Use this exact disclaimer:\s*([^\n]+)",
        r"exact disclaimer\s*[:：]\s*([^\n]+)",
        r"免责声明\s*[:：]\s*([^\n]+)",
    ]
    for pat in patterns:
        m = re.search(pat, s, flags=re.IGNORECASE)
        if not m:
            continue
        phrase = str(m.group(1) or "").strip().strip("。；;")
        if phrase and len(phrase) >= 6:
            return phrase
    return ""


def _count_term_rows(section_text: str) -> int:
    count = 0
    for raw in (section_text or "").splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        if not re.match(r"^\|\s*[^|\n]+\s*\|\s*[^|\n]+\s*\|\s*[^|\n]+\s*\|$", line):
            continue
        if re.match(r"^\|\s*:?-{2,}\s*\|\s*:?-{2,}\s*\|\s*:?-{2,}\s*\|$", line):
            continue
        if "中文术语" in line and "英文术语" in line:
            continue
        count += 1
    return count


def _ensure_required_h2_sections(
    text: str,
    instruction: str,
    *,
    extract_required_sections_from_instruction: Callable[[str], list[str]],
    extract_sections: Callable[..., list[Any]],
    normalize_heading_text: Callable[[str], str],
    append_new_h2_section: Callable[[str, str, list[str]], str],
) -> str:
    required = extract_required_sections_from_instruction(instruction)
    if not required:
        return text
    existing = extract_sections(text, prefer_levels=(2,))
    existing_norm = {normalize_heading_text(getattr(sec, "title", "")) for sec in existing}
    out = text
    for title in required:
        if normalize_heading_text(title) in existing_norm:
            continue
        out = append_new_h2_section(out, title, [f"- TODO: add executable content for '{title}'."])
        existing_norm.add(normalize_heading_text(title))
    return out


def _ensure_disclaimer(
    text: str,
    instruction: str,
    *,
    append_new_h2_section: Callable[[str, str, list[str]], str],
    insert_lines_into_section: Callable[[str, str, list[str]], str],
) -> str:
    body = str(text or "")
    inst = str(instruction or "")
    if not re.search(r"(免责声明|disclaimer)", inst, flags=re.IGNORECASE):
        return body
    exact = _extract_exact_disclaimer(inst)
    default_line = "本文仅供一般信息参考，不构成医疗、法律或投资建议。"
    phrase = exact or default_line
    if phrase in body and re.search(r"(?m)^##\s*免责声明\s*$", body):
        return body
    if re.search(r"(?m)^##\s*免责声明\s*$", body):
        if phrase in body:
            return body
        return insert_lines_into_section(body, "免责声明", [phrase])
    return append_new_h2_section(body, "免责声明", [phrase])


def _ensure_terminology_mapping(
    text: str,
    instruction: str,
    *,
    extract_sections: Callable[..., list[Any]],
    find_section: Callable[[list[Any], str], Any | None],
    split_lines: Callable[[str], list[str]],
    insert_lines_into_section: Callable[[str, str, list[str]], str],
) -> str:
    inst = str(instruction or "")
    if not re.search(r"(术语映射表|术语表|terminology\s+mapping)", inst, flags=re.IGNORECASE):
        return text
    min_rows = 0
    m = re.search(
        r"(?:术语映射表|术语表|terminology\s+mapping)[^。；;\n]{0,160}?(?:至少|不少于)\s*(\d{1,3})\s*(?:项|条|行|rows?)",
        inst,
        flags=re.IGNORECASE,
    )
    if m:
        try:
            min_rows = int(m.group(1))
        except Exception:
            min_rows = 0
    if min_rows <= 0:
        min_rows = _extract_min_count(
            inst,
            keyword_re=r"(术语映射表|术语表|terminology\s+mapping)",
            unit_re=r"(项|条|行|rows?)",
            default=10,
            cap=50,
        )
    min_rows = max(1, min_rows)
    sec_candidates = ["术语映射表", "术语表", "Terminology Mapping"]
    sec_title = "术语映射表"
    sec_text = ""
    sections = extract_sections(text, prefer_levels=(2, 3))
    found = None
    for cand in sec_candidates:
        found = find_section(sections, cand)
        if found is not None:
            sec_title = cand
            break
    if found is not None:
        lines = split_lines(text)
        sec_text = "\n".join(lines[getattr(found, "start", 0) : getattr(found, "end", 0)])
    row_count = _count_term_rows(sec_text)
    if row_count >= min_rows:
        return text
    extra: list[str] = []
    if row_count == 0:
        extra.extend(
            [
                "| 中文术语 | 英文术语 | 业务定义 |",
                "| :-- | :-- | :-- |",
            ]
        )
    for i in range(row_count + 1, min_rows + 1):
        extra.append(f"| 术语{i} | Term-{i} | 业务定义待补充 |")
    return insert_lines_into_section(text, sec_title, extra)


def _ensure_weekly_plan(
    text: str,
    instruction: str,
    *,
    extract_sections: Callable[..., list[Any]],
    find_section: Callable[[list[Any], str], Any | None],
    split_lines: Callable[[str], list[str]],
    insert_lines_into_section: Callable[[str, str, list[str]], str],
) -> str:
    inst = str(instruction or "")
    if not re.search(r"(执行版清单|执行清单|按周|每周)", inst):
        return text
    min_weeks = _extract_min_count(inst, keyword_re=r"(周|执行版清单|执行清单)", unit_re=r"(周)", default=0, cap=52)
    if min_weeks <= 0:
        return text
    section_title = "执行版清单"
    sections = extract_sections(text, prefer_levels=(2, 3))
    sec = find_section(sections, section_title)
    sec_text = ""
    if sec is not None:
        lines = split_lines(text)
        sec_text = "\n".join(lines[getattr(sec, "start", 0) : getattr(sec, "end", 0)])
    explicit_weeks = set(int(x) for x in re.findall(r"第\s*(\d+)\s*周", sec_text))
    missing_weeks = [w for w in range(1, min_weeks + 1) if w not in explicit_weeks]
    if not missing_weeks:
        return text
    extra: list[str] = []
    for w in missing_weeks:
        extra.extend(
            [
                f"### 第{w}周",
                "- 负责人：待定",
                "- 输入：上游需求、数据与策略约束",
                "- 输出：阶段交付物与执行记录",
                "- 验收标准：结果可复核、可追踪、可落地",
                "",
            ]
        )
    return insert_lines_into_section(text, section_title, extra)


def _ensure_risk_register(
    text: str,
    instruction: str,
    *,
    extract_sections: Callable[..., list[Any]],
    find_section: Callable[[list[Any], str], Any | None],
    split_lines: Callable[[str], list[str]],
    insert_lines_into_section: Callable[[str, str, list[str]], str],
) -> str:
    inst = str(instruction or "")
    if not re.search(r"(风险台账|风险)", inst):
        return text
    min_items = 0
    m = re.search(r"风险台账[^。;\n]{0,160}?(?:至少|不少于)\s*(\d{1,3})\s*(?:项|条)?", inst)
    if m:
        try:
            min_items = int(m.group(1))
        except Exception:
            min_items = 0
    if min_items <= 0:
        m2 = re.search(r"(?:至少|不少于)\s*(\d{1,3})\s*(?:项|条)?\s*风险", inst)
        if m2:
            try:
                min_items = int(m2.group(1))
            except Exception:
                min_items = 0
    if min_items <= 0:
        min_items = _extract_min_count(inst, keyword_re=r"(风险台账|风险)", unit_re=r"(项|条)", default=0, cap=50)
    if min_items <= 0:
        return text
    section_title = "风险台账"
    sections = extract_sections(text, prefer_levels=(2, 3))
    sec = find_section(sections, section_title)
    sec_text = ""
    if sec is not None:
        lines = split_lines(text)
        sec_text = "\n".join(lines[getattr(sec, "start", 0) : getattr(sec, "end", 0)])
    ids = sorted(set(re.findall(r"\bR(\d+)\b", sec_text)))
    count = len(ids)
    if count >= min_items:
        return text
    extra: list[str] = []
    if count == 0:
        extra.append("| 风险ID | 概率 | 影响 | 缓解策略 | 预警信号 |")
        extra.append("| :-- | :-- | :-- | :-- | :-- |")
    for i in range(count + 1, min_items + 1):
        extra.append(f"| R{i} | 中 | 中 | 制定预案并设置责任人 | 告警阈值连续触发 |")
    return insert_lines_into_section(text, section_title, extra)


def _ensure_slo_metrics(
    text: str,
    instruction: str,
    *,
    extract_sections: Callable[..., list[Any]],
    find_section: Callable[[list[Any], str], Any | None],
    split_lines: Callable[[str], list[str]],
    insert_lines_into_section: Callable[[str, str, list[str]], str],
) -> str:
    inst = str(instruction or "")
    if not re.search(r"(SLO|可量化指标|指标)", inst, flags=re.IGNORECASE):
        return text
    min_metrics = _extract_min_count(
        inst,
        keyword_re=r"(SLO|可量化指标|指标)",
        unit_re=r"(项|条)",
        default=0,
        cap=50,
    )
    if min_metrics <= 0:
        return text
    section_title = "监控告警与SLO"
    sections = extract_sections(text, prefer_levels=(2, 3))
    sec = find_section(sections, section_title)
    sec_text = ""
    if sec is not None:
        lines = split_lines(text)
        sec_text = "\n".join(lines[getattr(sec, "start", 0) : getattr(sec, "end", 0)])
    metric_count = len(
        re.findall(
            r"(?m)^(?:-|\d+\.)\s*(?:指标|SLO|可用性|错误率|延迟|吞吐)",
            sec_text,
        )
    )
    if metric_count >= min_metrics:
        return text
    extra: list[str] = []
    for i in range(metric_count + 1, min_metrics + 1):
        extra.append(f"- 指标{i}：阈值按业务SLO设定；采样周期每5分钟；触发动作为自动告警并升级处理。")
    return insert_lines_into_section(text, section_title, extra)


def _ensure_appendix_checklist(
    text: str,
    instruction: str,
    *,
    extract_sections: Callable[..., list[Any]],
    find_section: Callable[[list[Any], str], Any | None],
    split_lines: Callable[[str], list[str]],
    insert_lines_into_section: Callable[[str, str, list[str]], str],
) -> str:
    inst = str(instruction or "")
    if not re.search(r"(附录|检查清单|checklist)", inst, flags=re.IGNORECASE):
        return text
    min_items = 0
    m = re.search(r"(?:附录|检查清单|checklist)[^。;\n]{0,160}?(?:至少|不少于)\s*(\d{1,3})\s*(?:项|条)?", inst)
    if m:
        try:
            min_items = int(m.group(1))
        except Exception:
            min_items = 0
    if min_items <= 0:
        min_items = _extract_min_count(
            inst,
            keyword_re=r"(附录检查清单|检查清单|打勾项)",
            unit_re=r"(项|条)",
            default=0,
            cap=100,
        )
    if min_items <= 0:
        return text
    section_title = "附录检查清单"
    sections = extract_sections(text, prefer_levels=(2, 3))
    sec = find_section(sections, section_title)
    sec_text = ""
    if sec is not None:
        lines = split_lines(text)
        sec_text = "\n".join(lines[getattr(sec, "start", 0) : getattr(sec, "end", 0)])
    count = len(re.findall(r"(?m)^\s*(?:- \[[ xX]\]|- \[ \]|- |\d+\.)\s*", sec_text))
    if count >= min_items:
        return text
    extra: list[str] = []
    for i in range(count + 1, min_items + 1):
        extra.append(f"- [ ] 检查项{i}：完成后请记录证据与责任人。")
    return insert_lines_into_section(text, section_title, extra)


def enforce_instruction_requirements(
    text: str,
    instruction: str,
    *,
    extract_required_sections_from_instruction: Callable[[str], list[str]],
    extract_sections: Callable[..., list[Any]],
    normalize_heading_text: Callable[[str], str],
    append_new_h2_section: Callable[[str, str, list[str]], str],
    find_section: Callable[[list[Any], str], Any | None],
    split_lines: Callable[[str], list[str]],
    insert_lines_into_section: Callable[[str, str, list[str]], str],
) -> str:
    out = str(text or "").strip()
    if not out:
        return out
    inst = str(instruction or "").strip()
    if not inst:
        return out

    out = _ensure_required_h2_sections(
        out,
        inst,
        extract_required_sections_from_instruction=extract_required_sections_from_instruction,
        extract_sections=extract_sections,
        normalize_heading_text=normalize_heading_text,
        append_new_h2_section=append_new_h2_section,
    )
    out = _ensure_disclaimer(
        out,
        inst,
        append_new_h2_section=append_new_h2_section,
        insert_lines_into_section=insert_lines_into_section,
    )
    out = _ensure_terminology_mapping(
        out,
        inst,
        extract_sections=extract_sections,
        find_section=find_section,
        split_lines=split_lines,
        insert_lines_into_section=insert_lines_into_section,
    )
    out = _ensure_weekly_plan(
        out,
        inst,
        extract_sections=extract_sections,
        find_section=find_section,
        split_lines=split_lines,
        insert_lines_into_section=insert_lines_into_section,
    )
    out = _ensure_risk_register(
        out,
        inst,
        extract_sections=extract_sections,
        find_section=find_section,
        split_lines=split_lines,
        insert_lines_into_section=insert_lines_into_section,
    )
    out = _ensure_slo_metrics(
        out,
        inst,
        extract_sections=extract_sections,
        find_section=find_section,
        split_lines=split_lines,
        insert_lines_into_section=insert_lines_into_section,
    )
    out = _ensure_appendix_checklist(
        out,
        inst,
        extract_sections=extract_sections,
        find_section=find_section,
        split_lines=split_lines,
        insert_lines_into_section=insert_lines_into_section,
    )
    return out.strip()
