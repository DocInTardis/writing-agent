from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = [
    "writing_agent/web/services/generation_service.py",
    "writing_agent/web/services/generation_service_support.py",
    "writing_agent/web/services/generation_service_runtime.py",
    "writing_agent/v2/graph_section_continue_domain.py",
    "writing_agent/v2/graph_section_fill_domain.py",
    "writing_agent/v2/graph_section_draft_domain.py",
    "writing_agent/v2/graph_runner_rag_context_domain.py",
    "writing_agent/v2/graph_runner_title_domain.py",
    "writing_agent/v2/graph_runner_post_domain.py",
    "writing_agent/v2/graph_reference_domain.py",
    "writing_agent/v2/graph_reference_plan_domain.py",
    "writing_agent/v2/diagram_design.py",
    "writing_agent/v2/diagram_design_render_domain.py",
    "writing_agent/v2/figure_render.py",
    "writing_agent/document/v2_report_docx.py",
    "writing_agent/document/v2_report_docx_toc.py",
    "writing_agent/document/v2_report_docx_helpers.py",
    "writing_agent/document/v2_report_docx_content_helpers.py",
    "scripts/run_quality_suite.py",
]


def _tool_python() -> str:
    if sys.platform.startswith("win"):
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def _run(command: list[str]) -> None:
    print("$", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    python_exe = _tool_python()
    _run([python_exe, "-m", "py_compile", *DEFAULT_TARGETS])
    _run([python_exe, "-m", "ruff", "check", *DEFAULT_TARGETS])
    _run([python_exe, "-m", "vulture", *DEFAULT_TARGETS, "--min-confidence", "90"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
