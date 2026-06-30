"""Generate a Notion-compatible Markdown preview of KnowledgeUnits.

This lets you see the export format before connecting to Notion API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def to_notion_markdown(units: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "# 📚 知识点卡片（Notion 预览）\n",
        "## 导入说明",
        "1. 复制以下内容到 Notion 页面",
        "2. 或使用 Notion 的 CSV 导入功能",
        "3. 每个知识点 = 一个 Notion 页面（Database 条目）\n",
        "---\n",
    ]

    for i, u in enumerate(units[:20], 1):
        lines.append(f"### 📌 {u.get('claim', '无观点')[:80]}")
        lines.append(f"- **KU ID**: `{u.get('ku_id', '')}`")
        lines.append(f"- **置信度**: {u.get('confidence', 0):.0%}")
        lines.append(f"- **状态**: 审核中")
        lines.append(f"- **来源**: {u.get('source_doc', '')}")
        lines.append(f"- **论文**: {u.get('source_title', '')}")
        if u.get('source_page'):
            lines.append(f"- **页码**: {u['source_page']}")
        if u.get('entities'):
            lines.append(f"- **实体**: {', '.join(u['entities'])}")
        if u.get('relation_hints'):
            lines.append(f"- **关系**: {', '.join(u['relation_hints'])}")
        lines.append(f"\n> **依据**: {u.get('evidence', '')[:300]}{'...' if len(u.get('evidence', '')) > 300 else ''}\n")

    return "\n".join(lines)


def to_notion_csv(units: list[dict[str, Any]]) -> str:
    """Generate CSV for Notion Database import."""
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Claim", "Evidence", "Source", "Page", "Confidence", "Status", "Entities", "KU ID"])
    for u in units:
        writer.writerow([
            u.get("claim", ""),
            u.get("evidence", ""),
            u.get("source_doc", ""),
            u.get("source_page", ""),
            u.get("confidence", 0),
            "审核中",
            ", ".join(u.get("entities", [])),
            u.get("ku_id", ""),
        ])
    return output.getvalue()


def main() -> None:
    ku_path = Path(".data/kg/knowledge_units.jsonl")
    if not ku_path.exists():
        print("No knowledge units found. Run fetch script first.")
        return

    lines = ku_path.read_text(encoding="utf-8").strip().split("\n")
    units = [json.loads(line) for line in lines if line.strip()]
    print(f"Loaded {len(units)} knowledge units")

    # Markdown preview
    md = to_notion_markdown(units)
    md_path = Path(".data/kg/notion_preview.md")
    md_path.write_text(md, encoding="utf-8")
    print(f"Markdown preview: {md_path.resolve()}")

    # CSV for import
    csv_content = to_notion_csv(units)
    csv_path = Path(".data/kg/notion_import.csv")
    csv_path.write_text(csv_content, encoding="utf-8")
    print(f"CSV import file: {csv_path.resolve()}")


if __name__ == "__main__":
    main()
