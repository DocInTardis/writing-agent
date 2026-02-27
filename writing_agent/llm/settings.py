"""Settings module.

This module belongs to `writing_agent.llm` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import json


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
    
    # 优化: 自动选择最大可用模型（优先7b > 3b > 1.5b > 0.5b）
    default_model = os.environ.get("OLLAMA_MODEL", "").strip()
    if not default_model:
        # 按质量优先级自动选择
        try:
            import subprocess
            result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                available = set()
                for line in result.stdout.splitlines()[1:]:
                    parts = line.split()
                    if parts:
                        available.add(parts[0].strip())
                
                # 优先级: 7b > 3b > 1.5b > 0.5b
                for candidate in ["qwen2.5:7b", "qwen2.5:3b", "qwen2.5:1.5b", "qwen2.5:0.5b"]:
                    if candidate in available:
                        default_model = candidate
                        break
        except Exception:
            pass
    
    model = default_model or "qwen2.5:1.5b"
    if model.strip().lower() in {"name", "model", "default", "unknown"}:
        model = "qwen2.5:7b"  # 默认改为7b
    
    timeout_s = float(os.environ.get("OLLAMA_TIMEOUT_S", "180"))
    metrics_path = Path(".data/metrics/stream_timing.json")
    if metrics_path.exists():
        try:
            data = json.loads(metrics_path.read_text(encoding="utf-8"))
            runs = data.get("runs") if isinstance(data, dict) else None
            if isinstance(runs, list) and runs:
                totals = [float(r.get("total_s", 0)) for r in runs if r.get("total_s")]
                if totals:
                    p95 = sorted(totals)[max(0, int(round((len(totals) - 1) * 0.95)))]
                    timeout_s = max(timeout_s, float(p95) * 1.2)
        except Exception:
            pass
    return OllamaSettings(enabled=enabled, base_url=base_url, model=model, timeout_s=timeout_s)
