"""Opt-in, bounded diagnostic files; never use this for user documents or audit data.

Serializes writers within this process. Cross-process ownership is not provided.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_TRUE = {'1', 'true', 'yes', 'on'}


def enabled(feature: str) -> bool:
    return os.environ.get(feature, os.environ.get('WRITING_AGENT_PERSIST_DIAGNOSTICS', '0')).strip().lower() in _TRUE


def diagnostic_path(override: str, filename: str) -> Path:
    raw = os.environ.get(override, '').strip()
    if raw:
        return Path(raw)
    return Path(os.environ.get('WRITING_AGENT_DATA_DIR', '').strip() or '.data') / 'metrics' / filename


def append_diagnostic(path: Path, row: dict[str, Any], *, max_bytes: int = 2 * 1024 * 1024) -> bool:
    """Drop oversized rows; retain complete UTF-8 JSONL records within the limit.

An old oversized log is read only at its tail, not loaded wholesale. Failures to
write diagnostics must not turn a successful application operation into a failure.
"""
    temporary = None
    try:
        line = (json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
        if len(line) > max_bytes:
            return False
        with _LOCK:
            if path.is_symlink() or any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in path.parents):
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            size = path.stat().st_size if path.exists() else 0
            complete = True
            if size:
                with path.open('rb') as stream:
                    stream.seek(-1, os.SEEK_END)
                    complete = stream.read(1) == b'\n'
            if complete and size + len(line) <= max_bytes:
                with path.open('ab') as stream:
                    stream.write(line)
                return True
            allowance = max_bytes - len(line)
            tail = b''
            if allowance:
                with path.open('rb') as stream:
                    offset = max(0, size - allowance)
                    stream.seek(offset)
                    tail = stream.read(allowance)
                if offset:
                    _, separator, tail = tail.partition(b'\n')
                    if not separator:
                        tail = b''
                # Ignore a partial final row left by an interrupted legacy writer.
                if tail and not tail.endswith(b'\n'):
                    tail = tail[:tail.rfind(b'\n') + 1]
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(tail + line)
            os.replace(temporary, path)
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
