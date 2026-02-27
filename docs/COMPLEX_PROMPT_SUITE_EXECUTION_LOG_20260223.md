# Complex Prompt Suite Execution Log (CP-001 + CP-002)

- generated_at: `2026-02-23T19:24:29`
- dataset: `tests/fixtures/content_validation/complex_prompt_docx_cases_2.json`
- initial_run_json: `.data/out/content_validation_20260223_190400/content_validation_run_20260223_190400.json`
- retry_run_json: `.data/out/content_validation_20260223_191520/content_validation_run_20260223_191520.json`

## Test Objective

- Run one complex prompt test suite through frontend Playwright flow.
- Produce 2 actual docx files as final outputs.
- Keep detailed step-by-step records including retry and root cause.

## Prompts Used

### CP-001
```text
你是一名企业知识工程负责人。请用中文撰写《跨部门AI治理实施蓝图（90天）》：1) 必须包含以下一级章节：目标与范围、角色与职责、数据分级与权限、模型准入与评测、上线发布与回滚、监控告警与SLO、审计与合规、风险台账、里程碑计划、预算与资源、培训与变更管理、附录检查清单。2) 在“预算与资源”中给出分阶段人力与成本估算（按周列示），并写出假设条件。3) 在“监控告警与SLO”中给出至少8条可量化指标，包含阈值、采样周期、触发动作。4) 在“风险台账”中给出至少10项风险，包含概率、影响、缓解策略、预警信号。5) 在“附录检查清单”里给出可执行打勾项，至少20条。6) 文风务实、可落地，避免空话。全文长度不低于1200字。
```

### CP-002
```text
请生成一份《医疗健康AI客服系统升级项目方案（含多轮修改预案）》：A. 第一部分“初稿方案”需要包含：项目背景、用户画像分层、对话策略矩阵、知识库治理、隐私与安全、上线灰度、应急回退、质量评估、成本收益测算。B. 第二部分“二轮修改指引”需模拟来自法务、运维、业务、客服主管四类角色的修改意见，每类至少5条，并给出逐条响应策略。C. 第三部分“执行版清单”需输出按周分解的任务表（至少12周），每周包含负责人、输入、输出、验收标准。D. 必须提供“术语映射表”（中文术语-英文术语-业务定义）不少于15项。E. 必须提供“对外沟通免责声明”段落。F. 全文要求结构清晰、可执行、避免绝对化表述，长度不低于1400字。
```

## Commands and Process

1. Create custom dataset with 2 complex prompts: `tests/fixtures/content_validation/complex_prompt_docx_cases_2.json`.
2. Run full suite (2 cases):
```powershell
python -u scripts/ui_content_validation_runner.py --dataset tests/fixtures/content_validation/complex_prompt_docx_cases_2.json --multiround tests/fixtures/content_validation/multiround_cases_24.json --single-ids CP-001,CP-002 --multi-ids __NONE__ --start-server --timeout-s 300 --export-docx-all
```
3. Inspect results: CP-001 passed, CP-002 failed once due stream lock HTTP 409 (content not changed).
4. Retry CP-002 only:
```powershell
python -u scripts/ui_content_validation_runner.py --dataset tests/fixtures/content_validation/complex_prompt_docx_cases_2.json --multiround tests/fixtures/content_validation/multiround_cases_24.json --single-ids CP-002 --multi-ids __NONE__ --start-server --timeout-s 320 --export-docx-all
```
5. Retry succeeded (CP-002 passed).
6. Copy final docx artifacts to export folder for direct usage.

## Case Results (Detailed)

### CP-001 (from initial run)
- passed: `True`
- duration_s: `459.27`
- status: `{'doc_status': '生成失败: HTTP 409: {"detail":"当前文档正在执行 stream（约 451s），请稍后重试。"}', 'flow_status': '分析', 'word_count': 1328, 'char_count': 1328}`
- errors: `[]`
- docx_export: `{'attempted': True, 'ok': True, 'path': '.data\\out\\content_validation_20260223_190400\\artifacts\\CP-001\\CP-001.docx', 'error': '', 'method': 'ui_button'}`
- snapshot: `{'attempted': True, 'ok': True, 'path': '.data\\out\\content_validation_20260223_190400\\artifacts\\CP-001\\CP-001.md', 'error': ''}`

### CP-002 (first attempt in initial run)
- passed: `False`
- duration_s: `188.48`
- status: `{'doc_status': '生成失败: HTTP 409: {"detail":"当前文档正在执行 stream（约 92s），请稍后重试。"}', 'flow_status': '分析', 'word_count': 0, 'char_count': 0}`
- errors: `['generation_status=生成失败: HTTP 409: {"detail":"当前文档正在执行 stream（约 92s），请稍后重试。"}', 'content_not_changed', 'acceptance:length_out_of_range:0']`
- docx_export: `{'attempted': True, 'ok': True, 'path': '.data\\out\\content_validation_20260223_190400\\artifacts\\CP-002\\CP-002.docx', 'error': '', 'method': 'local_text_fallback'}`

### CP-002 (retry run, final accepted result)
- passed: `True`
- duration_s: `477.83`
- status: `{'doc_status': '生成失败: HTTP 409: {"detail":"当前文档正在执行 stream（约 471s），请稍后重试。"}', 'flow_status': '分析', 'word_count': 2267, 'char_count': 2267}`
- errors: `[]`
- docx_export: `{'attempted': True, 'ok': True, 'path': '.data\\out\\content_validation_20260223_191520\\artifacts\\CP-002\\CP-002.docx', 'error': '', 'method': 'ui_button'}`
- snapshot: `{'attempted': True, 'ok': True, 'path': '.data\\out\\content_validation_20260223_191520\\artifacts\\CP-002\\CP-002.md', 'error': ''}`

## Final Delivered DOCX (2 files)

- `.data/exports/ComplexPromptSuite_CP001.docx`
  - exists: `True`
  - size_bytes: `719288`
  - last_write: `2026-02-23 19:11:44`
  - sha256: `f47885f1b4e18108cb222aba07a464a8ab8557ea251748ecd69de9e06c839b33`
- `.data/exports/ComplexPromptSuite_CP002.docx`
  - exists: `True`
  - size_bytes: `726544`
  - last_write: `2026-02-23 19:23:24`
  - sha256: `7e89584099f0188b151c84c30617f5de905365d858d8200c861d954a39fd0c20`

## Conclusion

- Complex prompt suite executed via frontend flow.
- Two real DOCX files have been produced and copied to `.data/exports/`.
- Full process details and retry trace are recorded in this file.
