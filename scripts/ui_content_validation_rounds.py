"""Ui Content Validation Rounds command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from playwright.sync_api import Page


def run_multiround_case(
    page: Page,
    base_url: str,
    case: Dict[str, Any],
    cfg,
    artifacts_root: Path,
    *,
    case_artifact_dir,
    open_new_case_page,
    get_ui_state,
    build_round_instruction,
    run_generation_with_retry,
    check_keep_and_change,
    evaluate_acceptance,
    should_try_round_acceptance_repair,
    build_round_acceptance_repair_prompt,
    _status_indicates_failure,
    _status_indicates_busy,
    save_failure_screenshot,
    save_text_snapshot,
    compact_len,
    should_export_docx,
    is_format_sensitive_case,
    fetch_export_precheck,
    classify_precheck_warnings,
    export_docx_if_requested,
    probe_docx_download_headers,
    validate_docx_style_conformance,
) -> Dict[str, Any]:
    case_id = str(case.get("id", "mr-unknown"))
    artifact_dir = case_artifact_dir(artifacts_root, case_id)
    started_at = time.time()
    errors = []
    warnings = []
    round_results = []

    doc_id = open_new_case_page(page, base_url)
    current_text = str(get_ui_state(page).get("sourceText", ""))

    for r in case.get("rounds", []):
        round_no = int(r.get("round", len(round_results) + 1))
        round_input = str(r.get("round_input", "")).strip()
        round_input_with_constraints = build_round_instruction(
            round_input,
            r.get("acceptance_checks", {}) or {},
            r.get("must_keep", []) or [],
            r.get("must_change", []) or [],
        )
        round_start = time.time()

        generation = run_generation_with_retry(page, round_input_with_constraints, cfg, retries=2)
        cycle = generation["cycle"]
        post = generation["post"]
        post_text = str(post.get("sourceText", ""))
        post_status = str(post.get("docStatus", ""))
        generation_failed = _status_indicates_failure(post_status)
        conflict_409 = _status_indicates_busy(post_status)

        keep_change = check_keep_and_change(
            post_text,
            current_text,
            r.get("must_keep", []) or [],
            r.get("must_change", []) or [],
        )
        acceptance = evaluate_acceptance(post_text, r.get("acceptance_checks", {}) or {})
        repair_prompt = ""
        if (not acceptance.get("passed")) and should_try_round_acceptance_repair(acceptance):
            for _repair_round in range(3):
                repair_prompt = build_round_instruction(
                    build_round_acceptance_repair_prompt(
                        r.get("acceptance_checks", {}) or {},
                        acceptance,
                        r.get("must_keep", []) or [],
                        r.get("must_change", []) or [],
                    ),
                    r.get("acceptance_checks", {}) or {},
                    r.get("must_keep", []) or [],
                    r.get("must_change", []) or [],
                )
                generation_fix = run_generation_with_retry(page, repair_prompt, cfg, retries=2)
                cycle_fix = generation_fix["cycle"]
                post_fix = generation_fix["post"]
                post_text_fix = str(post_fix.get("sourceText", ""))
                keep_change_fix = check_keep_and_change(
                    post_text_fix,
                    current_text,
                    r.get("must_keep", []) or [],
                    r.get("must_change", []) or [],
                )
                acceptance_fix = evaluate_acceptance(post_text_fix, r.get("acceptance_checks", {}) or {})
                old_fail_count = len(acceptance.get("failures") or [])
                new_fail_count = len(acceptance_fix.get("failures") or [])
                old_char = int(acceptance.get("char_count") or 0)
                new_char = int(acceptance_fix.get("char_count") or 0)
                improved = bool(acceptance_fix.get("passed")) or (new_fail_count < old_fail_count) or (
                    new_fail_count == old_fail_count and new_char > (old_char + 40)
                )
                if improved:
                    generation = generation_fix
                    cycle = cycle_fix
                    post = post_fix
                    post_text = post_text_fix
                    post_status = str(post.get("docStatus", ""))
                    keep_change = keep_change_fix
                    acceptance = acceptance_fix
                if acceptance.get("passed"):
                    break

        round_errors = []
        constraint_warnings = []
        soft_success = bool(acceptance.get("passed")) and bool(post_text.strip())
        if generation_failed and not (conflict_409 and post_text.strip()) and not soft_success:
            round_errors.append(f"generation_status={post_status}")
        if cycle.get("timed_out") and not (conflict_409 and post_text.strip()) and not soft_success:
            round_errors.append("generation_timeout")
        if not cycle.get("started"):
            round_errors.append("generation_not_started")
        if not cycle.get("finished") and not (conflict_409 and post_text.strip()) and not soft_success:
            round_errors.append("generation_not_finished")
        if not keep_change.get("passed"):
            constraint_warnings.extend([f"round_constraint:{x}" for x in keep_change.get("failures", [])])
        if not acceptance.get("passed"):
            round_errors.extend([f"acceptance:{x}" for x in acceptance.get("failures", [])])

        round_passed = len(round_errors) == 0
        if not round_passed:
            save_failure_screenshot(page, artifact_dir / f"round_{round_no:02d}_failure.png")
            errors.extend([f"round_{round_no}:{msg}" for msg in round_errors])

        round_snapshot = save_text_snapshot(
            artifact_dir=artifact_dir,
            file_name=f"round_{round_no:02d}.md",
            title=f"{case_id} Round {round_no}",
            text=post_text,
            meta={
                "mode": "multiround",
                "round": round_no,
                "doc_id": doc_id,
                "char_count": compact_len(post_text),
            },
        )
        if not round_snapshot.get("ok"):
            msg = f"text_snapshot_failed:{round_snapshot.get('error')}"
            constraint_warnings.append(msg)
            warnings.append(f"round_{round_no}:{msg}")

        round_results.append(
            {
                "round": round_no,
                "input_preview": round_input[:220],
                "duration_s": round(time.time() - round_start, 2),
                "attempts": int(generation.get("attempts", 1)),
                "repair_prompt": repair_prompt,
                "passed": round_passed,
                "errors": round_errors,
                "warnings": constraint_warnings,
                "stage_checks": {
                    "generation_started": bool(cycle.get("started")),
                    "generation_finished": bool(cycle.get("finished")),
                    "generation_timed_out": bool(cycle.get("timed_out")),
                    "content_changed": bool(keep_change.get("content_changed")),
                },
                "status": {
                    "doc_status": str(post.get("docStatus", "")),
                    "flow_status": str(post.get("flowStatus", "")),
                    "char_count": compact_len(post_text),
                },
                "text_preview": post_text[:300],
                "keep_change": keep_change,
                "acceptance": acceptance,
                "trace": cycle.get("trace", []),
                "text_snapshot": round_snapshot,
            }
        )
        current_text = post_text

    final_snapshot = save_text_snapshot(
        artifact_dir=artifact_dir,
        file_name=f"{case_id}.md",
        title=case_id,
        text=current_text,
        meta={
            "mode": "multiround",
            "group": str(case.get("group", "")),
            "doc_id": doc_id,
            "char_count": compact_len(current_text),
            "round_count": len(round_results),
        },
    )
    if not final_snapshot.get("ok"):
        warnings.append(f"text_snapshot_failed:{final_snapshot.get('error')}")

    export_result = None
    export_precheck = None
    export_provenance = None
    docx_style_check = None
    if should_export_docx(case, cfg):
        format_sensitive = is_format_sensitive_case(case)
        export_precheck = fetch_export_precheck(base_url, doc_id)
        if not export_precheck.get("ok"):
            errors.append(f"docx_precheck_failed:{export_precheck.get('error') or 'precheck_not_ok'}")
        else:
            if export_precheck.get("can_export") is False:
                issues = ",".join(export_precheck.get("issues") or []) or "blocked"
                errors.append(f"docx_precheck_blocked:{issues}")
            pre_warn = export_precheck.get("warnings") or []
            if pre_warn:
                classified = classify_precheck_warnings([str(x) for x in pre_warn])
                blocking_warn = classified.get("blocking") or []
                non_blocking_warn = classified.get("non_blocking") or []
                if blocking_warn:
                    errors.append("docx_precheck_warning:" + ",".join([str(x) for x in blocking_warn[:6]]))
                if non_blocking_warn:
                    warnings.append("docx_precheck_warning_non_blocking:" + ",".join([str(x) for x in non_blocking_warn[:6]]))
        export_result = export_docx_if_requested(page, artifact_dir, case_id, fallback_text=current_text)
        if not export_result.get("ok"):
            errors.append(f"docx_export_failed:{export_result.get('error')}")
        else:
            if format_sensitive and str(export_result.get("method") or "") == "local_text_fallback":
                errors.append("docx_export_method_not_allowed:local_text_fallback")
            export_provenance = probe_docx_download_headers(base_url, doc_id)
            if export_provenance.get("ok"):
                export_result["provenance"] = export_provenance
                backend = str(export_provenance.get("export_backend") or "").strip()
                if backend:
                    export_result["backend"] = backend
                warn = str(export_provenance.get("warn") or "").strip()
                if warn:
                    errors.append(f"docx_compat_warning:{warn}")
            else:
                warnings.append(f"docx_provenance_probe_failed:{export_provenance.get('error')}")
            docx_path_raw = str(export_result.get("path") or "").strip()
            if docx_path_raw:
                docx_style_check = validate_docx_style_conformance(Path(docx_path_raw), format_sensitive=format_sensitive)
                export_result["style_check"] = docx_style_check
                if not docx_style_check.get("passed"):
                    errors.extend([f"docx_style:{x}" for x in (docx_style_check.get("failures") or [])])

    passed = len(errors) == 0
    if not passed:
        save_failure_screenshot(page, artifact_dir / "failure.png")

    return {
        "id": case_id,
        "title": case.get("title", ""),
        "group": case.get("group", ""),
        "mode": "multiround",
        "doc_id": doc_id,
        "duration_s": round(time.time() - started_at, 2),
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "rounds": round_results,
        "artifact_dir": str(artifact_dir),
        "text_snapshot": final_snapshot,
        "docx_export": export_result,
        "export_precheck": export_precheck,
        "docx_provenance": export_provenance,
        "docx_style_check": docx_style_check,
    }
