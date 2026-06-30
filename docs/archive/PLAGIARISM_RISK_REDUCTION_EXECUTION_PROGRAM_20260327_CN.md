# 重合风险治理执行大纲（2026-03-27）

## 目标重定义

本方案不以“规避查重系统”为目标，而是把目标定义为：

1. 持续降低真实重合风险。
2. 减少连续长片段命中。
3. 提高作者自有分析占比。
4. 把每轮修订结果用统一口径量化。

统一汇报口径只保留三项：

- 当前重合风险：`current_overlap_risk`
- 较上轮下降：`reduced_by`
- 是否还有下降空间：`still_has_reduction_space`

## 为什么不能把“查重率越低越好”当作唯一目标

单纯追求低分会导致三个常见问题：

1. 为了压分而破坏事实准确性。
2. 删除必要引文和术语，反而损害可验证性。
3. 诱发无意义改写，例如只换同义词、乱改句序、引入口语噪声。

因此系统执行顺序必须是：

1. 先保留事实和引用边界。
2. 再重写来源后的分析句群。
3. 最后复测重合风险，而不是先盯着分数做表面修改。

## 当前系统已具备的底座

### 核心比对算法

位置：

- `writing_agent/quality/plagiarism.py`

指标：

- `containment`
- `jaccard_resemblance`
- `winnowing_overlap`
- `simhash_similarity`
- `sequence_ratio`
- `longest_match_chars`

当前主判断分数：

- `max_score`

### 运行时治理能力

位置：

- `writing_agent/v2/graph_runner_runtime_originality_domain.py`
- `writing_agent/v2/graph_runner_runtime_session_domain.py`
- `writing_agent/v2/prompt_builder_domain.py`
- `writing_agent/v2/graph_section_continue_prompt_domain.py`

已接入能力：

- 前置原创性写作约束
- 章节类型差异化写作指导
- 热采样失败后的自动重写
- 来源片段相似风险提示

### 质量接口

位置：

- `writing_agent/web/services/quality_service.py`
- `writing_agent/web/domains/plagiarism_domain.py`

当前可用接口：

- `POST /api/doc/{doc_id}/plagiarism/check`
- `POST /api/doc/{doc_id}/plagiarism/library_scan`
- `GET /api/doc/{doc_id}/plagiarism/library_scan/latest`

## 2026-03-27 新增的执行化度量

本轮新增：

- `progress_summary`

字段说明：

- `current_overlap_risk`
  - 当前扫描结果中的最大重合风险分数，直接对应 `max_score`。
- `previous_overlap_risk`
  - 上一轮全库扫描保存在会话里的 `max_score`。
- `reduced_by`
  - `previous_overlap_risk - current_overlap_risk`
- `reduced_percent`
  - 相对上轮的下降比例
- `still_has_reduction_space`
  - 当前是否仍高于目标带，或是否仍存在超阈值来源
- `target_band`
  - 系统内部用于判断“是否还有明显下降空间”的目标区间

设计目的：

- 以后每轮汇报可以只报数字，不必手工比较两次报告。
- 统一“当前为多少、降低了多少、还有没有空间”的口径。

## 执行链路

### 第一阶段：建立风险基线

1. 对当前稿件运行一次 `plagiarism/library_scan`
2. 记录：
   - `max_score`
   - `flagged_count`
   - 命中来源列表
   - 最长命中片段
3. 将结果作为“第 0 轮基线”

### 第二阶段：定向修订

修订优先级：

1. 先处理 `longest_match_chars` 长的来源
2. 再处理 `containment` 高的来源
3. 最后处理局部块重合多但连续命中不长的来源

每段修订动作必须优先使用：

- 把来源事实转成你自己的分析句
- 合并多条证据后再写结论
- 改写“证据之后的解释段”，不是只删证据句
- 保留必要的引号、出处、年份、数字事实

### 第三阶段：复测

每次修订后重新运行：

- `plagiarism/library_scan`

只看三项：

