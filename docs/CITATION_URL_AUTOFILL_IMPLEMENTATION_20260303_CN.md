# 引用 URL 自动补全功能改造方案（2026-03-03）

## 1. 目标与范围
- 目标：用户在“引用管理”中输入一个链接，系统自动解析并补全文献信息（标题、作者、年份、来源、建议 ID），并允许一键加入当前文档引用列表。
- 范围：
  - 后端新增 URL 解析接口；
  - 前端新增“链接自动补全”交互；
  - 新增后端测试与路由注册测试更新；
  - 不引入新的重量级依赖，优先复用现有 citation verify / OpenAlex / Crossref 能力。
- 非目标：
  - 不做全量爬虫；
  - 不保证任意网页都能 100% 解析成功；
  - 不改变现有引用核验流程语义。

## 2. 现状与问题
- 当前仅支持手动录入 `id/author/title/year/source`，用户成本高、易出错。
- 现有能力已经具备：
  - OpenAlex/Crossref 搜索与候选打分；
  - 引用归一化、核验缓存、候选挑选逻辑。
- 缺口：
  - 无“给 URL -> 自动补全引用”闭环。

## 3. 总体设计
采用“多阶段解析 + 逐级兜底”的确定性流水线：
1. URL 校验与安全过滤；
2. 结构化标识提取（DOI/arXiv/OpenAlex）；
3. 页面元数据抓取（title/meta/json-ld）作为补充；
4. 调用 OpenAlex/Crossref 检索并复用现有打分逻辑做实体补全；
5. 返回标准化引用建议 + 置信度 + 警告信息。

## 4. API 设计
### 4.1 新增接口
- `POST /api/doc/{doc_id}/citations/resolve-url`
- `GET /api/metrics/citation_resolve_url`（新增，可观测指标）
- `GET /api/metrics/citation_resolve_url/alerts/config`（resolve 告警配置读取）
- `POST /api/metrics/citation_resolve_url/alerts/config`（resolve 告警配置保存/重置）

### 4.2 请求体
```json
{
  "url": "https://example.com/paper"
}
```

### 4.3 响应体
```json
{
  "ok": 1,
  "item": {
    "id": "smith2024llm",
    "author": "Alice Smith, Bob Li",
    "title": "Large Language Model Evaluation in Practice",
    "year": "2024",
    "source": "Journal of LLM Studies",
    "url": "https://doi.org/10.1234/llm.2024.01"
  },
  "confidence": 0.93,
  "warnings": ["metadata_partial"],
  "debug": {
    "resolver": "doi_exact|search_match|metadata_only",
    "provider": "crossref",
    "score": 0.93
  }
}
```

### 4.4 错误语义
- `400`: URL 缺失、格式错误、非 http/https、命中 SSRF 风险策略。
- `404`: 文档不存在。
- `422`: URL 可访问但未提取到足够引用信息（如标题为空且检索失败）。
- `500`: 兜底异常。

## 5. 安全与稳健性
### 5.1 URL 安全策略
- 仅允许 `http/https`。
- 拒绝 `localhost`、回环地址、私网地址、链路本地地址、保留地址。
- 拒绝显式用户名密码（`user:pass@host`）。
- 限制端口为 `80/443`（或默认端口）。
- 请求超时与响应体大小上限（例如 8s、256KB 文本截断）。

### 5.2 网络调用策略
- 优先走结构化 ID（DOI/arXiv/OpenAlex）减少盲查。
- 页面抓取失败不直接失败，进入检索兜底。
- 检索失败但元数据可用时仍返回低置信度结果（`metadata_only`）。

## 6. 解析与补全策略
### 6.1 第一层：URL 模式提取
- DOI：`doi.org/...` 或 URL 中 DOI 正则。
- arXiv：`arxiv.org/abs/...`、`arxiv.org/pdf/...`。
- OpenAlex：`openalex.org/W...`。

### 6.2 第二层：HTML 元数据提取
- `title`、`meta[name=\"citation_title\"]`、`og:title`、`dc.title`。
- `citation_author` / `author` / `dc.creator`。
- `citation_publication_date` / `article:published_time` / `dc.date`。
- `citation_journal_title` / `og:site_name`。
- `application/ld+json`（Article/ScholarlyArticle 的 `name/headline/author/datePublished/isPartOf`）。

### 6.3 第三层：检索补全
- 生成查询串：`title + 第一作者姓 + year`（可用时）。
- 调用现有 `search_openalex` + `search_crossref`。
- 复用 `_pick_best_citation_candidate` 评分。
- DOI 精确命中优先级最高；否则使用分数阈值：
  - `>=0.82`：高置信度；
  - `>=0.60`：中置信度；
  - 否则标记低置信度。

### 6.4 ID 生成与冲突处理
- 基础规则：`authorSurname + year + titleToken`，统一小写与安全字符。
- 若与当前文档已有引用冲突，自动追加 `_2/_3...`。

