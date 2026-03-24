"""Generation service helpers for document create/stream/revise flows.

This module keeps transport-level orchestration out of the FastAPI route layer and
contains request normalization, idempotency integration, generation shortcuts, and
targeted revision helpers used by the web workbench and automation scripts.
"""

# Revision prompt markers retained in service wrapper:
# <task>revise_full_document</task>
# <constraints>
# <revised_markdown>

from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import StreamingResponse

from writing_agent.web.idempotency import IdempotencyStore
from writing_agent.workflows import GenerateGraphRequest, run_generate_graph_with_fallback

from .base import app_v2_module
from .generation_service_runtime import (
    run_revision_request as _run_revision_request_impl,
    run_section_generation_request as _run_section_generation_request_impl,
)
from .generation_service_support import (
    build_confirmation_shortcut_result as _build_confirmation_shortcut_result_impl,
    build_generation_instruction as _build_generation_instruction_impl,
    build_revision_fallback_prompt as _build_revision_fallback_prompt_impl,
    build_shortcut_result as _build_shortcut_result_impl,
    compact_len as _compact_len_impl,
    extract_revision_fallback_text as _extract_revision_fallback_text_impl,
    fallback_normalize_heading_text as _fallback_normalize_heading_text_impl,
    load_idempotent_result as _load_idempotent_result_impl,
    load_plan_confirm_state as _load_plan_confirm_state_impl,
    normalize_plan_confirm_payload as _normalize_plan_confirm_payload_impl,
    parse_generate_payload as _parse_generate_payload_impl,
    prepare_generation_config as _prepare_generation_config_impl,
    resolve_idempotency_key as _resolve_idempotency_key_impl,
    resolve_target_section_selection as _resolve_target_section_selection_impl,
    revision_candidate_metrics as _revision_candidate_metrics_impl,
    save_idempotent_result as _save_idempotent_result_impl,
    save_plan_confirm_state as _save_plan_confirm_state_impl,
    strip_fences as _strip_fences_impl,
    validate_revision_candidate as _validate_revision_candidate_impl,
    xml_escape as _xml_escape_impl,
)


