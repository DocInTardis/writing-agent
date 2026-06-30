# 查重逻辑简述

## 一句话

系统会把“导出后的文档文本”和库里的其他文档逐一比对，再把多个相似度信号加权成一个 `0~1` 的风险分数。

## 5 个信号

1. `containment`
   当前文档有多少片段被参考文档覆盖。

2. `jaccard`
   两边共有多少字符 `n-gram`。

3. `winnowing overlap`
   两边局部连续片段的指纹重合度。

4. `simhash similarity`
   两边整体词汇分布是否接近。

5. `sequence ratio`
   两边整体字符串顺序是否相似。

## 总分公式

```text
score = 0.36*containment
      + 0.24*jaccard
      + 0.20*winnowing_overlap
      + 0.12*simhash_similarity
      + 0.08*sequence_ratio
```

## 阈值

- 默认阈值：`0.35`
- `score >= 0.35`：高风险命中
- `score < 0.35`：未命中，但分数越高表示越接近风险区

## 当前最新结果

- 当前内部查重风险：`0.1138`
- 相比上一轮变化：`+0.0019`
- 是否还有降低空间：`false`

## 最新导出文件

- DOCX：`deliverables/export_quality_loop_smoke_case2_after_selected_v3/round_00/export.docx`
- 汇总：`deliverables/export_quality_loop_smoke_case2_after_selected_v3/summary.json`

## 代码位置

- 计算逻辑：`writing_agent/quality/plagiarism.py`
- 接口与持久化：`writing_agent/web/services/quality_service.py`
- 进度摘要：`writing_agent/web/domains/plagiarism_domain.py`
