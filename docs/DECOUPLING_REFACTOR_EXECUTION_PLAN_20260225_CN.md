# 解耦重构执行方案（2026-02-25）

## 1. 背景与核心问题

当前系统存在明显的“单文件过载”问题，已经直接影响质量稳定性与定位效率：

- 后端核心文件过大：
  - `writing_agent/web/app_v2.py`：10930 行
  - `writing_agent/v2/graph_runner.py`：3873 行
  - `writing_agent/document/v2_report_docx.py`：1368 行
- 前端核心文件过大：
  - `writing_agent/web/frontend_svelte/src/App.svelte`：4858 行
  - `writing_agent/web/frontend_svelte/src/lib/components/Editor.svelte`：3837 行
- 生成流程存在重复链路与历史兼容分支叠加，导致维护和排错成本过高。
- 对 AI 生成过程存在过多结构性限制，导致文档出现“可通过流程但质量不高”的现象。

本方案目标是：**先解耦，再精简，再复盘，最终让每个流程都能独立审视和独立回归。**

---

## 2. 重构原则（强约束）

### 2.1 架构原则

- 一条业务主流程对应一个主文件（Flow File），避免跨文件来回跳转。
- 路由层只做参数与响应编排，不做业务计算。
- 业务逻辑统一进入服务层，不允许在路由函数中堆叠复杂状态机。
- 公共能力（日志、锁、重试、度量、序列化）集中在 shared 模块，禁止重复实现。

### 2.2 代码规模约束

- 任意业务文件建议不超过 800 行，硬上限 1000 行。
- 任意函数建议不超过 80 行，硬上限 120 行。
- 同一职责不允许在多个 endpoint 中复制粘贴实现。

### 2.3 AI 生成策略原则（本次必须执行）

- 不对 AI 生成施加“过量硬限制”；限制仅保留：
  - 用户明确要求的格式约束；
  - 基础安全合规约束；
  - 导出必需的结构完整性约束。
- 生成质量治理以“后验评估 + 有针对性的修复提示”为主，不以“前置强约束”硬压模型。
- 禁止为追求结构一致性而牺牲内容自然性、篇幅完整性与语言一致性。

---

## 3. 目标目录结构（按流程一文件）

以下为目标拆分蓝图（后端）：

```text
writing_agent/web/
  app_v2.py                      # 仅应用组装（create_app + include_router）
  api/
    generation_flow.py           # 生成主流程（stream/non-stream/section）
    revision_flow.py             # 修改与续写流程
    export_flow.py               # 导出流程（check/docx/pdf）
    citation_flow.py             # 引用管理与核验流程
    feedback_flow.py             # 评分反馈流程
    quality_flow.py              # 查重/AI率流程
    rag_flow.py                  # 检索与资料库流程
    version_flow.py              # 版本树与回滚流程
    template_flow.py             # 模板/上传/偏好提取流程
  services/
    generation_orchestrator.py   # 统一生成编排（核心）
    export_service.py
    citation_service.py
    quality_service.py
    rag_service.py
    version_service.py
  shared/
    locks.py
    streaming.py
    metrics.py
    errors.py
    dto.py
```

前端目标拆分蓝图：

```text
writing_agent/web/frontend_svelte/src/
  App.svelte                      # 容器壳：布局 + 页面状态装配
  flows/
    generationFlow.ts             # 生成事件流处理
    exportFlow.ts
    revisionFlow.ts
    qualityFlow.ts
    citationFlow.ts
    feedbackFlow.ts
  lib/components/
    editor/EditorShell.svelte
    editor/EditorCore.svelte
    editor/EditorSelection.svelte
    editor/EditorSlashCommand.svelte
    editor/EditorBlockOps.svelte
```

---

## 4. 分阶段执行方案

## Phase A：建立“可重构基线”（先保行为）

- 冻结当前对外 API 路径与请求/响应结构。
- 建立生成链路、导出链路、修订链路的 golden 回归样例。
- 记录当前关键性能与稳定性指标，作为重构前基线。

验收：

- 回归样例可重复执行。
- 基线指标可自动生成报告。

## Phase B：后端按流程拆路由文件（不改语义）

