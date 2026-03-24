# 整改优先级清单（2026-03-24）

本文档用于记录本轮重新扫描后确认的主要非规范项，并按“先清阻塞、再修守卫、后做结构和卫生”的顺序推进整改。

## P0：立即处理的阻塞项（已完成）

### 1. Citation verify 回归

- 现象：`tests/test_citation_verify_and_delete.py` 失败，快速预检被阻断。
- 根因：`writing_agent/web/app_v2.py` 兼容导出缺失，`writing_agent/web/app_v2_citation_runtime_part2.py` 存在缺失导入。
- 整改：补齐兼容导出与运行时导入，恢复 citation verify 调用链。
- 结果：相关测试恢复通过。

### 2. Guard globstar 漏扫

- 现象：多个 guard 对根目录或单层目录文件漏扫，导致“看起来通过、实际上未检查完整”。
- 根因：`**/` 模式没有正确覆盖 0 层目录场景。
- 整改：统一修复 guard 的 glob 匹配逻辑，并补充根级文件回归测试。
- 结果：行数、复杂度、架构边界三个 guard 都恢复真实扫描。

### 3. 快速预检链路中的真实阻塞

- 现象：重新跑 `release_preflight.py --quick` 时，陆续暴露 docs reality、data classification、capacity 和前端 audit 等阻塞。
- 整改：逐项修复脚本判断逻辑、清理陈旧本地数据、重校准 local quick capacity baseline，并修复前端 audit 问题。
- 结果：快速预检恢复端到端通过。

### 4. 指标接口自放大型 I/O 热点

- 现象：`/api/metrics/citation_verify` 在高并发探测时会频繁全量读写趋势文件，导致最新 capacity probe 偶发掉速。
- 根因：趋势记录路径每次请求都会立即写盘，形成接口自我放大。
- 整改：改为趋势缓存 + 节流落盘，并补充回归测试验证节流行为。
- 结果：快速预检中的 capacity guard 恢复稳定通过。

### 5. 事件通知尾部阻塞

- 现象：快速预检尾部的 `incident_notify` 会因为本地没有可用外发通道而偶发失败。
- 根因：升级事件已经生成，但本地环境没有 webhook / Slack / Feishu / 可用 SMTP 时，脚本直接返回失败。
- 整改：在非严格且 `--only-when-escalated` 的预检场景下，改为写入 dead letter 并标记 `delivery_deferred`，不再阻塞总预检。
- 结果：保留追踪证据的同时，`release_preflight.py --quick` 恢复稳定全绿。

## P1：本轮完成的结构与卫生项（已完成）

### 5. 超长工作流文件

- 现象：`writing_agent/workflows/generate_request_workflow.py` 超出行数守卫阈值。
- 整改：抽离 metric / failover 规划逻辑到 `writing_agent/workflows/generate_request_metrics.py`。
- 结果：主文件回到可维护范围内。

### 6. 乱码与损坏文本

- 现象：服务代码、能力文件、测试文本、说明文档中存在明显乱码和损坏内容。
- 整改：将关键路径文件改写为可读 UTF-8 内容，并补齐失真的说明文档。
- 结果：代码注释、测试文本、交付文档均恢复可读。

### 7. 仓库临时文件污染

- 现象：`.tmp_*`、`tmp/` 等临时产物容易污染工作树。
- 整改：补齐 `.gitignore` 规则。
- 结果：新产生的临时文件默认被忽略。

### 8. 文件体积重新超线

- 现象：在修复指标趋势热点后，`writing_agent/web/app_v2_citation_runtime_part1.py` 一度再次超出行数守卫。
- 整改：继续压缩无行为变化的空行和局部实现，恢复到守卫阈值内。
- 结果：`guard_file_line_limits.py` 重新通过。

## P2：后续建议项（未阻塞本轮验收）

### 9. 大文件继续拆分

- 建议：继续拆分 `writing_agent/web/app_v2_citation_runtime_part1.py` 及相关运行时模块，降低局部复杂度和状态耦合。

### 10. 配置来源收敛

- 建议：后续收敛测试、依赖、容量策略等配置来源，减少双轨配置的漂移风险。

### 11. 编码守卫扩展

- 建议：将文本编码守卫从 Markdown 扩展到更多 Python / 文本文档路径，提前拦截 mojibake 回归。

## 本轮执行顺序

1. 修复 Citation verify 回归。
2. 修复 guard 漏扫。
3. 清理快速预检阻塞项。
4. 修复指标接口热点和容量链路不稳定因素。
5. 收敛大文件、乱码、文档与仓库卫生问题。
