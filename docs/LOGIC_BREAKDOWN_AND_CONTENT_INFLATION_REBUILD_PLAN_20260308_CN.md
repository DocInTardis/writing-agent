# 逻辑崩坏与内容注水治理方案（2026-03-08）

## 1. 背景与问题定义

当前系统出现的核心问题不是单点 Prompt 质量，而是“约束系统熵增”导致的结构性失控：

1. 元指令残留（Prompt Contamination）进入正文并被重复扩写。
2. 字数约束失衡（尤其摘要/关键词）触发无意义注水。
3. 章节结构与论文范式冲突（CiteSpace 题目却输出工程实现模板）。
4. RAG 主题漂移，检索高被引但无关内容污染正文。
5. 质量门禁偏重“形式达标”，缺少“语义正确性”硬约束。

目标：将系统从“模板拼接+字数驱动”改为“范式锁定+语义验收驱动”，并彻底消灭伪成功。

---

## 2. 设计原则（必须同时满足）

1. 范式优先：先判论文范式，再决定结构、证据和写作策略。
2. 语义优先：任何字数补齐不能破坏主题一致性。
3. 失败可解释：不满足门禁时必须 `failed`，附结构化 `failure_reason`。
4. 双层防护：规则过滤（快）+ Refiner 重写（准）联合工作。
5. 可追溯：每次拦截、回退、失败都产出事件证据。

---

## 2.1 第一阶段（Step 1）：多模型兼容基础能力

该目标可行，且应作为本次重构的第一步先落地：

1. 系统必须同时支持本地开源模型（如 Ollama）与远端 API 模型（OpenAI 兼容）。
2. 用户可以通过配置/API Key 使用外部模型，不再被单一模型栈绑定。
3. 运行时支持按任务路由到不同模型，并保留可回退能力。

### 2.1.1 当前约束与事实

1. 项目已存在 OpenAI Compatible Provider，但部分核心链路仍直接使用 `OllamaClient`。
2. OpenAI Compatible Provider 当前使用 `chat/completions` 协议，不是 `responses` 协议。
3. 因此“仅配置 API Key”不足以完成全链路切换，必须做 provider 抽象统一改造。

### 2.1.2 目标状态

1. 所有生成/分析/修订/聚合链路统一走 `LLMProvider` 接口，不允许直连具体厂商 SDK。
2. 支持 provider 类型：
   - `ollama`（本地开源）
   - `openai_compatible`（远端 API Key）
   - `node_gateway`（可选网关）
3. 支持按任务配置模型：
   - `model`
   - `review_model`
   - `reasoning_effort`（可选）
4. 支持安全地配置 API Key（环境变量/密钥管理），禁止明文入库。

### 2.1.3 最小可落地执行清单

1. Provider 抽象统一：
   - 将 `graph_runner / graph_runner_runtime / graph_aggregate_domain / graph_reference_domain` 等路径中的 `OllamaClient` 直连替换为 `get_default_provider(...)` 注入。
2. 配置统一：
   - 支持 `WRITING_AGENT_LLM_PROVIDER`、`WRITING_AGENT_OPENAI_BASE_URL`、`WRITING_AGENT_OPENAI_API_KEY`、`WRITING_AGENT_OPENAI_MODEL`。
3. 连通性预检（启动前）：
   - `/models` 探活；
   - 一次最小 `chat/completions` 调用探活；
   - 失败时返回结构化错误，不进入生成主流程。
4. 协议兼容策略：
   - 第一版先稳定 `chat/completions`；
   - 第二版再增加 `responses` 适配器（若目标服务要求）。
5. 回退策略：
   - 远端 provider 不可用时，根据配置决定是否自动回退本地 provider。

### 2.1.4 安全与密钥治理（强制）

1. API Key 仅允许通过环境变量或密钥服务注入。
2. 日志与事件流对 Key 做脱敏，禁止原文输出。
3. 一旦 Key 在对话/日志中暴露，必须立即吊销并轮换。
4. 密钥错误返回：
   - `failure_reason=api_auth_failed`
   - `failure_reason=api_provider_unreachable`