- 从 `app_v2.py` 迁出 route handler 到 `api/*_flow.py`。
- `app_v2.py` 仅保留 app 初始化与 router 注册。
- 保持 URL 与返回结构完全一致。

验收：

- `app_v2.py` 降到 <= 1500 行。
- 所有既有 API 测试通过。

本轮已完成（第一批）：

- 已落地 `writing_agent/web/api/generation_flow.py`，接管生成/续写相关路由。
- 已落地 `writing_agent/web/api/export_flow.py`，接管导出相关路由。
- 已落地 `writing_agent/web/api/feedback_flow.py`，接管反馈与会话日志路由。
- 已落地 `writing_agent/web/api/quality_flow.py`，接管查重与 AI 率相关路由。
- `app_v2.py` 中上述流程函数已改为薄代理（调用 flow 实现），开始实质瘦身。

## Phase C：抽出生成编排器（去重复）

- 新增 `services/generation_orchestrator.py`，统一处理：
  - 快速编辑分支
  - 流式主生成
  - 非流式兜底
  - 持久化与版本提交
- 删除 stream/non-stream 的重复分支与重复后处理代码。

验收：

- 生成主链路只有一套编排实现。
- 相同输入下行为与历史一致（除明确修复项）。

## Phase D：降低过度限制（恢复内容质量）

- 将过强的前置硬约束改为可配置、可降级策略。
- 将质量检查从“仅提示”升级为“可配置阻断 + 自动修复建议”。
- 保留基础结构校验，但不做破坏自然语言的强修补。

验收：

- 复杂 prompt 下平均篇幅、段落完整度、语言一致性提升。
- 不再出现“流程通过但正文质量明显失真”的常见问题。

## Phase E：图谱与导出模块拆分

- `graph_runner.py` 拆为 plan/draft/aggregate/runner 模块。
- `v2_report_docx.py` 拆为 toc/styles/content/field/builder 模块。

验收：

- 超长函数（>200 行）清零。
- 文档目录、页码、段落格式等回归通过。

## Phase F：前端按流程拆分

- `App.svelte` 下沉业务逻辑到 `flows/*.ts`。
- `Editor.svelte` 拆为 editor 子组件簇。
- 去除旧版双栈路径依赖（`v2.js` 与旧模板仅保留迁移窗口）。

验收：

- `App.svelte` <= 1200 行。
- `Editor.svelte` <= 1500 行。
- 前端 Playwright 回归通过。

---

## 5. “每个流程一个文件”映射表（执行清单）

- 生成：`api/generation_flow.py`
- 修订：`api/revision_flow.py`
- 导出：`api/export_flow.py`
- 引用：`api/citation_flow.py`
- 质量（查重/AI率）：`api/quality_flow.py`
- 反馈评分：`api/feedback_flow.py`
- RAG 与资料库：`api/rag_flow.py`
- 版本：`api/version_flow.py`
- 模板与上传：`api/template_flow.py`

说明：每个 Flow 文件内部允许按小函数拆解，但不允许跨 Flow 随意混写业务。

---

## 6. 风险与防护

- 风险：拆分期间引入行为回归。
  - 防护：先 golden 测试，再迁移；每迁移一个 flow 执行对应回归。
- 风险：测试过度绑定私有函数，阻碍重构。
  - 防护：优先改为黑盒 API 测试，逐步减少对 `_private` 的直接引用。
- 风险：前端双栈并存导致路径分叉。
  - 防护：定义迁移窗口，窗口结束后强制单栈。

---

## 7. 完成定义（DoD）

以下全部满足才视为“解耦完成”：

- `app_v2.py` 仅保留组装逻辑，且 <= 1500 行。
- 核心业务流按“一个流程一个文件”完成落地。
- 超过 1000 行的业务文件数量明显下降，超长函数全部拆解到阈值内。
- 复杂 prompt 的文档质量指标提升并稳定。
- 前端页面测试（Playwright）全链路通过，导出 DOCX 质量可复核。

---

## 8. 结论

“单文件超载 + 过度限制 AI 生成”是当前质量与稳定性问题的主要原因之一。  
本方案采用“流程解耦优先、约束降噪、回归兜底”的策略，目标是让系统可读、可测、可维护，并使内容质量真正由能力提升而非规则堆叠驱动。
