"""Process-noise and duplicate detection helpers for text sanitize."""

from __future__ import annotations

import json
import re

from writing_agent.v2.figure_render import is_renderable_figure_spec

def _looks_like_process_line(line: str) -> bool:
    token = str(line or "").strip()
    if not token:
        return False
    if token.startswith("[[TABLE:") or token.startswith("[[FIGURE:"):
        return False
    if re.search(
        r"(?i)(?:^|[,{]\s*)\"?(?:section_id|block_id|type|items|caption|columns|rows)\"?\s*:",
        token,
    ):
        return True
    if re.match(r'^\s*[{}\[\],:"]+\s*$', token):
        return True
    if re.match(
        r"^(?:topic|doc_type|audience|style|keywords?|key\s*points?|analysis(?:_summary)?|plan(?:_summary)?)\s*:",
        token,
        flags=re.IGNORECASE,
    ):
        return True
    if "<analysis_summary>" in token or "</analysis_summary>" in token:
        return True
    if "<user_instruction>" in token or "</user_instruction>" in token:
        return True
    if "应给出可测量的验收规则" in token:
        return True
    if re.search(r"(?:本节|本段).{0,16}(?:应|需|建议|请).{0,24}(?:验收|可复核|可复现|边界|约束)", token):
        return True
    if re.search(r"(?:围绕|针对).{0,24}(?:应说明|需交代|补充).{0,36}(?:验收标准|可复核|可复现)", token):
        return True
    if re.search(r"^(?:[^\s，。]{0,16})?(?:应覆盖|应阐明|应说明|需突出|需交代|建议统一术语口径)", token):
        return True
    if re.search(r"^在[^，。]{0,16}中，建议统一术语口径", token):
        return True
    if "附录：相关文献列表" in token:
        return True
    if "感谢中国知网提供的数据支持" in token:
        return True
    if "补充说明：本研究进一步明确了方法边界、复现条件与应用场景" in token:
        return True
    if re.search(r"(?:本段|本节|本章).{0,12}(?:补充了|围绕).{0,40}(?:方法路径|输入输出|关键参数|样本边界|变量(?:定义|控制)|论证路径|证据支撑)", token):
        return True
    if re.search(r"(?:此外|同时|进一步).{0,8}(?:围绕|补充).{0,48}(?:本节|本章|核心问题|关键问题|论证路径|证据支撑)", token):
        return True
    if re.search(r"围绕[“\"].+[”\"](?:，|,)?(?:进一步)?(?:补充|展开)", token):
        return True
    if re.search(r"先界定研究目标与对象，再说明核心问题的形成机制", token):
        return True
    if re.search(r"给出方法路径、输入输出与关键参数设置", token):
        return True
    if re.search(r"基于数据来源、评价指标与结果解释构建证据链", token):
        return True
    if re.search(r"说明边界条件、潜在偏差与适用范围", token):
        return True
    if re.search(r"文本(?:明确|呈现|通过|识别|结合).{0,36}(?:样本边界|协同链路|对照场景|风险来源|证据链条)", token):
        return True
    if re.search(r"^Based on the available sources", token, flags=re.IGNORECASE):
        return True
    if re.search(r"^The sources listed are", token, flags=re.IGNORECASE):
        return True
    if re.search(r"^(本段旨在|本节将|本章将|应当涵盖|需要说明|请在本节)", token):
        return True
    if re.search(r"(禁止输出|写作要求|以下要求|违者扣分|不要在文章中显式说明)", token):
        return True
    return False

def _is_dedup_candidate_line(line: str) -> bool:
    token = str(line or "").strip()
    if not token:
        return False
    if token.startswith("#"):
        return False
    if token.startswith("[[TABLE:") or token.startswith("[[FIGURE:"):
        return False
    if re.match(r"^\[\d+\]\s+", token):
        return False
    if re.match(r"^\s*(?:[-*•·]|\d+[.\uFF0E\u3001\)]|[一二三四五六七八九十]+[.\u3001\)])\s+", token):
        return False
    return len(token) >= 12

