from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class OllamaSettings:
    enabled: bool
    base_url: str
    model: str
    timeout_s: float


def get_ollama_settings() -> OllamaSettings:
    enabled_raw = os.environ.get("WRITING_AGENT_USE_OLLAMA", "1").strip().lower()
    enabled = enabled_raw not in {"0", "false", "no", "off"}
    base_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "qwen:7b").strip() or "qwen:7b"
    timeout_s = float(os.environ.get("OLLAMA_TIMEOUT_S", "60"))
    return OllamaSettings(enabled=enabled, base_url=base_url, model=model, timeout_s=timeout_s)

