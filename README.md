# 写作 Agent（课程报告/论文写作辅助）

基于 `写作agent.md` 的最小可运行原型：左侧像 Word 一样编辑，右侧用自然语言下指令，Agent 直接修改文档并可导出 `.docx`。


## 运行

### 一键启动（推荐）

确保已安装 Ollama（并且 `ollama` 在 PATH 中），然后在项目根目录执行：

```powershell
.\start.ps1
```

或双击 `start.bat`。

默认会：
- 启动本地 Ollama（`ollama serve`，`OLLAMA_HOST=http://127.0.0.1:11434`）
- 拉取并使用模型 `qwen:7b`（`ollama pull qwen:7b`，`OLLAMA_MODEL=qwen:7b`）
- 启动 Web：`http://127.0.0.1:8000`

如果你需要指定 pip 镜像：

```powershell
.\start.ps1 -IndexUrl https://pypi.org/simple
```

### 手动安装/启动

1) 安装依赖

```bash
python -m venv .venv
.venv\\Scripts\\pip install -r requirements.txt
```

如果你遇到镜像源 `HTTP 403`（例如清华源偶发对部分文件返回 403），可以临时切到官方源或其它镜像：

```bash
.venv\\Scripts\\pip install -r requirements.txt -i https://pypi.org/simple
```

或：

```bash
.venv\\Scripts\\pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple
```

2) 启动 Web

```bash
.venv\\Scripts\\uvicorn writing_agent.web.app:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`。

## 说明

- 默认使用本地 Ollama（`qwen:7b`）把自然语言指令应用到左侧文档。
- 引用：目前只保留 `[@citekey]` 文本标注（可在后续版本把引用管理与导出格式化接上）。

## 模板

- 内置参考模板：`writing_agent/report_templates/`（选择后会按模板章节强制补齐段落与内容占位）
- 上传模板：在 `/new` 页面上传 `.html` 模板（支持 `{{TITLE}}` 占位符）

## 图表

- 工作台工具栏支持插入流程图/ER 图（会生成内嵌 SVG）。
- 也支持在右侧指令框使用：
  - /flow ... 生成流程图并插入到文档末尾
  - /er ... 生成 ER 图并插入到文档末尾

## 编辑

- 字体/字号：支持宋体/黑体等与小四/小五等，导出 .docx 会保留。
- 字色/高亮：支持对选中文本应用颜色与背景高亮。
- 段落：支持对齐与行距（作用于当前段落）。
- 表格/图片：支持插入表格与上传图片（图片导出 .docx 可保留）。



