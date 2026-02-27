# 架构解耦执行规范（2026-02-25）

## 1. 目标
- 直接降低 `writing_agent/web/app_v2.py` 的体量与耦合度。
- 将“业务实现”从 `app_v2.py` 拆到独立领域模块，`app_v2.py` 只保留装配与兼容入口。
- 引入行数治理，防止后续再次出现超大业务文件失控增长。

## 2. 强约束（本规范内必须执行）
- 不修改现有 API 路径与响应语义。
- 不删除现有兼容函数名（尤其是测试覆盖到的私有函数）。
- 新增领域模块后，服务层优先依赖领域模块，不再新增对 `app_v2` 私有实现的直接依赖。
- 新增行数治理脚本与测试，并纳入仓库。

## 3. 本轮执行清单（全部执行）
1. 新增以下领域模块：
   - `writing_agent/web/domains/plagiarism_domain.py`
   - `writing_agent/web/domains/citation_render_domain.py`
   - `writing_agent/web/domains/doc_ir_html_domain.py`
2. 从 `app_v2.py` 迁出对应实现，`app_v2.py` 仅保留薄封装（wrapper）或导入绑定。
3. 调整 `writing_agent/web/services/quality_service.py`，让抄袭检测相关逻辑优先走 `plagiarism_domain`。
4. 新增行数治理：
   - `scripts/guard_file_line_limits.py`
   - `security/file_line_limits.json`
   - `tests/test_file_line_limits_guard.py`
5. 执行验证并记录结果：
   - 统计 `app_v2.py` 重构前后行数变化。
   - 跑与改动直接相关的测试。

## 4. 验收标准
- 代码可运行，相关测试通过。
- `app_v2.py` 行数显著下降（本轮至少下降 700 行）。
- 所有新增模块均被真实调用，不允许“只建文件不接线”。
- 行数治理脚本可在本地直接执行并输出机器可读结果（JSON）。

## 5. 后续增量（不阻塞本轮验收）
- 继续将生成编排（generation orchestration）从 `app_v2.py` 下沉到独立 orchestrator。
- 将 citation verify 大块逻辑进一步外移到可注入上下文的组件。
- 对 `graph_runner.py` 与 `v2_report_docx.py` 应用同一治理策略。
