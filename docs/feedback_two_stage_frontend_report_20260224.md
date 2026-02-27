# 评分与两阶段前端测试执行报告（2026-02-24）

## 1. 目标与范围
本轮工作的目标是完成以下闭环：
- 在前端增加“满意度评分”入口，用户可选择 1-5 分并提交备注。
- 在后端持久化评分数据，并把低满意度样本（默认 <=2 分）沉淀到学习池。
- 通过前端页面（Playwright）执行“两阶段测试”：
  - 阶段1：按复杂 Prompt 生成文档、导出 DOCX、评分。
  - 阶段2：基于阶段1失败项自动构建修订 Prompt，再生成、导出 DOCX、评分。
- 生成详细测试记录文档，明确输入、输出、评分、存储路径。

## 2. 代码与数据改动
### 2.1 后端能力
- 文件：`writing_agent/web/app_v2.py:1128`
- 改动：`doc_meta` 表新增 `feedback_json` 字段，支持评分日志持久化。
- 文件：`writing_agent/web/app_v2.py:890`
- 改动：新增低满意度样本池文件路径 `.data/learning/low_satisfaction_feedback.jsonl`。
- 文件：`writing_agent/web/app_v2.py:1503`
- 改动：新增 `GET /api/doc/{doc_id}/feedback`。
- 文件：`writing_agent/web/app_v2.py:1512`
- 改动：新增 `POST /api/doc/{doc_id}/feedback`，支持单条/批量评分入库，低分自动写入学习池。
- 文件：`writing_agent/web/app_v2.py:1559`
- 改动：新增 `GET /api/feedback/low`，用于查看低满意度样本。

### 2.2 前端能力
- 文件：`writing_agent/web/frontend_svelte/src/App.svelte:3010`
- 改动：新增评分面板开关按钮 `data-testid="feedback-toggle"`。
- 文件：`writing_agent/web/frontend_svelte/src/App.svelte:1853`
- 改动：新增 `submitSatisfaction()`，提交评分到后端。
- 文件：`writing_agent/web/frontend_svelte/src/App.svelte:1834`
- 改动：新增 `loadFeedback()`，加载历史评分。
- 文件：`writing_agent/web/frontend_svelte/src/App.svelte:3152`
- 改动：新增阶段选择 `data-testid="feedback-stage"`（general/stage1/stage2/final）。
- 文件：`writing_agent/web/frontend_svelte/src/App.svelte:3172`
- 改动：新增评分提交按钮 `data-testid="feedback-submit"` 与最近评分展示。

### 2.3 自动化测试脚本
- 文件：`scripts/ui_two_stage_feedback_validation.py:101`
- 改动：阶段2 Prompt 自动构建逻辑（按阶段1失败项定向修订）。
- 文件：`scripts/ui_two_stage_feedback_validation.py:241`
- 改动：评分提交改为“提交后核验入库”，并记录 `persisted/note_matched`。
- 文件：`scripts/ui_two_stage_feedback_validation.py:494`
- 改动：输出中文可读测试报告（Markdown）。
- 文件：`scripts/ui_two_stage_feedback_validation.py:539`
- 改动：输出同内容 DOCX 报告。
- 文件：`scripts/ui_two_stage_feedback_validation.py:60`
- 改动：数据集读取兼容 UTF-8 BOM（`utf-8-sig`）。

### 2.4 测试数据集
- 文件：`tests/fixtures/content_validation/two_stage_complex_cases_4.json`
- 改动：修复乱码并重建为可读复杂场景（含字体字号要求、结构要求、关键词约束）。
- 文件：`tests/fixtures/content_validation/two_stage_complex_case_smoke_1.json`
- 改动：可快速回归的单用例 smoke 数据。
- 文件：`tests/fixtures/content_validation/two_stage_complex_cases_2_real.json`
- 改动：真实模型两题材验证数据（企业治理 + 金融科普）。

## 3. 已执行验证
### 3.1 单元/回归测试
执行命令：
```bash
python -m pytest -q tests/test_feedback_pipeline.py tests/test_generation_lock.py tests/test_complex_prompt_requirement_enforcer.py
```
结果：
- 9 passed in 1.78s

覆盖点：
- 评分 API 入库与回读。
- 低满意度写入学习池。
- 非法评分拒绝。
- 生成锁与复杂约束相关回归不回退。

### 3.2 前端 smoke（降级模式）
执行命令：
```bash
python -u scripts/ui_two_stage_feedback_validation.py --dataset tests/fixtures/content_validation/two_stage_complex_case_smoke_1.json --start-server --disable-ollama --timeout-s 90
```
运行目录：
- `.data/out/two_stage_validation_20260224_045435`

