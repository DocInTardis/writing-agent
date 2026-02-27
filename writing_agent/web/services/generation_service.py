"""Generation Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import StreamingResponse

from writing_agent.web.idempotency import IdempotencyStore, make_idempotency_key

from .base import app_v2_module


class GenerationService:
    """Service wrapper for generation and stream endpoints."""

    def __init__(self) -> None:
        self._idempotency = IdempotencyStore()

    async def generate_stream(self, doc_id: str, request: Request) -> StreamingResponse:
        """Proxy streaming generation to the legacy runtime implementation."""
        app_v2 = app_v2_module()
        return await app_v2.api_generate_stream(doc_id, request)

    async def generate(self, doc_id: str, request: Request) -> dict:
        """
        Run generation flow with idempotency, lock control, and fallback strategies.

        The method keeps existing behavior by delegating model/runtime details to
        `app_v2` while isolating request parsing and shortcut branches in this service.
        """
        app_v2 = app_v2_module()
        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")

        data = await request.json()
        req = self._parse_generate_payload(app_v2, data)
        idempotency_key = self._resolve_idempotency_key(doc_id=doc_id, request=request, payload=data)
        cached = self._load_idempotent_result(idempotency_key)
        if cached is not None:
            return cached

        if not req["raw_instruction"]:
            raise app_v2.HTTPException(status_code=400, detail="instruction required")

        token = app_v2._try_begin_doc_generation_with_wait(doc_id, mode="generate")
        if not token:
            raise app_v2.HTTPException(status_code=409, detail=app_v2._generation_busy_message(doc_id))

        try:
            compose_instruction = self._build_generation_instruction(
                app_v2=app_v2,
                session=session,
                raw_instruction=req["raw_instruction"],
                compose_mode=req["compose_mode"],
                resume_sections=req["resume_sections"],
                cursor_anchor=req["cursor_anchor"],
            )
            base_text = "" if req["compose_mode"] == "overwrite" else (req["current_text"] or session.doc_text or "")

            shortcut = self._try_shortcuts(
                app_v2=app_v2,
                session=session,
                raw_instruction=req["raw_instruction"],
                compose_instruction=compose_instruction,
                compose_mode=req["compose_mode"],
                resume_sections=req["resume_sections"],
                selection=req["selection"],
                base_text=base_text,
            )
            if shortcut is not None:
                self._save_idempotent_result(idempotency_key, shortcut)
                return shortcut

            ok, msg = app_v2._ensure_ollama_ready()
            if not ok:
                raise app_v2.HTTPException(status_code=400, detail=msg)

            analysis_instruction, cfg, target_chars = self._prepare_generation_config(
                app_v2=app_v2,
                session=session,
                raw_instruction=req["raw_instruction"],
                compose_instruction=compose_instruction,
                resume_sections=req["resume_sections"],
                base_text=base_text,
            )

            final_text, problems = self._run_graph_with_fallback(
                app_v2=app_v2,
                session=session,
                instruction=analysis_instruction,
                raw_instruction=req["raw_instruction"],
                resume_sections=req["resume_sections"],
                base_text=base_text,
                cfg=cfg,
                target_chars=target_chars,
            )
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
            result = {"ok": 1, "text": final_text, "problems": problems, "doc_ir": app_v2._safe_doc_ir_payload(final_text)}
            self._save_idempotent_result(idempotency_key, result)
            return result
        finally:
            app_v2._finish_doc_generation(doc_id, token)

    def _parse_generate_payload(self, app_v2, data: dict) -> dict:
        """Normalize request payload into an internal generation request shape."""
        return {
            "raw_instruction": str(data.get("instruction") or "").strip(),
            "current_text": str(data.get("text") or ""),
            "selection": str(data.get("selection") or ""),
            "compose_mode": app_v2._normalize_compose_mode(data.get("compose_mode")),
            "resume_sections": app_v2._normalize_resume_sections(data.get("resume_sections")),
            "cursor_anchor": str(data.get("cursor_anchor") or ""),
        }

    def _resolve_idempotency_key(self, *, doc_id: str, request: Request, payload: dict) -> str:
        """Prefer caller-provided idempotency key, otherwise derive a deterministic key."""
        header_key = str(request.headers.get("x-idempotency-key") or "").strip()
        if header_key:
            return header_key
        return make_idempotency_key(doc_id=doc_id, route="generate", body=payload)

    def _load_idempotent_result(self, key: str) -> dict | None:
        cached = self._idempotency.get(key)
        if not isinstance(cached, dict):
            return None
        payload = cached.get("payload")
        return payload if isinstance(payload, dict) and payload.get("ok") else None

    def _save_idempotent_result(self, key: str, payload: dict) -> None:
        if not isinstance(payload, dict) or not payload.get("ok"):
            return
        self._idempotency.put(key, payload)

    def _build_generation_instruction(
        self,
        *,
        app_v2,
        session,
        raw_instruction: str,
        compose_mode: str,
        resume_sections: list[str],
        cursor_anchor: str,
    ) -> str:
        """Compose a final instruction string based on mode and resume settings."""
        has_existing = bool(str(session.doc_text or "").strip())
        instruction = app_v2._apply_compose_mode_instruction(raw_instruction, compose_mode, has_existing=has_existing)
        if resume_sections:
            instruction = app_v2._apply_resume_sections_instruction(
                instruction,
                resume_sections,
                cursor_anchor=cursor_anchor,
            )
        return instruction

    def _try_shortcuts(
        self,
        *,
        app_v2,
        session,
        raw_instruction: str,
        compose_instruction: str,
        compose_mode: str,
        resume_sections: list[str],
        selection: str,
        base_text: str,
    ) -> dict | None:
        """Try low-latency edit/generation shortcuts before full graph execution."""
        format_only = app_v2._try_handle_format_only_request(
            session=session,
            instruction=raw_instruction,
            base_text=base_text,
            compose_mode=compose_mode,
            selection=selection,
        )
        if format_only is not None:
            return {"ok": 1, **format_only}

        if base_text.strip():
            if base_text != session.doc_text:
                app_v2._set_doc_text(session, base_text)
            app_v2._auto_commit_version(session, "auto: before update")

        quick_edit = None if resume_sections else app_v2._try_quick_edit(base_text, raw_instruction)
        if quick_edit:
            updated_text, _ = quick_edit
            return self._build_shortcut_result(
                app_v2=app_v2,
                session=session,
                text=updated_text,
                instruction=raw_instruction,
                base_text=base_text,
            )

        analysis_quick = app_v2._run_message_analysis(session, compose_instruction, quick=True)
        ai_edit = None if resume_sections else app_v2._try_ai_intent_edit(base_text, raw_instruction, analysis_quick)
        if ai_edit:
            updated_text, note = ai_edit
            out = self._build_shortcut_result(
                app_v2=app_v2,
                session=session,
                text=updated_text,
                instruction=raw_instruction,
                base_text=base_text,
            )
            out["note"] = note
            return out

        if app_v2._should_route_to_revision(raw_instruction, base_text, analysis_quick):
            revised = app_v2._try_revision_edit(
                session=session,
                instruction=raw_instruction,
                text=base_text,
                selection=selection,
                analysis=analysis_quick,
            )
            if revised:
                updated_text, _ = revised
                return self._build_shortcut_result(
                    app_v2=app_v2,
                    session=session,
                    text=updated_text,
                    instruction=raw_instruction,
                    base_text=base_text,
                )

        if app_v2._should_use_fast_generate(raw_instruction, app_v2._resolve_target_chars(session.formatting or {}, session.generation_prefs or {}), session.generation_prefs or {}):
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
                    return self._build_shortcut_result(
                        app_v2=app_v2,
                        session=session,
                        text=final_text,
                        instruction=raw_instruction,
                        base_text=base_text,
                    )
            except Exception:
                pass

        return None

    def _build_shortcut_result(self, *, app_v2, session, text: str, instruction: str, base_text: str) -> dict:
        updated_text = app_v2._postprocess_output_text(
            session,
            text,
            instruction,
            current_text=base_text,
            base_text=base_text,
        )
        app_v2._set_doc_text(session, updated_text)
        app_v2._auto_commit_version(session, "auto: after update")
        app_v2.store.put(session)
        return {"ok": 1, "text": updated_text, "problems": [], "doc_ir": app_v2._safe_doc_ir_payload(updated_text)}

    def _prepare_generation_config(self, *, app_v2, session, raw_instruction: str, compose_instruction: str, resume_sections: list[str], base_text: str):
        """Build analysis instruction and runtime config for the graph path."""
        analysis_timeout = float(app_v2.os.environ.get("WRITING_AGENT_ANALYSIS_MAX_S", "20"))
        analysis = app_v2._run_with_timeout(
            lambda: app_v2._run_message_analysis(session, compose_instruction),
            analysis_timeout,
            app_v2._normalize_analysis({}, compose_instruction),
        )
        analysis_instruction = app_v2._compose_analysis_input(compose_instruction, analysis)
        instruction = app_v2._augment_instruction(
            analysis_instruction,
            formatting=session.formatting or {},
            generation_prefs=session.generation_prefs or {},
        )

        if (not resume_sections) and (not session.template_required_h2) and (not session.template_outline):
            auto_outline = app_v2._default_outline_from_instruction(raw_instruction)
            if auto_outline:
                session.template_required_h2 = auto_outline
                app_v2.store.put(session)

        target_chars = app_v2._resolve_target_chars(session.formatting or {}, session.generation_prefs or {})
        if target_chars <= 0:
            target_chars = app_v2._extract_target_chars_from_instruction(raw_instruction)
        if target_chars > 0:
            raw_margin = app_v2.os.environ.get("WRITING_AGENT_TARGET_MARGIN", "").strip()
            try:
                margin = float(raw_margin) if raw_margin else 0.15
            except Exception:
                margin = 0.15
            margin = max(0.0, min(0.3, margin))
            internal_target = int(round(target_chars * (1.0 + margin)))
            cfg = app_v2.GenerateConfig(
                workers=int(app_v2.os.environ.get("WRITING_AGENT_WORKERS", "12")),
                min_total_chars=internal_target,
                max_total_chars=internal_target,
            )
        else:
            cfg = app_v2.GenerateConfig(workers=int(app_v2.os.environ.get("WRITING_AGENT_WORKERS", "12")))
        return instruction, cfg, target_chars

    def _run_graph_with_fallback(
        self,
        *,
        app_v2,
        session,
        instruction: str,
        raw_instruction: str,
        resume_sections: list[str],
        base_text: str,
        cfg,
        target_chars: int,
    ) -> tuple[str, list[str]]:
        """Execute graph generation and fallback paths until a valid final text is produced."""
        required_h2 = list(resume_sections) if resume_sections else list(session.template_required_h2 or [])
        required_outline = [] if resume_sections else list(session.template_outline or [])

        final_text: str | None = None
        problems: list[str] = []
        try:
            expand_outline = bool((session.generation_prefs or {}).get("expand_outline", False))
            gen = app_v2.run_generate_graph(
                instruction=instruction,
                current_text=base_text,
                required_h2=required_h2,
                required_outline=required_outline,
                expand_outline=expand_outline,
                config=cfg,
            )
            stall_s = float(
                app_v2.os.environ.get(
                    "WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S",
                    app_v2.os.environ.get("WRITING_AGENT_STREAM_EVENT_TIMEOUT_S", "90"),
                )
            )
            overall_s = float(
                app_v2.os.environ.get(
                    "WRITING_AGENT_NONSTREAM_MAX_S",
                    app_v2.os.environ.get("WRITING_AGENT_STREAM_MAX_S", "180"),
                )
            )
            for ev in app_v2._iter_with_timeout(gen, per_event=stall_s, overall=overall_s):
                if ev.get("event") == "final":
                    final_text = str(ev.get("text") or "")
                    problems = list(ev.get("problems") or [])
                    break
        except Exception as e:
            try:
                final_text = app_v2._single_pass_generate(
                    session,
                    instruction=instruction,
                    current_text=base_text,
                    target_chars=target_chars,
                )
            except Exception as ee:
                raise app_v2.HTTPException(status_code=500, detail=f"generation failed: {e}; fallback failed: {ee}") from ee

        if not final_text or len(str(final_text).strip()) < 20:
            try:
                final_text = app_v2._single_pass_generate(
                    session,
                    instruction=instruction,
                    current_text=base_text,
                    target_chars=target_chars,
                )
            except Exception as e:
                raise app_v2.HTTPException(status_code=500, detail=f"generation produced insufficient text: {e}") from e

        return str(final_text), problems

    async def generate_section(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()
        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")

        data = await request.json()
        section = str(data.get("section") or "").strip()
        if not section:
            raise app_v2.HTTPException(status_code=400, detail="section required")

        instruction = str(data.get("instruction") or "").strip() or (session.last_instruction or "")
        current_text = session.doc_text or ""
        cfg = app_v2.GenerateConfig(workers=1, min_total_chars=0, max_total_chars=0)
        final_text: str | None = None
        try:
            gen = app_v2.run_generate_graph(
                instruction=instruction,
                current_text=current_text,
                required_h2=[section],
                required_outline=[],
                expand_outline=False,
                config=cfg,
            )
            for ev in gen:
                if ev.get("event") == "final":
                    final_text = str(ev.get("text") or "")
                    break
        except Exception as e:
            raise app_v2.HTTPException(status_code=500, detail=f"section generation failed: {e}")

        if not final_text:
            raise app_v2.HTTPException(status_code=500, detail="section generation produced no text")

        try:
            from writing_agent.v2.graph_runner import _apply_section_updates  # type: ignore

            updated = _apply_section_updates(current_text, final_text, [section])
        except Exception:
            updated = final_text

        app_v2._set_doc_text(session, updated)
        app_v2.store.put(session)
        final_doc_ir = session.doc_ir if isinstance(getattr(session, "doc_ir", None), dict) else app_v2._safe_doc_ir_payload(updated)
        return {"ok": 1, "text": updated, "doc_ir": final_doc_ir}

    async def revise_doc(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()
        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")

        data = await request.json()
        instruction = str(data.get("instruction") or "").strip()
        selection = str(data.get("selection") or "").strip()
        incoming_ir = data.get("doc_ir")
        if isinstance(incoming_ir, dict) and incoming_ir.get("sections") is not None:
            try:
                session.doc_ir = incoming_ir
                text = app_v2.doc_ir_to_text(app_v2.doc_ir_from_dict(session.doc_ir))
            except Exception:
                text = str(data.get("text") or session.doc_text or "")
        else:
            text = str(data.get("text") or session.doc_text or "")

        base_text = text
        if not instruction:
            raise app_v2.HTTPException(status_code=400, detail="instruction required")
        if not text.strip():
            raise app_v2.HTTPException(status_code=400, detail="empty document")

        settings = app_v2.get_ollama_settings()
        if not settings.enabled:
            raise app_v2.HTTPException(status_code=400, detail="Ollama is not enabled")
        if not app_v2.OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s).is_running():
            raise app_v2.HTTPException(status_code=400, detail="Ollama is not running")

        analysis = app_v2._run_message_analysis(session, instruction)
        analysis_instruction = str(analysis.get("rewritten_query") or instruction).strip() or instruction
        model = app_v2.os.environ.get("WRITING_AGENT_REVISE_MODEL", "").strip() or settings.model
        client = app_v2.OllamaClient(base_url=settings.base_url, model=model, timeout_s=settings.timeout_s)

        decision = app_v2._revision_decision_with_model(
            base_url=settings.base_url,
            model=model,
            instruction=analysis_instruction,
            selection=selection,
            text=text,
        )
        if isinstance(decision, dict) and decision.get("should_apply") is False:
            return {"ok": 1, "text": text}

        plan_steps = []
        if isinstance(decision, dict):
            plan_steps = [str(x).strip() for x in (decision.get("plan") or []) if str(x).strip()]
        plan_hint = ""
        if plan_steps:
            plan_hint = "淇璁″垝:\n- " + "\n- ".join(plan_steps) + "\n\n"

        if selection:
            system = "浣犳槸鏂囨。淇鍔╂墜銆傚彧杈撳嚭鏇挎崲鍚庣殑鐗囨鏂囨湰锛屼笉瑕佽В閲娿€?"
            user = f"閫変腑鏂囨湰:\n{selection}\n\n淇瑕佹眰:\n{analysis_instruction}\n\n{plan_hint}璇疯緭鍑烘浛鎹㈠悗鐨勫唴瀹广€?"
            buf: list[str] = []
            for delta in client.chat_stream(system=system, user=user, temperature=0.25):
                buf.append(delta)
            rewritten = app_v2._sanitize_output_text("".join(buf).strip())
            if rewritten and selection in text:
                text = text.replace(selection, rewritten, 1)
            text = app_v2._replace_question_headings(text)
        else:
            system = "浣犳槸鏂囨。淇鍔╂墜銆傝緭鍑哄畬鏁翠慨璁㈠悗鐨?Markdown 鏂囨湰銆?"
            user = f"淇瑕佹眰:\n{analysis_instruction}\n\n{plan_hint}鍘熸枃:\n{text}\n\n璇疯緭鍑轰慨璁㈠悗鐨勫畬鏁存枃鏈€?"
            buf: list[str] = []
            for delta in client.chat_stream(system=system, user=user, temperature=0.25):
                buf.append(delta)
            text = app_v2._sanitize_output_text("".join(buf).strip() or text)
            text = app_v2._replace_question_headings(text)

        if not text.strip():
            raise app_v2.HTTPException(status_code=500, detail="revision produced empty text")

        text = app_v2._postprocess_output_text(
            session,
            text,
            instruction,
            current_text=base_text,
            base_text=base_text,
        )
        app_v2._set_doc_text(session, text)
        app_v2.store.put(session)
        return {"ok": 1, "text": text, "doc_ir": session.doc_ir or {}}
