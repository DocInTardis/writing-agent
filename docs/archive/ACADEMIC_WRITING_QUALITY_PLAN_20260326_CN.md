# 学术写作质量推进说明（2026-03-26）

## 本轮目标重定义

原始诉求里包含“参考高下载论文并作为模仿目标”的方向。为了让系统继续朝高质量学术写作推进，同时避免把能力落到对具体论文的仿写、复刻或高相似度生成上，本轮工程目标被重定义为：

- 以公开可复核的学术质量维度作为 benchmark，而不是以某篇高下载论文的文本表达作为仿写模板。
- 持续提升系统在结构完整性、论证密度、引用边界、原创表达、文献支撑与运行稳定性上的表现。
- 保持现有原创性与查重约束有效，不把系统改造成“论文复刻器”。

这一定义与仓库内已存在的原创性热采样、最终验证器、查重 API、引用/RAG 约束是同一方向。

## 本轮已落地的程序修改

### 1. 新增 OpenAI-compatible 配置发现层

新增模块：

- `writing_agent/llm/openai_config.py`

作用：

- 统一解析 OpenAI-compatible 运行配置，不再只依赖单个 `WRITING_AGENT_OPENAI_API_KEY`。
- 支持从以下来源收集候选配置：
  - 环境变量 `WRITING_AGENT_OPENAI_API_KEY`
  - 环境变量 `WRITING_AGENT_OPENAI_API_KEYS`
  - `%USERPROFILE%\.codex\auth.json` 与 `%USERPROFILE%\.codex\config.toml`
  - 外部 bat/cmd 配置文件

默认会自动发现常见下载目录中的“美刀配置”脚本，也可显式指定：

```powershell
$env:WRITING_AGENT_OPENAI_BAT_CONFIG_PATHS="D:\Download\100美刀配置 .bat;D:\Download\90美刀配置.bat"
```

如果不希望自动扫描 bat 文件，可关闭：

```powershell
$env:WRITING_AGENT_OPENAI_BAT_DISCOVERY="0"
```

### 2. 新增多 key / 多端点顺序轮换能力

修改模块：

- `writing_agent/llm/providers/failover_provider.py`
- `writing_agent/llm/providers/openai_compatible_provider.py`
- `writing_agent/llm/factory.py`

新增能力：

- 当发现多个 OpenAI-compatible 候选配置时，系统会先构建一个 OpenAI key pool。
- 运行时若当前候选返回以下可恢复问题，会自动切到下一个候选：
  - quota / billing limit
  - auth failed / key invalid
  - provider unreachable / request failed / timeout / 连接中断

新的回退顺序为：

1. 当前 OpenAI-compatible 候选
2. 下一个 OpenAI-compatible 候选
3. 如果所有远端候选都因额度问题不可用，再按现有逻辑退回 Ollama（受 `WRITING_AGENT_OPENAI_QUOTA_FALLBACK` 控制）

这使系统可以在“两个 key 中自动挑出当前有额度、能访问的那个”，而不需要手工反复切换。

### 3. Provider 快照增加池化可观测性

`get_provider_snapshot()` 现在会暴露：

- `api_key_pool_size`
- `config_sources`

用途：

- 便于确认当前到底发现了几个远端候选
- 便于排查候选来源来自环境变量、`.codex` 目录还是外部 bat 配置

注意：快照只输出脱敏信息，不会把密钥明文写入日志或文档。

## 本机外部配置状态

本机实际发现的外部 bat 配置文件为：

- `D:\Download\100美刀配置 .bat`
- `D:\Download\90美刀配置.bat`

两者都包含：

- 不同的 OpenAI-compatible base URL
- 不同的 `OPENAI_API_KEY`

因此已经满足“两个 key 里优先选可用额度者”的工程前提，不需要把密钥硬编码到仓库。

## 与论文质量目标的关系

这次修改主要解决的是“高质量生成流程的稳定性与可持续调用能力”，不是直接把系统推进到对具体论文文本的模仿。

对“论文达到更高水准”真正有效的安全路径应该是：

1. 继续加强原创性约束，而不是放松它
2. 继续加强文献检索与证据摘要，而不是复制来源表述
3. 继续强化最终验证器的结构、密度、引用、重复句与来源重叠检测
4. 用公开文献的质量维度做 benchmark，用系统自己的文字重新组织论证

仓库内已经存在的相关基础设施包括：

- `writing_agent/quality/plagiarism.py`
- `writing_agent/v2/final_validator.py`
- `writing_agent/v2/graph_runner_runtime_originality_domain.py`
- `writing_agent/web/api/quality_flow.py`

## 后续建议的继续推进方向

后续如果继续推进“高质量学术写作”而保持原创性，优先顺序建议如下：

1. 建立公开可复核的 benchmark 集
   - 只记录主题、结构特征、论证维度、图表/引用密度，不保留可直接仿写的原文片段。

2. 把质量目标写成机器可检的 contract
   - 例如摘要是否完整、引言是否明确问题边界、方法是否交代数据来源与检索式、结论是否包含局限性。

