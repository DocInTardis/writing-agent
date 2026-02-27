"""Ui Content Validation Multiround Adapter command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

from typing import Any, Dict

from playwright.sync_api import Page


def run_multiround_case(
    page: Page,
    base_url: str,
    case: Dict[str, Any],
    cfg,
    artifacts_root,
) -> Dict[str, Any]:
    from scripts import ui_content_validation_runner as runner
    from scripts.ui_content_validation_rounds import run_multiround_case as _impl

    return _impl(
        page,
        base_url,
        case,
        cfg,
        artifacts_root,
        case_artifact_dir=runner.case_artifact_dir,
        open_new_case_page=runner.open_new_case_page,
        get_ui_state=runner.get_ui_state,
        build_round_instruction=runner.build_round_instruction,
        run_generation_with_retry=runner.run_generation_with_retry,
        check_keep_and_change=runner.check_keep_and_change,
        evaluate_acceptance=runner.evaluate_acceptance,
        should_try_round_acceptance_repair=runner.should_try_round_acceptance_repair,
        build_round_acceptance_repair_prompt=runner.build_round_acceptance_repair_prompt,
        _status_indicates_failure=runner._status_indicates_failure,
        _status_indicates_busy=runner._status_indicates_busy,
        save_failure_screenshot=runner.save_failure_screenshot,
        save_text_snapshot=runner.save_text_snapshot,
        compact_len=runner.compact_len,
        should_export_docx=runner.should_export_docx,
        is_format_sensitive_case=runner.is_format_sensitive_case,
        fetch_export_precheck=runner.fetch_export_precheck,
        classify_precheck_warnings=runner.classify_precheck_warnings,
        export_docx_if_requested=runner.export_docx_if_requested,
        probe_docx_download_headers=runner.probe_docx_download_headers,
        validate_docx_style_conformance=runner.validate_docx_style_conformance,
    )
