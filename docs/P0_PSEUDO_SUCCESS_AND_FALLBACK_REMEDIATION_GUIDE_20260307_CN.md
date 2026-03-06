# P0 伪成功与降级链路整改执行指南（2026-03-07）

## 1. 文档目标

本文档用于把当前 13 条问题收敛为少数共因，并给出可执行的改造方案。

本文档聚焦三件事：
1. 为什么会反复出现“看起来成功、实际失败”。
2. 先改哪些点可以立即止血。
3. 每个改造点具体怎么做、改哪里、如何验收。

## 2. 一句话结论

当前不是 13 个独立问题，而是 4 类共因叠加：
1. 默认策略错位：论文任务被周报模板和英文兜底污染。
2. 失败策略失衡：前段过严（直接中断），后段过松（无约束回退重写）。
3. 质量门禁不硬：空字段、错结构、硬约束未满足仍可“继续成功”。
4. 观测链路不全：关键阶段事件缺失，降级路径丢上下文。

## 3. 问题与共因映射

| 问题编号 | 现象摘要 | 对应共因 |
|---|---|---|
| 1 | 主题偏移到周报模板 | 默认策略错位 |
| 2 | 中英混写与英语模板句 | 默认策略错位 |
| 3 | 内容重复、增量低 | 默认策略错位 + 质量门禁不硬 |
| 4 | revise 回退后分数下降 | 失败策略失衡 |
| 5 | revise 不执行硬约束 | 失败策略失衡 + 质量门禁不硬 |
| 6 | planner section 集合错误 | 默认策略错位 + 质量门禁不硬 |
| 7 | struct_plan 细化字段为空 | 质量门禁不硬 |
| 8 | analysis 事件缺失 | 观测链路不全 |
| 9 | Ollama timeout 触发降级 | 失败策略失衡 + 观测链路不全 |
| 10 | `_ollama_installed_models` NameError | 工程健壮性不足 |
| 11 | strict-json 空章节直接中断 | 失败策略失衡 |
| 12 | fallback 丢 planner/targets | 观测链路不全 |
| 13 | 终端中文乱码 | 运行环境编码配置问题 |

## 4. 先止血（P0）与后重构（P1/P2）

### 4.1 P0（必须先做，目标是消灭伪成功）

1. 禁止论文任务进入“周报默认章结构”。
2. 禁止 revise 在默认情况下做无约束全篇回退重写。
3. 对 revise 回退结果增加硬性验收，不达标不写回。
4. 补发 `analysis` 结构化事件，保证阶段追踪完整。
5. strict-json 从“直接中断”改为“先恢复再失败”。

### 4.2 P1（结构优化，目标是提升稳定性与可维护性）

1. planner 细化字段最小内容约束（key_points/figures/tables/evidence_queries）。
2. fallback 路径补齐规划事件上下文。
3. 超时策略分层（单阶段、单节、全局）和可解释失败码。

### 4.3 P2（体验优化）

1. 控制台统一 UTF-8 显示策略。
2. Trace 报告模板增加“降级路径提示”和“恢复来源”。

## 5. 详细实施步骤（按顺序执行）

## Step 1：切断周报模板污染（P0）

目标：论文任务不再出现 `This Week Work / Next Week Plan / Support Needed` 结构。

修改文件：
- `writing_agent/v2/prompts.py`
- `writing_agent/v2/graph_runner.py`
- `writing_agent/v2/graph_runner_runtime.py`
- `scripts/run_cnki_trace_workflow.py`

实施动作：
1. 将 `PLANNER_FEW_SHOT` 从“Project Weekly Report”替换为“中文学术论文”示例。
2. `_default_outline_from_instruction` 仅在明确周报意图时返回周报结构；论文意图必须返回空并交给学术 outline 逻辑。
3. `WRITING_AGENT_FAST_PLAN` 分支中，论文任务禁止使用周报 fallback sections。
4. 在 benchmark 脚本中显式设置 `WRITING_AGENT_FAST_PLAN=0`。

验收标准：
1. `stage_summary.struct_plan.sections` 中不得出现周报模板标题。
2. 连续 5 次 CNKI trace 中，planner section 集合均为学术章节。

失败回滚：
1. 若线上出现生成空白，可临时恢复 fast-plan，但必须附带“interrupted + failure_reason”，不能标 success。

## Step 2：修复 revise 回退重写的本质问题（P0）

目标：不再出现“修订后质量下降且仍写回”的伪成功。

