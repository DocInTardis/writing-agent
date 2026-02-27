"""
Prompt管理模块 - 集中管理所有LLM提示词

采用最佳实践:
1. 模板化: 使用Jinja2模板引擎支持动态参数
2. 分层管理: System/User/Few-shot示例分离
3. 版本控制: 支持prompt版本追踪
4. 类型安全: 使用dataclass定义参数结构
"""

from dataclasses import dataclass
from typing import Optional
from jinja2 import Template


@dataclass
class PromptConfig:
    """Prompt配置基类"""
    temperature: float = 0.2
    max_tokens: Optional[int] = None


# ========== Planner Agent ==========

PLANNER_SYSTEM = """你是严谨的报告规划Agent，只输出JSON，不要Markdown，不要多余文字。

Schema: {title:string,total_chars:number,sections:[{title:string,target_chars:number,key_points:[string],context_from_previous:boolean,figures:[{type,caption}],tables:[{caption,columns}],evidence_queries:[string]}]}.

规则：
- 章节标题必须严格来自给定列表，不允许新增/改名
- 字数总和约等于total_chars
- 不要摘要/关键词/建议/附录/致谢
- 最后一节必须是"参考文献"
- 请为每个章节给出2-5条要点与1-3条检索关键词
- 如适合给出1个图或表

重要：
- key_points应为写作方向指导，使用名词短语或主题词，避免'明确/展示/确保'等动词开头
- context_from_previous标记该章节是否需要前章内容作为上下文（如'实现'依赖'设计'），默认false"""

PLANNER_USER_TEMPLATE = Template("""报告标题：{{ title }}
总字数目标：{{ total_chars }}
章节列表：
{{ section_list }}

用户需求：
{{ instruction }}

请输出规划JSON。""")

PLANNER_FEW_SHOT = """示例：
{
  "title":"工资管理系统",
  "total_chars":2000,
  "sections":[
    {"title":"需求分析","target_chars":420,"key_points":["用户角色与使用场景","薪酬核算流程与规则","数据安全与审计要求"],"figures":[{"type":"flow","caption":"业务流程图"}],"tables":[{"caption":"需求清单","columns":["编号","需求","优先级"]}],"evidence_queries":["工资管理 系统 需求","薪资管理 非功能需求"]}
  ]
}"""

@dataclass
class PlannerConfig(PromptConfig):
    temperature: float = 0.3  # 提升多样性


# ========== Analysis Agent ==========

ANALYSIS_SYSTEM = """你是需求分析Agent，只输出JSON，不要Markdown，不要多余文字。

Schema: {topic:string,doc_type:string,audience:string,style:string,keywords:[string],must_include:[string],avoid_sections:[string],constraints:[string],questions:[string],doc_structure:string}.

规则：
- 尽量提取明确需求
- 不确定的放到questions
- 不要臆造内容
- doc_structure说明文档整体结构特点，如'周报格式，按时间线组织'、'技术方案，问题-分析-解决'等"""

ANALYSIS_USER_TEMPLATE = Template("""用户需求：
{{ instruction }}

已存在文本（节选）：
{{ excerpt }}

请输出分析JSON。""")

@dataclass
class AnalysisConfig(PromptConfig):
    temperature: float = 0.15


# ========== Writer Agent ==========

WRITER_SYSTEM_BASE = """????????????Agent????????????????

???????
1. ???????????????????
2. ????/????????????????
3. ????????????????????????10%?
4. ??????????????????

???????
- ???NDJSON???????JSON???????????????
- Schema????????????
  {"section_id":string,"block_id":string,"type":"paragraph"|"list"|"table"|"figure"|"reference","text"?:string,"items"?:[string],"caption"?:string,"columns"?:[string],"rows"?:[[string]]}
- section_id ?????????? section_id ??
- paragraph ?? text
- list ?? items ????????????
- table ?? caption/columns/rows?figure ?? caption
- reference ????????????????
- ???? Markdown ??/??/????"""


