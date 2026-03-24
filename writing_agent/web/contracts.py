"""Contracts module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JobSubmitRequest(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    callback_url: str = ""


class JobSubmitResponse(BaseModel):
    ok: int = 1
    job_id: str
    status: str


class JobPollResponse(BaseModel):
    ok: int = 1
    job_id: str
    status: str
    result: dict[str, Any] | None = None


class WebhookEvent(BaseModel):
    event_type: str
    tenant_id: str = "default"
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "writing-agent"
