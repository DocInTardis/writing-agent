"""Paradigm lock classifier and outline probe utilities."""

from __future__ import annotations

from dataclasses import dataclass
import re


_PARADIGM_BIBLIOMETRIC = "bibliometric"
_PARADIGM_ENGINEERING = "engineering"
_PARADIGM_EMPIRICAL = "empirical"
_SUPPORTED_PARADIGMS = (_PARADIGM_BIBLIOMETRIC, _PARADIGM_ENGINEERING, _PARADIGM_EMPIRICAL)

_DEFAULT_BIBLIOMETRIC_OUTLINE = [
    "摘要",
    "关键词",
    "引言",
    "数据来源与检索策略",
    "发文量时空分布",
    "作者与机构合作网络",
    "关键词共现与聚类分析",
    "研究热点演化与突现分析",
    "讨论",
    "结论",
    "参考文献",
]

_DEFAULT_ENGINEERING_OUTLINE = [
    "摘要",
    "关键词",
    "引言",
    "需求分析",
    "系统总体架构",
    "关键技术实现",
    "实验设计与结果分析",
    "工程落地与部署",
    "结论",
    "参考文献",
]

_DEFAULT_EMPIRICAL_OUTLINE = [
    "摘要",
    "关键词",
    "引言",
    "研究设计",
    "数据来源与变量定义",
    "实证结果",
    "稳健性与异质性分析",
    "讨论",
    "结论",
    "参考文献",
]