WRITER_IMPORTANT_NOTE = """
【重要说明】
- '章节规划'中的'本章要点'是写作方向指导，不是待填充的句式模板
- 必须根据要点自行展开成完整段落，包含具体定义、步骤、约束、边界条件等
- 禁止照搬要点文字，禁止输出类似'明确XXX'、'展示XXX'、'确保XXX'这种指令性语句
- 必须写成完整的学术叙述文本，而非任务清单或提纲

示例对比：
❌ 错误：明确项目目标与阶段性成果，展示各阶段的工作进度。
✓ 正确：本周项目推进主要围绕需求分析和架构设计两个阶段。需求分析阶段完成了核心功能清单梳理，包括用户管理、权限控制等5个模块；架构设计阶段确定了前后端分离方案，采用React+FastAPI技术栈..."""

WRITER_USER_TEMPLATE = Template("""????????
section_id?{{ section_id }}
???????{{ section_title }}
{{ plan_hint }}

???????
???????{{ doc_title }}
{{ analysis_summary }}
{% if previous_content %}
?????????
{{ previous_content }}
{% endif %}

{% if rag_context %}
????????
{{ rag_context }}
{% endif %}

????????????NDJSON??""")


@dataclass
class WriterConfig(PromptConfig):
    temperature: float = 0.2
    stream: bool = True


# ========== Reference Agent ==========

REFERENCE_SYSTEM = """你是文献管理Agent，负责生成参考文献列表。

格式要求：
- 使用国标GB/T 7714-2015格式
- 自动编号[1] [2]...
- 包含作者、标题、出处、年份、URL（如有）
- 按引用顺序排列"""

REFERENCE_USER_TEMPLATE = Template("""已引用资料：
{{ sources }}

请生成规范的参考文献列表。""")


# ========== Revision Agent ==========

REVISION_SYSTEM = """你是内容修订Agent，负责根据用户反馈修改文档。

修订原则：
1. 准确理解用户意图，精准定位需修改部分
2. 保持文档整体风格一致
3. 修改范围最小化，避免不必要的改动
4. 保留原有正确内容"""

REVISION_USER_TEMPLATE = Template("""【原始内容】
{{ original_text }}

【用户反馈】
{{ feedback }}

请输出修订后的内容。""")

@dataclass
class RevisionConfig(PromptConfig):
    temperature: float = 0.15


# ========== Prompt 构建器 ==========

class PromptBuilder:
    """统一的Prompt构建接口"""
    
    @staticmethod
    def build_planner_prompt(title: str, total_chars: int, sections: list[str], instruction: str) -> tuple[str, str]:
        """构建Planner的system和user prompt"""
        system = PLANNER_SYSTEM + "\n" + PLANNER_FEW_SHOT
        section_list = "\n".join([f"- {s}" for s in sections])
        user = PLANNER_USER_TEMPLATE.render(
            title=title,
            total_chars=total_chars,
            section_list=section_list,
            instruction=instruction
        )
        return system, user
    
    @staticmethod
    def build_analysis_prompt(instruction: str, excerpt: str) -> tuple[str, str]:
        """构建Analysis的system和user prompt"""
        system = ANALYSIS_SYSTEM
        user = ANALYSIS_USER_TEMPLATE.render(
            instruction=instruction,
            excerpt=excerpt
        )
        return system, user
    
    @staticmethod
    def build_writer_prompt(
        section_title: str,
        plan_hint: str,
        doc_title: str,
        analysis_summary: str,
        section_id: str,
        previous_content: Optional[str] = None,
        rag_context: Optional[str] = None
    ) -> tuple[str, str]:
        """构建Writer的system和user prompt"""
        system = WRITER_SYSTEM_BASE + "\n" + WRITER_IMPORTANT_NOTE
        user = WRITER_USER_TEMPLATE.render(
            section_title=section_title,
            section_id=section_id,
            plan_hint=plan_hint,
            doc_title=doc_title,
            analysis_summary=analysis_summary,
            previous_content=previous_content,
            rag_context=rag_context
        )
        return system, user
    
    @staticmethod
    def build_reference_prompt(sources: list[dict]) -> tuple[str, str]:
        """构建Reference的system和user prompt"""
        system = REFERENCE_SYSTEM
        sources_text = "\n\n".join([
            f"[{i+1}] {s.get('title', '')} {s.get('url', '')}"
            for i, s in enumerate(sources)
        ])
        user = REFERENCE_USER_TEMPLATE.render(sources=sources_text)
        return system, user
    
    @staticmethod
    def build_revision_prompt(original_text: str, feedback: str) -> tuple[str, str]:
        """构建Revision的system和user prompt"""
        system = REVISION_SYSTEM
        user = REVISION_USER_TEMPLATE.render(
            original_text=original_text,
            feedback=feedback
        )
        return system, user


