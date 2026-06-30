# 编辑意图解析最佳实践与改造方案（2026-02-28）

## 1. 目标与结论

本文面向 `writing-agent` 当前“规则优先”的编辑指令解析链路，基于 2026-02-28 前可获得的主流官方文档与论文，给出可落地的最终改造方案。

结论先行：

1. 单纯“增加规则同义词”不是长期可行方案，边际收益快速下降，维护成本和误判率会同步上升。
2. 行业主流方案是“结构化语义解析（Schema/Grammar 约束）+ 执行前验证 + 风险分级确认 + 持续评测”。
3. 对本项目，建议采用“混合双轨”：`Schema-LLM 主路径 + 规则解析兜底路径`，并在 2-3 个迭代内完成主路径切换。

## 2. 市面最佳实践（官方与论文共识）

### 2.1 用结构化输出替代自由文本解析

共识：让模型直接输出符合 JSON Schema 的结构化对象，而不是自然语言描述。

原因：

1. 可解析性稳定，减少“模型输出可读但不可执行”的失败。
2. 下游执行器可以做静态校验（字段类型、必填、枚举、范围）。
3. 便于版本管理（Schema v1/v2）。

参考：

1. OpenAI Function Calling / Structured Outputs（`strict: true`）。
2. Google Gemini Controlled Generation（response schema）。
3. Azure OpenAI Structured Outputs（显式 schema 能力）。

### 2.2 约束解码（Constrained Decoding）是关键，不是“提示词更长”

共识：模型输出要受语法/Schema 约束，不能只靠提示词“要求返回 JSON”。

原因：

1. 约束解码可显著降低结构错误。
2. 当任务是“文本 -> 操作计划”时，结构正确率是第一门槛。

参考：

1. PICARD（经典约束解码思想，先保证结构有效）。
2. Grammar-Constrained Decoding。
3. JSONSchemaBench（大规模 schema 实测，显示结构约束必要性）。

### 2.3 执行前验证（Execution Guard）必须独立于解析器

共识：即便结构化输出正确，也不代表语义正确，必须在执行前再做校验。

典型校验：

1. 目标是否存在（章节名、索引合法性）。
2. 操作是否冲突（同一节先删后改）。
3. 是否高风险（全局替换、大范围删除）。

参考：

1. Execution-guided 思想（解析与可执行性联动）。
2. 主流 Agent 文档中的 guardrails / policy checks。

### 2.4 使用风险分级与人工确认，而不是一刀切自动执行

共识：把编辑操作按风险等级路由。

建议：

1. 低风险：自动执行（如改标题、单点替换）。
2. 中风险：先 dry-run 产出 diff，再自动执行并可回滚。
3. 高风险：必须确认（如删除多个章节、全局替换）。

参考：

1. OpenAI Guardrails 与安全实践文档。
2. 云厂商工具调用文档中对“高后果动作”确认建议。

### 2.5 评测集驱动迭代，而不是靠线上反馈临时补规则

共识：要有专门的 tool-call / action-parse 评测集。

核心指标：

1. `parse_valid_rate`：结构合法率。
2. `arg_exact_match`：关键参数精确匹配率。
3. `exec_success_rate`：执行成功率。
4. `silent_failure_rate`：静默误执行率（最危险）。
5. `clarification_rate`：进入澄清率（需要平衡）。

参考：

1. BFCL、τ-bench、τ²-bench 等函数调用/代理评测方向。
2. OpenAI Evals 设计建议（先定义失败模式，再做数据集）。

### 2.6 保留规则层，但角色应降级为“兜底与快速路径”

共识：规则层仍有价值，但应限于：

1. 高频、短指令、低歧义操作。
2. 无模型依赖时的降级可用性。

不应继续把规则层当主解析器，否则扩展性和可维护性恶化。

## 3. 当前项目差距评估（基于现状代码）

现状关键点：

1. 规则主解析：`writing_agent/web/domains/revision_edit_runtime_domain.py` 的 `_parse_edit_ops`。
2. 规则定义：`writing_agent/web/edit_rules.json`。
3. 语义兜底入口存在，但模型解析尚未实现：`_parse_edit_ops_with_model` 当前返回空列表。
4. `looks_like_modify_instruction` 仍以关键词启发式为主。

主要差距：

1. 缺少“受 schema 约束”的主解析路径。
2. 缺少统一的执行前语义验证器（目前主要靠规则命中后直接执行）。
3. 缺少基于风险级别的确认机制。
4. 缺少专门的解析评测集与线上可观测指标看板。

## 4. 最终改造方案（建议采用）

### 4.1 目标架构（主路径 + 兜底路径）

```text
用户指令
  -> 轻量归一化（口语/错别字/标点）
  -> Schema-LLM 解析（strict schema）  [主路径]
      -> 语义验证器（目标存在/冲突/风险）
          -> 执行计划（EditOp[]）
              -> dry-run diff
                  -> 自动执行或确认执行
  -> 若主路径失败：规则解析 `_parse_edit_ops` [兜底]
  -> 若仍失败：澄清问题（单轮）
```

### 4.2 统一数据契约（EditPlan v2）

建议定义 `EditPlanV2`：

1. `version`: `"v2"`
2. `operations`: `EditOp[]`
3. `confidence`: `0-1`
4. `ambiguities`: `string[]`
5. `requires_confirmation`: `bool`
6. `risk_level`: `low|medium|high`

要求：所有执行入口只接受该结构，不再直接消费自由文本。

### 4.3 执行前验证器（必须落地）

最小验证集：

