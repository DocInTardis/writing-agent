# Writing-Agent 最终架构与修改总文档（2026-03-09）

## 1. 文档目的

本文件作为当前阶段的单一总文档（SSOT），完整汇总以下内容：

1. 已落地代码修改（已在仓库中可核对）。
2. 当前架构已具备能力（代码事实，不是计划）。
3. 当前系统仍存在的根因级问题。
4. 下一轮完整重构任务清单（执行列表）。
5. 验收标准、回归口径与执行建议。

---

## 2. 本轮已落地修改（已改代码）

### 2.1 全链路模型切换为 OpenAI GPT

已修改启动入口，默认全链路走 OpenAI，避免本地 Ollama 参与主生成链路：

1. `_misc_root/start.ps1`
2. `_misc_root/start_desktop.ps1`
3. `_misc_root/run_server.bat`

### 2.2 具体变更内容

已落实以下配置策略：

1. 强制 Provider：
   - `WRITING_AGENT_LLM_PROVIDER=openai`
2. 强制主模型一致：
   - `WRITING_AGENT_OPENAI_MODEL=gpt-5.4`
   - `WRITING_AGENT_MODEL=gpt-5.4`
   - `WRITING_AGENT_AGG_MODEL=gpt-5.4`
   - `WRITING_AGENT_WORKER_MODELS=gpt-5.4`
   - `WRITING_AGENT_DRAFT_MAIN_MODEL=gpt-5.4`
   - `WRITING_AGENT_DRAFT_SUPPORT_MODEL=gpt-5.4`
3. 关闭本地模型路径：
   - `WRITING_AGENT_USE_OLLAMA=0`
4. 关闭慢速 embedding 路径：
   - `WRITING_AGENT_RAG_USE_EMBEDDINGS=0`
5. API 并发利用：
   - `WRITING_AGENT_DRAFT_PARALLEL=1`
   - `WRITING_AGENT_DRAFT_MAX_MODELS=1`
   - `WRITING_AGENT_PER_MODEL_CONCURRENCY=3`
6. 启动时自动读取 Codex 鉴权（兜底）：
   - 从 `%USERPROFILE%\\.codex\\auth.json` 读取 `OPENAI_API_KEY`
   - 仅在 `WRITING_AGENT_OPENAI_API_KEY` 未显式设置时注入

---

## 3. 当前架构“已具备能力”总览（代码事实）

### 3.1 Prompt 路由与结构化约束

系统已支持：

1. 按 `intent/doc_type/language/quality_profile` 路由 Prompt。
2. Planner/Analysis/Writer 使用结构化格式（JSON/NDJSON）约束。
3. Writer Prompt 内置元指令禁止规则。

核心代码：

1. `writing_agent/v2/prompts.py`
2. `writing_agent/v2/graph_runner.py`

### 3.2 范式锁（Paradigm Lock）

系统已实现：

1. 范式分类（`bibliometric/engineering/empirical`）。
2. `confidence + margin` 输出。
3. `dual_outline_probe` 低置信度双大纲探测。

核心代码：

1. `writing_agent/v2/paradigm_lock.py`

### 3.3 Section Contract（章节合同）

系统已实现：

1. 按范式与章节分配 `min/max chars`。
2. 关键词章节 slot filling 与校验。
3. 维度展开提示（dimension hints）基础能力。

核心代码：

1. `writing_agent/v2/section_contract.py`
2. `writing_agent/v2/graph_runner_runtime.py`

### 3.4 Meta Firewall（元指令防火墙）

系统已实现：

1. 硬规则与软规则扫描。
2. 段落级剔除（hard pattern）。
3. `REWRITE_WITHOUT_META` 重写提示模板。

核心代码：

1. `writing_agent/v2/meta_firewall.py`
2. `writing_agent/v2/graph_section_draft_domain.py`

### 3.5 RAG 主题/实体闸门

系统已实现：

1. Theme consistency score。
2. Entity alignment（例如标题含“区块链”而文献缺实体时剔除）。
3. `rag_entity_mismatch / rag_theme_mismatch` 结构化原因输出。

核心代码：

1. `writing_agent/v2/rag_gate.py`

### 3.6 终态质量门禁

系统已实现：

1. 结构门禁（缺章节）。
2. 语义门禁（问题前缀、重复率、镜像率、模板注水率）。
3. Meta residue 检测。
4. 实体对齐判定。
5. `passed=false` 时强制失败（避免伪成功）。

核心代码：

1. `writing_agent/v2/final_validator.py`
2. `writing_agent/v2/graph_runner_runtime.py`

---

## 4. 当前架构仍存在的根因级问题

### 4.1 章节身份仍以标题文本为核心，而非稳定 UID

现状：

