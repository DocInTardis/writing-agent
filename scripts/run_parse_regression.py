"""Run Parse Regression command utility.

This script is part of the writing-agent operational toolchain.
"""

import json
from writing_agent.web import app_v2

cases = json.load(open('tests/fixtures/parse_cases.json', 'r', encoding='utf-8'))
for c in cases:
    text = c.get('input', '')
    parsed = app_v2._fast_extract_prefs(text)
    analysis = app_v2._normalize_analysis({}, text)
    summary = app_v2._build_pref_summary(text, analysis, parsed.get('title',''), parsed.get('formatting',{}), parsed.get('generation_prefs',{}))
    print('==', c.get('id'))
    print('input:', text)
    print('summary:', summary)
    print('parsed:', parsed)
    print()