## 7. 前端交互改造
- 在 `CitationManager.svelte` 的“添加引用”区域新增：
  - URL 输入框；
  - “自动补全”按钮；
  - 解析状态（loading）与错误提示（toast）。
- 成功后：
  - 将返回的 `item` 填充至 `newCitation`（可编辑）；
  - 若返回 `warnings`，提示“已补全但建议核对”。
- 保持原有“手动添加”路径，避免单点依赖自动化。

## 8. 代码改造清单（按执行顺序）
1. `writing_agent/web/services/citation_service.py`
   - 增加 URL 解析与补全核心逻辑。
2. `writing_agent/web/api/citation_flow.py`
   - 新增 `resolve-url` 路由及 service 调用。
3. `writing_agent/web/frontend_svelte/src/lib/components/CitationManager.svelte`
   - 新增 URL 自动补全 UI 与调用逻辑。
4. `tests/test_citation_resolve_url.py`
   - 新增接口行为测试（成功、非法 URL、元数据兜底、ID 冲突）。
5. `tests/test_flow_router_registration.py`
   - 增加新路由归属断言。
6. `writing_agent/web/frontend_svelte/src/lib/components/PerformanceMetrics.svelte`
   - resolve 指标面板新增告警配置表单（读写/重置）。
7. `writing_agent/web/frontend_svelte/src/lib/components/performanceMetricsUtils.ts`
   - resolve 告警配置表单类型与 clamp 归一化。

## 9. 测试计划
- 单元/接口测试：
  - `test_resolve_url_doi_exact_match`
  - `test_resolve_url_rejects_private_host`
  - `test_resolve_url_returns_metadata_only_when_search_unavailable`
  - `test_resolve_url_generates_unique_id_with_existing_citations`
  - `test_resolve_url_metrics_tracks_success_failure_and_fallback`
  - `test_resolve_url_metrics_alerts_respect_thresholds`
  - `test_resolve_url_metrics_alerts_send_and_dedupe`
  - `test_resolve_url_alerts_config_endpoint_roundtrip`
  - `test_resolve_url_metrics_alerts_use_saved_config`
  - `test_resolve_url_alerts_config_admin_key_guard`
  - `test_resolve_url_alerts_config_ops_rbac_role_separation`
- 回归：
  - `tests/test_citation_verify_and_delete.py`
  - `tests/test_flow_router_registration.py`

## 10. 验收标准
- 用户输入常见论文 URL 可自动得到可用引用条目。
- 接口在异常网络环境下可降级返回，不崩溃。
- SSRF 基础防护生效。
- 新旧引用功能都可用，测试通过。

## 11. 风险与后续迭代
- 风险：站点反爬、JS 渲染页面元数据缺失、部分中文站点 meta 非标准。
- 后续可迭代：
  - 增加域名级策略（如 arxiv/doi/openalex 直接解析优先）；
  - 增加可观测指标（resolve 成功率、平均延迟、fallback 比例）；
  - 与引用核验结果联动，自动标注“已核验/待核验”。

## 12. 实施状态（2026-03-03）
- 已完成：
  - 新增后端接口：`POST /api/doc/{doc_id}/citations/resolve-url`。
  - 新增服务能力：URL 安全校验、结构化 hint 提取、HTML/meta/json-ld 元数据提取、OpenAlex/Crossref 补全、唯一引用 ID 生成。
  - 新增前端交互：引用管理弹窗中支持 URL 输入 + 一键自动补全并回填表单。
  - 新增可观测指标：成功率、失败数、fallback 比例、延迟分位、provider/resolver 分布与 recent 明细。
  - 新增 resolve 告警评估：failure_rate / fallback_rate / p95_ms / low_confidence_rate 阈值规则与 severity 汇总。
  - 新增 resolve 告警通知：webhook 通道、signature 去重、cooldown 抑制、recent events 追踪。
  - 新增指标接口：`GET /api/metrics/citation_resolve_url`。
  - 新增 resolve 告警配置接口：`GET/POST /api/metrics/citation_resolve_url/alerts/config`（RBAC: `alerts.read`/`alerts.write`）。
  - 新增 resolve 告警配置持久化：支持 env 默认值 + `.data/citation_resolve_alerts_config.json` 覆盖。
  - 前端性能面板已接入 resolve-url 指标展示（概览卡片 + resolver/provider 分布 + recent runs + alert 状态/规则 + notify 状态/事件）。
  - 前端性能面板新增 Resolve Alert Config 可编辑表单（阈值 + notify 开关/cooldown/timeout）。
  - 新增测试：`tests/test_citation_resolve_url.py`（11 个关键场景，含 resolve config 的 admin key 与 RBAC 角色隔离校验）。
  - 更新路由归属测试：`tests/test_flow_router_registration.py`。
- 已验证：
  - `tests/test_citation_resolve_url.py`
  - `tests/test_flow_router_registration.py`
  - `tests/test_citation_verify_and_delete.py`
  - 前端构建：`npm --prefix writing_agent/web/frontend_svelte run build`
