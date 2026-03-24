# 外部评审问题与最佳实践整改基线（2026-03-10）

## 1. 文档目的

本文件综合以下三份输入，形成本轮代码整改的直接实施基线：

1. `C:\Users\Lenovo\Desktop\temp\2026-3-10\gpt方案.md`
2. `C:\Users\Lenovo\Desktop\temp\2026-3-10\gemini方案.md`
3. `D:\codes\writing-agent\docs\FINAL_ARCHITECTURE_AND_CHANGESET_MASTER_20260309_CN.md`

执行原则：

1. `FINAL_ARCHITECTURE_AND_CHANGESET_MASTER_20260309_CN.md` 仍为最高优先级架构约束。
2. 外部评审中的问题必须映射为代码级修复，而不是仅停留在 Prompt 建议层。
3. 所有质量问题必须做到“可观测、可追踪、可失败”，禁止伪成功。

## 2. 外部评审问题汇总

### 2.1 GPT 评审指出的问题

1. 运行时状态和质量门禁状态混杂，`reference_items_insufficient` 被直接当作 runtime failure。
2. 参考文献数量约束仅靠 Prompt，缺少确定性的 `reference repair step`。
3. 生成链路实际上已稳定，但阈值策略使系统把“质量不达标”误报为“生成失败”。
4. 标题-正文对齐仍有提升空间，说明质量门禁虽通过，但仍缺少更细粒度的对齐治理。

### 2.2 Gemini 评审指出的问题

1. 乱码与导出一致性风险，说明导出前缺少结构与 OOXML 一致性校验。
2. RAG 事实供给不足，长文仅靠少量文献支撑，导致 `Evidence Starvation`。
3. 在没有真实统计数据时仍生成表格和具体数值，出现 `Table Hallucination`。
4. 引用与章节语义错位，出现 `Ref Misplacement`。
5. 上下文隔离不足，综述型内容污染了分析型章节。
6. 元指令残留变体逃逸，现有正则未覆盖如 `[1]；区块链...` 的残留形态。
7. 终审语义门禁存在假阳性，无法识别“没有信息增量的学术套话”。
8. 在事实密度极低时仍强行补齐总字数，导致 `Over-Inflation`。
9. 通用填充模板把章节目录/章节说明直接写入正文，形成 `Section Catalog Leakage`。
10. 高质量验证脚本仍硬编码 9000 字，未消费运行时返回的 `effective_min_total_chars`，会制造脚本层假失败。

## 3. 问题到整改动作的映射

| 问题 | 根因 | 最佳实践 | 本仓库落地动作 |
| --- | --- | --- | --- |
| runtime 与 quality 语义混杂 | 终态字段只保留一个 `status` | 将运行完成状态与质量通过状态拆开，分别记录执行结果与质量判定 | 在 `graph_runner_runtime.py` 中增加 `runtime_status / runtime_failure_reason / quality_passed / quality_failure_reason`，保留总终态 `success\|failed\|interrupted` |
| 引用不足直接失败 | 无确定性引用修复阶段 | 先生成正文，再做独立引用修复与二次校验 | 在引用聚合后增加 `reference_repair` 步骤，优先复用现有 sources，不足时调用 fallback/OpenAlex 补足 |
| 事实不足仍强行冲字数 | 目标字数固定，未根据事实密度动态收缩 | 让目标字数由事实密度驱动，低密度时提前收缩目标或进入 `STUB_MODE` | 在 `graph_runner_runtime.py` 中加入 `fact_density_target_adjustment` 事件与 `effective_min_total_chars` |
| 元指令变体漏检 | 黑名单覆盖不足 | 使用显式残留模式与负样本反馈重写 | 在 `meta_firewall.py` 中扩充 `[数字]；`、自评式补齐等模式，并保留 `REWRITE_WITHOUT_META` |
| 学术套话门禁不足 | 终审只看重复率/镜像率/模板率 | 增加“低信息增量”检测，拒绝没有实质信息的模板化段落 | 在 `final_validator.py` 中增加 `low_information_ratio` 与阈值 |
| RAG 文献贫血 | sources 召回不足且无修复 | 检索与引用分离，引用区以结构化元数据生成，不足时走二次检索 | 在 `graph_reference_domain.py` 与 `graph_runner_runtime.py` 中做引用修复与去重归并 |
| 表格/统计幻觉 | 无事实也允许写表格与数值 | 没有事实就禁写统计型表格，或显式触发失败/降级 | 保持 `RAG-Fact Protocol` 主链，不在本轮新增任何“猜测填表”路径 |
| 章节说明泄漏进正文 | 通用填充模板复用了 Section Catalog 描述 | 未命中显式领域模板时宁缺毯滥，不把章节写作说明转成正文 | 在 `graph_section_draft_domain.py` 中移除 catalog-desc 驱动的 fallback 正文填充，未知章节保持空并交由质量门禁处理 |
| 外层验证脚本误判长度失败 | 脚本忽略运行时 `effective_min_total_chars` | 评测层必须消费运行时自适应阈值，避免脚本制造假阴性 | 在 `run_dual_provider_high_quality_cn.py` 中改为读取 `quality_snapshot.effective_min_total_chars` 作为长度验收线 |
| 导出一致性缺失 | 导出前缺少结构校验 | 在导出前做结构与文档格式校验 | 维持最终 validator 前置拦截，并补充文档中对 OpenXML 校验钩子的要求 |

