# Failure Breakdown (Detailed)

Generated at: 2026-02-24T14:44:15.069498

- Total failed items: 76
- Content validation failed items: 44
- Two-stage failed items: 32

## 1. [content] run=20260222_195838 case=C-001 mode=single
- Scenario: single/academic_research/C-001
- Scenario detail: ???????????????????????????????AI???????????????????????????????????????????? ???????????????
- Failure reasons: generation_timeout, generation_not_finished, acceptance:length_out_of_range, acceptance:missing_required_keywords, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260222_195838\artifacts\C-001`

## 2. [content] run=20260222_200114 case=C-001 mode=single
- Scenario: single/academic_research/C-001
- Scenario detail: ???????????????????????????????AI???????????????????????????????????????????? ???????????????
- Failure reasons: acceptance:missing_required_keywords, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260222_200114\artifacts\C-001`

## 3. [content] run=20260222_200602 case=C-001 mode=single
- Scenario: single/academic_research/C-001
- Scenario detail: ???????????????????????????????AI???????????????????????????????????????????? ???????????????
- Failure reasons: acceptance:missing_required_keywords, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260222_200602\artifacts\C-001`

## 4. [content] run=20260222_201202 case=C-001 mode=single
- Scenario: single/academic_research/C-001
- Scenario detail: Write a Research Report for undergraduate student on topic 'Impact of generative AI on course design quality'. Requirements: Use section ...
- Failure reasons: acceptance:missing_required_keywords, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260222_201202\artifacts\C-001`

## 5. [content] run=20260222_202003 case=MR-001 mode=multiround
- Scenario: multiround/academic_research/MR-001
- Scenario detail: Academic iterative paper revision
- Failure reasons: round_constraint:missing_must_keep, round_constraint:missing_must_change, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260222_202003\artifacts\MR-001`

## 6. [content] run=20260222_202003 case=C-008 mode=single
- Scenario: single/government_public/C-008
- Scenario detail: Write a Policy Execution Brief for frontline clerk on topic 'Community eldercare expansion plan'. Requirements: Use section headers: Back...
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260222_202003\artifacts\C-008`

## 7. [content] run=20260222_202003 case=C-057 mode=single
- Scenario: single/technical_manual/C-057
- Scenario detail: Write a Technical Operation Manual for junior engineer on topic 'Rollback workflow in staged releases'. Requirements: Use section headers...
- Failure reasons: generation_status_model_timeout_or_unreachable
- Artifact: `.data\out\content_validation_20260222_202003\artifacts\C-057`

## 8. [content] run=20260222_210626 case=MR-001 mode=multiround
- Scenario: multiround/academic_research/MR-001
- Scenario detail: Academic iterative paper revision
- Failure reasons: round_constraint:missing_must_change, acceptance:missing_required_headings, round_constraint:missing_must_keep, acceptance:length_out_of_range, acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260222_210626\artifacts\MR-001`

## 9. [content] run=20260222_212518 case=MR-001 mode=multiround
- Scenario: multiround/academic_research/MR-001
- Scenario detail: Academic iterative paper revision
- Failure reasons: acceptance:missing_required_headings, acceptance:length_out_of_range, acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260222_212518\artifacts\MR-001`

## 10. [content] run=20260222_214003 case=MR-001 mode=multiround
- Scenario: multiround/academic_research/MR-001
- Scenario detail: Academic iterative paper revision
- Failure reasons: acceptance:length_out_of_range, acceptance:missing_required_keywords, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260222_214003\artifacts\MR-001`

## 11. [content] run=20260222_215121 case=MR-001 mode=multiround
- Scenario: multiround/academic_research/MR-001
- Scenario detail: Academic iterative paper revision
- Failure reasons: acceptance:missing_required_keywords, round_constraint:missing_must_change, round_constraint:content_not_changed
- Artifact: `.data\out\content_validation_20260222_215121\artifacts\MR-001`

## 12. [content] run=20260222_222355 case=C-022 mode=single
- Scenario: single/marketing_brand/C-022
- Scenario detail: Write a Campaign Content Plan for brand manager on topic 'New purifier launch messaging'. Requirements: Use section headers: Background, ...
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260222_222355\artifacts\C-022`

