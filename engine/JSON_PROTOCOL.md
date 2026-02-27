# 强制 JSON 协议（结构/内容解耦）草案

## 目标
- 所有模型与系统、模型与模型的通信都使用严格 JSON。
- 正文内容与结构解耦：JSON 只携带结构与 block_id，正文在 TextStore 中按 id 存取。
- 任何阶段不再接受自由文本回退；解析失败即重试，仍失败则报错。

## 核心概念
- Block: 文档的最小结构单元（paragraph/table/figure/heading/list）。
- Block ID: 每个 Block 的唯一标识，正文内容通过 ID 访问。
- TextStore: 用于存储/获取正文与复杂对象的存储层（文件或 KV）。

## 通用约束
- 所有响应必须是单个 JSON 对象。
- 禁止输出 Markdown/自然语言前缀或后缀。
- 必须包含 "stage" 字段。

## TextStore 规范
- 读写接口（抽象）：
  - put_text(id: string, text: string)
  - get_text(id: string) -> string
  - put_json(id: string, obj: object)
  - get_json(id: string) -> object
- 允许的后端：文件系统（.data/text_store）、内存 KV、数据库。

## 阶段协议

### 1) ANALYSIS
```json
{
  "stage": "analysis",
  "intent": "generate_report",
  "confidence": 0.82,
  "rewritten_query": "生成一份不限内容的周报，约2000字",
  "constraints": {
    "language": "zh",
    "tone": "正式",
    "length_chars": 2000,
    "format": "docx"
  },
  "missing": [],
  "entities": {
    "topic": "周报",
    "time_range": "本周"
  },
  "audience": "项目经理/研发团队",
  "style_guide": {
    "heading_levels": 3,
    "numbering": "auto",
    "use_toc": true
  },
  "risk_flags": ["数据敏感", "延期风险"]
}
```

### 2) PLAN
```json
{
  "stage": "plan",
  "title": "项目周报",
  "total_chars": 2000,
  "sections": [
    {
      "title": "背景",
      "target_chars": 300,
      "key_points": ["项目现状", "本周总体目标", "关键里程碑"],
      "figures": [],
      "tables": [],
      "evidence_queries": []
    },
    {
      "title": "本周工作",
      "target_chars": 900,
      "key_points": ["需求梳理", "研发进度", "联调与测试", "风险处理"],
      "figures": [
        {
          "type": "flow",
          "caption": "本周交付流程",
          "nodes": ["需求", "设计", "开发", "测试", "发布"]
        }
      ],
      "tables": [
        {
          "caption": "任务清单",
          "columns": ["任务", "负责人", "状态", "完成率"],
          "row_budget": 6
        }
      ],
      "evidence_queries": ["项目管理 周报", "研发进度 风险管理"]
    },
    {
      "title": "问题与风险",
      "target_chars": 400,
      "key_points": ["阻塞项", "影响范围", "应对方案"],
      "figures": [],
      "tables": [
        {
          "caption": "风险清单",
          "columns": ["风险", "影响", "概率", "应对"],
          "row_budget": 4
        }
      ],
      "evidence_queries": []
    },
    {
      "title": "下周计划",
      "target_chars": 300,
      "key_points": ["功能收尾", "性能优化", "跨部门协作"],
      "figures": [],
      "tables": [],
      "evidence_queries": []
    }
  ]
}
```

### 3) EVIDENCE
```json
{
  "stage": "evidence",
  "section_title": "背景",
  "items": [
    {
      "id": "ref_001",
      "title": "项目管理年度报告",
      "url": "https://example.com/report",
      "snippet": "本年度项目管理强调跨部门协作...",
      "source": "internal"
    },
    {
      "id": "ref_002",
      "title": "敏捷研发实践白皮书",
      "url": "https://example.com/agile",
      "snippet": "敏捷流程可提升迭代交付效率...",
      "source": "external"
    }
  ]
}
```

### 4) SECTION（结构引用）
```json
{
  "stage": "section",
  "section_title": "本周工作",
  "blocks": [
    {"type": "paragraph", "id": "p_9a7c"},
    {"type": "paragraph", "id": "p_1f02"},
    {"type": "list", "ordered": false, "id": "l_120d"},
    {"type": "table", "id": "t_33b1"},
    {"type": "figure", "id": "f_0c21"}
  ]
}
```

### 5) AGGREGATE（最终结构）
```json
{
  "stage": "aggregate",
  "title": "项目周报",
  "blocks": [
    {"type": "heading", "level": 1, "text": "项目周报"},
    {"type": "heading", "level": 2, "text": "本周工作"},
    {"type": "paragraph", "id": "p_9a7c"},
    {"type": "list", "ordered": false, "id": "l_120d"},
    {"type": "table", "id": "t_33b1"},
    {"type": "figure", "id": "f_0c21"},
    {"type": "heading", "level": 2, "text": "问题与风险"},
    {"type": "paragraph", "id": "p_risk_01"},
    {"type": "table", "id": "t_risk_01"}
  ]
}
```

## TextStore 示例（文件存储）
```
.data/text_store/p_9a7c.txt
.data/text_store/p_1f02.txt
.data/text_store/p_risk_01.txt
.data/text_store/t_33b1.json
.data/text_store/t_risk_01.json
.data/text_store/f_0c21.json
```

## 失败策略
- JSON 解析失败：自动重试（强制只输出 JSON）。
- 重试仍失败：报告明确错误并中止流程。
- 禁止回退到自由文本。
