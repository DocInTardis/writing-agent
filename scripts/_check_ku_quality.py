import json
from pathlib import Path

lines = Path('.data/kg/knowledge_units.jsonl').read_text(encoding='utf-8').strip().split('\n')
print(f'Total lines: {len(lines)}')
has_entities = sum(1 for l in lines if json.loads(l).get('entities'))
has_relations = sum(1 for l in lines if json.loads(l).get('relation_hints'))
print(f'With entities: {has_entities}')
print(f'With relation_hints: {has_relations}')

for l in lines:
    d = json.loads(l)
    if d.get('entities'):
        print(f'\nExample claim: {d["claim"][:80]}')
        print(f'  entities: {d["entities"]}')
        print(f'  relation_hints: {d["relation_hints"]}')
        break
