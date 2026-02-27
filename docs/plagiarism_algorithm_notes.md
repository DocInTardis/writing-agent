# 查重算法选型记录

## 目标
为写作系统提供可工程化落地的查重能力，兼顾：
- 局部复制粘贴检测（短片段）
- 近重复改写检测（词序变化）
- 批量扫描性能（对多文档）

## 采用的混合方案
本系统实现为以下算法组合：
1. 字符 n-gram（resemblance + containment）
2. Winnowing 指纹（局部重叠鲁棒）
3. SimHash（语义近似下的词项扰动鲁棒）
4. SequenceMatcher 最长公共片段（证据片段抽取）

## 为什么是混合方案
- 单一算法在中文场景下容易偏科：
  - 只看编辑距离，容易误报结构相似但内容不同的文档。
  - 只看关键词重合，容易漏掉改写后的近重复。
- 混合后可平衡：
  - containment 强于“源文被覆盖程度”
  - winnowing 强于“局部块复制”
  - simhash 强于“轻改写相似”

## 参考资料（检索来源）
- Schleimer et al., Winnowing (SIGMOD 2003):
  - https://theory.stanford.edu/~aiken/publications/papers/sigmod03.pdf
- Broder, Near-duplicate document filtering:
  - https://research.google/pubs/identifying-and-filtering-near-duplicate-documents/
- Charikar, Similarity estimation techniques (SimHash lineage):
  - https://dl.acm.org/doi/10.1145/509907.509965

## 当前实现位置
- 核心算法：`writing_agent/quality/plagiarism.py`
- 单文档查重 API：`POST /api/doc/{doc_id}/plagiarism/check`
- 全库扫描 API：`POST /api/doc/{doc_id}/plagiarism/library_scan`

## 后续可演进方向
1. 引入 ANN 向量索引做候选召回，降低全量比对成本。
2. 增加句向量模型特征，提升同义改写识别能力。
3. 建立阈值校准集（按题材/体裁分桶）做分场景阈值策略。