1. `section_id` 仍由标题编码派生，不是生命周期稳定主键。
2. 章节内容容器仍依赖 `dict[section_token/title]`。

后果：

1. 标题微小变化会导致映射失稳。
2. 聚合时容易错位或误覆盖。

### 4.2 聚合主路径是“顺序+标题拼接”，不是 ID 坑位填充

现状：

1. 主流程通过 `_merge_sections_text` 依序拼接内容。
2. 并非按 `SectionSpec.id` 强绑定填充。

后果：

1. “标题/内容不对应”难彻底杜绝。
2. 后续修补会被顺序变化反噬。

### 4.3 字数补齐仍有模板化扩写路径

现状：

1. 当总字数不足，仍可能走模板段落补齐。
2. 不是严格“新事实驱动”。

后果：

1. 产生低信息增量注水文本。
2. 易触发“指令镜像/模板腔”残留。

### 4.4 参考文献虽已格式化，但来源注入链路仍可能漂移

现状：

1. 格式化函数已偏 deterministic。
2. fallback 来源扩展仍可能引入主题边缘文献。

后果：

1. 引文与主题弱相关风险仍在。
2. 参考区质量对上游检索噪声敏感。

### 4.5 缺少“RAG 召回浓度熔断”机制

现状：

1. 当前补齐主要判断“是否有事实”。
2. 对“弱相关事实/低密度事实”缺少硬拦截。

后果：

1. 无效事实进入写作链路，造成无意义润色。
2. 继续放大注水风险。

### 4.6 缺少“中间态语义热采样”

现状：

1. 语义对齐主要在 final validator 做终审。
2. 章节早期跑偏无法被快速中止。

后果：

1. Token 成本高，失败发现过晚。
2. “写完才失败”的体验差。

### 4.7 多章节上下文隔离仍不够严格

现状：

1. Worker 生成时仍可能携带较大共用上下文。
2. 缺少 `section_id` 级 Clean Context 沙盒规则。

后果：

1. 摘要/引言语气污染正文。
2. 元指令与模板语句跨章节扩散。

### 4.8 聚合阶段缺少“不可逆性防护”

现状：

1. 聚合层有文本处理能力，边界不够硬。
2. 缺少“聚合只拼装，不改写”的强约束。

后果：

1. 聚合器可能成为新的废话/污染来源。
2. 排查路径复杂化，责任边界模糊。

---

## 5. 最终重构任务清单（完整执行列表）

以下为下一轮必须执行的任务列表，按顺序实施：

1. 引入 `SectionSpec` 数据结构：`id/title/level/parent_id/order/type`。
2. 在 Planner 输出中强制携带稳定 `section_id`，禁止仅标题驱动。
3. 将运行时 `section_text` 从标题键改为 `section_id` 键。
4. 改造 section worker 入参为 `section_spec`，不再只传标题字符串。
5. 改造 `_normalize_section_id`：外部兼容保留，内部以计划发放的 `section_id` 为准。
6. 在 `_stream_structured_blocks` 中强制校验 block 的 `section_id` 必须匹配当前 `section_spec.id`。
7. 为每个 block 增加稳定 `block_uid`（可追踪生成来源与重试版本）。
8. 引入 `DocumentAssemblyMap`（按 `section_id` 坑位装配正文）。
9. 替换 `_merge_sections_text` 主路径为 `assemble_by_id_map`。
10. 聚合失败时禁止“相邻章节代填”，缺失章节必须显式缺失并进入失败路径。
11. 引入 `section_missing` 结构化错误：`section_id/title/reason/stage`。
12. 实现 `RAG-Fact Protocol`：仅当收到有效 `Fact_Tokens` 时允许扩写；并加入“召回浓度熔断（Retrieval Density Kill-switch）”。
13. 建立“空事实降级路径”：当事实注入量低于阈值时进入 `STUB_MODE` 并抛出 `Data_Deficit_Warning`，禁止模板注水补字。
14. 删除/下线模板化补段函数在主链路中的调用入口。
15. 为补齐流程增加 `fact_gain_count` 与 `fact_density_score` 指标并写入 trace。
16. 建立 `ReferenceAgent` 沙盒：输入仅文献 JSON，不接收正文上下文。
17. 参考文献输出严格按行校验（编号、条目结构），不合格直接失败。
18. 参考区禁止自然语言解释句，命中即熔断并返回 `reference_format_violation`。
19. 在 section worker 第一批 block 产出后触发“语义热采样”（In-process Semantic Sampling）。
20. 热采样发现 instruction echo / plan echo 时，立即章节级重试或切换策略，禁止继续长写。
21. 建立 `section_id` 级 Context Sandbox：每章使用 Clean Context，禁止全量历史上下文无界注入。
22. 在 `assemble_by_id_map` 阶段加入 `Immutability Guard`：聚合只拼装，禁止改写正文。
23. 在 final validator 增加“标题-正文语义对齐分”硬阈值，不达标直接 `failed`。
24. 统一终态语义：`success | failed | interrupted`，失败必须带 `failure_reason`。
25. 禁止任何“fallback 写回 success”的路径，并加入单测。
26. 输出阶段记录完整追踪：planner JSON / per-section docir / validator report / assembly map。
27. 新增回归测试：章节错位、模板注水、参考污染、实体错配、热采样早停。
28. 新增双模型一致性测试：同任务本地与云端结构一致性比较。
29. 导出前增加最终拦截：未通过 validator 的文档禁止导出。

