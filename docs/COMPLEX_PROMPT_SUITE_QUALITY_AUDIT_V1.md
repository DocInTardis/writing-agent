# Complex Prompt Suite Quality Audit V1

- Scope: `ComplexPromptSuite_CP001.docx`, `ComplexPromptSuite_CP002.docx`
- Method: rule-based audit against custom prompt requirements

## Overall

| Case | Score | Tier |
|---|---:|---|
| CP-001 | 58.35 / 100 | C（可迭代） |
| CP-002 | 77.20 / 100 | B（可内测） |

## CP-001

| Item | Score | Max |
|---|---:|---:|
| 章节覆盖（12项） | 16.67 | 25.00 |
| 长度要求（>=1200字） | 10.00 | 10.00 |
| 预算与资源细化 | 0.00 | 15.00 |
| 监控告警与SLO | 12.75 | 15.00 |
| 风险台账完整度 | 9.60 | 15.00 |
| 附录检查清单 | 0.00 | 10.00 |
| 可执行性表达 | 9.33 | 10.00 |

Details:

- `章节覆盖（12项）`: `{"hit_count": 8, "required_count": 12, "hits": {"目标与范围": true, "角色与职责": true, "数据分级与权限": true, "模型准入与评测": true, "上线发布与回滚": true, "监控告警与SLO": true, "审计与合规": true, "风险台账": true, "里程碑计划": false, "预算与资源": false, "培训与变更管理": false, "附录检查清单": false}}`
- `长度要求（>=1200字）`: `{"chars": 1667}`
- `预算与资源细化`: `{"has_section": false, "has_weekly_breakdown": false, "has_manpower": false, "has_cost": false, "has_assumptions": false}`
- `监控告警与SLO`: `{"metric_count_estimate": 5, "has_threshold": true, "has_sampling_cycle": true, "has_trigger_action": true}`
- `风险台账完整度`: `{"risk_item_ids": ["R1"], "risk_item_count": 1, "has_probability": true, "has_impact": true, "has_mitigation": true, "has_warning_signal": true}`
- `附录检查清单`: `{"checklist_item_count_estimate": 0, "has_checklist_section": false}`
- `可执行性表达`: `{"action_verb_hits": 28}`

## CP-002

| Item | Score | Max |
|---|---:|---:|
| Part A 初稿方案章节 | 25.00 | 25.00 |
| Part B 二轮修改指引 | 20.00 | 20.00 |
| Part C 执行版清单 | 16.00 | 20.00 |
| Part D 术语映射表 | 6.20 | 15.00 |
| Part E 对外沟通免责声明 | 0.00 | 10.00 |
| 长度要求（>=1400字） | 5.00 | 5.00 |
| 表达稳健性（避免绝对化） | 5.00 | 5.00 |

Details:

- `Part A 初稿方案章节`: `{"hit_count": 9, "required_count": 9, "hits": {"项目背景": true, "用户画像分层": true, "对话策略矩阵": true, "知识库治理": true, "隐私与安全": true, "上线灰度": true, "应急回退": true, "质量评估": true, "成本收益测算": true}}`
- `Part B 二轮修改指引`: `{"role_coverage": 4, "response_count_by_role": {"法务意见": 5, "运维意见": 5, "业务意见": 5, "客服主管意见": 5}}`
- `Part C 执行版清单`: `{"week_line_count": 7, "covered_weeks_count": 14, "field_complete_entries": 7, "range_line_count": 6}`
- `Part D 术语映射表`: `{"has_section": true, "term_rows_estimate": 3}`
- `Part E 对外沟通免责声明`: `{"has_disclaimer": false}`
- `长度要求（>=1400字）`: `{"chars": 2621}`
- `表达稳健性（避免绝对化）`: `{"absolute_hits": []}`

## Actionable Fixes (Top)

1. CP-001: 补齐缺失的4个强制章节（里程碑计划、预算与资源、培训与变更管理、附录检查清单）。
2. CP-001: 风险台账扩展到>=10项，并完整包含概率/影响/缓解策略/预警信号。
3. CP-001: 在预算章节补充按周的人力和成本分解，以及显式假设条件。
4. CP-002: 术语映射表扩展到>=15行完整条目。
5. CP-002: 增加对外沟通免责声明段落。
6. CP-002: 执行清单从“周段”改成“逐周”12+行，每行保留负责人/输入/输出/验收标准。
