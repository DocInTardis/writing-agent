"""Mcp Client module.

This module belongs to `writing_agent` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _encode(msg: Dict[str, Any]) -> bytes:
    raw = json.dumps(msg, ensure_ascii=False)
    payload = raw.encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    return header + payload


def _read_message(stdout) -> Optional[Dict[str, Any]]:
    headers: Dict[str, str] = {}
    while True:
        line = stdout.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        try:
            key, value = line.decode("ascii").split(":", 1)
            headers[key.strip().lower()] = value.strip()
        except Exception:
            continue
    length = int(headers.get("content-length", "0") or 0)
    if length <= 0:
        return None
    body = stdout.read(length)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


class McpClient:
    def __init__(self, cmd: list[str], *, env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None):
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=cwd,
        )
        self._next_id = 1

    def close(self) -> None:
        try:
            if self._proc.stdin:
                msg = {"jsonrpc": "2.0", "id": self._next_id, "method": "shutdown", "params": {}}
                self._proc.stdin.write(_encode(msg))
                self._proc.stdin.flush()
        except Exception:
            pass
        try:
            self._proc.terminate()
        except Exception:
            pass

    def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if self._proc.stdin is None or self._proc.stdout is None:
            return None
        req_id = self._next_id
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
        self._proc.stdin.write(_encode(msg))
        self._proc.stdin.flush()
        while True:
            resp = _read_message(self._proc.stdout)
            if resp is None:
                return None
            if resp.get("id") == req_id:
                return resp


def _default_cmd() -> list[str]:
    return [sys.executable, "-m", "writing_agent.mcp_ref_server"]


def _parse_cmd(raw: str) -> list[str]:
    if not raw:
        return _default_cmd()
    return shlex.split(raw, posix=os.name != "nt")


def fetch_mcp_resource(uri: str) -> Optional[Dict[str, Any]]:
    cmd = _parse_cmd(os.environ.get("WRITING_AGENT_MCP_REF_CMD", ""))
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(root))
    client = McpClient(cmd, env=env, cwd=str(root))
    try:
        client.request("initialize", {"clientInfo": {"name": "writing-agent", "version": "0.1.0"}})
        resp = client.request("resources/read", {"uri": uri})
        if not resp:
            return None
        return resp.get("result")
    finally:
        client.close()


def _first_content_text(result: Optional[Dict[str, Any]]) -> str:
    if not isinstance(result, dict):
        return ""
    contents = result.get("contents")
    if not isinstance(contents, list) or not contents:
        return ""
    item = contents[0] if isinstance(contents[0], dict) else None
    if not isinstance(item, dict):
        return ""
    return str(item.get("text") or "")


def fetch_mcp_json(uri: str) -> Optional[Any]:
    result = fetch_mcp_resource(uri)
    raw = _first_content_text(result)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None
