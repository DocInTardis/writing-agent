"""Diagram skill registry used by generation and rendering flows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiagramSkillProfile:
    key: str
    title: str
    aliases: tuple[str, ...]
    use_cases: tuple[str, ...]
    schema_hint: str
    guidance: str


@dataclass(frozen=True)
class DiagramSkillBundle:
    academic: DiagramSkillProfile
    selected: DiagramSkillProfile


ACADEMIC_PAPER_SKILL = DiagramSkillProfile(
    key="paper",
    title="论文图表技能",
    aliases=(),
    use_cases=("学术论文", "技术报告", "系统设计说明", "实验章节"),
    schema_hint="caption 应简洁、学术化，并突出对象、关系、阶段或指标。",
    guidance="优先使用学术化标题，避免装饰性节点，标签应准确、简洁并适合论文或报告直接使用。",
)


_SKILLS = (
    DiagramSkillProfile(
        key="flow",
        title="流程图技能",
        aliases=("flowchart", "流程图"),
        use_cases=("业务流程", "方法步骤", "处理链路", "机制说明"),
        schema_hint="flow.data: nodes[{id,label,subtitle,kind,lane}], edges[{from,to,label,style}]",
        guidance="适合表达真实流程，节点以步骤或动作命名，边应体现明确方向。",
    ),
    DiagramSkillProfile(
        key="architecture",
        title="架构图技能",
        aliases=("architecture_diagram", "arch", "架构图", "系统架构图"),
        use_cases=("系统架构", "模块框架", "分层设计", "平台能力"),
        schema_hint="architecture.data: lanes[{id,title}], nodes[{id,label,subtitle,kind,lane}], edges[{from,to,label,style}]",
        guidance="按分层或职责组织节点，突出稳定的模块边界与能力关系。",
    ),
    DiagramSkillProfile(
        key="er",
        title="ER 图技能",
        aliases=("er图", "实体关系图"),
        use_cases=("实体关系", "数据库模式", "数据建模", "主外键关系"),
        schema_hint="er.data: entities[{name,attributes}], relations[{left,right,label,cardinality}]",
        guidance="优先使用规范实体名，明确属性字段，并标注关系基数。",
    ),
    DiagramSkillProfile(
        key="sequence",
        title="时序图技能",
        aliases=("sequence_diagram", "时序图"),
        use_cases=("交互时序", "服务调用链", "消息流", "请求响应"),
        schema_hint="sequence.data: participants[], messages[{from,to,label,style}]",
        guidance="明确参与者角色，按交互顺序组织消息链路，保证时序清晰。",
    ),
    DiagramSkillProfile(
        key="state",
        title="状态图技能",
        aliases=("state_diagram", "uml_state", "状态图", "状态机图"),
        use_cases=("生命周期", "状态迁移", "审批流状态", "任务状态机"),
        schema_hint="state.data: states[{id,label,kind}], transitions[{from,to,label}]",
        guidance="突出稳定状态与合法迁移，必要时标明开始态和结束态。",
    ),
    DiagramSkillProfile(
        key="class",
        title="类图技能",
        aliases=("class_diagram", "uml_class", "类图"),
        use_cases=("领域模型", "面向对象设计", "类关系", "接口抽象"),
        schema_hint="class.data: classes[{name,attributes[],methods[]}], relations[{from,to,label,kind}]",
        guidance="保持类职责清晰，区分属性与方法，并标注关系语义。",
    ),
    DiagramSkillProfile(
        key="gantt",
        title="Gantt 图技能",
        aliases=("gantt_chart", "甘特图", "gantt图"),
        use_cases=("项目计划", "实施排期", "里程碑安排", "研发节奏"),
        schema_hint="gantt.data: tasks[{task,start,end,owner,status}]",
        guidance="任务应有明确顺序，并清楚标明起止时间、负责人或状态。",
    ),
    DiagramSkillProfile(
        key="mindmap",
        title="思维导图技能",
        aliases=("mind_map", "思维导图", "脑图"),
        use_cases=("概念拆解", "主题发散", "论文章节脑图", "知识结构"),
        schema_hint="mindmap.data: center, branches[{label,children[]}]",
        guidance="围绕一个中心主题展开，一级分支应简洁，必要时补充二级节点。",
    ),
    DiagramSkillProfile(
        key="quadrant",
        title="四象限图技能",
        aliases=("quadrant_chart", "matrix_2x2", "四象限图", "四象限"),
        use_cases=("优先级矩阵", "策略分布", "风险评估", "方案定位"),
        schema_hint="quadrant.data: x_axis, y_axis, items[{label,x,y,quadrant}]",
        guidance="在清晰的二维坐标中放置少量关键事项，突出四象限定位。",
    ),
    DiagramSkillProfile(
        key="radar",
        title="雷达图技能",
        aliases=("radar_chart", "雷达图"),
        use_cases=("能力画像", "多维评估", "指标对比", "模型特征"),
        schema_hint="radar.data: axes[], series[{name,values[]}]",
        guidance="维度设置应均衡，数值尽量归一化，便于多维对比阅读。",
    ),
    DiagramSkillProfile(
        key="scatter",
        title="散点图技能",
        aliases=("scatter_plot", "散点图"),
        use_cases=("相关性分析", "样本分布", "性能定位", "实验点云"),
        schema_hint="scatter.data: x_label, y_label, points[{label,x,y,group}]",
        guidance="使用数值坐标与精简标签，突出聚类、离群点或相关关系。",
    ),
    DiagramSkillProfile(
        key="timeline",
        title="时间线技能",
        aliases=("时间线",),
        use_cases=("研究路线", "里程碑", "演化历程", "阶段推进"),
        schema_hint="timeline.data: events[{time,label}]",
        guidance="按时间顺序组织里程碑，用简短事件名突出关键阶段。",
    ),
    DiagramSkillProfile(
        key="bar",
        title="柱状图技能",
        aliases=("bar_chart", "柱状图"),
        use_cases=("对比分析", "排名统计", "类别分布", "指标比较"),
        schema_hint="bar.data: labels[], values[]",
        guidance="类别应可横向比较，配合清晰数值展示差异。",
    ),
    DiagramSkillProfile(
        key="line",
        title="折线图技能",
        aliases=("line_chart", "折线图"),
        use_cases=("趋势变化", "时间序列", "增长曲线", "性能演化"),
        schema_hint="line.data: labels[], series[{name,values[]}]",
        guidance="标签应有顺序，数列应连续，用于呈现趋势变化。",
    ),
    DiagramSkillProfile(
        key="pie",
        title="饼图技能",
        aliases=("pie_chart", "饼图"),
        use_cases=("组成占比", "份额结构", "资源分配", "主题比例"),
        schema_hint="pie.data: segments[{label,value}]",
        guidance="分块数量不宜过多，应突出整体与部分的构成关系。",
    ),
    DiagramSkillProfile(
        key="heatmap",
        title="热力图技能",
        aliases=("heatmap_chart", "热力图"),
        use_cases=("强度分布", "矩阵热区", "相关热点", "章节密度"),
        schema_hint="heatmap.data: rows[], cols[], values[][]",
        guidance="使用紧凑矩阵配合清晰行列标签，突出强度或热点分布。",
    ),
    DiagramSkillProfile(
        key="funnel",
        title="漏斗图技能",
        aliases=("funnel_chart", "漏斗图"),
        use_cases=("流程转化", "筛选收敛", "候选缩减", "阶段留存"),
        schema_hint="funnel.data: stages[{label,value}]",
        guidance="用递减阶段展示收敛过程，标签和数值要清楚。",
    ),
    DiagramSkillProfile(
        key="sankey",
        title="桑基图技能",
        aliases=("sankey_chart", "桑基图"),
        use_cases=("流向分析", "资源转移", "路径分流", "输入输出分配"),
        schema_hint="sankey.data: nodes[], links[{source,target,value}]",
        guidance="突出少量关键节点之间的主要流向，保持连线清晰可读。",
    ),
    DiagramSkillProfile(
        key="swot",
        title="SWOT 图技能",
        aliases=("swot_chart", "swot图", "SWOT图"),
        use_cases=("战略分析", "方案评估", "项目复盘", "竞争定位"),
        schema_hint="swot.data: strengths[], weaknesses[], opportunities[], threats[]",
        guidance="将要点分布到 SWOT 四个象限中，每个象限保持简洁不过载。",
    ),
)

_BY_KEY = {skill.key: skill for skill in _SKILLS}
_ALIAS_TO_KEY = {alias: skill.key for skill in _SKILLS for alias in skill.aliases}


def allowed_diagram_types() -> set[str]:
    return set(_BY_KEY)


def allowed_diagram_aliases() -> set[str]:
    return set(_ALIAS_TO_KEY)


def normalize_diagram_kind(kind: str | None) -> str:
    raw = str(kind or "").strip().lower()
    if not raw:
        return "flow"
    return _ALIAS_TO_KEY.get(raw, raw if raw in _BY_KEY else "flow")


def get_diagram_skill(kind: str | None) -> DiagramSkillProfile:
    return _BY_KEY[normalize_diagram_kind(kind)]


def get_diagram_skill_bundle(kind: str | None) -> DiagramSkillBundle:
    return DiagramSkillBundle(academic=ACADEMIC_PAPER_SKILL, selected=get_diagram_skill(kind))


__all__ = [name for name in globals() if not name.startswith("__")]
