# Writing-Agent 最终版待办清单（升级点 + 大文件治理）

## 文档信息
- 日期: 2026-02-26
- 目标: 合并“系统升级点”和“大文件治理”形成一份最终待办文档
- 规则: 不区分优先级，不区分执行顺序，只列需要做到的点
- 使用方式: 完成一项勾一项，后续可直接抽取已完成项写入简历

---

## 一、当前基线（用于后续验收对照）

### 1.1 大文件规模快照
- `>=1000` 行文件数: `14`
- `>=2000` 行文件数: `6`
- `>=3000` 行文件数: `5`

### 1.2 Top 大文件清单（按行数）
| 文件 | 当前行数 |
|---|---:|
| `writing_agent/web/app_v2.py` | 6110 |
| `writing_agent/web/frontend_svelte/src/App.svelte` | 4858 |
| `writing_agent/v2/graph_runner.py` | 3873 |
| `writing_agent/web/frontend_svelte/src/lib/components/Editor.svelte` | 3837 |
| `writing_agent/web/static/v2.js` | 3034 |
| `scripts/ui_content_validation_runner.py` | 2050 |
| `tests/test_citation_verify_and_delete.py` | 1853 |
| `writing_agent/web/frontend_svelte/src/lib/components/PerformanceMetrics.svelte` | 1476 |
| `writing_agent/document/v2_report_docx.py` | 1368 |
| `writing_agent/web/frontend_svelte/src/lib/utils/markdown.ts` | 1231 |

---

## 二、统一完成标准（DoD）
- [x] `>=3000` 行文件数从 `5` 降到 `0`。
- [x] `>=2000` 行文件数从 `6` 降到 `<=1`。
- [x] `>=1000` 行文件数从 `14` 降到 `<=5`。
- [x] 新增代码文件满足“建议 `<=800` 行、硬上限 `<=1000` 行”。
- [x] 核心业务函数满足“建议 `<=80` 行、硬上限 `<=120` 行”。
- [x] 关键回归（生成/导出/引用/RAG）通过率不下降。
- [x] 外部 API 路径与响应契约保持兼容或提供版本化迁移。
- [x] preflight 与 CI 质量门禁持续全绿。

---

## 三、综合待办清单

## 编排架构与 Agent Runtime
- [x] 将现有自研 `graph_runner` 升级为“自研图 + LangGraph”双引擎能力层。
- [x] 在编排层引入 `StateGraph` 显式节点与边定义，沉淀可追踪执行路径。
- [x] 建立统一状态模型（Typed State + Schema Version），支持状态演进兼容。
- [x] 为每个节点定义输入/输出契约（schema），降低节点耦合导致的连锁错误。
- [x] 增加章节级 checkpoint，支持中断恢复、失败重试和续跑。
- [x] 增加 human-in-the-loop interrupt 点（如大纲确认、引用复核、终稿审批）。
- [x] 引入子图（subgraph）拆分 planner/writer/reviewer/qa。
- [x] 增加 graph 运行回放（deterministic replay）能力，用于事故复盘。
- [x] 引入 graph 执行 metadata（trace_id/span_id/node_id）统一日志协议。
- [x] 为 `compose_mode/resume_sections/format_only` 等入口建立显式路由节点。

## 组件引入（含 Vercel AI SDK）
- [x] 在前端引入 Vercel AI SDK 流式接口能力，统一 token streaming 与中断恢复交互。
- [x] 在后端建立 AI SDK 适配层，统一 `streamText/generateObject/tool calling` 语义映射。
- [x] 统一结构化输出链路（Zod/Pydantic/JSON Schema），降低输出不可解析率。
- [x] 通过 SDK 层屏蔽多模型提供商差异，降低 provider 切换改造成本。
- [x] 建立 SDK 级错误分类（rate limit/timeout/context overflow/schema fail）与回退策略。
- [x] 支持前端流式增量 patch（而非整段替换），提升编辑器渲染稳定性。
- [x] 将工具调用协议标准化（tool registry + manifest），降低插件接入成本。
- [x] 加入请求去重与幂等键，避免重复触发导致重复生成。

## Prompt 工程与上下文治理
- [x] 建立 Prompt Registry（版本、标签、灰度、人群、回滚）。
- [x] 将 prompt 拆分为 system/developer/task/style/citation 子层，减少单 prompt 过重。
- [x] 对 prompt 变量建立 schema 校验与缺失兜底。
- [x] 建立 prompt lint（禁词、长度、变量覆盖率、冲突规则）。
- [x] 增加 prompt A/B 测试框架，支持按任务类型比较成稿质量。
- [x] 增加 few-shot 示例集管理（按领域、语种、文体分类）。
- [x] 建立上下文预算器（token budgeting）并按章节动态分配上下文。
- [x] 引入上下文压缩策略（摘要记忆 + 关键约束保留）控制超长文漂移。
- [x] 对抗 prompt injection（来源隔离、指令优先级规则、引用污染拦截）。