### 2.1.5 验收标准（Step 1 DoD）

1. 同一套生成链路可在 `ollama` 与 `openai_compatible` 间切换运行。
2. 输入合法 API Key 后可完成一次完整生成与导出。
3. API 不可达/鉴权失败时可解释失败，不出现伪成功。
4. 全链路不再依赖写死的 `OllamaClient` 直连。

---

## 3. 核心架构重构

## 3.1 范式锁（Paradigm Lock）

### 3.1.1 范式分类

统一定义文档范式：

- `bibliometric`（文献计量/可视化分析）
- `engineering`（系统设计/工程实现）
- `empirical`（实证研究）

### 3.1.2 锁定内容

范式锁不仅锁章节骨架，还锁语料权重和证据类型：

- Bibliometric：优先使用“中心度、聚类标签、突现词、发文量时序、合作网络”。
- Engineering：优先使用“架构、模块职责、流程、伪代码、实验验证”。

### 3.1.3 冲突与失败语义

- 如果题目/用户目标是 `bibliometric`，但规划结果包含大量工程章节且无法纠正：
  - `status=failed`
  - `failure_reason=paradigm_conflict`
- 如果 RAG Top-K 与范式相似度低于阈值（建议 0.4）：
  - `status=failed`
  - `failure_reason=data_insufficient`

禁止用 fallback 文本掩盖失败。

### 3.1.4 容错与反馈（分类低置信处理）

为避免分类器误判导致全链路失败，分类器输出必须包含：

- `paradigm`
- `confidence`
- `runner_up`
- `margin`（第一候选与第二候选差值）
- `reasons`

低置信触发条件建议：

- `confidence < 0.8` 或
- `margin < 0.15`

低置信处理策略：

1. 在 Planner 阶段触发 `dual_outline_probe`（双大纲预演）：
   - 同时生成两个候选范式目录；
   - 由轻量 Quality Gate 做结构匹配与主题一致性初筛；
   - 选择得分更高者进入主流程。
2. 提供 `user_paradigm_override` 手动修正入口（UI 或 API）。
3. 记录 `override_source` 与 `classifier_meta` 供追踪回放。

相关失败语义：

- `failure_reason=paradigm_low_confidence_unresolved`
- `failure_reason=paradigm_override_conflict`

---

## 3.2 章节级约束合同（Section Contract）

每章必须有合同，不允许统一按“凑字数”处理。

合同字段建议：

- `section_name`
- `purpose`
- `allowed_content_types`
- `required_slots`
- `char_range`
- `min_paragraphs`
- `citation_policy`
- `rag_scope`
- `forbidden_patterns`

### 3.2.1 推荐字数/结构（文献计量论文）

1. 摘要：300-500字
2. 关键词：3-8个词条（按词条数量约束，不做 600+ 字约束）
3. 引言：1200-1800字
4. 数据来源与检索策略：800-1200字
5. 发文量时空分布：1000-1500字
6. 作者与机构合作网络：1000-1500字
7. 关键词共现与聚类分析：1200-1800字
8. 研究热点演化与突现分析：1200-1800字
9. 讨论：1000-1500字
10. 结论：600-1000字
11. 参考文献：按条目数约束，不作为正文凑字来源

### 3.2.2 Slot Filling（替代笨重 Filler）

当章节不足时，补“槽位”而不是补“套话”。

示例（关键词章节）：

- `keywords: list`
- `descriptions: string`
- `relations(optional): string`

如果字数不足，优先扩写关键词内涵、边界、相互关系；禁止拉入无关文献统计。

---

## 3.3 元指令防火墙（Meta Firewall）

双层实现：

1. 规则层：正则 + 黑名单，快速拦截元话语。
2. Refiner 层：触发 `REWRITE_WITHOUT_META` 重写。

### 3.3.1 黑名单（起始）

建议最小集合：

- `应涵盖`
- `旨在界定`
- `补充方法`
- `建立统一语义`
- `强化了结论`
- `topic:`
- `doc_type:`
- `key points:`

### 3.3.2 自动处理策略