---

## 6. 验收标准（DoD）

满足以下全部条件才可标记完成：

1. 章节映射正确率 100%（无标题内容错位）。
2. 参考文献区无自然语言污染。
3. 模板注水率不超过阈值（默认 3%）。
4. 指令镜像率不超过阈值（默认 5%）。
5. 重复句比率不超过阈值（默认 5%）。
6. 语义热采样命中后可在章节级提前止损。
7. RAG 低浓度触发熔断并可追踪。
8. 任一关键门禁失败时终态必须为 `failed`。
9. 导出前存在完整 `final_validation` 证据。
10. 失败原因可追踪到阶段与 `section_id`。

---

## 7. 回归测试口径

1. 文献计量题目（含 CiteSpace）：
   - 期望：不会出现工程实现章节污染。
2. 工程报告题目：
   - 期望：不会被误锁到文献计量骨架。
3. 高字数目标但低证据输入：
   - 期望：短而实，不注水；触发 `Data_Deficit_Warning`。
4. 参考文献脏数据输入：
   - 期望：过滤或失败，不可伪成功。
5. 元指令诱导输入：
   - 期望：正文零残留。
6. 首段即跑偏场景：
   - 期望：热采样早停，不耗尽全文 token。
7. 跨章节污染场景：
   - 期望：Context Sandbox 生效，污染不扩散。

---

## 8. 启动与运行基线（当前已改）

推荐启动：

```powershell
$env:WRITING_AGENT_OPENAI_BASE_URL="https://api.openai.com/v1"
.\_misc_root\start.ps1 -SkipInstall
```

桌面版：

```powershell
.\_misc_root\start_desktop.ps1 -SkipInstall
```

---

## 9. 执行建议（本轮决策）

结论：

1. 该总文档可作为当前唯一执行基线。
2. 下一步应立即进入第 5 节任务 `1-5`（ID 链路第一刀）。
3. 在 `1-5` 完成前，不建议继续做 Prompt 微调类工作。

建议执行顺序：

1. 先做 `SectionSpec + section_id 全链路`。
2. 再做 `assemble_by_id_map + Immutability Guard`。
3. 最后切换“事实驱动补齐 + 熔断 + 热采样”。

---

## 10. 总结

当前系统已经具备范式锁、合同约束、防火墙、质量门禁等关键模块。  
但由于“章节身份与聚合机制仍偏标题驱动/顺序拼接”，以及“补齐路径尚未完全事实驱动”，你观察到的问题会反复出现。

下一轮必须围绕以下三条主轴收口：

1. `Section ID-Map` 装配。
2. `RAG-Fact Protocol` 与低浓度熔断。
3. 聚合不可改写（Immutability Guard）。

做到这三点，系统才能从“可运行”进入“可稳定交付”。


---

## 11. 中断恢复清单（未完成/半完成项，2026-03-09）

说明：以下条目为本轮被中断前尚未闭环的工作，包含“已写一半但未完成验收”的内容，统一按未完成处理。

1. `RAG Lite 存储` 仅完成代码落地，未完成端到端验证  
   - 已做：`writing_agent/v2/rag/index.py` 增加轻量模式开关、PDF chunk 可关闭、文本精简存储、`i8` 向量量化与旧数据兼容字段。  
   - 未完成：存量索引重建/迁移脚本、磁盘占用对比基准、召回质量回归报告。

2. `在线补货（OpenAlex）` 仅完成检索侧接入，未完成稳定性与质量验证  
   - 已做：`writing_agent/v2/rag/retrieve.py` 增加本地命中不足时的在线补货、结果合并与重排。  
   - 未完成：超时/限流策略压测、中文查询召回效果评估、失败重试与熔断指标校准。

3. `Data Starvation 闸门` 仅完成证据包结构化输出，未完成完整失败闭环验证  
   - 已做：`writing_agent/v2/graph_runner.py` 增加证据密度与主题对齐评分，输出 `data_starvation` 结构。  
   - 未完成：阈值调参基线、章节级告警可视化、与 section contract 的联动验证。