## RAG、检索与引用可信度
- [x] 升级为 Hybrid Retrieval（BM25 + Vector）并引入 reranker。
- [x] 支持 multi-query 检索扩展，提高召回覆盖率。
- [x] 引入来源质量评分与黑白名单（域名、作者、时效、可信级别）。
- [x] 建立引用片段级绑定（citation span grounding）。
- [x] 增加引用可达性检查（URL 可访问、文档存在、状态码正常）。
- [x] 增加引用元数据一致性校验（标题/作者/时间/来源一致）。
- [x] 对 RAG 结果做去重、去近重复与冲突来源标注。
- [x] 增加“无证据降级策略”（证据不足时低置信表达或提示补充来源）。
- [x] 建立历史知识快照版本，支持可复现离线评测。

## 模型路由、稳定性与效果控制
- [x] 建立模型路由器（按任务复杂度、时延目标、质量目标动态选模）。
- [x] 支持 planner/writer/reviewer 多模型协作策略。
- [x] 增加温度、top_p、max_tokens 的场景化策略模板。
- [x] 建立 fallback 链（主模型失败自动切换备模型）。
- [x] 增加超时、重试、指数退避、熔断、限流全链路策略。
- [x] 建立输出长度控制算法（章节预算 + 段落预算 + 终稿校正）。
- [x] 引入语义缓存（L1 本地 + L2 远程）减少重复生成。
- [x] 增加一致性自检器（逻辑断裂、术语漂移、前后冲突检测）。

## 可观测性、评测与质量门禁
- [x] 接入 OpenTelemetry（trace/metric/log）并统一 correlation_id。
- [x] 增加链路级 dashboard（TTFT、完成时延、失败率、重试率、每千字成本）。
- [x] 建立自动评测流水线（事实性、结构性、可读性、风格一致性、引用正确率）。
- [x] 引入 LLM-as-judge + 人审抽样双轨评测，减少单评测源偏差。
- [x] 建立评测基准集（按场景、语种、模板、长度分层）。
- [x] 将评测回归门禁接入 CI/CD，质量退化自动阻断发布。
- [x] 建立 chaos 测试（接口抖动、超时、引用失效、事件乱序）覆盖关键链路。
- [x] 建立事故复盘模板（输入快照、graph 轨迹、模型响应、最终差异）。

## 后端服务拆分与 API 治理
- [x] 继续拆分 `app_v2.py`，仅保留应用装配和路由注册。
- [x] 将业务逻辑下沉到 `api/*_flow.py`、`services/*_service.py`、`domain/*`。
- [x] 将长任务改为 job 队列模式（提交/轮询/回调）提升峰值稳定性。
- [x] 建立 generation/export/citation/rag 的服务边界和契约。
- [x] 统一请求/响应 schema 与错误码规范。
- [x] 引入 API 版本管理（兼容期、弃用公告、迁移文档）。
- [x] 增加 webhook/event-bus 接口能力便于企业集成。
- [x] 增加多租户隔离和细粒度 RBAC。
- [x] 建立审计日志（谁在何时触发了何种生成/导出/审批行为）。

## 前端工作台与编辑器能力
- [x] 拆分 `App.svelte` 与 `Editor.svelte` 超大组件，沉淀 `flows/stores/components` 分层。
- [x] 引入前端状态机（生成态、编辑态、恢复态、失败态）统一状态迁移。
- [x] 增强流式渲染性能（分块更新、虚拟滚动、节流重绘）。
- [x] 增加可恢复会话能力（刷新后继续、断线后恢复、失败后重试）。
- [x] 增加段落级 diff/patch 视图，支持可视化审阅与回退。
- [x] 增加引用审阅面板（来源、置信度、可达性、替换建议）。
- [x] 增加模板 lint 可视反馈和自动修复建议。
- [x] 完善异常路径体验（超时、配额不足、引用失效、网络抖动）。