- 当前重合风险
- 较上轮下降
- 是否还有下降空间

### 第四阶段：停止条件

以下任一满足即可停止：

1. `still_has_reduction_space = false`
2. `flagged_count = 0` 且 `current_overlap_risk` 已进入目标带
3. 再继续修订会明显损伤事实准确性或引用清晰度

## 修订动作库

### A. 适用于高 `containment`

表现：

- 当前稿件覆盖了来源较多原始措辞

优先动作：

- 脱离原文顺序重新组织论证
- 先列出你要表达的三到四个判断点，再把来源事实重新填回去
- 把“来源说了什么”改成“这些来源共同支持什么判断”

### B. 适用于高 `winnowing_overlap`

表现：

- 局部块复制明显

优先动作：

- 拆段
- 重组句序
- 用比较句、机制句、限制句替换来源描述句

### C. 适用于高 `longest_match_chars`

表现：

- 有连续长片段命中

优先动作：

- 判断是否必须保留直接引语
- 必须保留时加引号和出处
- 不必保留时整体重写，不做碎片式同义词替换

### D. 适用于低分但仍高风险的情况

表现：

- 总分不高，但有少数命中来源接近阈值

优先动作：

- 优先看证据片段和引用边界
- 核对是否把参考来源的话直接挪进正文分析

## 不建议的修改方式

- 把专业术语改成不准确说法
- 删除本该保留的引用
- 刻意掺入口语、错别字、标点噪声
- 只换同义词，不改论证组织
- 只为了降低分数而打断原本清晰的句子

## 每轮汇报模板

以后执行时只需要给出：

1. 当前重合风险：`x.xxxx`
2. 较上轮下降：`x.xxxx`
3. 是否还有下降空间：`true/false`

如需补充，只附一行：

- 主要问题仍集中在：`来源A / 来源B / 连续长片段 / 高覆盖度`

## 代码落点

- 风险计算：`writing_agent/quality/plagiarism.py`
- 扫描报告：`writing_agent/web/services/quality_service.py`
- 报告生成：`writing_agent/web/domains/plagiarism_domain.py`
- 运行时原创性治理：`writing_agent/v2/graph_runner_runtime_originality_domain.py`

## 2026-03-27 导出稿闭环执行链路

本轮补充了一个面向“导出文档”的执行脚本：

- `scripts/export_quality_optimization_loop.py`

执行顺序固定为：

1. 创建文档并生成初稿
2. 执行导出预检
3. 下载 DOCX
4. 从导出 DOCX 提取正文文本
5. 使用导出稿文本运行 `plagiarism/library_scan`
6. 使用导出稿文本运行 `ai_rate/check`
7. 合成修订指令并调用 `/api/doc/{doc_id}/revise`
8. 重新导出、复测、对比 `current_overlap_risk / reduced_by / still_has_reduction_space`

这次还补了一项关键能力：

- `POST /api/doc/{doc_id}/plagiarism/library_scan`
- `POST /api/doc/{doc_id}/plagiarism/check`

以上两个接口现在都支持可选的 `text` 字段，因此可以直接对“导出后的文本”做内部重合风险扫描，而不是只能对会话中的原始正文扫描。

输出物默认按轮次落盘：

- 每轮导出的 `export.docx`
- 导出稿提取文本 `exported_text.md`
- `plagiarism_scan.json`
- `ai_rate_check.json`
- `decision.json`
- 自动生成的 `revise_instruction.txt`

这样后续继续做真实回归时，可以直接复盘每一轮“导出稿当前为多少、降低了多少、是否还有下降空间”。

## 结论

当前仓库已经不只是“能算一个查重分数”，而是具备：

- 计算重合风险
- 输出定向修订建议
- 记录轮次进展
- 判断是否还有明显下降空间

后续如果继续推进，建议优先做：

1. 前端面板直接显示 `progress_summary`
2. 按来源类型细分风险优先级
3. 增加“长片段命中 Top N”专项报告
