# Canonical Document Format Spec (v0.1)

## 目标
- 所有内容统一到一种内部格式（Canonical Format）
- 引擎只处理 AST，所有外部格式通过适配器映射

---

## 核心结构

```json
{
  "id": "uuid",
  "version": 1,
  "metadata": {
    "title": "",
    "author": "",
    "created_at": 0,
    "updated_at": 0
  },
  "blocks": []
}
```

---

## Block 类型

### Heading
```json
{ "type": "heading", "id": "uuid", "level": 1, "content": [Inline], "dirty": false }
```

### Paragraph
```json
{ "type": "paragraph", "id": "uuid", "content": [Inline], "dirty": false }
```

### List
```json
{ "type": "list", "id": "uuid", "ordered": false, "items": [ListItem], "dirty": false }
```

### Quote
```json
{ "type": "quote", "id": "uuid", "content": [Block], "dirty": false }
```

### Code
```json
{ "type": "code", "id": "uuid", "lang": "rs", "code": "...", "dirty": false }
```

### Table
```json
{ "type": "table", "id": "uuid", "rows": [[Cell]], "dirty": false }
```

### Figure
```json
{ "type": "figure", "id": "uuid", "url": "...", "caption": "...", "dirty": false }
```

---

## Inline 类型

### Text
```json
{ "type": "text", "value": "..." }
```

### Styled
```json
{ "type": "styled", "style": {"bold": true, "italic": false, "underline": false}, "content": [Inline] }
```

### Link
```json
{ "type": "link", "url": "...", "text": [Inline] }
```

### CodeSpan
```json
{ "type": "codespan", "value": "..." }
```

---

## 适配器原则

- 外部格式只能转换为 AST
- AST 内不保存外部格式特有语法
- 导出时按目标格式做语义映射

---

## 兼容性规则

- 未识别的格式 → 降级为 Paragraph
- 不支持的样式 → 丢弃但保留纯文本
- 图表/表格优先保留标题信息

---

## 版本与扩展

- `version` 用于兼容升级
- 新增 Block / Inline 时必须向后兼容
- 建议通过 `extra` 字段扩展（v0.2 预留）

---

## 后续工作

- 根据此规范实现：
  - Markdown 适配器
  - Docx 适配器
  - HTML 适配器