1. `target_exists`: 目标章节/文本存在。
2. `args_type_valid`: 参数类型和范围正确。
3. `ops_non_conflicting`: 操作顺序无冲突。
4. `safety_policy`: 高风险操作触发确认。
5. `idempotency_hint`: 同一操作重复提交可识别。

### 4.4 风险分级策略

1. `low`: `set_title`, 单点 `replace_text`，自动执行。
2. `medium`: 章节移动/重排，先 dry-run，再自动执行并记录审计。
3. `high`: 删除章节、全局替换、批量操作，要求确认。

### 4.5 澄清机制

当满足任一条件，返回澄清而不是猜执行：

1. 解析置信度低于阈值。
2. 存在多个互斥可行计划。
3. 高风险且参数缺失。

澄清问题约束：

1. 只问 1 个关键问题。
2. 提供当前候选计划摘要，减少用户负担。

## 5. 分阶段实施计划

### 阶段 A（1 个迭代）：建立可评测基线

1. 增加 `tests/intent_parse_cases/` 数据集（口语、省略、错别字、混合意图）。
2. 补指标采集：`parse_valid_rate`、`arg_exact_match`、`exec_success_rate`、`silent_failure_rate`。
3. 保持现有行为不变，仅建立“测量能力”。

验收标准：

1. 形成首版基线报告。
2. 每次变更可自动回归。

### 阶段 B（1-2 个迭代）：上线 Schema-LLM 主解析

1. 新增 `parse_edit_plan_v2()`，输出 `EditPlanV2`。
2. 使用严格 schema（必须可机器校验）。
3. 将 `_parse_edit_ops` 保留为 fallback。

验收标准：

1. 主路径覆盖 >70% 实际编辑请求。
2. 结构非法率显著下降。

### 阶段 C（1 个迭代）：加验证器与风险确认

1. 接入执行前验证器。
2. 高风险路径加确认与 dry-run diff。
3. 增强审计日志（解析结果、验证结论、最终执行）。

验收标准：

1. `silent_failure_rate` 下降到可接受阈值。
2. 高风险误执行可追踪可回滚。

### 阶段 D（持续）：削减规则复杂度

1. 下线低收益高维护规则。
2. 保留高精度高频规则作为无模型降级。
3. 持续扩充评测集，而非“线上出错后临时打补丁”。

验收标准：

1. 规则总量下降，覆盖率不降。
2. 维护成本下降，回归稳定性提升。

## 6. 不建议的路径

1. 持续堆叠同义词正则（“米多加水水多加米”）。
2. 把澄清问题省掉，改为低置信度也直接执行。
3. 没有评测基线就替换主解析器。

## 7. 立即执行清单（针对本项目）

1. 创建 `EditPlanV2` schema 与解析接口（不替换现网路径）。
2. 给 `_parse_edit_ops_with_model` 实现严格 schema 输出。
3. 增加执行前验证器模块，并接入 `generation_service` 的编辑分支。
4. 建立解析评测数据集与 CI 回归任务。
5. 以功能开关灰度切流：`schema_parser_ratio` 从 10% -> 50% -> 100%。

## 8. 参考资料（检索日期：2026-02-28）

### 官方文档

1. OpenAI Function Calling Guide: https://platform.openai.com/docs/guides/function-calling
2. OpenAI Structured Outputs Intro: https://platform.openai.com/docs/guides/structured-outputs
3. OpenAI Evals Design Guide: https://platform.openai.com/docs/guides/evals-design
4. OpenAI Building Guardrails for Agents: https://openai.github.io/openai-agents-js/guides/guardrails
5. Anthropic Tool Use (Claude): https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use
6. Google Gemini Function Calling: https://ai.google.dev/gemini-api/docs/function-calling
7. Google Gemini Structured Output: https://ai.google.dev/gemini-api/docs/structured-output
8. Azure OpenAI Structured Outputs: https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/structured-outputs
9. AWS Bedrock Tool Use + Structured JSON: https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use.html

### 论文与评测

1. PICARD (EMNLP 2021): https://aclanthology.org/2021.emnlp-main.779/
2. Grammar-Constrained Decoding (arXiv 2023): https://arxiv.org/abs/2305.13971
3. JSONSchemaBench (arXiv 2025): https://arxiv.org/abs/2501.10868
4. Execution-Guided Decoding (arXiv 2018): https://arxiv.org/abs/1807.03100
5. BFCL (Function Calling Benchmark): https://gorilla.cs.berkeley.edu/leaderboard
6. τ-bench (Agent Reliability): https://arxiv.org/abs/2406.12045
7. τ²-bench (Multiturn Agent Benchmark): https://arxiv.org/abs/2506.07982

## 9. 当前实现状态（2026-02-28，已落地）

本轮代码已按“最终版本”一次性接入以下能力：

1. `Schema-LLM 主解析 + 规则兜底` 已接入到快捷编辑与意图编辑路径。
2. `执行前验证` 已接入：参数合法性、目标存在、冲突检查、风险分级。
3. `高风险确认` 已从“手动在指令里追加口令”升级为结构化协议：
   - 后端返回 `requires_confirmation` / `confirmation_reason` / `confirmation_action`
   - 前端展示“确认执行 / 取消”按钮弹窗
   - 二次提交使用 `confirm_apply=true`，不依赖解析 `note` 文本
4. `本地静默指标` 已落盘到 JSONL（默认 `.data/metrics/edit_plan_events.jsonl`），仅用于研发观测，不暴露到用户 UI/API。
5. 已补充对应测试，覆盖高风险阻断、确认放行、模型失败兜底、指标落盘等关键路径。