用途：
- 快速验证“前端生成流程 + 评分 + 导出 + 报告导出”的链路稳定性。

### 3.3 前端真实模型多题材两阶段测试（最终主结果）
执行命令：
```bash
python -u scripts/ui_two_stage_feedback_validation.py --dataset tests/fixtures/content_validation/two_stage_complex_cases_2_real.json --start-server --timeout-s 180
```
运行目录：
- `.data/out/two_stage_validation_20260224_045821`

摘要结果：
- 用例数：2
- Stage1 通过：1
- Stage2 通过：1
- Stage1 评分入库确认：2/2
- Stage2 评分入库确认：2/2

## 4. 最终主结果明细（two_stage_validation_20260224_045821）
### 4.1 TS-001 企业AI治理90天落地方案
- 文档ID：`91578a6553214b5a9a217b93488fe144`
- 阶段1：
  - 评分：4/5
  - 验收：未通过（缺少关键词）
  - 字符数：991
  - 快照：`.data/out/two_stage_validation_20260224_045821/artifacts/TS-001/TS-001_stage1.md`
  - DOCX：`.data/out/two_stage_validation_20260224_045821/artifacts/TS-001/TS-001_stage1.docx`
- 阶段2：
  - 评分：2/5
  - 验收：未通过（长度不足 + 缺关键词 + 缺标题）
  - 字符数：394
  - 快照：`.data/out/two_stage_validation_20260224_045821/artifacts/TS-001/TS-001_stage2.md`
  - DOCX：`.data/out/two_stage_validation_20260224_045821/artifacts/TS-001/TS-001_stage2.docx`
- 评分入库跟踪：
  - Stage1：before=0, after=1, persisted=True, note_matched=True
  - Stage2：before=1, after=2, persisted=True, note_matched=True
- 低满意度沉淀：
  - TS-001 的 stage2 评分 2 分已写入学习池（见第 5 节）。

### 4.2 TS-003 家庭资产配置科普手册
- 文档ID：`82884ec8e4484cadb09d59fe321306d9`
- 阶段1：
  - 评分：5/5
  - 验收：通过
  - 字符数：893
  - 快照：`.data/out/two_stage_validation_20260224_045821/artifacts/TS-003/TS-003_stage1.md`
  - DOCX：`.data/out/two_stage_validation_20260224_045821/artifacts/TS-003/TS-003_stage1.docx`
- 阶段2：
  - 评分：5/5
  - 验收：通过
  - 字符数：1166
  - 快照：`.data/out/two_stage_validation_20260224_045821/artifacts/TS-003/TS-003_stage2.md`
  - DOCX：`.data/out/two_stage_validation_20260224_045821/artifacts/TS-003/TS-003_stage2.docx`
- 评分入库跟踪：
  - Stage1：before=0, after=1, persisted=True, note_matched=True
  - Stage2：before=1, after=2, persisted=True, note_matched=True

## 5. 低满意度学习池验证
低满意度样本池路径：
- `.data/learning/low_satisfaction_feedback.jsonl`

本轮可确认写入样本：
- `doc_id=91578a6553214b5a9a217b93488fe144`（TS-001 stage2, rating=2）

可检索命令：
```bash
rg "91578a6553214b5a9a217b93488fe144" .data/learning/low_satisfaction_feedback.jsonl
```

## 6. 产物总路径
### 6.1 最终主运行（推荐查看）
- JSON：`.data/out/two_stage_validation_20260224_045821/two_stage_run_20260224_045821.json`
- Markdown 报告：`.data/out/two_stage_validation_20260224_045821/two_stage_report_20260224_045821.md`
- DOCX 报告：`.data/out/two_stage_validation_20260224_045821/two_stage_report_20260224_045821.docx`

### 6.2 每个用例导出 DOCX
- `.data/out/two_stage_validation_20260224_045821/artifacts/TS-001/TS-001_stage1.docx`
- `.data/out/two_stage_validation_20260224_045821/artifacts/TS-001/TS-001_stage2.docx`
- `.data/out/two_stage_validation_20260224_045821/artifacts/TS-003/TS-003_stage1.docx`
- `.data/out/two_stage_validation_20260224_045821/artifacts/TS-003/TS-003_stage2.docx`

## 7. 注意事项
- Windows 终端代码页导致中文在控制台可能显示乱码，但产物文件（JSON/MD/DOCX）为 UTF-8 正常内容。
- 两阶段结果受模型随机性影响较大，同一用例多次执行可能出现评分波动。

## 8. 当前结论
- “评分 + 低分沉淀 + 前端两阶段测试 + DOCX 导出 + 详细记录”已完整打通。
- 评分数据可回查，低分样本可沉淀用于后续学习。
- 前端实测可稳定执行，并能产出可交付文档与报告。
