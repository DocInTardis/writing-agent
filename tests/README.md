# Test Layout

## Layering

- `tests/unit/`：纯函数/模块级测试
- `tests/integration/`：服务集成测试
- `tests/e2e/`：端到端占位或真实场景测试
- `tests/export/`：导出专项测试
- `tests/ui/`：前端与工作台流程测试

## Fixtures

- `tests/fixtures/`：统一测试数据

## Legacy

- `tests/legacy/`：历史脚本化测试，默认不参与 `pytest -q tests`