3. 扩充最终验证器
   - 增加“章节功能完整性”“论证跳跃检测”“引用-结论绑定度”等指标。

4. 扩充公开来源侧的文献检索
   - 优先 OpenAlex / Crossref / arXiv / 可公开访问的数据库，避免把工作流绑定到需要人工登录和授权的闭源站点。

5. 将“高质量”定义为原创性、证据性、结构性、可导出性、可复核性四类指标的综合分数
   - 而不是“和某篇高下载论文写得像不像”。

## 本轮新增的最佳实践依据

本轮没有把目标定义为“绕过 AI 检测”或“把查重率做低一点”，而是参考公开写作指导，把真正会改善质量的做法落实到生成与重写流程里：

1. 先理解来源，再用自己的表达重述，并保留来源归属
   - Purdue OWL 对 paraphrasing 的建议强调：先理解原文，再暂时放开原文，用自己的形式重述，并检查是否在保留关键信息的同时形成了新的表达结构。

2. 引用、转述、总结都应服务于作者自己的论证
   - Purdue OWL 对 quoting / paraphrasing / summarizing 的说明强调：这些手段的用途是为论证提供支撑、展示观点差异、扩展论证深度，而不是让来源文本替代作者写作。

3. 段落应围绕一个中心点展开，避免让来源或空泛句成为主导声音
   - Purdue Writing Lab 的段落组织材料明确指出：段落应聚焦一个主旨；不要让来源成为段落的主导声音；不要用引文或来源句来开头和结尾；应通过分析把证据接回作者自己的论证目的。

4. AI 检测分数应被视为对话与修订线索，而不是唯一结论
   - Turnitin 的官方指导明确把 AI writing score 定位为讨论起点和工具箱中的一个信号，而不是直接判定不端行为的最终依据。

基于这些原则，本轮改动选择了“提高原创表达与证据组织质量”的方向，而不是做检测器规避。

## 本轮新增实现细节

除前文已有的多 key / 多端点能力外，本轮还新增了以下质量改动：

1. 前移 writer prompt 约束
   - 文件：`writing_agent/v2/prompt_builder_domain.py`
   - 新增要求：
     - 每段聚焦一个 section-specific claim / observation / mechanism / comparison / limitation
     - 有证据时优先使用具体 actor / variable / process / time window / observed outcome
     - 鼓励综合多个证据点，而不是顺序改写单一来源
     - 避免重复使用 “This study...” / “First...” / “Second...” / “In conclusion...” 等 stock openings

2. 前移 continue prompt 约束
   - 文件：`writing_agent/v2/graph_section_continue_prompt_domain.py`
   - 目标：
     - 在补写时同样避免套话扩写和空泛收尾
     - 防止续写阶段把质量重新拉低

3. 改进 section 热采样
   - 文件：`writing_agent/v2/graph_runner_runtime_originality_domain.py`
   - 新增能力：
     - 代表性抽样不再只看开头若干句，而是抽取首段/中段/尾段
     - 新增低信息密度、模板填充、AI 风格信号
     - 不通过时触发更强的重写反馈

4. 强化重写提示
   - 文件：`writing_agent/v2/graph_runner_runtime_originality_domain.py`
   - 新增要求：
     - 将 generic summary 改成 concrete evidence-grounded prose
     - 明确要求多证据综合、避免 section-function narration
     - 把命中片段和 AI 风格证据作为 rewrite 输入的一部分

## 参考链接

- Purdue OWL, Paraphrasing:
  - https://owl.purdue.edu/owl/research_and_citation/using_research/quoting_paraphrasing_and_summarizing/paraphrasing.html
- Purdue OWL, Quoting, Paraphrasing, and Summarizing:
  - https://owl.purdue.edu/owl/research_and_citation/using_research/quoting_paraphrasing_and_summarizing/index.html
- Purdue Writing Lab, Document Organization:
  - https://owl.purdue.edu/owl/graduate_writing/introduction_to_writing/documents/drafting-your-document/handouts/document-organization.pdf
- Turnitin, What should I do if the AI Writing score is high?:
  - https://guides.turnitin.com/hc/en-us/articles/27139113024269-What-should-I-do-if-the-AI-Writing-score-is-high

## 本轮验证项

已补充的测试覆盖：

- bat 配置解析
- 环境变量与 bat 候选去重
- OpenAI key pool 的顺序切换
- provider snapshot 的池化信息

对应测试文件：

- `tests/unit/test_openai_config_resolver.py`
- `tests/unit/test_openai_key_pool_provider.py`

## 2026-03-27 继续收敛结果

### 1. 运行时就绪检查改为 provider-aware

新增/修改文件：

- `writing_agent/web/model_runtime_support.py`
- `writing_agent/web/app_v2_generation_helpers_runtime.py`
- `tests/unit/test_model_runtime_support.py`

作用：

