# Writing Agent Desktop (Tauri 2.x)

PoC 桌面端应用，基于 Tauri 2.x + Svelte 5 + Rust 引擎。

## 架构

- **Frontend**: Svelte 5 (复用现有 `frontend_svelte` 代码)
- **Backend**: Tauri 2.x Rust 运行时
- **Engine**: `wa_core` + `wa_engine` (路径引用)
- **Python Sidecar**: 启动时拉起 Python FastAPI 后端

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

# 开发模式（自动启动 Python 后端 sidecar）
npm run tauri dev

# 构建
npm run tauri build
```

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
