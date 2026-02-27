# 导出质量与解耦执行规范（2026-02-25）

## 1. 执行目标

- 修复“导出文本质量偏低”的非模型根因，重点处理导出前算法对语义的破坏。
- 将导出清洗逻辑从 `writing_agent/web/app_v2.py` 下沉到独立 domain，降低单文件耦合。
- 建立回归测试，保证“默认常规导出保语义、显式严格模式可继续生效”。

## 2. 适用范围

- `writing_agent/web/app_v2.py`
- `writing_agent/web/services/export_service.py`
- `writing_agent/web/domains/`（新增导出质量 domain）
- 导出相关测试集：
  - `tests/export/test_docx_export.py`
  - `tests/test_generation_guards.py`
  - `tests/test_doc_format_heading_glue.py`

## 3. 强制执行清单（必须全部完成）

1. 新增 domain 模块：`writing_agent/web/domains/export_quality_domain.py`。
2. `app_v2.py` 导出清洗函数改为薄封装，调用 domain 实现（完成导出链路局部解耦）。
3. `_clean_export_text` 改为保语义清洗：
   - 保留 Markdown 强调符号与列表标记；
   - 保留正文内容，不做短行拼接与符号删除；
   - 仅保留安全性清洗（非法控制字符、标题空格规范、空行压缩）。
4. 严格模式开关改为“显式开启”：
   - `strict_doc_format` 默认关闭；
   - `strict_citation_verify` 默认关闭；
   - 允许通过环境变量显式设定默认值。
5. 移除“无引用时自动注入占位参考文献”行为：
   - `_ensure_reference_section` 在无真实引用数据时直接跳过。
6. 严格导出规则收敛：
   - 仅在“存在真实引用需求”时才校验/整理参考文献章节；
   - 默认模式不强制 TOC/References。
7. `download_docx` 自动修复触发条件调整为“仅严格模式下启用”。
8. 新增/更新回归测试，覆盖：
   - 默认非严格模式不强制结构；
   - 引用核验阻断需显式开启；
   - 清洗不破坏 Markdown 语义；
   - 无引用不注入占位参考文献；
   - 严格模式下结构自修复仍可生效。
9. 执行并通过目标测试命令：
   - `python -m pytest -q tests/export/test_docx_export.py tests/test_generation_guards.py tests/test_doc_format_heading_glue.py`

## 4. 验收标准

- 代码层：
  - 导出清洗逻辑已完成模块化下沉（domain 化）。
  - 默认导出路径不再进行破坏语义的强修补。
  - 参考文献占位注入被移除。
- 行为层：
  - 默认非严格模式下导出不因缺 TOC/参考文献而强阻断。
  - 严格模式显式开启时，结构校验与自动修复仍可用。
- 测试层：
  - 指定测试集全部通过。

## 5. 规范执行原则

- 本规范内条目必须一次性执行完毕，不留“仅文档未落地代码”的空项。
- 若执行中发现冲突，以“保语义、可回归、低耦合”为优先级处理。