## 大文件治理与代码结构治理
- [x] 建立文件大小门禁（建议 `<=800` 行，硬上限 `<=1000` 行）。
- [x] 建立函数复杂度门禁（行数、圈复杂度、参数个数）。
- [x] 建立“新增超大文件阻断”规则并接入 preflight。
- [x] 建立架构边界检查（禁止跨层直接调用）。
- [x] 沉淀 ADR（Architecture Decision Record）记录关键改造决策。
- [x] 为 `graph_runner.py` 按 `analysis/planning/drafting/aggregate/validation` 拆模块。
- [x] 为 `v2_report_docx.py` 按 `toc/styles/content/fields/builder` 拆模块。
- [x] 为 `v2.js` 与前端大组件做职责拆分（状态、渲染、命令、数据访问）。
- [x] 对大测试文件按场景拆分，减少冲突与调试难度。

## 大文件逐文件落地任务（目标行数）
- [x] `writing_agent/web/app_v2.py`：`6110 -> <=1500`，保留应用装配与路由注册，其余下沉到 `api/services`。
- [x] `writing_agent/v2/graph_runner.py`：`3873 -> <=1200`，拆为 `analysis/planning/drafting/aggregate/validation/runner`。
- [x] `writing_agent/web/frontend_svelte/src/App.svelte`：`4858 -> <=1200`，业务流下沉到 `flows/stores`。
- [x] `writing_agent/web/frontend_svelte/src/lib/components/Editor.svelte`：`3837 -> <=1500`，拆分 editor 子组件并统一状态管理。
- [x] `writing_agent/document/v2_report_docx.py`：`1368 -> <=800`，拆分 `toc/styles/content/field/builder`。
- [x] `writing_agent/web/static/v2.js`：`3034 -> <=1000`，按域拆分并逐步迁移到 Svelte 侧。
- [x] `scripts/ui_content_validation_runner.py`：`2050 -> <=1000`，拆分为 `runner/core/reporter/config`。
- [x] `tests/test_citation_verify_and_delete.py`：`1853 -> <=900`，按场景拆分到多个 test module。
- [x] `writing_agent/web/frontend_svelte/src/lib/components/PerformanceMetrics.svelte`：`1476 -> <=800`，图表层与数据层分离。
- [x] `writing_agent/web/frontend_svelte/src/lib/utils/markdown.ts`：`1231 -> <=700`，解析器与渲染工具解耦。

## 测试体系与回归保障
- [x] 建立单元/集成/E2E 分层测试金字塔，避免过度依赖端到端测试。
- [x] 对 prompt 与结构化输出增加 schema 回归测试。
- [x] 对导出链路建立 golden 文件回归（DOCX/PDF/Markdown）。
- [x] 增加合成数据与真实样本混合测试集。
- [x] 增加并发与长任务压力测试（高并发提交、长文持续生成）。
- [x] 增加引用链路专项测试（可达性、元数据一致、断链恢复）。
- [x] 增加前端 Playwright 人设矩阵与异常路径矩阵。
- [x] 建立 flaky test 识别与隔离机制。

## 安全、合规与企业能力
- [x] 建立敏感信息识别与脱敏（PII、密钥、内部标识）。
- [x] 建立数据留存与删除策略（按租户、按文档类型、按时效）。
- [x] 建立内容安全策略（违规内容拦截、风险提示、人工复核）。
- [x] 建立 Policy-as-Code（策略可版本化、可审计、可回滚）。
- [x] 增加供应链安全扫描（依赖漏洞、许可证、SBOM）。
- [x] 建立审计证据链（操作日志不可篡改、关键事件签名）。
- [x] 建立租户级访问隔离与导出权限控制。

## 性能、部署与平台化
- [x] 建立本地推理与远程推理的统一编排层，支持无缝切换。
- [x] 为 CPU/GPU/模型服务建立资源感知调度策略。
- [x] 建立分层缓存（请求缓存、片段缓存、引用缓存、导出缓存）。
- [x] 建立发布灰度机制（feature flag、按租户灰度、快速回滚）。
- [x] 建立多环境一致性检查（dev/staging/prod 配置差异治理）。
- [x] 建立容器化与基础设施即代码（IaC）规范化部署。
- [x] 建立容量规划与成本看板（调用量、token、时延、成功率）。
- [x] 建立多区域容灾与备份恢复演练。

---

## 四、完成后可直接提炼为简历亮点
- [x] LangGraph + 自研图双引擎编排上线并完成线上灰度。
- [x] Vercel AI SDK 驱动的端到端流式生成与工具调用上线。
- [x] Prompt Registry + A/B 评测 + 一键回滚闭环上线。
- [x] Hybrid RAG + reranker + 引用真实性门禁上线。
- [x] 超大文件治理落地（核心模块拆分 + 门禁上线 + 回归稳定）。
- [x] OTel 全链路观测 + 质量门禁 CI 自动阻断上线。
- [x] 多租户 RBAC + 审计闭环上线。
