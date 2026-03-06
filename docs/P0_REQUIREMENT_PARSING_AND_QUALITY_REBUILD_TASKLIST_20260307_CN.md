# P0 问题根因与重构任务清单（2026-03-07）

## 1. 文档目的

这份文档用于固化当前系统在“需求解析、规划分发、质量判定、兜底策略、图表与参考文献”方面的 P0 级问题，明确：

- 已确认根因（含代码证据）
- 对当前 8 条建议的结论
- 一份可直接执行的任务清单（不分阶段）
- 最终验收标准（避免“伪成功”）

---

## 2. P0 根因（已确认）

### 2.1 规划跑偏（周报化）根因

- 根因 A：Planner few-shot 本身是周报模板，强烈诱导输出 `This Week Work / Next Week Plan`。
  - 证据：`writing_agent/v2/prompts.py:41-52`
- 根因 B：存在周报关键字触发的默认大纲分支。
  - 证据：`writing_agent/v2/graph_runner.py:305-309`
- 根因 C：`FAST_PLAN` 分支会使用英文周报类 fallback sections。
  - 证据：`writing_agent/v2/graph_runner_runtime.py:124-134`
- 运行证据：实际 trace 中 struct_plan 已出现周报章节，说明问题发生在规划环节，不是后处理误伤。
  - 证据：`deliverables/cnki_trace_workflow_20260306_230721/stage_summary.json`
  - 证据：`deliverables/cnki_trace_workflow_20260306_230721/raw_events.jsonl`

### 2.2 学术结构缺失（摘要/关键词）根因

- 根因：系统把 `摘要/关键词` 设为 disallowed，后处理中会直接剔除。
  - 证据：`writing_agent/v2/graph_runner.py:252-275`
  - 证据：`writing_agent/v2/graph_runner_runtime.py:676`

### 2.3 “看起来成功但质量不达标”（伪成功）根因

- 根因 A：生成失败或不足时，语义兜底会自动补泛化文本，掩盖真实失败。
  - 证据：`writing_agent/v2/graph_runner_runtime.py:650-694`
- 根因 B：服务层 graph 失败会 fallback 到 single-pass，指标上可能“恢复”，但不保证结构和学术质量达标。
  - 证据：`writing_agent/web/services/generation_service.py:628-684`

### 2.4 revise 路径弱门槛提交根因

- 根因：`revise_doc` 在 fallback 分支中只要结果非空就写回，缺少强制质量 gate。
  - 证据：`writing_agent/web/services/generation_service.py:870-907`

### 2.5 图表能力“名义存在、实际未强约束”根因

- 根因：`ensure_media_markers` 统计 marker 但不补写，`append_lines` 永远为空，等价 no-op。
  - 证据：`writing_agent/v2/graph_section_draft_domain.py:320-337`

### 2.6 参考文献质量退化根因

- 根因：保守修复模式下 `target_unique` 可降至 1，导致“有参考文献标题但质量极低”。
  - 证据：`writing_agent/web/app_v2_textops_runtime_part2.py:785-824`

### 2.7 死代码 / 无效实现放大不确定性

- 明确死代码：`return` 后仍存在一整段旧逻辑，永远不会执行。
  - 证据：`writing_agent/web/domains/revision_edit_runtime_domain.py:2273`（后续段落不可达）
- 占位实现：模板抽取与偏好抽取多个函数返回空/原样，仍被上层流程依赖，造成“看似有 AI 解析，实则无效”。
  - 证据：`writing_agent/web/app_v2_textops_runtime_part1.py:545-602`
  - 调用点证据：`writing_agent/web/api/template_flow.py:177-193,311-323`

### 2.8 Prompt 语言与模板单一化根因

- 根因 A：Prompt Registry 的 planner/analysis/writer 主提示词均为英文，且缺少“按任务类型/语言域切换”的机制。
  - 证据：`writing_agent/v2/prompts.py:34-89`
- 根因 B：Planner few-shot 固化为英文周报示例，导致计划产物被模板牵引。
  - 证据：`writing_agent/v2/prompts.py:41-52`
