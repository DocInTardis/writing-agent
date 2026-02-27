"""Prefs Analysis Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import re


def normalize_analysis(data: object, raw_text: str) -> dict:
    base = {
        "intent": {"name": "other", "confidence": 0.1, "reason": ""},
        "rewritten_query": raw_text.strip(),
        "decomposition": [],
        "constraints": [],
        "missing": [],
        "entities": {},
    }
    if not isinstance(data, dict):
        return base
    intent = data.get("intent")
    if isinstance(intent, dict):
        name = str(intent.get("name") or "").strip() or "other"
        conf = intent.get("confidence")
        try:
            conf_val = float(conf)
        except Exception:
            conf_val = 0.1
        base["intent"] = {"name": name, "confidence": max(0.0, min(1.0, conf_val)), "reason": str(intent.get("reason") or "")}
    rewritten = str(data.get("rewritten_query") or "").strip()
    if rewritten:
        base["rewritten_query"] = rewritten
    decomp = data.get("decomposition")
    if isinstance(decomp, list):
        base["decomposition"] = [str(x).strip() for x in decomp if str(x).strip()][:12]
    constraints = data.get("constraints")
    if isinstance(constraints, list):
        base["constraints"] = [str(x).strip() for x in constraints if str(x).strip()][:12]
    missing = data.get("missing")
    if isinstance(missing, list):
        base["missing"] = [str(x).strip() for x in missing if str(x).strip()][:12]
    entities = data.get("entities")
    if isinstance(entities, dict):
        base["entities"] = {k: str(v).strip() for k, v in entities.items() if str(v).strip()}
    return base


def build_pref_summary(raw: str, analysis: dict, title: str, fmt: dict, prefs: dict) -> str:
    parts: list[str] = []
    clean_title = str(title or "").strip()
    if clean_title:
        parts.append(f"\u4e3b\u9898\uff1a{clean_title}")
    purpose = str(prefs.get("purpose") or "").strip() if isinstance(prefs, dict) else ""
    if purpose:
        parts.append(f"\u7528\u9014\uff1a{purpose}")
    mode = str(prefs.get("target_length_mode") or "").strip().lower() if isinstance(prefs, dict) else ""
    val = prefs.get("target_length_value") if isinstance(prefs, dict) else None
    if mode in {"chars", "pages"} and val:
        unit = "\u5b57" if mode == "chars" else "\u9875"
        parts.append(f"\u957f\u5ea6\uff1a\u7ea6{val}{unit}")
    if isinstance(fmt, dict):
        font = str(fmt.get("font_name_east_asia") or fmt.get("font_name") or "").strip()
        size = fmt.get("font_size_name") or (f"{fmt.get('font_size_pt')}pt" if fmt.get("font_size_pt") else "")
        if font or size:
            parts.append(f"\u6b63\u6587\uff1a{font} {size}".strip())
        h1 = fmt.get("heading1_size_pt")
        if h1:
            parts.append(f"\u6807\u9898\u5b57\u53f7\uff1a{h1}pt")
    decomp = analysis.get("decomposition") if isinstance(analysis, dict) else None
    if isinstance(decomp, list) and decomp:
        items = [str(x).strip() for x in decomp if str(x).strip()][:5]
        if items:
            parts.append("\u5185\u5bb9\u8981\u70b9\uff1a" + "\u3001".join(items))
    constraints = analysis.get("constraints") if isinstance(analysis, dict) else None
    if isinstance(constraints, list) and constraints:
        items = [str(x).strip() for x in constraints if str(x).strip()][:4]
        if items:
            parts.append("\u7ea6\u675f\uff1a" + "\u3001".join(items))
    entities = analysis.get("entities") if isinstance(analysis, dict) else None
    if isinstance(entities, dict):
        audience = str(entities.get("audience") or "").strip()
        if audience:
            parts.append(f"\u53d7\u4f17\uff1a{audience}")
        output_form = str(entities.get("output_form") or "").strip()
        if output_form:
            parts.append(f"\u8f93\u51fa\u5f62\u5f0f\uff1a{output_form}")
        voice = str(entities.get("voice") or "").strip()
        if voice:
            parts.append(f"\u8bed\u6c14/\u98ce\u683c\uff1a{voice}")
        scope = str(entities.get("scope") or "").strip()
        if scope:
            parts.append(f"\u5185\u5bb9\u8303\u56f4\uff1a{scope}")
        avoid = str(entities.get("avoid") or "").strip()
        if avoid:
            parts.append(f"\u907f\u514d/\u4e0d\u8981\uff1a{avoid}")
    if not parts:
        base = str(analysis.get("rewritten_query") or raw or "").strip()
        if base:
            return f"\u6211\u7406\u89e3\u4f60\u7684\u9700\u6c42\u662f\uff1a{base}"
        return ""
    return "\u6211\u7406\u89e3\u4f60\u7684\u9700\u6c42\u5982\u4e0b\uff1a\n" + "\n".join(parts)


def field_confidence(raw: str, analysis: dict, title: str, prefs: dict, fmt: dict) -> dict:
    raw_s = (raw or "").strip()
    ent = analysis.get("entities") if isinstance(analysis, dict) else None
    ent = ent if isinstance(ent, dict) else {}
    conf: dict[str, float] = {}
    if title and (title in raw_s or title in str(ent.get("title") or "")):
        conf["title"] = 0.8
    elif title:
        conf["title"] = 0.5
    purpose = str(prefs.get("purpose") or "").strip() if isinstance(prefs, dict) else ""
    if purpose and (purpose in raw_s or purpose in str(ent.get("purpose") or "")):
        conf["purpose"] = 0.8
    elif purpose:
        conf["purpose"] = 0.5
    mode = str(prefs.get("target_length_mode") or "").strip().lower() if isinstance(prefs, dict) else ""
    val = prefs.get("target_length_value") if isinstance(prefs, dict) else None
    if mode in {"chars", "pages"} and val:
        if re.search(r"\d+\s*(?:\u5b57|\u5b57\u7b26|\u9875|\u9762|\u4e07\u5b57)", raw_s):
            conf["length"] = 0.8
        else:
            conf["length"] = 0.5
    if isinstance(fmt, dict) and fmt:
        if re.search(r"\u5b57\u53f7|\u5b57\u4f53|\u884c\u8ddd|\u6392\u7248", raw_s):
            conf["format"] = 0.7
        else:
            conf["format"] = 0.45
    return conf


def low_conf_questions(conf: dict) -> list[str]:
    out: list[str] = []
    if conf.get("title", 1.0) < 0.6:
        out.append("\u6807\u9898\u53ef\u80fd\u7406\u89e3\u4e0d\u51c6\uff0c\u8bf7\u786e\u8ba4\u6807\u9898\u3002")
    if conf.get("purpose", 1.0) < 0.6:
        out.append("\u7528\u9014/\u573a\u666f\u53ef\u80fd\u4e0d\u660e\u786e\uff0c\u8bf7\u8865\u5145\u3002")
    if conf.get("length", 1.0) < 0.6:
        out.append("\u957f\u5ea6\u53ef\u80fd\u4e0d\u51c6\uff0c\u8bf7\u786e\u8ba4\u5b57\u6570/\u9875\u6570\u3002")
    if conf.get("format", 1.0) < 0.5:
        out.append("\u683c\u5f0f/\u6392\u7248\u8981\u6c42\u4e0d\u660e\u786e\uff0c\u6709\u7684\u8bdd\u8bf7\u8865\u5145\uff0c\u6ca1\u6709\u5199\u201c\u9ed8\u8ba4\u201d\u3002")
    return out


def prioritize_missing(raw: str, analysis: dict, items: list[str]) -> list[str]:
    if not items:
        return []
    _ = ((raw or "") + " " + str(analysis.get("rewritten_query") or "")).replace(" ", "")
    priority = [
        "title/purpose",
        "format/layout",
        "length",
        "structure/outline/scope",
        "audience",
        "deliverable/output requirements",
        "tone/style",
        "references/data sources",
        "special constraints",
    ]
    ordered = []
    seen = set()
    for p in priority:
        for it in items:
            if it in seen:
                continue
            if p == it:
                ordered.append(it)
                seen.add(it)
    for it in items:
        if it not in seen:
            ordered.append(it)
            seen.add(it)
    return ordered


def build_missing_questions(title: str, fmt: dict, prefs: dict, analysis: dict) -> list[str]:
    missing: list[str] = []
    clean_title = str(title or "").strip()
    if not clean_title:
        missing.append("\u4e3b\u9898/\u9898\u76ee")
    purpose = str(prefs.get("purpose") or "").strip() if isinstance(prefs, dict) else ""
    if not purpose:
        missing.append("\u7528\u9014/\u573a\u666f")
    mode = str(prefs.get("target_length_mode") or "").strip().lower() if isinstance(prefs, dict) else ""
    val = prefs.get("target_length_value") if isinstance(prefs, dict) else None
    if not (mode in {"chars", "pages"} and val):
        missing.append("\u76ee\u6807\u5b57\u6570\u6216\u9875\u6570")
    if not (isinstance(fmt, dict) and fmt):
        missing.append("\u683c\u5f0f/\u6392\u7248\u8981\u6c42\uff08\u6709\u5c31\u8bf4\uff0c\u6ca1\u6709\u5199\u201c\u9ed8\u8ba4\u201d\uff09")
    entities = analysis.get("entities") if isinstance(analysis, dict) else None
    if isinstance(entities, dict):
        audience = str(entities.get("audience") or "").strip()
        if not audience:
            missing.append("\u53d7\u4f17/\u5bf9\u8c61")
        output_form = str(entities.get("output_form") or "").strip()
        if not output_form:
            missing.append("\u8f93\u51fa\u5f62\u5f0f\uff08\u62a5\u544a/\u65b9\u6848/\u603b\u7ed3/\u6c47\u62a5\uff09")
        voice = str(entities.get("voice") or "").strip()
        if not voice:
            missing.append("\u8bed\u6c14/\u98ce\u683c")
        scope = str(entities.get("scope") or "").strip()
        if not scope:
            missing.append("\u5185\u5bb9\u8303\u56f4")
        avoid = str(entities.get("avoid") or "").strip()
        if not avoid:
            missing.append("\u4e0d\u5e0c\u671b\u51fa\u73b0\u7684\u5185\u5bb9")
    extra = analysis.get("missing") if isinstance(analysis, dict) else None
    if isinstance(extra, list):
        for item in extra:
            s = str(item).strip()
            if s and s not in missing:
                missing.append(s)
    missing = [m for m in missing if m][:4]
    if not missing:
        return []
    return ["\u8fd8\u7f3a\u8fd9\u4e9b\u5173\u952e\u4fe1\u606f\uff0c\u8bf7\u4e00\u6b21\u8865\u5145\uff1a" + "\u3001".join(missing)]


def length_from_text(raw: str) -> tuple[str, int] | None:
    s = (raw or "").strip()
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*\u4e07\u5b57", s)
    if m:
        return ("chars", int(float(m.group(1)) * 10000))
    m = re.search(r"(\d+)\s*(?:\u5b57|\u5b57\u7b26)", s)
    if m:
        return ("chars", int(m.group(1)))
    m = re.search(r"(\d+)\s*(?:\u9875|\u9762)", s)
    if m:
        return ("pages", int(m.group(1)))
    return None


def detect_extract_conflicts(*, analysis: dict, title: str, prefs: dict) -> list[str]:
    conflicts: list[str] = []
    entities = analysis.get("entities") if isinstance(analysis, dict) else None
    if not isinstance(entities, dict):
        return conflicts
    a_title = str(entities.get("title") or "").strip()
    if a_title and title and a_title not in title and title not in a_title:
        conflicts.append("\u6807\u9898\u7406\u89e3\u4e0d\u4e00\u81f4\uff0c\u8bf7\u786e\u8ba4\u6807\u9898\u3002")
    a_purpose = str(entities.get("purpose") or "").strip()
    p_purpose = str(prefs.get("purpose") or "").strip() if isinstance(prefs, dict) else ""
    if a_purpose and p_purpose and a_purpose not in p_purpose and p_purpose not in a_purpose:
        conflicts.append("\u7528\u9014/\u573a\u666f\u53ef\u80fd\u6709\u51fa\u5165\uff0c\u8bf7\u786e\u8ba4\u3002")
    a_len = length_from_text(str(entities.get("length") or "")) if isinstance(entities, dict) else None
    mode = str(prefs.get("target_length_mode") or "").strip().lower() if isinstance(prefs, dict) else ""
    val = prefs.get("target_length_value") if isinstance(prefs, dict) else None
    if a_len and mode in {"chars", "pages"} and val:
        a_mode, a_val = a_len
        try:
            v = int(val)
        except Exception:
            v = 0
        if a_mode == mode and v and abs(a_val - v) > max(80, int(0.2 * a_val)):
            conflicts.append("\u957f\u5ea6\u4fe1\u606f\u524d\u540e\u4e0d\u4e00\u81f4\uff0c\u8bf7\u786e\u8ba4\u5b57\u6570/\u9875\u6570\u3002")
    return conflicts


def infer_role_defaults(raw: str, prefs: dict, analysis: dict) -> dict:
    p = dict(prefs or {})
    s = ((raw or "") + " " + str(analysis.get("rewritten_query") or "")).lower()

    def _set_if_empty(key: str, val: str) -> None:
        if not p.get(key) and val:
            p[key] = val

    if any(k in s for k in ["research", "thesis", "paper", "academic"]):
        _set_if_empty("audience", "academic readers")
        _set_if_empty("voice", "objective")
        _set_if_empty("output_form", "paper")
    if any(k in s for k in ["business", "market", "proposal", "investment"]):
        _set_if_empty("audience", "business stakeholders")
        _set_if_empty("voice", "professional")
        _set_if_empty("output_form", "proposal")
    if any(k in s for k in ["news", "report", "briefing"]):
        _set_if_empty("audience", "general readers")
        _set_if_empty("voice", "neutral")
        _set_if_empty("output_form", "brief")
    return p


def detect_multi_intent(text: str) -> list[str]:
    s = (text or "").lower()
    if not s:
        return []
    deliverables = ["report", "proposal", "ppt", "brief", "prd", "weekly", "summary"]
    hit = [d for d in deliverables if d in s]
    if len(hit) >= 2:
        return [f"Multiple deliverables detected: {', '.join(hit[:4])}. Please confirm one primary output."]
    return []


def info_score(title: str, fmt: dict, prefs: dict, analysis: dict) -> int:
    score = 0
    if str(title or "").strip():
        score += 1
    if isinstance(prefs, dict):
        if prefs.get("purpose"):
            score += 1
        if prefs.get("target_length_mode") and prefs.get("target_length_value"):
            score += 1
        if prefs.get("output_form"):
            score += 1
        if prefs.get("audience"):
            score += 1
        if prefs.get("voice"):
            score += 1
        if prefs.get("scope"):
            score += 1
    if isinstance(fmt, dict) and fmt:
        score += 1
    return score
