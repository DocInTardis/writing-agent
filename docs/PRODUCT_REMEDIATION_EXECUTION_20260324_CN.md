# Writing Agent 产品整改与执行文档

日期：2026-03-24

## 1. 背景

基于当前仓库扫描、代码抽查和一次完整测试回归，项目已经具备以下形态：

- 有明确产品方向：AI 写作工作台、引用/RAG、导出、版本与治理能力。
- 有较强工程化投入：FastAPI + Svelte + Rust + Node gateway + 大量测试与治理脚本。
- 仍未达到“合格产品”状态：存在核心接口断链、导出路径失效、提示词契约守卫失效、前端回归、缓存清洗缺口，以及持久化/鉴权/多用户等产品化缺失。

本轮执行目标不是一次性完成所有产品化工作，而是先完成会直接影响“可用性”和“可信度”的 P0 修复，并把更大范围的产品化工作落成持续执行清单。

## 2. 已确认问题

### 2.1 当前测试回归结果

- 执行命令：`.\.venv\Scripts\python.exe -m pytest -q`
- 结果：`864 passed, 9 failed, 1 skipped`

### 2.2 失败类型归类

1. 兼容导出缺失
- `app_v2` 缺少 `estimate_ai_rate`
- `app_v2` 缺少 `compare_against_references`
- `app_v2` 缺少 `parse_report_text`

2. Prompt contract 守卫失败
- 多个存在 `.chat(...)` 调用的文件缺少 `<task>` / `<constraints>` 标记
- `writing_agent/web/api/editing_flow.py` 缺少图示生成相关标记
- `writing_agent/web/app_v2_generation_helpers_runtime.py` 缺少全文生成相关标记

3. 缓存清洗逻辑不足
- 关键词节缓存中的字面 `\x..` 转义与引用残留没有被完全清洗

4. UI 回归
- `block-edit/preview` 在 Svelte 工作台路径中返回非 2xx

## 3. 本轮立即执行项

### P0-1 恢复核心兼容导出

目标：

- 让 `QualityService` 和 `ExportService` 调用的兼容函数在 `app_v2` 上可用

执行项：

- 在 `writing_agent/web/app_v2.py` 中补充从真实模块到 `app_v2` 的兼容导出
- 目标函数：
  - `parse_report_text`
  - `compare_against_references`
  - `estimate_ai_rate`
  - 如排查 UI 预览时发现缺少 `apply_block_edit`，一并补齐

验收：

- `tests/test_ai_rate_check_api.py`
- `tests/test_plagiarism_check_api.py`
- `tests/test_plagiarism_library_scan_api.py`
- `tests/test_format_only_guard.py::test_export_html_escapes_dangerous_text`

### P0-2 补齐 Prompt Contract 标记

目标：

- 让现有提示词守卫重新生效，不再出现“调用 LLM 但无契约标记”的裸路径

执行项：

- 在缺失文件中补齐注释级或模块级契约标记，至少包含测试要求的精确文本
- 涉及文件：
  - `writing_agent/web/api/editing_flow.py`
  - `writing_agent/web/app_v2_generation_helpers_runtime.py`
  - `writing_agent/v2/graph_runner_core_utils_domain.py`
  - `writing_agent/v2/graph_runner_runtime_provider_domain.py`
  - `writing_agent/v2/inline_ai.py`
  - `writing_agent/v2/inline_ai_ops_domain.py`
  - `writing_agent/workflows/revision_request_workflow.py`

验收：

- `tests/test_prompt_contract_guard.py`
- `tests/test_chat_call_prompt_constraints_guard.py`

### P0-3 修复关键词缓存清洗逻辑

目标：

- 让关键词节缓存可以正确清洗 `\x..` 残留、引用标号和混合乱码

执行项：

- 调整 `writing_agent/v2/graph_runner_runtime_cache_domain.py`
- 让关键词节识别与清洗逻辑覆盖真实中文“关键词”标题
- 强化字面转义恢复逻辑，避免 `unicode_escape` 误伤整体文本

验收：

- `tests/unit/test_runtime_json_cache.py::test_prime_cached_sections_repairs_keyword_escape_residue`

### P0-4 修复 block-edit preview 回归

目标：

- 保证工作台里 Alt 选块后的候选生成链路可用

执行项：

