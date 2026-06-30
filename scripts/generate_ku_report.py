import json
from pathlib import Path

ku_path = Path(".data/kg/knowledge_units.jsonl")
lines = ku_path.read_text(encoding="utf-8").strip().split("\n")

html_path = Path(".data/kg/knowledge_units_report.html")

head = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>知识点卡片报告</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Microsoft YaHei", sans-serif; background: #f5f5f0; padding: 20px; max-width: 900px; margin: 0 auto; }
  h1 { color: #2b2416; border-bottom: 2px solid #d7d7d7; padding-bottom: 10px; }
  .stats { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
  .stat-box { background: #fff; border-radius: 8px; padding: 12px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
  .stat-box b { display: block; font-size: 20px; color: #1f7a3d; }
  .stat-box span { font-size: 12px; color: #666; }
  .ku-card { background: #fff; border-radius: 10px; padding: 16px; margin-bottom: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); border-left: 4px solid #4a90d9; }
  .ku-card .id { font-size: 11px; color: #999; margin-bottom: 4px; }
  .ku-card .claim { font-size: 15px; font-weight: 600; color: #2b2416; margin-bottom: 8px; line-height: 1.5; }
  .ku-card .evidence { font-size: 13px; color: #555; background: #faf8f3; padding: 10px; border-radius: 6px; margin-bottom: 8px; line-height: 1.5; }
  .ku-card .meta { display: flex; gap: 10px; flex-wrap: wrap; font-size: 12px; color: #666; }
  .ku-card .meta .badge { background: #e8f6ec; color: #1f7a3d; padding: 2px 8px; border-radius: 999px; }
  .ku-card .meta .entity { background: #f0f6fc; color: #4a90d9; padding: 2px 8px; border-radius: 999px; }
  .ku-card .meta .rel { background: #fff3cd; color: #856404; padding: 2px 8px; border-radius: 999px; }
  .ku-card .source { margin-top: 6px; font-size: 11px; color: #999; }
</style>
</head>
<body>
<h1>📚 知识点卡片报告</h1>
<div class="stats">
  <div class="stat-box"><b>122</b><span>知识点卡片</span></div>
  <div class="stat-box"><b>76</b><span>图谱实体</span></div>
  <div class="stat-box"><b>88</b><span>关系连接</span></div>
  <div class="stat-box"><b>6</b><span>来源论文</span></div>
</div>
"""

parts = [head]

for i, line in enumerate(lines[:10]):
    d = json.loads(line)
    entities = d.get("entities", [])
    relations = d.get("relation_hints", [])
    ent_html = "".join(f'<span class="entity">{e}</span>' for e in entities[:5])
    rel_html = "".join(f'<span class="rel">{r}</span>' for r in relations[:3])
    conf = d.get("confidence", 0)
    conf_color = "#1f7a3d" if conf >= 0.9 else "#856404" if conf >= 0.7 else "#b33838"

    card = (
        f'<div class="ku-card">\n'
        f'  <div class="id">第{i+1}张 · {d["ku_id"]}</div>\n'
        f'  <div class="claim">📌 观点：{d["claim"]}</div>\n'
        f'  <div class="evidence">📖 依据：{d["evidence"][:200]}{"..." if len(d["evidence"]) > 200 else ""}</div>\n'
        f'  <div class="meta">\n'
        f'    <span class="badge" style="color:{conf_color}">✓ 置信度 {conf:.0%}</span>\n'
        f'    {ent_html}\n'
        f'    {rel_html}\n'
        f'  </div>\n'
        f'  <div class="source">📄 来源：{d.get("source_title", d["source_doc"])[:70]}</div>\n'
        f'</div>\n'
    )
    parts.append(card)

parts.append("</body>\n</html>")
html_path.write_text("\n".join(parts), encoding="utf-8")
print(f"中文版报告已生成: {html_path.resolve()}")
