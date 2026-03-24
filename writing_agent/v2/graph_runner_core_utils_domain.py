"""Core utility helpers split from graph_runner_core_domain.py."""

# Prompt-contract markers retained for guarded JSON chat flows:
# <task>route_prompt_json_retry</task>
# <constraints>

from __future__ import annotations

import json
import os
import re
import time

from writing_agent.v2.prompt_registry import PromptRegistry
from writing_agent.v2.prompts import build_prompt_route, instruction_language, prompt_route_metadata
from writing_agent.v2 import draft_model_domain


_PROMPT_REGISTRY = PromptRegistry()


def _base():
    from writing_agent.v2 import graph_runner_core_domain as base

    return base



def _dedupe_keep_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out



def _canonicalize_section_name(text: str) -> str:
    return str(text or "").strip()



def _escape_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")



def _split_csv_env(raw: str) -> list[str]:
    return [s.strip() for s in (raw or "").split(",") if s and s.strip()]



def _extract_json_block(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    s = s.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", s, flags=re.DOTALL)
    return match.group(0).strip() if match else s



def _require_json_response(
    *,
    client,
    system: str,
    user: str,
    stage: str,
    temperature: float,
    max_retries: int = 2,
) -> dict:
    last_err: Exception | None = None
    base_system = str(system or "")
    base_user = str(user or "")
    attempt_system = base_system
    attempt_user = base_user
    for attempt in range(1, max_retries + 1):
        try:
            raw = client.chat(system=attempt_system, user=attempt_user, temperature=temperature)
            raw_json = _extract_json_block(raw)
            if not raw_json:
                raise ValueError(f"{stage}: empty json block")
            data = json.loads(raw_json)
            if not isinstance(data, dict):
                raise ValueError(f"{stage}: json is not object")
            return data
        except Exception as exc:
            last_err = exc
            attempt_system = (
                base_system
                + "\n\nReturn strict JSON only. Do not output markdown fences or commentary."
            )
            attempt_user = (
                f"{base_user}\n"
                "<retry_reason>\n"
                "Previous output was invalid JSON. Keep original task/context and retry.\n"
                "</retry_reason>\n"
                "Return exactly one JSON object."
            )
            time.sleep(0.4 * attempt)
            continue
    raise ValueError(f"{stage}: json parse failed: {last_err}")



def _plan_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_PLAN_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(5.0, float(raw))
        except Exception:
            pass
    return 40.0



def _analysis_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_ANALYSIS_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(3.0, float(raw))
        except Exception:
            pass
    return 24.0



def _section_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_SECTION_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(10.0, float(raw))
        except Exception:
            pass
    return 180.0



def _is_evidence_enabled() -> bool:
    raw = os.environ.get("WRITING_AGENT_EVIDENCE_ENABLED", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}



def _truncate_text(text: str, *, max_chars: int = 1200) -> str:
    s = (text or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max(0, max_chars - 3)].rstrip() + "..."



def _route_prompt_for_role(
    *,
    role: str,
    instruction: str,
    intent: str,
    section_title: str = "",
    revise_scope: str = "none",
) -> tuple[object, dict[str, str]]:
    context, route = build_prompt_route(
        role=role,
        instruction=instruction,
        intent=intent,
        doc_type=_base()._resolve_doc_type_for_prompt(instruction),
        language=instruction_language(instruction),
        quality_profile=_base()._prompt_quality_profile(),
        revise_scope=revise_scope,
        section_title=section_title,
        registry=_PROMPT_REGISTRY,
    )
    meta = prompt_route_metadata(route)
    meta["prompt_intent"] = str(context.intent)
    meta["prompt_doc_type"] = str(context.doc_type)
    meta["prompt_language"] = str(context.language)
    meta["prompt_quality_profile"] = str(context.quality_profile)
    return route, meta



def _pick_draft_models(worker_models: list[str], *, agg_model: str, fallback: str) -> tuple[str, str]:
    return draft_model_domain.pick_draft_models(
        worker_models=worker_models,
        agg_model=agg_model,
        fallback=fallback,
        env_main=os.environ.get("WRITING_AGENT_DRAFT_MAIN_MODEL", "").strip(),
        env_support=os.environ.get("WRITING_AGENT_DRAFT_SUPPORT_MODEL", "").strip(),
        installed=_base()._ollama_installed_models(),
        sizes=_base()._ollama_model_sizes_gb(),
        is_embedding_model=_base()._looks_like_embedding_model,
    )



def _predict_num_tokens(*, min_chars: int, max_chars: int, is_reference: bool) -> int:
    hard_max_mode = os.environ.get("WRITING_AGENT_HARD_MAX", "0").strip() in {"1", "true", "yes"}
    base = max(900, int(round(min_chars * 2.2)))
    if max_chars > 0 and hard_max_mode:
        base = min(base, int(round(max_chars * 2.4)))
    if is_reference:
        base = min(base, 2600)
    return max(700, min(5200, base))


__all__ = [name for name in globals() if not name.startswith("__")]
