# Writing Agent Desktop (Tauri 2.x, experimental)

实验桌面端应用，基于 Tauri 2.x + Svelte 5 + Rust 引擎。当前可用于开发验证，正式打包仍缺少 Python sidecar 构建步骤；日常使用请优先运行仓库根目录的 `scripts/start_desktop.ps1`。

## 架构

- **Frontend**: Svelte 5 (复用现有 `frontend_svelte` 代码)
- **Backend**: Tauri 2.x Rust 运行时
- **Engine**: `wa_core` + `wa_engine` (路径引用)
- **Python Sidecar**: 开发时从项目 `.venv` 拉起 FastAPI；也可通过 `WRITING_AGENT_PYTHON_BACKEND` 指定可执行文件

## 目录结构

```
desktop-tauri/
├── src/                        # Svelte 前端源码
│   ├── App.svelte
│   ├── AppWorkbench.svelte
│   └── lib/...
├── src-tauri/
│   ├── Cargo.toml              # Rust 依赖
│   ├── src/main.rs             # Tauri commands
│   ├── tauri.conf.json         # Tauri 配置
│   └── capabilities/default.json
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## 开发

```bash
# 安装前端依赖
npm install

# 开发模式（需要仓库根目录已有 .venv）
npm run tauri dev

# 仅构建实验桌面壳；发布前仍需提供 python-backend.exe
npm run tauri build
```

开发服务器会把 `/api`、`/download` 和工作区路由代理到 `http://127.0.0.1:8000`。退出桌面程序时，由它启动的 Python 子进程会一并关闭。

## Commands

| Command | 描述 |
|---|---|
| `load_json` | 加载文档 JSON |
| `export_json` | 导出文档 JSON |
| `insert_text` | 插入文本 |
| `toggle_bold` / `toggle_italic` | 样式切换 |
| `set_heading` | 设置标题层级 |
| `insert_list` / `insert_table` | 插入列表/表格 |
| `undo` / `redo` | 撤销/重做 |
| `find` / `replace` | 查找替换 |
| `export_markdown` / `import_markdown` | Markdown 导入导出 |
| `layout` | 文档排版 |
| `ping` | 健康检查 |