class GenerationService:
    """Service wrapper for generate and generate_stream endpoints."""

    def __init__(self) -> None:
        self._idempotency = IdempotencyStore()

    _xml_escape = staticmethod(_xml_escape_impl)
    _strip_fences = staticmethod(_strip_fences_impl)
    _fallback_normalize_heading_text = staticmethod(_fallback_normalize_heading_text_impl)
    _resolve_target_section_selection = staticmethod(_resolve_target_section_selection_impl)
    _build_revision_fallback_prompt = staticmethod(_build_revision_fallback_prompt_impl)
    _extract_revision_fallback_text = staticmethod(_extract_revision_fallback_text_impl)
    _compact_len = staticmethod(_compact_len_impl)
    _revision_candidate_metrics = staticmethod(_revision_candidate_metrics_impl)
    validate_revision_candidate = staticmethod(_validate_revision_candidate_impl)

    async def generate_stream(self, doc_id: str, request: Request) -> StreamingResponse:
        """Stream generation endpoint delegated to runtime implementation."""
        app_v2 = app_v2_module()
        return await app_v2.api_generate_stream(doc_id, request)

    async def generate(self, doc_id: str, request: Request) -> dict:
        """
        Non-SSE ??????
        1. ????????????????
        2. ???????????????????
        3. ????????????????????
        4. ????????????????????????
        5. ????????????????? graph + fallback?
        6. ???????????????????
        """
        app_v2 = app_v2_module()
        # ?? 1???????????????????
        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        prefs = dict(session.generation_prefs or {})
        touched_defaults = False
        if not str(prefs.get("quality_profile") or "").strip():
            prefs["quality_profile"] = "academic_cnki_default"
            touched_defaults = True
        for key, value in (("min_reference_count", 8), ("min_h2_count", 3), ("min_h3_count", 1)):
            try:
                current = int(prefs.get(key) or 0)
            except Exception:
                current = 0
            if current <= 0:
                prefs[key] = value
                touched_defaults = True
        if touched_defaults:
            session.generation_prefs = prefs
            app_v2.store.put(session)

        # ?? 2???????????????????
        data = await request.json()
        req = self._parse_generate_payload(app_v2, data, session=session)
        idempotency_key = self._resolve_idempotency_key(doc_id=doc_id, request=request, payload=data)
        cached = self._load_idempotent_result(idempotency_key)
        if cached is not None:
            return cached

        if not req["raw_instruction"]:
            raise app_v2.HTTPException(status_code=400, detail="instruction required")

        # ?? 3?????????????????????
        token = app_v2._try_begin_doc_generation_with_wait(doc_id, mode="generate")
        if not token:
            raise app_v2.HTTPException(status_code=409, detail=app_v2._generation_busy_message(doc_id))

        try:
            # ?? 4???????????????????????????
            compose_instruction = self._build_generation_instruction(
                app_v2=app_v2,
                session=session,
                raw_instruction=req["raw_instruction"],
                compose_mode=req["compose_mode"],
                resume_sections=req["resume_sections"],
                cursor_anchor=req["cursor_anchor"],
            )
            # overwrite ?????????????????????????????????
            base_text = "" if req["compose_mode"] == "overwrite" else (req["current_text"] or session.doc_text or "")
            if str((req.get("plan_confirm") or {}).get("decision") or "").strip().lower() == "interrupted":
                interrupted_result = {
                    "ok": 1,
                    "status": "interrupted",
                    "failure_reason": "plan_not_confirmed_by_user",
                    "quality_snapshot": {
                        "status": "interrupted",
                        "reason": "plan_not_confirmed_by_user",
                        "problem_count": 1,
                    },
                    "text": base_text,
                    "problems": ["plan_not_confirmed_by_user"],
                    "doc_ir": app_v2._safe_doc_ir_payload(base_text),
                    "plan_feedback": dict(req.get("plan_confirm") or {}),
                }
                self._save_idempotent_result(idempotency_key, interrupted_result)
                return interrupted_result

            # ?? 5?????????????????????
            shortcut, revision_meta = self._try_shortcuts(
                app_v2=app_v2,
                session=session,
                raw_instruction=req["raw_instruction"],
                compose_instruction=compose_instruction,
                compose_mode=req["compose_mode"],
                resume_sections=req["resume_sections"],
                selection_text=req["selection_text"],
                selection_payload=req["selection_payload"],
                context_policy=req["context_policy"],
                base_text=base_text,
                confirm_apply=req["confirm_apply"],
            )
            if shortcut is not None:
                if revision_meta and "revision_meta" not in shortcut:
                    shortcut["revision_meta"] = revision_meta
                self._save_idempotent_result(idempotency_key, shortcut)
                return shortcut

            # ?? 6???????????????????????
            ok, msg = app_v2._ensure_ollama_ready()
            if not ok:
                raise app_v2.HTTPException(status_code=400, detail=msg)

            # ?? 7??? graph ??????????????????????
            analysis_instruction, cfg, target_chars = self._prepare_generation_config(
                app_v2=app_v2,
                session=session,
                raw_instruction=req["raw_instruction"],
                compose_instruction=compose_instruction,
                resume_sections=req["resume_sections"],
                base_text=base_text,
            )

            # ?? 8??? graph ??????????? single-pass?
            final_text, problems, graph_meta = self._run_graph_with_fallback(
                app_v2=app_v2,
                session=session,
                instruction=analysis_instruction,
                raw_instruction=req["raw_instruction"],
                compose_mode=req["compose_mode"],
                resume_sections=req["resume_sections"],
                base_text=base_text,
                cfg=cfg,
                target_chars=target_chars,
                plan_confirm=req["plan_confirm"],
            )
            # ?? 9??????????????
            final_text = app_v2._postprocess_output_text(
                session,
                final_text,
                req["raw_instruction"],
                current_text=base_text,
                base_text=base_text,
            )
            app_v2._set_doc_text(session, final_text)
            app_v2._auto_commit_version(session, "auto: after update")
            app_v2.store.put(session)
            terminal_status = str((graph_meta or {}).get("terminal_status") or "success").strip().lower()
            if terminal_status not in {"success", "failed", "interrupted"}:
                terminal_status = "success"
            result = {
                "ok": 1,
                "status": terminal_status,
                "failure_reason": str((graph_meta or {}).get("failure_reason") or ""),
                "quality_snapshot": dict((graph_meta or {}).get("quality_snapshot") or {}),
                "text": final_text,
                "problems": problems,
                "doc_ir": app_v2._safe_doc_ir_payload(final_text),
            }
            if revision_meta:
                result["revision_meta"] = revision_meta
            if graph_meta:
                result["graph_meta"] = graph_meta
            self._save_idempotent_result(idempotency_key, result)
            return result
        finally:
            # ?? 10?????????????????????
            app_v2._finish_doc_generation(doc_id, token)

    def _parse_generate_payload(self, app_v2, data: dict, *, session=None) -> dict:
        return _parse_generate_payload_impl(
            app_v2,
            data,
            session=session,
            load_plan_confirm_state_fn=self._load_plan_confirm_state,
            normalize_plan_confirm_payload_fn=self._normalize_plan_confirm_payload,
        )

    _normalize_plan_confirm_payload = staticmethod(_normalize_plan_confirm_payload_impl)
    _load_plan_confirm_state = staticmethod(_load_plan_confirm_state_impl)
    _save_plan_confirm_state = staticmethod(_save_plan_confirm_state_impl)

    @staticmethod
    def _load_plan_confirm_state(app_v2, *, session) -> dict | None:
        if session is None:
            return None
        try:
            data = app_v2._get_internal_pref(session, "_wa_plan_confirm", {})  # type: ignore[attr-defined]
            return data if isinstance(data, dict) else None
        except Exception:
            prefs = session.generation_prefs if isinstance(getattr(session, "generation_prefs", None), dict) else {}
            value = prefs.get("_wa_plan_confirm") if isinstance(prefs, dict) else None
            return value if isinstance(value, dict) else None

    @staticmethod
    def _save_plan_confirm_state(app_v2, *, session, payload: dict) -> None:
        if session is None:
            return
        value = dict(payload or {})
        value["updated_at"] = time.time()
        try:
            app_v2._set_internal_pref(session, "_wa_plan_confirm", value)  # type: ignore[attr-defined]
        except Exception:
            prefs = dict(session.generation_prefs or {})
            prefs["_wa_plan_confirm"] = value
            session.generation_prefs = prefs
        app_v2.store.put(session)

    async def plan_confirm(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()
        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        data = await request.json()
        if not isinstance(data, dict):
            raise app_v2.HTTPException(status_code=400, detail="body must be object")
        payload = self._normalize_plan_confirm_payload(data)
        self._save_plan_confirm_state(app_v2, session=session, payload=payload)
        return {"ok": 1, "plan_confirm": payload}

    _resolve_idempotency_key = staticmethod(_resolve_idempotency_key_impl)

    def _load_idempotent_result(self, key: str) -> dict | None:
        return _load_idempotent_result_impl(self._idempotency, key)

    def _save_idempotent_result(self, key: str, payload: dict) -> None:
        _save_idempotent_result_impl(self._idempotency, key, payload)

    _build_generation_instruction = staticmethod(_build_generation_instruction_impl)

    def _try_shortcuts(
        self,
        *,
        app_v2,
        session,
        raw_instruction: str,
        compose_instruction: str,
        compose_mode: str,
        resume_sections: list[str],
        selection_text: str,
        selection_payload: object,
        context_policy: object | None,
        base_text: str,
        confirm_apply: bool,
    ) -> tuple[dict | None, dict | None]:
        """Shortcut branches before full graph generation."""
        revision_meta: dict | None = None
        format_only = app_v2._try_handle_format_only_request(
            session=session,
            instruction=raw_instruction,
            base_text=base_text,
            compose_mode=compose_mode,
            selection=selection_text,
        )
        if format_only is not None:
            return {"ok": 1, **format_only}, revision_meta

        quick_edit = None if resume_sections else app_v2._try_quick_edit(base_text, raw_instruction, confirm_apply)
        if quick_edit:
            if quick_edit.requires_confirmation:
                return self._build_confirmation_shortcut_result(
                    app_v2=app_v2,
                    base_text=base_text,
                    note=quick_edit.note,
                    confirmation_reason=quick_edit.confirmation_reason,
                    risk_level=quick_edit.risk_level,
                    source=quick_edit.source,
                    operations_count=quick_edit.operations_count,
                ), revision_meta
            out = self._build_shortcut_result(
                app_v2=app_v2,
                session=session,
                text=quick_edit.text,
                instruction=raw_instruction,
                base_text=base_text,
            )
            out["note"] = quick_edit.note
            return out, revision_meta

        analysis_quick = app_v2._run_message_analysis(session, compose_instruction, quick=True)
        ai_edit = None if resume_sections else app_v2._try_ai_intent_edit(base_text, raw_instruction, analysis_quick, confirm_apply)
        if ai_edit:
            if ai_edit.requires_confirmation:
                return self._build_confirmation_shortcut_result(
                    app_v2=app_v2,
                    base_text=base_text,
                    note=ai_edit.note,
                    confirmation_reason=ai_edit.confirmation_reason,
                    risk_level=ai_edit.risk_level,
                    source=ai_edit.source,
                    operations_count=ai_edit.operations_count,
                ), revision_meta
            out = self._build_shortcut_result(
                app_v2=app_v2,
                session=session,
                text=ai_edit.text,
                instruction=raw_instruction,
                base_text=base_text,
            )
            out["note"] = ai_edit.note
            return out, revision_meta

        if app_v2._should_route_to_revision(raw_instruction, base_text, analysis_quick):
            status: dict[str, object] = {}

            def _capture_revision_status(payload: dict[str, object]) -> None:
                if isinstance(payload, dict):
                    status.update(payload)

            revised = app_v2._try_revision_edit(
                session=session,
                instruction=raw_instruction,
                text=base_text,
                selection=selection_payload,
                analysis=analysis_quick,
                context_policy=context_policy,
                report_status=_capture_revision_status,
            )
            if status:
                revision_meta = dict(status)
            if revised:
                updated_text, _ = revised
                out = self._build_shortcut_result(
                    app_v2=app_v2,
                    session=session,
                    text=updated_text,
                    instruction=raw_instruction,
                    base_text=base_text,
                )
                if revision_meta:
                    out["revision_meta"] = revision_meta
                return out, revision_meta

        if app_v2._should_use_fast_generate(
            raw_instruction,
            app_v2._resolve_target_chars(session.formatting or {}, session.generation_prefs or {}),
            session.generation_prefs or {},
        ):
            try:
                instruction = app_v2._augment_instruction(
                    compose_instruction,
                    formatting=session.formatting or {},
                    generation_prefs=session.generation_prefs or {},
                )
                final_text = app_v2._single_pass_generate(
                    session,
                    instruction=instruction,
                    current_text=base_text,
                    target_chars=app_v2._resolve_target_chars(session.formatting or {}, session.generation_prefs or {}),
                )
                if final_text and not app_v2._looks_like_prompt_echo(final_text, raw_instruction):
                    out = self._build_shortcut_result(
                        app_v2=app_v2,
                        session=session,
                        text=final_text,
                        instruction=raw_instruction,
                        base_text=base_text,
                    )
                    return out, revision_meta
            except Exception:
                pass

        return None, revision_meta

    _build_shortcut_result = staticmethod(_build_shortcut_result_impl)

    _build_confirmation_shortcut_result = staticmethod(_build_confirmation_shortcut_result_impl)

    _prepare_generation_config = staticmethod(_prepare_generation_config_impl)

    def _run_graph_with_fallback(
        self,
        *,
        app_v2,
        session,
        instruction: str,
        raw_instruction: str,
        compose_mode: str,
        resume_sections: list[str],
        base_text: str,
        cfg,
        target_chars: int,
        plan_confirm: dict,
    ) -> tuple[str, list[str], dict | None]:
        return run_generate_graph_with_fallback(
            request=GenerateGraphRequest(
                app_v2=app_v2,
                session=session,
                instruction=instruction,
                raw_instruction=raw_instruction,
                compose_mode=compose_mode,
                resume_sections=resume_sections,
                base_text=base_text,
                cfg=cfg,
                target_chars=target_chars,
                plan_confirm=plan_confirm,
            )
        )

    async def generate_section(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()
        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")

        data = await request.json()
        return _run_section_generation_request_impl(app_v2=app_v2, session=session, data=data)

    async def revise_doc(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()
        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")

        data = await request.json()
        return _run_revision_request_impl(
            app_v2=app_v2,
            session=session,
            data=data,
            fallback_normalize_heading_text_fn=self._fallback_normalize_heading_text,
            resolve_target_section_selection_fn=self._resolve_target_section_selection,
            build_revision_fallback_prompt_fn=self._build_revision_fallback_prompt,
            extract_revision_fallback_text_fn=self._extract_revision_fallback_text,
            validate_revision_candidate_fn=self.validate_revision_candidate,
        )
