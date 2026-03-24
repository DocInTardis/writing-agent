# Writing-Agent 全量信息汇总与本轮落地总文档（2026-03-12）

## 1. 目的

本文档作为本轮整改的唯一实施依据，汇总以下信息：

1. 现有架构中已经真实落地的能力。
2. 来自历史复盘、外部评审和最近导出结果的核心缺陷。
3. 针对每个缺陷的明确修复策略、代码落点与验收标准。
4. 本轮必须完成的实现范围，以及暂不在本轮改动的后续项。

本文档强调“避免伪成功、优先失败可解释、宁短不水、宁拒绝不幻觉”。

## 2. 信息来源

本轮文档综合以下来源整理：

1. `docs/FINAL_ARCHITECTURE_AND_CHANGESET_MASTER_20260309_CN.md`
2. `docs/EXTERNAL_REVIEW_PROBLEMS_AND_REMEDIATIONS_20260310_CN.md`
3. `docs/LOGIC_BREAKDOWN_AND_CONTENT_INFLATION_REBUILD_PLAN_20260308_CN.md`
4. 最近一轮用户审查中对 `final_output.docx` 与 `RUN_SUMMARY.json` 的问题归纳
5. 当前仓库中已经落地的代码事实与测试覆盖情况

## 3. 当前已落地能力

以下能力视为已存在，不在本轮重复推倒重来：

1. 多模型 Provider 抽象与 OpenAI 兼容接入。
2. 范式锁（Paradigm Lock）与双大纲预演（dual outline probe）。
3. Section Contract 基础版：章节最小/最大字数、关键词 slot filling、维度展开提示。
4. Meta Firewall 基础版：提示词残留拦截、重写提示、段落级清洗。
5. RAG 主题/实体闸门基础版：主题一致性与实体对齐。
6. 最终质量门禁基础版：结构、重复率、镜像率、模板注水率、unsupported claim 检测。
7. 图片质量打分与导出阶段的 figure gate。
8. 长章节 continuation 分段负载均衡。
9. 已移除主要伪成功兜底：不再用模板文本硬填满章节。

## 4. 仍未闭环的核心问题

### 4.1 元数据编码链路分叉

表现：

1. 正文大体正常，但“关键词”“参考文献”“标题/图注”等元数据区域存在选择性乱码风险。
2. 部分导出辅助代码和历史文本处理逻辑中存在遗留乱码字面量与可疑字符路径。

根因：

1. 正文生成链路主要保持 Unicode 文本流。
2. 元数据拼装、参考文献修复、Docx 写入辅助链路存在额外清洗/拼接步骤，可能引入错误转码或污染文本。
3. 缺少在导出前对可疑 mojibake 的统一检测与修复/拒绝策略。

### 4.2 字数目标仍偏“全局静态驱动”

表现：

1. 系统虽然已有文档级 fact density 调整，但章节级别仍可能被统一合同推向过长输出。
2. 章节证据不足时，系统会在 expand/top-up 路径上浪费时间，并诱发“正确的废话”或不必要改写。

根因：

1. `SectionContract` 当前主要基于 `total_chars / section_count` 估算。
2. 缺少“每章证据可承载字数上限”的硬限制。
3. 缺少将 evidence pack 直接映射为 section max/min budget 的机制。

### 4.3 占位残留与低信息密度仍可能逃逸

表现：

1. 关键词或小节中可能出现 `实验项`、`步骤一`、`序号占位符`、`[数字]；` 等残留。
2. 文本可以不重复、不镜像，却依然“信息熵很低”，以学术套话掩盖证据不足。

根因：

1. Meta Firewall 与 Final Validator 的规则集中在显性元指令，尚未覆盖部分枚举型残留。
2. 低信息量检测目前主要依靠固定模式，缺少结构化的“信息密度代理指标”。

### 4.4 RAG 过滤更偏文档主题，章节粒度不够严格

表现：

1. 文档主题正确，但单个章节仍可能吸收边缘相关证据。
2. 章节级 evidence context 里仍可能出现“与标题只有弱重叠”的文献片段。

根因：

1. 当前 reference gate 和 theme/entity gate 更多在全局层面起作用。
2. 章节 evidence pack 生成前缺少“以 section_title 为准”的二次过滤门槛。

## 5. 本轮强制实施原则

