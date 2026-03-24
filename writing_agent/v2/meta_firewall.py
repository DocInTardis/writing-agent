"""Meta-instruction firewall for section drafts."""

from __future__ import annotations

from dataclasses import dataclass
import re


META_HARD_PATTERNS = [
    r"应给出.*验收规则",
    r"需突出.*实施策略",
    r"针对.*需交代",
    r"围绕.*应说明",
    r"本节.*核心问题",
    r"关键论证与结论",
    r"方法路径、关键假设与实现步骤",
    r"工程约束与适用范围",
    r"风险控制与可落地的实施要点",
    r"topic:.*doc_type:",
    r"key points?:",
    r"(?:摘要|引言|结论).{0,8}(?:应覆盖|应说明|应阐明|需突出|需交代)",
    r"^(?:topic|doc_type|audience|style|keywords?|key\s*points?|analysis(?:_summary)?|plan(?:_summary)?)\s*:",
    r"^(?:本段旨在|本节将|本章将|应当涵盖|需要说明|请在本节)",
    r"(?:禁止输出|写作要求|以下要求|违者扣分|不要在文章中显式说明)",
    r"(?:本段|本节|本章).{0,12}(?:补充了|围绕).{0,40}(?:方法路径|输入输出|关键参数|样本边界|变量(?:定义|控制)|论证路径|证据支撑)",
    r"(?:此外|同时|进一步).{0,8}(?:围绕|补充).{0,48}(?:本节|本章|核心问题|关键问题|论证路径|证据支撑)",
    r"补充方法路径、输入输出与关键参数设置",
    r"围绕[‘“].+[’”](?:，|,)?(?:进一步)?(?:补充|展开)",
    r"(?:本段|本节).{0,8}(?:主要|重点)?(?:说明|补充|阐述).{0,30}(?:写作|方法路径|输入输出|关键参数|证据支撑)",
    r"先界定研究目标与对象，再说明核心问题的形成机制",
    r"给出方法路径、输入输出与关键参数设置",
    r"基于数据来源、评价指标与结果解释构建证据链",
    r"说明边界条件、潜在偏差与适用范围",
    r"文本明确样本边界、变量定义与判定规则",
    r"文本呈现跨主体协同链路中的数据校验细节",
    r"文本通过对照场景分析实施差异",
    r"文本识别风险来源并给出缓释路径",
    r"文本结合评价指标建立证据链条",
    r"^\[\d+\][；;]\s*[\u4e00-\u9fffA-Za-z]",
    r"(?:\u6458\u8981|\u5f15\u8a00|\u7ed3\u8bba|\u76f8\u5173\u7814\u7a76|\u8ba8\u8bba|\u6570\u636e\u6765\u6e90\u4e0e\u68c0\u7d22\u7b56\u7565).{0,12}(?:\u4ea4\u4ee3|\u754c\u5b9a|\u8bf4\u660e|\u7ed9\u51fa|\u68b3\u7406|\u603b\u7ed3).{0,80}(?:\u7814\u7a76\u6216\u9879\u76ee\u80cc\u666f|\u95ee\u9898\u8d77\u70b9|\u62a5\u544a\u8303\u56f4|\u7814\u7a76\u610f\u4e49|\u7ed3\u6784\u5b89\u6392|\u65b9\u6cd5\u6d41\u7a0b|\u5173\u952e\u53c2\u6570|\u8f93\u5165\u8f93\u51fa|\u8bc4\u4ef7\u6307\u6807\u4f53\u7cfb|\u8bef\u5dee\u6765\u6e90)",
    r"(?:\u5b9e\u9a8c\u9879|\u6b65\u9aa4\u4e00|\u6b65\u9aa4\u4e8c|\u6b65\u9aa4\u4e09|\u5e8f\u53f7\u5360\u4f4d\u7b26|\u5360\u4f4d\u7b26|\u5f85\u8865\u5145|placeholder|tbd|todo)",
    r"\[\d+\]\s*[?;]\s*[\u4e00-\u9fffA-Za-z]",
    r"\u5e2e\u52a9\u8bfb\u8005\u7406\u89e3\u4e3a\u4ec0\u4e48\u8981\u505a",
    r"\u76f8\u5173\u7684\u7814\u7a76\u5bf9\u8c61\u4e0e\u8fb9\u754c\u6761\u4ef6",
    r"\u5c55\u793a\u7814\u7a76\u8def\u5f84\u7684\u53ef\u590d\u73b0\u6027",
    r"\u5bf9\u4e3b\u8981\u7ed3\u679c\u8fdb\u884c\u91cf\u5316\u89e3\u91ca\uff0c\u5e76\u8bf4\u660e\u53ef\u80fd\u7684\u8bef\u5dee\u6765\u6e90",
]