## 13. [content] run=20260222_222355 case=C-029 mode=single
- Scenario: single/customer_service/C-029
- Scenario detail: Write a Customer Communication Script for agent on topic 'Bulk delay complaint handling'. Requirements: Use section headers: Background, ...
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260222_222355\artifacts\C-029`

## 14. [content] run=20260222_222355 case=C-057 mode=single
- Scenario: single/technical_manual/C-057
- Scenario detail: Write a Technical Operation Manual for junior engineer on topic 'Rollback workflow in staged releases'. Requirements: Use section headers...
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260222_222355\artifacts\C-057`

## 15. [content] run=20260222_231158 case=C-029 mode=single
- Scenario: single/customer_service/C-029
- Scenario detail: Write a Customer Communication Script for agent on topic 'Bulk delay complaint handling'. Requirements: Use section headers: Background, ...
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260222_231158\artifacts\C-029`

## 16. [content] run=20260222_231158 case=C-057 mode=single
- Scenario: single/technical_manual/C-057
- Scenario detail: Write a Technical Operation Manual for junior engineer on topic 'Rollback workflow in staged releases'. Requirements: Use section headers...
- Failure reasons: acceptance:length_out_of_range, acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260222_231158\artifacts\C-057`

## 17. [content] run=20260222_234017 case=C-057 mode=single
- Scenario: single/technical_manual/C-057
- Scenario detail: Write a Technical Operation Manual for junior engineer on topic 'Rollback workflow in staged releases'. Requirements: Use section headers...
- Failure reasons: generation_status_http409_busy
- Artifact: `.data\out\content_validation_20260222_234017\artifacts\C-057`

## 18. [content] run=20260223_002839 case=C-057 mode=single
- Scenario: single/technical_manual/C-057
- Scenario detail: Write a Technical Operation Manual for junior engineer on topic 'Rollback workflow in staged releases'. Requirements: Use section headers...
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260223_002839\artifacts\C-057`

## 19. [content] run=20260223_004303 case=MR-001 mode=multiround
- Scenario: multiround/academic_research/MR-001
- Scenario detail: Academic iterative paper revision
- Failure reasons: acceptance:length_out_of_range
- Artifact: `.data\out\content_validation_20260223_004303\artifacts\MR-001`

## 20. [content] run=20260223_170154 case=MR-001 mode=multiround
- Scenario: multiround/academic_research/MR-001
- Scenario detail: Academic iterative paper revision
- Failure reasons: generation_status_model_disabled, acceptance:length_out_of_range, acceptance:missing_required_keywords, acceptance:missing_required_headings, docx_export_failed
- Artifact: `.data\out\content_validation_20260223_170154\artifacts\MR-001`

## 21. [content] run=20260223_170154 case=C-001 mode=single
- Scenario: single/academic_research/C-001
- Scenario detail: Write a Research Report for undergraduate student on topic 'Impact of generative AI on course design quality'. Requirements: Use section ...
- Failure reasons: generation_status_model_disabled, content_not_changed, acceptance:length_out_of_range, acceptance:missing_required_keywords, acceptance:missing_required_headings, docx_export_failed
- Artifact: `.data\out\content_validation_20260223_170154\artifacts\C-001`

## 22. [content] run=20260223_172623 case=MR-001 mode=multiround
- Scenario: multiround/academic_research/MR-001
- Scenario detail: Academic iterative paper revision
- Failure reasons: acceptance:length_out_of_range
- Artifact: `.data\out\content_validation_20260223_172623\artifacts\MR-001`

## 23. [content] run=20260223_172623 case=C-001 mode=single
- Scenario: single/academic_research/C-001
- Scenario detail: Write a Research Report for undergraduate student on topic 'Impact of generative AI on course design quality'. Requirements: Use section ...
- Failure reasons: docx_export_failed
- Artifact: `.data\out\content_validation_20260223_172623\artifacts\C-001`

## 24. [content] run=20260223_174321 case=C-001 mode=single
- Scenario: single/academic_research/C-001
- Scenario detail: Write a Research Report for undergraduate student on topic 'Impact of generative AI on course design quality'. Requirements: Use section ...
- Failure reasons: docx_export_failed
- Artifact: `.data\out\content_validation_20260223_174321\artifacts\C-001`

## 25. [content] run=20260223_180936 case=C-001 mode=single
- Scenario: single/academic_research/C-001
- Scenario detail: Write a Research Report for undergraduate student on topic 'Impact of generative AI on course design quality'. Requirements: Use section ...
- Failure reasons: generation_status_model_disabled, content_not_changed, acceptance:length_out_of_range, acceptance:missing_required_keywords, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260223_180936\artifacts\C-001`