1. 编码链路统一：所有进入导出的文字都必须走同一套 Unicode 归一化与乱码检测流程。
2. 证据驱动预算：章节预算由证据密度决定，而不是由静态总字数硬推。
3. 门禁前置 + 终审双保险：章节级先拦截明显污染，最终文档再做严格拒绝。
4. 章节优先对齐：所有 RAG 过滤优先对齐章节标题，而不是仅对齐总标题。
5. 不允许伪成功：若导出文本出现可疑乱码、占位残留、严重低信息密度，则必须失败或裁剪，而不是放行。

## 6. 本轮实施项

### 6.1 Encoding Invariant：导出元数据编码统一

目标：

1. 为标题、关键词、参考文献、图注、表注和普通段落建立统一文本归一化入口。
2. 对可疑乱码（UTF-8/Latin-1、UTF-8/GBK 式 mojibake）进行检测。
3. 能修则修；无法安全修复时直接在导出/验证阶段失败，而不是输出脏文档。

落点：

1. `writing_agent/document/v2_report_docx_helpers.py`
2. `writing_agent/document/v2_report_docx.py`
3. 如有必要，补充到运行时最终归一化链路

实施要求：

1. 新增统一文本规范化函数，用于 heading / paragraph / keywords / references / captions。
2. 新增可疑乱码检测函数，支持关键词和参考文献区域重点检查。
3. 导出前执行扫描并记录结构化问题；问题无法修复时拒绝通过。

### 6.2 Evidence-Driven Section Budget：章节级证据预算重平衡

目标：

1. 将 section contract 从“平均分配”升级为“平均分配 + 证据上限约束”。
2. 给每章计算 `supported_chars`，并用它限制 expand/top-up 的上限。
3. 证据不足时缩短章节，而不是反复扩写。

落点：

1. `writing_agent/v2/section_contract.py`
2. `writing_agent/v2/graph_runner.py`
3. `writing_agent/v2/graph_runner_runtime.py`

实施要求：

1. 依据 `fact_gain_count`、`source_count`、`fact_density_score`、`stub_mode` 计算章节证据承载字数。
2. 对摘要、关键词、参考文献保留特殊规则，不被普通预算机制破坏。
3. 在 evidence pack 就绪后，对 section contract 执行二次重平衡。
4. 记录结构化事件，输出每章原预算与重平衡预算。

### 6.3 Validator Upgrade：占位残留与信息密度双门禁

目标：

1. 拦截枚举型残留、占位型残留、序号型残留。
2. 对“正确但空洞”的低信息文本增加更稳定的识别方法。

落点：

1. `writing_agent/v2/meta_firewall.py`
2. `writing_agent/v2/final_validator.py`

实施要求：

1. Meta Firewall 增加以下负样本覆盖：
   - `实验项`
   - `步骤一/步骤二`
   - `序号占位符`
   - `占位符`
   - `待补充`
   - `[数字]；` / `[number];`
2. Final Validator 增加段落级信息密度指标：
   - 内容词密度代理（名词/术语/数字/英文术语/引用锚点比例）
   - 连接词过多且有效实体过少的段落标记为低信息段落
3. 低信息段落比例超阈值时，`semantic_passed=false`。
4. 输出命中样本与统计指标，便于追查。

### 6.4 Section-Scoped RAG Gate：章节级相关性收紧

目标：

1. 在章节 evidence context 进入 writer 之前，先按 `section_title` 做过滤。
2. 避免总标题相关、但章节标题无关的材料进入该章上下文。

落点：

1. `writing_agent/v2/rag_gate.py`
2. `writing_agent/v2/graph_reference_domain.py`
3. `writing_agent/v2/graph_runner_runtime.py`

实施要求：

1. 支持 `section_title` 与 `document_title` 双重输入的 gate。
2. 章节过滤默认阈值高于全局 reference gate。
3. 对 evidence pack 中的 `sources` 和 `facts` 同时做收缩。
4. 记录被剔除条目的 `reason / section / theme_score / entity_aligned`。

## 7. 本轮不做的事项

以下事项保留在后续轮次，不作为本轮阻塞项：

1. 全面重写为 XML Prompt 协议。
2. 完整的 Section UID 生命周期重构与聚合器不可变性改造。
3. 独立 ReferenceAgent 的格式化沙盒重做。
4. 在线学术 API 的完整 authority weighting 与长期缓存策略。
5. Token anomaly kill-switch 与索引 compact 定时任务。

## 8. 验收标准

### 8.1 文本与导出

