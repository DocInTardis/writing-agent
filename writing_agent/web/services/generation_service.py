"""鐢熸垚鏈嶅姟妯″潡锛圙eneration Service锛夈€?

鑱岃矗瀹氫綅锛堝彲绫绘瘮 Java 鐨?Service 灞傦級锛?
1. 瑙ｆ瀽骞舵爣鍑嗗寲璇锋眰鍙傛暟銆?
2. 鎵ц骞傜瓑鎺у埗涓庢枃妗ｇ骇骞跺彂閿佹帶鍒躲€?
3. 鍏堝皾璇曚綆寤惰繜蹇嵎璺緞锛屽啀杩涘叆瀹屾暣鍥剧敓鎴愭祦绋嬨€?
4. 瀵圭敓鎴愮粨鏋滃仛鍚庡鐞嗗苟鎸佷箙鍖栦細璇濈姸鎬併€?
"""

from __future__ import annotations

import re
import time

from fastapi import Request
from fastapi.responses import StreamingResponse

from writing_agent.web.domains import route_graph_metrics_domain
from writing_agent.web.idempotency import IdempotencyStore, make_idempotency_key

from .base import app_v2_module


class GenerationService:
    """Service wrapper for generate and generate_stream endpoints."""

    def __init__(self) -> None:
        self._idempotency = IdempotencyStore()

    @staticmethod
    def _xml_escape(raw: object) -> str:
        text = str(raw or "")
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _strip_fences(raw: object) -> str:
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text).strip()
            text = re.sub(r"\s*```$", "", text).strip()
        return text

    @classmethod
    def _build_revision_fallback_prompt(
        cls,
        *,
        instruction: str,
        plan_steps: list[str],
        text: str,
    ) -> tuple[str, str]:
        system = (
            "You are a constrained document revision assistant.\n"
            "Return complete Markdown only inside <revised_markdown>...</revised_markdown>.\n"
            "Do not output any text outside that tag."
        )
        plan_rows = []
        for step in plan_steps:
            clean_step = cls._xml_escape(step)
            if clean_step:
                plan_rows.append(f"<step>{clean_step}</step>")
            if len(plan_rows) >= 12:
                break
        plan_block = "\n".join(plan_rows) if plan_rows else "<step>no-explicit-plan</step>"
        user = (
            "<task>revise_full_document</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Rewrite the full document, not a summary.\n"
            "- Preserve heading structure unless instruction explicitly asks to change it.\n"
            "- Preserve markers like [[TABLE:...]] and [[FIGURE:...]] when present.\n"
            "- Do not include analysis, explanation, or JSON.\n"
            "</constraints>\n"
            f"<revision_request>\n{cls._xml_escape(instruction)}\n</revision_request>\n"
            f"<execution_plan>\n{plan_block}\n</execution_plan>\n"
            f"<original_document>\n{cls._xml_escape(text)}\n</original_document>\n"
            "Return only one block:\n"
            "<revised_markdown>\n"
            "...complete revised markdown...\n"
            "</revised_markdown>"
        )
        return system, user

    @classmethod
    def _extract_revision_fallback_text(cls, raw: object) -> str:
        text = cls._strip_fences(raw)
        match = re.search(r"<revised_markdown>\s*([\s\S]*?)\s*</revised_markdown>", text, flags=re.IGNORECASE)
        if match:
            return str(match.group(1) or "").strip()
        alt = re.search(r"<revised_text>\s*([\s\S]*?)\s*</revised_text>", text, flags=re.IGNORECASE)
        if alt:
            return str(alt.group(1) or "").strip()
        return text.strip()

    async def generate_stream(self, doc_id: str, request: Request) -> StreamingResponse:
        """Stream generation endpoint delegated to runtime implementation."""
        app_v2 = app_v2_module()
        return await app_v2.api_generate_stream(doc_id, request)

    async def generate(self, doc_id: str, request: Request) -> dict:
        """
        鍚屾鐢熸垚涓绘祦绋嬶紙闈?SSE锛夛細
        1. 璇诲彇浼氳瘽骞惰В鏋愯姹傘€?
        2. 鍋氬箓绛夊懡涓鏌ワ紙閬垮厤閲嶅鎻愪氦閲嶅璁＄畻锛夈€?
        3. 鑾峰彇鏂囨。绾х敓鎴愰攣锛堥伩鍏嶅悓涓€鏂囨。骞跺彂鍐欏叆锛夈€?
        4. 鍏堣蛋蹇嵎璺緞锛堟牸寮忎慨澶?蹇€熸敼鍐?蹇€熺敓鎴愶級銆?
        5. 蹇嵎璺緞鏈懡涓椂锛岃繘鍏ュ畬鏁?graph 鐢熸垚 + fallback銆?
        6. 鍚庡鐞嗗苟钀藉簱锛屾渶缁堥噴鏀鹃攣銆?
        """
        app_v2 = app_v2_module()
        # 闃舵1锛氫細璇濆瓨鍦ㄦ€ф牎楠屻€?
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

        # 闃舵2锛氳姹傛爣鍑嗗寲 + 骞傜瓑鎺у埗銆?
        data = await request.json()
        req = self._parse_generate_payload(app_v2, data, session=session)
        idempotency_key = self._resolve_idempotency_key(doc_id=doc_id, request=request, payload=data)
        cached = self._load_idempotent_result(idempotency_key)
        if cached is not None:
            return cached

        if not req["raw_instruction"]:
            raise app_v2.HTTPException(status_code=400, detail="instruction required")

        # 闃舵3锛氭枃妗ｇ骇骞跺彂閿侊紙闃叉鍚屼竴鏂囨。骞跺彂鐢熸垚瀵艰嚧鐘舵€佽鐩栵級銆?
        token = app_v2._try_begin_doc_generation_with_wait(doc_id, mode="generate")
        if not token:
            raise app_v2.HTTPException(status_code=409, detail=app_v2._generation_busy_message(doc_id))

        try:
            # 闃舵4锛氭瀯閫犳渶缁堟寚浠わ紙缁勫悎妯″紡/缁啓绔犺妭/閿氱偣绛夛級銆?
            compose_instruction = self._build_generation_instruction(
                app_v2=app_v2,
                session=session,
                raw_instruction=req["raw_instruction"],
                compose_mode=req["compose_mode"],
                resume_sections=req["resume_sections"],
                cursor_anchor=req["cursor_anchor"],
            )
            # overwrite 妯″紡涓嬩笉甯﹀巻鍙叉鏂囷紱鍏朵粬妯″紡浼樺厛鍙栬姹備腑鐨?text锛屽叾娆′細璇濇鏂囥€?
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

            # 闃舵5锛氬厛灏濊瘯浣庡欢杩熷揩鎹疯矾寰勶紝鍛戒腑鍒欑洿鎺ヨ繑鍥炪€?
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

            # 闃舵6锛氭ā鍨嬪彲鐢ㄦ€ф鏌ワ紙鏈湴鎺ㄧ悊鏈嶅姟涓嶅彲鐢ㄦ椂鐩存帴鎶ラ敊锛夈€?
            ok, msg = app_v2._ensure_ollama_ready()
            if not ok:
                raise app_v2.HTTPException(status_code=400, detail=msg)

            # 闃舵7锛氬噯澶囧浘鐢熸垚閰嶇疆锛堝垎鏋愭寚浠ゃ€侀暱搴︾洰鏍囥€佸苟鍙戝弬鏁扮瓑锛夈€?
            analysis_instruction, cfg, target_chars = self._prepare_generation_config(
                app_v2=app_v2,
                session=session,
                raw_instruction=req["raw_instruction"],
                compose_instruction=compose_instruction,
                resume_sections=req["resume_sections"],
                base_text=base_text,
            )

            # 闃舵8锛氭墽琛?graph 鐢熸垚锛涘紓甯告椂鑷姩闄嶇骇鍒?single-pass 鍏滃簳銆?
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
            # 闃舵9锛氱粺涓€鍚庡鐞嗭紙娓呯悊鍥炲０銆佷慨澶嶇粨鏋勭瓑锛夊苟鎸佷箙鍖栥€?
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
            # 闃舵10锛氭棤璁烘垚鍔熷け璐ラ兘閲婃斁鏂囨。绾х敓鎴愰攣銆?
            app_v2._finish_doc_generation(doc_id, token)

    def _parse_generate_payload(self, app_v2, data: dict, *, session=None) -> dict:
        """Normalize external request payload into internal fields."""
        selection_payload = data.get("selection")
        selection_text = (
            str(selection_payload.get("text") or "")
            if isinstance(selection_payload, dict)
            else str(selection_payload or "")
        )
        incoming_plan_confirm = data.get("plan_confirm")
        if incoming_plan_confirm is None:
            incoming_plan_confirm = self._load_plan_confirm_state(app_v2, session=session)
        return {
            "raw_instruction": str(data.get("instruction") or "").strip(),
            "current_text": str(data.get("text") or ""),
            "selection_payload": selection_payload,
            "selection_text": selection_text,
            "context_policy": data.get("context_policy"),
            "compose_mode": app_v2._normalize_compose_mode(data.get("compose_mode")),
            "resume_sections": app_v2._normalize_resume_sections(data.get("resume_sections")),
            "cursor_anchor": str(data.get("cursor_anchor") or ""),
            "confirm_apply": bool(data.get("confirm_apply") is True),
            "plan_confirm": self._normalize_plan_confirm_payload(incoming_plan_confirm),
        }

    @staticmethod
    def _normalize_plan_confirm_payload(raw: object) -> dict:
        data = raw if isinstance(raw, dict) else {}
        decision_raw = str(data.get("decision") or "").strip().lower()
        if decision_raw in {"stop", "terminate", "cancel", "reject"}:
            decision = "interrupted"
        elif decision_raw in {"interrupted", "approved"}:
            decision = decision_raw
        else:
            decision = "approved"
        try:
            score = int(data.get("score") or 0)
        except Exception:
            score = 0
        score = max(0, min(5, score))
        note = str(data.get("note") or "").strip()[:300]
        return {
            "decision": decision,
            "score": score,
            "note": note,
        }

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

    def _resolve_idempotency_key(self, *, doc_id: str, request: Request, payload: dict) -> str:
        """Resolve idempotency key from header or deterministic payload hash."""
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
        """Compose final instruction from compose mode and resume hints."""
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

    def _build_shortcut_result(self, *, app_v2, session, text: str, instruction: str, base_text: str) -> dict:
        """Apply shortcut result and persist text/doc_ir into session."""
        if base_text.strip():
            # Save a rollback point only when we are about to apply a real mutation.
            if base_text != session.doc_text:
                app_v2._set_doc_text(session, base_text)
            app_v2._auto_commit_version(session, "auto: before update")
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

    def _build_confirmation_shortcut_result(
        self,
        *,
        app_v2,
        base_text: str,
        note: str,
        confirmation_reason: str,
        risk_level: str,
        source: str,
        operations_count: int,
    ) -> dict:
        # Confirmation-required response must not mutate document/session.
        return {
            "ok": 1,
            "text": base_text,
            "problems": [],
            "doc_ir": app_v2._safe_doc_ir_payload(base_text),
            "note": note,
            "requires_confirmation": True,
            "confirmation_reason": confirmation_reason or "high_risk_edit",
            "risk_level": risk_level or "high",
            "plan_source": source or "rules",
            "operations_count": int(operations_count or 0),
            "confirmation_action": "confirm_apply",
        }

    def _prepare_generation_config(self, *, app_v2, session, raw_instruction: str, compose_instruction: str, resume_sections: list[str], base_text: str):
        """Prepare analysis output and generation config for graph execution."""
        # 鍏堝仛鎸囦护鍒嗘瀽锛堝甫瓒呮椂淇濇姢锛夛紝閬垮厤鍒嗘瀽闃舵闃诲鏁翠綋閾捐矾銆?
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

        # 鑻ユ湭鎸囧畾妯℃澘缁撴瀯锛屽垯灏濊瘯浠庢寚浠よ嚜鍔ㄦ帹鏂ぇ绾层€?
        if (not resume_sections) and (not session.template_required_h2) and (not session.template_outline):
            auto_outline = app_v2._default_outline_from_instruction(raw_instruction)
            if auto_outline:
                session.template_required_h2 = auto_outline
                app_v2.store.put(session)

        # 鐩爣瀛楁暟瀛樺湪鏃讹紝缁欏唴閮ㄧ敓鎴愰鐣欎竴瀹?margin锛屽噺灏戝悗缁ˉ鍋跨敓鎴愩€?
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
                # Keep only a lower bound to avoid truncating complete paragraphs at tail.
                max_total_chars=0,
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
        compose_mode: str,
        resume_sections: list[str],
        base_text: str,
        cfg,
        target_chars: int,
        plan_confirm: dict,
    ) -> tuple[str, list[str], dict | None]:
        """Run graph generation with single-pass fallback on failure/insufficient output."""
        required_h2 = list(resume_sections) if resume_sections else list(session.template_required_h2 or [])
        required_outline = [] if resume_sections else list(session.template_outline or [])

        final_text: str | None = None
        problems: list[str] = []
        graph_meta: dict | None = None
        prompt_trace: list[dict] = []
        terminal_status = "success"
        failure_reason = ""
        quality_snapshot: dict = {}
        engine_failover = False
        started = time.time()
        use_route_graph = False

        def _elapsed_ms() -> float:
            return max(0.0, (time.time() - started) * 1000.0)

        def _record_metric(
            event: str,
            *,
            path: str,
            fallback_triggered: bool | None = None,
            fallback_recovered: bool | None = None,
            error_code: str = "",
        ) -> None:
            route_id = ""
            route_entry = ""
            engine = ""
            if isinstance(graph_meta, dict):
                route_id = str(graph_meta.get("route_id") or "")
                route_entry = str(graph_meta.get("route_entry") or "")
                engine = str(graph_meta.get("engine") or "")
            route_graph_metrics_domain.record_route_graph_metric(
                event,
                phase="generate",
                path=path,
                route_id=route_id,
                route_entry=route_entry,
                engine=engine,
                fallback_triggered=fallback_triggered,
                fallback_recovered=fallback_recovered,
                error_code=error_code,
                elapsed_ms=_elapsed_ms(),
                extra={
                    "compose_mode": str(compose_mode or "").strip(),
                    "resume_sections_count": int(len(resume_sections or [])),
                },
            )

        try:
            expand_outline = bool((session.generation_prefs or {}).get("expand_outline", False))
            use_route_graph = str(app_v2.os.environ.get("WRITING_AGENT_USE_ROUTE_GRAPH", "0")).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if use_route_graph and hasattr(app_v2, "run_generate_graph_dual_engine"):
                if route_graph_metrics_domain.should_inject_route_graph_failure(phase="generate"):
                    raise RuntimeError("E_INJECTED_ROUTE_GRAPH_FAILURE")
                out = app_v2.run_generate_graph_dual_engine(
                    instruction=instruction,
                    current_text=base_text,
                    required_h2=required_h2,
                    required_outline=required_outline,
                    expand_outline=expand_outline,
                    config=cfg,
                    compose_mode=compose_mode,
                    resume_sections=resume_sections,
                    format_only=False,
                    plan_confirm=plan_confirm,
                )
                if isinstance(out, dict):
                    final_text = str(out.get("text") or "")
                    problems = list(out.get("problems") or [])
                    status_raw = str(out.get("terminal_status") or "").strip().lower()
                    if status_raw in {"success", "failed", "interrupted"}:
                        terminal_status = status_raw
                    failure_reason = str(out.get("failure_reason") or "").strip()
                    if isinstance(out.get("quality_snapshot"), dict):
                        quality_snapshot = dict(out.get("quality_snapshot") or {})
                    raw_prompt_trace = out.get("prompt_trace")
                    if isinstance(raw_prompt_trace, list):
                        prompt_trace = [dict(x) for x in raw_prompt_trace if isinstance(x, dict)]
                    graph_meta = {
                        "path": "route_graph",
                        "trace_id": str(out.get("trace_id") or ""),
                        "engine": str(out.get("engine") or ""),
                        "route_id": str(out.get("route_id") or ""),
                        "route_entry": str(out.get("route_entry") or ""),
                        "plan_feedback": dict(out.get("plan_feedback") or {}),
                    }
                    if terminal_status != "success" and failure_reason and failure_reason not in problems:
                        problems.append(failure_reason)
                    if str(final_text).strip():
                        _record_metric(
                            "route_graph_success",
                            path="route_graph",
                            fallback_triggered=False,
                            fallback_recovered=False,
                        )
            else:
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
                    if ev.get("event") == "prompt_route":
                        meta = ev.get("metadata") if isinstance(ev.get("metadata"), dict) else {}
                        prompt_trace.append(
                            {
                                "stage": str(ev.get("stage") or ""),
                                "metadata": dict(meta),
                            }
                        )
                        continue
                    if ev.get("event") == "final":
                        final_text = str(ev.get("text") or "")
                        problems = list(ev.get("problems") or [])
                        status_raw = str(ev.get("status") or "").strip().lower()
                        if status_raw in {"success", "failed", "interrupted"}:
                            terminal_status = status_raw
                        failure_reason = str(ev.get("failure_reason") or "").strip()
                        if isinstance(ev.get("quality_snapshot"), dict):
                            quality_snapshot = dict(ev.get("quality_snapshot") or {})
                        if terminal_status != "success" and failure_reason and failure_reason not in problems:
                            problems.append(failure_reason)
                        _record_metric(
                            "legacy_graph_success",
                            path="legacy_graph",
                            fallback_triggered=False,
                            fallback_recovered=False,
                        )
                        break
        except Exception as e:
            _record_metric(
                "graph_failed",
                path="route_graph" if use_route_graph else "legacy_graph",
                fallback_triggered=True,
                fallback_recovered=False,
                error_code=route_graph_metrics_domain.extract_error_code(e, default="E_GRAPH_FAILED"),
            )
            try:
                final_text = app_v2._single_pass_generate(
                    session,
                    instruction=instruction,
                    current_text=base_text,
                    target_chars=target_chars,
                )
                engine_failover = True
                terminal_status = "interrupted"
                failure_reason = "engine_failover_graph_failed"
                quality_snapshot = {
                    "status": terminal_status,
                    "reason": failure_reason,
                    "problem_count": len(problems),
                    "needs_review": True,
                }
                if failure_reason not in problems:
                    problems.append(failure_reason)
                _record_metric(
                    "fallback_recovered",
                    path="single_pass",
                    fallback_triggered=True,
                    fallback_recovered=True,
                )
            except Exception as ee:
                _record_metric(
                    "fallback_failed",
                    path="single_pass",
                    fallback_triggered=True,
                    fallback_recovered=False,
                    error_code=route_graph_metrics_domain.extract_error_code(ee, default="E_FALLBACK_FAILED"),
                )
                raise app_v2.HTTPException(status_code=500, detail=f"generation failed: {e}; fallback failed: {ee}") from ee

        no_semantic_failover_reasons = {
            "analysis_needs_clarification",
            "analysis_guard_failed",
            "section_language_mismatch",
            "section_hierarchy_insufficient",
            "must_include_missing",
            "keyword_domain_mismatch",
            "missing_section_headings",
            "section_content_missing",
        }
        no_semantic_failover = (
            terminal_status in {"failed", "interrupted"}
            and str(failure_reason or "").strip() in no_semantic_failover_reasons
        )
        if (not final_text or len(str(final_text).strip()) < 20) and not no_semantic_failover:
            _record_metric(
                "graph_insufficient",
                path="route_graph" if use_route_graph else "legacy_graph",
                fallback_triggered=True,
                fallback_recovered=False,
                error_code="E_TEXT_INSUFFICIENT",
            )
            try:
                final_text = app_v2._single_pass_generate(
                    session,
                    instruction=instruction,
                    current_text=base_text,
                    target_chars=target_chars,
                )
                engine_failover = True
                terminal_status = "interrupted"
                failure_reason = "engine_failover_insufficient_output"
                quality_snapshot = {
                    "status": terminal_status,
                    "reason": failure_reason,
                    "problem_count": len(problems),
                    "needs_review": True,
                }
                if failure_reason not in problems:
                    problems.append(failure_reason)
                _record_metric(
                    "fallback_recovered",
                    path="single_pass",
                    fallback_triggered=True,
                    fallback_recovered=True,
                )
            except Exception as e:
                _record_metric(
                    "fallback_failed",
                    path="single_pass",
                    fallback_triggered=True,
                    fallback_recovered=False,
                    error_code=route_graph_metrics_domain.extract_error_code(e, default="E_FALLBACK_FAILED"),
                )
                raise app_v2.HTTPException(status_code=500, detail=f"generation produced insufficient text: {e}") from e

        if graph_meta is None:
            graph_meta = {}
        graph_meta["terminal_status"] = terminal_status if terminal_status in {"success", "failed", "interrupted"} else "failed"
        graph_meta["failure_reason"] = failure_reason
        graph_meta["quality_snapshot"] = dict(quality_snapshot or {})
        graph_meta["engine_failover"] = bool(engine_failover)
        graph_meta["needs_review"] = bool(engine_failover)
        if prompt_trace:
            graph_meta["prompt_trace"] = prompt_trace[-24:]

        return str(final_text), problems, graph_meta

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
        graph_meta: dict | None = None
        try:
            use_route_graph = str(app_v2.os.environ.get("WRITING_AGENT_USE_ROUTE_GRAPH", "0")).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if use_route_graph and hasattr(app_v2, "run_generate_graph_dual_engine"):
                out = app_v2.run_generate_graph_dual_engine(
                    instruction=instruction,
                    current_text=current_text,
                    required_h2=[section],
                    required_outline=[],
                    expand_outline=False,
                    config=cfg,
                    compose_mode="continue",
                    resume_sections=[section],
                    format_only=False,
                )
                if isinstance(out, dict):
                    final_text = str(out.get("text") or "")
                    graph_meta = {
                        "path": "route_graph",
                        "trace_id": str(out.get("trace_id") or ""),
                        "engine": str(out.get("engine") or ""),
                        "route_id": str(out.get("route_id") or ""),
                        "route_entry": str(out.get("route_entry") or ""),
                    }
            else:
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
        out = {"ok": 1, "text": updated, "doc_ir": final_doc_ir}
        if graph_meta:
            out["graph_meta"] = graph_meta
        return out

    async def revise_doc(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()
        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")

        data = await request.json()
        instruction = str(data.get("instruction") or "").strip()
        raw_selection = data.get("selection")
        selection_text = (
            str(raw_selection.get("text") or "")
            if isinstance(raw_selection, dict)
            else str(raw_selection or "")
        ).strip()
        selection_payload: object = raw_selection
        if not selection_text:
            fallback_selection_text = str(data.get("selection_text") or "").strip()
            if fallback_selection_text:
                selection_text = fallback_selection_text
                if not isinstance(selection_payload, dict):
                    selection_payload = fallback_selection_text
        context_policy = data.get("context_policy")
        allow_unscoped_fallback = bool(data.get("allow_unscoped_fallback") is True)
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

        decision = app_v2._revision_decision_with_model(
            base_url=settings.base_url,
            model=model,
            instruction=analysis_instruction,
            selection=selection_text,
            text=text,
        )
        if isinstance(decision, dict) and decision.get("should_apply") is False:
            return {"ok": 1, "text": text}

        plan_steps = []
        if isinstance(decision, dict):
            plan_steps = [str(x).strip() for x in (decision.get("plan") or []) if str(x).strip()]

        revision_status: dict[str, object] = {}
        if selection_text:
            def _capture_revision_status(payload: dict[str, object]) -> None:
                if isinstance(payload, dict):
                    revision_status.update(payload)

            revised = app_v2._try_revision_edit(
                session=session,
                instruction=analysis_instruction,
                text=text,
                selection=selection_payload if selection_payload is not None else selection_text,
                analysis=analysis,
                context_policy=context_policy,
                report_status=_capture_revision_status,
            )
            if revised:
                text, note = revised
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
                out = {"ok": 1, "text": text, "doc_ir": session.doc_ir or {}, "note": note}
                if revision_status:
                    out["revision_meta"] = revision_status
                return out
            if not allow_unscoped_fallback:
                out = {"ok": 1, "text": text, "doc_ir": session.doc_ir or {}, "applied": False}
                if revision_status:
                    out["revision_meta"] = revision_status
                return out

        client = app_v2.OllamaClient(base_url=settings.base_url, model=model, timeout_s=settings.timeout_s)
        system, user = self._build_revision_fallback_prompt(
            instruction=analysis_instruction,
            plan_steps=plan_steps,
            text=text,
        )
        buf: list[str] = []
        for delta in client.chat_stream(system=system, user=user, temperature=0.25):
            buf.append(delta)
        raw_fallback = "".join(buf).strip()
        parsed_fallback = self._extract_revision_fallback_text(raw_fallback)
        text = app_v2._sanitize_output_text(parsed_fallback or text)
        if app_v2._looks_like_prompt_echo(text, analysis_instruction):
            text = base_text
        normalized_text = str(text or "").strip().lower()
        if normalized_text and normalized_text in {
            str(analysis_instruction or "").strip().lower(),
            str(instruction or "").strip().lower(),
        }:
            text = base_text
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
        out = {"ok": 1, "text": text, "doc_ir": session.doc_ir or {}}
        if revision_status:
            out["revision_meta"] = revision_status
        return out



