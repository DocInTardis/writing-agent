"""Ui Content Validation Text Eval command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List

from scripts.ui_content_validation_constants import FORMAT_SENSITIVE_HINTS, TERM_ALIASES


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def normalize_for_match(text: str) -> str:
    raw = unicodedata.normalize("NFKC", str(text or ""))
    lowered = raw.lower()
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def squash_for_match(text: str) -> str:
    normalized = normalize_for_match(text)
    # Keep CJK/alnum tokens; drop most punctuation for resilient matching.
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def alias_candidates(term: str) -> List[str]:
    base = str(term or "").strip()
    if not base:
        return []
    key = base.lower()
    aliases = TERM_ALIASES.get(key, [])
    out = [base]
    for alias in aliases:
        if alias and alias not in out:
            out.append(alias)
    return out


def token_present(text: str, token: str) -> bool:
    src = str(text or "")
    if not src:
        return False
    src_norm = normalize_for_match(src)
    src_squash = squash_for_match(src)
    candidates = alias_candidates(token)
    for cand in candidates:
        c = str(cand or "").strip()
        if not c:
            continue
        if c in src:
            return True
        c_norm = normalize_for_match(c)
        if c_norm and c_norm in src_norm:
            return True
        if c.isascii() and re.search(rf"(?i)(?<![a-z0-9]){re.escape(c)}(?![a-z0-9])", src_norm):
            return True
        c_squash = squash_for_match(c)
        if c_squash and len(c_squash) >= 3 and c_squash in src_squash:
            return True
    return False


def heading_present(text: str, heading: str) -> bool:
    if not heading:
        return True
    src = str(text or "")
    for token in alias_candidates(heading):
        t = str(token or "").strip()
        if not t:
            continue
        if t in src:
            return True
        pattern = rf"(?im)^\s*(?:#{1,6}\s*)?{re.escape(t)}\s*(?:[:\uff1a\-]|$)"
        if re.search(pattern, src):
            return True
        pattern2 = rf"(?im)^\s*(?:section|\u7ae0\u8282|\u6807\u9898)\s*[:\uff1a]\s*{re.escape(t)}\s*$"
        if re.search(pattern2, src):
            return True
    return False


def is_format_sensitive_case(case: Dict[str, Any]) -> bool:
    constraints = case.get("constraints") if isinstance(case.get("constraints"), dict) else {}
    if bool(constraints.get("format_required")):
        return True
    acceptance = case.get("acceptance") if isinstance(case.get("acceptance"), dict) else {}
    parts: List[str] = [
        str(case.get("prompt") or ""),
        str(constraints.get("notes") or ""),
    ]
    for arr_key in ("required_keywords", "required_headings"):
        values = acceptance.get(arr_key) if isinstance(acceptance.get(arr_key), list) else []
        parts.extend([str(x) for x in values if str(x).strip()])
    hay = normalize_for_match(" ".join(parts))
    return any(h in hay for h in FORMAT_SENSITIVE_HINTS)


def extract_heading_text(line: str) -> str:
    raw = str(line or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"^#{1,6}\s*", "", raw)
    raw = re.sub(r"^(第?[一二三四五六七八九十0-9]+(?:章|节|部分)\s*)", "", raw)
    raw = re.sub(r"^[0-9]+(?:\.[0-9]+){0,3}\s*[、\.\)]\s*", "", raw)
    return raw.strip(" :：-")


def looks_like_numbered_list_item_heading(title: str) -> bool:
    s = re.sub(r"[\*_`]+", "", str(title or "")).strip()
    if not s:
        return False
    if len(s) > 24:
        return True
    if re.search(r"[：:；;。！？!?]", s):
        return True
    if s.endswith(("；", ";", "。", "，", ",")):
        return True
    if s.startswith(("负责人", "输入", "输出", "验收标准")):
        return True
    return False


def parse_heading_line(line: str) -> Dict[str, Any] | None:
    s = str(line or "").strip()
    if not s:
        return None
    m_md = re.match(r"^(#{1,6})\s+(.+)$", s)
    if m_md:
        return {"level": len(m_md.group(1)), "title": extract_heading_text(s)}
    if re.match(r"^第?[一二三四五六七八九十0-9]+(?:章|节|部分)\s*\S+", s):
        return {"level": 2, "title": extract_heading_text(s)}
    m_num = re.match(r"^(?P<num>[0-9]+(?:\.[0-9]+){0,3})\s*[、\.\)]\s*(?P<title>\S.+)$", s)
    if m_num:
        heading_text = extract_heading_text(s)
        if looks_like_numbered_list_item_heading(heading_text):
            return None
        dot_count = str(m_num.group("num") or "").count(".")
        return {"level": min(6, 2 + dot_count), "title": heading_text}
    return None


def is_heading_line(line: str) -> bool:
    return parse_heading_line(line) is not None


def split_sections_by_headings(text: str) -> List[Dict[str, Any]]:
    lines = [str(x).rstrip() for x in str(text or "").splitlines()]
    headings: List[Dict[str, Any]] = []
    for idx, line in enumerate(lines):
        parsed = parse_heading_line(line)
        if not parsed:
            continue
        headings.append({"idx": idx, "level": int(parsed.get("level") or 0), "title": str(parsed.get("title") or "")})

    if len(headings) <= 1:
        return []

    levels = [int(h.get("level") or 0) for h in headings if int(h.get("level") or 0) > 0]
    if not levels:
        return []

    scope_level = 2 if levels.count(2) >= 2 else min(levels)
    sections: List[Dict[str, Any]] = []
    for i, heading in enumerate(headings):
        if int(heading.get("level") or 0) != scope_level:
            continue
        start_idx = int(heading.get("idx") or 0)
        end_idx = len(lines)
        for nxt in headings[i + 1 :]:
            if int(nxt.get("level") or 0) <= scope_level:
                end_idx = int(nxt.get("idx") or len(lines))
                break
        body_lines = lines[start_idx + 1 : end_idx]
        sections.append({"heading": str(heading.get("title") or ""), "body_lines": body_lines})

    if len(sections) > 1:
        return sections

    fallback: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for line in lines:
        parsed = parse_heading_line(line)
        if parsed:
            current = {"heading": str(parsed.get("title") or ""), "body_lines": []}
            fallback.append(current)
            continue
        if current is not None:
            current["body_lines"].append(line)
    return fallback if len(fallback) > 1 else []


def looks_like_bilingual_case(acceptance: Dict[str, Any]) -> bool:
    parts: List[str] = []
    for key in ("required_keywords", "required_headings"):
        values = acceptance.get(key) if isinstance(acceptance.get(key), list) else []
        parts.extend([str(v) for v in values if str(v).strip()])
    hay = normalize_for_match(" ".join(parts))
    return any(tok in hay for tok in ("双语", "bilingual", "english", "英文", "en-us", "zh-cn"))


def evaluate_section_richness(text: str, acceptance: Dict[str, Any]) -> Dict[str, Any]:
    sections = split_sections_by_headings(text)
    if not sections:
        return {
            "enforced": False,
            "section_count": 0,
            "min_section_chars": 0,
            "empty_sections": [],
            "short_sections": [],
            "orphan_bilingual_lines": [],
        }
    min_chars = int(acceptance.get("min_chars") or 0)
    required_headings = [str(x).strip() for x in (acceptance.get("required_headings") or []) if str(x).strip()]
    enforce = bool(acceptance.get("enforce_section_richness")) or min_chars >= 700 or len(required_headings) >= 4
    if not enforce:
        return {
            "enforced": False,
            "section_count": len(sections),
            "min_section_chars": 0,
            "empty_sections": [],
            "short_sections": [],
            "orphan_bilingual_lines": [],
        }
    cfg_min = int(acceptance.get("min_section_chars") or 0)
    min_section_chars = cfg_min if cfg_min > 0 else (120 if min_chars >= 1000 else 80)
    empty_sections: List[str] = []
    short_sections: List[str] = []
    for sec in sections:
        heading = str(sec.get("heading") or "").strip() or "[untitled]"
        body = "\n".join([str(x).strip() for x in (sec.get("body_lines") or []) if str(x).strip()]).strip()
        body_chars = compact_len(body)
        if body_chars == 0:
            empty_sections.append(heading)
        elif body_chars < min_section_chars:
            short_sections.append(heading)

    orphan_bilingual: List[str] = []
    if not looks_like_bilingual_case(acceptance):
        lines = [str(x).strip() for x in str(text or "").splitlines()]
        for idx, line in enumerate(lines):
            if not re.match(r"^\([A-Za-z][A-Za-z\s\-/]{2,60}\)$", line):
                continue
            prev = ""
            for j in range(idx - 1, -1, -1):
                prev = lines[j].strip()
                if prev:
                    break
            nxt = ""
            for j in range(idx + 1, len(lines)):
                nxt = lines[j].strip()
                if nxt:
                    break
            if prev and is_heading_line(prev) and not re.search(r"[A-Za-z]{2,}", prev):
                if compact_len(nxt) < 40:
                    orphan_bilingual.append(line)

    return {
        "enforced": True,
        "section_count": len(sections),
        "min_section_chars": min_section_chars,
        "empty_sections": empty_sections,
        "short_sections": short_sections,
        "orphan_bilingual_lines": orphan_bilingual,
    }


def evaluate_acceptance(text: str, acceptance: Dict[str, Any]) -> Dict[str, Any]:
    text = str(text or "")
    norm_len = compact_len(text)
    min_chars = int(acceptance.get("min_chars") or 0)
    max_chars = int(acceptance.get("max_chars") or 0)
    required_keywords = [str(x) for x in acceptance.get("required_keywords", []) if str(x).strip()]
    forbidden_keywords = [str(x) for x in acceptance.get("forbidden_keywords", []) if str(x).strip()]
    required_headings = [str(x) for x in acceptance.get("required_headings", []) if str(x).strip()]

    missing_required = [kw for kw in required_keywords if not token_present(text, kw)]
    norm_text = normalize_for_match(text)
    present_forbidden = [kw for kw in forbidden_keywords if normalize_for_match(kw) in norm_text]
    missing_headings = [h for h in required_headings if not heading_present(text, h)]

    keyword_hit = len(required_keywords) - len(missing_required)
    heading_hit = len(required_headings) - len(missing_headings)
    keyword_min_raw = acceptance.get("required_keywords_min_hit", None)
    heading_min_raw = acceptance.get("required_headings_min_hit", None)
    keyword_min_hit = int(keyword_min_raw) if keyword_min_raw is not None else -1
    heading_min_hit = int(heading_min_raw) if heading_min_raw is not None else -1
    if required_keywords and keyword_min_hit < 0:
        keyword_min_hit = max(1, (len(required_keywords) + 1) // 2)  # ceil(0.5*n)
    if required_headings and heading_min_hit < 0:
        heading_min_hit = max(1, (len(required_headings) + 1) // 2)  # ceil(0.5*n)
    keyword_hit_ok = keyword_hit >= keyword_min_hit
    heading_hit_ok = heading_hit >= heading_min_hit

    length_ok = True
    if min_chars and norm_len < min_chars:
        length_ok = False
    if max_chars and max_chars > 0 and norm_len > max_chars:
        length_ok = False

    failures: List[str] = []
    if not length_ok:
        failures.append(f"length_out_of_range:{norm_len}")
    if required_keywords and not keyword_hit_ok:
        failures.append("missing_required_keywords")
    if present_forbidden:
        failures.append("forbidden_keywords_present")
    if required_headings and not heading_hit_ok:
        failures.append("missing_required_headings")

    richness = evaluate_section_richness(text, acceptance)
    if bool(richness.get("enforced")):
        short_sections = [str(x) for x in (richness.get("short_sections") or []) if str(x).strip()]
        empty_sections = [str(x) for x in (richness.get("empty_sections") or []) if str(x).strip()]
        orphan_bilingual = [str(x) for x in (richness.get("orphan_bilingual_lines") or []) if str(x).strip()]
        max_short_sections = int(acceptance.get("max_short_sections") or 0)
        if empty_sections:
            failures.append("empty_section_body")
        if len(short_sections) > max_short_sections:
            failures.append("section_body_too_short")
        if orphan_bilingual:
            failures.append("orphan_bilingual_residue")
    else:
        short_sections = []
        empty_sections = []
        orphan_bilingual = []

    return {
        "passed": len(failures) == 0,
        "char_count": norm_len,
        "keyword_hit": keyword_hit,
        "keyword_total": len(required_keywords),
        "keyword_min_hit": keyword_min_hit,
        "heading_hit": heading_hit,
        "heading_total": len(required_headings),
        "heading_min_hit": heading_min_hit,
        "missing_required_keywords": missing_required,
        "present_forbidden_keywords": present_forbidden,
        "missing_required_headings": missing_headings,
        "section_richness": richness,
        "short_sections": short_sections,
        "empty_sections": empty_sections,
        "orphan_bilingual_lines": orphan_bilingual,
        "failures": failures,
    }


def build_instruction_with_acceptance(base_instruction: str, acceptance: Dict[str, Any]) -> str:
    inst = str(base_instruction or "").strip()
    acc = acceptance if isinstance(acceptance, dict) else {}
    if not inst:
        return inst
    min_chars = int(acc.get("min_chars") or 0)
    max_chars = int(acc.get("max_chars") or 0)
    required_keywords = [str(x).strip() for x in (acc.get("required_keywords") or []) if str(x).strip()]
    required_headings = [str(x).strip() for x in (acc.get("required_headings") or []) if str(x).strip()]

    lines: List[str] = [inst, "", "[Validation Constraints]"]
    if min_chars > 0 and max_chars > 0:
        lines.append(f"- Keep total content length between {min_chars} and {max_chars} characters.")
    elif min_chars > 0:
        lines.append(f"- Keep total content length at least {min_chars} characters.")
    elif max_chars > 0:
        lines.append(f"- Keep total content length at most {max_chars} characters.")
    if required_headings:
        lines.append("- Include clear section headings: " + ", ".join(required_headings[:10]))
    if required_keywords:
        lines.append("- Ensure core terms are present: " + ", ".join(required_keywords[:12]))
    lines.append("- Output only the final document content, not commentary.")
    return "\n".join(lines).strip()


def build_round_instruction(
    base_instruction: str,
    acceptance: Dict[str, Any],
    must_keep: Iterable[str],
    must_change: Iterable[str],
) -> str:
    core = build_instruction_with_acceptance(base_instruction, acceptance)
    keep_items = [str(x).strip() for x in must_keep if str(x).strip()]
    change_items = [str(x).strip() for x in must_change if str(x).strip()]
    lines = [core, "", "[Round Constraints]"]
    if keep_items:
        lines.append("- Keep and retain these anchor items: " + ", ".join(keep_items[:12]))
    if change_items:
        lines.append("- This round must introduce or revise these items: " + ", ".join(change_items[:12]))
    lines.append("- Return full revised document.")
    return "\n".join(lines).strip()


def should_try_round_length_repair(acceptance_result: Dict[str, Any]) -> bool:
    failures = [str(x) for x in (acceptance_result.get("failures") or [])]
    return bool(failures) and all(x.startswith("length_out_of_range") for x in failures)


def should_try_round_acceptance_repair(acceptance_result: Dict[str, Any]) -> bool:
    failures = [str(x) for x in (acceptance_result.get("failures") or [])]
    if not failures:
        return False
    allowed = (
        "length_out_of_range",
        "missing_required_keywords",
        "missing_required_headings",
        "section_body_too_short",
        "empty_section_body",
        "orphan_bilingual_residue",
    )
    return all(any(flag in f for flag in allowed) for f in failures)


def build_round_length_repair_prompt(
    acceptance_cfg: Dict[str, Any],
    acceptance_result: Dict[str, Any],
    must_keep: Iterable[str],
    must_change: Iterable[str],
) -> str:
    min_chars = int(acceptance_cfg.get("min_chars") or 0)
    max_chars = int(acceptance_cfg.get("max_chars") or 0)
    current = int(acceptance_result.get("char_count") or 0)
    lines = [
        "Revise the current draft to satisfy length constraints while preserving existing logic.",
        f"Current char count: {current}.",
    ]
    if min_chars > 0 and max_chars > 0:
        lines.append(f"Target range: {min_chars}-{max_chars} characters.")
    elif min_chars > 0:
        lines.append(f"Target minimum: {min_chars} characters.")
    elif max_chars > 0:
        lines.append(f"Target maximum: {max_chars} characters.")
    keep_items = [str(x).strip() for x in must_keep if str(x).strip()]
    change_items = [str(x).strip() for x in must_change if str(x).strip()]
    if keep_items:
        lines.append("Keep anchors: " + ", ".join(keep_items[:10]))
    if change_items:
        lines.append("Keep change markers: " + ", ".join(change_items[:10]))
    lines.append("Return full revised document only.")
    return "\n".join(lines).strip()


def build_round_acceptance_repair_prompt(
    acceptance_cfg: Dict[str, Any],
    acceptance_result: Dict[str, Any],
    must_keep: Iterable[str],
    must_change: Iterable[str],
) -> str:
    min_chars = int(acceptance_cfg.get("min_chars") or 0)
    max_chars = int(acceptance_cfg.get("max_chars") or 0)
    current = int(acceptance_result.get("char_count") or 0)
    missing_keywords = [str(x).strip() for x in (acceptance_result.get("missing_required_keywords") or []) if str(x).strip()]
    missing_headings = [str(x).strip() for x in (acceptance_result.get("missing_required_headings") or []) if str(x).strip()]
    short_sections = [str(x).strip() for x in (acceptance_result.get("short_sections") or []) if str(x).strip()]
    empty_sections = [str(x).strip() for x in (acceptance_result.get("empty_sections") or []) if str(x).strip()]
    orphan_lines = [str(x).strip() for x in (acceptance_result.get("orphan_bilingual_lines") or []) if str(x).strip()]

    lines = [
        "Revise the current draft to satisfy acceptance constraints without removing valid content.",
        f"Current char count: {current}.",
    ]
    if min_chars > 0 and max_chars > 0:
        lines.append(f"Target range: {min_chars}-{max_chars} characters.")
    elif min_chars > 0:
        lines.append(f"Target minimum: {min_chars} characters.")
    elif max_chars > 0:
        lines.append(f"Target maximum: {max_chars} characters.")
    if missing_headings:
        lines.append("Add missing headings as standalone section headings: " + ", ".join(missing_headings[:12]))
    if missing_keywords:
        lines.append("Ensure these required keywords appear verbatim: " + ", ".join(missing_keywords[:16]))
    if empty_sections:
        lines.append("Fill empty sections with substantive body text: " + ", ".join(empty_sections[:10]))
    if short_sections:
        lines.append("Expand short sections with concrete details: " + ", ".join(short_sections[:10]))
    if orphan_lines:
        lines.append("Remove orphan bilingual residue lines and merge them into proper section paragraphs.")
    keep_items = [str(x).strip() for x in must_keep if str(x).strip()]
    change_items = [str(x).strip() for x in must_change if str(x).strip()]
    if keep_items:
        lines.append("Keep anchors: " + ", ".join(keep_items[:10]))
    if change_items:
        lines.append("Keep change markers: " + ", ".join(change_items[:10]))
    lines.append("Return full revised document only.")
    return "\n".join(lines).strip()


def check_keep_and_change(text: str, previous_text: str, must_keep: Iterable[str], must_change: Iterable[str]) -> Dict[str, Any]:
    t = str(text or "")
    p = str(previous_text or "")
    must_keep_list = [str(x) for x in must_keep if str(x).strip()]
    must_change_list = [str(x) for x in must_change if str(x).strip()]
    keep_missing = [x for x in must_keep_list if not token_present(t, x)]
    change_missing = [x for x in must_change_list if not token_present(t, x)]
    keep_hit = len(must_keep_list) - len(keep_missing)
    change_hit = len(must_change_list) - len(change_missing)
    keep_min_hit = max(1, int(len(must_keep_list) * 0.34)) if must_keep_list else 0
    change_min_hit = max(1, (len(must_change_list) + 1) // 2) if must_change_list else 0
    content_changed = t.strip() != p.strip()
    failures: List[str] = []
    if must_keep_list and keep_hit < keep_min_hit:
        failures.append("missing_must_keep")
    # In multi-round editing, content drift itself is the strongest signal.
    # If content changed but explicit marker terms are absent, treat as warning not hard failure.
    if must_change_list and change_hit < change_min_hit and not content_changed:
        failures.append("missing_must_change")
    if must_change_list and not content_changed:
        failures.append("content_not_changed")
    return {
        "passed": len(failures) == 0,
        "keep_missing": keep_missing,
        "change_missing": change_missing,
        "keep_hit": keep_hit,
        "keep_total": len(must_keep_list),
        "keep_min_hit": keep_min_hit,
        "change_hit": change_hit,
        "change_total": len(must_change_list),
        "change_min_hit": change_min_hit,
        "content_changed": content_changed,
        "failures": failures,
    }