1. 标题、摘要、关键词、参考文献、图注、表注不得出现可疑乱码。
2. 导出链路中若检测到可疑乱码，必须返回失败或在日志中给出结构化 failure reason。

### 8.2 预算与扩写

1. 章节预算事件中必须能看到 evidence-driven rebalance 结果。
2. 证据不足时，系统应收缩预算，而不是继续模板补齐。

### 8.3 质量门禁

1. `实验项/步骤一/序号占位符/待补充/[数字]；` 等残留必须能触发拦截。
2. 低信息密度段落占比超阈值时，最终文档必须判为 `semantic_passed=false`。

### 8.4 RAG 对齐

1. 章节 evidence gate 需要输出 dropped rows。
2. 章节主题明显不一致的证据不得继续进入该章节 writer prompt。

## 9. 测试要求

本轮至少补齐以下验证：

1. 编码归一化与可疑乱码检测单测。
2. section contract evidence rebalance 单测。
3. final validator 占位残留与信息密度单测。
4. section-scoped RAG gate 单测。
5. docx 导出关键词/参考文献中文保持正确的回归测试。

## 10. 交付物

本轮完成后必须同时交付：

1. 本文档对应的代码实现。
2. 相关单元测试与导出回归结果。
3. 至少一轮实际导出结果路径。
4. 若仍失败，必须给出结构化失败原因，禁止伪成功。

## 11. 本轮实际落地结果（已完成）

### 11.1 已修改代码

1. `writing_agent/v2/section_contract.py`
   - 新增 evidence-driven contract rebalance。
   - 新增 `estimate_supported_chars` 与 `rebalance_contracts_by_evidence`。
2. `writing_agent/v2/graph_runner.py`
   - 新增 `_rebalance_section_contracts` 包装入口。
   - 在 evidence pack 构建中加入 section-scoped RAG gate。
   - 新增 context/facts 过滤辅助函数。
3. `writing_agent/v2/graph_runner_runtime.py`
   - 新增章节级 contract rebalance 回写逻辑。
   - 新增 `section_rag_gate_dropped` 事件与 evidence pack 字段透传。
4. `writing_agent/v2/rag_gate.py`
   - 新增 `section_theme_consistency_score`。
   - 新增 `filter_sources_for_section`。
5. `writing_agent/v2/meta_firewall.py`
   - 新增占位残留模式拦截。
6. `writing_agent/v2/final_validator.py`
   - 新增 placeholder residue ratio。
   - 新增 information density fail ratio。
   - 修正参考文献章节识别逻辑中的历史乱码常量依赖。
7. `writing_agent/document/v2_report_docx_helpers.py`
   - 新增导出文本归一化函数。
   - 新增导出阶段可疑乱码扫描。
   - 修正参考文献定位逻辑对乱码字面量的依赖。
8. `writing_agent/document/v2_report_docx.py`
   - 标题导出改为先经过 heading sanitation。
   - 导出前新增 mojibake 片段硬拦截。

### 11.2 新增测试

1. `tests/unit/test_section_contract_evidence_rebalance.py`
2. `tests/unit/test_rag_gate_section_scope.py`
3. `tests/unit/test_final_validator_density_and_placeholders.py`
4. `tests/unit/test_docx_encoding_guards.py`
5. `tests/unit/test_runtime_skip_plan_detail.py`（新增 fixed outline lock 回归）
6. `tests/unit/test_runtime_output_normalization.py`（新增 unexpected heading prune 回归）
7. `tests/unit/test_final_validator.py`（覆盖结构越界后的 validator 行为）

### 11.3 验证结果

1. 定向新增测试：10 passed
2. 扩大回归：90 passed
3. 真实导出验证产物：
   - `deliverables/architecture_impl_docx_export_20260312_161107/final_output.docx`
   - `deliverables/architecture_impl_docx_export_20260312_161107/RUN_SUMMARY.json`
4. 导出验证结论：关键词与参考文献标题在故意注入 mojibake 输入后仍能被修复并正确写入 docx。

### 11.4 当前仍未彻底闭环的问题

