# 选中文本改写功能优化策略（2026-03-01）

## 1. 背景与问题定义

当前“选中文本改写”链路存在核心风险：当用户只选中 1-2 句甚至更短片段时，模型仅看局部文本会缺少语义与篇章上下文，导致：

1. 改写偏题或语义漂移。
2. 误改未选中区域（off-target edits）。
3. 结构标记被破坏（如 `[[TABLE]]`、`[[FIGURE]]`）。
4. 结果不可解释、不可稳定重放。

目标不是“让模型写得更花”，而是把任务从自由生成改为受控编辑，提升可控性、可验证性、可回滚性。

## 2. 设计目标与非目标

### 2.1 设计目标

1. 上下文充分：短选区也能携带必要上下文。
2. 作用域严格：只允许修改选中范围或显式允许的扩展范围。
3. 输出可执行：模型返回结构化操作，而非自由文本。
4. 执行原子：要么整次编辑成功，要么整次回滚。
5. 质量可度量：有明确指标与回归测试。

### 2.2 非目标

1. 不把该功能升级为“全文重写器”。
2. 不在第一阶段引入复杂训练或新模型微调。
3. 不破坏既有双引擎/断点恢复架构。

## 3. 总体策略（六层防线）

### 3.1 输入分区（Prompt Delimiters / XML Tags）

将请求拆为明确区块，避免指令与数据混淆：

1. `<task>`：本次编辑任务与风格目标。
2. `<constraints>`：不可修改范围、结构保留要求。
3. `<left_context>`：选区左侧上下文。
4. `<selected_text>`：用户选中文本。
5. `<right_context>`：选区右侧上下文。

收益：降低误解率，减少模型把参考文本当“可改区域”。

### 3.2 短选区自动扩展（Context Expansion Policy）

当选区过短时自动扩展到更稳定的语义边界：

1. 若字符数 `< 30` 或 token 数 `< 8`，扩展到句子边界。
2. 若仍不足语义最小单元，再扩展到段落边界。
3. 记录 `original_selection` 与 `effective_selection`，供回放与审计。

收益：减少“只改一句但忽略上下文”的语义错配。

### 3.3 动态窗口策略（Dynamic Context Window Policy）

固定 `400/400` 只适合中等长度选区，不适合短选区和长选区。改为动态计算：

1. 先算有效选区长度 `L = len(effective_selection_chars)`。
2. 每侧候选窗口使用线性公式：
`window_side_candidate = 220 + 0.8 * L + short_boost`
3. 其中 `short_boost = 180` 当 `L < 60`，否则 `short_boost = 0`。
4. 对每侧窗口做边界裁剪：`window_side = clamp(window_side_candidate, 240, 1200)`。
5. 默认左右对称；若任务是“承接上文/续写语气”，可左侧加权（如 `left:right = 6:4`）。
6. 记录 `window_policy_version = dynamic_v1` 和最终 `left_window/right_window`。

该策略的直觉：

1. 选区越短，窗口相对更大，优先补语义。
2. 选区越长，窗口增幅放缓，避免无意义扩张。
3. 有明确上限，控制成本与延迟。

### 3.4 Token 预算裁剪（Budget-Aware Trimming）

动态窗口算完后，仍需受模型上下文预算约束：

1. 设 `prompt_budget_tokens`，建议不超过模型上下文上限的 25%-30%。
2. 组包后做一次 tokenizer 估算。
3. 若超预算，按比例缩减左右窗口，保证最小每侧窗口（如 `>=120 chars`）。
4. 若仍超预算，优先保留 `selected_text` 与最近邻句，舍弃远端上下文。

收益：保证可用性与稳定延迟，不因极端输入导致超长上下文失败。

### 3.5 Schema 约束输出（Structured Outputs, strict）

模型必须输出结构化编辑计划，禁止直接返回自由改写正文。建议输出：

1. `ops`：编辑操作序列（如 `test`、`replace`）。
2. `meta`：计划摘要与风险级别。
3. `checks`：结构标记保留断言。

收益：从“看起来合理”转为“程序可验证可执行”。

### 3.6 原子应用与二阶段兜底

执行前先断言、再应用，并保留一次受控兜底：

1. `test`：校验锚点/哈希/原文片段是否仍一致。
2. `replace`：仅在断言通过时执行。
3. 任一操作失败则整次回滚，返回错误码。
4. 主路径失败时触发一次 Self-Refine（附带失败原因）。
5. 二阶段仍失败则终止，不做无限重试。