## 4. 采用的外部最佳实践

### 4.1 状态图与并发状态管理

参考 LangGraph 的 Graph API / StateGraph 实践，关键点是：

1. 共享状态必须显式建模，不能把“运行完成”和“质量通过”混成一个布尔结果。
2. 并行分支汇合时需要 reducer/显式合并语义，避免串行拼接隐式吞错。
3. 失败要保留结构化状态，以便后续恢复、重试和证据追踪。

本仓库映射：`graph_runner_runtime.py` 的 final payload、`quality_snapshot`、`raw_events.jsonl`。

### 4.2 Prompt 与评测治理

参考 OpenAI 的 Prompt Engineering / Eval-driven 最佳实践，关键点是：

1. 指令必须版本化与可追踪，不依赖临时经验性 Prompt。
2. 质量治理不能只靠人工肉眼，应将失败样例固化为评测与规则。
3. 对代表性样本持续运行评测，发现回归后立刻阻断。

本仓库映射：`meta_firewall.py`、`final_validator.py`、`tests/unit/test_meta_firewall.py`、`tests/unit/test_final_validator.py`。

### 4.3 RAG 与带来源回答

参考 OpenAI Cookbook 的 File Search / source-grounded generation 实践，关键点是：

1. 先检索事实，再生成正文；不能让模型无证据扩写。
2. 生成时必须携带可用来源列表，引用区应由结构化来源驱动。
3. 对检索结果不足的情况，应触发额外检索或降级，而不是让模型猜。

本仓库映射：`graph_reference_domain.py`、`graph_runner_runtime.py`、`writing_agent/v2/rag/openalex.py`。

### 4.4 学术检索补货与排序

参考 OpenAlex 官方文档，关键点是：

1. 学术文献检索应使用结构化元数据，而不是随意抓网页正文。
2. 检索结果可按 `relevance_score`、`cited_by_count`、`publication_year` 等字段做再排序。
3. 当本地 sources 不足时，在线检索应作为补货层，而不是混入正文上下文直接生成。

本仓库映射：`graph_reference_domain.py` 的 fallback / OpenAlex 补货逻辑。

### 4.5 Word/OpenXML 导出一致性

参考 Microsoft Learn 的 Open XML 校验实践，关键点是：

1. 文档导出前应保证结构合法，而不是把不完整内容直接写成最终交付物。
2. 对目录、段落、引用等关键结构，应在导出前完成一致性校验。
3. 如果结构校验失败，应在导出前阻断，而不是把问题推给最终用户打开文档时暴露。

本仓库映射：最终 validator 前置拦截、导出前摘要化的结构检查、后续可接入显式 OOXML 校验钩子。

