"""Small bounded JSONL primitives for application-owned local records."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


def append_bounded_jsonl(path: Path, row: dict[str, Any], *, max_bytes: int) -> bool:
    limit = max(1, int(max_bytes))
    line = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(line) > limit:
        return False

    target = Path(path)
    temporary: Path | None = None
    try:
        with _LOCK:
            target.parent.mkdir(parents=True, exist_ok=True)
            size = target.stat().st_size if target.exists() else 0
            complete = True
            if size:
                with target.open("rb") as stream:
                    stream.seek(-1, os.SEEK_END)
                    complete = stream.read(1) == b"\n"
            if complete and size + len(line) <= limit:
                with target.open("ab") as stream:
                    stream.write(line)
                return True

            allowance = limit - len(line)
            tail = b""
            if allowance and target.exists():
                with target.open("rb") as stream:
                    offset = max(0, size - allowance)
                    stream.seek(offset)
                    tail = stream.read(allowance)
                if offset:
                    _, separator, tail = tail.partition(b"\n")
                    if not separator:
                        tail = b""
                if tail and not tail.endswith(b"\n"):
                    tail = tail[: tail.rfind(b"\n") + 1]

            with tempfile.NamedTemporaryFile(
                dir=target.parent,
                prefix=target.name + ".",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(tail + line)
            os.replace(temporary, target)
            temporary = None
            return True
    except (OSError, TypeError, ValueError):
        return False
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def read_recent_jsonl(path: Path, *, max_bytes: int, limit: int = 0) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        size = target.stat().st_size
        allowance = max(1, int(max_bytes))
        with target.open("rb") as stream:
            offset = max(0, size - allowance)
            stream.seek(offset)
            payload = stream.read(allowance)
        if offset:
            _, separator, payload = payload.partition(b"\n")
            if not separator:
                return []
    except OSError:
        return []

    rows: list[dict[str, Any]] = []
    for raw in payload.decode("utf-8", errors="replace").splitlines():
        try:
            item = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:] if limit > 0 else rows
