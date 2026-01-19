from __future__ import annotations

import os
import subprocess
import sys
import time

from writing_agent.llm import OllamaClient, get_ollama_settings


def _start_ollama_serve() -> None:
    # 让 ollama serve 在后台跑；uvicorn 占用前台输出。
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def _wait_until(predicate, timeout_s: float, interval_s: float = 0.2) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


def main() -> int:
    settings = get_ollama_settings()
    if settings.enabled:
        client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
        if not client.is_running():
            try:
                _start_ollama_serve()
            except FileNotFoundError:
                print("未找到 ollama 可执行文件：请先安装 Ollama 并加入 PATH。", file=sys.stderr)
                return 2
            if not _wait_until(client.is_running, timeout_s=10):
                print(f"Ollama 未就绪：请确认 {settings.base_url} 可访问。", file=sys.stderr)
                return 3
        if not client.has_model():
            print(f"首次使用，正在拉取模型 {settings.model} ...")
            client.pull_model()

    host = os.environ.get("WRITING_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("WRITING_AGENT_PORT", "8000"))
    # 等价于：uvicorn writing_agent.web.app_v2:app --host ... --port ...
    import uvicorn

    uvicorn.run("writing_agent.web.app_v2:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

