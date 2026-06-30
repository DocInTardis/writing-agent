"""System Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

from writing_agent import __version__
from writing_agent.llm import OllamaClient, get_ollama_settings
from writing_agent.llm.user_config import UserConfigStore

from .base import app_v2_module


class SystemService:
    def healthz(self) -> dict:
        return {"ok": 1, "status": "ok", "service": "writing-agent"}

    def system_status(self) -> dict:
        app_v2 = app_v2_module()
        try:
            from writing_agent.web.services.workspace_service import WorkspaceService

            WorkspaceService().cleanup_expired_trash()
        except Exception:
            import logging
            logging.getLogger(__name__).warning("system_status: cleanup_expired_trash failed", exc_info=True)

        # Check user-configured provider first
        user_store = UserConfigStore()
        user_active = user_store.get_active_provider()

        if user_active is not None:
            model_status = {
                "backend": "user_configured",
                "enabled": bool(user_active.enabled),
                "provider_id": str(user_active.provider_id or ""),
                "label": str(user_active.label or user_active.provider_id or ""),
                "base_url": str(user_active.base_url or ""),
                "model": str(user_active.model or ""),
                "reachable": False,
            }
            try:
                from writing_agent.llm.providers.openai_compatible_provider import OpenAICompatibleProvider
                client = OpenAICompatibleProvider(
                    base_url=(user_active.base_url or "https://api.openai.com/v1").rstrip("/"),
                    api_key=user_active.api_key,
                    model=user_active.model or "gpt-4o-mini",
                    timeout_s=min(user_active.timeout_s, 30.0),
                )
                model_status["reachable"] = bool(client.is_running())
            except Exception:
                model_status["reachable"] = False
        else:
            settings = get_ollama_settings()
            model_status = {
                "backend": "ollama" if settings.enabled else "offline",
                "enabled": bool(settings.enabled),
                "base_url": str(settings.base_url or ""),
                "model": str(settings.model or ""),
                "reachable": False,
            }
            if settings.enabled:
                try:
                    model_status["reachable"] = bool(
                        OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s).is_running()
                    )
                except Exception:
                    model_status["reachable"] = False

        sessions = [session for _, session in app_v2.store.items()]
        workspaces = {
            "total": len(sessions),
            "active": sum(
                1
                for session in sessions
                if not bool(getattr(session, "archived", False)) and not bool(getattr(session, "trashed", False))
            ),
            "archived": sum(
                1
                for session in sessions
                if bool(getattr(session, "archived", False)) and not bool(getattr(session, "trashed", False))
            ),
            "trashed": sum(1 for session in sessions if bool(getattr(session, "trashed", False))),
        }

        try:
            library_total = len(app_v2.user_library.list_items())
        except Exception:
            library_total = 0

        try:
            rag_total = len(app_v2.rag_store.list_papers())
        except Exception:
            rag_total = 0

        return {
            "ok": 1,
            "service": "writing-agent",
            "version": __version__,
            "data_dir": str(app_v2.DATA_DIR),
            "workspace_dir": str(app_v2.DATA_DIR / "workspaces"),
            "workspaces": workspaces,
            "library": {"items": library_total},
            "rag": {"papers": rag_total},
            "model": model_status,
        }
