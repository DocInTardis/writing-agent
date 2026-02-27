# ADR-2026-02-26: 架构治理门禁与解耦执行策略

## 状态
- Accepted

## 背景
- 项目进入大文件治理与架构解耦阶段后，存在两类持续回退风险：
  - 文件/函数规模在后续需求迭代中再次膨胀。
  - `web` 分层边界被新代码绕开，导致耦合回流到 `app_v2.py`。
- 需要“可自动执行、可在 CI/Preflight 阻断”的治理机制，而不是只靠人工 Code Review。

## 决策
- 引入并强制执行以下门禁：
  - 文件行数门禁：`scripts/guard_file_line_limits.py`
  - 函数复杂度门禁（函数行数/参数数/圈复杂度）：`scripts/guard_function_complexity.py`
  - 分层边界门禁：`scripts/guard_architecture_boundaries.py`
- 三类门禁均接入：
  - CI：`.github/workflows/ci.yml`
  - release preflight：`scripts/release_preflight.py`
  - preflight 产物归档：`.github/workflows/release-preflight.yml`
- 门禁策略文件固化在 `security/`：
  - `security/file_line_limits.json`
  - `security/function_complexity_limits.json`
  - `security/architecture_boundaries.json`

## 取舍
- 允许现有历史大函数以显式 override 方式短期保留，不影响主线发布。
- 所有 override 仅作为过渡机制，后续拆分应持续降低阈值并逐步移除。
- 分层门禁采用“禁止规则 + allowlist”模型，兼顾稳定性与可迁移性。

## 影响
- 新增跨层耦合和超限函数会在 CI/Preflight 阶段被阻断。
- 解耦工作从“阶段性治理”变成“持续治理”。
- 后续模块拆分（如 `graph_runner.py`、`app_v2.py`）有了可量化防回退基线。

## 后续动作
- 在每次大文件拆分后同步下调对应 override 上限。
- 逐步清理 `architecture_boundaries.json` 中的 allowlist。
- 将函数复杂度门禁从 `writing_agent/web` 扩展到 `writing_agent/v2` 与关键脚本域。
