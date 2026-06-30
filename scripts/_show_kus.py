import json
from pathlib import Path

lines = Path(".data/kg/knowledge_units.jsonl").read_text(encoding="utf-8").strip().split("\n")
print(f"Total: {len(lines)} knowledge units\n")
for i, line in enumerate(lines[:10]):
    d = json.loads(line)
    print(f"--- [{i+1}] {d['ku_id']} ---")
    print(f"Claim:    {d['claim']}")
    print(f"Evidence: {d['evidence'][:100]}...")
    print(f"Source:   {d['source_doc']}")
    print(f"Title:    {d.get('source_title', '')[:60]}")
    print(f"Entities: {d.get('entities', [])}")
    print(f"Relation: {d.get('relation_hints', [])}")
    print(f"Confidence: {d.get('confidence', 0)}")
    print()
