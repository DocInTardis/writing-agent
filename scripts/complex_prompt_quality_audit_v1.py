#!/usr/bin/env python3
"""Complex Prompt Quality Audit V1 command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from docx import Document


CP001_PATH = Path(".data/exports/ComplexPromptSuite_CP001.docx")
CP002_PATH = Path(".data/exports/ComplexPromptSuite_CP002.docx")
OUT_MD = Path("docs/COMPLEX_PROMPT_SUITE_QUALITY_AUDIT_V1.md")
OUT_JSON = Path("docs/COMPLEX_PROMPT_SUITE_QUALITY_AUDIT_V1.json")


@dataclass
class ScoreItem:
    name: str
    score: float
    max_score: float
    details: Dict[str, object]


def read_paragraphs(path: Path) -> List[str]:
    doc = Document(str(path))
    return [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]


def char_count(paragraphs: List[str]) -> int:
    return len("\n".join(paragraphs))


def section_block(paragraphs: List[str], heading_kw: str) -> List[str]:
    start = -1
    for i, p in enumerate(paragraphs):
        if heading_kw in p:
            start = i
            break
    if start < 0:
        return []
    for j in range(start + 1, len(paragraphs)):
        if re.match(r"^\s*(?:[一二三四五六七八九十]+、|\d+\.)", paragraphs[j]):
            return paragraphs[start:j]
    return paragraphs[start:]


def score_cp001(paragraphs: List[str]) -> Tuple[float, List[ScoreItem]]:
    text = "\n".join(paragraphs)
    items: List[ScoreItem] = []

    sections = [
        "目标与范围",
        "角色与职责",
        "数据分级与权限",
        "模型准入与评测",
        "上线发布与回滚",
        "监控告警与SLO",
        "审计与合规",
        "风险台账",
        "里程碑计划",
        "预算与资源",
        "培训与变更管理",
        "附录检查清单",
    ]
    sec_hits = {s: (s in text) for s in sections}
    sec_hit_count = sum(1 for v in sec_hits.values() if v)
    sec_score = 25.0 * sec_hit_count / len(sections)
    items.append(
        ScoreItem(
            name="章节覆盖（12项）",
            score=sec_score,
            max_score=25.0,
            details={"hit_count": sec_hit_count, "required_count": len(sections), "hits": sec_hits},
        )
    )

    c = char_count(paragraphs)
    len_score = 10.0 if c >= 1200 else 10.0 * c / 1200.0
    items.append(
        ScoreItem(name="长度要求（>=1200字）", score=min(len_score, 10.0), max_score=10.0, details={"chars": c})
    )

    budget = "\n".join(section_block(paragraphs, "预算与资源"))
    has_budget_sec = bool(budget)
    has_week = bool(re.search(r"第\s*\d+\s*(?:至|到|-)?\s*\d*\s*周|周\s*\d+", budget))
    has_manpower = any(k in budget for k in ["人力", "人员", "FTE"])
    has_cost = any(k in budget for k in ["成本", "预算", "费用"])
    has_assumption = any(k in budget for k in ["假设", "前提"])
    budget_score = sum(
        [
            3.0 if has_budget_sec else 0.0,
            3.0 if has_week else 0.0,
            3.0 if has_manpower else 0.0,
            3.0 if has_cost else 0.0,
            3.0 if has_assumption else 0.0,
        ]
    )
    items.append(
        ScoreItem(
            name="预算与资源细化",
            score=budget_score,
            max_score=15.0,
            details={
                "has_section": has_budget_sec,
                "has_weekly_breakdown": has_week,
                "has_manpower": has_manpower,
                "has_cost": has_cost,
                "has_assumptions": has_assumption,
            },
        )
    )

    mon_paras = section_block(paragraphs, "监控告警与SLO")
    mon_text = "\n".join(mon_paras)
    metric_lines = []
    for p in mon_paras:
        if re.search(r"%|秒|分钟|小时|ms|\d", p) and any(
            kw in p for kw in ["率", "时间", "可用", "吞吐", "用户", "CPU", "内存", "错误", "覆盖", "告警"]
        ):
            metric_lines.append(p)
    metric_count = len(metric_lines)
    has_threshold = bool(re.search(r"[<>≤≥]|%|秒|分钟|小时", mon_text))
    has_sampling = any(k in mon_text for k in ["采样", "每分钟", "每小时", "每日", "每周"])
    has_action = any(k in mon_text for k in ["触发", "动作", "通知", "回滚", "自动", "升级"])
    mon_score = 0.0
    mon_score += 3.0 if mon_text else 0.0
    mon_score += 6.0 * min(metric_count, 8) / 8.0
    mon_score += 2.0 if has_threshold else 0.0
    mon_score += 2.0 if has_sampling else 0.0
    mon_score += 2.0 if has_action else 0.0
    items.append(
        ScoreItem(
            name="监控告警与SLO",
            score=mon_score,
            max_score=15.0,
            details={
                "metric_count_estimate": metric_count,
                "has_threshold": has_threshold,
                "has_sampling_cycle": has_sampling,
                "has_trigger_action": has_action,
            },
        )
    )

    risk_paras = section_block(paragraphs, "风险台账")
    risk_text = "\n".join(risk_paras)
    risk_ids = sorted(set(re.findall(r"\bR\d+\b", risk_text)))
    has_prob = "概率" in risk_text
    has_impact = "影响" in risk_text
    has_mitigation = any(k in risk_text for k in ["缓解", "措施", "应对"])
    has_signal = any(k in risk_text for k in ["预警", "信号"])
    risk_score = 0.0
    risk_score += 3.0 if risk_text else 0.0
    risk_score += 6.0 * min(len(risk_ids), 10) / 10.0
    risk_score += 1.5 if has_prob else 0.0
    risk_score += 1.5 if has_impact else 0.0
    risk_score += 1.5 if has_mitigation else 0.0
    risk_score += 1.5 if has_signal else 0.0
    items.append(
        ScoreItem(
            name="风险台账完整度",
            score=risk_score,
            max_score=15.0,
            details={
                "risk_item_ids": risk_ids,
                "risk_item_count": len(risk_ids),
                "has_probability": has_prob,
                "has_impact": has_impact,
                "has_mitigation": has_mitigation,
                "has_warning_signal": has_signal,
            },
        )
    )

    ck_paras = section_block(paragraphs, "附录检查清单")
    checklist_count = 0
    if ck_paras:
        for p in ck_paras:
            if re.search(r"^\s*(?:[-*•]|[0-9]+\.)\s+\S+", p) or "检查项" in p or "☐" in p or "[ ]" in p:
                checklist_count += 1
    ck_score = 0.0
    ck_score += 3.0 if ck_paras else 0.0
    ck_score += 7.0 * min(checklist_count, 20) / 20.0
    items.append(
        ScoreItem(
            name="附录检查清单",
            score=ck_score,
            max_score=10.0,
            details={"checklist_item_count_estimate": checklist_count, "has_checklist_section": bool(ck_paras)},
        )
    )

    action_verbs = ["负责", "制定", "执行", "监控", "评估", "检查", "确保", "建立", "优化", "审核", "响应", "回滚", "验收"]
    verb_hits = sum(text.count(v) for v in action_verbs)
    prac_score = 10.0 * min(verb_hits, 30) / 30.0
    items.append(
        ScoreItem(name="可执行性表达", score=prac_score, max_score=10.0, details={"action_verb_hits": verb_hits})
    )

    total = round(sum(i.score for i in items), 2)
    return total, items


def score_cp002(paragraphs: List[str]) -> Tuple[float, List[ScoreItem]]:
    text = "\n".join(paragraphs)
    items: List[ScoreItem] = []

    part_a = [
        "项目背景",
        "用户画像分层",
        "对话策略矩阵",
        "知识库治理",
        "隐私与安全",
        "上线灰度",
        "应急回退",
        "质量评估",
        "成本收益测算",
    ]
    a_hits = {s: (s in text) for s in part_a}
    a_hit_count = sum(1 for v in a_hits.values() if v)
    a_score = 25.0 * a_hit_count / len(part_a)
    items.append(
        ScoreItem(
            name="Part A 初稿方案章节",
            score=a_score,
            max_score=25.0,
            details={"hit_count": a_hit_count, "required_count": len(part_a), "hits": a_hits},
        )
    )

    roles = ["法务意见", "运维意见", "业务意见", "客服主管意见"]
    role_idx: Dict[str, int] = {}
    for r in roles:
        for i, p in enumerate(paragraphs):
            if r in p:
                role_idx[r] = i
                break
    role_cover = len(role_idx)
    part_c_idx = len(paragraphs)
    for i, p in enumerate(paragraphs):
        if "三、执行版清单" in p:
            part_c_idx = i
            break

    role_resp: Dict[str, int] = {}
    for r in roles:
        if r not in role_idx:
            role_resp[r] = 0
            continue
        start = role_idx[r] + 1
        stop = part_c_idx
        for rr in roles:
            if rr in role_idx and role_idx[rr] > role_idx[r]:
                stop = min(stop, role_idx[rr])
        count = 0
        for p in paragraphs[start:stop]:
            if "响应策略" in p:
                count += 1
        role_resp[r] = count

    b_score = 0.0
    b_score += 8.0 * role_cover / len(roles)
    for r in roles:
        b_score += 3.0 * min(role_resp.get(r, 0), 5) / 5.0
    items.append(
        ScoreItem(
            name="Part B 二轮修改指引",
            score=b_score,
            max_score=20.0,
            details={"role_coverage": role_cover, "response_count_by_role": role_resp},
        )
    )

    c_score = 0.0
    has_part_c = "三、执行版清单" in text
    week_pattern = r"第\s*(\d+)\s*(?:至|到|-)?\s*(\d+)?\s*周"
    week_lines: List[str] = []
    covered_weeks: set[int] = set()
    range_line_count = 0
    for p in paragraphs:
        m = re.search(week_pattern, p)
        if not m:
            continue
        week_lines.append(p)
        s = int(m.group(1))
        e = int(m.group(2)) if m.group(2) else s
        if m.group(2):
            range_line_count += 1
        if e < s:
            s, e = e, s
        for w in range(s, e + 1):
            covered_weeks.add(w)

    field_complete = 0
    week_idx = [i for i, p in enumerate(paragraphs) if re.search(week_pattern, p)]
    week_idx.append(len(paragraphs))
    for i in range(len(week_idx) - 1):
        blk = "\n".join(paragraphs[week_idx[i] : week_idx[i + 1]])
        if all(k in blk for k in ["负责人", "输入", "输出", "验收标准"]):
            field_complete += 1

    c_score += 3.0 if has_part_c else 0.0
    c_score += 9.0 * min(len(covered_weeks), 12) / 12.0
    c_score += 8.0 * field_complete / max(1, len(week_lines))
    # If using week ranges instead of per-week rows, reduce score.
    if range_line_count > 0:
        c_score -= min(4.0, float(range_line_count))
    c_score = max(0.0, c_score)
    items.append(
        ScoreItem(
            name="Part C 执行版清单",
            score=c_score,
            max_score=20.0,
            details={
                "week_line_count": len(week_lines),
                "covered_weeks_count": len(covered_weeks),
                "field_complete_entries": field_complete,
                "range_line_count": range_line_count,
            },
        )
    )

    term_blk = "\n".join(section_block(paragraphs, "术语映射表"))
    has_term_sec = bool(term_blk)
    rows = re.findall(r"\|\s*[^|]+\s*\|\s*[^|]+\s*\|\s*[^|]+\s*\|", term_blk)
    term_rows = max(0, len(rows) - 1)
    d_score = 0.0
    d_score += 4.0 if has_term_sec else 0.0
    d_score += 11.0 * min(term_rows, 15) / 15.0
    items.append(
        ScoreItem(
            name="Part D 术语映射表",
            score=d_score,
            max_score=15.0,
            details={"has_section": has_term_sec, "term_rows_estimate": term_rows},
        )
    )

    disclaimer_terms = ["免责声明", "仅供参考", "不构成医疗建议", "不构成法律建议", "不构成诊断"]
    has_disclaimer = any(k in text for k in disclaimer_terms)
    e_score = 10.0 if has_disclaimer else 0.0
    items.append(
        ScoreItem(
            name="Part E 对外沟通免责声明",
            score=e_score,
            max_score=10.0,
            details={"has_disclaimer": has_disclaimer},
        )
    )

    c = char_count(paragraphs)
    len_score = 5.0 if c >= 1400 else 5.0 * c / 1400.0
    items.append(
        ScoreItem(name="长度要求（>=1400字）", score=min(len_score, 5.0), max_score=5.0, details={"chars": c})
    )

    absolute_terms = ["绝对", "保证", "一定", "完全不会", "百分之百", "必然"]
    abs_hits = [w for w in absolute_terms if w in text]
    lang_score = 5.0 - min(5.0, float(len(abs_hits)))
    items.append(
        ScoreItem(
            name="表达稳健性（避免绝对化）",
            score=lang_score,
            max_score=5.0,
            details={"absolute_hits": abs_hits},
        )
    )

    total = round(sum(i.score for i in items), 2)
    return total, items


def tier(score: float) -> str:
    if score >= 85:
        return "A（可发布）"
    if score >= 70:
        return "B（可内测）"
    if score >= 55:
        return "C（可迭代）"
    return "D（需重做）"


def write_report(cp1_total: float, cp1_items: List[ScoreItem], cp2_total: float, cp2_items: List[ScoreItem]) -> None:
    lines: List[str] = []
    lines.append("# Complex Prompt Suite Quality Audit V1")
    lines.append("")
    lines.append("- Scope: `ComplexPromptSuite_CP001.docx`, `ComplexPromptSuite_CP002.docx`")
    lines.append("- Method: rule-based audit against custom prompt requirements")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append("| Case | Score | Tier |")
    lines.append("|---|---:|---|")
    lines.append(f"| CP-001 | {cp1_total:.2f} / 100 | {tier(cp1_total)} |")
    lines.append(f"| CP-002 | {cp2_total:.2f} / 100 | {tier(cp2_total)} |")
    lines.append("")

    def emit_case(name: str, items: List[ScoreItem]) -> None:
        lines.append(f"## {name}")
        lines.append("")
        lines.append("| Item | Score | Max |")
        lines.append("|---|---:|---:|")
        for it in items:
            lines.append(f"| {it.name} | {it.score:.2f} | {it.max_score:.2f} |")
        lines.append("")
        lines.append("Details:")
        lines.append("")
        for it in items:
            lines.append(f"- `{it.name}`: `{json.dumps(it.details, ensure_ascii=False)}`")
        lines.append("")

    emit_case("CP-001", cp1_items)
    emit_case("CP-002", cp2_items)

    lines.append("## Actionable Fixes (Top)")
    lines.append("")
    lines.append("1. CP-001: 补齐缺失的4个强制章节（里程碑计划、预算与资源、培训与变更管理、附录检查清单）。")
    lines.append("2. CP-001: 风险台账扩展到>=10项，并完整包含概率/影响/缓解策略/预警信号。")
    lines.append("3. CP-001: 在预算章节补充按周的人力和成本分解，以及显式假设条件。")
    lines.append("4. CP-002: 术语映射表扩展到>=15行完整条目。")
    lines.append("5. CP-002: 增加对外沟通免责声明段落。")
    lines.append("6. CP-002: 执行清单从“周段”改成“逐周”12+行，每行保留负责人/输入/输出/验收标准。")
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    payload = {
        "cp001": {
            "score": cp1_total,
            "tier": tier(cp1_total),
            "items": [
                {"name": i.name, "score": i.score, "max": i.max_score, "details": i.details} for i in cp1_items
            ],
        },
        "cp002": {
            "score": cp2_total,
            "tier": tier(cp2_total),
            "items": [
                {"name": i.name, "score": i.score, "max": i.max_score, "details": i.details} for i in cp2_items
            ],
        },
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    if not CP001_PATH.exists() or not CP002_PATH.exists():
        raise SystemExit("missing docx under .data/exports")
    cp1_paras = read_paragraphs(CP001_PATH)
    cp2_paras = read_paragraphs(CP002_PATH)
    cp1_total, cp1_items = score_cp001(cp1_paras)
    cp2_total, cp2_items = score_cp002(cp2_paras)
    write_report(cp1_total, cp1_items, cp2_total, cp2_items)
    print(f"CP-001 score={cp1_total:.2f} tier={tier(cp1_total)}")
    print(f"CP-002 score={cp2_total:.2f} tier={tier(cp2_total)}")
    print(f"report_md={OUT_MD.as_posix()}")
    print(f"report_json={OUT_JSON.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
