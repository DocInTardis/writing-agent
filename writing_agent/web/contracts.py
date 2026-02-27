"""Contracts module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    BAD_REQUEST = "BAD_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TIMEOUT = "TIMEOUT"


class APIError(BaseModel):
    ok: int = 0
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    instruction: str
    text: str = ""
    selection: str = ""
    compose_mode: str = "auto"
    resume_sections: list[str] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    ok: int = 1
    text: str
    problems: list[str] = Field(default_factory=list)


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
