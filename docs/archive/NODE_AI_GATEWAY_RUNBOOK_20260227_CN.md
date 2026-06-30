# Node AI Gateway 运行与回滚手册（Phase 4）

## 1. 服务启动

目录：`gateway/node_ai_gateway`

```bash
npm install
npm start
```

默认监听：`127.0.0.1:8787`

## 2. Python 侧切换

开启 Node 后端：

```bash
WRITING_AGENT_LLM_BACKEND=node
WRITING_AGENT_NODE_GATEWAY_URL=http://127.0.0.1:8787
WRITING_AGENT_LLM_BACKEND_ROLLOUT_PERCENT=5
WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK=1
```

一键回滚到 Python：

```bash
WRITING_AGENT_LLM_BACKEND=python
```

## 3. 灰度策略（Phase 3）

按稳定性逐步推进：
1. 5%
2. 20%
3. 50%
4. 100%

每个阶段至少观察 24 小时，满足指标再推进。

## 4. 关键指标

- 4xx/5xx 错误率
- p95/p99 延迟
- schema 失败率
- 导出失败率（回归套件）
- Node->Python 回退触发率

指标汇总命令：

```bash
python scripts/node_gateway_rollout_monitor.py \
  --node-log .data/metrics/node_gateway_events.jsonl \
  --fallback-log .data/metrics/node_backend_fallback.jsonl
```

## 5. 故障处置

1. 触发条件：
- 错误率或延迟异常
- schema 失败率突增
- fallback 触发率持续升高
2. 立即动作：
- 将 `WRITING_AGENT_LLM_BACKEND=python`
- 保持网关运行采集证据
3. 复盘资料：
- `.data/metrics/node_gateway_events.jsonl`
- `.data/metrics/node_backend_fallback.jsonl`
- 回归测试与门禁报告

## 6. 变更审计证据

需至少保留：
- 协议文档
- 回归测试结果
- 门禁通过结果
- 灰度阶段指标快照
- 回滚演练记录
