"""Application launcher for writing-agent."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys

from writing_agent.config import cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


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
    raise RuntimeError(f"No available local port in range {base_port}..{base_port + tries - 1}")


def main(argv: list[str] | None = None) -> int:
    """Open the desktop product; the HTTP-only host is an explicit developer mode."""
    parser = argparse.ArgumentParser(description="Writing Agent Desktop")
    parser.add_argument("--web", action="store_true", help="Run the local service only (development)")
    args = parser.parse_args(argv)
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    if not args.web:
        try:
            from writing_agent.desktop_app import main as desktop_main
        except ModuleNotFoundError as exc:
            if not (exc.name or "").startswith("webview"):
                raise
            print("Desktop dependencies are missing. Run scripts/start_desktop.ps1 to install them.", file=sys.stderr)
            return 2
        return desktop_main([])

    errors = cfg.validate()
    if errors:
        for err in errors:
            logger.warning("Config warning: %s", err)
    cfg.log_summary()

    host = os.environ.get("WRITING_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("WRITING_AGENT_PORT", "8000"))
    port = _pick_available_port(host, port)

    import uvicorn

    uvicorn.run("writing_agent.web.app_v2:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