修改文件：
- `scripts/run_cnki_trace_workflow.py`
- `writing_agent/web/services/generation_service.py`
- `writing_agent/web/app_v2_textops_runtime_part2.py`

本质原因：
1. 脚本主动传入 `allow_unscoped_fallback=True`，允许局部修订失败后走全篇重写。
2. 回退重写后缺乏硬性质量门禁，结果“非空即可写回”。
3. 指令硬约束执行默认关闭，无法强制补齐章节/字数/参考/图表。

实施动作：
1. benchmark 默认改为 `allow_unscoped_fallback=False`。
2. 在 `revise_doc` 中引入 `validate_revision_candidate()`：
   - 输入：候选文本、原文、硬约束配置。
   - 输出：`passed`、`reasons`、`score_delta`。
3. 仅当 `passed=true` 才允许写回；否则返回 `applied=false` 并保留原文。
4. benchmark 环境开启 `WRITING_AGENT_ENFORCE_INSTRUCTION_REQUIREMENTS=1`。
5. revise fallback prompt 增加“硬约束摘要块”，禁止模型忽略关键指标。

建议判定门槛（先保守）：
1. `chars >= min_chars`
2. `required_h2_coverage >= 100%`
3. `refs_count >= min_refs`
4. `table_markers >= min_tables`
5. `figure_markers >= min_figures`
6. `quality_score_after >= quality_score_before - epsilon`

验收标准：
1. revise 后质量分数不再出现明显回退。
2. 不达标 revise 结果不写回且有结构化拒绝原因。

## Step 3：收紧 planner 输出质量门禁（P0/P1）

目标：`struct_plan` 不再出现“标题有了，细化全空”的伪规划。

修改文件：
- `writing_agent/v2/graph_reference_domain.py`
- `writing_agent/v2/graph_runner_runtime.py`

实施动作：
1. `default_plan_map()` 不再默认全空列表，至少填充每节最小 `key_points`。
2. 在 `PLAN_DETAIL` 后增加 `validate_plan_detail()`：
   - 若 `key_points` 全空，触发一次重试。
   - 二次仍失败，进入 fail-fast，不得当作成功计划。
3. 对学术任务设置最小字段要求：
   - `key_points` 每节至少 2 条。
   - 全文至少 2 个 `evidence_queries`。
   - 方法/实验类章节至少提供 `tables` 或 `figures` 计划之一。

验收标准：
1. `struct_plan` 中不再出现普遍空字段。
2. planner 失败会明确报错，不会进入后续伪成功链路。

## Step 4：补齐 analysis 与阶段可观测性（P0）

目标：每个阶段都有结构化事件，便于定位问题起点。

修改文件：
- `writing_agent/v2/graph_runner_runtime.py`
- `scripts/run_cnki_trace_workflow.py`
- `writing_agent/web/app_v2_generate_stream_runtime.py`

实施动作：
1. 在 `run_generate_graph` 中新增：
   - `yield {"event":"analysis", ...}`
2. 保留现有 delta 文本，但不得替代结构化 analysis 事件。
3. fallback/single-pass 路径增加 `trace_context`：
   - `route_path`
   - `fallback_trigger`
   - `fallback_recovered`
4. benchmark 报告中增加“是否走 fallback 路径”显式字段。

验收标准：
1. `stage_summary.analysis` 非空。
2. 任一 run 均可从事件流还原“何时降级、为何降级、是否恢复”。

## Step 5：strict-json 改为恢复优先（P0）

目标：空章节优先修复，不再直接崩断全流程。

修改文件：
- `writing_agent/v2/graph_runner_runtime.py`

实施动作：
1. 当前 `strict_json` 空章节直接 `raise ValueError` 的逻辑改为：
   - 第一轮：按缺失章节做定向补写。
   - 第二轮：仍缺失则用高约束最小文本兜底。
   - 第三轮：仍失败才 `failed/interrupted`，附详细缺失清单。
2. 失败时必须返回结构化失败，不允许 silent fail。

验收标准：
1. 空章节场景不再直接中断。
2. 若最终失败，failure_reason 可直接定位缺失章节。

## Step 6：超时与稳定性治理（P1）

目标：减少 timeout 引发的质量降级和链路抖动。

修改文件：
- `writing_agent/web/app_v2_generate_stream_runtime.py`
- `writing_agent/v2/graph_runner_runtime.py`
- `writing_agent/v2/graph_runner_post_domain.py`

