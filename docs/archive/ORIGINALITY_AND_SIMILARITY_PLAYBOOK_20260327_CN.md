# 原创性与相似度治理手册（2026-03-27）

## 边界

本文档的目标不是“规避查重”或“绕过 AI 检测”，而是把两类指标当作质量信号来治理：

- 对查重：优先减少真实的高重合、错误引用边界和误读相似度报告。
- 对 AI 率：优先减少模板化、低信息密度和过度整齐的机器式表达，降低误判风险。

这与仓库现有方向一致：提高原创性、证据性和可复核性，而不是生成“看起来不像 AI”的空洞文本。

## 系统内现有算法

### 查重

当前实现位置：

- `writing_agent/quality/plagiarism.py`
- `writing_agent/web/api/quality_flow.py`
- `writing_agent/web/services/quality_service.py`

当前混合算法：

1. 字符 `n-gram`：看局部字串重合，输出 `containment` 和 `jaccard_resemblance`。
2. `Winnowing` 指纹：看局部复制块重合，适合发现大段重叠。
3. `SimHash`：看轻改写后的词项相似度。
4. `SequenceMatcher`：提取最长公共片段和证据片段。

当前接口：

- `POST /api/doc/{doc_id}/plagiarism/check`
- `POST /api/doc/{doc_id}/plagiarism/library_scan`
- `GET /api/doc/{doc_id}/plagiarism/library_scan/latest`

### AI 率

当前实现位置：

- `writing_agent/quality/ai_rate.py`
- `writing_agent/web/api/quality_flow.py`
- `writing_agent/v2/graph_runner_runtime_originality_domain.py`

当前启发式信号：

1. 句长波动 `burstiness`
2. `3-gram` 重复率
3. 连接词密度
4. 句末标点集中度
5. 词项熵
6. 词汇多样性
7. 模板化标题密度

当前接口：

- `POST /api/doc/{doc_id}/ai_rate/check`
- `GET /api/doc/{doc_id}/ai_rate/latest`

## 2026-03-27 本轮新增落地

### API 输出增加可执行修订建议

本轮新增：

- `ai_rate` 结果返回 `improvement_actions`
- `plagiarism` 结果返回 `revision_advice`
- `plagiarism/library_scan/latest` 也保留 `revision_advice`
- 查重 Markdown 报告增加 `Revision Advice` 段落

设计原则：

- 只给“提高原创性/降低误判”的修订建议。
- 不给“绕过检测器”的技巧。
- 建议必须和当前命中的异常信号绑定，而不是泛泛而谈。

### 章节类型差异化治理

本轮继续新增：

- `writer prompt` 和 `continue prompt` 会按章节标题分成 `摘要 / 引言 / 方法 / 结果 / 结论 / 通用` 六类。
- `section originality hot sample` 不再对所有章节共用一套固定阈值，而是按章节类型微调。

当前策略示例：

- `摘要`：
  - 更严格控制重复句、低信息密度、模板填充和 AI 风格信号。
- `引言`：
  - 更严格控制空泛背景铺垫和模板化开头。
- `方法`：
  - 更强调数据来源、变量、流程、参数和验证边界。
  - 对来源重叠允许度略高于结果讨论类章节，因为方法术语和流程表达更容易出现稳定表述。
- `结果/讨论`：
  - 更严格控制空泛总结，要求比较、异常、机制和边界条件。
- `结论`：
  - 更严格控制重复正文和套话式总结。

这样做的目的不是“调低检测器”，而是减少不同章节被同一套规则误伤。

## 公开资料检索到的最佳实践

检索日期：2026-03-27

### 对查重/相似度报告的正确理解

1. 相似度分数不是抄袭结论。
   - Turnitin 明确说明：高相似度不一定代表抄袭，低相似度也不一定代表没有问题。
2. 解释报告前要先处理过滤项。
   - Turnitin 支持排除 `quotes`、`bibliography` 和 `small matches`；这些设置会明显影响相似度解读。
3. 连续长片段命中比零散小片段更值得优先修订。
4. 多次把同一稿件提交到机构私有库，可能抬高后续版本的相似度，需要谨慎解释。

对应系统策略：

- 查重结果优先输出最长命中片段和覆盖度信号。
- 报告建议优先提示“先核对引用边界、引号、参考文献、小匹配过滤”，再决定重写范围。

### 对 AI 率的正确理解

1. AI 检测分数应被当作讨论起点，而不是单独定责依据。
   - Turnitin 对 AI Writing score 的定位是辅助调查和对话信号，不是唯一结论。