## 26. [content] run=20260223_184816 case=C-042 mode=single
- Scenario: single/healthcare_science/C-042
- Scenario detail: Write a Health Education Material for employee wellness admin on topic 'Early response for sports injuries'. Requirements: Output two par...
- Failure reasons: acceptance:missing_required_keywords, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260223_184816\artifacts\C-042`

## 27. [content] run=20260223_184816 case=C-049 mode=single
- Scenario: single/legal_compliance/C-049
- Scenario detail: Write a Risk Notice Document for sales representative on topic 'Online terms update communication'. Requirements: Output two parts: Draft...
- Failure reasons: acceptance:missing_required_keywords, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260223_184816\artifacts\C-049`

## 28. [content] run=20260223_190400 case=CP-002 mode=single
- Scenario: single/custom_complex/CP-002
- Scenario detail: 请生成一份《医疗健康AI客服系统升级项目方案（含多轮修改预案）》：A. 第一部分“初稿方案”需要包含：项目背景、用户画像分层、对话策略矩阵、知识库治理、隐私与安全、上线灰度、应急回退、质量评估、成本收益测算。B. 第二部分“二轮修改指引”需模拟来自法务、运维、业务、客服主管...
- Failure reasons: generation_status_http409_busy, content_not_changed, acceptance:length_out_of_range
- Artifact: `.data\out\content_validation_20260223_190400\artifacts\CP-002`

## 29. [content] run=20260223_220224 case=CP-002 mode=single
- Scenario: single/custom_complex/CP-002
- Scenario detail: 请生成一份《医疗健康AI客服系统升级项目方案（含多轮修改预案）》：A. 第一部分“初稿方案”需要包含：项目背景、用户画像分层、对话策略矩阵、知识库治理、隐私与安全、上线灰度、应急回退、质量评估、成本收益测算。B. 第二部分“二轮修改指引”需模拟来自法务、运维、业务、客服主管...
- Failure reasons: generation_status_http409_busy, content_not_changed, acceptance:length_out_of_range
- Artifact: `.data\out\content_validation_20260223_220224\artifacts\CP-002`

## 30. [content] run=20260223_223244 case=CP-001 mode=single
- Scenario: single/custom_complex/CP-001
- Scenario detail: 你是一名企业知识工程负责人。请用中文撰写《跨部门AI治理实施蓝图（90天）》：1) 必须包含以下一级章节：目标与范围、角色与职责、数据分级与权限、模型准入与评测、上线发布与回滚、监控告警与SLO、审计与合规、风险台账、里程碑计划、预算与资源、培训与变更管理、附录检查清单。2...
- Failure reasons: generation_timeout, generation_not_finished
- Artifact: `.data\out\content_validation_20260223_223244\artifacts\CP-001`

## 31. [content] run=20260223_223244 case=CP-002 mode=single
- Scenario: single/custom_complex/CP-002
- Failure reasons: playwright_timeout
- Artifact: `.data\out\content_validation_20260223_223244\artifacts\CP-002`