def _normalize_sentence_key(text: str) -> str:
    token = str(text or "").strip().lower()
    token = re.sub(r"\s+", "", token)
    token = re.sub(r"[，。！？；:：、,.!?;\"'“”‘’()（）\[\]{}<>《》]", "", token)
    return token

def _dedupe_repeated_sentences(text: str) -> str:
    src = str(text or "")
    if not src:
        return ""
    seen: set[str] = set()
    out_lines: list[str] = []
    for raw in src.split("\n"):
        line = str(raw or "")
        token = line.strip()
        if not token:
            out_lines.append(line)
            continue
        if token.startswith("#") or token.startswith("[[TABLE:") or token.startswith("[[FIGURE:"):
            out_lines.append(line)
            continue
        if re.match(r"^\[\d+\]\s+", token):
            out_lines.append(line)
            continue
        parts = re.split(r"(?<=[。！？!?；;])", token)
        kept: list[str] = []
        for part in parts:
            sent = str(part or "").strip()
            if not sent:
                continue
            key = _normalize_sentence_key(sent)
            # Keep short factual fragments to avoid over-aggressive drops.
            if len(key) < 16:
                kept.append(sent)
                continue
            if key in seen:
                continue
            seen.add(key)
            kept.append(sent)
        if kept:
            out_lines.append("".join(kept))
    return "\n".join(out_lines)

def _normalize_global_media_markers(text: str) -> str:
    src = str(text or "")
    if not src:
        return src

    def _fix_table(match: re.Match[str]) -> str:
        raw = str(match.group(1) or "").strip()
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        caption = str(payload.get("caption") or "").strip() or "关键指标对比"
        rows = payload.get("rows")
        if not isinstance(rows, list):
            rows = []
        value_cells: list[str] = []
        for row in rows:
            if isinstance(row, list):
                cells = [str(c).strip() for c in row]
                if len(cells) > 1:
                    value_cells.extend(cells[1:])
                else:
                    value_cells.extend(cells)
        if value_cells and all(c in {"--", "-", ""} for c in value_cells):
            rows = [
                ["数据可信性", "依赖中心化校验，跨主体核验成本高", "链上校验与多方共识降低篡改风险"],
                ["服务响应效率", "流程环节多，跨部门协同时延高", "流程标准化后可缩短处理链路"],
                ["治理透明度", "状态追踪分散，责任定位困难", "关键流程可追踪，便于审计复核"],
            ]
            payload["columns"] = ["评价维度", "现有方案", "本研究方案"]
        payload["caption"] = caption
        payload["rows"] = rows
        return f"[[TABLE:{json.dumps(payload, ensure_ascii=False)}]]"

    def _fix_figure(match: re.Match[str]) -> str:
        raw = str(match.group(1) or "").strip()
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if not is_renderable_figure_spec(payload):
            return ""
        caption = str(payload.get("caption") or "").strip()
        if (not caption) or (caption in {"\u65b9\u6cd5\u6d41\u7a0b\u56fe", "\u6d41\u7a0b\u56fe", "\u4e1a\u52a1\u6d41\u7a0b\u793a\u610f\u56fe", "\u5173\u952e\u6d41\u7a0b\u793a\u610f\u56fe"}):
            payload["caption"] = "\u6d41\u7a0b\u793a\u610f\u56fe"
        return f"[[FIGURE:{json.dumps(payload, ensure_ascii=False)}]]"

    src = re.sub(r"\[\[\s*TABLE\s*:\s*(\{[\s\S]*?\})\s*\]\]", _fix_table, src, flags=re.IGNORECASE)
    src = re.sub(r"\[\[\s*FIGURE\s*:\s*(\{[\s\S]*?\})\s*\]\]", _fix_figure, src, flags=re.IGNORECASE)
    return src

__all__ = [name for name in globals() if not name.startswith("__")]
