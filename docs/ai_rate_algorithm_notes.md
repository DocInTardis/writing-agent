# AI 率检测算法选型记录

## 目标
- 在本地系统内提供“AI生成风险估计”，用于质量筛查和编辑提醒。
- 强调“风险提示”而非“法律意义上的最终判定”。

## 方案
采用启发式混合评分（可离线运行）：
1. 句长 burstiness（句长波动）
2. 3-gram 重复率
3. 连接词密度（每千字）
4. 句末标点集中度
5. token 熵（归一化）
6. 词汇多样性
7. 模板化标题密度

输出：
- `ai_rate`（0~1）
- `risk_level`（low/medium/high）
- `confidence`（随文本长度变化）
- `evidence`（触发的异常信号）

## 相关研究检索（用于实现参考）
- GLTR（基于语言模型 token rank 分布的人机文本区分思路）
  - https://aclanthology.org/P19-3019/
- DetectGPT（利用曲率差异检测 LLM 生成文本）
  - https://arxiv.org/abs/2301.11305
- LLM Text Watermarking（从生成端加入可检验信号）
  - https://arxiv.org/abs/2301.10226
- Ghostbuster（面向真实场景的 AI 文本检测器）
  - https://arxiv.org/abs/2305.15047

## 为什么当前不直接实现 DetectGPT/GLTR 全量版本
- DetectGPT/GLTR 都依赖额外语言模型概率接口或大规模采样，线上成本高。
- 当前系统优先可用性与吞吐，先落地无需外部依赖的启发式版本。
- 后续可在此基础上扩展“强模型检测模式”。

## 当前代码位置
- 核心算法：`writing_agent/quality/ai_rate.py`
- 后端接口：`/api/doc/{doc_id}/ai_rate/check`、`/api/doc/{doc_id}/ai_rate/latest`
- 前端入口：`AI率检测` 面板（Svelte）

