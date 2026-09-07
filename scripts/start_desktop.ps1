param([switch]$SkipInstall)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Missing .venv. Install the Python project dependencies first." }

& (Join-Path $PSScriptRoot "build_frontend.ps1") -SkipInstall:$SkipInstall
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $repoRoot "desktop-tauri")
if (-not $SkipInstall) {
  & npm ci
  if ($LASTEXITCODE -ne 0) { throw "Tauri dependency installation failed." }
}
$env:WRITING_AGENT_PROJECT_ROOT = $repoRoot
& npm run dev
exit $LASTEXITCODE