收益：避免并发编辑导致的半成功脏写，并在可控范围内提升成功率。

## 4. 请求与响应协议草案

### 4.1 请求体（建议）

```json
{
  "doc_id": "string",
  "revision_id": "string",
  "task": "rewrite_selected_text",
  "instruction": "string",
  "selection": {
    "start": 120,
    "end": 186,
    "text": "原始选中文本"
  },
  "context_policy": {
    "version": "dynamic_v1",
    "short_selection_threshold_chars": 30,
    "short_selection_threshold_tokens": 8,
    "window_formula": "220 + 0.8 * L + short_boost",
    "window_min_chars": 240,
    "window_max_chars": 1200,
    "prompt_budget_ratio": 0.3
  },
  "constraints": {
    "immutable_outside_selection": true,
    "preserve_markers": ["[[TABLE]]", "[[FIGURE]]"],
    "max_change_ratio": 0.35
  }
}
```

### 4.2 响应体（建议，strict schema）

```json
{
  "ops": [
    {
      "op": "test",
      "path": "/content",
      "expected_hash": "sha256:..."
    },
    {
      "op": "replace",
      "path": "/content",
      "range": {"start": 120, "end": 186},
      "value": "改写后的文本"
    }
  ],
  "meta": {
    "risk_level": "low",
    "notes": "仅改写选区，不改其他区域",
    "window_policy_version": "dynamic_v1",
    "window_chars": {"left": 420, "right": 420},
    "selection": {
      "original": {"start": 120, "end": 186},
      "effective": {"start": 96, "end": 210}
    }
  },
  "checks": {
    "preserve_markers": true
  }
}
```

## 5. 执行流水线

1. 接收请求并标准化选区。
2. 根据阈值执行短选区扩展，得到 `effective_selection`。
3. 按 `dynamic_v1` 计算左右窗口。
4. 按 token 预算裁剪窗口并组包标签化 prompt。
5. 调用模型并按 strict schema 解析。
6. 先跑 `test` 断言，再执行 `replace`。
7. 运行质量门禁（off-target、结构标记、变更比例）。
8. 失败则触发一次 Self-Refine；仍失败则返回明确错误码。

## 6. 质量门禁与错误码

### 6.1 质量门禁（建议最小集）

1. `off_target_delta == 0`：非目标区域不允许变化。
2. `marker_integrity == pass`：关键标记必须完整保留。
3. `change_ratio <= max_change_ratio`：防止过度改写。
4. `semantic_intent_match == pass`：与用户指令一致。

### 6.2 错误码（建议）

1. `E_SELECTION_TOO_SHORT`：选区不足且扩展失败。
2. `E_SCHEMA_INVALID`：模型输出不符合 schema。
3. `E_ANCHOR_MISMATCH`：`test` 断言失败。
4. `E_OFFTARGET_EDIT`：检测到越界修改。
5. `E_MARKER_BROKEN`：结构标记损坏。
6. `E_BUDGET_EXCEEDED`：最小窗口仍超预算。
7. `E_REFINE_FAILED`：二阶段兜底失败。

## 7. 指标与回归测试

### 7.1 线上指标

1. `parse_valid_rate`
2. `atomic_apply_success_rate`
3. `off_target_violation_rate`
4. `marker_break_rate`
5. `fallback_trigger_rate`
6. `fallback_recovery_rate`
7. `window_trim_rate`（动态窗口触发预算裁剪的比例）
8. `window_coverage_score`（选区前后语境覆盖质量）
9. `p95_latency_ms`

### 7.2 回归用例（最小集合）

1. 极短选区（1 句）改写成功且无越界修改。
2. 并发更新导致锚点变化，`test` 失败并整次回滚。
3. 包含 `[[TABLE]]` 的段落改写后标记完整。
4. 模型返回非 schema 文本，正确进入错误处理。
5. 动态窗口超预算后按比例裁剪，仍可稳定生成。
6. 主路径失败后二阶段兜底成功。

## 8. 动态参数调优建议

上线后通过 A/B 与离线集联动调参，避免拍脑袋改参数：