_ENGINEERING_SECTION_PATTERN = re.compile(
    r"(\u7cfb\u7edf\u8bbe\u8ba1|\u67b6\u6784|\u5b9e\u73b0|\u5de5\u7a0b|\u90e8\u7f72|api|module|implementation|architecture)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParadigmDecision:
    paradigm: str
    runner_up: str
    confidence: float
    margin: float
    reasons: list[str]
    score_map: dict[str, float]
    source: str = "classifier"

    @property
    def low_confidence(self) -> bool:
        return False

    def to_dict(self, *, low_confidence: bool) -> dict[str, object]:
        return {
            "paradigm": self.paradigm,
            "runner_up": self.runner_up,
            "confidence": float(self.confidence),
            "margin": float(self.margin),
            "reasons": list(self.reasons),
            "score_map": dict(self.score_map),
            "source": str(self.source),
            "low_confidence": bool(low_confidence),
        }


class ParadigmLock:
    def __init__(self, *, low_conf_threshold: float = 0.8, low_margin_threshold: float = 0.15) -> None:
        self.low_conf_threshold = float(low_conf_threshold)
        self.low_margin_threshold = float(low_margin_threshold)

    @staticmethod
    def normalize_paradigm(value: str) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        alias_map = {
            "biblio": _PARADIGM_BIBLIOMETRIC,
            "bibliometric": _PARADIGM_BIBLIOMETRIC,
            "literature_review_map": _PARADIGM_BIBLIOMETRIC,
            "文献计量": _PARADIGM_BIBLIOMETRIC,
            "知识图谱": _PARADIGM_BIBLIOMETRIC,
            "engineering": _PARADIGM_ENGINEERING,
            "technical": _PARADIGM_ENGINEERING,
            "tech_report": _PARADIGM_ENGINEERING,
            "工程": _PARADIGM_ENGINEERING,
            "实证": _PARADIGM_EMPIRICAL,
            "empirical": _PARADIGM_EMPIRICAL,
            "quantitative": _PARADIGM_EMPIRICAL,
        }
        return alias_map.get(raw, "")

    def is_low_confidence(self, decision: ParadigmDecision) -> bool:
        return (float(decision.confidence) < self.low_conf_threshold) or (
            float(decision.margin) < self.low_margin_threshold
        )

    def classify(
        self,
        *,
        instruction: str,
        analysis: dict | None = None,
        user_override: str = "",
    ) -> ParadigmDecision:
        text = str(instruction or "")
        analysis_obj = analysis if isinstance(analysis, dict) else {}
        topics = " ".join(
            [
                text,
                str(analysis_obj.get("topic") or ""),
                str(analysis_obj.get("doc_type") or ""),
                " ".join([str(x) for x in (analysis_obj.get("keywords") or []) if str(x).strip()]),
                " ".join([str(x) for x in (analysis_obj.get("must_include") or []) if str(x).strip()]),
            ]
        )
        lowered = topics.lower()

        scores = {
            _PARADIGM_BIBLIOMETRIC: 0.0,
            _PARADIGM_ENGINEERING: 0.0,
            _PARADIGM_EMPIRICAL: 0.0,
        }
        reasons: list[str] = []

        def _hit(pattern: str, *, weight: float, target: str, reason: str) -> None:
            m = re.search(pattern, lowered, flags=re.IGNORECASE)
            if not m:
                return
            scores[target] += float(weight)
            if reason not in reasons:
                reasons.append(reason)

        _hit(
            r"(citespace|bibliometric|\u6587\u732e\u8ba1\u91cf|\u53ef\u89c6\u5316\u5206\u6790|\u77e5\u8bc6\u56fe\u8c31|\u5173\u952e\u8bcd\u5171\u73b0|\u805a\u7c7b\u5206\u6790|\u7a81\u73b0\u5206\u6790|\u53d1\u6587\u91cf)",
            weight=3.2,
            target=_PARADIGM_BIBLIOMETRIC,
            reason="bibliometric_markers",
        )
        _hit(
            r"(\u7cfb\u7edf\u8bbe\u8ba1|\u5de5\u7a0b\u5b9e\u73b0|\u90e8\u7f72|\u67b6\u6784|implementation|architecture|api|module|state machine)",
            weight=3.0,
            target=_PARADIGM_ENGINEERING,
            reason="engineering_markers",
        )
        _hit(
            r"(\u5b9e\u8bc1|\u56de\u5f52|\u6837\u672c|\u53d8\u91cf|\u5047\u8bbe|\u7a33\u5065\u6027|\u5f02\u8d28\u6027|empirical|regression)",
            weight=2.8,
            target=_PARADIGM_EMPIRICAL,
            reason="empirical_markers",
        )

        doc_type = str(analysis_obj.get("doc_type") or "").strip().lower()
        if doc_type in {"technical", "technical_report", "report"}:
            scores[_PARADIGM_ENGINEERING] += 1.0
        elif doc_type in {"academic", "paper", "thesis"}:
            scores[_PARADIGM_BIBLIOMETRIC] += 0.4
            scores[_PARADIGM_EMPIRICAL] += 0.4

        total = max(1e-6, float(sum(max(0.0, s) for s in scores.values())))
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_name, top_score = ranked[0]
        second_name, second_score = ranked[1]
        confidence = max(0.0, min(1.0, float(top_score) / total))
        margin = max(0.0, min(1.0, float(top_score - second_score) / total))

        source = "classifier"
        override = self.normalize_paradigm(user_override)
        if override in _SUPPORTED_PARADIGMS:
            top_name = override
            confidence = 1.0
            margin = 1.0
            source = "override"
            if "user_override" not in reasons:
                reasons.append("user_override")
            alt = [k for k, _ in ranked if k != override]
            second_name = alt[0] if alt else second_name

        return ParadigmDecision(
            paradigm=top_name,
            runner_up=second_name,
            confidence=round(float(confidence), 4),
            margin=round(float(margin), 4),
            reasons=reasons[:8],
            score_map={k: round(float(v), 4) for k, v in scores.items()},
            source=source,
        )

    def outline_for(self, paradigm: str, *, bibliometric_outline: list[str] | None = None) -> list[str]:
        p = self.normalize_paradigm(paradigm) or _PARADIGM_EMPIRICAL
        if p == _PARADIGM_BIBLIOMETRIC:
            return [str(x).strip() for x in (bibliometric_outline or _DEFAULT_BIBLIOMETRIC_OUTLINE) if str(x).strip()]
        if p == _PARADIGM_ENGINEERING:
            return list(_DEFAULT_ENGINEERING_OUTLINE)
        return list(_DEFAULT_EMPIRICAL_OUTLINE)

    def enforce_sections(
        self,
        *,
        sections: list[str],
        paradigm: str,
        allow_engineering: bool,
        bibliometric_outline: list[str] | None = None,
    ) -> list[str]:
        normalized = [str(x).strip() for x in (sections or []) if str(x).strip()]
        if not normalized:
            return []
        p = self.normalize_paradigm(paradigm) or _PARADIGM_EMPIRICAL
        if p == _PARADIGM_BIBLIOMETRIC and not allow_engineering:
            return self.outline_for(_PARADIGM_BIBLIOMETRIC, bibliometric_outline=bibliometric_outline)
        if p == _PARADIGM_BIBLIOMETRIC and allow_engineering:
            return [x for x in normalized if not _ENGINEERING_SECTION_PATTERN.search(x)] or self.outline_for(
                _PARADIGM_BIBLIOMETRIC,
                bibliometric_outline=bibliometric_outline,
            )
        out: list[str] = []
        seen: set[str] = set()
        for sec in normalized:
            key = sec.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(sec)
        return out

    def dual_outline_probe(
        self,
        *,
        instruction: str,
        analysis: dict | None,
        primary_paradigm: str,
        secondary_paradigm: str,
        primary_outline: list[str],
        secondary_outline: list[str],
    ) -> dict[str, object]:
        score_primary = self._outline_score(
            instruction=instruction,
            analysis=analysis,
            paradigm=primary_paradigm,
            outline=primary_outline,
        )
        score_secondary = self._outline_score(
            instruction=instruction,
            analysis=analysis,
            paradigm=secondary_paradigm,
            outline=secondary_outline,
        )
        margin = abs(score_primary - score_secondary)
        if margin < 0.06:
            return {
                "resolved": False,
                "selected_paradigm": "",
                "selected_outline": [],
                "margin": round(float(margin), 4),
                "scores": {
                    str(primary_paradigm): round(float(score_primary), 4),
                    str(secondary_paradigm): round(float(score_secondary), 4),
                },
                "reason": "probe_score_too_close",
            }
        if score_primary >= score_secondary:
            selected_paradigm = str(primary_paradigm)
            selected_outline = [str(x).strip() for x in (primary_outline or []) if str(x).strip()]
        else:
            selected_paradigm = str(secondary_paradigm)
            selected_outline = [str(x).strip() for x in (secondary_outline or []) if str(x).strip()]
        return {
            "resolved": bool(selected_outline),
            "selected_paradigm": selected_paradigm,
            "selected_outline": selected_outline,
            "margin": round(float(margin), 4),
            "scores": {
                str(primary_paradigm): round(float(score_primary), 4),
                str(secondary_paradigm): round(float(score_secondary), 4),
            },
            "reason": "",
        }

    def _outline_score(self, *, instruction: str, analysis: dict | None, paradigm: str, outline: list[str]) -> float:
        p = self.normalize_paradigm(paradigm)
        if not p:
            return 0.0
        joined = " ".join([str(instruction or ""), " ".join([str(x) for x in outline if str(x).strip()])]).lower()
        if analysis and isinstance(analysis, dict):
            joined += " " + str(analysis.get("topic") or "").lower()

        score = 0.0
        if p == _PARADIGM_BIBLIOMETRIC:
            if re.search(r"(citespace|bibliometric|\u6587\u732e\u8ba1\u91cf|\u77e5\u8bc6\u56fe\u8c31)", joined, flags=re.IGNORECASE):
                score += 0.8
            if re.search(
                r"(\u5173\u952e\u8bcd\u5171\u73b0|\u805a\u7c7b|\u7a81\u73b0|\u53d1\u6587\u91cf|\u5408\u4f5c\u7f51\u7edc|"
                r"keyword co-occurrence|cluster|burst|publication volume|collaboration network)",
                joined,
                flags=re.IGNORECASE,
            ):
                score += 0.5
            if _ENGINEERING_SECTION_PATTERN.search(" ".join(outline or [])):
                score -= 0.3
        elif p == _PARADIGM_ENGINEERING:
            if _ENGINEERING_SECTION_PATTERN.search(joined):
                score += 0.9
            if re.search(r"(experiment|benchmark|\u5b9e\u9a8c|\u7cfb\u7edf)", joined, flags=re.IGNORECASE):
                score += 0.4
        else:
            if re.search(r"(\u5b9e\u8bc1|regression|\u7a33\u5065\u6027|\u5f02\u8d28\u6027|\u53d8\u91cf)", joined, flags=re.IGNORECASE):
                score += 0.9
            if re.search(r"(\u6570\u636e\u6765\u6e90|\u6837\u672c)", joined, flags=re.IGNORECASE):
                score += 0.3
        # Prefer richer, non-trivial outlines.
        score += min(0.25, max(0.0, float(len(outline or [])) / 60.0))
        return max(0.0, min(2.0, score))