实施动作：
1. 明确三层超时：单事件、单章节、全流程。
2. 超时后先重试关键阶段，再 fallback；每次都记录原因码。
3. `_ollama_installed_models` 调用统一走安全封装，杜绝 NameError 类问题重现。
4. 健康检查失败时直接 fail-fast，避免错误结果继续流入下游。

验收标准：
1. timeout 发生时有明确 reason code 与阶段定位。
2. 不再出现未捕获 NameError 导致整链路崩溃。

## Step 7：控制台中文乱码治理（P2）

目标：排查时终端可直接读取中文，不影响诊断效率。

环境动作：
1. 终端设置 UTF-8 代码页：`chcp 65001`
2. PowerShell 会话设置：
   - `[Console]::InputEncoding = [System.Text.Encoding]::UTF8`
   - `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`
3. 读取文件时显式 UTF-8：`Get-Content -Encoding utf8`

说明：
1. 这是显示层问题，不是文件损坏问题。
2. 文件本体继续统一 UTF-8 保存。

## 6. 代码级改造清单（可直接开工）

| 序号 | 文件 | 改造点 | 优先级 |
|---|---|---|---|
| 1 | `writing_agent/v2/prompts.py` | 替换周报 few-shot 为学术 few-shot | P0 |
| 2 | `writing_agent/v2/graph_runner.py` | 限制周报 heuristic 触发条件 | P0 |
| 3 | `writing_agent/v2/graph_runner_runtime.py` | 禁止论文 fast-plan 周报 fallback；新增 analysis 事件；strict-json 恢复链路 | P0 |
| 4 | `writing_agent/web/services/generation_service.py` | revise fallback 前后增加硬门禁校验与拒绝回写 | P0 |
| 5 | `scripts/run_cnki_trace_workflow.py` | 关闭 `allow_unscoped_fallback`；强制开启硬约束执行 | P0 |
| 6 | `writing_agent/v2/graph_reference_domain.py` | default plan map 最小细化填充与校验 | P1 |
| 7 | `writing_agent/web/app_v2_generate_stream_runtime.py` | fallback 事件上下文补齐 | P1 |
| 8 | `writing_agent/v2/graph_runner_post_domain.py` | `_ollama_installed_models` 安全调用封装 | P1 |

## 7. 测试与验收计划

## 7.1 单元测试新增建议

建议新增测试文件：
1. `tests/unit/test_planner_academic_outline_guard.py`
2. `tests/unit/test_revise_fallback_hard_gate.py`
3. `tests/unit/test_graph_analysis_event_emission.py`
4. `tests/unit/test_strict_json_recovery.py`
5. `tests/unit/test_fallback_trace_context.py`

关键断言：
1. 学术任务不得生成周报章节。
2. revise 候选不达标时不得写回。
3. 事件流必须包含 `analysis`。
4. strict-json 空章节先恢复后失败。
5. fallback 路径必须记录 route/fallback 元数据。

## 7.2 集成回归（CNKI trace）

执行方式：
1. 连续跑 5 次 `scripts/run_cnki_trace_workflow.py`。
2. 每次保存 `raw_events.jsonl`、`stage_summary.json`、`quality_rounds.json`。
3. 对比失败率、回退率、质量分和结构完整率。

通过门槛：
1. 周报章节出现率 = 0。
2. `stage_summary.analysis` 非空率 = 100%。
3. revise 回退后质量下降率 <= 5%。
4. 硬约束达标率 >= 95%。

## 8. 发布策略

分三步发布：
1. 第一步：P0 改造灰度到 benchmark 专用环境。
2. 第二步：通过 5 轮回归后扩展到日常生成流。
3. 第三步：开启 P1 稳定性与可观测性增强。

回滚条件：
1. 连续 2 次出现结构性失败且无法恢复。
2. 质量分位显著下降。
3. 关键接口 5xx 超阈值。

回滚动作：
1. 回退 prompt registry 到上一稳定版本。
2. 暂时关闭新 recovery 逻辑并保留 fail-fast。
3. 保留事件增强逻辑，确保仍可诊断。

## 9. 你最关心的 3 个问题（白话版）

1. 是不是共因导致的？
是。核心是“错误默认 + 松门禁 + 弱观测”，不是 13 个独立偶发点。

2. “小模板集合”要不要删？
不要直接全删。应改为“仅紧急保底可用”，不能进入正常学术链路。

3. revise 回退重写的本质是什么？
不是模型突然变差，而是流程允许“局部失败后无约束全篇重写”，且回写门槛过低。

---

执行建议：按 Step 1 到 Step 5 先做 P0，完成后再做 P1/P2；不要并行大改，避免定位困难。
