param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000,
  [string]$IndexUrl = "",
  [switch]$SkipInstall,
  [switch]$NoWeb
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot

# A stale custom PYTHON_HOME can make venv/pip use a removed interpreter.
Remove-Item Env:PYTHON_HOME -ErrorAction SilentlyContinue

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not $SkipInstall) {
  if (-not (Test-Path $python)) {
    python -m venv .venv
  }

  $pipArgs = @("-m", "pip", "install", "-r", "requirements.txt")
  if ($IndexUrl.Trim()) {
    $pipArgs += @("--index-url", $IndexUrl.Trim())
  }
  & $python @pipArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed. Recreate .venv if its base Python was removed."
  }
}

if (-not (Test-Path $python)) {
  throw "Virtual environment not found. Run this script without -SkipInstall first."
}

$env:WRITING_AGENT_HOST = $HostAddress
$env:WRITING_AGENT_PORT = [string]$Port
if ($NoWeb) {
  Write-Host "Environment is ready."
  exit 0
}

& $python -m writing_agent.launch