1. 如果 `semantic_intent_match` 低而 `off_target` 正常，优先增大 `window_min_chars` 或 `short_boost`。
2. 如果 `p95_latency_ms` 高且 `window_trim_rate` 高，优先下调 `window_max_chars` 或 `prompt_budget_ratio`。
3. 如果长选区经常跑偏，降低线性系数 `0.8`，减缓窗口随 `L` 的增长。
4. 参数变更必须带 `window_policy_version` 升级，保证回放可追溯。

## 9. 落地改造路径（对应本仓库）

建议按三阶段推进，减少一次性改动风险：

1. Phase A（协议层）：新增 `context_policy`、schema 与错误码定义。
2. Phase B（执行层）：加入“短选区扩展 + 动态窗口 + 预算裁剪 + 原子 patch”流程。
3. Phase C（质量层）：补充回归测试、指标埋点和看板。

重点改造位点（以当前代码结构为准）：

1. `writing_agent/web/app_v2_generate_stream_runtime.py`
2. `writing_agent/web/domains/revision_edit_runtime_domain.py`
3. `writing_agent/web/block_edit.py`

## 10. 面试表达模板（30 秒版）

“我们把选中改写从自由生成改造成受控编辑：先做短选区扩展，再按选区长度动态计算左右上下文窗口并受 token 预算约束；输出端强制 strict schema；执行端采用 `test + replace` 原子应用；失败再走一次带反馈的 refine 兜底。这样可以把越界修改、结构破坏和并发脏写风险收敛到可监控、可回滚的范围内。”

## 11. 参考依据

1. OpenAI Reasoning Best Practices
2. Anthropic Prompting Best Practices（XML tags）
3. OpenAI Structured Outputs（strict mode）
4. RFC 5789（HTTP PATCH Atomicity）
5. RFC 6902（JSON Patch + test operation）
6. LaserTagger / Levenshtein Transformer（编辑范式）
7. EditEval / XATU（编辑任务评测）
8. Self-Refine（二阶段反馈修正）

## 12. 实施状态（2026-03-02）

本策略已完成首轮工程落地，状态如下：

1. 已完成：`selection` 对象协议（`start/end/text`）与兼容旧字符串选区。
2. 已完成：`context_policy(dynamic_v1)` 透传与后端动态窗口计算。
3. 已完成：短选区句/段扩展、token 预算裁剪、上下文标签化输入。
4. 已完成：结构化编辑输出解析（`ops.replace`）与一次 refine 兜底。
5. 已完成：原子应用检查（锚点一致性 + off-target 检查 + 标记完整性检查）。
6. 已完成：错误码对外暴露（`revision_meta` / `revision_status`）与回退可观测。
7. 已完成：指标落盘（`selected_revision_events.jsonl`），覆盖触发、恢复、失败路径。
8. 已完成：回归测试（单元 + 接口）并通过。

## 13. Frontend rollout status (2026-03-02)

1. Svelte workbench now sends `context_policy` by default on `/generate` and `/generate/stream` requests.
2. Svelte workbench now sends optional `selection` payload from current block selection (`start/end/text` when uniquely anchored, otherwise `text`).
3. Svelte stream consumer now handles `revision_status` SSE events and records diagnostic thoughts for fallback visibility.
4. Svelte stream + non-stream final handlers now consume `revision_meta` and surface revision diagnostics.
5. Legacy runtime (`v2_legacy_runtime.js`) now sends textarea selection as `selection` and includes `context_policy` defaults.
6. Legacy runtime now handles `revision_status` events and `revision_meta` in final payload for runtime diagnostics.

## 14. Constraint hardening sweep (2026-03-02)

1. `/api/doc/{doc_id}/revise` selected-revision path no longer uses unconstrained string replacement fallback by default.
2. `revise` now reuses constrained revision runtime (`selection` + `context_policy` + `revision_meta`) and only falls back to full-document rewrite when `allow_unscoped_fallback=true`.
3. `inline-ai` and `inline-ai/stream` now apply dynamic context-window trimming on `before_text/after_text` with policy metadata.
4. `InlineAIEngine` now uses a guarded chat proxy for edit-like operations:
5. Tagged context blocks (`<left_context>/<selected_text>/<right_context>`) and strict JSON output requirement.
6. Output sanitization and oversized rewrite guard for strict rewrite operations.
7. `ask_ai` / `explain` are now also covered by guarded prompt + strict JSON extraction (same tagged-context contract), avoiding unconstrained free-form prompt path.
8. Added regression tests for stream `context_meta` first-event contract and non-stream parameter passthrough (`question` / `target_language`) to prevent silent behavior drift.