## 32. [content] run=20260223_225331 case=CP-001 mode=single
- Scenario: single/custom_complex/CP-001
- Scenario detail: 你是一名企业知识工程负责人。请用中文撰写《跨部门AI治理实施蓝图（90天）》：1) 必须包含以下一级章节：目标与范围、角色与职责、数据分级与权限、模型准入与评测、上线发布与回滚、监控告警与SLO、审计与合规、风险台账、里程碑计划、预算与资源、培训与变更管理、附录检查清单。2...
- Failure reasons: generation_timeout, generation_not_finished
- Artifact: `.data\out\content_validation_20260223_225331\artifacts\CP-001`

## 33. [content] run=20260223_233703 case=MR-003 mode=multiround
- Scenario: multiround/marketing_brand/MR-003
- Scenario detail: Marketing copy compliance rewrite
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260223_233703\artifacts\MR-003`

## 34. [content] run=20260223_233703 case=MR-009 mode=multiround
- Scenario: multiround/academic_research/MR-009
- Scenario detail: Font-size strict revision
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260223_233703\artifacts\MR-009`

## 35. [content] run=20260223_233703 case=MR-010 mode=multiround
- Scenario: multiround/legal_compliance/MR-010
- Scenario detail: High-risk boundary correction
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260223_233703\artifacts\MR-010`

## 36. [content] run=20260224_000252 case=CMR-001 mode=multiround
- Scenario: multiround/custom_revision/CMR-001
- Scenario detail: Enterprise governance plan iterative revision
- Failure reasons: acceptance:length_out_of_range, acceptance:missing_required_keywords, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260224_000252\artifacts\CMR-001`

## 37. [content] run=20260224_000252 case=CMR-002 mode=multiround
- Scenario: multiround/custom_revision/CMR-002
- Scenario detail: Healthcare SOP iterative revision
- Failure reasons: acceptance:missing_required_keywords, acceptance:missing_required_headings, acceptance:length_out_of_range, generation_timeout, generation_not_finished
- Artifact: `.data\out\content_validation_20260224_000252\artifacts\CMR-002`

## 38. [content] run=20260224_000252 case=CMR-003 mode=multiround
- Scenario: multiround/custom_revision/CMR-003
- Scenario detail: Government service optimization iterative revision
- Failure reasons: generation_timeout, generation_not_finished, acceptance:length_out_of_range, acceptance:missing_required_keywords, acceptance:missing_required_headings, generation_status_http409_busy
- Artifact: `.data\out\content_validation_20260224_000252\artifacts\CMR-003`

## 39. [content] run=20260224_005508 case=SMR-001 mode=multiround
- Scenario: multiround/revision_smoke/SMR-001
- Scenario detail: Policy memo iterative edit
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260224_005508\artifacts\SMR-001`

## 40. [content] run=20260224_005508 case=SMR-002 mode=multiround
- Scenario: multiround/revision_smoke/SMR-002
- Scenario detail: Customer reply iterative polish
- Failure reasons: acceptance:missing_required_keywords, acceptance:length_out_of_range
- Artifact: `.data\out\content_validation_20260224_005508\artifacts\SMR-002`

## 41. [content] run=20260224_005508 case=SMR-003 mode=multiround
- Scenario: multiround/revision_smoke/SMR-003
- Scenario detail: Ops runbook iterative revision
- Failure reasons: acceptance:missing_required_keywords
- Artifact: `.data\out\content_validation_20260224_005508\artifacts\SMR-003`

## 42. [content] run=20260224_012358 case=EMR-001 mode=multiround
- Scenario: multiround/revision_en_smoke/EMR-001
- Scenario detail: Incident response runbook iterative edit
- Failure reasons: acceptance:missing_required_keywords, generation_timeout, generation_not_finished, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260224_012358\artifacts\EMR-001`

## 43. [content] run=20260224_012358 case=EMR-002 mode=multiround
- Scenario: multiround/revision_en_smoke/EMR-002
- Scenario detail: Customer success playbook iterative edit
- Failure reasons: acceptance:missing_required_keywords, acceptance:missing_required_headings, acceptance:length_out_of_range
- Artifact: `.data\out\content_validation_20260224_012358\artifacts\EMR-002`