- 命中硬规则：段落标记为 `rewrite_required`
- 重写失败连续 2 次：章节失败
- 全文重写比例 >30%：判定上游规划/提示失真，直接失败

失败语义：

- `failure_reason=meta_residue_unrecoverable`

### 3.3.3 防止“死循环重写”（Feedback Rewrite）

重写不允许无反馈盲重试，必须使用“反馈式重写”：

1. Refiner 命中后，不仅返回 `rewrite`，还返回具体命中片段与禁用原因；
2. Drafter 下一次重写必须接收该反馈（Instructional Feedback）；
3. 超出预算立即失败，禁止无限重试。

建议预算：

- 每段 `max_rewrite_attempts=2`
- 每节 `max_rewrite_blocks=8`
- 全文 `max_rewrite_ratio=0.3`

触发失败：

- `failure_reason=rewrite_budget_exhausted`
- `failure_reason=meta_residue_unrecoverable`

---

## 3.4 “不注水补齐”机制

## 3.4.1 维度展开法（Dimension Expansion）

当字数不足时，只允许新增“信息维度”，禁止同义重复。

默认展开维度：

1. 与同类研究对比
2. 区域差异（如东部/西部农村）
3. 政策影响与治理机制差异
4. 方法边界与局限
5. 可复核性与可复现条件

### 3.4.2 新信息校验

新增段落必须满足以下至少一项：

- 引入新事实/新变量
- 引入新对比对象
- 引入新因果链
- 引入新证据来源

否则判定 `redundant_expansion`，不计入补齐。

---

## 3.5 RAG 主题一致性闸门

## 3.5.1 三道闸

1. 粗筛：标题关键词覆盖（词面）
2. 重排：语义相似度阈值
3. 章节落地：与当前章节目标匹配

### 3.5.2 核心语义重叠度

计算建议：

`overlap = |Intersection(检索文档关键词, 标题核心关键词)| / |标题核心关键词|`

规则建议：

- `overlap < 0.4`：剔除
- 如果仅单个泛词（如“农村”）重叠，且缺少“区块链/社会化服务/CiteSpace”等核心词，剔除

失败语义：

- `failure_reason=rag_topic_drift`

### 3.5.3 实体对齐硬约束（落地闸）

在落地闸增加“核心实体对齐”检查：

1. 从标题抽取核心实体（如：区块链、农村社会化服务、CiteSpace）；
2. 候选文献需满足实体覆盖与语义重叠双阈值；
3. 若标题包含关键实体（例如“区块链”），候选文本必须命中同义实体集合。

示例（区块链同义集合）：

- `区块链`
- `分布式账本`
- `智能合约`
- `链上`

若候选文献仅命中泛词（如“农村”）而未命中核心实体，直接剔除。

相关失败语义：

- `failure_reason=rag_entity_mismatch`
- `failure_reason=rag_topic_drift`

---

## 3.6 质量门禁重建（形式 + 语义双通过）

仅“字数/章节数”达标不再视为成功。

必须通过以下联合门禁：

1. 结构正确：章节顺序与范式一致
2. 主题一致：章节与标题核心语义一致
3. 元指令残留率：必须为 0（或极低阈值）
4. 重复率：低于阈值
5. 无依据量化结论：严格受控（百分比结论需证据）
6. 引用相关性：每条引用需通过主题校验

任何一项失败：

- `status=failed`
- 禁止回写 `success`

---

## 4. 统一状态与异常语义

系统状态仅允许：

- `success`
- `failed`
- `interrupted`

错误码建议：

- `paradigm_conflict`
- `data_insufficient`
- `rag_topic_drift`
- `meta_residue_unrecoverable`
- `redundant_expansion`
- `quality_gate_not_passed`
- `paradigm_low_confidence_unresolved`
- `paradigm_override_conflict`
- `rewrite_budget_exhausted`
- `rag_entity_mismatch`

禁止状态：

- 伪成功（看似结构完整但语义失真）

---

## 5. 逻辑流程（目标版）

