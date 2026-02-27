import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from writing_agent.v2.rag.user_library import _extract_text  # noqa


def main() -> int:
    if len(sys.argv) < 2:
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        return 3
    text = _extract_text(path) or ""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.write(text)
    except Exception:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
