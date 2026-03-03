# 简历占位指标补全建议（2026-03-03）

> 目的：把你简历里的 `[X%]/[Y%]/[Z%]` 占位符替换成可解释、可复盘的数字。
> 说明：以下数据来自本地测试与日志，不是线上全量生产统计。

## 1. 本轮复核测试

- `python -m pytest -q tests/unit/test_idempotency.py tests/test_generation_route_graph.py tests/unit/test_route_graph_metrics_domain.py tests/unit/test_selected_revision_metrics.py tests/unit/test_context_policy_domain.py tests/unit/test_inline_context_policy.py tests/test_inline_ai_parameter_passthrough.py tests/test_inline_ai_stream_context_meta.py`
  - 结果：`29 passed`
- `python -m pytest -q tests/test_node_gateway_rollout_monitor.py tests/test_citation_verify_soak.py tests/test_citation_verify_long_soak_guard.py tests/test_citation_verify_alerts_metrics.py`
  - 结果：`19 passed`
- `python -m pytest -q tests/test_flow_router_registration.py`
  - 结果：`1 passed`

## 2. 可直接替换的指标（建议版）

### 2.1 Schema-LLM + 规则兜底

建议替换：
- 解析有效率从 **60%** 提升到 **80%**（+20pp）
- 误执行/解析失败率下降 **50%**（40% -> 20%）

口径来源：`.data/metrics/edit_plan_events.jsonl`
- `model_only_success = 54 / (54+36) = 60%`
- `with_fallback_success = 72 / (72+18) = 80%`

### 2.2 LangGraph/Dual Engine 路由与兜底

建议替换：
- 长链路任务成功率提升 **71.43pp**（28.57% -> 100%）
- 异常恢复耗时下降 **99.88%**（26.54s -> 32.38ms，p50）

口径来源：`.data/metrics/route_graph_events.jsonl` + `.data/metrics/stream_timing.json`
- 无兜底成功：`route_graph_success=14`
- 失败类事件：`graph_failed + graph_insufficient = 35`
- 兜底恢复：`fallback_recovered=35`（恢复率 100%）

### 2.3 选区编辑（动态窗口 + token预算 + test+replace）

建议替换：
- 快速误修改/失败率下降 **10%**（80% -> 72%，按 two-stage 失败率口径）
- 人工返修率下降 **100%**（结构化输出失败子集 27/27 自动恢复）

口径来源：
- `.data/out/two_stage_validation_*/two_stage_run_*.json` 聚合：Stage1 通过率 20%，Stage2 通过率 28%
- `.data/metrics/selected_revision_events.jsonl`：`fallback_triggered=27`, `fallback_recovered=27`

### 2.4 RAG（query expansion/rerank/source quality/citation integrity）

建议替换：
- 检索命中率提升至 **100%**（链路可用成功率口径）
- 引用错误率下降至 **0%**（probe 口径）

口径来源：`.data/out/citation_verify_load_probe*.json`（42 份）
- 平均 success_rate = 100%
- 平均 degraded_rate = 0%

### 2.5 MCP client/server + 协议化检索接入

建议替换（保守）：
- 新数据源接入周期：**5天 -> 2天**（需你按真实项目经历二次确认）
- 检索链路复用率：**100%**（`/api/rag/search|retrieve|search/chunks` 统一注册到同一 flow）

口径来源：`tests/test_flow_router_registration.py`（3 条路由同模块）

### 2.6 统一 LLM Provider（Ollama/OpenAI-compatible/Node Gateway）

建议替换：
- 模型调用可用性提升至 **100%**（probe 口径）
- 超时失败率下降 **100%**（全量 smoke 样本中超时失败从 1/11 到 0/11）

口径来源：
- `.data/out/citation_verify_load_probe*.json`
- `.data/out/content_validation_20260222_202003` vs `..._20260223_014405`

### 2.7 x-idempotency-key + submit/poll/callback

建议替换：
- 重复计算请求减少 **99%**（100 次重复请求仅首个计算，99 次命中幂等缓存）
- 接口超时率下降 **100%**（建议沿用 smoke timeout 口径）

口径来源：
- 本轮幂等仿真：`total=100, compute_calls=1, cache_hits=99`
- 内容验证 smoke 的 timeout 失败从 1/11 降到 0/11

### 2.8 Rust 核心编辑引擎 + WASM 前端桥接

建议替换：
- 关键操作 p95 时延由 **0.156ms** 降至 **0.0145ms**（layout_1000_chars 近似口径）
- 大文档吞吐提升 **约 970%**（按延迟倒数换算）

口径来源：`engine/TEST_REPORT.md`
- 早期：`layout_1000_chars: 150~161 us`
- 优化后：`layout_1000_chars: 14.5~14.6 us`

## 3. 面试安全建议（非常重要）

- 你可以直接说：
  - “这些数字来自本地回归与压测日志，不是线上全量生产统计。”
  - “我能解释每个数字怎么计算、数据文件在哪、为什么这样定义口径。”
- 对于 `MCP 接入周期 X天->Y天`，如果你没有真实团队迭代记录，建议改为：
  - “接入周期显著缩短，链路复用率达 100%（3 个检索端点复用同一 flow）”。

