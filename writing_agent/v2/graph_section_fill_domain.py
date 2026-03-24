"""Fast-fill fallback helpers for section drafting."""

from __future__ import annotations

import re
from collections.abc import Callable


def generic_fill_paragraph(
    section: str,
    *,
    idx: int = 1,
    section_title: Callable[[str], str],
    is_reference_section: Callable[[str], bool],
    _find_section_description: Callable[[str], str],
) -> str:
    sec = (section_title(section) or "").strip() or "本节"
    if is_reference_section(sec):
        return ""
    if re.search(r"(关键词|key ?words?)", sec, flags=re.IGNORECASE):
        # 关键词章节只允许术语列表，不追加段落填充文本。
        return ""

    bibliometric_templates: list[tuple[re.Pattern[str], list[str]]] = [
        (
            re.compile(r"(摘要|abstract)", flags=re.IGNORECASE),
            [
                "本文以区块链赋能农村社会化服务为研究对象，基于文献计量与可视化方法识别研究演进脉络与核心主题。",
                "研究围绕发文趋势、合作网络与关键词聚类展开，重点揭示热点转移路径及其背后的治理议题。",
                "结果表明，该领域已由技术可行性讨论逐步转向治理协同与应用落地，研究前沿呈现跨学科融合趋势。",
            ],
        ),
        (
            re.compile(r"(引言|绪论|background|introduction)", flags=re.IGNORECASE),
            [
                "数字乡村建设推动了农村服务流程的数据化与协同化，但跨主体协作中仍存在信息孤岛、责任链不清和追溯成本高等问题。",
                "区块链以可追溯、不可篡改和多方共识机制，为农村社会化服务提供了可信数据底座与流程治理工具。",
                "在此背景下，系统梳理该主题的研究结构与热点演化，有助于明确后续理论突破点与政策实践方向。",
            ],
        ),
        (
            re.compile(r"(相关研究|文献综述|related)", flags=re.IGNORECASE),
            [
                "既有研究主要集中在农业供应链追溯、农村金融协同和基层治理数字化三条主线，并形成了较为稳定的议题群。",
                "部分文献强调技术架构与系统性能，另一些研究则转向制度设计、组织协同和应用场景适配问题。",
                "总体来看，当前研究在跨区域比较、长期效果评估与标准化指标构建方面仍存在改进空间。",
            ],
        ),
        (
            re.compile(r"(数据来源|检索策略|data source|search strategy)", flags=re.IGNORECASE),
            [
                "数据检索以主题词组合与布尔逻辑为基础，限定时间窗口、文献类型与语种范围，以保证样本可比性与可复核性。",
                "为降低检索噪声，采用同义词扩展与人工筛选结合的策略，剔除主题偏离或信息缺失样本。",
                "最终样本覆盖核心期刊与高相关研究，能够支持发文演进、合作网络与热点聚类的后续分析。",
            ],
        ),
        (
            re.compile(r"(发文量|时空分布|publication|temporal)", flags=re.IGNORECASE),
            [
                "从时间序列看，相关研究在近年进入持续增长阶段，节点年份附近出现明显的发文跃升现象。",
                "空间分布显示研究力量集中于数字农业基础较好的地区，区域间研究活跃度存在显著梯度差异。",
                "这种时空格局反映了政策推动、产业需求与技术扩散在不同地区的叠加效应。",
            ],
        ),
        (
            re.compile(r"(作者与机构|合作网络|collaboration)", flags=re.IGNORECASE),
            [
                "合作网络呈现“核心机构带动+外围扩散”的结构特征，头部团队在知识生产与议题设置中具有显著影响力。",
                "跨机构合作频次虽有提升，但网络密度仍偏低，说明高质量协同尚未形成广泛稳定的共同体。",
                "后续研究可通过多中心协同和数据共享机制，提升跨区域、跨学科联合研究的深度与持续性。",
            ],
        ),
        (
            re.compile(r"(关键词共现|聚类分析|cluster|co-occurrence)", flags=re.IGNORECASE),
            [
                "关键词共现网络显示“区块链”“农村治理”“供应链追溯”等节点处于核心位置，具有较高连接度与中介作用。",
                "聚类结果揭示主题从技术验证逐步拓展至治理机制、平台协同与应用绩效评估等方向。",
                "不同聚类之间存在交叉关联，表明该领域已由单点技术讨论转向系统性治理议题。",
            ],
        ),
        (
            re.compile(r"(热点演化|突现|burst|evolution)", flags=re.IGNORECASE),
            [
                "突现词分析表明，研究关注点经历了“底层技术—场景应用—治理协同”的阶段性迁移。",
                "近年新兴热点更多指向制度安排、数据治理与多主体协同，显示研究正在向应用深水区推进。",
                "热点演化路径提示后续研究应加强动态评估与场景对比，避免静态结论的过度外推。",
            ],
        ),
        (
            re.compile(r"(讨论|discussion)", flags=re.IGNORECASE),
            [
                "综合前述结果可见，技术可用性已不是唯一瓶颈，制度协同与组织执行能力成为影响落地效果的关键变量。",
                "在不同地区与应用场景中，治理目标、资源禀赋和监管要求差异明显，统一方案往往难以直接迁移。",
                "因此，建议在后续实践中采用分层治理与分阶段实施策略，以平衡效率、透明度与合规性要求。",
            ],
        ),
        (
            re.compile(r"(结论|conclusion)", flags=re.IGNORECASE),
            [
                "本研究从文献计量视角系统刻画了区块链与农村社会化服务交叉领域的研究结构、演进趋势与热点前沿。",
                "研究显示该领域正由技术导向向治理导向演进，跨学科协同与场景化评估将成为下一阶段重点。",
                "未来可进一步结合区域样本与纵向数据，提升结论的解释力、稳健性与实践可转化程度。",
            ],
        ),
    ]
    for pattern, templates in bibliometric_templates:
        if pattern.search(sec):
            return templates[(idx - 1) % len(templates)]

    # Do not turn section catalog guidance into reader-facing filler.
    # If no explicit domain template matches, prefer empty output over pseudo-success padding.

    return ""




def fast_fill_references(topic: str) -> str:
    _ = topic
    return ""


def fast_fill_section(
    section: str,
    *,
    min_paras: int,
    min_chars: int,
    min_tables: int,
    min_figures: int,
    section_title: Callable[[str], str],
    is_reference_section: Callable[[str], bool],
    generic_fill_paragraph: Callable[[str, int], str],
) -> str:
    _ = (
        section,
        min_paras,
        min_chars,
        min_tables,
        min_figures,
        section_title,
        is_reference_section,
        generic_fill_paragraph,
    )
    # Fast-draft fallback is intentionally disabled to avoid pseudo-success.
    return ""


