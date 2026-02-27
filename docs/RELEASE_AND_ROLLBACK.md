# 发布与回滚流程

## 1. 版本策略

- 推荐使用 `MAJOR.MINOR.PATCH`
- `PATCH`：缺陷修复、无破坏性变更
- `MINOR`：向后兼容的新能力
- `MAJOR`：存在不兼容变更

## 2. 发布前检查清单

1. 后端测试通过：`pytest -q`
2. 引用核验专项通过：`pytest -q tests/test_citation_verify_and_delete.py`
3. 前端构建通过：`npm --prefix writing_agent/web/frontend_svelte run build`
4. Rust 相关通过：`cargo test --quiet`（`engine/`）
5. 压测门禁通过：`python scripts/citation_verify_load_probe.py ...`
6. 异常网络演练通过：`python scripts/citation_verify_alert_chaos.py`
7. 依赖安全审计通过：`python scripts/dependency_audit.py`
8. SBOM 生成通过：`python scripts/generate_sbom.py --out-dir .data/out/sbom --strict`
9. 关键文档更新（Runbook/README/变更记录）

建议统一执行：

```powershell
python scripts/release_preflight.py --quick
```

## 3. 发布步骤（建议）

1. 打版本标签并生成变更摘要。
2. 先灰度（小流量/内部环境）验证 30-60 分钟。
3. 观察以下指标：
   - `alerts.severity` 是否升高
   - `degraded_rate` 是否异常
   - p95/p99 是否回归
4. 灰度通过后全量发布。

自动化入口：

- 工作流：`.github/workflows/release-preflight.yml`
- 本地脚本：`scripts/release_preflight.py`
- 依赖安全工作流：`.github/workflows/dependency-security.yml`
- CI 会设置 `WA_PREFLIGHT_REQUIRE_PIP_AUDIT=1` 强制启用 Python 依赖漏洞审计。
- 依赖安全工作流失败可选推送到 webhook（`SECURITY_ALERT_WEBHOOK_URL`）并自动创建 issue。
- 依赖基线文件：`security/dependency_baseline.json`（用于回归比较，禁止风险回升）。

## 4. 兼容性注意点

以下文件属于运行态数据，升级时需保留：

- `.data/citation_verify_alerts_config.json`
- `.data/citation_verify_alert_events.json`
- `.data/citation_verify_metrics_trends.json`

如果升级涉及结构调整，必须提供迁移脚本或兼容读取逻辑。

## 5. 回滚触发条件

- 连续 5 分钟出现 `severity=critical`
- `success_rate` 低于 SLO 下限
- 新版本引入的接口错误率明显上升

## 6. 回滚步骤

1. 停止继续放量，恢复上一稳定版本。
2. 保留并导出当前 `.data/out` 压测报告与告警事件日志。
3. 校验关键接口：
   - `/api/metrics/citation_verify`
   - `/api/metrics/citation_verify/alerts/events`
4. 记录回滚原因与时间线，进入故障复盘。

## 7. 发布后验收

1. 观察至少 30 分钟，确认无新增 `critical` 告警。
2. 执行一次小规模压测并归档报告。
3. 更新变更记录，关闭发布任务。

## 8. Dependency Baseline Lifecycle

- Do not edit `security/dependency_baseline.json` by hand.
- Refresh baseline via:
  - `python scripts/update_dependency_baseline.py --reason "<change reason>"`
- If risk increase is temporarily accepted, use:
  - `python scripts/update_dependency_baseline.py --allow-regression --reason "<temporary accepted risk>"`
- Governance details:
  - `docs/DEPENDENCY_BASELINE_POLICY.md`

## 9. Release Governance

- Release governance check:
  - `python scripts/release_governance_check.py --strict`
- Release manifest generation:
  - `python scripts/generate_release_manifest.py`
- Policy source:
  - `security/release_policy.json`
- Reference doc:
  - `docs/RELEASE_ENGINEERING.md`

## 10. Release Channels

- Channel registry file:
  - `security/release_channels.json`
- Validate channels:
  - `python scripts/release_channel_control.py validate --strict`
- Promote canary to stable:
  - `python scripts/release_channel_control.py promote --source canary --target stable --reason "canary healthy" --actor release-bot`
- Emergency rollback:
  - `python scripts/release_channel_control.py rollback --channel stable --to-version <version> --reason "incident" --actor oncall`
- Rollback bundle:
  - `python scripts/create_rollback_bundle.py --label emergency --strict`
- Release manifest with gate evidence map:
  - `python scripts/generate_release_manifest.py --require-gate-evidence --release-candidate-id <rc_id>`
- Signed drill evidence:
  - `python scripts/sign_rollback_drill_evidence.py --require-key --strict`
- Rollback drill guard with signature:
  - `python scripts/rollback_drill_guard.py --strict --require-email-drill --require-history-rollback --require-signature --signing-key "<key>"`
- Rollout stage executor (dry-run):
  - `python scripts/release_rollout_executor.py --dry-run --strict`
- Rollout stage executor (apply one step):
  - `python scripts/release_rollout_executor.py --apply --strict --target-version <version>`
- Reference doc:
  - `docs/RELEASE_CHANNELS.md`

## 11. SLO Guard

- SLO policy file:
  - `security/slo_targets.json`
- Evaluate SLO using latest load probe report:
  - `python scripts/slo_guard.py`
- Quick mode (for quick preflight):
  - `python scripts/slo_guard.py --quick`
- SLO policy doc:
  - `docs/SLO_POLICY.md`

## 12. Release Compatibility Matrix

- Matrix config:
  - `security/release_compat_matrix.json`
- Run compatibility regression:
  - `python scripts/release_compat_matrix.py --strict`
- Minimum case coverage (enforced via matrix rules in strict mode):
  - N-1 -> N upgrade
  - N -> N upgrade (current schema baseline)
  - N -> N+1 upgrade
  - N+1 -> N rollback
  - At least one failure-mode fixture with `expect_readable=false`
- Failure-mode fixtures can include `expected_failed_checks` to guarantee deterministic assertions.
- Purpose:
  - Validate upgrade and rollback case fixtures against current release policy and state schema compatibility.

## 13. Correlation Traceability

- Correlation guard:
  - `python scripts/correlation_trace_guard.py --strict`
- Purpose:
  - Ensure `correlation_id` / `release_candidate_id` stay consistent across:
    - rollout execution reports
    - alert escalation reports
    - incident reports
- Rollout executor supports:
  - `--correlation-id <id>`
  - `--release-candidate-id <id>`

## 14. Traffic Adapter Contract

- Contract file:
  - `security/release_traffic_adapter_contract.json`
- Validate contract examples:
  - `python scripts/release_rollout_adapter_contract_check.py --strict`
- Validate runtime command template:
  - `python scripts/release_rollout_adapter_contract_check.py --strict --require-runtime-command --command-template "<template>"`
- Purpose:
  - Ensure rollout traffic command templates use only supported placeholders and include required routing fields.