- 根因 C：当规划失败或快速路径触发时，fallback sections 与 fallback paragraphs 以英文模板为主。
  - 证据：`writing_agent/v2/graph_runner_runtime.py:127-154`
  - 证据：`writing_agent/v2/graph_section_draft_domain.py:355-367`
- 根因 D：当前缺少 Prompt 的版本化、灰度发布、线上评测与回滚机制，问题 Prompt 难以及时隔离。

---

## 3. 对 8 条建议与补充建议的结论

### 3.1 先扫 dead code，再做需求识别算法；加“用户确定”按钮

- 结论：同意。
- 补充：
  - 先清不可达代码与占位实现，再做解析优化，避免“算法升级被脏路径污染”。
  - “用户确定”应插在 `planner 完成 -> writer 开始` 之间，新增 `plan_confirm` gate。
  - 现有确认机制可复用（当前用于高风险编辑确认）。
    - 参考：`writing_agent/web/services/generation_service.py:426-450`

### 3.2 质量要求重构，建立知网高质量默认模板

- 结论：同意。
- 补充：
  - 现有质量阈值偏通用，不足以支撑“毕设/知网风格”默认交付。
  - 需引入 `academic_cnki_default` profile，并前置到计划与写作阶段，而非仅靠导出后检查。

### 3.3 二级章节问题要优先保证解析和分发正确

- 结论：同意。
- 补充：
  - 二级章节缺失并非单点 bug，而是“解析偏差 -> 规划偏差 -> 写作偏差 -> 兜底掩盖”的链路问题。

### 3.4 兜底策略是否保留

- 结论：保留“基础设施兜底”，移除“语义伪装兜底”。
- 原则：
  - 可保留：网络超时、引擎故障时的 failover。
  - 必须移除：自动灌入通用段落使结果看起来完成。

### 3.5 图表功能实现并对齐最佳实践

- 结论：同意，且必须从 marker 升级为结构化对象。
- 参考依据（官方/主流规范）：
  - OpenXML 表格插入：<https://learn.microsoft.com/en-us/office/open-xml/word/how-to-add-tables-to-word-processing-documents>
  - OpenXML 图片插入：<https://learn.microsoft.com/en-us/office/open-xml/word/how-to-insert-a-picture-into-a-word-processing-document>
  - OpenXML 验证器：<https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.validation.openxmlvalidator>
  - ECMA-376（DOCX 标准）：<https://www.ecma-international.org/publications-and-standards/standards/ecma-376/>
  - python-docx 图片：<https://python-docx.readthedocs.io/en/latest/user/shapes.html>

### 3.6 参考文献标准重构；状态改为 成功/失败/中断；不要伪成功

- 结论：同意。
- 补充：
  - “possible”不应默认可放行，应显式进入“需人工确认”或失败态。
  - 终态统一为：`success | failed | interrupted`，并附结构化 `failure_reason`。

### 3.7 需求解析问题过大（同 1）

- 结论：同意，且应作为最高优先工作线。

### 3.8 revise 是什么

- 结论：
  - `revise` 是“编辑模式”，优先做局部原子改写；失败时可选回退到全文改写。
  - 若 `allow_unscoped_fallback=true`，局部失败后会走全文 fallback。
  - 当前问题不在机制本身，而在 fallback 写回门槛偏低，导致质量和可信度下降。

### 3.9 Prompt 需按用户输入/需求动态切换，并建立 Prompt 管理机制

- 结论：同意，且这是需求解析稳定性的核心基础设施。
- 补充：
  - Prompt 不能再“一套系统词跑所有任务”，必须依据 `任务类型 + 目标文体 + 语言域 + 风险等级` 路由。
  - 对“学术论文、技术报告、周报、改写、格式化、提纲抽取”应分别使用专用 prompt 套件。
  - Prompt 管理必须具备：版本号、owner、变更记录、A/B 开关、离线评测分数、线上回滚开关。
  - Prompt 失效时应进入受控降级（fail-fast + 标记失败原因），不能静默切回泛化模板。

