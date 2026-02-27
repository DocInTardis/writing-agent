# 导出质量修复执行报告（2026-02-26）

## 1. 对应规范

- 规范文件：`docs/EXPORT_QUALITY_EXECUTION_SPEC_20260226_CN.md`
- 执行结论：**全部执行完成**

## 2. 根因结论

导出质量偏低的主因是系统算法与架构策略，不是模型本身：

1. 导出清洗算法存在破坏语义行为（历史上会删符号、改列表、拼接短行）。
2. 严格格式/引用核验默认偏强，普通文档也被套入“学术硬约束”。
3. 无引用数据时仍会尝试构造参考文献章节，造成文本异化。
4. 下载 DOCX 路径默认自动修复，会覆盖原始文本表达。

## 3. 执行项核对

- [x] 新增导出清洗 domain：`writing_agent/web/domains/export_quality_domain.py`
- [x] `app_v2.py` 的 `_clean_export_text` / `_compact_list_spacing_for_export` 改为薄封装委托 domain
- [x] 清洗策略改为“保语义优先”
- [x] `strict_doc_format` 默认关闭（可通过 `WRITING_AGENT_STRICT_DOC_FORMAT_DEFAULT` 覆盖）
- [x] `strict_citation_verify` 默认关闭（可通过 `WRITING_AGENT_STRICT_CITATION_VERIFY_DEFAULT` 覆盖）
- [x] `_ensure_reference_section` 无引用时不再注入占位内容
- [x] 仅在存在真实引用需求时才执行参考文献相关约束
- [x] `download_docx` 自动修复仅在严格模式触发
- [x] 新增/更新回归测试并通过

## 4. 关键改动文件

- `writing_agent/web/domains/export_quality_domain.py`
- `writing_agent/web/app_v2.py`
- `writing_agent/web/services/export_service.py`
- `tests/export/test_docx_export.py`
- `tests/test_generation_guards.py`

## 5. 测试证据

执行命令：

```bash
python -m pytest -q tests/export/test_docx_export.py tests/test_generation_guards.py tests/test_doc_format_heading_glue.py
```

结果：

- `34 passed`

## 6. 行为变化

修复前：

- 默认导出即触发强规则链，文本易被改写；
- 常见 Markdown 表达（如 `*强调*`、列表）可能被破坏；
- 无引用时可能出现占位参考文献文本。

修复后：

- 默认导出优先保留原语义；
- 学术格式约束变为显式开启；
- 只有有真实引用需求时才处理参考文献章节；
- 自动修复不再默认覆盖普通导出。

## 7. 知网/标准依据（查询日期：2026-02-26）

1. CNKI 期刊系统投稿须知样例（明确要求参考文献按 GB/T 7714 著录）：
   - https://hzdb.cbpt.cnki.net/EditorGN/PromptPageInfo.aspx?c=1&t=v
2. CNKI 期刊系统投稿须知样例（给出摘要、篇幅、图表、参考文献等结构化要求）：
   - https://xdcsgdjt.cbpt.cnki.net/EditorE3N/PromptPageInfo.aspx?c=1&t=v
3. CNKI 期刊门户稿约样例（参考文献按 GB/T 7714-2015 及文中引用顺序编码）：
   - https://yxnuxb.cbpt.cnki.net/portal/journal/portal/client/news/8cd36c97c8f94e35d9d705970a2e40e3
4. 全国标准信息公共服务平台 GB/T 7714-2015 条目（实施日期 2015-12-01，并显示相近标准含 GB/T 7714-2025）：
   - https://std.samr.gov.cn/gb/search/gbDetailed?id=71F772D8055ED3A7E05397BE0A0AB82A&review=true
5. 标准公告查询入口（可检索 2025 年第 33 号等国家标准公告）：
   - https://std.samr.gov.cn/noc

结论：CNKI 期刊实践与国家标准条目共同指向“参考文献规范是学术体裁约束”，应放在显式严格模式；默认导出应保持语义完整与可读性优先。本次算法修复与该结论一致。
