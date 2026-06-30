# 单篇结果拟合说明

## 结论

可以做“拟合”：

- 给定某一篇文档及其外部观测分数
- 反复搜索本地估计器参数
- 找到一组让本地结果尽量接近该分数的参数

但这**不能证明**你找到了外部系统的真实算法。它只说明：

- 在你提供的样本上
- 本地估计器可以把误差压低

## 为什么不能当成真实反推

原因主要有 3 个：

1. 外部比对库不可见
2. 过滤规则和阈值不公开
3. 单篇样本极易过拟合，换一篇就可能失效

所以更准确的说法是：

- `参数拟合`
- `标签对齐`
- `样本校准`

而不是：

- `反推出真实算法`

## 已落地能力

新增脚本：

- [scripts/calibrate_quality_models.py](/D:/codes/writing-agent/scripts/calibrate_quality_models.py)

它支持两类校准：

1. `plagiarism`
   目标是拟合本地查重估计器输出
2. `ai_rate`
   目标是拟合本地 AIGC 风险估计器输出

输出会给出：

- 最佳参数
- 每个样本的目标分数
- 本地预测分数
- 单样本绝对误差
- 总体 `MAE`
- 总体 `RMSE`

## 输入示例

```json
{
  "plagiarism": {
    "samples": [
      {
        "id": "p1",
        "target_score": 0.28,
        "source_path": "D:/tmp/source.txt",
        "reference_paths": [
          "D:/tmp/ref1.txt",
          "D:/tmp/ref2.txt"
        ]
      }
    ]
  },
  "ai_rate": {
    "samples": [
      {
        "id": "a1",
        "target_score": 0.41,
        "path": "D:/tmp/body.txt",
        "threshold": 0.6
      }
    ]
  }
}
```

也可以直接传文本字段：

- `source_text`
- `reference_texts`
- `text`

## 运行方式

```powershell
.\.venv\Scripts\python.exe scripts\calibrate_quality_models.py `
  --input D:\tmp\calibration_input.json `
  --output D:\tmp\calibration_output.json
```

## 怎么看结果

优先看这几个字段：

- `mae`
- `rmse`
- `predictions[].abs_error`

解释：

- `mae` 越小，平均误差越小
- `rmse` 越小，大误差样本越少
- 如果只拟合 1 篇，哪怕误差为 0，也不能说明模型真实一致

## 建议用法

更可靠的方式不是盯住单篇，而是：

1. 至少准备多篇样本
2. 同时看查重和 AIGC 两个方向
3. 看趋势是否一致，而不是追求单篇同分
4. 把拟合参数当作内部校准参数，不当作外部算法真值