---

## 4. `revise` 工作原理（便于面试解释）

1. 解析选区锚点（start/end/text 或文本定位），构造局部上下文窗口。  
   - 证据：`writing_agent/web/domains/revision_edit_runtime_domain.py:1953-1974`
2. 生成局部改写指令，要求仅返回 replace 操作 JSON。  
   - 证据：`writing_agent/web/domains/revision_edit_runtime_domain.py:1751-1801`
3. 两次尝试（初次 + refine），失败则返回错误码，不做越界写入。  
   - 证据：`writing_agent/web/domains/revision_edit_runtime_domain.py:2010-2061`
4. 原子替换并做 marker/hash 一致性校验，确保不改选区外文本。  
   - 证据：`writing_agent/web/domains/revision_edit_runtime_domain.py:2118-2165`
5. 局部失败后是否全量 fallback，由 `allow_unscoped_fallback` 控制。  
   - 证据：`writing_agent/web/services/generation_service.py:864-875`

---

## 5. 重构任务清单（不分阶段，按执行项列出）

- [x] 删除 planner 周报 few-shot，替换为中文学术论文/技术报告样例（至少 2 组，含二级章节）。
- [x] 删除/禁用所有周报 heuristics 默认路径（包括 `_default_outline_from_instruction` 周报分支和相关 fallback sections）。
- [x] 建立 Prompt 路由器：根据 `intent/doc_type/language/quality_profile` 选择 planner/analysis/writer/revise prompt 版本。
- [x] 为学术、技术报告、周报、局部改写、全文改写分别提供独立 prompt 套件，禁止共享同一 few-shot。
- [x] 建立 Prompt Registry 元数据：`prompt_id/version/owner/created_at/updated_at/changelog/status(tags)`。
- [x] 建立 Prompt 发布治理：灰度开关、A/B 对比、线上异常自动熔断、单版本一键回滚。
- [x] 建立 Prompt 评测流水线：离线基准（结构正确率、中文率、章节层级正确率、引用合规率）达标后才能上线。
- [x] 在 trace 中记录本次命中的 prompt 版本与路由决策依据（用于复盘和面试可解释性）。
- [x] 清理 `revise` 域中的不可达代码，保留单一路径实现并补充单元测试覆盖。
- [x] 清理模板/偏好抽取占位实现：未实现就显式报错，不允许“静默返回空对象”。
- [x] 新增 `plan_confirm` 节点与 API/UI：在 plan 下发 writer 前要求用户确认（通过/终止/评分）。
- [x] 新增需求解析 strict schema 与字段置信度评分；低置信度必须触发澄清问题，不允许直接写作。
- [x] 新增“解析正确性守卫”：章节语言、层级、标题域、关键词一致性不通过则直接 failed。
- [x] 引入 `academic_cnki_default` 质量模板（默认启用），写入 generation_prefs。
- [x] 将摘要/关键词从 disallowed 集移除，并在学术模板中设为必需章节。
- [x] 重建章节深度约束：一级/二级/三级最小数量与分布规则在 plan 阶段强制满足。
- [x] 将“语义灌水兜底”改为 fail-fast：禁止 `_generic_fill_paragraph` 在生产路径伪造可交付正文。
- [x] 保留基础设施兜底但标注恢复来源：`engine_failover=true`，并进入 “需复核” 状态而非 success。
- [x] 统一终态状态机：`success | failed | interrupted`，移除隐式“恢复成功即成功”语义。
- [x] 终态必须附 `failure_reason` 和 `quality_snapshot`，前端展示可追踪失败原因。
- [x] 参考文献从“可补种子”改为“可核验来源驱动”：不足/重复/未核验直接 failed。
- [x] 禁止 conservative 模式将 `target_unique` 降到 1；最低条数由质量模板硬约束。
- [x] 图表改为 DocIR 强类型节点（table/figure object），禁止仅依赖文本 marker。
- [x] 写作阶段增加“图表引用一致性校验”：文中提及图表必须有实体对象，编号连续。
- [x] 导出前增加 OpenXML 结构校验与对象完整性校验，不通过直接 failed。
- [x] 新增端到端回归集：复杂中文 prompt、章节深度、图表、参考文献、revise 局部编辑、导出可打开性。
- [x] 更新 trace 报告格式：必须记录 planner JSON、每节点 DocIR、质量 gate 决策与最终终态。