1. Input：题目/要求
2. Classifier：判定范式并输出置信度
3. Low-Confidence Router：必要时触发双大纲预演或用户覆盖
4. Planner：生成范式专属 Skeleton
5. Contractor：下发章节合同（字数、槽位、RAG范围、禁用模式）
6. Drafter：生成初稿
7. Meta Firewall：规则扫描 + Refiner 反馈式重写
8. Consistency Gate：语义一致性 + RAG 实体对齐校验
9. Final Aggregate：仅通过门禁后导出

---

## 6. Refiner 模板（REWRITE_WITHOUT_META）

```text
<System>
你是学术文本净化与重写器。目标是把输入段落改写为可发表风格正文。
你必须删除所有“写作指令/过程解释/元话语”，并保持原主题一致。
禁止输出：本段旨在、本节将、应当涵盖、需要说明、topic:, doc_type:, key points:, 写作要求。
如果输入与主题明显无关，返回 failed 而不是编造。
</System>

<User>
<task>REWRITE_WITHOUT_META</task>
<section>{section_name}</section>
<topic>{title}</topic>
<topic_keywords>{kw1,kw2,kw3}</topic_keywords>
<input_paragraph>
{paragraph_text}
</input_paragraph>

<output_schema>
返回严格 JSON:
{
  "status": "success|failed",
  "clean_text": "重写后的纯正文",
  "failure_reason": "",
  "removed_patterns": ["..."],
  "topic_overlap_score": 0.0
}
</output_schema>

<quality_rules>
1) 不得出现元指令句式。
2) 不得新增无依据数字结论（如提高30%）。
3) 必须与 topic_keywords 至少 40% 语义重叠。
4) 保持该 section 的语体角色。
</quality_rules>
</User>
```

---

## 7. Python 规则防火墙参考（可直接工程化）

```python
META_HARD_PATTERNS = [
    r"^(摘要|关键词|引言|本节|本段|本章).{0,12}(应|需|旨在|将|建议)",
    r"(应当涵盖|需要说明|补充方法路径|建立统一语义|可复核|可复现)",
    r"^(topic|doc_type|key\s*points?|analysis_summary|plan_hint)\s*:",
    r"(作为AI|写作要求|以下要求|禁止输出|违者扣分)",
]

META_SOFT_PATTERNS = [
    r"(围绕|针对).{0,20}(应说明|需交代|补充)",
    r"(本研究进一步明确了|强化了结论|边界条件如下)",
    r"(综上所述|总而言之|通过上述分析)，我们可以看到",
    r"本研究旨在通过.+来达到.+(的目标|目的)",
    r"由于.+的原因，因此.+",
]

# 判定策略：keep | trim | rewrite | fail
# 命中硬规则 -> rewrite
# 连续重写失败 >= 2 -> fail
# 全文 rewrite 比例 > 30% -> fail
# 分章节启用建议：
# - 在“结论”章节，对“综上所述”类表达降级为 soft warning，避免误杀。
# - 同段命中 >=2 个 soft 模式再触发 rewrite，单命中且主题重叠高可 trim/keep。
```

---

## 8. 落地顺序（建议执行顺序）

1. 多模型兼容基础能力（Provider 统一 + API Key 接入）
2. 范式锁与冲突失败语义
3. 章节合同与字数重分配（修复摘要/关键词失衡）
4. Slot Filling 替换传统 Filler
5. 元指令防火墙 + Refiner 链路
6. RAG 主题闸门
7. 双门禁验收（结构+语义）
8. 全链路观测与回归测试

---

## 9. 验收标准（DoD）

1. CiteSpace 题目不再输出工程实现章节。
2. 摘要不再出现“摘要应当如何写”等元指令残留。
3. 关键词章节不再出现无关文献统计注水。
4. RAG 引用主题相关率达到设定阈值。
5. 质量门禁失败时严格返回 `failed`，无伪成功。
6. 导出文本通过人工抽检：逻辑连续、主题一致、可复核。

---

## 10. 备注

本方案是“系统架构级重构”，不是 Prompt 微调。若只做提示词修补而不做门禁重建，问题会在高压力约束（长文本、严格字数、复杂主题）下复发。