## 44. [content] run=20260224_012358 case=EMR-003 mode=multiround
- Scenario: multiround/revision_en_smoke/EMR-003
- Scenario detail: Product launch plan iterative edit
- Failure reasons: acceptance:missing_required_keywords, acceptance:missing_required_headings
- Artifact: `.data\out\content_validation_20260224_012358\artifacts\EMR-003`

## 45. [two_stage] run=20260224_022754 case=TS-001 mode=stage1
- Scenario: two_stage/TS-001/stage1
- Scenario detail: ???AI????
- Failure reasons: acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_022754\artifacts\TS-001`

## 46. [two_stage] run=20260224_022754 case=TS-001 mode=stage2
- Scenario: two_stage/TS-001/stage2
- Scenario detail: ???AI????
- Failure reasons: infra_model_unreachable, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_022754\artifacts\TS-001`

## 47. [two_stage] run=20260224_024133 case=TS-001 mode=stage1
- Scenario: two_stage/TS-001/stage1
- Scenario detail: ???AI????
- Failure reasons: acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_024133\artifacts\TS-001`

## 48. [two_stage] run=20260224_024133 case=TS-002 mode=stage1
- Scenario: two_stage/TS-002/stage1
- Scenario detail: ????AI????
- Failure reasons: acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_024133\artifacts\TS-002`

## 49. [two_stage] run=20260224_024133 case=TS-003 mode=stage1
- Scenario: two_stage/TS-003/stage1
- Scenario detail: ??????????
- Failure reasons: acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_024133\artifacts\TS-003`

## 50. [two_stage] run=20260224_024133 case=TS-004 mode=stage1
- Scenario: two_stage/TS-004/stage1
- Scenario detail: ????????????
- Failure reasons: acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_024133\artifacts\TS-004`

## 51. [two_stage] run=20260224_024133 case=TS-001 mode=stage2
- Scenario: two_stage/TS-001/stage2
- Scenario detail: ???AI????
- Failure reasons: infra_model_unreachable, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_024133\artifacts\TS-001`

## 52. [two_stage] run=20260224_024133 case=TS-002 mode=stage2
- Scenario: two_stage/TS-002/stage2
- Scenario detail: ????AI????
- Failure reasons: infra_model_unreachable, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_024133\artifacts\TS-002`

## 53. [two_stage] run=20260224_024133 case=TS-003 mode=stage2
- Scenario: two_stage/TS-003/stage2
- Scenario detail: ??????????
- Failure reasons: acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_024133\artifacts\TS-003`

## 54. [two_stage] run=20260224_024133 case=TS-004 mode=stage2
- Scenario: two_stage/TS-004/stage2
- Scenario detail: ????????????
- Failure reasons: acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_024133\artifacts\TS-004`

## 55. [two_stage] run=20260224_034402 case=TS-001 mode=stage1
- Scenario: two_stage/TS-001/stage1
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_034402\artifacts\TS-001`

## 56. [two_stage] run=20260224_034402 case=TS-001 mode=stage2
- Scenario: two_stage/TS-001/stage2
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_034402\artifacts\TS-001`

## 57. [two_stage] run=20260224_034740 case=TS-001 mode=stage1
- Scenario: two_stage/TS-001/stage1
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_034740\artifacts\TS-001`

## 58. [two_stage] run=20260224_034740 case=TS-002 mode=stage1
- Scenario: two_stage/TS-002/stage1
- Scenario detail: 医疗客服AI分诊SOP
- Failure reasons: acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_034740\artifacts\TS-002`

## 59. [two_stage] run=20260224_034740 case=TS-003 mode=stage1
- Scenario: two_stage/TS-003/stage1
- Scenario detail: 家庭资产配置科普手册
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_034740\artifacts\TS-003`

## 60. [two_stage] run=20260224_034740 case=TS-004 mode=stage1
- Scenario: two_stage/TS-004/stage1
- Scenario detail: 项目制课程教学设计说明
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_034740\artifacts\TS-004`

## 61. [two_stage] run=20260224_034740 case=TS-001 mode=stage2
- Scenario: two_stage/TS-001/stage2
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_034740\artifacts\TS-001`

## 62. [two_stage] run=20260224_034740 case=TS-002 mode=stage2
- Scenario: two_stage/TS-002/stage2
- Scenario detail: 医疗客服AI分诊SOP
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_034740\artifacts\TS-002`