## 15. OSS benchmark gap-closure (2026-03-02)

Compared against common patterns from well-known OSS projects (Aider, Continue, LangGraph, OpenHands), two additional gaps were found and fixed:

1. Prompt boundary hardening gap:
   Before: inline context (`left/selected/right/instruction`) was inserted directly into XML-like tags.
   Risk: if user content contains tag-like text such as `</selected_text>`, boundaries can be confused and instruction injection risk increases.
   Fix: apply XML escaping (`&`, `<`, `>`) before filling tagged blocks in guarded prompt.
2. Strict-JSON enforcement gap:
   Before: when model output was not valid JSON, parser could still fall through and accept free-form text.
   Risk: weakens contract reliability and can re-introduce unconstrained outputs.
   Fix: add one retry with explicit `retry_reason` for JSON repair; for strict rewrite operations, if still invalid then fallback to original selected span.
3. Context-meta consistency gap:
   Before: API layer trimmed context with `context_policy`, but engine could trim again internally.
   Risk: reported `context_meta` might not match actual prompt context sent to model.
   Fix: add `InlineContext.pretrimmed` flag; API now sets `pretrimmed=True` so engine skips second trimming.

Regression coverage added:

1. Guarded prompt escapes tag-like content correctly.
2. Invalid JSON triggers exactly one retry and recovers when second output is valid.
3. `pretrimmed=True` preserves caller-trimmed context (no second trim).

## 16. Legacy `/studio` flow hardening (2026-03-02)

Legacy editing flow had unconstrained free-text model outputs in both non-stream and stream paths. This round adds protocol-level constraints:

1. `DocumentEditAgent` now uses strict JSON output contract:
   JSON schema includes `html` + `assistant` (+ optional meta), with tagged input blocks (`instruction`, `selection_text`, `document_html`).
2. `DocumentEditAgent` now retries once on invalid JSON:
   if still invalid and request is selection-scoped, fail-closed (keep original document unchanged) instead of applying unconstrained output.
3. `studio_chat_stream` section worker now requires structured JSON:
   worker response is parsed from `section_html` (with fallback keys) before normalization.
4. `studio_chat_stream` aggregator now requires structured JSON:
   aggregator response is parsed from `html` (with fallback keys) before sanitization and policy enforcement.

New regression tests:

1. `tests/unit/test_document_edit_agent_constraints.py`:
   prompt protocol, structured parsing success path, and selection fail-closed path.
2. `tests/test_studio_stream_constraints.py`:
   verifies stream flow consumes structured worker/aggregator outputs and lands final HTML.

## 17. Analysis-Chain hardening for dynamic questions (2026-03-02)

Scope: `_generate_dynamic_questions_with_model` in `writing_agent/web/app_v2_textops_runtime_part1.py`.
This is the clarification-question analysis chain (not the final rewrite chain).

1. Tagged input segmentation:
- Build prompt with explicit channels: `<task>`, `<constraints>`, `<history>`, `<raw_input>`, `<analysis_payload>`.
- Escape user/history/payload text (`&`, `<`, `>`) before interpolation.
- Goal: reduce boundary confusion and prompt-injection-by-tag-content risk.

2. Strict JSON schema contract:
- System prompt requires strict JSON only (no markdown).
- Required shape:
  - `summary: string`
  - `questions: string[]` (max 3 expected)
  - `confidence: {title,purpose,length,format,scope,voice}` with values in `[0,1]`.

3. One-shot repair retry:
- First parse attempt: extract JSON block and decode.
- If invalid: one retry with explicit `<retry_reason>` that previous output was invalid JSON.
- Retry temperature is lower to bias deterministic structured output.
- If still invalid: fail closed to `{}`.

4. Output normalization before downstream use:
- `summary` trimmed to max 600 chars.
- `questions`:
  - accept `string` and object forms (`question/text/q`),
  - trim each question to 200 chars,
  - deduplicate,
  - cap to 3.
- `confidence`:
  - coerce each field to float,
  - clamp to `[0,1]`,
  - use default `0.5` when missing/invalid.

5. Rationale:
- Tagged segmentation improves instruction/data separation.
- Strict schema + retry improves structured reliability.
- Normalization prevents malformed or oversized outputs from polluting template-flow follow-up logic.
