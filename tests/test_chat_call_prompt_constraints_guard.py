from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = ROOT / "writing_agent"


_ALLOWED_WITHOUT_CONTRACT = {
    # LLM adapters/providers are transport layers, not prompt business logic.
    "writing_agent/llm/ai_sdk_adapter.py",
    "writing_agent/llm/providers/ollama_provider.py",
    "writing_agent/llm/providers/node_ai_gateway_provider.py",
    # Startup warm-up ping only.
    "writing_agent/web/app_v2.py",
}


def _normalize(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def test_chat_calls_require_prompt_contract_markers() -> None:
    missing: list[str] = []
    pattern = re.compile(r"\.chat(?:_stream)?\(")

    for file in CODE_ROOT.rglob("*.py"):
        rel = _normalize(file)
        text = file.read_text(encoding="utf-8")
        if not pattern.search(text):
            continue
        if rel in _ALLOWED_WITHOUT_CONTRACT:
            continue
        if "<task>" not in text or "<constraints>" not in text:
            missing.append(rel)

    assert not missing, "Missing prompt-contract markers for chat calls:\n" + "\n".join(sorted(missing))