1. 真实生成链路仍存在中文主题质量、参考文献质量和事实密度不足时的退化风险。
2. 本轮已将章节级 RAG gate、章节预算、导出编码防线，以及固定目录硬约束补齐；剩余风险已不再是“固定目录漂移”本身。
3. 因此，本轮交付结论是：
   - P0 修复已完成：编码链路统一、章节预算证据化、占位/低信息门禁增强、章节级 RAG gate 已落地。
   - 本轮新增完成：fixed outline lock、最终输出硬裁剪、validator 结构越界拒收已落地。
   - 后续高优先级工作应聚焦中文真实生成质量、参考文献质量和事实充分性，而不是继续放松结构门禁。

### 11.5 本轮追加收紧（2026-03-12 晚间）

1. `writing_agent/v2/graph_runner_runtime.py`
   - 将 `WRITING_AGENT_FORCE_REQUIRED_OUTLINE_ONLY` 从“只影响 merge 分支”收紧为真正的 runtime 白名单锁。
   - 固定目录模式下直接回写 `_allowed_sections` 与 `must_include`，并发出 `required_outline_lock` 事件。
   - 在 `struct_plan` 生成前对 `plan_map` 做 allowed-sections 裁剪与缺项回填，避免缓存或 planner 残留把额外章节带入 worker。
   - 重写 `_normalize_final_output`：不再按位置重命名章节，而是按允许目录重组正文，直接丢弃不在白名单内的 heading 与其正文块。
2. `writing_agent/v2/final_validator.py`
   - 结构门禁升级为：`missing_sections + unexpected_sections + duplicate_sections(exceed-expected-count) + section_order_passed` 四联判定。
   - 即使上游漏掉裁剪，只要最终文档仍出现额外章节，也会被 `structure_passed=false` 拒收。
3. 新增/补强回归：
   - `tests/unit/test_runtime_skip_plan_detail.py`：验证 fixed outline lock 后 `struct_plan` 只保留指定章节。
   - `tests/unit/test_runtime_output_normalization.py`：验证最终输出会清除 `Related Work` 等越界章节。
   - `tests/unit/test_final_validator_density_and_placeholders.py`：验证 unexpected section 与顺序漂移会导致失败。
4. 本轮验证结果：
   - 定向收紧回归：10 passed
   - 扩大回归：90 passed
5. 新增真实 smoke 证据：
   - `deliverables/fixed_outline_lock_smoke_20260312_180454/RUN_SUMMARY.json`
   - `deliverables/fixed_outline_lock_smoke_20260312_180454/final_output.md`
   - 结果：`required_outline_lock` 生效，`struct_plan_titles` 与固定目录一致，最终 `final_validation.passed=true`，且未出现 `Related Work`、`Data Source and Retrieval Strategy`、`System Design and Implementation`。
6. 对“仍未彻底闭环问题”的更新：
   - “强制严格按指定目录生成”的 runtime/normalize/validator 三层硬约束已落地。
   - 当前剩余风险不再是固定目录漂移本身，而是更高层的中文真实生成质量、参考文献质量和事实密度质量。

### 11.6 本轮继续收紧（2026-03-12 夜间）

1. `writing_agent/v2/final_validator.py`
   - 将参考文献门禁从“只统计数量”收紧为“数量 + 质量”双重判定。
   - 新增参考文献提取与质量度量辅助函数：连续编号检查、重复条目检查、弱引用（placeholder / 过短 / 缺少年份或 locator）检查。
   - validator 返回新增字段：`reference_quality_passed`、`reference_sequence_passed`、`reference_quality_issues`、`weak_reference_items`、`duplicate_reference_items` 等，用于追踪细粒度失败原因。
2. `writing_agent/v2/graph_runner_runtime.py`
   - 新增 `_starvation_failure_decision(...)`，在 evidence 模式下按“实质章节数据饥饿占比”进行硬失败判定。
   - 默认新增阈值环境变量：`WRITING_AGENT_RAG_DATA_STARVATION_FAIL_RATIO=0.25`；支持保持旧布尔开关 `WRITING_AGENT_RAG_DATA_STARVATION_FAIL` 作为更强开关。
   - 忽略 `摘要/关键词/参考文献` 这些不应进入饥饿比例的节区，只对实质正文章节进行门禁判定。
   - 运行时新增 `rag_data_starvation_gate` 事件和 `quality_snapshot` 相关指标，包含 `ratio / threshold / triggered`。
   - 终态失败原因细化：参考文献数量不足、编号断裂、重复引用、弱引用质量问题不再全部折叠成同一个 failure reason。
3. 新增 / 更新回归：
   - `tests/unit/test_final_validator.py`：补充参考文献质量通过 / 失败断言。
   - `tests/unit/test_runtime_starvation_gate.py`：新增章节级 starvation ratio gate 测试，验证触发和忽略摘要 / 参考文献等节区的行为。