2. 过高的模板化表达、重复句式、连接词堆叠、低信息密度，会抬高启发式风险。
3. 短文本置信度天然有限，不能把一次短样本结果当成最终结论。

对应系统策略：

- `ai_rate` 输出里保留 `confidence`
- 对短文本加入保守提示
- 把“重复 3-gram、低多样性、低 burstiness”直接转成修订动作

### 真正有助于降低高重合和 AI 风格误判的写作实践

1. 先理解来源，再脱离原文重述。
   - Purdue OWL 建议先读懂原文，再把原文放到一边，用自己的表达重写，并重新核对是否准确。
2. 摘要、转述、引用都必须服务于作者自己的论证。
   - 不是让来源替你写段落，而是让来源为你的结论提供支撑、对比或限制。
3. 段落应该围绕一个中心点展开。
   - 不要让段落只是“首先/其次/最后”的模板推进，也不要用空泛过渡句占位。
4. 直接引用应节制使用。
   - 必须逐字保留时才用引号；其余内容优先转化为自己的分析。
5. 不要只做同义词替换。
   - 真正有效的改写应该连同句序、论证顺序、信息组织方式一起重构。
6. 具体化写作对象。
   - 用对象、时间窗、变量、机制、结果、边界条件替代泛化总结句。

对应系统策略：

- 原创性热采样会拦截重复句、模板开头、低信息密度和来源重叠。
- `rewrite_for_originality()` 明确要求保留事实边界与引用，改写为具体、证据驱动的表述。

## 建议的修订-复测链路

1. 生成初稿。
2. 运行 `AI 率检测`。
3. 运行 `内容查重检测` 或 `全库查重`。
4. 只针对命中的高风险段落修订，不全篇盲改。
5. 修订时优先做以下动作：
   - 改写高频重复的开头句和套话过渡。
   - 把泛化句改成“对象-动作-证据-结论”。
   - 重写证据后的分析句群，而不是仅删掉来源句。
   - 保留必要引用和数字事实，不改事实边界。
6. 再次运行 `ai_rate/check` 与 `plagiarism/library_scan`。
7. 最后做人工复核：
   - 引用是否准确
   - 结论是否真的来自证据
   - 长引文是否必要
   - 是否仍存在连续高重合片段

## 导出稿执行脚本

为了把上面的链路真正落到系统里，本轮新增：

- `scripts/export_quality_optimization_loop.py`

它会在每一轮严格执行：

1. 生成
2. 导出 DOCX
3. 提取导出稿文本
4. 对导出稿文本运行内部查重与 AI 风险评估
5. 合成修订指令
6. 修订后重新导出与复测

同时，`plagiarism/check` 和 `plagiarism/library_scan` 现在都支持传入 `text`，因此系统可以直接对“导出后的文本版本”做内部扫描，而不是只能对会话中的原始正文扫描。

## 不建议采用的“伪优化”

- 只替换同义词
- 只删引文，不补自己的分析
- 故意打乱标点或插入口语噪声
- 为了压分而牺牲事实准确性
- 把检测分数当成唯一目标，忽略可读性和证据链

这些做法通常只会让文本更差，也更容易引入事实错误、引用错误或新的异常信号。

## 参考链接

- Turnitin, Using the AI Writing Report  
  https://guides.turnitin.com/hc/en-us/articles/22774058814093-Using-the-AI-Writing-Report
- Turnitin, What should I do if the AI Writing score is high?  
  https://guides.turnitin.com/hc/en-us/articles/27139113024269-What-should-I-do-if-the-AI-Writing-score-is-high
- Turnitin, Interpreting the Similarity Score  
  https://help.turnitin.com/sv/integrity/studenter/lti/likhetsrapporten/interpreting-the-similarity-score.htm
- Turnitin, Excluding content from the Similarity Report  
  https://help.turnitin.com/sv/integrity/studenter/lti/likhetsrapporten/excluding-content-from-the-similarity-report.htm
- Purdue OWL, Quoting, Paraphrasing, and Summarizing  
  https://owl.purdue.edu/owl/research_and_citation/using_research/quoting_paraphrasing_and_summarizing/index.html
- Purdue OWL, Paraphrasing  
  https://owl.purdue.edu/owl/research_and_citation/using_research/quoting_paraphrasing_and_summarizing/paraphrasing.html
- Purdue OWL, Document Organization  
  https://owl.purdue.edu/owl/graduate_writing/introduction_to_writing/documents/drafting-your-document/handouts/document-organization.pdf