META_SOFT_PATTERNS = [
    r"(?:综上所述|总而言之|通过上述分析)，我们可以看到",
    r"本研究旨在通过.+来达到.+(?:目标|目的)",
    r"由于.+的原因，因此.+",
]


@dataclass(frozen=True)
class MetaScanResult:
    has_meta: bool
    fragments: list[str]


class MetaFirewall:
    def __init__(self) -> None:
        self._hard = [re.compile(p, re.IGNORECASE) for p in META_HARD_PATTERNS]
        self._soft = [re.compile(p, re.IGNORECASE) for p in META_SOFT_PATTERNS]

    def scan(self, text: str, *, max_hits: int = 8) -> MetaScanResult:
        fragments: list[str] = []
        for para in self._paragraphs(text):
            token = para.strip()
            if not token:
                continue
            if self._matches_hard(token) or self._matches_soft(token):
                fragments.append(token[:200])
                if len(fragments) >= max_hits:
                    break
        return MetaScanResult(has_meta=bool(fragments), fragments=fragments)

    def strip(self, text: str) -> str:
        if not text:
            return ""
        kept: list[str] = []
        for para in self._paragraphs(text):
            token = para.strip()
            if not token:
                continue
            if self._matches_hard(token):
                continue
            kept.append(token)
        return "\n\n".join(kept).strip()

    def build_rewrite_prompt(
        self,
        *,
        section_title: str,
        draft: str,
        hit_fragments: list[str],
    ) -> tuple[str, str]:
        fragments = [str(x).strip() for x in (hit_fragments or []) if str(x).strip()]
        frag_block = "\n".join(f"- {x}" for x in fragments[:8]) if fragments else "- (none)"
        system = (
            "You are a strict academic refiner.\n"
            "Task: REWRITE_WITHOUT_META.\n"
            "Output only cleaned reader-facing正文内容.\n"
            "Never output guidance, prompt residue, control fields, or self-referential process text.\n"
        )
        user = (
            "<task>REWRITE_WITHOUT_META</task>\n"
            f"<section_title>\n{section_title}\n</section_title>\n"
            "<meta_hits>\n"
            f"{frag_block}\n"
            "</meta_hits>\n"
            "<constraints>\n"
            "- Remove all meta-instructions and prompt residue.\n"
            "- Keep factual meaning and structure of the section.\n"
            "- Remove self-evaluative sentences such as '本段补充了…'、'围绕…展开'、'进一步补充了…'.\n"
            "- Remove bracket-semicolon residues such as '[1]；区块链…'.\n"
            "- Rewrite as direct factual prose for readers.\n"
            "- Do not mention these constraints in output.\n"
            "</constraints>\n"
            "<draft>\n"
            f"{draft}\n"
            "</draft>\n"
            "Return cleaned section text only."
        )
        return system, user

    def _matches_hard(self, token: str) -> bool:
        return any(p.search(token) for p in self._hard)

    def _matches_soft(self, token: str) -> bool:
        return any(p.search(token) for p in self._soft)

    @staticmethod
    def _paragraphs(text: str) -> list[str]:
        return [p for p in re.split(r"\n\s*\n+", str(text or "")) if str(p).strip()]
