param([switch]$SkipInstall)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$dist = Join-Path $repoRoot "desktop-tauri\src-tauri\sidecar"

if (-not (Test-Path $python)) { throw "Missing .venv. Create the project environment first." }
if (-not $SkipInstall) {
  & $python -m pip install --no-cache-dir "pyinstaller==6.16.0"
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed." }
}

Set-Location $repoRoot
$dataArgs = @(
  "--add-data=$repoRoot\writing_agent\web\templates;writing_agent/web/templates",
  "--add-data=$repoRoot\writing_agent\web\static;writing_agent/web/static",
  "--add-data=$repoRoot\writing_agent\report_templates;writing_agent/report_templates",
  "--add-data=$repoRoot\writing_agent\web\edit_rules.json;writing_agent/web",
  "--add-data=$repoRoot\writing_agent\llm\tool_manifest.json;writing_agent/llm",
  "--add-data=$repoRoot\templates;templates"
)
& $python -m PyInstaller --noconfirm --clean --onedir --contents-directory runtime `
  --name writing-agent-sidecar --distpath $dist --workpath "$repoRoot\build\pyinstaller" `
  --specpath "$repoRoot\build" --collect-submodules writing_agent `
  --exclude-module PySide6 --exclude-module webview --exclude-module playwright `
  --exclude-module torch --exclude-module tensorflow --exclude-module onnxruntime `
  @dataArgs "writing_agent\sidecar.py"
if ($LASTEXITCODE -ne 0) { throw "Python sidecar build failed." }