## 63. [two_stage] run=20260224_034740 case=TS-003 mode=stage2
- Scenario: two_stage/TS-003/stage2
- Scenario detail: 家庭资产配置科普手册
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_034740\artifacts\TS-003`

## 64. [two_stage] run=20260224_034740 case=TS-004 mode=stage2
- Scenario: two_stage/TS-004/stage2
- Scenario detail: 项目制课程教学设计说明
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_034740\artifacts\TS-004`

## 65. [two_stage] run=20260224_041455 case=TS-001 mode=stage1
- Scenario: two_stage/TS-001/stage1
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_still_parsing, acceptance_missing_required_keywords
- Artifact: `.data\out\two_stage_validation_20260224_041455\artifacts\TS-001`

## 66. [two_stage] run=20260224_041455 case=TS-001 mode=stage2
- Scenario: two_stage/TS-001/stage2
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_model_unreachable, acceptance_missing_required_keywords
- Artifact: `.data\out\two_stage_validation_20260224_041455\artifacts\TS-001`

## 67. [two_stage] run=20260224_042729 case=TS-001 mode=stage1
- Scenario: two_stage/TS-001/stage1
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_still_parsing
- Artifact: `.data\out\two_stage_validation_20260224_042729\artifacts\TS-001`

## 68. [two_stage] run=20260224_042729 case=TS-003 mode=stage1
- Scenario: two_stage/TS-003/stage1
- Scenario detail: 家庭资产配置科普手册
- Failure reasons: infra_still_parsing
- Artifact: `.data\out\two_stage_validation_20260224_042729\artifacts\TS-003`

## 69. [two_stage] run=20260224_042729 case=TS-001 mode=stage2
- Scenario: two_stage/TS-001/stage2
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_model_unreachable
- Artifact: `.data\out\two_stage_validation_20260224_042729\artifacts\TS-001`

## 70. [two_stage] run=20260224_042729 case=TS-003 mode=stage2
- Scenario: two_stage/TS-003/stage2
- Scenario detail: 家庭资产配置科普手册
- Failure reasons: infra_model_unreachable
- Artifact: `.data\out\two_stage_validation_20260224_042729\artifacts\TS-003`

## 71. [two_stage] run=20260224_045435 case=TS-001 mode=stage1
- Scenario: two_stage/TS-001/stage1
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_045435\artifacts\TS-001`

## 72. [two_stage] run=20260224_045435 case=TS-001 mode=stage2
- Scenario: two_stage/TS-001/stage2
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_model_disabled, acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_045435\artifacts\TS-001`

## 73. [two_stage] run=20260224_045821 case=TS-001 mode=stage1
- Scenario: two_stage/TS-001/stage1
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: infra_still_parsing, acceptance_missing_required_keywords
- Artifact: `.data\out\two_stage_validation_20260224_045821\artifacts\TS-001`

## 74. [two_stage] run=20260224_045821 case=TS-003 mode=stage1
- Scenario: two_stage/TS-003/stage1
- Scenario detail: 家庭资产配置科普手册
- Failure reasons: infra_still_parsing
- Artifact: `.data\out\two_stage_validation_20260224_045821\artifacts\TS-003`

## 75. [two_stage] run=20260224_045821 case=TS-001 mode=stage2
- Scenario: two_stage/TS-001/stage2
- Scenario detail: 企业AI治理90天落地方案
- Failure reasons: acceptance_length_out_of_range, acceptance_missing_required_keywords, acceptance_missing_required_headings
- Artifact: `.data\out\two_stage_validation_20260224_045821\artifacts\TS-001`

## 76. [two_stage] run=20260224_045821 case=TS-003 mode=stage2
- Scenario: two_stage/TS-003/stage2
- Scenario detail: 家庭资产配置科普手册
- Failure reasons: infra_model_unreachable
- Artifact: `.data\out\two_stage_validation_20260224_045821\artifacts\TS-003`

