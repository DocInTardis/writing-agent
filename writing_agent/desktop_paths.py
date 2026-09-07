"""Desktop-owned data/cache locations and conservative legacy migration."""

from __future__ import annotations

import json
import os
import shutil
import socket
import time
import uuid
from pathlib import Path


def _local_app_data() -> Path:
    configured = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
    if configured:
        return Path(configured)
    return Path.home() / ".local" / "share"


def desktop_data_dir() -> Path:
    configured = str(os.environ.get("WRITING_AGENT_DATA_DIR", "") or "").strip()
    return Path(configured).expanduser().resolve() if configured else (_local_app_data() / "WritingAgent" / "data").resolve()


def desktop_cache_dir() -> Path:
    configured = str(os.environ.get("WRITING_AGENT_CACHE_DIR", "") or "").strip()
    return Path(configured).expanduser().resolve() if configured else (_local_app_data() / "WritingAgent" / "cache").resolve()


def _legacy_candidates(project_root: Path | None) -> list[Path]:
    rows: list[Path] = []
    configured = str(os.environ.get("WRITING_AGENT_LEGACY_DATA_DIR", "") or "").strip()
    if configured:
        rows.append(Path(configured).expanduser().resolve())
    if project_root is not None:
        rows.append((project_root / ".data").resolve())
    cwd_candidate = (Path.cwd() / ".data").resolve()
    if cwd_candidate not in rows:
        rows.append(cwd_candidate)
    return rows


def _copy_tree_without_links(source: Path, target: Path) -> int:
    copied = 0
    for current, dirs, files in os.walk(source, followlinks=False):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]
        relative = current_path.relative_to(source)
        destination_dir = target / relative
        destination_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            src = current_path / name
            if src.is_symlink() or not src.is_file():
                continue
            dst = destination_dir / name
            if dst.exists():
                continue
            temp = destination_dir / f".{name}.{uuid.uuid4().hex}.migrating"
            try:
                shutil.copy2(src, temp, follow_symlinks=False)
                os.replace(temp, dst)
                copied += 1
            finally:
                temp.unlink(missing_ok=True)
    return copied


def migrate_legacy_data(target: Path, *, project_root: Path | None = None, wait_s: float = 15.0) -> dict:
    """Copy old project data once; never delete or overwrite the source.

    An exclusive marker provides cross-process serialization. Interrupted copies
    are safe to retry because every file is installed with an atomic replace.
    """

    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    marker = target / "migration-v1.json"
    if marker.is_file():
        return json.loads(marker.read_text(encoding="utf-8"))

    lock = target / ".migration-v1.lock"
    deadline = time.monotonic() + max(0.0, wait_s)
    lock_fd: int | None = None
    while lock_fd is None:
        try:
            lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, f"{os.getpid()}@{socket.gethostname()}".encode("utf-8", errors="replace"))
        except FileExistsError:
            if marker.is_file():
                return json.loads(marker.read_text(encoding="utf-8"))
            try:
                stale = (time.time() - lock.stat().st_mtime) > 600
            except OSError:
                stale = False
            if stale:
                lock.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                return {"status": "busy", "copied_files": 0}
            time.sleep(0.05)

    # Another process may have completed between our last marker check and
    # acquiring the lock. Do not replace its migration record with a zero-copy
    # result.
    if marker.is_file():
        result = json.loads(marker.read_text(encoding="utf-8"))
        os.close(lock_fd)
        lock_fd = None
        lock.unlink(missing_ok=True)
        return result

    try:
        copied = 0
        source_used = ""
        for source in _legacy_candidates(project_root):
            if source == target or not source.is_dir() or source.is_symlink():
                continue
            source_used = str(source)
            copied += _copy_tree_without_links(source, target)
            break
        result = {
            "status": "complete",
            "source": source_used,
            "copied_files": copied,
            "completed_at": int(time.time()),
        }
        temp_marker = target / f".migration-v1.{uuid.uuid4().hex}.tmp"
        temp_marker.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temp_marker, marker)
        return result
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        lock.unlink(missing_ok=True)


def configure_desktop_environment(*, project_root: Path | None = None) -> tuple[Path, Path]:
    data_dir = desktop_data_dir()
    cache_dir = desktop_cache_dir()
    migrate_legacy_data(data_dir, project_root=project_root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["WRITING_AGENT_DATA_DIR"] = str(data_dir)
    os.environ["WRITING_AGENT_CACHE_DIR"] = str(cache_dir)
    return data_dir, cache_dir
