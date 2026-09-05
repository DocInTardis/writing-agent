"""Preview and explicitly apply safe cleanup for legacy runtime artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

_ID_PATTERN = re.compile(r"[A-Za-z0-9_]+_sha256_[0-9a-f]{64}|[A-Za-z0-9_-]{8,}")
_MAX_REFERENCE_FILE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class CleanupCandidate:
    kind: str
    path: str
    age_days: float
    size_bytes: int
    reason: str


def _data_root(value: Path | str | None = None) -> Path:
    if value is not None:
        return Path(value).resolve()
    configured = str(os.environ.get("WRITING_AGENT_DATA_DIR", "") or "").strip()
    return Path(configured or ".data").resolve()


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _references(paths: Iterable[Path]) -> set[str]:
    found: set[str] = set()
    for path in paths:
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_REFERENCE_FILE_BYTES:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, TypeError):
            continue
        for value in _strings(payload):
            found.update(_ID_PATTERN.findall(value))
    return found


def _json_files(root: Path) -> Iterable[Path]:
    if not root.is_dir() or root.is_symlink():
        return ()
    return (path for path in root.rglob("*.json") if path.is_file() and not path.is_symlink())


def preview_cleanup(
    data_dir: Path | str | None = None,
    *,
    text_max_age_days: int = 30,
    checkpoint_max_age_days: int = 14,
    now: float | None = None,
) -> list[CleanupCandidate]:
    """Return old, unreferenced candidates without mutating the data directory."""
    root = _data_root(data_dir)
    current = time.time() if now is None else float(now)
    text_root = root / "text_store"
    checkpoint_root = root / "graph_checkpoints"
    workspace_files = tuple(_json_files(root / "workspaces"))
    checkpoint_files = tuple(_json_files(checkpoint_root))
    text_refs = _references((*workspace_files, *checkpoint_files))
    checkpoint_refs = _references(workspace_files)
    candidates: list[CleanupCandidate] = []

    if text_root.is_dir() and not text_root.is_symlink():
        for path in text_root.iterdir():
            if path.suffix not in {".txt", ".json"} or path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            age_days = max(0.0, (current - stat.st_mtime) / 86400)
            if age_days >= max(1, int(text_max_age_days)) and path.stem not in text_refs:
                candidates.append(
                    CleanupCandidate("text_block", str(path.resolve()), age_days, stat.st_size, "expired and unreferenced")
                )

    for path in checkpoint_files:
        try:
            stat = path.stat()
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, TypeError):
            continue
        saved_at = payload.get("saved_at") if isinstance(payload, dict) else None
        timestamp = float(saved_at) if isinstance(saved_at, (int, float)) else stat.st_mtime
        age_days = max(0.0, (current - timestamp) / 86400)
        run_id = str(payload.get("run_id") or path.stem) if isinstance(payload, dict) else path.stem
        if age_days >= max(1, int(checkpoint_max_age_days)) and run_id not in checkpoint_refs:
            candidates.append(
                CleanupCandidate("checkpoint", str(path.resolve()), age_days, stat.st_size, "expired and unreferenced")
            )

    return sorted(candidates, key=lambda item: (item.kind, item.path))


def apply_cleanup(candidates: Iterable[CleanupCandidate], data_dir: Path | str | None = None) -> list[str]:
    """Delete only validated preview candidates beneath the two managed artifact roots."""
    root = _data_root(data_dir)
    allowed = {(root / "text_store").resolve(), (root / "graph_checkpoints").resolve()}
    removed: list[str] = []
    for candidate in candidates:
        path = Path(candidate.path)
        try:
            resolved = path.resolve(strict=True)
            if path.is_symlink() or not path.is_file() or resolved.parent not in allowed:
                continue
            path.unlink()
            removed.append(str(resolved))
        except OSError:
            continue
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview old, unreferenced writing-agent artifacts")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--apply", action="store_true", help="delete only the candidates shown by this run")
    args = parser.parse_args()
    candidates = preview_cleanup(args.data_dir)
    removed = apply_cleanup(candidates, args.data_dir) if args.apply else []
    print(json.dumps({"apply": args.apply, "candidates": [asdict(item) for item in candidates], "removed": removed}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
