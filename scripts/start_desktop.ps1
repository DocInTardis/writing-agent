param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000,
  [string]$IndexUrl = "",
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot
Remove-Item Env:PYTHON_HOME -ErrorAction SilentlyContinue

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not $SkipInstall) {
  if (-not (Test-Path $python)) {
    python -m venv .venv
  }
  $pipArgs = @("-m", "pip", "install", "-e", ".[desktop]")
  if ($IndexUrl.Trim()) {
    $pipArgs += @("--index-url", $IndexUrl.Trim())
  }
  & $python @pipArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Desktop dependency installation failed."
  }
}

if (-not (Test-Path $python)) {
  throw "Virtual environment not found. Run this script without -SkipInstall first."
}

$env:WRITING_AGENT_HOST = $HostAddress
$env:WRITING_AGENT_PORT = [string]$Port
& $python -m writing_agent.desktop_app