4. 本轮验证结果：
   - 定向测试：`21 passed`
   - 扩大回归：`93 passed`
5. 这一轮“收紧”完成后的状态更新：
   - fixed outline lock 已从结构层闭环，当前优先级上移到“文献质量”与“事实充分性”两条质量链。
   - evidence 模式下已不再允许“多章节缺料但仍成功”的伪成功结果。
   - 参考文献也不再是“数量达标即通过”，而是必须同时通过编号连续、无重复、无弱引用残留的质量检查。

### 11.7 更严格的 smoke 验证（2026-03-12 21:19）

1. `writing_agent/v2/final_validator.py`
   - 新增 `empty_sections` 检测，空章节会直接导致 `structure_passed=false`。
   - 新增未格式化参考文献行检测，异常行会计入 `reference_unformatted_lines_detected`。
   - validator 输出补充 `empty_sections`、`unformatted_reference_count`、`unformatted_reference_items` 等字段，便于定位失败根因。
2. `writing_agent/v2/graph_runner_runtime.py`
   - 将 final validator 的空章节结果映射为明确 failure reason：`final_validation_empty_sections`。
   - 将 starvation ratio 默认阈值进一步收紧到 `0.25`，避免多章节缺料仍被放行。
   - 对参考文献污染类结果补充更细的 failure reason 映射，避免全部折叠成单一失败原因。
3. 新增 / 更新回归：
   - `tests/unit/test_final_validator_density_and_placeholders.py`：覆盖空章节失败断言。
   - `tests/unit/test_final_validator.py`：覆盖未格式化参考文献断言。
   - `tests/unit/test_runtime_starvation_gate.py`：覆盖更严格默认阈值 `0.25` 的行为。
4. 验证结果：
   - 定向测试：`27 passed`
   - 扩大回归：`96 passed`
5. 真实 smoke 证据：
   - `deliverables/codex_smoke_test_20260312_211910/codex_openai_compat/RUN_SUMMARY.json`
   - `deliverables/codex_smoke_test_20260312_211910/codex_openai_compat/final_output.md`
   - `deliverables/codex_smoke_test_20260312_211910/codex_openai_compat/final_output.docx`
   - `deliverables/codex_smoke_test_20260312_211910/codex_openai_compat/raw_events.jsonl`
6. 结果说明：
   - 本轮 smoke 已不再把“空章节但总字数达标”的结果视为成功。
   - 失败时会明确给出 `status=failed` 与 `failure_reason=final_validation_empty_sections`。
   - `rag_data_starvation_gate` 现在可见更严格的阈值与 ratio 事件，便于区分“证据饥饿”与“结构污染”。
7. 当前判断：
   - 结构层面的空章节伪成功已被堵住；后续重点转向缓存污染、元数据编码与真实中文质量。

### 11.8 缓存文本与中文间距修复（2026-03-12 23:20）

1. `writing_agent/v2/graph_text_sanitize_domain.py`
   - 调整 `sanitize_output_text(...)`，修复中文标题与正文边界被异常空格打断的问题。
   - 修复 `## 标题\n\n正文...` 被错误拼接成同一行的情况，保证 heading/body 边界稳定。
   - 增补对 `(?<=[\u4e00-\u9fff])[ \t\u3000]+(?=[\u4e00-\u9fff])` 的清理，减少中文内部异常空格。
2. `writing_agent/v2/graph_runner_runtime.py`
   - 新增缓存修复辅助函数：`_repair_mixed_cached_mojibake`、`_decode_cache_literal_escapes`、`_normalize_cached_keywords`、`_usable_cached_section_text`。
   - 统一处理 UTF-8 mojibake、literal escape residue 和缓存章节污染，避免旧缓存把脏文本重新注回运行时。
   - 在缓存命中路径上增加更严格的可用性判断，降低缓存污染扩散到导出阶段的概率。
3. 风险收口：
   - `assembly_map` 中的关键词 / 参考文献残留不再直接信任缓存，必须经过 `sanitize_output_text(...)` 与运行时归一化。
   - 对疑似 Latin-1 mojibake 的文本优先在 runtime 修复，避免把问题拖到 docx 导出再暴露。
