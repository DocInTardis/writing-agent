# 导出质量与解耦执行报告（2026-02-25）

## 1. 对应执行规范

- 规范文件：`docs/EXPORT_QUALITY_DECOUPLING_EXECUTION_SPEC_20260225_CN.md`
- 执行状态：**已按清单全部完成**

## 2. 完成项逐条核对

- [x] 新增导出质量 domain：`writing_agent/web/domains/export_quality_domain.py`
- [x] `app_v2.py` 导出清洗函数改为薄封装并调用 domain
- [x] 导出清洗改为保语义策略（不再删除 `*`、不再去掉列表标记、不再短行强拼接）
- [x] 严格模式默认关闭（支持环境变量显式开启）
- [x] 移除“无引用时注入占位参考文献”
- [x] 仅在有真实引用需求时处理参考文献章节约束
- [x] `download_docx` 自动修复只在严格模式触发
- [x] 回归测试已补齐并更新
- [x] 目标测试命令执行通过

## 3. 关键代码改动

### 3.1 架构解耦（导出链路局部）

- 新增：
  - `writing_agent/web/domains/export_quality_domain.py`
- 调整：
  - `writing_agent/web/app_v2.py`
    - `_clean_export_text` -> 薄封装，委托 domain
    - `_compact_list_spacing_for_export` -> 薄封装，委托 domain

### 3.2 导出算法修复

- `writing_agent/web/app_v2.py`
  - `_normalize_export_text`：仅在 `strict_doc_format=True` 时执行标题去重，不再默认强改结构。
  - `_strict_doc_format_enabled`：默认关闭，支持 `WRITING_AGENT_STRICT_DOC_FORMAT_DEFAULT`。
  - `_strict_citation_verify_enabled`：默认关闭，支持 `WRITING_AGENT_STRICT_CITATION_VERIFY_DEFAULT`。
  - `_ensure_reference_section`：无真实引用时不再注入占位参考文献。
  - `_export_quality_report`：
    - 仅在“有真实引用需求”时校验参考文献相关规则；
    - 默认模式下不强制 TOC/参考文献。

- `writing_agent/web/services/export_service.py`
  - `download_docx`：`auto_fix` 改为仅严格模式启用。

## 4. 测试变更

- 更新：
  - `tests/test_generation_guards.py`
    - 引用核验阻断相关用例改为显式开启 `strict_citation_verify=True`
    - 结构校验 off/warn 用例改为显式覆盖严格开关
    - 新增默认非严格模式不强制结构用例
- 新增：
  - `tests/export/test_docx_export.py`
    - 清洗保留 Markdown 强调与列表标记
    - 无引用时不注入占位参考文献
    - 严格开关默认关闭验证
    - 仅严格模式触发标题去重验证

## 5. 执行验证结果

- 执行命令：
  - `python -m pytest -q tests/export/test_docx_export.py tests/test_generation_guards.py tests/test_doc_format_heading_glue.py`
- 结果：
  - `34 passed in 10.64s`

## 6. 行为变化（前后对比）

- 修复前：
  - 默认就进入严格结构约束，导出前会进行多轮强改写；
  - 清洗阶段会删除单星号和列表标记，易造成语义损失；
  - 无引用也可能被插入占位参考文献。
- 修复后：
  - 默认非严格导出，保留用户原文语义；
  - 严格模式需显式开启，且仅在有真实引用需求时约束参考文献；
  - 自动修复不再默认对所有导出路径生效。

## 7. 格式参考核对（知网/标准）

查询时间：2026-02-25。用于校对“参考文献与学术格式约束应作为可选严格策略，而非默认强制”这一执行方向。

- 国家标准信息平台检索页显示 `GB/T 7714-2025` 已发布，实施日期为 **2026-07-01**，并替代 `GB/T 7714-2015`：
  - https://std.samr.gov.cn/gb/search/gbDetailed?id=1D45D6C7CA6C6A5BE06397BE0A0A168A
- CNKI 期刊页面可见主流引文导出格式包含 GB/T 7714 等：
  - https://zgty.cbpt.cnki.net/portal/journal/portal/client/newest

结论：默认导出应优先保证语义完整；学术格式强化（如严格参考文献校验）应为显式开关策略。