---

## 6. 验收标准（完成定义）

- 规划侧：
  - 任意中文学术题目，plan 结果不得出现周报章节词（如 This Week Work / Next Week Plan）。
  - 二级章节数量、命名域、语言域与用户需求一致。
  - Prompt 路由日志可追溯：每次生成必须可查询命中的 `prompt_id/version` 与路由原因。

- 质量侧：
  - 学术模板下，摘要、关键词、参考文献为硬门槛。
  - 质量不达标时必须 `failed`，不可输出“看似完整”的 success 文档。
  - 中文场景下，正文中文率、标题中文率达到阈值（阈值由质量模板定义），否则直接失败。

- Prompt 治理侧：
  - 新 prompt 上线前，离线评测通过率达到发布门槛后方可灰度。
  - 灰度期间若关键指标下降（结构正确率、中文率、引用合规率、失败率）超阈值，自动回滚。
  - 任意线上问题可在分钟级回滚到上一个稳定 prompt 版本。

- 状态侧：
  - 所有生成任务终态严格属于 `success | failed | interrupted`。
  - 每次失败必须带可读 `failure_reason`，并可追溯到节点与规则。

- revise 侧：
  - 局部编辑只改选区，锚点不一致必须失败并返回错误码。
  - 全文 fallback 仅在显式允许下启用，并保留诊断元数据。

- 导出侧：
  - DOCX 连续 20 次抽样导出均可直接打开，无“发现无法读取内容”弹窗。
  - 图表、目录、引用在 Word 中结构可导航、编号一致。

---

## 7. 备注

- 本文档为执行基线；后续每完成一项任务应在对应条目前打勾，并附提交哈希与测试证据路径。

---

## 8. 任务账本（27 项）