4. `Runtime 失败语义接入` 仅完成事件与失败原因注入，未完成全分支覆盖  
   - 已做：`writing_agent/v2/graph_runner_runtime.py` 增加 `rag_data_starvation` 事件、失败原因接入、质量快照字段。  
   - 未完成：证据准备所有异常分支统一携带 `data_starvation` 默认结构，防止分支行为不一致。

5. `单元测试与回归测试` 尚未执行  
   - 未完成：新增/补齐以下测试并通过：  
   - `rag/index` 量化编码解码与检索兼容性  
   - `rag/retrieve` 在线补货触发条件与合并排序  
   - `graph_runner` 饥饿闸门判定与结构化输出  
   - `graph_runner_runtime` 饥饿触发后的终态语义（`success|failed|interrupted`）

6. `文档同步` 尚未完成  
   - 未完成：将本轮新增环境变量与默认值写入统一配置文档（包括 `WRITING_AGENT_RAG_LITE_MODE`、`WRITING_AGENT_RAG_ONLINE_FILL_*`、`WRITING_AGENT_RAG_DATA_STARVATION_*`）。

7. `实测产物` 尚未完成  
   - 未完成：分别用本地模型与 OpenAI/Codex 跑至少 1 轮完整流程，沉淀可复核交付物：  
   - 过程 trace（planner/section/docir/validator）  
   - 最终导出文档  
   - 质量门禁结果与失败原因证据

8. `P0 语义要求` 尚未确认完全满足  
   - 未完成：确认“无伪成功”在新分支仍成立（即弱证据不得写回 `success`，失败原因可追踪到 section 级别）。

---

## 12. 加固钉子（2026-03-09 新增）

为提高硬盘受限与多模型切换场景下的稳定性，新增以下强制加固项：

1. `Authority Weighting`（时效性与权威性加权）
   - 在 RAG 重排阶段引入文献元数据加权：`cited_by_count`、`publication_year`。
   - 目标：在相关性相近时优先高被引且较新文献，降低低质量来源污染正文概率。

2. `Token Anomaly Kill-switch`（Token 异常熔断）
   - 增加单章节 token 消耗上限监控；超过阈值强制 `interrupted`。
   - 建议默认：单章预算阈值 4000 tokens（可配置），并输出结构化 `failure_reason=token_budget_exceeded`。

3. `Index Compact Task`（本地索引碎片整理）
   - 在 `rag/index.py` 增加 compact 任务（手动与定时两种触发方式）。
   - 目标：回收频繁增删改产生的索引碎片，避免磁盘“虚占用”持续增长。

---

## 13. 本轮实际已落地补充（2026-03-09）

以下能力已从方案落到代码：

1. `Section ID-Map` 主链已接入：
   - 新增 `SectionSpec` 与稳定 `sec_xxx` 标识。
   - `struct_plan`、section 事件、quality_snapshot 已携带 `section_id`。

2. `assemble_by_id_map` 已替换主装配路径：
   - 新增 `document_assembly.py`。
   - 运行时已使用 `section_id -> content` 装配正文。
   - 新增 `assembly_map` trace 与 `section_missing` 结构化错误。

3. `Immutability Guard` 已落地：
   - 聚合阶段改为只拼装，不再承担正文改写职责。

4. `RAG-Fact Protocol` 已补强：
   - evidence pack 输出 `facts`、`fact_gain_count`、`fact_density_score`、`online_hits`。
   - 低浓度命中时进入 `STUB_MODE` 并输出 `Data_Deficit_Warning`。

5. `模板补字主路径` 已关闭：
   - strict-json 第二轮不再使用模板兜底补段。
   - 总字数不足时不再注入 `_generic_fill_paragraph` 之类模板文本。

6. `ReferenceAgent` 沙盒已接入：
   - 参考文献仅由元数据 JSON 格式化生成。
   - 新增按行校验，命中自然语言污染返回 `reference_format_violation`。

7. `中间态语义热采样` 已接入：
   - section 首批 block 输出后即做语义热采样。
   - 命中元指令/说明书腔后立即早停并走章节级重试。

8. `标题-正文语义对齐门禁` 已接入：
   - final validator 新增 `title_body_alignment_score` 与硬阈值。

9. `Token Anomaly Kill-switch` 已接入：
   - section 级输出超过预算阈值时触发 `section_token_budget_exceeded`。
   - 终态可进入 `interrupted`，并输出 `failure_reason=token_budget_exceeded`。

10. `Authority Weighting` 与 `Index Compact Task` 已接入：
    - OpenAlex 在线补货加入 `cited_by_count/publication_year` 加权。
    - `RagIndex.compact()` 已新增。

---

