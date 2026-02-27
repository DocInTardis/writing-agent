import json
from pathlib import Path


def test_mixed_dataset_has_synthetic_and_real() -> None:
    rows = json.loads(Path('tests/fixtures/mixed_dataset.json').read_text(encoding='utf-8'))
    kinds = {str(r.get('type')) for r in rows if isinstance(r, dict)}
    assert 'synthetic' in kinds
    assert 'real' in kinds
