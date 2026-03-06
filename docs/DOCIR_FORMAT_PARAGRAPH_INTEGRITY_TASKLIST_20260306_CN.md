# DocIR格式与段落完整性优化任务清单（2026-03-06）

> 目标：保证输出严格按既定格式生成，并且每个段落为完整语义单元，不出现截断、误删、误拆。

- [x] 任务1：移除生成链路中的总字数硬上限绑定（禁止 `min_total_chars` 与 `max_total_chars` 绑定为同一值）。
- [x] 任务2：关闭/改造总字数收尾裁剪入口，避免在最终聚合后切断段落结尾。
- [x] 任务3：调整文本清洗规则，禁止按“ASCII行”直接删行，保留英文参考文献、DOI、URL等内容。
- [x] 任务4：新增段落完整性校验（句尾完整、括号闭合、引号闭合等），不满足则自动续写补全。
- [x] 任务5：优化超时策略：优先续写补齐而不是直接回退短文本；提升长文场景稳定性。
- [x] 任务6：将参考文献修复切换为保守模式：不激进拆分、不激进重排，优先保留原始条目结构。
- [x] 任务7：降低导出层猜测式分段强度，避免标题/段落在导出阶段被截短或错误拆分。
- [x] 任务8：强化 DocIR 单一真源：减少 text↔DocIR 往返引入的内容漂移，保证导出与编辑一致。
- [x] 任务9：严格结构输出约束：结构化输出不合规时必须重试或失败，不走弱兜底混合输出。
- [x] 任务10：增加“截断原因码”可观测埋点（例如：context_trim、timeout_fallback、post_trim、sanitize_drop）。
- [x] 任务11：补全自动化测试（长段落、英文文献、中英混排、超时恢复、导出一致性）并跑回归。
- [x] 任务12：更新本清单为全量完成状态，并附上实际修改文件与测试结果。

## 实际修改文件

- writing_agent/web/app_v2_generate_stream_runtime.py
- writing_agent/web/services/generation_service.py
- writing_agent/v2/graph_runner_runtime.py
- writing_agent/v2/graph_text_sanitize_domain.py
- writing_agent/v2/graph_section_draft_domain.py
- writing_agent/v2/graph_runner.py
- writing_agent/web/app_v2_textops_runtime_part2.py
- writing_agent/document/v2_report_docx_helpers.py
- writing_agent/web/domains/doc_state_domain.py
- writing_agent/web/api/editing_flow.py
- tests/unit/test_docir_format_integrity_guards.py

## 回归测试结果

- 命令：`python -m pytest -q tests/unit/test_docir_format_integrity_guards.py tests/unit/test_inline_context_policy.py tests/test_generation_route_graph.py tests/export/test_docx_export.py tests/test_studio_stream_constraints.py tests/test_generation_guards.py`
- 结果：`55 passed`

- 命令：`python -m pytest -q tests/export/test_docx_export.py tests/test_studio_stream_constraints.py tests/test_generation_guards.py`
- 结果：`36 passed`