# ========== 配置获取器 ==========

def get_prompt_config(agent_type: str) -> PromptConfig:
    """获取指定Agent的Prompt配置"""
    configs = {
        "planner": PlannerConfig(),
        "analysis": AnalysisConfig(),
        "writer": WriterConfig(),
        "reference": PromptConfig(temperature=0.1),
        "revision": RevisionConfig(),
    }
    return configs.get(agent_type, PromptConfig())

# --- JSON-only protocol overrides (appended) ---
PLANNER_FEW_SHOT = """Example:
{
  \"title\":\"项目周报\",
  \"total_chars\":2000,
  \"sections\":[
    {\"title\":\"背景\",\"target_chars\":300,\"key_points\":[\"项目现状\",\"关键里程碑\"],\"figures\":[],\"tables\":[],\"evidence_queries\":[]},
    {\"title\":\"本周工作\",\"target_chars\":900,\"key_points\":[\"研发进度\",\"联调测试\",\"风险处理\"],\"figures\":[{\"type\":\"flow\",\"caption\":\"本周交付流程\",\"nodes\":[\"需求\",\"设计\",\"开发\",\"测试\",\"发布\"]}],\"tables\":[{\"caption\":\"任务清单\",\"columns\":[\"任务\",\"负责人\",\"状态\",\"完成率\"],\"row_budget\":6}],\"evidence_queries\":[\"项目管理 周报\",\"研发进度 风险管理\"]},
    {\"title\":\"问题与风险\",\"target_chars\":400,\"key_points\":[\"阻塞项\",\"影响范围\",\"应对方案\"],\"figures\":[],\"tables\":[{\"caption\":\"风险清单\",\"columns\":[\"风险\",\"影响\",\"概率\",\"应对\"],\"row_budget\":4}],\"evidence_queries\":[]},
    {\"title\":\"下周计划\",\"target_chars\":300,\"key_points\":[\"功能收尾\",\"性能优化\",\"跨部门协作\"],\"figures\":[],\"tables\":[],\"evidence_queries\":[]},
    {\"title\":\"参考文献\",\"target_chars\":100,\"key_points\":[\"引用列表\"],\"figures\":[],\"tables\":[],\"evidence_queries\":[\"周报 写作 参考文献\"]}
  ]
}"""

WRITER_SYSTEM_BASE = """你是严格的写作Agent，只输出JSON，不要Markdown或自然语言说明。

输出规则：
1. 仅输出 NDJSON：每一行必须是一个完整 JSON 对象。
2. 禁止在 JSON 之外输出任何字符。
3. 至少输出 4 个段落块，单段不少于 3 句。
4. 结构必须与 section_id 匹配。

Schema:
{\"section_id\":string,\"block_id\":string,\"type\":\"paragraph\"|\"list\"|\"table\"|\"figure\"|\"reference\",\"text\"?:string,\"items\"?:[string],\"caption\"?:string,\"columns\"?:[string],\"rows\"?:[[string]]}

约束：
- paragraph 必须包含 text
- list 必须包含 items
- table 必须包含 caption/columns/rows
- figure 必须包含 caption
- reference 仅在参考文献章节出现
"""
