"""Headless contracts for the Tauri 2 desktop shell."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

from writing_agent import launch

ROOT = Path(__file__).resolve().parents[2]


def test_tauri_shell_is_local_private_and_has_no_privileged_frontend_plugins() -> None:
    config = json.loads((ROOT / "desktop-tauri/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    capability = json.loads((ROOT / "desktop-tauri/src-tauri/capabilities/default.json").read_text(encoding="utf-8"))
    source = (ROOT / "desktop-tauri/src-tauri/src/main.rs").read_text(encoding="utf-8")
    assert config["app"]["windows"] == []
    assert config["bundle"]["targets"] == ["nsis"]
    assert config["bundle"]["windows"]["nsis"]["installMode"] == "currentUser"
    assert capability["permissions"] == ["core:default"]
    assert "127.0.0.1" in source
    assert ".incognito(true)" in source
    assert ".data_directory(" in source
    assert ".on_download(" in source
    assert "CREATE_NO_WINDOW" in source
    assert "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE" in source
    assert "child.kill()" in source
    assert "Duration::from_secs(30)" in source


def test_default_launcher_starts_built_tauri_binary(tmp_path: Path) -> None:
    executable = tmp_path / "desktop-tauri/src-tauri/target/release/writing-agent-desktop.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    fake_launch = tmp_path / "writing_agent/launch.py"
    fake_launch.parent.mkdir()
    fake_launch.touch()
    with patch.object(launch, "__file__", str(fake_launch)), patch.object(launch.subprocess, "call", return_value=0) as call:
        assert launch.main([]) == 0
    call.assert_called_once_with([str(executable)], cwd=str(tmp_path))


def test_missing_desktop_build_does_not_fall_back_to_browser(tmp_path: Path) -> None:
    fake_launch = tmp_path / "writing_agent/launch.py"
    fake_launch.parent.mkdir()
    fake_launch.touch()
    output = io.StringIO()
    with patch.object(launch, "__file__", str(fake_launch)), patch("sys.stderr", output):
        assert launch.main([]) == 2
    assert "start_desktop.ps1" in output.getvalue()


def test_explicit_web_mode_remains_available_for_development() -> None:
    with patch("uvicorn.run") as run, patch.object(launch, "_pick_available_port", return_value=8123):
        assert launch.main(["--web"]) == 0
    run.assert_called_once()


def test_desktop_sources_do_not_start_or_download_models() -> None:
    sources = [ROOT / "writing_agent/sidecar.py", ROOT / "desktop-tauri/src-tauri/src/main.rs", ROOT / "scripts/start_desktop.ps1"]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources).lower()
    assert "ollama pull" not in combined
    assert "download_model" not in combined
    assert "playwright" not in combined
    assert "pywebview" not in combined
