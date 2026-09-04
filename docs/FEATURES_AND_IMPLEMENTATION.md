# 功能与实现清单

本文是当前项目的功能地图。它说明功能入口、主要实现位置和实际使用方式，避免继续依赖分散的历史计划文档。

## 1. 产品入口与工作区

- 产品首页：`GET /`
- 新建工作区：`GET /new`、`POST /api/workspaces/create`
- 最近工作区：`GET /latest`
- 工作区列表、筛选、排序和批量操作：`writing_agent/web/api/workspace_flow.py`
- 工作区业务规则：`writing_agent/web/services/workspace_service.py`
- 本地持久化：`writing_agent/storage.py`，数据默认写入 `.data/workspaces/`
- 保存视图：`workspace_view_flow.py` 和 `workspace_view_service.py`

工作区支持标题、正文、标签、状态、负责人、优先级、截止日期、置顶、复制、归档、回收站、恢复和永久删除。

## 2. AI 写作与修订

- HTTP 入口：`writing_agent/web/api/generation_flow.py`
- 请求编排：`writing_agent/web/services/generation_service.py`
- 工作流入口：`writing_agent/workflows/`
- 核心生成图：`writing_agent/v2/graph_runner.py` 及同目录的 `graph_*_domain.py`
- 提示词和章节约束：`writing_agent/v2/prompts.py`、`section_contract*.py`
- 局部编辑：`writing_agent/web/api/editing_flow.py`

生成过程包含规划、章节起草、聚合、验证和失败回退。高风险修改先返回确认信息，由前端明确确认后执行。

## 3. 模型接入

- Provider 工厂：`writing_agent/llm/factory.py`
- OpenAI 兼容接口：`writing_agent/llm/providers/openai_compatible_provider.py`
- Ollama：`writing_agent/llm/providers/ollama_provider.py`
- 故障转移：`writing_agent/llm/providers/failover_provider.py`
- 用户配置：`writing_agent/llm/user_config.py`
- 可选 Node 网关：`gateway/node_ai_gateway/`

默认使用 OpenAI 兼容接口。密钥通过环境变量或应用内模型设置提供；启动脚本不会读取其他应用的认证文件，也不会强制覆盖用户选择的模型。

## 4. 资料库、RAG 与引用

- 资料库 API：`writing_agent/web/api/rag_flow.py`
- 检索入口：`writing_agent/v2/rag/retrieve.py`
- 结构化知识单元：`knowledge_unit.py`、`structured_records.py`
- 分层检索：`hierarchical_retriever.py`
- 知识图谱：`knowledge_graph.py`、`kg_retriever.py`
- 引用登记和审计：`citation_registry.py`、`audit_trail.py`
- 引用管理 API：`writing_agent/web/api/citation_flow.py`

系统优先检索本地资料，可按配置使用 OpenAlex、Crossref 等公开元数据补充结果，并把来源信息传入生成和引用检查流程。

## 5. 编辑器与版本

- Svelte 工作台：`writing_agent/web/frontend_svelte/src/AppWorkbench.svelte`
- 编辑器组件：`src/lib/components/EditorWorkbench.svelte`
- 文档中间表示：`writing_agent/v2/doc_ir.py`
- 编辑操作：`writing_agent/web/api/editing_flow.py`
- 版本 API：`writing_agent/web/api/version_flow.py`
- 状态与回放：`writing_agent/state_engine/`

前端通过流式事件接收生成结果，并以 DocIR 操作完成段落级修改、预览、差异和版本恢复。

## 6. 质量检查

- API：`writing_agent/web/api/quality_flow.py`
- 文本相似度：`writing_agent/quality/plagiarism.py`
- AI 文本特征估计：`writing_agent/quality/ai_rate.py`
- 生成质量门禁：`writing_agent/capabilities/generation_quality.py`

这些结果是本地启发式风险提示，不等同于学校或商业查重平台的正式结论。

## 7. 图表与导出

- 图表能力：`writing_agent/capabilities/diagramming.py`
- SVG 渲染：`writing_agent/diagrams/render_svg.py`
- 导出 API：`writing_agent/web/api/export_flow.py`
- DOCX 导出：`writing_agent/document/v2_report_docx.py`
- 通用文档构建：`writing_agent/document/docx_builder.py`

支持 Markdown、DOCX、HTML 和 PDF 相关导出入口。DOCX 负责目录、标题、段落、图片、引用和格式偏好；PDF 能力取决于当前运行环境的转换支持。

## 8. 桌面端

- 默认桌面入口：`python -m writing_agent.launch`，使用 PySide6 内嵌本地工作台；完整桌面交互验收尚未完成。
- `desktop-tauri/` 是 Tauri 2 实验实现，包含 Rust 编辑命令，但 Python sidecar 的发布打包仍未完成，不作为当前稳定入口。

## 9. 运行与验证

开发用本地服务（不是默认产品入口）：

```powershell
.\scripts\start.ps1
```

PySide 桌面端：

```powershell
.\scripts\start_desktop.ps1
```

开发检查：

```powershell
python -m pytest -q tests
npm --prefix writing_agent/web/frontend_svelte run build
npm --prefix gateway/node_ai_gateway test
cargo test --workspace --manifest-path engine/Cargo.toml
```

浏览器自动化测试链路已移除，不再需要下载测试浏览器。桌面交互验收尚待随桌面架构收敛重新建立；现有单元、集成和导出测试不替代这部分验收。

## 10. 当前边界

- 应用面向单机个人使用，没有多人账号、权限和远程数据库。
- AI 生成依赖用户配置的模型服务。
- PySide 是默认桌面入口；HTTP 服务保留用于内部界面及开发调试。Tauri 历史实验尚待退役。
- 已删除的历史设计记录可从 Git 历史查阅，不代表当前功能或操作方式。
