from __future__ import annotations

from pathlib import Path

from writing_agent.llm.openai_config import resolve_openai_candidates


def test_resolve_openai_candidates_loads_keys_from_bat_configs(monkeypatch, tmp_path: Path) -> None:
    first = tmp_path / "100美刀配置 .bat"
    first.write_text(
        '\n'.join(
            [
                '@echo off',
                'echo [model_providers.aixj]',
                'echo base_url = "https://aixj.vip"',
                'echo model = "gpt-5.4"',
                'echo wire_api = "responses"',
                '(',
                'echo {',
                'echo   "OPENAI_API_KEY": "sk-first-key"',
                'echo }',
                ') > "%userprofile%\\.codex\\auth.json"',
            ]
        ),
        encoding="utf-8",
    )
    second = tmp_path / "90美刀配置.bat"
    second.write_text(
        '\n'.join(
            [
                '@echo off',
                'echo [model_providers.sub2api]',
                'echo base_url = "https://vpsairobot.com"',
                'echo model = "gpt-5.4"',
                '(',
                'echo {',
                'echo   "OPENAI_API_KEY": "sk-second-key"',
                'echo }',
                ') > "%userprofile%\\.codex\\auth.json"',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("WRITING_AGENT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("WRITING_AGENT_OPENAI_API_KEYS", raising=False)
    monkeypatch.delenv("WRITING_AGENT_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("WRITING_AGENT_OPENAI_MODEL", raising=False)
    monkeypatch.setenv("WRITING_AGENT_OPENAI_BAT_CONFIG_PATHS", f"{first};{second}")

    configs = resolve_openai_candidates()

    assert len(configs) == 2
    assert configs[0].base_url == "https://aixj.vip/v1"
    assert configs[0].api_key == "sk-first-key"
    assert configs[0].wire_api == "responses"
    assert configs[1].base_url == "https://vpsairobot.com/v1"
    assert configs[1].api_key == "sk-second-key"
    assert configs[1].wire_api == "chat_completions"
    assert all(item.model == "gpt-5.4" for item in configs)


def test_resolve_openai_candidates_dedupes_env_and_bat_duplicates(monkeypatch, tmp_path: Path) -> None:
    bat_path = tmp_path / "100美刀配置 .bat"
    bat_path.write_text(
        '\n'.join(
            [
                '@echo off',
                'echo base_url = "https://api.example.com/v1"',
                'echo model = "gpt-5.4"',
                'echo   "OPENAI_API_KEY": "sk-dup-key"',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("WRITING_AGENT_OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_API_KEY", "sk-dup-key")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_BAT_CONFIG_PATHS", str(bat_path))

    configs = resolve_openai_candidates(model="gpt-5.4")

    assert len(configs) == 1
    assert configs[0].source == "env:WRITING_AGENT_OPENAI_API_KEY"
