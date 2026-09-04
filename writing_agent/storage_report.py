"""Read-only size inventory. Never follow links or inspect file contents."""
from __future__ import annotations

import argparse
import json
import os
import stat
from collections import defaultdict
from pathlib import Path


def classify(parts: tuple[str, ...]) -> str:
    # Data is protected, including caches whose ownership is not yet migrated.
    if parts[0] == '.data':
        return 'user_data_and_runtime_state'
    if parts[0] in {'deliverables', 'data'}:
        return 'user_outputs'
    if parts[0] == '.git':
        return 'version_history'
    if any(p == 'node_modules' or p.startswith('.venv') for p in parts):
        return 'development_and_runtime_dependencies'
    if any(p in {'__pycache__', '.pytest_cache', '.ruff_cache', '.tmp', '.vite'} for p in parts):
        return 'temporary_and_tool_cache'
    if any(p in {'target', 'dist', 'build'} for p in parts):
        return 'build_outputs_review_before_cleanup'
    return 'source_assets_and_other'


def inventory(root: Path) -> dict:
    root = root.absolute()
    errors: list[dict[str, str]] = []
    skipped: list[str] = []
    buckets = defaultdict(lambda: {'bytes': 0, 'files': 0})
    directories = defaultdict(lambda: {'bytes': 0, 'files': 0})

    def walk(directory: Path, parts: tuple[str, ...] = ()) -> None:
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    relative = (*parts, entry.name)
                    name = '/'.join(relative)
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                            skipped.append(name)
                        elif stat.S_ISDIR(info.st_mode):
                            walk(Path(entry.path), relative)
                        elif stat.S_ISREG(info.st_mode):
                            for bucket in (buckets[classify(relative)], directories[relative[0]]):
                                bucket['bytes'] += info.st_size
                                bucket['files'] += 1
                    except OSError as exc:
                        errors.append({'path': name, 'error': str(exc)})
        except OSError as exc:
            errors.append({'path': '/'.join(parts) or '.', 'error': str(exc)})

    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Inventory root must be a real directory, not a link or junction')
    walk(root)
    return {
        'root': str(root),
        'total_bytes': sum(item['bytes'] for item in buckets.values()),
        'categories': dict(sorted(buckets.items())),
        'top_level': dict(sorted(directories.items(), key=lambda item: item[1]['bytes'], reverse=True)),
        'skipped_links': sorted(skipped),
        'errors': errors,
        'note': 'Logical file sizes, not allocated disk space or installation size. Categories are not deletion permission.',
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        report = inventory(args.root)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'{exc}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