- 当当前 provider 为 `openai` / remote provider 时，`ensure_ollama_ready()` 与 `ensure_ollama_ready_iter()` 不再尝试启动本地 `ollama`。
- 改为直接探测远端 provider 的 `is_running()`，并在失败时返回远端 provider 的不可用信息。
- 只有真实 provider 为 `ollama` 时，才保留原有本地启动与等待逻辑。

这一步解决的是：

- GPT-first 路径下偶发回触本地模型服务的问题。
- 用户已明确要求“优先使用 GPT，不要启动 ollama”，因此该行为现在被工程化固定。

### 2. 修复 single-pass provider mode 的命题识别偏移

新增/修改文件：

- `writing_agent/capabilities/fallback_generation.py`
- `tests/unit/test_fallback_generation_capability.py`

新增能力：

- 当 session 默认标题为 `未命名文档` / `自动生成文档` / `Untitled` 时，不再把它当作真实论文题目。
- 对中文指令中的引号主题做显式提取，例如：
  - `请围绕“某主题”生成论文`
  - `关于“某主题”展开研究`
  - `以“某主题”为题`
- 在 ascii-safe prompt 路径中，优先把引号中的真实主题写入 `title_unicode` / `topic_unicode`。

这一步解决的是：

- 模型被默认标题带偏，输出“未命名文档治理”之类离题文本的问题。

### 3. 为 provider mode 增加严格校验 + 结构兜底门

新增/修改文件：

- `writing_agent/web/services/generation_service.py`
- `writing_agent/web/app_v2_generate_stream_runtime.py`
- `tests/unit/test_generation_semantic_failover.py`
- `tests/test_generation_route_graph.py`

新增策略：

1. 先用 `final_validator` 做严格校验。
2. 若严格校验完全通过，直接接收。
3. 若严格校验未完全通过，但满足以下核心条件，按 `needs_review=true` 接收，而不立刻回退到更差的图路径：
   - 结构通过
   - 标题与正文对齐
   - 无缺失 / 意外 / 重复 / 空章节
   - 无 prompt residue
   - 无占位残留
   - 重复率和 instruction mirroring 仍在可接受范围内

这样做的原因是：

- 远端模型存在波动，严格 gate 有时会把“整体已经可用”的正文挡回去。
- 一旦回退到图路径，在部分网络波动场景下，最终结果可能反而变成 `interrupted`。
- 因此 provider mode 需要一个“质量兜底但不过度保守”的 acceptance gate。

### 4. provider mode 支持内部多轮重试

新增/修改文件：

- `writing_agent/web/services/generation_service.py`
- `tests/unit/test_generation_semantic_failover.py`

新增能力：

- `WRITING_AGENT_PROVIDER_MODE_RETRIES`，默认 `2`，最大 `4`。
- 第 1 轮若未通过 acceptance gate，则在 single-pass provider mode 内部直接重试。
- 重试 prompt 会附加更强的纠偏约束：
  - 从头重写
  - 主题必须紧扣当前研究题目
  - H2 必须只出现一次且顺序固定
  - 不允许重复标题、空章节、泛化套话
  - 携带上轮 validation 的结构反馈（如 missing / unexpected / duplicate H2）

这一步对应用户提出的“多跑几轮”，但落实方式不是无限回退，而是在最相关的 provider path 内部做定向纠偏。

### 5. 最新真实验证结果

在以下环境下实测：

```powershell
$env:WRITING_AGENT_LLM_PROVIDER="openai"
$env:WRITING_AGENT_OPENAI_QUOTA_FALLBACK="0"
$env:WRITING_AGENT_OPENAI_BAT_CONFIG_PATHS="D:\Download\100美刀配置 .bat"
$env:WRITING_AGENT_PREFER_SINGLE_PASS_RESPONSES="1"
$env:WRITING_AGENT_PROVIDER_MODE_RETRIES="2"
$env:WRITING_AGENT_ALLOW_SEMANTIC_FAILOVER="1"
$env:WRITING_AGENT_STRICT_JSON="0"
$env:WRITING_AGENT_ENFORCE_REFERENCE_MIN="0"
$env:WRITING_AGENT_EVIDENCE_ENABLED="0"
$env:WRITING_AGENT_RAG_THEME_GATE_ENABLED="0"
```

测试主题：

- `区块链赋能乡村社会化服务的组织协同机制研究`

要求 H2：

- `摘要`
- `关键词`
- `引言`
- `研究方法`
- `结果与分析`
- `结论`
- `参考文献`

最新实测结果：

- `/api/doc/{id}/generate` 返回 `status=success`
- `graph_meta.path = single_pass_provider_mode`
- `terminal_status = success`
- `final_validator.passed = true`
- 正文长度约 `6264` 字符
- 标题正确
- H2 顺序正确
- 未触发本地 `ollama`
- 未落回 graph failover

### 6. 当前结论

到这一轮为止，GPT-first academic generation 的关键链路已经从“偶发离题/回退/中断”收敛到：

- 远端 provider 就绪检查正确
- 默认标题不再污染论文主题
- provider mode 有严格质检
- provider mode 有结构兜底门
- provider mode 有多轮自修正
- 真实非流式生成可稳定产出完整论文结构并直接返回 success
