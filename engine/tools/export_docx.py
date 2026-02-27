import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from writing_agent.document.v2_report_docx import V2ReportDocxExporter, ExportPrefs
from writing_agent.models import FormattingRequirements


def main() -> int:
    if len(sys.argv) < 3:
        return 2
    json_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    if not json_path.exists():
        return 3
    try:
        raw = json_path.read_text(encoding="utf-8")
    except Exception:
        raw = json_path.read_text(encoding="utf-8-sig")
    if raw and raw[0] == "\ufeff":
        raw = raw.lstrip("\ufeff")
    data = json.loads(raw)
    text = data.get("text") or ""
    fmt = FormattingRequirements()
    prefs = ExportPrefs()
    exporter = V2ReportDocxExporter()
    payload = exporter.build_from_text(text, fmt, prefs)
    out_path.write_bytes(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
