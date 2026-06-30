# 2026-03-30 项目整治审计（第一轮）

## 本轮方法

依据 `C:\Users\Lenovo\Desktop\md\2026-3-30-通用.md`，本轮按“扫描半成品/死代码 -> 记录问题 -> 修复根因 -> 回归验证”的方式推进，优先处理会阻断真实使用路径与测试链路的问题。

## 本轮已确认并处理的问题

### 1. `meta_db` 初始化链路是半成品
- 现象：`DocumentService` / `FeedbackService` 依赖 `writing_agent.web.meta_db`，但其路径初始化仅放在 FastAPI lifespan 中。
- 影响：在 `TestClient(app)` 非上下文用法、脚本直调或部分非标准启动路径下，`GET /api/doc/{doc_id}` 会因 `meta_db.init() has not been called` 直接失败。
- 根因：元数据库模块假设“所有调用都经过完整应用启动流程”，没有提供懒初始化兜底。
- 本轮处理：为 `writing_agent/web/meta_db.py` 增加惰性初始化能力，自动从当前运行环境推导 `.data` 目录；若工作区存储被重定向，则优先跟随当前 `store` 的持久化目录。
- 结果：工作区详情读取与模板建工作区链路恢复可用。

## 本轮检查过但暂不处理的项

### 2. 受控 fallback / 占位逻辑
- 扫描到 `writing_agent/agents/diagram_agent.py`、`writing_agent/agents/document_edit.py`、`writing_agent/state_engine/dual_engine.py` 等位置存在 `fallback` 或 `pass`。
- 判断：这些点当前主要承担“解析失败降级”“可选后端不可用时回退”“异常吞掉后继续兜底”的职责，暂不属于可直接删除的死代码。
- 后续要求：如果继续做第 2 轮，应逐项确认是否需要更显式的日志、指标或异常分类，而不是直接删除。

### 3. `engine/` 子目录仍带 WIP 信号
- 扫描到 `engine/README.md` 标注 `(WIP)`，说明该子系统仍处于演进中。
- 判断：这属于独立子系统，不应在本轮“工作区产品化”中顺手大改。
- 后续要求：单独开一轮审计，区分“实验区”与“主产品路径”边界，避免 WIP 能力误导主文档。

## 本轮验证
- `tests/test_workspace_productization.py::test_workspace_lifecycle_routes`
- `tests/test_workspace_productization.py::test_template_catalog_and_template_based_workspace_creation`

## 下一轮建议
1. 继续沿“真实产品路径”扫描 `/api/system/status`、首页摘要、活动流与保存视图的一致性。
2. 对 `workspace` 相关 API 做一次“非 lifespan 启动路径”专项回归，确认不存在类似懒初始化缺口。
3. 再做一轮 dead code 审计时，先限定范围到 `writing_agent/web/` 与 `writing_agent/web/services/`，避免把实验性模块误删。
