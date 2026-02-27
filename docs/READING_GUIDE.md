# 项目阅读指南

本指南用于快速理解 `writing-agent` 的整体运行方式与关键模块关系。

## 1. 从运行入口开始

建议按以下顺序阅读：

1. `writing_agent/launch.py`
2. `writing_agent/web/app_v2.py`
3. `writing_agent/web/api/`（HTTP 路由层）
4. `writing_agent/web/services/`（业务编排层）

重点关注：
- 请求如何进入系统
- 会话状态在何处加载与保存
- 生成任务在何处被分发

## 2. 跟踪生成流水线

核心生成路径：

1. `writing_agent/web/services/generation_service.py`
2. `writing_agent/web/app_v2_generate_stream_runtime.py`
3. `writing_agent/v2/graph_runner_runtime.py`
4. `writing_agent/v2/graph_runner.py`
5. `writing_agent/v2/graph_runner_post_domain.py`

重点关注：
- 规划阶段、起草阶段、聚合阶段的职责边界
- 超时、重试、兜底策略
- 质量校验在何处介入

## 3. 理解状态与持久化

建议阅读：

1. `writing_agent/storage.py`
2. `writing_agent/state_engine/`
3. `writing_agent/v2/text_store.py`

重点关注：
- 内存会话的数据结构
- 版本与回放机制的责任划分
- 文本块存储方式与 ID 规则

## 4. 理解 LLM 提供方路由

建议阅读：

1. `writing_agent/llm/provider.py`
2. `writing_agent/llm/factory.py`
3. `writing_agent/llm/model_router.py`
4. `writing_agent/llm/providers/`

重点关注：
- Provider 接口契约
- 后端选择逻辑（`ollama`、node gateway、OpenAI-compatible）
- 模型回退策略

## 5. 前端按垂直切片阅读

建议阅读：

1. `writing_agent/web/frontend_svelte/src/App.svelte`
2. `writing_agent/web/frontend_svelte/src/AppWorkbench.svelte`
3. `writing_agent/web/frontend_svelte/src/lib/components/EditorWorkbench.svelte`
4. `writing_agent/web/frontend_svelte/src/lib/flows/workbenchStateMachine.ts`

重点关注：
- UI 状态流转
- 流式事件处理（`delta`、`section`、`final`）
- 错误与恢复路径

## 6. 阅读校验与守护规则

建议阅读：

1. `scripts/` 下的守护脚本（规模、复杂度、架构边界）
2. `security/*.json`（policy-as-code）
3. `.github/workflows/`

重点关注：
- CI 中哪些质量门禁是强制的
- 哪些失败是告警、哪些会阻塞合并

## 7. 实用阅读方法

阅读任意模块时，可使用以下检查清单：

1. 先识别输入和输出。
2. 再定位外部依赖（LLM、存储、文件系统）。
3. 明确兜底与超时分支。
4. 标注副作用（写状态、写文件、网络调用）。
5. 确认错误如何上浮到 API 响应层。

## 8. 快速排障入口

出现问题时可优先定位：

- 生成结果异常：`writing_agent/v2/graph_runner_runtime.py`
- 流式中断：`writing_agent/web/app_v2_generate_stream_runtime.py`
- 导出问题：`writing_agent/web/api/export_flow.py`
- 引用核验问题：`writing_agent/web/api/citation_flow.py`
- UI 渲染或交互问题：`writing_agent/web/frontend_svelte/src/lib/components/`
