# Scripts Directory

该目录存放命令行脚本，分为两类：

- `scripts/*.py`：生产门禁、发布治理、运维检查脚本（可进入 CI）
- `scripts/dev/*.py`：开发调试脚本（默认不作为正式发布门禁）

## 常用脚本

- `release_preflight.py`：发布前综合检查
- `guard_file_line_limits.py`：文件行数门禁
- `guard_function_complexity.py`：函数复杂度门禁
- `guard_architecture_boundaries.py`：分层边界门禁
- `golden_export_regression.py`：导出链路回归
- `node_gateway_rollout_monitor.py`：Node AI Gateway 灰度指标汇总