4. 相关测试：
   - `tests/unit/test_generation_residue_and_reference_guards.py`
     - `test_sanitize_output_text_preserves_cjk_heading_body_boundaries`
   - `tests/unit/test_runtime_json_cache.py`
     - `test_prime_cached_sections_repairs_keyword_escape_residue`
5. 验证结果：
   - 定向测试：`53 passed`
   - 扩大回归：`60 passed`
   - 真实 smoke：`deliverables/codex_smoke_test_20260312_231925/codex_openai_compat/final_output.md`
   - 真实 smoke docx：`deliverables/codex_smoke_test_20260312_231925/codex_openai_compat/final_output.docx`
   - 真实 smoke 事件：`deliverables/codex_smoke_test_20260312_231925/codex_openai_compat/raw_events.jsonl`
   - 关键结果：`status=success`、`quality_passed=true`、`empty_sections=[]`、`meta_hits=[]`、`reference_gate_passed=true`
6. 风险更新：
   - 缓存污染与中文边界错乱已被显著收敛，但真实生成质量仍需继续靠章节级质量热采样与定向修订闭环。

### 11.9 原创性热采样与风险章节定向修订（2026-03-14）

1. `writing_agent/v2/final_validator.py`
   - 新增原创性风险门禁：`formulaic_opening_ratio` 与 `source_overlap_ratio`。
   - 终态 `quality_snapshot` 现在会输出章节级原创性热采样摘要，便于定位高风险节区，而不是只给全局通过 / 失败。
2. `writing_agent/v2/graph_runner_runtime.py`
   - 增加章节级 originality hot sample，在 section worker 输出后立即抽样检查套话开头、来源重叠与重复句式。
   - 热采样结果会写回 `quality_snapshot.section_originality_hot_sample`，并输出 rewrite / retry / cache_rejected / fast_draft_rejected 等计数。
3. `writing_agent/web/services/generation_service.py`
   - `revise_doc()` 新增 `target_section` 支持。
   - 新增 `_resolve_target_section_selection(...)`，仅重写指定节区。
   - 当 `target_section` 未命中时，服务直接返回 `HTTP 400`，禁止静默回退到全文修订。
4. `scripts/targeted_revision_utils.py`
   - 新增 `pick_top_risk_sections(...)` 与 `run_targeted_section_revisions(...)`。
   - 运行脚本会优先挑选原创性热采样中失败 / 重写次数高的章节，执行保守的一轮定向修订。
5. 运行脚本已接入定向修订与摘要透传：
   - `scripts/run_dual_provider_high_quality_cn.py`
   - `scripts/run_codex_full_with_figures_utf8.py`
   - `scripts/run_codex_forced_figure_and_refs_validation.py`
   - `scripts/run_summary_utils.py`
6. 前端工作台补充：
   - `writing_agent/web/frontend_svelte/src/AppWorkbench.svelte` 现在展示章节级原创性风险摘要。
   - UI 提供“定向修订”按钮，可直接对高风险章节调用服务侧 `target_section` 修订，不再只能全文回炉。
7. 新增测试：
   - `tests/unit/test_generation_service_target_section_selection.py`
   - `tests/unit/test_targeted_revision_utils.py`
   - `tests/unit/test_run_summary_utils.py`
   - `tests/unit/test_runtime_section_originality_hot_sample.py`
   - `tests/unit/test_final_validator_originality_guards.py`
8. 本轮剩余风险与后续事项：
   - 目前的定向修订仍是保守单轮策略，后续可继续升级为“按风险顺序迭代多轮，但必须有 token 上限保护”。
   - 原创性热采样目前已接入运行脚本和工作台，但仍需继续观察真实长文场景下的误报率。
   - 系统明确不做“规避 AI 检测器”式实现；后续只会继续提升原创性、事实密度和模板化抑制，而不会做规避检测的对抗逻辑。

## 12. 更新后的剩余风险与后续事项

1. 真实长文场景下，中文事实密度不足仍可能触发过度保守的失败；需要继续提高章节级 RAG 供料质量，而不是放松门禁。
2. 前端已能展示原创性热区并发起定向修订，但还需要在完整 UI 流程里补充更细的 revision telemetry 展示。
3. 当前脚本侧的定向修订采用小范围一轮修订，适合作为保守收口；若后续扩展为多轮，必须同步引入 token 异常熔断。
4. 真实导出长文的最终质量，仍取决于高质量参考文献、章节证据密度和图片素材质量；这些仍是后续持续优化重点。
