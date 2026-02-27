"""Sections Catalog module.

This module belongs to `writing_agent` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SectionCatalogEntry:
    name: str
    description: str
    aliases: tuple[str, ...] = ()


SECTION_CATALOG: tuple[SectionCatalogEntry, ...] = (
    SectionCatalogEntry(
        name="引言",
        description=(
            "交代研究或项目背景、问题起点与报告范围，帮助读者理解为什么要做。"
            "可简述研究意义、目标与结构安排，强调本文解决的核心问题与边界。"
        ),
        aliases=("绪论",),
    ),
    SectionCatalogEntry(
        name="背景与问题定义",
        description=(
            "补充行业或场景背景，明确问题边界、关键概念与约束条件。"
            "可用典型案例或现状说明问题的现实性与迫切性，并指出当前痛点。"
        ),
        aliases=("研究背景", "问题定义"),
    ),
    SectionCatalogEntry(
        name="研究目的与意义",
        description=(
            "说明报告希望达成的目标及其学术或实践价值，强调贡献点与应用价值。"
            "可指出与现有工作的差异与预期影响，帮助读者把握研究价值。"
        ),
        aliases=("研究目标", "研究意义", "项目目标"),
    ),
    SectionCatalogEntry(
        name="范围与限制",
        description=(
            "明确报告覆盖的范围、排除的内容与前置假设，避免过度外推。"
            "说明时间、数据或资源限制，为后续结论提供合理边界。"
        ),
        aliases=("研究范围", "适用范围", "限制条件"),
    ),
    SectionCatalogEntry(
        name="术语与定义",
        description=(
            "统一关键术语、缩略语和专有名词的定义，确保后文表达一致。"
            "必要时给出对比解释或引用标准定义，降低歧义。"
        ),
        aliases=("术语定义", "名词解释"),
    ),
    SectionCatalogEntry(
        name="相关工作与文献综述",
        description=(
            "概述已有研究或同类系统，比较现有方案优缺点并指出不足与差距。"
            "需要体现关键观点的归纳和对比，明确本文工作的定位。"
        ),
        aliases=("相关工作", "文献综述", "研究现状"),
    ),
    SectionCatalogEntry(
        name="理论基础",
        description=(
            "介绍报告涉及的核心概念、理论模型、标准规范或算法原理。"
            "为后续设计与分析提供统一的理论语言与术语支撑。"
        ),
        aliases=("理论基础与关键概念",),
    ),
    SectionCatalogEntry(
        name="需求分析",
        description=(
            "从业务和用户角度明确功能需求与非功能需求，描述使用场景与约束。"
            "可细分为功能清单、性能/安全/可用性指标与边界条件。"
        ),
        aliases=("业务需求分析",),
    ),
    SectionCatalogEntry(
        name="用户与角色分析",
        description=(
            "描述目标用户、角色职责与使用场景，明确权限边界和关键诉求。"
            "可补充用户痛点与期望，支撑后续功能与交互设计。"
        ),
        aliases=("角色分析", "用户分析"),
    ),
    SectionCatalogEntry(
        name="业务流程",
        description=(
            "梳理现有或目标业务流程，说明关键节点与数据流转关系。"
            "可配合流程图展示主流程与异常分支，突出业务逻辑。"
        ),
        aliases=("流程分析", "业务流"),
    ),
    SectionCatalogEntry(
        name="用例分析",
        description=(
            "通过用例描述系统在不同场景下的交互与期望结果。"
            "包含参与者、前置条件、主流程和异常流程，体现可执行性。"
        ),
        aliases=("用例设计", "场景分析"),
    ),
    SectionCatalogEntry(
        name="需求确认与验收标准",
        description=(
            "给出需求验收口径与评估标准，明确交付边界与验收方式。"
            "可列出验收项、指标阈值与责任分工，便于后续验证。"
        ),
        aliases=("验收标准", "需求确认"),
    ),
    SectionCatalogEntry(
        name="可行性分析",
        description=(
            "评估技术、经济、时间与资源可行性，说明项目是否具备落地条件。"
            "可简要列出风险与对策，形成结论性判断。"
        ),
        aliases=("可行性研究",),
    ),
    SectionCatalogEntry(
        name="总体设计",
        description=(
            "给出系统或方案的整体架构与模块划分，说明关键流程与数据流。"
            "建议配合架构图或流程图解释设计思路与核心边界。"
        ),
        aliases=("系统设计", "总体架构"),
    ),
    SectionCatalogEntry(
        name="技术路线与方法",
        description=(
            "描述采用的方法论、技术路线或解决流程，强调关键步骤与策略。"
            "适用于算法、模型或流程性方案的整体说明。"
        ),
        aliases=("方法", "技术路线"),
    ),
    SectionCatalogEntry(
        name="数据来源与预处理",
        description=(
            "说明数据来源、采集方式、样本范围与清洗方法，明确数据质量。"
            "对实验或数据驱动项目尤为重要，可补充处理规则。"
        ),
        aliases=("数据准备", "数据处理"),
    ),
    SectionCatalogEntry(
        name="系统架构",
        description=(
            "细化总体设计中的架构层次（如表示层、业务层、数据层），说明模块交互。"
            "可描述技术选型、通信机制与部署拓扑，体现工程落地。"
        ),
        aliases=("架构设计",),
    ),
    SectionCatalogEntry(
        name="模块设计",
        description=(
            "逐一说明核心模块的职责、输入输出与关键逻辑。"
            "可用模块图、流程图或接口说明来组织结构与依赖关系。"
        ),
        aliases=("功能设计", "子模块设计"),
    ),
    SectionCatalogEntry(
        name="接口设计",
        description=(
            "说明模块间或系统对外接口的协议、字段与调用方式。"
            "可列出关键接口示例与异常处理规则，保证可集成性。"
        ),
        aliases=("API 设计", "服务接口"),
    ),
    SectionCatalogEntry(
        name="数据库设计",
        description=(
            "阐述数据模型、表结构与约束关系，明确主键、索引与关联方式。"
            "适合配合 ER 图与数据字典说明数据语义与约束。"
        ),
        aliases=("数据模型设计",),
    ),
    SectionCatalogEntry(
        name="数据字典",
        description=(
            "列出关键数据表、字段含义、类型与约束，便于理解数据结构。"
            "通常与数据库设计配套，作为实现与测试的重要依据。"
        ),
        aliases=("字段说明", "数据说明"),
    ),
    SectionCatalogEntry(
        name="算法与模型设计",
        description=(
            "描述关键算法或模型的核心思想、输入输出与参数设置。"
            "强调为何选择该方法，可结合伪代码或流程说明。"
        ),
        aliases=("模型设计", "算法设计"),
    ),
    SectionCatalogEntry(
        name="界面与交互设计",
        description=(
            "描述主要页面布局、交互逻辑和易用性考虑。"
            "可配合原型图或组件说明，体现用户路径与操作反馈。"
        ),
        aliases=("UI 设计", "交互设计"),
    ),
    SectionCatalogEntry(
        name="原型与视觉规范",
        description=(
            "说明界面风格、字体、色彩与组件规范，保证一致性。"
            "可补充原型链接或设计规则，便于后续实现与验收。"
        ),
        aliases=("视觉规范", "原型设计"),
    ),
    SectionCatalogEntry(
        name="安全设计",
        description=(
            "说明认证、授权、数据保护、日志审计等安全策略。"
            "明确风险场景与防护措施，必要时给出安全基线要求。"
        ),
        aliases=("安全方案", "安全策略"),
    ),
    SectionCatalogEntry(
        name="性能与可靠性设计",
        description=(
            "阐明性能目标、容量估算与高可用策略，说明关键指标口径。"
            "可包含缓存、并发控制、容灾与监控策略，体现稳定性。"
        ),
        aliases=("性能设计", "可靠性设计"),
    ),
    SectionCatalogEntry(
        name="实现与部署",
        description=(
            "介绍具体实现步骤、技术栈与部署方式，说明环境配置与依赖关系。"
            "适合包含关键实现细节与运行流程，突出可复现性。"
        ),
        aliases=("系统实现", "部署方案"),
    ),
    SectionCatalogEntry(
        name="实验与测试",
        description=(
            "说明实验或测试目标、方案、工具与指标，明确测试范围。"
            "可包含功能测试、性能测试与安全测试等分类说明。"
        ),
        aliases=("测试方案", "实验设计"),
    ),
    SectionCatalogEntry(
        name="测试用例与覆盖",
        description=(
            "给出关键测试用例、覆盖范围与预期结果，确保验证可追溯。"
            "可按功能/性能/安全分类说明，便于复现实验或验收。"
        ),
        aliases=("测试用例", "测试覆盖"),
    ),
    SectionCatalogEntry(
        name="结果与分析",
        description=(
            "展示实验或评估结果，结合图表进行对比与解释，得出结论性发现。"
            "强调结果与目标的一致性或差异性，并指出关键影响因素。"
        ),
        aliases=("结果分析", "效果评估"),
    ),
    SectionCatalogEntry(
        name="讨论",
        description=(
            "深入分析结果的原因、意义与局限，讨论可能的改进方向。"
            "适合补充对比与反思，强化论证深度。"
        ),
        aliases=("讨论与展望",),
    ),
    SectionCatalogEntry(
        name="风险与对策",
        description=(
            "识别项目可能面临的技术、资源、进度或安全风险，并提出可执行对策。"
            "可与可行性分析互补，说明风险缓释路径。"
        ),
        aliases=("风险分析",),
    ),
    SectionCatalogEntry(
        name="成本与效益分析",
        description=(
            "评估实施成本、维护成本与预期收益，提供量化或半量化依据。"
            "适合工程与管理类报告，体现投入产出逻辑。"
        ),
        aliases=("经济效益分析",),
    ),
    SectionCatalogEntry(
        name="项目管理与进度",
        description=(
            "说明项目组织、里程碑与时间安排，体现过程管理与资源协调。"
            "可配合甘特图或进度表，增强可执行性。"
        ),
        aliases=("实施计划", "进度计划"),
    ),
    SectionCatalogEntry(
        name="质量保证",
        description=(
            "说明质量标准、评审机制与持续改进方式，保证交付质量。"
            "可包括代码规范、评审流程与缺陷管理策略。"
        ),
        aliases=("质量控制", "质量管理"),
    ),
    SectionCatalogEntry(
        name="运维与监控",
        description=(
            "描述上线后监控指标、告警策略与运维流程，保障持续可用。"
            "包括备份恢复与故障处理机制，体现可维护性。"
        ),
        aliases=("运维方案", "监控方案"),
    ),
    SectionCatalogEntry(
        name="用户手册",
        description=(
            "面向终端用户的操作说明与注意事项，强调关键步骤与常见问题。"
            "可配合截图或流程说明，降低学习成本。"
        ),
        aliases=("使用说明", "操作指南"),
    ),
    SectionCatalogEntry(
        name="结论",
        description=(
            "总结核心工作与主要发现，突出关键贡献与实践价值。"
            "避免引入新内容，强调结论的可验证性与限制条件。"
        ),
        aliases=("总结", "总结与展望"),
    ),
    SectionCatalogEntry(
        name="参考文献",
        description=(
            "列出报告中引用或借鉴的文献、标准与资料，格式统一且可追溯。"
            "建议与正文引用一一对应，保证学术规范。"
        ),
        aliases=("参考资料",),
    ),
    SectionCatalogEntry(
        name="致谢",
        description=(
            "仅当用户明确要求时使用，用于感谢指导与支持（默认不输出）。"
            "应简洁克制，避免占用正文篇幅。"
        ),
        aliases=("鸣谢",),
    ),
    SectionCatalogEntry(
        name="附录",
        description=(
            "用于放置正文不宜展开的补充材料，如详细数据或原始记录（默认不输出）。"
            "仅在用户要求或模板明确包含时使用。"
        ),
        aliases=(),
    ),
)


def section_catalog_text(limit: int | None = None) -> str:
    lines: list[str] = []
    items = SECTION_CATALOG if not limit else SECTION_CATALOG[:limit]
    for item in items:
        lines.append(f"- {item.name}：{item.description}")
    return "\n".join(lines)


def find_section_description(title: str) -> str | None:
    t = (title or "").strip()
    if not t:
        return None
    for item in SECTION_CATALOG:
        if t == item.name:
            return item.description
        if any(alias for alias in item.aliases if alias and alias in t):
            return item.description
        if item.name in t:
            return item.description
    return None