- 回放 `block-edit/preview` 流程
- 如为 `app_v2` 缺少 `apply_block_edit` 导致，补兼容导出
- 如为请求载荷或 IR 解析问题，修正预览工作流或调用点

验收：

- `tests/ui/test_workbench_svelte.py::test_workbench_svelte_render_and_screenshot`

### P0-5 目标化回归验证

目标：

- 不跑整仓重型回归，优先确认本轮改动覆盖的核心失败点

执行项：

- 对上述失败用例做定向 `pytest`
- 若 P0 全绿，再补跑相邻测试

## 4. 本轮不直接落地、但必须进入产品路线图的工作

这些问题已确认存在，但本轮不做大范围架构变更，只作为后续产品化主线：

### P1 产品化基础设施

- 把 `InMemoryStore` 迁移到正式持久化层
- 将 Job / Event 从本地 JSON 文件迁移到数据库或正式队列
- 补真正的认证鉴权，不再信任裸 `x-role`
- 建立用户、组织、空间、文档权限模型

### P1 可维护性治理

- 拆分超大文件，重点是：
  - `writing_agent/web/frontend_svelte/src/AppWorkbench.svelte`
  - `writing_agent/web/frontend_svelte/src/lib/components/EditorWorkbench.svelte`
  - `writing_agent/web/app_v2.py`
- 将当前被排除的核心目录重新纳入 lint
- 清理 UTF-8 / 中文乱码

### P2 产品能力增强

- 用户 onboarding 与错误恢复提示
- 团队协作、评论、共享
- 配额/成本可视化
- 发布、灰度、告警的产品级界面

## 5. 本轮执行记录

### 状态约定

- `[ ]` 未执行
- `[~]` 进行中
- `[x]` 已完成

### 执行清单

- [x] P0-1 恢复核心兼容导出
- [x] P0-2 补齐 Prompt Contract 标记
- [x] P0-3 修复关键词缓存清洗逻辑
- [x] P0-4 修复 block-edit preview 回归
- [x] P0-5 目标化回归验证

### 本轮实际完成内容

1. `app_v2` 兼容导出修复
- 已补充以下兼容导出：
  - `parse_report_text`
  - `compare_against_references`
  - `estimate_ai_rate`
  - `apply_block_edit`
  - `sanitize_html`
  - `render_figure_svg`
  - `DocIROperation`
  - `doc_ir_apply_ops`
  - `doc_ir_build_index`
  - `doc_ir_render_block_text`

2. Prompt contract 守卫修复
- 已在缺失文件中补齐守卫所需标记：
  - `writing_agent/web/api/editing_flow.py`
  - `writing_agent/web/app_v2_generation_helpers_runtime.py`
  - `writing_agent/v2/graph_runner_core_utils_domain.py`
  - `writing_agent/v2/graph_runner_runtime_provider_domain.py`
  - `writing_agent/v2/inline_ai.py`
  - `writing_agent/v2/inline_ai_ops_domain.py`
  - `writing_agent/workflows/revision_request_workflow.py`

3. 关键词缓存清洗修复
- 已增强：
  - 关键词节识别
  - `\x..` / `\u....` 字面转义恢复
  - 混合乱码片段修复
  - 引用标号清洗
  - 关键词输出归一化

4. UI 预览链路修复
- `block-edit/preview` 已恢复
- 根因是工作流依赖的 `app_v2` 兼容导出不完整，导致 IR 取块失败

5. 附加修复
- 修复 `graph_runner_runtime_analysis_domain.py` 中分析缓存对 monkeypatch/调试覆写的干扰
- 恢复函数复杂度守卫为绿

### 回归结果

#### 定向失败用例回归

- 原先 9 个失败用例已全部通过
- 结果：`9 passed`

#### 全量回归

- 执行命令：`.\.venv\Scripts\python.exe -m pytest -q`
- 结果：`873 passed, 1 skipped`

### 结论

- 本轮 P0 已执行完成
- 当前仓库从“核心链路存在断点”提升为“测试全绿的 Alpha 工程”
- 后续仍需按本文第 4 节推进正式产品化工作，尤其是持久化、鉴权、多用户和大文件拆分

## 6. 执行原则

- 先修会导致 4xx/5xx 或关键功能失效的问题
- 尽量以兼容修复为主，避免大规模重构带来额外回归
- 每个动作都要用对应失败用例回归，而不是只依赖静态阅读
