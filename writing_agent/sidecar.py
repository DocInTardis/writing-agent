"""Local-only HTTP sidecar used by the Tauri desktop shell."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _source_project_root() -> Path | None:
    if getattr(sys, "frozen", False):
        return None
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Writing Agent internal desktop service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("desktop sidecar only accepts a loopback host")

    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["WRITING_AGENT_DESKTOP"] = "1"
    os.environ.setdefault("WRITING_AGENT_PERF_MODE", "1")

    from writing_agent.desktop_paths import configure_desktop_environment

    configure_desktop_environment(project_root=_source_project_root())

    import uvicorn

    uvicorn.run(
        "writing_agent.web.app_v2:app",
        host=args.host,
        port=args.port,
        log_level="warning",
        access_log=False,
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
