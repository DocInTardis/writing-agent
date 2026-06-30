"""OpenAI-compatible configuration resolution helpers."""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


_VALUE_SPLIT_RE = re.compile(r"[,\n;\r]+")
_BASE_URL_RE = re.compile(r'base_url\s*=\s*"([^"\r\n]+)"', flags=re.IGNORECASE)
_MODEL_RE = re.compile(r'model\s*=\s*"([^"\r\n]+)"', flags=re.IGNORECASE)
_WIRE_API_RE = re.compile(r'wire_api\s*=\s*"([^"\r\n]+)"', flags=re.IGNORECASE)
_AUTH_KEY_RE = re.compile(r'"OPENAI_API_KEY"\s*:\s*"([^"\r\n]+)"', flags=re.IGNORECASE)


@dataclass(frozen=True)
class OpenAIResolvedConfig:
    base_url: str
    api_key: str
    model: str
    timeout_s: float
    wire_api: str
    source: str


def _split_values(raw: str) -> list[str]:
    return [part.strip() for part in _VALUE_SPLIT_RE.split(str(raw or "")) if str(part or "").strip()]


def _normalize_timeout(timeout_s: float | None) -> float:
    if timeout_s is not None:
        try:
            return max(1.0, float(timeout_s))
        except Exception as _exc:
            logger.debug("Ignored error in openai_config.py: %s", _exc, exc_info=True)

    try:
        return max(1.0, float(os.environ.get("WRITING_AGENT_OPENAI_TIMEOUT_S", "60") or "60"))
    except Exception:
        return 60.0


def _normalize_model(model: str | None, fallback: str = "") -> str:
    chosen = str(model or "").strip()
    if chosen:
        return chosen
    inherited = str(os.environ.get("WRITING_AGENT_OPENAI_MODEL", "")).strip()
    if inherited:
        return inherited
    return str(fallback or "").strip() or "gpt-4o-mini"


def _normalize_wire_api(wire_api: str | None, fallback: str = "") -> str:
    chosen = str(wire_api or "").strip().lower()
    if not chosen:
        chosen = str(os.environ.get("WRITING_AGENT_OPENAI_WIRE_API", "")).strip().lower()
    if not chosen:
        chosen = str(fallback or "").strip().lower()
    if chosen == "responses":
        return "responses"
    return "chat_completions"