| ID | 任务描述 | 代码位置（主） | 依赖 | 状态 | 证据 |
|---|---|---|---|---|---|
| T01 | 删除 planner 周报 few-shot，替换中文学术/技术报告示例 | `writing_agent/v2/prompts.py` | 无 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T02 | 删除/禁用周报 heuristics 与相关 fallback sections | `writing_agent/v2/graph_runner.py`, `writing_agent/v2/graph_runner_runtime.py` | T01 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T03 | 建立 Prompt 路由器（intent/doc_type/language/quality_profile） | `writing_agent/v2/prompts.py`, `writing_agent/v2/graph_runner.py` | T01,T02 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T04 | 学术/技术报告/周报/局部改写/全文改写 Prompt 套件拆分 | `writing_agent/v2/prompts.py`, `writing_agent/web/domains/revision_edit_runtime_domain.py` | T03 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T05 | Prompt Registry 元数据落地（id/version/owner/changelog/status） | `writing_agent/v2/prompt_registry.py`, `.data/prompt_registry/prompts.json` | T03 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T06 | Prompt 发布治理（灰度/A-B/熔断/回滚） | `writing_agent/v2/prompt_registry.py`, `writing_agent/v2/graph_runner.py` | T05 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T07 | Prompt 评测流水线（离线基准门禁） | `scripts/`, `tests/`, `deliverables/` | T03,T04,T05 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T08 | trace 记录命中 prompt 版本与路由依据 | `writing_agent/v2/graph_runner_runtime.py`, `writing_agent/web/services/generation_service.py` | T03,T05 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T09 | 清理 revise 不可达代码并补测 | `writing_agent/web/domains/revision_edit_runtime_domain.py`, `tests/` | 无 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T10 | 清理模板/偏好抽取占位实现（禁止静默空返回） | `writing_agent/web/app_v2_textops_runtime_part1.py`, `writing_agent/web/api/template_flow.py` | 无 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T11 | 新增 plan_confirm 节点与 API/UI（通过/终止/评分） | `writing_agent/state_engine/*`, `writing_agent/web/services/generation_service.py`, `writing_agent/web/frontend_svelte/src/AppWorkbench.svelte` | T03 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T12 | 需求解析 strict schema + 字段置信度评分 + 低置信度澄清 | `writing_agent/web/app_v2_textops_runtime_part1.py`, `writing_agent/v2/graph_runner.py` | T03,T10 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T13 | 解析正确性守卫（语言/层级/标题域/关键词一致） | `writing_agent/v2/graph_runner_runtime.py`, `writing_agent/web/domains/export_structure_domain.py` | T12 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T14 | 引入 `academic_cnki_default` 质量模板并默认启用 | `writing_agent/web/app_v2.py`, `writing_agent/web/domains/export_structure_domain.py` | 无 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T15 | 摘要/关键词从 disallowed 移除并设为学术必需 | `writing_agent/v2/graph_runner.py`, `writing_agent/v2/graph_runner_runtime.py`, `writing_agent/web/domains/export_structure_domain.py` | T14 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T16 | 章节深度约束（H1/H2/H3 最小数量与分布）前置到 plan 阶段 | `writing_agent/v2/graph_runner_runtime.py`, `writing_agent/v2/graph_runner.py` | T14,T15 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T17 | 语义灌水兜底改为 fail-fast（禁用 generic fill 生产伪造） | `writing_agent/v2/graph_runner_runtime.py`, `writing_agent/v2/graph_section_draft_domain.py` | T02 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T18 | 保留基础设施兜底并标注 `engine_failover=true` + “需复核” | `writing_agent/web/services/generation_service.py`, `writing_agent/web/app_v2_generate_stream_runtime.py` | T17 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T19 | 统一终态状态机：`success/failed/interrupted` | `writing_agent/web/app_v2.py`, `writing_agent/web/services/generation_service.py`, `writing_agent/web/frontend_svelte/src/AppWorkbench.svelte` | T18 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T20 | 终态附 `failure_reason` 与 `quality_snapshot` | `writing_agent/web/services/generation_service.py`, `writing_agent/v2/graph_runner_runtime.py` | T19 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T21 | 参考文献改为可核验来源驱动，不足/重复/未核验直接 failed | `writing_agent/web/app_v2_textops_runtime_part2.py`, `writing_agent/web/domains/export_structure_domain.py` | T14 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T22 | 禁止 conservative 模式把 `target_unique` 降到 1 | `writing_agent/web/app_v2_textops_runtime_part2.py` | T21 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T23 | 图表升级为 DocIR 强类型节点（table/figure object） | `writing_agent/v2/doc_format.py`, `writing_agent/v2/graph_runner_runtime.py`, `writing_agent/v2/graph_section_draft_domain.py` | T04 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T24 | 图表引用一致性校验（提及必须有对象、编号连续） | `writing_agent/web/domains/export_structure_domain.py`, `writing_agent/v2/graph_runner_runtime.py` | T23 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T25 | 导出前 OpenXML 结构校验与对象完整性校验，不通过 failed | `writing_agent/web/services/export_service.py`, `writing_agent/web/domains/export_structure_domain.py` | T23,T24 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T26 | 新增端到端回归集（复杂中文/章节深度/图表/参考/revise/导出） | `tests/`, `tests/ui/`, `scripts/` | T01-T25 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |
| T27 | trace 报告格式升级（planner JSON/每节点 DocIR/quality gate/终态） | `scripts/`, `deliverables/`, `writing_agent/v2/graph_runner_runtime.py` | T08,T20 | completed | commit:5052557; tests:deliverables/p0_20260307/p0_core_tests.log|deliverables/p0_20260307/p0_extended_tests.log|deliverables/p0_20260307/p0_acceptance_tests.log; gate:deliverables/p0_20260307/prompt_offline_eval_gate.json|deliverables/p0_20260307/docx_20_rounds_validation.json; compile:deliverables/p0_20260307/p0_py_compile.log |


