# 本地运行与空间

普通运行只需要 `.venv`、预构建前端、编译后的 Rust 文档内核、系统 WebView2 和 `.data`。pywebview 默认使用 private mode，不保留浏览器缓存。Node 与 Cargo 只是构建工具，不参与日常启动；Qt、Tauri、Node 网关和 Playwright 已退役。

## 目录性质

| 位置 | 性质 | 是否可直接删除 |
|---|---|---|
| `.data/` | 用户文档、资料、配置和必要状态 | 否 |
| `.venv/` | 当前 Python 运行环境 | 不建议；删后需重装 |
| `.venv-audit/`、旧 `.venv-*` | 旧测试环境 | 确认未使用后可删 |
| `writing_agent/web/frontend_svelte/node_modules/` | 前端开发依赖 | 可删；开发时需重装 |
| `engine/target/`、`engine/bridge/pkg/` | Rust/WASM 构建产物 | 可删；开发构建时再生成，安装包不应携带整个目录 |
| `__pycache__/`、`.pytest_cache/`、构建目录 | 可重建缓存 | 可删 |
| C 盘 Playwright 浏览器缓存 | 已退役工具缓存 | 确认无其他项目共用后可删 |

运行 `python -B -m writing_agent.storage_report` 可只读盘点。工具不会自动删除 `.data` 或其他应用的共享缓存。

## 写盘策略

- 启动不探测、启动或下载模型。
- Python 字节码默认关闭。
- 路由、编辑、选区、流耗时和 RAG 审计默认不落盘；显式开启后均有容量上限。
- 集成事件和可选 RAG 审计默认保留 30 天；反馈副本和应用审计链默认保留 90 天，同时都有固定容量窗口。可分别用 `WRITING_AGENT_INTEGRATION_EVENT_TTL_S`、`WRITING_AGENT_RAG_AUDIT_TTL_S`、`WRITING_AGENT_FEEDBACK_LOG_TTL_S`、`WRITING_AGENT_AUDIT_TTL_S` 调整秒数；程序会把异常值限制在 1 天至 1/2 年的安全范围内。
- 生成文本默认直接随事件传递；旧文件块仅在显式开启时写盘。
- 向量嵌入默认关闭；配置 `WRITING_AGENT_EMBED_MODEL` 后才调用 API。

当前仍需人工清理的已知大项是 C 盘旧 Playwright 缓存（此前盘点约 1.31 GiB）与无效的 `.venv-audit`（约 127 MiB）。它们不再由项目运行重新生成。
