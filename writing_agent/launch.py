"""Application launcher for writing-agent."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

from writing_agent.llm import OllamaClient, get_ollama_settings


def _start_ollama_serve() -> None:
    """Start a detached local Ollama process if the binary is available."""
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
    """Poll `predicate` until it returns True or timeout is reached."""
    start = time.time()
    while time.time() - start < timeout_s:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


def _pick_available_port(host: str, base_port: int, tries: int = 20) -> int:
    """Find the first bindable port starting at `base_port`."""
    for i in range(tries):
        port = base_port + i
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    return base_port


def main() -> int:
    """Launch the web application and bootstrap Ollama when enabled."""
    settings = get_ollama_settings()
    if settings.enabled:
        client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
        if not client.is_running():
            try:
                _start_ollama_serve()
            except FileNotFoundError:
                print("ollama executable not found; install Ollama and add it to PATH.", file=sys.stderr)
                return 2
            if not _wait_until(client.is_running, timeout_s=10):
                print(f"Ollama is not reachable at {settings.base_url}.", file=sys.stderr)
                return 3
        if not client.has_model():
            print(f"Pulling model for first use: {settings.model} ...")
            client.pull_model()

    host = os.environ.get("WRITING_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("WRITING_AGENT_PORT", "8000"))
    port = _pick_available_port(host, port)

    import uvicorn

    uvicorn.run("writing_agent.web.app_v2:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
