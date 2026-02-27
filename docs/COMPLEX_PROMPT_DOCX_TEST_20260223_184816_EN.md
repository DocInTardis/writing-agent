# Complex Prompt Frontend Test Log (2 Cases / 2 DOCX)

- generated_at: `2026-02-23T19:02:31`
- run_id: `content_validation_20260223_184816`
- run_json: `.data/out/content_validation_20260223_184816/content_validation_run_20260223_184816.json`
- summary_md: `.data/out/content_validation_20260223_184816/content_validation_summary_20260223_184816.md`
- mode: `Playwright frontend flow`

## Goal

- Execute one complex-prompt UI test batch.
- Produce two real docx files from frontend-driven generation flow.
- Record each step and artifact in detail.

## Command

```powershell
python -u scripts/ui_content_validation_runner.py --dataset tests/fixtures/content_validation/content_cases_70.json --multiround tests/fixtures/content_validation/multiround_cases_24.json --single-ids C-042,C-049 --multi-ids __NONE__ --start-server --timeout-s 260 --export-docx-all
```

## Step-by-step

1. Load dataset and rank by prompt length.
2. Select two long complex prompts: C-042 and C-049.
3. Start local web server if not reachable.
4. Run case C-042 in browser UI.
5. Run case C-049 in browser UI.
6. Export docx for each case and verify file existence.
7. Validate docx readability by opening files and sampling paragraphs.

## Case C-042

- group: `healthcare_science`
- prompt_len: `311`
- duration_s: `314.92`
- status: `doc_status=完成`, `flow_status=完成`
- word_count: `990`
- char_count: `990`
- validation_passed: `False`
- validation_errors: `acceptance:missing_required_keywords; acceptance:missing_required_headings`
- docx_ok: `True`
- export_method: `local_text_fallback`
- docx_path: `.data/out/content_validation_20260223_184816/artifacts/C-042/C-042.docx`
- docx_size_bytes: `38377`
- docx_sha256: `2c99ddf64d83234336486ff545407d50aeb9f3b495371136a7427361d696d28a`
- text_snapshot: `.data\out\content_validation_20260223_184816\artifacts\C-042\C-042.md`

prompt:
```text
Write a Health Education Material for employee wellness admin on topic 'Early response for sports injuries'. Requirements: Output two parts: Draft Body and Editable Checklist for next-round revision. Keep the text practical and executable. Use this exact disclaimer: For education only; not a medical diagnosis.
```

docx_preview_paragraphs:
- paragraph_count: `16`
- 早期响应：运动伤害处理指南
- 引言
为了提高员工健康意识和促进企业内部的体育文化氛围，特制定本《早期响应：运动伤害处理指南》。此指南旨在帮助员工在遭遇运动伤害时能够及时采取正确的应对措施，减少伤害带来的影响，并提供必要的医疗信息以确保员工的安全与健康。
- 1. 运动伤害概述
- 1.1 定义
运动伤害是指在进行体育活动或锻炼过程中所发生的身体损伤。这些伤害可能包括但不限于肌肉拉伤、关节扭伤、骨折等。
- 1.2 常见类型及症状
**肌肉拉伤**：常见于腿部和背部，表现为局部疼痛、肿胀。
**关节扭伤**：通常发生在脚踝或膝盖部位，伴有剧烈的疼痛和活动受限。
**骨折**：表现为明显的疼痛、肿胀以及功能障碍。

## Case C-049

- group: `legal_compliance`
- prompt_len: `301`
- duration_s: `334.65`
- status: `doc_status=完成`, `flow_status=完成`
- word_count: `1007`
- char_count: `1007`
- validation_passed: `False`
- validation_errors: `acceptance:missing_required_keywords; acceptance:missing_required_headings`
- docx_ok: `True`
- export_method: `local_text_fallback`
- docx_path: `.data/out/content_validation_20260223_184816/artifacts/C-049/C-049.docx`
- docx_size_bytes: `38271`
- docx_sha256: `ada8b709b4b7f2c3afaffb170a4ada7a9d56d42deeceb4c6ea5a5eb07430d9b5`
- text_snapshot: `.data\out\content_validation_20260223_184816\artifacts\C-049\C-049.md`

prompt:
```text
Write a Risk Notice Document for sales representative on topic 'Online terms update communication'. Requirements: Output two parts: Draft Body and Editable Checklist for next-round revision. Keep the text practical and executable. Use this exact disclaimer: General information only; not legal advice.
```

docx_preview_paragraphs:
- paragraph_count: `39`
- 在线条款更新沟通风险通知
- 一、引言
随着业务的发展与市场环境的变化，在线销售平台上的条款和条件需要定期进行更新。为了确保所有销售人员能够准确理解和有效执行这些更新，特此发布本风险通知，旨在提醒相关销售人员在在线条款更新后的沟通过程中注意潜在的风险点。
- 1.1 目的明确沟通策略与流程防范可能的误解或冲突确保所有相关人员均能及时获取并理解最新信息
- 二、风险识别及预防措施
- 2.1 内部沟通风险及其应对

## Result

- cases: `2`
- docx_export_ok: `2`
- docx_export_rate: `100.00%`