def _append_v1_if_missing(base_url: str) -> str:
    raw = str(base_url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except Exception:
        return raw.rstrip("/")
    path = str(parsed.path or "").strip()
    if path in {"", "/"}:
        return urlunsplit((parsed.scheme, parsed.netloc, "/v1", parsed.query, parsed.fragment)).rstrip("/")
    return raw.rstrip("/")


def _normalize_base_url(base_url: str | None, *, append_v1_if_missing: bool = False) -> str:
    chosen = str(base_url or "").strip()
    if chosen:
        normalized = chosen.rstrip("/")
        return _append_v1_if_missing(normalized) if append_v1_if_missing else normalized
    inherited = str(os.environ.get("WRITING_AGENT_OPENAI_BASE_URL", "https://api.openai.com/v1")).strip()
    return inherited.rstrip("/") or "https://api.openai.com/v1"


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return ""


def _parse_auth_json(path: Path) -> str:
    raw = _read_text(path)
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except Exception:
        match = _AUTH_KEY_RE.search(raw)
        return str(match.group(1) if match else "").strip()
    return str((data or {}).get("OPENAI_API_KEY") or "").strip()


def _parse_config_toml_base_url(path: Path) -> str:
    raw = _read_text(path)
    if not raw:
        return ""
    match = _BASE_URL_RE.search(raw)
    return str(match.group(1) if match else "").strip().rstrip("/")


def _parse_config_toml_wire_api(path: Path) -> str:
    raw = _read_text(path)
    if not raw:
        return ""
    match = _WIRE_API_RE.search(raw)
    return str(match.group(1) if match else "").strip().lower()


def _build_config(
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout_s: float,
    wire_api: str,
    source: str,
    append_v1_if_missing: bool = False,
) -> OpenAIResolvedConfig | None:
    normalized_key = str(api_key or "").strip()
    if not normalized_key:
        return None
    return OpenAIResolvedConfig(
        base_url=_normalize_base_url(base_url, append_v1_if_missing=append_v1_if_missing),
        api_key=normalized_key,
        model=_normalize_model(model),
        timeout_s=_normalize_timeout(timeout_s),
        wire_api=_normalize_wire_api(wire_api),
        source=str(source or "").strip() or "unknown",
    )


def _dedupe_configs(items: list[OpenAIResolvedConfig]) -> list[OpenAIResolvedConfig]:
    seen: set[tuple[str, str]] = set()
    out: list[OpenAIResolvedConfig] = []
    for item in items:
        key = (item.base_url, item.api_key)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _configs_from_env(*, model: str | None, timeout_s: float | None) -> list[OpenAIResolvedConfig]:
    base_url = _normalize_base_url(None)
    chosen_model = _normalize_model(model)
    chosen_timeout = _normalize_timeout(timeout_s)
    configs: list[OpenAIResolvedConfig] = []
    primary_key = str(os.environ.get("WRITING_AGENT_OPENAI_API_KEY", "")).strip()
    if primary_key:
        cfg = _build_config(
            base_url=base_url,
            api_key=primary_key,
            model=chosen_model,
            timeout_s=chosen_timeout,
            wire_api=_normalize_wire_api(None),
            source="env:WRITING_AGENT_OPENAI_API_KEY",
        )
        if cfg is not None:
            configs.append(cfg)
    for idx, extra_key in enumerate(_split_values(os.environ.get("WRITING_AGENT_OPENAI_API_KEYS", "")), start=1):
        cfg = _build_config(
            base_url=base_url,
            api_key=extra_key,
            model=chosen_model,
            timeout_s=chosen_timeout,
            wire_api=_normalize_wire_api(None),
            source=f"env:WRITING_AGENT_OPENAI_API_KEYS[{idx}]",
        )
        if cfg is not None:
            configs.append(cfg)
    return configs


def _configs_from_codex_auth(*, model: str | None, timeout_s: float | None) -> list[OpenAIResolvedConfig]:
    codex_dir = Path.home() / ".codex"
    auth_path = codex_dir / "auth.json"
    if not auth_path.exists():
        return []
    api_key = _parse_auth_json(auth_path)
    if not api_key:
        return []
    config_path = codex_dir / "config.toml"
    base_url = _parse_config_toml_base_url(config_path)
    wire_api = _parse_config_toml_wire_api(config_path)
    cfg = _build_config(
        base_url=base_url,
        api_key=api_key,
        model=_normalize_model(model),
        timeout_s=_normalize_timeout(timeout_s),
        wire_api=wire_api,
        source=str(auth_path),
        append_v1_if_missing=True,
    )
    return [cfg] if cfg is not None else []


def _iter_bat_paths() -> list[Path]:
    configured = _split_values(os.environ.get("WRITING_AGENT_OPENAI_BAT_CONFIG_PATHS", ""))
    if configured:
        return [Path(value) for value in configured]
    enabled = str(os.environ.get("WRITING_AGENT_OPENAI_BAT_DISCOVERY", "0")).strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return []
    roots = [
        Path("D:/Download"),
        Path("D:/下载"),
        Path.home() / "Download",
        Path.home() / "Downloads",
        Path.home() / "下载",
    ]
    candidates: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for pattern in ("*美刀配置*.bat", "*美刀配置*.cmd"):
            for path in root.glob(pattern):
                key = str(path.resolve()) if path.exists() else str(path)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(path)
    candidates.sort(key=lambda item: (str(item.name), str(item)), reverse=True)
    return candidates


def _config_from_bat(path: Path, *, model: str | None, timeout_s: float | None) -> OpenAIResolvedConfig | None:
    if not path.exists() or not path.is_file():
        return None
    raw = _read_text(path)
    if not raw:
        return None
    key_match = _AUTH_KEY_RE.search(raw)
    api_key = str(key_match.group(1) if key_match else "").strip()
    if not api_key:
        return None
    base_match = _BASE_URL_RE.search(raw)
    parsed_base_url = str(base_match.group(1) if base_match else "").strip()
    model_match = _MODEL_RE.search(raw)
    parsed_model = str(model_match.group(1) if model_match else "").strip()
    wire_api_match = _WIRE_API_RE.search(raw)
    parsed_wire_api = str(wire_api_match.group(1) if wire_api_match else "").strip().lower()
    return _build_config(
        base_url=parsed_base_url,
        api_key=api_key,
        model=_normalize_model(model, fallback=parsed_model),
        timeout_s=_normalize_timeout(timeout_s),
        wire_api=parsed_wire_api,
        source=str(path),
        append_v1_if_missing=True,
    )


def resolve_openai_candidates(*, model: str | None = None, timeout_s: float | None = None) -> list[OpenAIResolvedConfig]:
    env_configs = _configs_from_env(model=model, timeout_s=timeout_s)
    configured_bat_paths = bool(_split_values(os.environ.get("WRITING_AGENT_OPENAI_BAT_CONFIG_PATHS", "")))
    configs: list[OpenAIResolvedConfig] = list(env_configs)
    bat_configs: list[OpenAIResolvedConfig] = []
    for path in _iter_bat_paths():
        cfg = _config_from_bat(path, model=model, timeout_s=timeout_s)
        if cfg is not None:
            bat_configs.append(cfg)
    if configured_bat_paths:
        configs.extend(bat_configs)
        return _dedupe_configs(configs)
    if env_configs:
        return _dedupe_configs(configs)
    if str(os.environ.get("WRITING_AGENT_OPENAI_INCLUDE_CODEX_AUTH", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        configs.extend(_configs_from_codex_auth(model=model, timeout_s=timeout_s))
    configs.extend(bat_configs)
    return _dedupe_configs(configs)


def resolve_openai_primary(*, model: str | None = None, timeout_s: float | None = None) -> OpenAIResolvedConfig | None:
    candidates = resolve_openai_candidates(model=model, timeout_s=timeout_s)
    return candidates[0] if candidates else None


__all__ = [
    "OpenAIResolvedConfig",
    "resolve_openai_candidates",
    "resolve_openai_primary",
]