## 5. 本轮必须落地的代码改动

1. 在 `writing_agent/v2/graph_runner_runtime.py` 中拆分运行态与质量态：
   - 新增 `runtime_status`
   - 新增 `runtime_failure_reason`
   - 新增 `quality_passed`
   - 新增 `quality_failure_reason`
   - 总终态仍保持 `success | failed | interrupted`

2. 在 `writing_agent/v2/graph_runner_runtime.py` 中新增引用修复阶段：
   - 统计现有可格式化引用条数
   - 不足阈值时触发 `reference_repair`
   - 通过 fallback + OpenAlex 进行结构化补货
   - 补货后重新去重、主题过滤、再格式化

3. 在 `writing_agent/v2/graph_runner_runtime.py` 中新增事实密度驱动的目标收缩：
   - 基于 `fact_gain_count` 和 `fact_density_score` 估算可支撑字数
   - 当事实预算显著低于目标字数时，下调 `effective_min_total_chars`
   - 记录 `fact_density_target_adjustment` 事件

4. 在 `writing_agent/v2/meta_firewall.py` 中扩充元指令残留模式：
   - 覆盖 `[1]；区块链...` 之类残留
   - 覆盖“本段补充了”“围绕……展开”“进一步补充了”等自评式补齐话术

5. 在 `writing_agent/v2/final_validator.py` 中增强低信息判定：
   - 新增 `low_information_ratio`
   - 新增 `low_information_hits`
   - 新增环境阈值 `WRITING_AGENT_MAX_LOW_INFORMATION_RATIO`
   - 当低信息率超限时，语义门禁直接失败

6. 补充单元测试：
   - `test_meta_firewall_scan_detects_bracket_semicolon_meta_residue`
   - `test_validate_final_document_fails_when_low_information_ratio_exceeds_threshold`
   - `test_runtime_reference_repair_and_status_split`

## 6. 本轮不做的事情

以下事项属于后续架构重构范围，本轮只在文档中保留要求，不做大爆炸改造：

1. 不重写整个导出器。
2. 不在本轮将所有 section worker 完全切换为新的 `SectionSpec` 入参协议。
3. 不引入新的外部数据库或大规模本地语料迁移。
4. 不做新的表格自动生成器，继续坚持“无事实不造表”。

## 7. 验收口径

本轮完成后，至少满足：

1. 当正文已生成但质量门禁未通过时，结果中能同时看到：
   - `status=failed`
   - `runtime_status=success`
   - `quality_passed=false`
   - 可追踪的 `quality_failure_reason`
2. 当引用不足时，系统会优先执行 `reference_repair`，而不是直接因条数不足失败。
3. 当事实密度过低时，系统会产生 `fact_density_target_adjustment` 或 `data_deficit_warning`，而不是继续盲目补齐。
4. `[1]；区块链...` 这类残留能被 Meta Firewall 命中。
5. “综上所述，我们可以看到”这类低信息学术套话能被终审识别并触发失败。
6. 现有缓存与 smoke profile 不被破坏，回归测试继续通过。

## 8. 参考来源

1. LangGraph Graph API / StateGraph 文档：<https://langchain-ai.github.io/langgraph/concepts/low_level/>
2. LangGraph Use Graph API 文档：<https://docs.langchain.com/oss/python/langgraph/use-graph-api>
3. OpenAI Prompt Engineering 指南：<https://platform.openai.com/docs/guides/prompt-engineering>
4. OpenAI Evals 设计指南：<https://platform.openai.com/docs/guides/evals-design>
5. OpenAI Cookbook File Search / source-grounded generation：<https://cookbook.openai.com/examples/file_search_responses>
6. OpenAlex Works 检索文档：<https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/search-entities>
7. OpenAlex 排序与过滤文档：<https://docs.openalex.org/api-entities/works/filter-works>
8. Microsoft Learn Open XML 文档校验：<https://learn.microsoft.com/en-us/office/open-xml/word/how-to-validate-a-word-processing-document>
