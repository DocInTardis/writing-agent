"""Section postprocess residue and duplicate guards."""

from __future__ import annotations

import re

from writing_agent.v2.meta_firewall import MetaFirewall

_META_FIREWALL = MetaFirewall()

def _looks_like_prompt_residue(paragraph: str) -> bool:
    token = str(paragraph or "").strip()
    if not token:
        return False
    if _META_FIREWALL.scan(token, max_hits=1).has_meta:
        return True
    meta_line = re.compile(
        r"^(?:topic|doc_type|audience|style|keywords?|key\s*points?|analysis(?:_summary)?|plan(?:_summary)?)\s*:",
        re.IGNORECASE,
    )
    if meta_line.match(token):
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
    if re.search(r"^\S+围绕[“\"].+[”\"]补充研究对象", token):
        return True
    if re.search(r"^(本段旨在|本节将|本章将|应当涵盖|需要说明|请在本节)", token):
        return True
    if re.search(r"(禁止输出|写作要求|以下要求|违者扣分|不要在文章中显式说明)", token):
        return True
    if "附录：相关文献列表" in token:
        return True
    if "感谢中国知网提供的数据支持" in token:
        return True
    return False

def _looks_like_unsupported_claim_paragraph(paragraph: str) -> bool:
    token = str(paragraph or "").strip()
    if not token:
        return False
    if _UNSUPPORTED_CLAIM_SUPPORT_RE.search(token):
        return False
    numeric_claim = bool(
        _UNSUPPORTED_CLAIM_NUMERIC_RE.search(token)
        and _UNSUPPORTED_CLAIM_COMPARATIVE_RE.search(token)
    )
    if numeric_claim and _UNSUPPORTED_CLAIM_CONFIGURATION_RE.search(token):
        numeric_claim = False
    signal_claim = bool(_UNSUPPORTED_CLAIM_SIGNAL_RE.search(token))
    return numeric_claim or signal_claim

def _normalize_paragraph_signature(paragraph: str) -> str:
    token = str(paragraph or "").strip().lower()
    token = re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", token, flags=re.IGNORECASE)
    token = re.sub(r"\s+", "", token)
    token = re.sub(r"[，。！？；：、,.!?;:\-—\"'“”‘’()（）\[\]{}<>《》/\\]", "", token)
    return token[:220]

def _near_duplicate_signature(sig_a: str, sig_b: str) -> bool:
    if not sig_a or not sig_b:
        return False
    if sig_a == sig_b:
        return True
    min_len = min(len(sig_a), len(sig_b))
    max_len = max(len(sig_a), len(sig_b))
    if min_len < 24:
        return False
    if max_len > min_len * 1.7:
        return False
    overlap = sum(1 for idx in range(min_len) if sig_a[idx] == sig_b[idx])
    ratio = float(overlap) / float(min_len)
    return ratio >= 0.9

__all__ = [name for name in globals() if not name.startswith('__')]
